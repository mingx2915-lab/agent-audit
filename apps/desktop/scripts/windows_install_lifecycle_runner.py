"""Isolated Windows NSIS install, upgrade, and uninstall evidence runner.

The runner only operates on two explicitly supplied installers, a runner-owned
installation directory, and an initially empty ``AGENT_AUDIT_HOME``.  It never
discovers an installed product, uses the default NSIS destination, deletes
user data, or terminates processes by executable name.

JSON is the sole evidence source.  Markdown is rendered from the completed
JSON object and does not recompute conclusions.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import ntpath
import os
import platform
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


PRODUCT_NAME = "知盾 AgentAudit"
PRODUCT_IDENTIFIER = "com.agent-audit.desktop"
MANUFACTURER = "知盾 AgentAudit"
MANIFEST_NAME = "agent-audit-workspace.json"
HISTORY_NAME = "agent_audit.sqlite3"
STATUS_NAME = "sidecar.status.json"
LOOPBACK = "127.0.0.1"
UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
PROCESS_QUERY_TIMEOUT = 10.0
HTTP_BODY_LIMIT = 64 * 1024
VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
DESKTOP_RUNNER_PATH = Path(__file__).with_name("desktop_lifecycle_runner.py")


class RunnerError(RuntimeError):
    """A safe, user-facing runner boundary error."""


@dataclass(frozen=True)
class InstallerInput:
    role: str
    path: Path
    version: str
    sha256: str
    size_bytes: int

    def public(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "name": self.path.name,
            "version": self.version,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int | None
    path: str | None
    created: str | None


def _desktop_runner():
    specification = importlib.util.spec_from_file_location(
        "agent_audit_desktop_lifecycle_for_install_runner", DESKTOP_RUNNER_PATH
    )
    if specification is None or specification.loader is None:
        raise RunnerError("无法加载 Desktop 生命周期边界")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _absolute(raw: str, label: str) -> Path:
    value = raw.strip()
    if not value:
        raise RunnerError(f"{label} 不能为空")
    candidate = Path(value).expanduser()
    if candidate.is_symlink():
        raise RunnerError(f"{label} 不能是符号链接")
    if not candidate.is_absolute():
        raise RunnerError(f"{label} 必须是绝对路径")
    resolved = candidate.resolve(strict=False)
    if resolved.parent == resolved:
        raise RunnerError(f"{label} 不能是文件系统根目录")
    return resolved


def _same_path(left: str | Path | None, right: str | Path) -> bool:
    if left is None:
        return False

    def canonical(value: str | Path) -> str:
        text = str(value).strip()
        if text.startswith('"') or text.endswith('"'):
            if len(text) < 2 or not (text.startswith('"') and text.endswith('"')):
                raise ValueError("path has an unmatched outer quote")
            text = text[1:-1]
            if '"' in text:
                raise ValueError("path contains an embedded quote")
        text = text.replace("/", "\\")
        if text.startswith("\\\\?\\UNC\\"):
            text = "\\\\" + text[8:]
        elif text.startswith("\\\\?\\"):
            text = text[4:]
        return ntpath.normcase(ntpath.normpath(text))

    try:
        return canonical(left) == canonical(right)
    except (OSError, TypeError, ValueError):
        return False


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version(value: str, label: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise RunnerError(f"{label} 必须是明确的 major.minor.patch 版本")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _installer(path_raw: str, version_raw: str, role: str) -> InstallerInput:
    path = _absolute(path_raw, f"--{role}-installer")
    if not path.is_file() or path.suffix.casefold() != ".exe":
        raise RunnerError(f"--{role}-installer 必须是现有的 NSIS .exe")
    version = version_raw.strip()
    _version(version, f"--{role}-version")
    return InstallerInput(role, path, version, _sha256(path), path.stat().st_size)


def _protected_roots() -> tuple[Path, ...]:
    values = [
        os.environ.get("USERPROFILE"),
        os.environ.get("SystemRoot"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramData"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    roots = [Path(value).resolve(strict=False) for value in values if value]
    if local_app_data:
        roots.append((Path(local_app_data) / "AgentAudit").resolve(strict=False))
    return tuple(roots)


def _validate_sandbox(path: Path) -> None:
    if " " in str(path):
        raise RunnerError("--sandbox-root 不能含空格，以保持 NSIS /D= 原始命令行语义")
    for protected in _protected_roots():
        if path == protected or _is_within(path, protected) or _is_within(protected, path):
            raise RunnerError("--sandbox-root 不能是受保护目录、其父目录或其子目录")


def _prepare_directories(sandbox_raw: str) -> tuple[Path, Path, Path, Path]:
    sandbox = _absolute(sandbox_raw, "--sandbox-root")
    _validate_sandbox(sandbox)
    if sandbox.exists():
        raise RunnerError("--sandbox-root 必须在运行前不存在，并由 Runner 创建")
    sandbox.mkdir(parents=True)
    output = sandbox / "evidence"
    install_root = sandbox / "install"
    home = sandbox / "home"
    output.mkdir()
    home.mkdir()
    token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = output / f"windows-install-lifecycle-{token}-{os.getpid()}"
    run_dir.mkdir()
    return install_root, home, run_dir, sandbox


def _nsis_install_command(
    installer: Path, install_root: Path, *, require_existing: bool = False
) -> tuple[Path, str]:
    """Return the only supported silent NSIS command.

    NSIS parses ``/D=`` only as the final command-line argument and the value
    must not be quoted.  F-052 therefore requires a space-free runner-owned
    sandbox and supplies the raw argument string with an explicit executable.
    """

    if require_existing:
        if not install_root.is_dir():
            raise RunnerError("upgrade NSIS 执行前安装根目录必须已存在")
    elif install_root.exists():
        raise RunnerError("baseline NSIS 执行前安装目录必须不存在")
    argument = f"/D={install_root}"
    if '"' in argument or " " in argument:
        raise RunnerError("NSIS /D= 目录不能包含引号或空格")
    return installer, f"/S {argument}"


def _run_raw(
    executable: Path,
    raw_arguments: str,
    *,
    timeout: float,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    raw_command_line = f'"{executable}" {raw_arguments}'
    try:
        completed = subprocess.run(
            raw_command_line,
            executable=str(executable),
            shell=False,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError("安装器或卸载器未在限定时间内完成") from exc
    return {"exitCode": completed.returncode, "completed": completed.returncode == 0}


def _safe(value: object, private_paths: Iterable[Path]) -> str:
    text = str(value).strip() or type(value).__name__
    for path in private_paths:
        for spelling in (str(path), str(path).replace("\\", "/")):
            text = text.replace(spelling, "<isolated-path>")
    return " ".join(text.split())[:500]


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
    prefix = (
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
                prefix + script,
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
        return None, "powershell_failed"
    try:
        return json.loads(completed.stdout.strip() or "[]"), None
    except json.JSONDecodeError:
        return None, "powershell_invalid_json"


def _process_tree(pid: int) -> tuple[list[ProcessInfo], str | None]:
    script = rf'''
$ErrorActionPreference = "SilentlyContinue"
function Find-Tree([int] $id) {{
  $w = Get-CimInstance Win32_Process -Filter ("ProcessId = {{0}}" -f $id)
  if ($null -eq $w) {{ return }}
  [pscustomobject]@{{ ProcessId=[int]$w.ProcessId; ParentProcessId=[int]$w.ParentProcessId; ExecutablePath=[string]$w.ExecutablePath; CreationDate=[string]$w.CreationDate }}
  foreach ($child in Get-CimInstance Win32_Process -Filter ("ParentProcessId = {{0}}" -f $id)) {{ Find-Tree ([int]$child.ProcessId) }}
}}
$rows = @(Find-Tree {pid})
if ($rows.Count -eq 0) {{ "[]" }} else {{ $rows | ConvertTo-Json -Compress }}
'''
    payload, error = _ps_json(script)
    if error:
        return [], error
    rows = payload if isinstance(payload, list) else [payload]
    result: list[ProcessInfo] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            result.append(
                ProcessInfo(
                    pid=int(row["ProcessId"]),
                    parent_pid=int(row["ParentProcessId"]),
                    path=str(row["ExecutablePath"]) if row.get("ExecutablePath") else None,
                    created=str(row["CreationDate"]) if row.get("CreationDate") else None,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result, None


def _registry_entries() -> tuple[list[dict[str, Any]], str | None]:
    script = rf'''
$ErrorActionPreference = "SilentlyContinue"
$root = "HKCU:\{UNINSTALL_ROOT}"
$rows = @()
if (Test-Path -LiteralPath $root) {{
  foreach ($key in Get-ChildItem -LiteralPath $root) {{
    $item = Get-ItemProperty -LiteralPath $key.PSPath
    $rows += [pscustomobject]@{{
      keyName=[string]$key.PSChildName
      displayName=[string]$item.DisplayName
      displayVersion=[string]$item.DisplayVersion
      installLocation=[string]$item.InstallLocation
      uninstallString=[string]$item.UninstallString
      quietUninstallString=[string]$item.QuietUninstallString
    }}
  }}
}}
if ($rows.Count -eq 0) {{ "[]" }} else {{ $rows | ConvertTo-Json -Compress }}
'''
    payload, error = _ps_json(script)
    if error:
        return [], error
    rows = payload if isinstance(payload, list) else [payload]
    return [row for row in rows if isinstance(row, dict)], None


def _manufacturer_install_location() -> tuple[str | None, str | None]:
    script = rf'''
$ErrorActionPreference = "SilentlyContinue"
$path = "HKCU:\Software\{MANUFACTURER}\{PRODUCT_NAME}"
if (Test-Path -LiteralPath $path) {{
  $key = Get-Item -LiteralPath $path
  [pscustomobject]@{{ present=$true; installLocation=[string]$key.GetValue("") }} | ConvertTo-Json -Compress
}} else {{
  [pscustomobject]@{{ present=$false; installLocation=$null }} | ConvertTo-Json -Compress
}}
'''
    payload, error = _ps_json(script)
    if error:
        return None, error
    row = payload if isinstance(payload, dict) else {}
    if not row.get("present"):
        return None, None
    value = row.get("installLocation")
    return (str(value) if value else "present_without_location"), None


def _assert_no_existing_installation() -> None:
    rows, error = _registry_entries()
    if error:
        raise RunnerError(f"无法读取 HKCU 卸载项：{error}")
    matches = [row for row in rows if row.get("displayName") == PRODUCT_NAME]
    manufacturer_location, manufacturer_error = _manufacturer_install_location()
    if manufacturer_error:
        raise RunnerError(f"无法读取 HKCU 产品安装位置：{manufacturer_error}")
    if matches or manufacturer_location is not None:
        raise RunnerError("当前用户已存在 AgentAudit 卸载项或厂商安装位置，Runner 拒绝覆盖")


def _verified_uninstall_entry(
    install_root: Path, expected_version: str
) -> tuple[dict[str, Any], Path, list[str]]:
    rows, error = _registry_entries()
    if error:
        raise RunnerError(f"无法读取 HKCU 卸载项：{error}")
    matches = [
        row
        for row in rows
        if row.get("displayName") == PRODUCT_NAME
        and row.get("displayVersion") == expected_version
        and _same_path(row.get("installLocation"), install_root)
    ]
    if len(matches) != 1:
        raise RunnerError("必须只有一个与产品、版本和安装目录精确匹配的 HKCU 卸载项")
    entry = matches[0]
    raw = str(entry.get("quietUninstallString") or entry.get("uninstallString") or "").strip()
    if not raw:
        raise RunnerError("唯一 HKCU 卸载项缺少 UninstallString")
    executable, arguments = _split_windows_command(raw)
    if not executable.is_file() or not _is_within(executable, install_root):
        raise RunnerError("卸载器可执行文件不在已验证的安装根目录内")
    return entry, executable, arguments


def _installed_desktop(install_root: Path) -> Path:
    candidate = install_root / "agent-audit-desktop.exe"
    if not candidate.is_file():
        raise RunnerError("安装目录缺少 agent-audit-desktop.exe")
    return candidate


def _desktop_session(
    artifact: Path,
    home: Path,
    ready_timeout: float,
    exit_timeout: float,
    action=None,
) -> dict[str, Any]:
    lifecycle = _desktop_runner()
    status = home / "data" / STATUS_NAME
    if status.exists():
        status.unlink()
    process, _ = lifecycle._launch(artifact, "desktop", home, status)
    before, before_error = lifecycle._process(process.pid, tree=True)
    ready, _ = lifecycle._ready(process, status, home, ready_timeout)
    at_ready, ready_error = lifecycle._process(process.pid, tree=True)
    observed = lifecycle._merge_observed(before, at_ready)
    action_result = None
    failures: list[str] = []
    if ready.get("status") != "ready":
        failures.append(str(ready.get("error") or "not_ready"))
    if before_error or ready_error:
        failures.append("process_identity_observation_failed")
    if not failures and action is not None:
        try:
            action_result = action(int(ready["sidecarStatus"]["port"]))
        except (RunnerError, KeyError, TypeError, ValueError) as exc:
            failures.append(_safe(exc, (artifact, home)))
    before_exit, before_exit_error = lifecycle._process(process.pid, tree=True)
    observed = lifecycle._merge_observed(observed, before_exit)
    if before_exit_error:
        failures.append("process_identity_observation_failed")
    termination = lifecycle._terminate(
        process, artifact, "desktop", False, exit_timeout, observed
    )
    exited, _ = lifecycle._wait_exit(process, min(5.0, exit_timeout))
    orphans, orphan_error, _, _ = lifecycle._orphans(
        observed, artifact, exit_timeout
    )
    port = (
        ready.get("sidecarStatus", {}).get("port")
        if isinstance(ready.get("sidecarStatus"), dict)
        else None
    )
    port_after = lifecycle._port_release(port, exit_timeout)
    if not exited:
        failures.append("desktop_exit_timeout")
    if termination.get("status") in {"identity_unverified", "failed"}:
        failures.append("desktop_termination_identity_failed")
    if orphans:
        failures.append("verified_orphan_processes_remain")
    if orphan_error:
        failures.append("orphan_identity_observation_failed")
    if port_after.get("status") == "occupied":
        failures.append("sidecar_port_remains_occupied")
    return {
        "status": "passed" if not failures else "failed",
        "ready": ready.get("status"),
        "processIdentityObserved": bool(at_ready and at_ready[0].created and at_ready[0].path),
        "observedProcessCount": len(observed),
        "termination": termination.get("status"),
        "portAfterExit": port_after.get("status"),
        "action": action_result,
        "failures": failures,
    }


def _api_json(port: int, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://{LOOPBACK}:{port}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Connection": "close"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=10.0) as response:
            raw = response.read(HTTP_BODY_LIMIT + 1)
            if response.status != 200 or len(raw) > HTTP_BODY_LIMIT:
                raise RunnerError("F-052 marker import API 未返回有界成功结果")
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise RunnerError("F-052 marker import API 请求失败") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError("F-052 marker import API 返回无效 JSON") from exc
    if not isinstance(value, dict):
        raise RunnerError("F-052 marker import API 返回非对象 JSON")
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise urllib.error.HTTPError(req.full_url, code, "redirect_forbidden", headers, fp)


def _write_marker(port: int) -> str:
    marker_content = "F-052 runner-owned synthetic marker for install upgrade preservation."
    payload = {
        "documents": [
            {
                "source": {
                    "sourceId": "f052-upgrade-marker",
                    "displayName": "f052-upgrade-marker.md",
                    "relativePath": "f052-upgrade-marker.md",
                    "extension": ".md",
                    "sizeBytes": len(marker_content.encode("utf-8")),
                    "content": marker_content,
                },
                "metadata": {
                    "title": "F-052 Upgrade Preservation Marker",
                    "sensitivity": "public",
                    "businessScope": "general",
                    "ownerId": None,
                    "trustLevel": "trusted",
                },
            }
        ]
    }
    result = _api_json(port, "/api/document-imports", payload)
    imported = result.get("imported")
    if not isinstance(imported, list) or len(imported) != 1:
        raise RunnerError("F-052 marker 未作为唯一文档导入")
    marker_id = imported[0].get("id") if isinstance(imported[0], dict) else None
    if not isinstance(marker_id, str) or not marker_id:
        raise RunnerError("F-052 marker 缺少真实文档 ID")
    return marker_id


def _split_windows_command(value: str) -> tuple[Path, list[str]]:
    """Parse the narrow quoted/unquoted NSIS uninstall command shape."""

    text = value.strip()
    if text.startswith('"'):
        closing = text.find('"', 1)
        if closing <= 1:
            raise RunnerError("卸载命令的引用可执行路径无效")
        executable = text[1:closing]
        tail = text[closing + 1 :].strip()
    else:
        marker = text.casefold().find(".exe")
        if marker < 0:
            raise RunnerError("卸载命令缺少 .exe")
        executable = text[: marker + 4]
        tail = text[marker + 4 :].strip()
    arguments = tail.split() if tail else []
    return Path(executable).expanduser().resolve(strict=False), arguments


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError("无法读取验收数据 JSON") from exc
    if not isinstance(value, dict):
        raise RunnerError("验收数据 JSON 必须是对象")
    return value


def _workspace_paths(home: Path) -> tuple[Path, Path]:
    root = home / "workspaces" / "default"
    manifest = _read_json(root / MANIFEST_NAME)
    history_dir = manifest.get("historyDir")
    if not isinstance(history_dir, str):
        raise RunnerError("Workspace manifest 缺少 historyDir")
    relative = PurePosixPath(history_dir)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise RunnerError("Workspace historyDir 不是安全相对目录")
    return root, root.joinpath(*relative.parts) / HISTORY_NAME


def _database_snapshot(database: Path) -> dict[str, Any]:
    try:
        connection = sqlite3.connect(
            f"file:{database.resolve().as_posix()}?mode=ro", uri=True, timeout=2.0
        )
        connection.row_factory = sqlite3.Row
        integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
        integrity = str(integrity_row[0]) if integrity_row else "unknown"
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        audit_ids = (
            [str(row[0]) for row in connection.execute("SELECT scan_id FROM audit_runs ORDER BY scan_id")]
            if "audit_runs" in tables
            else []
        )
        acceptance_ids = (
            [str(row[0]) for row in connection.execute("SELECT run_id FROM acceptance_runs ORDER BY run_id")]
            if "acceptance_runs" in tables
            else []
        )
    except (OSError, sqlite3.Error) as exc:
        raise RunnerError("Workspace SQLite 不可读") from exc
    finally:
        if "connection" in locals():
            connection.close()
    return {
        "integrity": integrity,
        "auditRunCount": len(audit_ids),
        "auditRunIds": audit_ids,
        "acceptanceRunCount": len(acceptance_ids),
        "acceptanceRunIds": acceptance_ids,
    }


def _business_hashes(workspace_root: Path) -> dict[str, str]:
    manifest = _read_json(workspace_root / MANIFEST_NAME)
    members = {
        "manifest": workspace_root / MANIFEST_NAME,
        "documents": workspace_root / str(manifest.get("documentsDir")) / "knowledge_documents.json",
        "contract": workspace_root / str(manifest.get("contractDir")) / "security_contract.json",
        "actors": workspace_root / str(manifest.get("documentsDir")) / "actors.json",
        "customers": workspace_root / str(manifest.get("documentsDir")) / "customers.json",
        "attackCases": workspace_root / str(manifest.get("casesDir")) / "attack_cases.json",
        "profiles": workspace_root / str(manifest.get("casesDir")) / "target_profiles.json",
        "groundTruth": workspace_root / str(manifest.get("casesDir")) / "ground_truth_cases.json",
    }
    hashes: dict[str, str] = {}
    for name, path in members.items():
        if not path.is_file() or not _is_within(path, workspace_root):
            raise RunnerError(f"Workspace 缺少必需业务文件：{name}")
        hashes[name] = _sha256(path)
    return hashes


def _create_controlled_history(workspace_root: Path) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[3]
    api_root = repository_root / "apps" / "api" / "src"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))
    try:
        from agent_audit_api.controlled_release_workflow import (
            build_controlled_release_workflow,
        )
    except ImportError as exc:
        raise RunnerError("无法加载发布证据主链") from exc
    try:
        workflow = asyncio.run(build_controlled_release_workflow(workspace_root))
    except Exception as exc:
        raise RunnerError(f"发布证据主链失败: {exc}") from exc
    if not workflow.scan_id or not workflow.acceptance_id:
        raise RunnerError("发布证据主链未生成非空 Scan/Acceptance History")
    return {
        "provider": "controlled_release_test_provider",
        "retriever": "tfidf_test_retriever",
        "scanIds": [workflow.scan_id],
        "acceptanceIds": [workflow.acceptance_id],
    }


def _workspace_snapshot(home: Path, marker_id: str) -> dict[str, Any]:
    workspace_root, database = _workspace_paths(home)
    manifest = _read_json(workspace_root / MANIFEST_NAME)
    try:
        raw_documents = json.loads(
            (workspace_root / "documents" / "knowledge_documents.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError("Workspace document catalog 不可读") from exc
    if isinstance(raw_documents, dict):
        raw_documents = raw_documents.get("documents")
    if not isinstance(raw_documents, list):
        raise RunnerError("Workspace document catalog 必须是文档列表")
    marker_present = any(
        isinstance(item, dict) and item.get("id") == marker_id for item in raw_documents
    )
    if not marker_present:
        raise RunnerError("F-052 marker 不在 Workspace catalog")
    database_state = _database_snapshot(database)
    if database_state["integrity"] != "ok":
        raise RunnerError("Workspace SQLite integrity_check 未通过")
    return {
        "manifestId": manifest.get("id"),
        "markerDocumentId": marker_id,
        "markerPresent": True,
        "hashes": _business_hashes(workspace_root),
        "database": database_state,
    }


def _assert_preserved(before: dict[str, Any], after: dict[str, Any]) -> None:
    if before != after:
        raise RunnerError("升级或卸载后 Workspace/History 快照不一致")


def _phase(result: dict[str, Any], phase_id: str, operation) -> Any:
    started = time.monotonic()
    try:
        detail = operation()
    except RunnerError as exc:
        result["phases"].append(
            {
                "id": phase_id,
                "status": "failed",
                "durationMs": int((time.monotonic() - started) * 1000),
                "detail": str(exc),
            }
        )
        result["checks"].append(
            {"id": phase_id, "status": "failed", "detail": str(exc)}
        )
        raise
    result["phases"].append(
        {
            "id": phase_id,
            "status": "passed",
            "durationMs": int((time.monotonic() - started) * 1000),
            "detail": detail,
        }
    )
    result["checks"].append({"id": phase_id, "status": "passed", "detail": None})
    return detail


def _install(
    installer: InstallerInput,
    install_root: Path,
    timeout: float,
    *,
    installed_version: str | None = None,
) -> dict[str, Any]:
    if installer.role == "upgrade":
        # Re-verify the exact baseline installation immediately before update;
        # a changed registry target or missing executable aborts the operation.
        if installed_version is None:
            raise RunnerError("upgrade 必须显式提供已安装 baseline 版本")
        _verified_uninstall_entry(install_root, installed_version)
        _installed_desktop(install_root)
        executable, arguments = _nsis_install_command(
            installer.path, install_root, require_existing=True
        )
    else:
        executable, arguments = _nsis_install_command(installer.path, install_root)
    run = _run_raw(executable, arguments, timeout=timeout)
    if not run["completed"]:
        raise RunnerError(f"{installer.role} NSIS 返回非零退出码")
    entry, _, _ = _verified_uninstall_entry(install_root, installer.version)
    desktop = _installed_desktop(install_root)
    return {
        "installerVersion": installer.version,
        "installerExitCode": run["exitCode"],
        "displayVersion": entry.get("displayVersion"),
        "desktopName": desktop.name,
        "installRootVerified": True,
    }


def _uninstall(install_root: Path, expected_version: str, timeout: float) -> dict[str, Any]:
    _, executable, _ = _verified_uninstall_entry(install_root, expected_version)
    # Run the verified installed NSIS uninstaller normally so NSIS can copy
    # itself to its temporary location and remove uninstall.exe afterwards.
    # Supplying _?= disables that self-copy and leaves the installed
    # uninstaller behind after the process exits.
    run = _run_raw(executable, "/S", timeout=timeout)
    if not run["completed"]:
        raise RunnerError("NSIS 卸载器返回非零退出码")
    deadline = time.monotonic() + min(timeout, 20.0)
    install_root_present = install_root.exists()
    rows: list[dict[str, Any]] = []
    registry_error: str | None = "not_queried"
    location: str | None = "not_queried"
    location_error: str | None = "not_queried"
    while time.monotonic() < deadline:
        install_root_present = install_root.exists()
        rows, registry_error = _registry_entries()
        location, location_error = _manufacturer_install_location()
        product_entry_present = any(
            row.get("displayName") == PRODUCT_NAME for row in rows
        )
        if (
            not install_root_present
            and registry_error is None
            and not product_entry_present
            and location_error is None
            and location is None
        ):
            return {
                "uninstallerExitCode": run["exitCode"],
                "installRootRemoved": True,
            }
        time.sleep(0.1)
    if install_root_present:
        raise RunnerError("卸载后安装根目录仍存在")
    if registry_error:
        raise RunnerError("卸载后无法复核 HKCU 卸载项")
    if any(row.get("displayName") == PRODUCT_NAME for row in rows):
        raise RunnerError("卸载后 HKCU 卸载项仍存在")
    if location_error:
        raise RunnerError("卸载后无法复核 HKCU 厂商安装位置")
    if location is not None:
        raise RunnerError("卸载后 HKCU 厂商安装位置仍存在")
    raise RunnerError("卸载最终状态未在限定时间内稳定")


def _base_result(
    args: argparse.Namespace,
    run_dir: Path,
    baseline: InstallerInput | None,
    upgrade: InstallerInput | None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "id": f"windows_install_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}_{os.getpid()}",
        "startedAt": _now(),
        "completedAt": None,
        "status": "failed",
        "environment": {
            "platform": sys.platform,
            "os": platform.system(),
            "osRelease": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "inputs": {
            "baseline": None if baseline is None else baseline.public(),
            "upgrade": None if upgrade is None else upgrade.public(),
            "sandboxRootProvided": True,
            "readyTimeoutSeconds": args.ready_timeout_seconds,
            "exitTimeoutSeconds": args.exit_timeout_seconds,
        },
        "isolation": {
            "installRootInitiallyAbsent": True,
            "homeInitiallyEmpty": True,
            "sandboxCreatedByRunner": True,
            "currentUserRegistryOnly": True,
            "defaultInstallDirectoryUsed": False,
            "userDataDeletionAllowed": False,
            "processNameTerminationAllowed": False,
            "absolutePathsOmittedFromArtifact": True,
        },
        "checks": [],
        "phases": [],
        "limitations": [
            "只针对调用者明确提供的两个 Windows current-user NSIS 工件",
            "只读写 Runner 拥有的安装根目录与 AGENT_AUDIT_HOME，不外推为干净 Windows 机器证据",
        ],
        "artifacts": {
            "json": "windows-install-lifecycle.json",
            "markdown": "windows-install-lifecycle.md",
            "directory": run_dir.name,
        },
    }


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Windows 安装、升级与卸载验收",
        "",
        f"- 状态：`{result['status']}`",
        f"- Run ID：`{result['id']}`",
        f"- 开始：`{result['startedAt']}`",
        f"- 完成：`{result['completedAt']}`",
        "",
        "## 工件",
        "",
        "| 角色 | 版本 | 文件 | SHA-256 |",
        "|---|---|---|---|",
    ]
    for key in ("baseline", "upgrade"):
        item = result["inputs"].get(key)
        if item:
            lines.append(
                f"| `{key}` | `{item['version']}` | `{item['name']}` | `{item['sha256']}` |"
            )
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| ID | 状态 | 详情 |",
            "|---|---|---|",
        ]
    )
    for check in result["checks"]:
        lines.append(
            f"| `{check['id']}` | `{check['status']}` | {check.get('detail') or ''} |"
        )
    lines.extend(["", "## 阶段", ""])
    for phase in result["phases"]:
        lines.append(f"- `{phase['id']}`：`{phase['status']}`")
    lines.extend(["", "## 限制与边界", ""])
    lines.extend(f"- {item}" for item in result["limitations"])
    lines.extend(
        [
            "",
            "## 工件来源",
            "",
            "本 Markdown 仅由同目录 `windows-install-lifecycle.json` 投影，不重新计算验收结论。",
            "",
        ]
    )
    return "\n".join(lines)


def _write(result: dict[str, Any], run_dir: Path) -> None:
    (run_dir / "windows-install-lifecycle.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (run_dir / "windows-install-lifecycle.md").write_text(
        _markdown(result), encoding="utf-8"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="windows-install-lifecycle-runner", allow_abbrev=False
    )
    parser.add_argument("--baseline-installer", required=True)
    parser.add_argument("--baseline-version", required=True)
    parser.add_argument("--upgrade-installer", required=True)
    parser.add_argument("--upgrade-version", required=True)
    parser.add_argument(
        "--sandbox-root",
        required=True,
        help="运行前不存在且不含空格的绝对目录；由 Runner 创建和持有",
    )
    parser.add_argument("--ready-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--exit-timeout-seconds", type=float, default=12.0)
    return parser


def _preflight(
    args: argparse.Namespace, run_dir: Path, install_root: Path
) -> dict[str, Any]:
    baseline = _installer(args.baseline_installer, args.baseline_version, "baseline")
    upgrade = _installer(args.upgrade_installer, args.upgrade_version, "upgrade")
    if baseline.path == upgrade.path or baseline.sha256 == upgrade.sha256:
        raise RunnerError("基线与升级安装包必须是两个不同工件")
    if _version(upgrade.version, "--upgrade-version") <= _version(
        baseline.version, "--baseline-version"
    ):
        raise RunnerError("升级版本必须严格高于基线版本")
    baseline_command = _nsis_install_command(baseline.path, install_root)
    _assert_no_existing_installation()
    result = _base_result(args, run_dir, baseline, upgrade)
    result["checks"].extend(
        [
            {"id": "distinct_versioned_installers", "status": "passed", "detail": None},
            {
                "id": "isolated_nsis_destination",
                "status": "passed",
                "detail": "space-free runner-owned sandbox; raw /S with final unquoted /D argument",
            },
            {
                "id": "no_existing_current_user_installation",
                "status": "passed",
                "detail": "HKCU uninstall and manufacturer product location absent",
            },
            {
                "id": "lifecycle_execution",
                "status": "not_verified",
                "detail": "implementation gate: no installer was executed",
            },
        ]
    )
    result["phases"].append(
        {
            "id": "preflight",
            "status": "passed",
            "installerCommand": [baseline_command[0].name, "/S", "/D=<isolated-install-root>"],
        }
    )
    result["status"] = "not_verified"
    result["completedAt"] = _now()
    return result


def _execute_lifecycle(
    args: argparse.Namespace,
    result: dict[str, Any],
    baseline: InstallerInput,
    upgrade: InstallerInput,
    install_root: Path,
    home: Path,
) -> dict[str, Any]:
    result["checks"] = [
        check for check in result["checks"] if check["id"] != "lifecycle_execution"
    ]
    install_timeout = max(args.ready_timeout_seconds, 60.0)
    _phase(
        result,
        "baseline_install",
        lambda: _install(baseline, install_root, install_timeout),
    )

    marker: dict[str, str] = {}

    def first_launch() -> dict[str, Any]:
        desktop = _installed_desktop(install_root)

        def action(port: int) -> dict[str, Any]:
            marker["id"] = _write_marker(port)
            return {"markerDocumentId": marker["id"]}

        session = _desktop_session(
            desktop,
            home,
            args.ready_timeout_seconds,
            args.exit_timeout_seconds,
            action,
        )
        if session["status"] != "passed":
            raise RunnerError("baseline Desktop 启停或 marker 写入失败")
        return session

    _phase(result, "baseline_launch_and_marker", first_launch)
    workspace_root, _ = _workspace_paths(home)
    history_evidence = _phase(
        result,
        "controlled_history",
        lambda: _create_controlled_history(workspace_root),
    )
    before = _phase(
        result,
        "baseline_snapshot",
        lambda: _workspace_snapshot(home, marker["id"]),
    )
    if not set(history_evidence["scanIds"]).issubset(
        set(before["database"]["auditRunIds"])
    ):
        raise RunnerError("StabilityRunner scan ID 未进入真实 audit_runs")
    if not set(history_evidence["acceptanceIds"]).issubset(
        set(before["database"]["acceptanceRunIds"])
    ):
        raise RunnerError("Acceptance Run ID 未进入真实 acceptance_runs")

    _phase(
        result,
        "upgrade_install",
        lambda: _install(
            upgrade,
            install_root,
            install_timeout,
            installed_version=baseline.version,
        ),
    )
    upgraded_session = _phase(
        result,
        "upgraded_launch",
        lambda: _desktop_session(
            _installed_desktop(install_root),
            home,
            args.ready_timeout_seconds,
            args.exit_timeout_seconds,
        ),
    )
    if upgraded_session["status"] != "passed":
        raise RunnerError("upgrade Desktop 启停或进程清理失败")
    after_upgrade = _phase(
        result,
        "upgrade_data_preserved",
        lambda: _workspace_snapshot(home, marker["id"]),
    )
    _assert_preserved(before, after_upgrade)

    _phase(
        result,
        "uninstall",
        lambda: _uninstall(install_root, upgrade.version, install_timeout),
    )
    after_uninstall = _phase(
        result,
        "uninstall_user_data_preserved",
        lambda: _workspace_snapshot(home, marker["id"]),
    )
    _assert_preserved(before, after_uninstall)
    result["checks"].append(
        {
            "id": "complete_install_upgrade_uninstall",
            "status": "passed",
            "detail": "two distinct versions; workspace and history preserved",
        }
    )
    result["status"] = "passed"
    result["completedAt"] = _now()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.ready_timeout_seconds <= 0 or args.exit_timeout_seconds <= 0:
        parser.error("超时必须大于 0")
    run_dir: Path | None = None
    try:
        install_root, home, run_dir, sandbox = _prepare_directories(args.sandbox_root)
        result = _preflight(args, run_dir, install_root)
        if sys.platform != "win32":
            result["status"] = "not_verified"
            result["limitations"].append("Windows-only lifecycle was not executed on this platform")
        else:
            baseline = _installer(
                args.baseline_installer, args.baseline_version, "baseline"
            )
            upgrade = _installer(args.upgrade_installer, args.upgrade_version, "upgrade")
            result = _execute_lifecycle(
                args, result, baseline, upgrade, install_root, home
            )
    except RunnerError as exc:
        if run_dir is None:
            print(
                json.dumps(
                    {"status": "failed", "error": _safe(exc, ())}, ensure_ascii=False
                ),
                file=sys.stderr,
            )
            return 2
        if "result" not in locals():
            result = _base_result(args, run_dir, None, None)
            result["checks"].append(
                {
                    "id": "runner_setup",
                    "status": "failed",
                    "detail": _safe(exc, (Path(args.sandbox_root),)),
                }
            )
        else:
            result["status"] = "failed"
            result["limitations"].append(
                "Lifecycle stopped at the first failed phase; sandbox and user data were not deleted"
            )
        result["completedAt"] = _now()
    _write(result, run_dir)
    print(
        json.dumps(
            {"status": result["status"], "directory": run_dir.name}, ensure_ascii=False
        )
    )
    if result["status"] == "passed":
        return 0
    if result["status"] == "not_verified":
        return 3
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
