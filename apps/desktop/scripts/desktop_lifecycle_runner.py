"""Explicit, isolated Windows Desktop/Sidecar lifecycle evidence runner.

The runner never discovers an artifact, starts a development server, scans a
machine-wide process list, or clears an existing Workspace.  JSON is the
source of truth; Markdown is only a projection of that JSON.  Linux and other
platforms are intentionally reported as unsupported/skipped for now.
"""

from __future__ import annotations

import argparse
import json
import ntpath
import os
import platform
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


LOOPBACK = "127.0.0.1"
MANIFEST = "agent-audit-workspace.json"
HISTORY_DB = "agent_audit.sqlite3"
STATUS_FILE = "sidecar.status.json"
MAX_ITERATIONS = 100
HTTP_BODY_LIMIT = 64 * 1024
PROCESS_QUERY_TIMEOUT = 10.0


class RunnerError(RuntimeError):
    """A safe, user-facing runner setup error."""


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int | None
    path: str | None
    created: str | None
    working_set: int | None

    @property
    def name(self) -> str | None:
        return Path(self.path).name if self.path else None

    def public(self, artifact: Path) -> dict[str, Any]:
        kind = "artifact" if _same_path(self.path, artifact) else (
            "sidecar" if self.name and "sidecar" in self.name.lower() else "unknown"
        )
        return {
            "pid": self.pid,
            "parentPid": self.parent_pid,
            "executableName": self.name,
            "kind": kind,
            "workingSetBytes": self.working_set,
            "identityObserved": bool(self.path and self.created),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _elapsed(start: float, end: float | None = None) -> int:
    return max(0, int(round(((end or time.monotonic()) - start) * 1000)))


def _safe(value: object, paths: tuple[Path, ...] = ()) -> str:
    text = str(value).strip() or type(value).__name__
    for path in paths:
        text = text.replace(str(path), "<isolated-path>")
        text = text.replace(str(path).replace("\\", "/"), "<isolated-path>")
    return " ".join(text.split())[:500]


def _same_path(value: str | None, expected: Path) -> bool:
    if not value:
        return False
    try:
        def canonical(path: str) -> str:
            text = path.strip().replace("/", "\\")
            if text.startswith("\\\\?\\UNC\\"):
                text = "\\\\" + text[8:]
            elif text.startswith("\\\\?\\"):
                text = text[4:]
            return ntpath.normcase(ntpath.normpath(text))

        return canonical(value) == canonical(str(expected))
    except (OSError, TypeError, ValueError):
        return False


def _absolute(raw: str, label: str) -> Path:
    value = raw.strip()
    if not value:
        raise RunnerError(f"{label} 不能为空")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RunnerError(f"{label} 必须是绝对路径")
    path = path.resolve(strict=False)
    if path.parent == path:
        raise RunnerError(f"{label} 不能是文件系统根目录")
    return path


def _prepare_dirs(output_raw: str, home_raw: str) -> tuple[Path, Path, Path]:
    output = _absolute(output_raw, "--output-dir")
    home_input = Path(home_raw.strip()).expanduser()
    if home_input.is_symlink():
        raise RunnerError("--agent-audit-home 不能是符号链接")
    home = _absolute(home_raw, "--agent-audit-home")
    if output == home or output.is_relative_to(home) or home.is_relative_to(output):
        raise RunnerError("--output-dir 与 --agent-audit-home 必须是相互独立的目录")
    if output.exists() and not output.is_dir():
        raise RunnerError("--output-dir 必须是目录")
    if home.exists() and not home.is_dir():
        raise RunnerError("--agent-audit-home 必须是目录")
    output.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    if any(home.iterdir()):
        raise RunnerError("--agent-audit-home 必须是新的空隔离目录；不会覆盖已有数据")
    token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = output / f"desktop-lifecycle-{token}-{os.getpid()}"
    if run_dir.exists():
        raise RunnerError("无法创建唯一验收工件目录")
    run_dir.mkdir()
    return output, home, run_dir


def _powershell() -> Path | None:
    root = os.environ.get("SystemRoot", "").strip()
    if not root:
        return None
    path = Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    return path if path.is_file() else None


def _ps_json(script: str) -> tuple[Any | None, str | None]:
    executable = _powershell()
    if executable is None:
        return None, "powershell_unavailable"
    utf8_prefix = (
        "$utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false\n"
        "[Console]::OutputEncoding = $utf8NoBom\n"
        "$OutputEncoding = $utf8NoBom\n"
    )
    try:
        completed = subprocess.run(
            [
                str(executable),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                utf8_prefix + script,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROCESS_QUERY_TIMEOUT,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "process_query_failed"
    output = completed.stdout.strip()
    if not output:
        return [], None
    try:
        return json.loads(output), None
    except json.JSONDecodeError:
        return None, "process_query_invalid_json"


def _process_rows(payload: Any) -> list[ProcessInfo]:
    rows = payload if isinstance(payload, list) else [payload]
    result: list[ProcessInfo] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            pid = int(row["ProcessId"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            parent = None if row.get("ParentProcessId") is None else int(row["ParentProcessId"])
        except (TypeError, ValueError):
            parent = None
        try:
            working = None if row.get("WorkingSetBytes") is None else int(row["WorkingSetBytes"])
        except (TypeError, ValueError):
            working = None
        result.append(
            ProcessInfo(
                pid=pid,
                parent_pid=parent,
                path=str(row["ExecutablePath"]) if row.get("ExecutablePath") else None,
                created=str(row["CreationDate"]) if row.get("CreationDate") else None,
                working_set=working,
            )
        )
    return result


def _process(pid: int, tree: bool = False) -> tuple[list[ProcessInfo], str | None]:
    if tree:
        body = rf'''
$ErrorActionPreference = "SilentlyContinue"
function Find-Tree([int] $id) {{
  $w = Get-CimInstance Win32_Process -Filter ("ProcessId = {{0}}" -f $id)
  if ($null -eq $w) {{ return }}
  $p = Get-Process -Id $id -ErrorAction SilentlyContinue
  [pscustomobject]@{{ ProcessId=[int]$w.ProcessId; ParentProcessId=[int]$w.ParentProcessId; ExecutablePath=[string]$w.ExecutablePath; CreationDate=[string]$w.CreationDate; WorkingSetBytes=if($null -eq $p){{$null}}else{{[int64]$p.WorkingSet64}} }}
  $children = Get-CimInstance Win32_Process -Filter ("ParentProcessId = {{0}}" -f $id)
  foreach ($child in $children) {{ Find-Tree ([int]$child.ProcessId) }}
}}
$rows = @(Find-Tree {pid})
if ($rows.Count -eq 0) {{ "[]" }} else {{ $rows | ConvertTo-Json -Compress }}
'''
    else:
        body = rf'''
$ErrorActionPreference = "SilentlyContinue"
$w = Get-CimInstance Win32_Process -Filter ("ProcessId = {{0}}" -f {pid})
if ($null -eq $w) {{ "[]" }} else {{
  $p = Get-Process -Id {pid} -ErrorAction SilentlyContinue
  [pscustomobject]@{{ ProcessId=[int]$w.ProcessId; ParentProcessId=[int]$w.ParentProcessId; ExecutablePath=[string]$w.ExecutablePath; CreationDate=[string]$w.CreationDate; WorkingSetBytes=if($null -eq $p){{$null}}else{{[int64]$p.WorkingSet64}} }} | ConvertTo-Json -Compress
}}
'''
    payload, error = _ps_json(body)
    return (_process_rows(payload) if error is None and payload is not None else [], error)


def _working_set(processes: list[ProcessInfo]) -> int | None:
    values = [p.working_set for p in processes if p.working_set is not None]
    return sum(values) if values else None


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "not_found"
    except (OSError, UnicodeError):
        return None, "read_failed"
    except json.JSONDecodeError:
        return None, "invalid_json"
    return (value, None) if isinstance(value, dict) else (None, "not_object")


def _safe_dir(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\\" in value or ":" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _workspace(home: Path) -> dict[str, Any]:
    root = home / "workspaces" / "default"
    manifest, error = _read_json(root / MANIFEST)
    output: dict[str, Any] = {
        "rootPresent": root.is_dir(),
        "manifest": {"status": "not_present", "readable": False, "error": error},
        "sqlite": {
            "status": "not_present",
            "readable": False,
            "integrity": None,
            "rowCount": None,
            "error": None,
        },
    }
    if error or manifest is None:
        return output
    # Workspace manifests are serialized with the shared camelCase DTO alias.
    directories = ("documentsDir", "contractDir", "casesDir", "historyDir", "exportsDir")
    states = []
    valid = bool(manifest.get("id")) and bool(manifest.get("name"))
    history: Path | None = None
    for member in directories:
        value = manifest.get(member)
        safe = _safe_dir(value)
        candidate = root / value if safe else None
        present = bool(candidate and candidate.is_dir())
        states.append({"name": member, "present": present})
        valid = valid and safe and present
        if member == "historyDir" and safe and candidate is not None:
            history = candidate
    output["manifest"] = {
        "status": "readable" if valid else "invalid_workspace",
        "readable": valid,
        "requiredDirectories": states,
        "error": None if valid else "manifest_or_directory_invalid",
    }
    if history is None or not (history / HISTORY_DB).is_file():
        return output
    database = history / HISTORY_DB
    connection: sqlite3.Connection | None = None
    output["sqlite"]["status"] = "unreadable"
    try:
        connection = sqlite3.connect(
            f"file:{database.resolve().as_posix()}?mode=ro", uri=True, timeout=1.0
        )
        check = connection.execute("PRAGMA integrity_check").fetchone()
        integrity = str(check[0]) if check else "unknown"
        output["sqlite"]["integrity"] = integrity
        output["sqlite"]["readable"] = integrity == "ok"
        output["sqlite"]["status"] = "readable" if integrity == "ok" else "invalid"
        if integrity == "ok":
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            count = 0
            for row in tables:
                table = row[0]
                if isinstance(table, str) and table.replace("_", "").isalnum():
                    count += int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            output["sqlite"]["rowCount"] = count
    except (OSError, sqlite3.Error):
        output["sqlite"]["error"] = "sqlite_read_failed"
    finally:
        if connection is not None:
            connection.close()
    if not output["sqlite"]["readable"] and output["sqlite"]["error"] is None:
        output["sqlite"]["error"] = "integrity_check_failed"
    return output


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(req.full_url, code, "redirect_forbidden", headers, fp)


_HTTP = urllib.request.build_opener(_NoRedirect)


def _health(port: int) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://{LOOPBACK}:{port}/api/health", method="GET", headers={"Connection": "close"}
    )
    try:
        with _HTTP.open(request, timeout=1.0) as response:
            chunks: list[bytes] = []
            remaining = HTTP_BODY_LIMIT
            while remaining:
                chunk = response.read(min(8192, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            if response.status != 200:
                return {"status": "failed", "httpStatus": response.status, "error": "http_error"}
            try:
                payload = json.loads(b"".join(chunks).decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                return {"status": "failed", "httpStatus": 200, "error": "invalid_health_json"}
            if not isinstance(payload, dict) or payload.get("status") != "ready":
                return {"status": "failed", "httpStatus": 200, "error": "health_not_ready"}
            if payload.get("host") not in (None, LOOPBACK):
                return {"status": "failed", "httpStatus": 200, "error": "health_host_not_loopback"}
            return {"status": "ready", "httpStatus": 200, "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": "failed", "httpStatus": exc.code, "error": "http_error"}
    except (OSError, urllib.error.URLError):
        return {"status": "not_ready", "httpStatus": None, "error": "connection_failed"}


def _port_release(port: int | None, timeout: float) -> dict[str, Any]:
    if port is None:
        return {"status": "not_observed", "error": None}
    deadline = time.monotonic() + min(timeout, 8.0)
    last: str | None = None
    while time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind((LOOPBACK, port))
            return {"status": "released", "error": None}
        except OSError as exc:
            last = type(exc).__name__
            time.sleep(0.1)
    return {"status": "occupied", "error": last}


def _launch(artifact: Path, kind: str, home: Path, status: Path) -> tuple[subprocess.Popen[bytes], int | None]:
    command = [str(artifact)]
    port: int | None = None
    if kind == "sidecar":
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind((LOOPBACK, 0))
            port = int(listener.getsockname()[1])
        command.extend(["--host", LOOPBACK, "--port", str(port), "--workspace", str(home / "workspaces" / "default"), "--ready-file", str(status)])
    environment = os.environ.copy()
    environment["AGENT_AUDIT_HOME"] = str(home)
    environment.pop("AGENT_AUDIT_PROVIDER_API_KEY", None)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        process = subprocess.Popen(command, cwd=str(artifact.parent), env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    except (OSError, ValueError) as exc:
        raise RunnerError("无法启动指定 Desktop/Sidecar artifact") from exc
    return process, port


def _ready(process: subprocess.Popen[bytes], status: Path, home: Path, timeout: float) -> tuple[dict[str, Any], float | None]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return {"status": "failed", "error": "artifact_exited_before_ready", "sidecarStatus": latest}, None
        payload, error = _read_json(status)
        if error is None and payload is not None:
            latest = {key: payload.get(key) for key in ("status", "host", "port", "detail")}
            if payload.get("status") == "failed":
                return {"status": "failed", "error": "sidecar_reported_failed", "sidecarStatus": latest}, None
            if payload.get("status") == "ready" and payload.get("host") == LOOPBACK:
                try:
                    port = int(payload.get("port"))
                except (TypeError, ValueError):
                    port = 0
                if 1 <= port <= 65535:
                    health = _health(port)
                    if health["status"] == "ready":
                        workspace = _workspace(home)
                        if workspace["manifest"]["readable"]:
                            return {"status": "ready", "error": None, "sidecarStatus": latest, "health": health, "workspace": workspace}, time.monotonic()
        time.sleep(0.1)
    return {"status": "failed", "error": "ready_timeout", "sidecarStatus": latest}, None


def _request_close(pid: int) -> dict[str, Any]:
    executable = _powershell()
    if executable is None:
        return {
            "found": False,
            "mainWindowHandle": None,
            "closeRequested": False,
            "error": "powershell_unavailable",
        }
    script = rf'''
$ErrorActionPreference = "SilentlyContinue"
$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue
if ($null -eq $p) {{
  [pscustomobject]@{{ found=$false; mainWindowHandle=$null; closeRequested=$false; error="process_not_found" }} | ConvertTo-Json -Compress
}} else {{
  $handle = 0
  $closeError = $null
  try {{ $handle = [int64]$p.MainWindowHandle }} catch {{ $closeError = "main_window_query_failed" }}
  $closeRequested = $false
  if ($null -eq $closeError -and $handle -eq 0) {{
    $closeError = "main_window_not_ready"
  }} elseif ($null -eq $closeError) {{
    try {{
      $closeRequested = [bool]$p.CloseMainWindow()
      if (-not $closeRequested) {{ $closeError = "close_request_rejected" }}
    }} catch {{ $closeError = "close_request_failed" }}
  }}
  [pscustomobject]@{{ found=$true; mainWindowHandle=$handle; closeRequested=$closeRequested; error=$closeError }} | ConvertTo-Json -Compress
}}
'''
    payload, error = _ps_json(script)
    if error:
        return {
            "found": False,
            "mainWindowHandle": None,
            "closeRequested": False,
            "error": error,
        }
    row = payload if isinstance(payload, dict) else {}
    handle = row.get("mainWindowHandle")
    try:
        handle = None if handle is None else int(handle)
    except (TypeError, ValueError):
        handle = None
    raw_error = row.get("error")
    close_error = raw_error if isinstance(raw_error, str) else None if raw_error is None else "close_observation_invalid"
    return {
        "found": bool(row.get("found")),
        "mainWindowHandle": handle,
        "closeRequested": bool(row.get("closeRequested")),
        "error": close_error,
    }


def _same_identity(current: ProcessInfo, observed: ProcessInfo) -> bool:
    return bool(
        current.created
        and observed.created
        and current.created == observed.created
        and current.path
        and observed.path
        and _same_path(current.path, Path(observed.path))
    )


def _taskkill_tree(pid: int, method: str) -> dict[str, Any]:
    root = os.environ.get("SystemRoot", "").strip()
    taskkill = Path(root) / "System32" / "taskkill.exe" if root else None
    if taskkill is None or not taskkill.is_file():
        return {
            "status": "failed",
            "method": method,
            "identityVerified": True,
            "error": "taskkill_unavailable",
        }
    try:
        finished = subprocess.run(
            [str(taskkill), "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "status": "failed",
            "method": method,
            "identityVerified": True,
            "error": "tree_termination_failed",
        }
    return {
        "status": "forced_owned_tree_termination",
        "method": method,
        "identityVerified": True,
        "taskkillExitCode": finished.returncode,
    }


def _tree_kill(process: subprocess.Popen[bytes], artifact: Path, current: ProcessInfo | None) -> dict[str, Any]:
    if process.poll() is not None:
        return {"status": "already_exited", "method": "none", "identityVerified": True}
    verified = bool(current and current.created and _same_path(current.path, artifact))
    if not verified:
        try:
            process.kill()
        except OSError:
            pass
        return {"status": "identity_unverified", "method": "popen_handle_kill", "identityVerified": False}
    return _taskkill_tree(process.pid, "taskkill_tree")


def _popen_handle_kill(process: subprocess.Popen[bytes], timeout: float) -> dict[str, Any]:
    if process.poll() is not None:
        return {
            "status": "already_exited",
            "method": "popen_exact_handle",
            "identityVerified": True,
        }
    try:
        process.kill()
    except OSError:
        return {
            "status": "failed",
            "method": "popen_exact_handle",
            "identityVerified": True,
            "error": "popen_handle_kill_failed",
        }
    exited, _ = _wait_exit(process, timeout)
    return {
        "status": "forced_owned_handle_termination" if exited else "failed",
        "method": "popen_exact_handle",
        "identityVerified": True,
        "postTermination": "gone" if exited else "still_present",
    }


def _merge_observed(*snapshots: list[ProcessInfo]) -> list[ProcessInfo]:
    merged: dict[int, ProcessInfo] = {}
    for snapshot in snapshots:
        for item in snapshot:
            previous = merged.get(item.pid)
            if previous is None or (item.created and item.path):
                merged[item.pid] = item
    return list(merged.values())


def _wait_identity_gone(observed: ProcessInfo, timeout: float) -> tuple[str, str | None]:
    deadline = time.monotonic() + min(timeout, 3.0)
    while time.monotonic() < deadline:
        rows, query_error = _process(observed.pid)
        if query_error:
            return "unobserved", query_error
        if not rows:
            return "gone", None
        if not _same_identity(rows[0], observed):
            return "identity_changed", None
        time.sleep(0.1)
    return "still_present", None


def _cleanup_observed_descendants(
    process: subprocess.Popen[bytes],
    artifact: Path,
    observed: list[ProcessInfo],
    timeout: float,
    root_query_error: str | None = None,
) -> dict[str, Any]:
    observed_by_pid = {item.pid: item for item in observed}
    root_observation = observed_by_pid.get(process.pid)
    root_verified = bool(
        root_observation
        and root_observation.created
        and root_observation.path
        and _same_path(root_observation.path, artifact)
    )
    cleanup: dict[str, Any] = {
        "rootPid": process.pid,
        "rootObserved": root_verified,
        "candidatePids": [],
        "verifiedDescendants": [],
        "actions": [],
        "skipped": [],
        "queryErrors": [root_query_error] if root_query_error else [],
    }
    if not root_verified:
        cleanup["status"] = "identity_unverified"
        return {
            "status": "identity_unverified",
            "method": "none",
            "identityVerified": False,
            "exactDescendantCleanup": cleanup,
    }

    live: dict[int, ProcessInfo] = {}
    identity_uncertain = False
    for item in observed:
        if item.pid == process.pid or not item.created or not item.path:
            continue
        rows, query_error = _process(item.pid)
        if query_error:
            cleanup["queryErrors"].append(query_error)
            cleanup["skipped"].append({"pid": item.pid, "reason": "process_query_failed"})
            continue
        if not rows:
            cleanup["skipped"].append({"pid": item.pid, "reason": "not_found"})
            continue
        current = rows[0]
        if not _same_identity(current, item) or current.parent_pid != item.parent_pid:
            cleanup["skipped"].append({"pid": item.pid, "reason": "identity_or_parent_mismatch"})
            identity_uncertain = True
            continue
        live[item.pid] = current

    top_level: list[ProcessInfo] = []
    for current in live.values():
        if current.parent_pid == process.pid or current.parent_pid not in live:
            parent_observed = observed_by_pid.get(current.parent_pid)
            if current.parent_pid == process.pid or (
                parent_observed is not None
                and parent_observed.created
                and parent_observed.path
            ):
                top_level.append(current)
            else:
                cleanup["skipped"].append({"pid": current.pid, "reason": "parent_not_observed"})
                identity_uncertain = True
    cleanup["candidatePids"] = [item.pid for item in top_level]
    cleanup["verifiedDescendants"] = [item.public(artifact) for item in top_level]

    action_failed = False
    action_unverified = bool(cleanup["queryErrors"]) or identity_uncertain
    for current in top_level:
        action = _taskkill_tree(current.pid, "taskkill_tree_exact_descendant")
        action["pid"] = current.pid
        action["executableName"] = current.name
        if action.get("status") == "forced_owned_tree_termination":
            gone_status, gone_error = _wait_identity_gone(current, timeout)
            action["postTermination"] = gone_status
            if gone_error:
                cleanup["queryErrors"].append(gone_error)
                action_unverified = True
            if gone_status == "still_present":
                action_failed = True
        else:
            action_failed = True
        cleanup["actions"].append(action)

    if action_failed:
        cleanup["status"] = "failed"
        status = "failed"
    elif action_unverified:
        cleanup["status"] = "identity_unverified"
        status = "identity_unverified"
    elif top_level:
        cleanup["status"] = "completed"
        status = "forced_owned_tree_termination"
    else:
        cleanup["status"] = "no_live_observed_descendants"
        status = "already_exited"
    return {
        "status": status,
        "method": "taskkill_tree_exact_descendant" if top_level else "none",
        "identityVerified": not action_unverified,
        "exactDescendantCleanup": cleanup,
    }


def _combine_crash_termination(
    root_termination: dict[str, Any],
    descendants: dict[str, Any],
    root_tree_attempt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root_status = root_termination.get("status")
    descendant_status = descendants.get("status")
    root_failed = root_status == "failed"
    descendant_failed = descendant_status == "failed"
    root_uncertain = root_status == "identity_unverified" or not root_termination.get("identityVerified", False)
    descendant_uncertain = descendant_status == "identity_unverified" or not descendants.get("identityVerified", False)
    tree_failed = bool(root_tree_attempt and root_tree_attempt.get("status") == "failed")
    tree_uncertain = bool(
        root_tree_attempt
        and (
            root_tree_attempt.get("status") == "identity_unverified"
            or not root_tree_attempt.get("identityVerified", False)
        )
    )
    if root_failed or descendant_failed or tree_failed:
        status = "failed"
    elif root_uncertain or descendant_uncertain or tree_uncertain:
        status = "identity_unverified"
    elif root_status in {"forced_owned_handle_termination", "forced_owned_tree_termination"} or descendant_status == "forced_owned_tree_termination":
        status = "forced_owned_tree_termination"
    else:
        status = "already_exited"
    if root_status in {"forced_owned_handle_termination", "already_exited"} and descendant_status == "forced_owned_tree_termination":
        method = "popen_exact_handle+taskkill_tree_exact_descendant"
    elif root_status == "forced_owned_tree_termination":
        method = str(root_termination.get("method", "taskkill_tree"))
    else:
        method = "popen_exact_handle" if root_status == "forced_owned_handle_termination" else "none"
    result = {
        "status": status,
        "method": method,
        "identityVerified": not (root_uncertain or descendant_uncertain or tree_uncertain),
        "rootTermination": root_termination,
        "exactDescendantCleanup": descendants.get("exactDescendantCleanup"),
        "terminationNote": "precise crash-recovery injection against this runner-owned PID tree",
    }
    if root_tree_attempt is not None:
        result["rootTreeAttempt"] = root_tree_attempt
    return result


def _terminate(
    process: subprocess.Popen[bytes],
    artifact: Path,
    kind: str,
    crash: bool,
    timeout: float,
    observed: list[ProcessInfo],
) -> dict[str, Any]:
    termination_started = time.monotonic()
    rows, query_error = _process(process.pid)
    current = rows[0] if rows else None
    if query_error:
        if not crash:
            return {"status": "identity_unverified", "method": "none", "identityVerified": False, "queryError": query_error}
        root_termination = _popen_handle_kill(process, timeout)
        descendants = _cleanup_observed_descendants(process, artifact, observed, timeout, query_error)
        return _combine_crash_termination(root_termination, descendants)
    if kind == "desktop" and not crash:
        close_started = time.monotonic()
        close_deadline = termination_started + timeout
        close_attempts = 0
        close_requested = False
        close_error: str | None = None
        main_window_handle: int | None = None
        while time.monotonic() < close_deadline:
            close_attempts += 1
            observation = _request_close(process.pid)
            main_window_handle = observation.get("mainWindowHandle")
            if observation.get("closeRequested"):
                close_requested = True
                close_error = None
                exited, _ = _wait_exit(process, max(0.0, close_deadline - time.monotonic()))
                if exited:
                    return {
                        "status": "graceful_exit",
                        "method": "CloseMainWindow",
                        "identityVerified": True,
                        "closeRequested": True,
                        "closeAttempts": close_attempts,
                        "closeElapsedMs": _elapsed(close_started),
                        "closeError": None,
                        "mainWindowHandle": main_window_handle,
                    }
                close_error = "close_timeout"
                break
            close_error = observation.get("error") or "close_request_not_submitted"
            if close_error in {"powershell_unavailable", "process_query_failed", "process_query_invalid_json"}:
                break
            if process.poll() is not None:
                break
            remaining = close_deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(0.1, remaining))
        forced = _tree_kill(process, artifact, current)
        forced["gracefulExitFailed"] = True
        if close_error:
            forced["closeError"] = close_error
        forced["closeRequested"] = close_requested
        forced["closeAttempts"] = close_attempts
        forced["closeElapsedMs"] = _elapsed(close_started)
        forced["mainWindowHandle"] = main_window_handle
        return forced
    if crash:
        if current is None or process.poll() is not None:
            root_termination = _popen_handle_kill(process, timeout)
            descendants = _cleanup_observed_descendants(process, artifact, observed, timeout)
            return _combine_crash_termination(root_termination, descendants)
        forced = _tree_kill(process, artifact, current)
        if forced.get("status") in {"already_exited", "identity_unverified", "failed"}:
            root_termination = _popen_handle_kill(process, timeout)
            descendants = _cleanup_observed_descendants(process, artifact, observed, timeout)
            return _combine_crash_termination(root_termination, descendants, forced)
        forced["rootTermination"] = forced.copy()
        forced["exactDescendantCleanup"] = {
            "status": "not_needed",
            "reason": "verified_root_tree_termination",
            "rootPid": process.pid,
        }
        forced["terminationNote"] = "precise crash-recovery injection against this runner-owned PID tree"
        return forced
    forced = _tree_kill(process, artifact, current)
    if kind == "sidecar" and forced.get("status") == "forced_owned_tree_termination":
        forced["terminationNote"] = "Sidecar-only artifact has no Desktop window; forced owned-tree termination is explicit"
    return forced


def _wait_exit(process: subprocess.Popen[bytes], timeout: float) -> tuple[bool, float | None]:
    try:
        process.wait(timeout=timeout)
        return True, time.monotonic()
    except subprocess.TimeoutExpired:
        return False, None


def _orphans(
    known: list[ProcessInfo], artifact: Path, timeout: float
) -> tuple[list[dict[str, Any]], str | None, int, int]:
    started = time.monotonic()
    deadline = started + min(max(timeout, 0.0), 8.0)
    polls = 0
    last: list[dict[str, Any]] = []
    error: str | None = None
    while True:
        polls += 1
        current_orphans: list[dict[str, Any]] = []
        for item in known:
            rows, query_error = _process(item.pid)
            error = error or query_error
            if query_error in {"powershell_unavailable", "process_query_failed", "process_query_invalid_json"}:
                return current_orphans, error, _elapsed(started), polls
            if rows and _same_identity(rows[0], item):
                current_orphans.append(rows[0].public(artifact))
        last = current_orphans
        if not last or time.monotonic() >= deadline:
            return last, error, _elapsed(started), polls
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.1, remaining))


def _attempt(artifact: Path, kind: str, home: Path, status: Path, ready_timeout: float, exit_timeout: float, crash: bool) -> dict[str, Any]:
    started_at = _now()
    started = time.monotonic()
    if status.exists():
        status.unlink()
    try:
        process, reserved_port = _launch(artifact, kind, home, status)
    except RunnerError as exc:
        return {
            "status": "failed", "startedAt": started_at, "readyAt": None, "exitAt": None, "processId": None, "port": None,
            "exitCode": None,
            "startupDurationMs": None, "durationMs": _elapsed(started), "ready": {"status": "failed", "error": _safe(exc, (artifact, home))},
            "resources": {"beforeReady": None, "ready": None, "beforeExit": None}, "workspaceAfterExit": _workspace(home),
            "portAfterExit": {"status": "not_observed", "error": None}, "orphanProcesses": [], "orphanWaitMs": 0, "orphanPolls": 0, "termination": {"status": "not_started", "method": "none"},
            "failures": [{"category": "launch", "message": _safe(exc, (artifact, home))}],
        }
    before, before_error = _process(process.pid, tree=True)
    ready, ready_mono = _ready(process, status, home, ready_timeout)
    ready_tree, ready_error = _process(process.pid, tree=True)
    known = _merge_observed(before, ready_tree)
    before_exit, before_exit_error = _process(process.pid, tree=True)
    observed = _merge_observed(known, before_exit)
    termination = _terminate(process, artifact, kind, crash, exit_timeout, observed)
    exited, exit_mono = _wait_exit(process, min(5.0, exit_timeout))
    exit_code = process.returncode if exited else None
    orphans, orphan_error, orphan_wait_ms, orphan_polls = _orphans(observed, artifact, exit_timeout)
    sidecar_port = (ready.get("sidecarStatus") or {}).get("port") if isinstance(ready.get("sidecarStatus"), dict) else reserved_port
    workspace_after = _workspace(home)
    port_after = _port_release(sidecar_port, exit_timeout)
    failures: list[dict[str, Any]] = []
    if ready.get("status") != "ready":
        failures.append({"category": "ready", "message": str(ready.get("error", "not_ready"))})
    if not exited:
        failures.append({"category": "exit", "message": "artifact 未在退出超时内结束"})
    if port_after["status"] == "occupied":
        failures.append({"category": "port", "message": "本轮端口退出后仍被占用"})
    if orphans:
        failures.append({"category": "orphan_process", "message": "检测到本轮孤儿进程"})
    if not workspace_after["manifest"]["readable"]:
        failures.append({"category": "manifest", "message": "退出后 Workspace manifest 不可读"})
    if workspace_after["sqlite"]["status"] not in {"readable", "not_present"}:
        failures.append({"category": "sqlite", "message": "退出后 SQLite 不可读"})
    if termination.get("status") in {"identity_unverified", "failed"}:
        failures.append({"category": "termination", "message": "未能以已验证身份完成本轮进程处理"})
    if termination.get("gracefulExitFailed"):
        failures.append({"category": "graceful_exit", "message": "Desktop CloseMainWindow 未在超时内退出，已强制清理"})
    if before_error or ready_error or before_exit_error or orphan_error:
        failures.append({"category": "process_observation", "message": "无法完整观察本轮进程身份"})
    return {
        "status": "passed" if not failures else "failed", "startedAt": started_at, "readyAt": _now() if ready_mono is not None else None,
        "exitAt": _now() if exited else None, "processId": process.pid, "exitCode": exit_code, "port": sidecar_port,
        "startupDurationMs": None if ready_mono is None else _elapsed(started, ready_mono), "durationMs": _elapsed(started, exit_mono if exited else None),
        "ready": ready,
        "resources": {"beforeReady": {"processCount": len(before), "workingSetBytes": _working_set(before)}, "ready": {"processCount": len(ready_tree), "workingSetBytes": _working_set(ready_tree)}, "beforeExit": {"processCount": len(before_exit), "workingSetBytes": _working_set(before_exit)}},
        "workspaceAfterExit": workspace_after, "portAfterExit": port_after, "orphanProcesses": orphans, "orphanWaitMs": orphan_wait_ms, "orphanPolls": orphan_polls, "termination": termination,
        "processObservationErrors": [e for e in (before_error, ready_error, before_exit_error, orphan_error) if e], "failures": failures,
    }


def _result_base(args: argparse.Namespace, run_dir: Path, artifact: Path | None) -> dict[str, Any]:
    return {
        "id": f"stability_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{os.getpid()}", "startedAt": _now(), "completedAt": None, "status": "failed",
        "environment": {"platform": sys.platform, "os": platform.system(), "osRelease": platform.release(), "machine": platform.machine(), "python": platform.python_version(), "artifact": None if artifact is None else {"kind": args.artifact_kind, "name": artifact.name, "sizeBytes": artifact.stat().st_size}, "artifactPathProvided": artifact is not None},
        "inputs": {"iterations": args.iterations, "readyTimeoutSeconds": args.ready_timeout_seconds, "exitTimeoutSeconds": args.exit_timeout_seconds, "crashRecoveryRequested": args.crash_recovery},
        "isolation": {"agentAuditHomeProvided": True, "outputDirectoryProvided": True, "homeInitiallyEmpty": True, "absolutePathsOmittedFromArtifact": True}, "checks": [],
        "observations": {"durationMs": None, "memoryStartBytes": None, "memoryEndBytes": None, "memoryDeltaBytes": None, "historyCount": None, "completedIterations": 0},
        "limitations": ["仅在本次显式隔离 home 中执行，不代表任意企业 Workspace 或机器性能保证", "本 Runner 只测量 Desktop/Sidecar 启停，不把 Test Double 或一次 smoke 外推为真实模型稳定性"], "rounds": [],
        "artifacts": {"json": "desktop-lifecycle.json", "markdown": "desktop-lifecycle.md", "directory": run_dir.name},
    }


def _execute(args: argparse.Namespace, run_dir: Path, home: Path) -> dict[str, Any]:
    artifact = None
    if args.artifact:
        artifact_input = Path(args.artifact.strip()).expanduser()
        if artifact_input.is_symlink():
            raise RunnerError("指定 artifact 不能是符号链接")
        artifact = _absolute(args.artifact, "--artifact")
        if not artifact.is_file():
            raise RunnerError("指定 artifact 不存在或不是普通文件")
        if artifact.suffix.lower() != ".exe":
            raise RunnerError("Windows Desktop/Sidecar artifact 必须是 .exe")
    result = _result_base(args, run_dir, artifact)
    started = time.monotonic()
    if sys.platform != "win32":
        result["status"] = "skipped"
        result["limitations"].append("当前平台不是 Windows；Linux/macOS artifact 生命周期保持 unsupported/skip")
        for check_id in ("desktop_sidecar_lifecycle", "crash_recovery"):
            result["checks"].append({"id": check_id, "status": "skipped", "iterations": args.iterations if check_id == "desktop_sidecar_lifecycle" else 1, "completedIterations": 0, "failureCount": 0, "failures": [], "detail": "platform_unsupported"})
    elif artifact is None:
        result["status"] = "skipped"
        result["limitations"].append("未提供显式 --artifact；没有把静态配置或缓存文件当作生命周期证据")
        for check_id in ("desktop_sidecar_lifecycle", "crash_recovery"):
            result["checks"].append({"id": check_id, "status": "skipped", "iterations": args.iterations if check_id == "desktop_sidecar_lifecycle" else 1, "completedIterations": 0, "failureCount": 0, "failures": [], "detail": "artifact_not_provided"})
    else:
        status = home / "data" / STATUS_FILE
        failures: list[dict[str, Any]] = []
        for index in range(1, args.iterations + 1):
            first = _attempt(artifact, args.artifact_kind, home, status, args.ready_timeout_seconds, args.exit_timeout_seconds, args.crash_recovery and index == 1)
            item: dict[str, Any] = {"index": index, "status": first["status"], "attempt": first, "crashRecovery": None, "failures": [{"round": index, **failure} for failure in first["failures"]]}
            if args.crash_recovery and index == 1:
                recovery = _attempt(artifact, args.artifact_kind, home, status, args.ready_timeout_seconds, args.exit_timeout_seconds, False) if first["ready"]["status"] == "ready" else None
                item["crashRecovery"] = {"status": "passed" if recovery and recovery["status"] == "passed" else "failed", "scenario": "ready_then_owned_tree_termination_then_same_home_restart", "attempt": recovery}
                if recovery is None:
                    item["failures"].append({"round": index, "category": "recovery", "message": "首次启动未 ready，未执行恢复重启"})
                else:
                    item["failures"].extend({"round": index, **failure} for failure in recovery["failures"])
                item["status"] = "passed" if not item["failures"] else "failed"
            result["rounds"].append(item)
            failures.extend(item["failures"])
        completed = sum(1 for item in result["rounds"] if item["status"] == "passed")
        result["observations"]["completedIterations"] = completed
        memory: list[int] = []
        histories: list[int] = []
        for item in result["rounds"]:
            attempts = [item["attempt"]] + ([item["crashRecovery"]["attempt"]] if item["crashRecovery"] and item["crashRecovery"]["attempt"] else [])
            for attempt in attempts:
                for phase in ("beforeReady", "ready", "beforeExit"):
                    value = attempt["resources"][phase]["workingSetBytes"]
                    if isinstance(value, int): memory.append(value)
                row_count = attempt["workspaceAfterExit"]["sqlite"]["rowCount"]
                if isinstance(row_count, int): histories.append(row_count)
        if memory:
            result["observations"].update(memoryStartBytes=memory[0], memoryEndBytes=memory[-1], memoryDeltaBytes=memory[-1] - memory[0])
        if histories: result["observations"]["historyCount"] = histories[-1]
        result["checks"].append({"id": "desktop_sidecar_lifecycle", "status": "passed" if not failures and completed == args.iterations else "failed", "iterations": args.iterations, "completedIterations": completed, "failureCount": len(failures), "failures": failures})
        if args.crash_recovery:
            crash = result["rounds"][0]["crashRecovery"]
            crash_failures = [] if crash and crash["status"] == "passed" else [{"category": "recovery", "message": "crash recovery failed"}]
            result["checks"].append({"id": "crash_recovery", "status": "passed" if not crash_failures else "failed", "iterations": 1, "completedIterations": 1 if not crash_failures else 0, "failureCount": len(crash_failures), "failures": crash_failures, "detail": "one_precise_owned_process_tree_crash_scenario"})
        else:
            result["checks"].append({"id": "crash_recovery", "status": "skipped", "iterations": 1, "completedIterations": 0, "failureCount": 0, "failures": [], "detail": "not_requested"})
        result["status"] = "passed" if all(check["status"] in {"passed", "skipped"} for check in result["checks"]) else "failed"
    result["observations"]["durationMs"] = _elapsed(started)
    result["completedAt"] = _now()
    return result


def _markdown(result: dict[str, Any]) -> str:
    env = result["environment"]
    obs = result["observations"]
    lines = ["# Desktop/Sidecar 生命周期与资源测量", "", f"- 状态：`{result['status']}`", f"- Run ID：`{result['id']}`", f"- 开始：`{result['startedAt']}`", f"- 完成：`{result['completedAt']}`", "", "## 输入与环境", "", f"- 平台：`{env.get('platform')}` / `{env.get('os')}`", f"- Artifact：`{(env.get('artifact') or {}).get('name', '未提供')}`", f"- 迭代数：`{result['inputs'].get('iterations')}`", "", "## Checks", "", "| ID | 状态 | 迭代 | 完成 | 失败数 |", "|---|---|---:|---:|---:|"]
    for check in result["checks"]:
        lines.append(f"| `{check['id']}` | `{check['status']}` | {check['iterations']} | {check['completedIterations']} | {check['failureCount']} |")
    lines.extend(["", "## 每轮观察", "", "| 轮次 | 状态 | PID | 退出码 | 端口 | 启动 ms | 总 ms | manifest | SQLite | 端口 | 孤儿 | 孤儿等待 ms | 孤儿采样 |", "|---:|---|---:|---:|---:|---:|---:|---|---|---|---:|---:|---:|"])
    for item in result["rounds"]:
        attempt = item["attempt"]
        lines.append(f"| {item['index']} | `{item['status']}` | {attempt['processId']} | {attempt['exitCode']} | {attempt['port']} | {attempt['startupDurationMs']} | {attempt['durationMs']} | `{attempt['workspaceAfterExit']['manifest']['status']}` | `{attempt['workspaceAfterExit']['sqlite']['status']}` | `{attempt['portAfterExit']['status']}` | {len(attempt['orphanProcesses'])} | {attempt['orphanWaitMs']} | {attempt['orphanPolls']} |")
        recovery = item.get("crashRecovery")
        if recovery and recovery.get("attempt"):
            attempt = recovery["attempt"]
            lines.append(f"| {item['index']} recovery | `{recovery['status']}` | {attempt['processId']} | {attempt['exitCode']} | {attempt['port']} | {attempt['startupDurationMs']} | {attempt['durationMs']} | `{attempt['workspaceAfterExit']['manifest']['status']}` | `{attempt['workspaceAfterExit']['sqlite']['status']}` | `{attempt['portAfterExit']['status']}` | {len(attempt['orphanProcesses'])} | {attempt['orphanWaitMs']} | {attempt['orphanPolls']} |")
    lines.extend(["", "## 资源观察", "", f"- 总耗时：`{obs['durationMs']} ms`", f"- 工作集起始：`{obs['memoryStartBytes']} bytes`", f"- 工作集结束：`{obs['memoryEndBytes']} bytes`", f"- 工作集差值：`{obs['memoryDeltaBytes']} bytes`", f"- History 行数：`{obs['historyCount']}`", "", "## 失败与边界", ""])
    failures = [failure for item in result["rounds"] for failure in item["failures"]]
    lines.extend([f"- 轮次 `{failure.get('round', '?')}`：`{failure.get('category')}` — {failure.get('message')}" for failure in failures] or ["- 本次 JSON 未记录轮次失败。"])
    lines.extend([f"- 限制：{limitation}" for limitation in result["limitations"]])
    lines.extend(["", "## 工件来源", "", "本 Markdown 由同目录 `desktop-lifecycle.json` 投影生成；结论不在 Markdown 中重新计算。", ""])
    return "\n".join(lines)


def _write(result: dict[str, Any], run_dir: Path) -> None:
    (run_dir / "desktop-lifecycle.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run_dir / "desktop-lifecycle.md").write_text(_markdown(result), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="desktop-lifecycle-runner", allow_abbrev=False)
    parser.add_argument("--artifact", help="显式绝对 Desktop/Sidecar .exe 路径；省略则 honest skip")
    parser.add_argument("--artifact-kind", required=True, choices=("desktop", "sidecar"), help="必须显式声明 artifact 类型")
    parser.add_argument("--iterations", type=int, required=True, help=f"生命周期轮数（1-{MAX_ITERATIONS}）")
    parser.add_argument("--output-dir", required=True, help="显式绝对验收工件目录")
    parser.add_argument("--agent-audit-home", required=True, help="显式绝对、初始为空的隔离 AGENT_AUDIT_HOME")
    parser.add_argument("--ready-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--exit-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--crash-recovery", action="store_true", help="执行一次 ready→精确进程树终止→同 home 重启")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not 1 <= args.iterations <= MAX_ITERATIONS:
        parser.error(f"--iterations 必须在 1 到 {MAX_ITERATIONS} 之间")
    if not 1 <= args.ready_timeout_seconds <= 180 or not 1 <= args.exit_timeout_seconds <= 120:
        parser.error("timeout 必须为正数且不超过上限")
    run_dir: Path | None = None
    try:
        _output, home, run_dir = _prepare_dirs(args.output_dir, args.agent_audit_home)
        result = _execute(args, run_dir, home)
    except RunnerError as exc:
        if run_dir is None:
            # Setup may fail before an isolated run directory exists. Do not
            # guess a path or overwrite an existing directory to emit a report.
            print(
                json.dumps(
                    {
                        "status": "failed",
                        "check": "runner_setup",
                        "error": _safe(exc),
                        "artifactPathProvided": bool(args.artifact),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        result = {
            "id": f"stability_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{os.getpid()}", "startedAt": _now(), "completedAt": _now(), "status": "failed",
            "environment": {"platform": sys.platform, "os": platform.system(), "python": platform.python_version(), "artifact": None, "artifactPathProvided": bool(args.artifact)},
            "inputs": {"iterations": args.iterations, "readyTimeoutSeconds": args.ready_timeout_seconds, "exitTimeoutSeconds": args.exit_timeout_seconds, "crashRecoveryRequested": args.crash_recovery},
            "isolation": {"agentAuditHomeProvided": True, "outputDirectoryProvided": True, "homeInitiallyEmpty": True, "absolutePathsOmittedFromArtifact": True},
            "checks": [{"id": "runner_setup", "status": "failed", "iterations": args.iterations, "completedIterations": 0, "failureCount": 1, "failures": [{"category": "setup", "message": _safe(exc)}]}],
            "observations": {"durationMs": None, "memoryStartBytes": None, "memoryEndBytes": None, "memoryDeltaBytes": None, "historyCount": None, "completedIterations": 0}, "limitations": ["Runner 在 artifact 启动前失败；没有静态文件或缓存证据"], "rounds": [], "artifacts": {"json": "desktop-lifecycle.json", "markdown": "desktop-lifecycle.md", "directory": run_dir.name},
        }
    _write(result, run_dir)
    print(json.dumps({"status": result["status"], "directory": run_dir.name}, ensure_ascii=False))
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
