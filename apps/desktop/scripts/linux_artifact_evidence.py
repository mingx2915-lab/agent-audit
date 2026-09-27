#!/usr/bin/env python3
"""Run real Linux artifact checks and emit one machine-readable evidence set."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


STATUS_VALUES = {"passed", "failed", "not_verified"}
RUNTIME_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LC_ALL",
    "DISPLAY",
    "XAUTHORITY",
    "DBUS_SESSION_BUS_ADDRESS",
)
# These credential-shaped names are intentionally absent from the allowlist;
# documenting them keeps the evidence trust boundary directly auditable.
RUNTIME_ENV_FORBIDDEN_CREDENTIAL_NAMES = ("TOKEN", "SECRET", "PASSWORD")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, env: dict[str, str] | None = None, timeout: int = 180) -> tuple[str, str]:
    try:
        completed = subprocess.run(
            command,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "failed", type(exc).__name__
    return ("passed", "") if completed.returncode == 0 else ("failed", f"exit_{completed.returncode}")


def process_identity(pid: int) -> tuple[int, int] | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    closing = stat.rfind(")")
    if closing < 0:
        raise ValueError("invalid proc stat")
    fields = stat[closing + 2 :].split()
    state = fields[0]
    if state == "Z":
        return None
    return pid, int(fields[19])


def descendant_pids(root_pid: int) -> set[int]:
    result = subprocess.run(
        ["ps", "-e", "-o", "pid=,ppid="],
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=True,
    )
    children: dict[int, set[int]] = {}
    for line in result.stdout.splitlines():
        pid_text, parent_text = line.split()
        children.setdefault(int(parent_text), set()).add(int(pid_text))
    known: set[int] = set()
    pending = [root_pid]
    while pending:
        parent = pending.pop()
        for child in children.get(parent, set()):
            if child not in known:
                known.add(child)
                pending.append(child)
    return known


def descendant_identities(root_pid: int) -> set[tuple[int, int]]:
    return {
        identity
        for pid in descendant_pids(root_pid)
        if (identity := process_identity(pid)) is not None
    }


def live_identities(
    identities: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    return {
        identity
        for identity in identities
        if process_identity(identity[0]) == identity
    }


def process_group_pids(group_id: int) -> set[int]:
    result = subprocess.run(
        ["ps", "-e", "-o", "pid=,pgid="],
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=True,
    )
    return {
        int(pid)
        for line in result.stdout.splitlines()
        for pid, group in [line.split()]
        if int(group) == group_id
    }


def elf_check(path: Path) -> tuple[str, str]:
    readelf = shutil.which("readelf")
    if readelf is None:
        return "failed", "readelf_unavailable"
    result = subprocess.run(
        [readelf, "-h", str(path)], text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        return "failed", "not_elf"
    if "ELF64" not in result.stdout or "Advanced Micro Devices X86-64" not in result.stdout:
        return "failed", "not_elf_x86_64"
    return "passed", ""


def appimage_excludes_probe(appimage: Path, root: Path) -> tuple[str, str]:
    extraction = root / "appimage-probe-inspection"
    extraction.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [str(appimage), "--appimage-extract"],
        cwd=extraction,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=60,
        check=False,
    )
    member = extraction / "squashfs-root" / "usr" / "bin" / "secret_service_probe"
    if member.exists() or member.is_symlink():
        return "failed", "ci_probe_packaged"
    return (
        ("passed", "")
        if completed.returncode == 0
        else ("failed", f"appimage_extract_exit_{completed.returncode}")
    )


def desktop_smoke(
    command: list[str], *, env: dict[str, str], manifest: Path, status_path: Path
) -> tuple[str, str]:
    try:
        process = subprocess.Popen(
            command,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return "failed", f"desktop_start_{type(exc).__name__}"
    try:
        process_group = os.getpgid(process.pid)
    except OSError as exc:
        process.wait(timeout=10)
        return "failed", f"process_group_{type(exc).__name__}"
    observed_descendants: set[tuple[int, int]] = set()
    result = ("failed", "desktop_smoke_incomplete")
    port: int | None = None
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                observed_descendants.update(descendant_identities(process.pid))
            except (OSError, subprocess.SubprocessError, ValueError):
                result = ("failed", "descendant_query_failed")
                break
            terminal_status = None
            if status_path.is_file():
                try:
                    status = json.loads(status_path.read_text(encoding="utf-8"))
                    if status.get("status") in {"ready", "failed", "stopped"}:
                        terminal_status = status
                except (OSError, ValueError, AttributeError):
                    pass
            if terminal_status is not None or process.poll() is not None:
                break
            time.sleep(0.25)
        if process.poll() is not None:
            result = ("failed", "desktop_exited_before_workspace")
        elif not manifest.is_file() or not status_path.is_file():
            result = ("failed", "workspace_or_status_not_created")
        else:
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                candidate_port = status["port"]
                if status.get("status") != "ready" or not isinstance(candidate_port, int):
                    result = ("failed", "sidecar_not_ready")
                else:
                    port = candidate_port
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/health", timeout=3
                    ) as response:
                        result = (
                            ("passed", "")
                            if response.status == 200
                            else ("failed", "health_not_200")
                        )
            except (OSError, ValueError, KeyError, TypeError):
                result = ("failed", "health_unavailable")
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 15)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, 9)
            process.wait(timeout=10)
        try:
            cleanup_deadline = time.monotonic() + 5
            group_members = process_group_pids(process_group)
            if group_members:
                os.killpg(process_group, 15)
            while time.monotonic() < cleanup_deadline:
                group_members = process_group_pids(process_group)
                if not group_members and not live_identities(observed_descendants):
                    break
                time.sleep(0.05)
            if group_members:
                os.killpg(process_group, 9)
                while time.monotonic() < cleanup_deadline:
                    group_members = process_group_pids(process_group)
                    if not group_members:
                        break
                    time.sleep(0.05)
        except (OSError, subprocess.SubprocessError, ValueError):
            group_members = set()
            result = ("failed", "process_group_query_failed")
        remaining_identities = live_identities(observed_descendants)
        remaining_count = len(remaining_identities) + len(group_members)
        if remaining_count:
            result = ("failed", f"verified_descendants_remained_{remaining_count}")
        if port is not None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1):
                    result = ("failed", "sidecar_port_remained_open")
            except OSError:
                pass
    return result


def check(id_: str, status: str, detail: str = "") -> dict[str, str]:
    if status not in STATUS_VALUES:
        raise ValueError("invalid evidence status")
    return {"id": id_, "status": status, "detail": detail}


def isolated_runtime(
    root: Path, name: str
) -> tuple[dict[str, str], dict[str, Path], Path, Path]:
    runtime = root / name
    roots = {
        "HOME": runtime / "home",
        "XDG_CONFIG_HOME": runtime / "config",
        "XDG_DATA_HOME": runtime / "data",
        "XDG_STATE_HOME": runtime / "state",
        "XDG_CACHE_HOME": runtime / "cache",
        "XDG_RUNTIME_DIR": runtime / "run",
    }
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
    roots["XDG_RUNTIME_DIR"].chmod(0o700)
    env = {
        key: os.environ[key]
        for key in RUNTIME_ENV_ALLOWLIST
        if key in os.environ
    }
    env.update({key: str(value) for key, value in roots.items()})
    env.pop("AGENT_AUDIT_HOME", None)
    app_data = roots["XDG_DATA_HOME"] / "agent-audit"
    # Use a non-default target so an ignored active-workspace pointer cannot
    # accidentally pass through the Sidecar's default seeding path.
    workspace = app_data / "workspaces" / "pointer-target"
    status_path = roots["XDG_STATE_HOME"] / "agent-audit" / "sidecar.status.json"
    return env, roots, workspace, status_path


def verify_xdg_layout(
    roots: dict[str, Path], workspace: Path, status_path: Path
) -> tuple[str, str]:
    config_app = roots["XDG_CONFIG_HOME"] / "agent-audit"
    data_app = roots["XDG_DATA_HOME"] / "agent-audit"
    state_app = roots["XDG_STATE_HOME"] / "agent-audit"
    # The evidence runtime deliberately points at a non-default Workspace.
    # Keep the default path as an explicit negative control: if the Desktop
    # ignores the active pointer, the Sidecar's fallback will seed this path
    # and the smoke must fail instead of claiming pointer consumption.
    default_manifest = data_app / "workspaces" / "default" / "agent-audit-workspace.json"
    expected_manifest = workspace / "agent-audit-workspace.json"
    wrong_layouts = (
        config_app / "workspaces" / "default" / "agent-audit-workspace.json",
        state_app / "workspaces" / "default" / "agent-audit-workspace.json",
        data_app / "sidecar.status.json",
        config_app / "sidecar.status.json",
    )
    valid = (
        len({config_app, data_app, state_app}) == 3
        and expected_manifest.is_file()
        and not default_manifest.exists()
        and status_path == state_app / "sidecar.status.json"
        and status_path.is_file()
        and all(not path.exists() for path in wrong_layouts)
    )
    return ("passed", "") if valid else ("failed", "xdg_layout_mismatch")


def prepare_active_workspace_pointer(roots: dict[str, Path], workspace: Path) -> Path:
    """Create the explicit relative pointer consumed by the real desktop.

    The artifact smoke starts with an isolated, known Workspace.  Writing this
    pointer before launching the packaged application exercises the production
    startup path that reads and validates it; the verification below then
    checks the on-disk artifact after the application has run.
    """
    config_app = roots["XDG_CONFIG_HOME"] / "agent-audit"
    config_app.mkdir(parents=True, exist_ok=True)
    data_app = roots["XDG_DATA_HOME"] / "agent-audit"
    try:
        relative = workspace.relative_to(data_app).as_posix()
    except ValueError as exc:
        raise ValueError("workspace must be inside the isolated XDG data root") from exc
    if relative == "workspaces/default" or not relative.startswith("workspaces/"):
        raise ValueError("pointer evidence requires a non-default Workspace")
    pointer = config_app / "active-workspace.json"
    pointer.write_text(
        json.dumps({"relativeDirectory": relative}, indent=2) + "\n",
        encoding="utf-8",
    )
    return pointer


def verify_active_workspace_pointer(
    roots: dict[str, Path], workspace: Path
) -> tuple[str, str]:
    pointer = roots["XDG_CONFIG_HOME"] / "agent-audit" / "active-workspace.json"
    try:
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        relative = payload.get("relativeDirectory")
        data_app = roots["XDG_DATA_HOME"] / "agent-audit"
        expected = workspace.relative_to(data_app).as_posix()
        target = roots["XDG_DATA_HOME"] / "agent-audit" / relative
        valid = (
            pointer.is_file()
            and isinstance(relative, str)
            and relative == expected
            and relative != "workspaces/default"
            and target == workspace
            and (target / "agent-audit-workspace.json").is_file()
            and not Path(relative).is_absolute()
        )
        return ("passed", "") if valid else ("failed", "active_workspace_pointer_mismatch")
    except (OSError, ValueError, TypeError, AttributeError):
        return "failed", "active_workspace_pointer_invalid"


def verify_picker_evidence(
    evidence_path: Path, appimage: Path, deb: Path
) -> tuple[str, str]:
    """Accept only fresh evidence produced by the real GUI picker harness."""
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        artifacts = {
            item["name"]: item
            for item in payload["artifacts"]
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        expected = (appimage, deb)
        for path in expected:
            item = artifacts.get(path.name)
            if (
                not isinstance(item, dict)
                or item.get("sha256") != sha256(path)
                or item.get("sizeBytes") != path.stat().st_size
            ):
                return "failed", "picker_evidence_artifact_mismatch"
        if (
            payload.get("schemaVersion") != 1
            or payload.get("status") != "passed"
            or payload.get("tool") != "tauri-driver+WebKitWebDriver+xdotool"
        ):
            return "failed", "picker_evidence_provenance_invalid"
        statuses = {
            item.get("id"): item.get("status")
            for item in payload.get("checks", [])
            if isinstance(item, dict)
        }
        required = {"appimage_native_file_selection", "deb_native_file_selection"}
        if required - statuses.keys():
            return "failed", "picker_evidence_checks_missing"
        if any(statuses[item] != "passed" for item in required):
            return "failed", "picker_evidence_not_passed"
        observations = payload.get("observations")
        if not isinstance(observations, dict):
            return "failed", "picker_evidence_observations_missing"
        for label in ("appimage", "deb"):
            observation = observations.get(label)
            if not isinstance(observation, dict):
                return "failed", "picker_evidence_observation_invalid"
            if observation.get("nativeDriver") != "WebKitWebDriver" or observation.get("nativeControl") != "xdotool":
                return "failed", "picker_evidence_tool_invalid"
            if observation.get("returnedToWebView") is not True:
                return "failed", "picker_evidence_webview_return_missing"
            actions = observation.get("initialActions")
            if actions != {"preview": 0, "commit": 0, "scan": 0}:
                return "failed", "picker_evidence_implicit_action_detected"
            selection_actions = observation.get("selectionActions")
            if selection_actions != {"preview": 0, "commit": 0, "scan": 0}:
                return "failed", "picker_evidence_implicit_selection_action_detected"
            display_name = observation.get("displayName")
            selected_text = observation.get("selectedItemText")
            if not isinstance(display_name, str) or not isinstance(selected_text, str) or display_name not in selected_text:
                return "failed", "picker_evidence_selection_not_returned"
        return "passed", ""
    except (OSError, ValueError, TypeError, KeyError):
        return "failed", "picker_evidence_invalid"


def prepare_legacy_workspace(workspace: Path) -> tuple[bytes, str]:
    repository_root = Path(__file__).resolve().parents[3]
    seed = repository_root / "data" / "demo"
    for directory in ("documents", "contract", "cases", "history", "exports"):
        (workspace / directory).mkdir(parents=True, exist_ok=True)
    mapping = {
        "actors.json": "documents/actors.json",
        "knowledge_documents.json": "documents/knowledge_documents.json",
        "customers.json": "documents/customers.json",
        "security_contract.json": "contract/security_contract.json",
        "attack_cases.json": "cases/attack_cases.json",
        "target_profiles.json": "cases/target_profiles.json",
        "ground_truth_cases.json": "cases/ground_truth_cases.json",
    }
    for source, relative in mapping.items():
        shutil.copy2(seed / source, workspace / relative)
    marker = "legacy-business-marker"
    marker_path = workspace / "exports" / "migration-marker.txt"
    marker_path.write_text(marker, encoding="utf-8")
    manifest = {
        "id": "linux-legacy-migration",
        "name": "Linux Legacy Migration",
        "version": 1,
        "schemaVersion": 1,
        "documentsDir": "documents",
        "contractDir": "contract",
        "casesDir": "cases",
        "historyDir": "history",
        "exportsDir": "exports",
    }
    (workspace / "agent-audit-workspace.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    database = workspace / "history" / "agent_audit.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audit_runs (
                scan_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL,
                contract_id TEXT NOT NULL, contract_version INTEGER NOT NULL,
                target_profile_id TEXT NOT NULL, status TEXT NOT NULL,
                stop_reason TEXT NOT NULL, attempt_count INTEGER NOT NULL,
                finding_count INTEGER NOT NULL, started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL, duration_ms REAL NOT NULL,
                scan_json TEXT NOT NULL, plan_json TEXT NOT NULL,
                contract_json TEXT NOT NULL, target_profile_json TEXT NOT NULL,
                runtime_json TEXT NOT NULL
            );
            CREATE TABLE audit_replays (
                scan_id TEXT NOT NULL, replay_id TEXT NOT NULL,
                created_at TEXT NOT NULL, replay_json TEXT NOT NULL,
                PRIMARY KEY (scan_id, replay_id)
            );
            PRAGMA user_version = 1;
            """
        )
        connection.execute(
            "INSERT INTO audit_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-history-marker", "plan", "contract", 1, "profile",
                "completed", "completed", 1, 0, "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:01Z", 1.0, "{}", "{}", "{}", "{}", "{}",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return marker_path.read_bytes(), "legacy-history-marker"


def verify_legacy_migration(workspace: Path, business_marker: bytes, history_marker: str) -> tuple[str, str]:
    try:
        manifest = json.loads(
            (workspace / "agent-audit-workspace.json").read_text(encoding="utf-8")
        )
        database = workspace / "history" / "agent_audit.sqlite3"
        connection = sqlite3.connect(database)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            marker = connection.execute(
                "SELECT scan_id FROM audit_runs WHERE scan_id = ?", (history_marker,)
            ).fetchone()
        finally:
            connection.close()
        backup_root = workspace.parents[1] / "migration-backups"
        backups = list(backup_root.glob("linuxlegacymigration-workspace-v1-sqlite-v1-to-v2.zip"))
        valid = (
            manifest.get("schemaVersion") == 2
            and version == 2
            and marker == (history_marker,)
            and (workspace / "exports" / "migration-marker.txt").read_bytes()
            == business_marker
            and len(backups) == 1
        )
        return ("passed", "") if valid else ("failed", "migration_invariant_failed")
    except (OSError, ValueError, KeyError, sqlite3.Error):
        return "failed", "migration_verification_failed"


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--appimage", type=Path, required=True)
    parser.add_argument("--deb", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--secret-service-verified", action="store_true")
    parser.add_argument(
        "--picker-evidence",
        type=Path,
        help="JSON produced by linux_native_picker_evidence.py",
    )
    args = parser.parse_args()

    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    artifacts = [args.appimage.resolve(), args.deb.resolve(), args.sidecar.resolve()]
    checks: list[dict[str, str]] = []
    for path in artifacts:
        if not path.is_file() or path.is_symlink():
            checks.append(check(f"artifact_{path.name}", "failed", "missing_regular_file"))
        else:
            checks.append(check(f"artifact_{path.name}", "passed"))

    linux = sys.platform == "linux" and platform.machine() == "x86_64"
    if not linux:
        checks.append(check("linux_x86_64_runner", "not_verified", "requires_linux_x86_64"))
    else:
        checks.append(check("linux_x86_64_runner", "passed"))
        file_tool = shutil.which("file")
        if file_tool is None:
            checks.append(check("appimage_format", "failed", "file_unavailable"))
        else:
            appimage_file = subprocess.run(
                [file_tool, str(artifacts[0])], text=True, capture_output=True, check=False
            )
            checks.append(
                check("appimage_format", "passed")
                if appimage_file.returncode == 0
                and "ELF 64-bit" in appimage_file.stdout
                and "x86-64" in appimage_file.stdout
                else check("appimage_format", "failed", "not_appimage_elf_x86_64")
            )
        dpkg = shutil.which("dpkg-deb")
        xvfb = shutil.which("xvfb-run")
        if dpkg is None:
            checks.append(check("deb_metadata", "failed", "dpkg_deb_unavailable"))
        else:
            status, detail = run([dpkg, "--info", str(artifacts[1])])
            checks.append(check("deb_metadata", status, detail))
            if status == "passed":
                control = subprocess.run(
                    [dpkg, "-f", str(artifacts[1]), "Version"],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                checks.append(
                    check("deb_version", "passed")
                    if control.returncode == 0 and control.stdout.strip() == args.version
                    else check("deb_version", "failed", "package_version_mismatch")
                )
                architecture = subprocess.run(
                    [dpkg, "-f", str(artifacts[1]), "Architecture"],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                checks.append(
                    check("deb_architecture", "passed")
                    if architecture.returncode == 0
                    and architecture.stdout.strip() == "amd64"
                    else check("deb_architecture", "failed", "package_architecture_mismatch")
                )

        for identifier, path in (("sidecar_elf", artifacts[2]),):
            status, detail = elf_check(path)
            checks.append(check(identifier, status, detail))

        with tempfile.TemporaryDirectory(prefix="agent-audit-linux-evidence-") as raw:
            root = Path(raw)
            probe_status, probe_detail = appimage_excludes_probe(artifacts[0], root)
            checks.append(
                check("appimage_excludes_secret_service_probe", probe_status, probe_detail)
            )
            appimage_env, appimage_roots, appimage_workspace, appimage_status = isolated_runtime(
                root, "appimage-runtime"
            )
            deb_env, deb_roots, deb_workspace, deb_status = isolated_runtime(
                root, "deb-runtime"
            )
            # Both packaged runtimes must start from a real, valid Workspace so
            # the active relative pointer is exercised by the production
            # startup path in each isolated environment.
            business_marker, history_marker = prepare_legacy_workspace(
                appimage_workspace
            )
            prepare_legacy_workspace(deb_workspace)
            prepare_active_workspace_pointer(appimage_roots, appimage_workspace)
            prepare_active_workspace_pointer(deb_roots, deb_workspace)

            if xvfb is None:
                checks.append(check("appimage_smoke", "not_verified", "xvfb_unavailable"))
                checks.append(
                    check("appimage_xdg_layout", "not_verified", "xvfb_unavailable")
                )
                checks.append(
                    check(
                        "legacy_workspace_migration",
                        "not_verified",
                        "xvfb_unavailable",
                    )
                )
                checks.append(
                    check("appimage_active_workspace_pointer", "not_verified", "xvfb_unavailable")
                )
                checks.append(
                    check("deb_active_workspace_pointer", "not_verified", "xvfb_unavailable")
                )
            else:
                status, detail = desktop_smoke(
                    [xvfb, "-a", str(artifacts[0]), "--appimage-extract-and-run"],
                    env=appimage_env,
                    manifest=appimage_workspace / "agent-audit-workspace.json",
                    status_path=appimage_status,
                )
                checks.append(check("appimage_smoke", status, detail))
                xdg_status, xdg_detail = (
                    verify_xdg_layout(
                        appimage_roots, appimage_workspace, appimage_status
                    )
                    if status == "passed"
                    else ("failed", "desktop_smoke_failed")
                )
                checks.append(check("appimage_xdg_layout", xdg_status, xdg_detail))
                if status == "passed":
                    migration_status, migration_detail = verify_legacy_migration(
                        appimage_workspace, business_marker, history_marker
                    )
                else:
                    migration_status, migration_detail = "failed", "desktop_smoke_failed"
                checks.append(
                    check(
                        "legacy_workspace_migration",
                        migration_status,
                        migration_detail,
                    )
                )
                pointer_status, pointer_detail = verify_active_workspace_pointer(
                    appimage_roots, appimage_workspace
                )
                checks.append(
                    check("appimage_active_workspace_pointer", pointer_status, pointer_detail)
                )

            if dpkg is not None and xvfb is not None:
                extracted = root / "deb-root"
                status, detail = run([dpkg, "-x", str(artifacts[1]), str(extracted)])
                if status == "passed":
                    packaged_probe = extracted / "usr" / "bin" / "secret_service_probe"
                    checks.append(
                        check("deb_excludes_secret_service_probe", "failed", "ci_probe_packaged")
                        if packaged_probe.exists() or packaged_probe.is_symlink()
                        else check("deb_excludes_secret_service_probe", "passed")
                    )
                    desktop_binary = extracted / "usr" / "bin" / "agent-audit-desktop"
                    if not desktop_binary.is_file() or desktop_binary.is_symlink():
                        status, detail = "failed", "desktop_binary_missing_or_unsafe"
                    else:
                        status_elf, detail_elf = elf_check(desktop_binary)
                        checks.append(check("deb_desktop_elf", status_elf, detail_elf))
                        status, detail = desktop_smoke(
                            [xvfb, "-a", str(desktop_binary)],
                            env=deb_env,
                            manifest=deb_workspace / "agent-audit-workspace.json",
                            status_path=deb_status,
                        )
                        xdg_status, xdg_detail = (
                            verify_xdg_layout(deb_roots, deb_workspace, deb_status)
                            if status == "passed"
                            else ("failed", "desktop_smoke_failed")
                        )
                        checks.append(
                            check("deb_xdg_layout", xdg_status, xdg_detail)
                        )
                        pointer_status, pointer_detail = verify_active_workspace_pointer(
                            deb_roots, deb_workspace
                        )
                        checks.append(
                            check("deb_active_workspace_pointer", pointer_status, pointer_detail)
                        )
                checks.append(check("deb_extracted_smoke", status, detail))
                if not any(
                    item["id"] == "deb_excludes_secret_service_probe"
                    for item in checks
                ):
                    checks.append(
                        check(
                            "deb_excludes_secret_service_probe",
                            "failed",
                            "deb_extract_failed",
                        )
                    )
                if not any(item["id"] == "deb_xdg_layout" for item in checks):
                    checks.append(
                        check("deb_xdg_layout", "failed", "deb_smoke_not_started")
                    )
            else:
                checks.append(check("deb_extracted_smoke", "not_verified", "runner_dependency_unavailable"))
                checks.append(
                    check(
                        "deb_xdg_layout",
                        "not_verified",
                        "runner_dependency_unavailable",
                    )
                )
                checks.append(
                    check("deb_active_workspace_pointer", "not_verified", "runner_dependency_unavailable")
                )

            if args.picker_evidence is None:
                checks.extend(
                    [
                        check(
                            "appimage_native_file_selection",
                            "not_verified",
                            "real_gui_picker_evidence_not_supplied",
                        ),
                        check(
                            "deb_native_file_selection",
                            "not_verified",
                            "real_gui_picker_evidence_not_supplied",
                        ),
                    ]
                )
            else:
                picker_status, picker_detail = verify_picker_evidence(
                    args.picker_evidence.resolve(), artifacts[0], artifacts[1]
                )
                checks.extend(
                    [
                        check("appimage_native_file_selection", picker_status, picker_detail),
                        check("deb_native_file_selection", picker_status, picker_detail),
                    ]
                )

            checks.append(
                check("secret_service_probe", "passed")
                if args.secret_service_verified
                else check(
                    "secret_service_probe",
                    "not_verified",
                    "explicit_probe_result_not_supplied",
                )
            )

    files = [
        {"name": path.name, "sha256": sha256(path), "sizeBytes": path.stat().st_size}
        for path in artifacts
        if path.is_file()
    ]
    counts = {status: sum(item["status"] == status for item in checks) for status in STATUS_VALUES}
    status = "failed" if counts["failed"] else ("incomplete" if counts["not_verified"] else "passed")
    summary = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "productVersion": args.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "status": status,
        "counts": counts,
        "checks": checks,
        "artifacts": files,
        "boundaries": [
            "No real Provider or external scan was invoked.",
            "not_verified is never counted as passed.",
            "The Linux active Workspace pointer is checked in each isolated packaged runtime.",
            "Native file selection is passed only when the separately recorded real WebView/GTK evidence matches these artifact hashes.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# AgentAudit Linux Artifact Evidence", "", f"- Status: `{status}`", f"- Version: `{args.version}`", "", "| Check | Status | Detail |", "|---|---|---|"]
    lines.extend(f"| {item['id']} | {item['status']} | {item['detail'] or '—'} |" for item in checks)
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    checksum_lines = [f"{item['sha256']}  {item['name']}" for item in files]
    (output / "checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
