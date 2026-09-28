from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "apps" / "desktop" / "scripts" / "linux_artifact_evidence.py"
PICKER_SCRIPT = ROOT / "apps" / "desktop" / "scripts" / "linux_native_picker_evidence.py"
RUST_PROBE = ROOT / "apps" / "desktop" / "src-tauri" / "examples" / "secret_service_probe.rs"


def _module():
    spec = importlib.util.spec_from_file_location("f055_linux_artifact_evidence", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _picker_module():
    spec = importlib.util.spec_from_file_location("f055_linux_native_picker", PICKER_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_webdriver_failure_route_redacts_session_and_element_ids() -> None:
    module = _picker_module()

    route = module.webdriver_route_label(
        "POST", "/session/transient-session/element/transient-element/click"
    )

    assert route == "POST /session/:session/element/:element/click"


def test_evidence_status_never_counts_not_verified_as_passed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'STATUS_VALUES = {"passed", "failed", "not_verified"}' in source
    assert '"incomplete" if counts["not_verified"] else "passed"' in source
    assert 'return 0 if status == "passed" else 1' in source
    assert "not_verified is never counted as passed" in source


def test_linux_smoke_uses_fresh_home_and_all_xdg_roots_without_agent_audit_home() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for name in (
        "HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
        "XAUTHORITY",
    ):
        assert name in source
    assert 'env.pop("AGENT_AUDIT_HOME", None)' in source
    assert 'def isolated_runtime(' in source
    assert "--appimage-extract-and-run" in source
    assert '[dpkg, "-x"' in source


def test_summary_has_explicit_xdg_checks_and_does_not_claim_manual_checks_passed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'check("appimage_xdg_layout"' in source
    assert 'check("deb_xdg_layout"' in source
    compact = re.sub(r"\s+", "", source)
    assert 'check("appimage_active_workspace_pointer"' in compact
    assert 'check("deb_active_workspace_pointer"' in compact
    assert 'check("appimage_native_file_selection"' in compact
    assert 'check("deb_native_file_selection"' in compact
    assert "active Workspace pointer is covered by Rust/XDG path tests" not in source
    assert "native GUI file selection remains manual external validation" not in source
    assert "real_gui_picker_evidence_not_supplied" in source


def test_appimage_and_deb_smokes_use_independent_complete_runtime_roots() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'def isolated_runtime(' in source
    assert 'appimage-runtime' in source
    assert 'deb-runtime' in source
    assert source.count('env.pop("AGENT_AUDIT_HOME", None)') >= 1
    assert 'shutil.rmtree(app_data, ignore_errors=True)' not in source


def test_linux_evidence_records_real_split_xdg_layout_without_extra_claims() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'def verify_xdg_layout(' in source
    assert '"appimage_xdg_layout"' in source
    assert '"deb_xdg_layout"' in source
    assert 'data_app / "workspaces" / "default" / "agent-audit-workspace.json"' in source
    assert 'state_app / "sidecar.status.json"' in source
    assert 'data_app / "sidecar.status.json"' in source
    assert 'check("appimage_active_workspace_pointer"' in source
    assert 'check("deb_active_workspace_pointer"' in source
    assert 'check("appimage_native_file_selection"' in source
    assert 'check("deb_native_file_selection"' in source


def test_active_workspace_pointer_evidence_requires_non_default_in_root_target(
    tmp_path: Path,
) -> None:
    module = _module()
    roots = {
        "XDG_CONFIG_HOME": tmp_path / "config",
        "XDG_DATA_HOME": tmp_path / "data",
    }
    data_app = roots["XDG_DATA_HOME"] / "agent-audit"
    workspace = data_app / "workspaces" / "pointer-target"
    workspace.mkdir(parents=True)
    (workspace / "agent-audit-workspace.json").write_text("{}", encoding="utf-8")

    pointer = module.prepare_active_workspace_pointer(roots, workspace)

    assert json.loads(pointer.read_text(encoding="utf-8")) == {
        "relativeDirectory": "workspaces/pointer-target"
    }
    assert module.verify_active_workspace_pointer(roots, workspace) == ("passed", "")

    with pytest.raises(ValueError, match="non-default"):
        module.prepare_active_workspace_pointer(
            roots, data_app / "workspaces" / "default"
        )
    with pytest.raises(ValueError, match="inside"):
        module.prepare_active_workspace_pointer(roots, tmp_path / "outside")


def test_linux_native_picker_uses_real_tauri_webdriver_and_scoped_gtk_dialog() -> None:
    source = PICKER_SCRIPT.read_text(encoding="utf-8")
    for required in (
        "tauri-driver",
        "WebKitWebDriver",
        "xdotool",
        "data-testid='document-import-open'",
        "data-testid='document-import-files'",
        "选择企业资料",
        "document-import-item",
        "--appimage-extract-and-run",
        "--deb",
        "initialActions",
        "selectionActions",
        "performance.getEntriesByType",
        "scrollIntoView",
        "display-scale-standard",
        "/element/{element}/click",
        "webdriver_compatibility_precondition",
        "threading.Thread",
        "click_thread",
        "preview_started_on_selection",
        "webdriver_route_label",
        "driverLogTail",
        "stderr=subprocess.STDOUT",
    ):
        assert required in source
    assert "__AGENT_AUDIT_DOCUMENT_PICKER__" not in source
    assert "playwright" not in source.lower()
    assert "browser transport" in source


@pytest.mark.parametrize("overall_status", ["failed", "incomplete"])
def test_picker_evidence_rejects_non_passed_overall_status(
    tmp_path: Path, overall_status: str
) -> None:
    module = _module()
    appimage = tmp_path / "agent-audit.AppImage"
    deb = tmp_path / "agent-audit.deb"
    appimage.write_bytes(b"appimage")
    deb.write_bytes(b"deb")
    action_counts = {"preview": 0, "commit": 0, "scan": 0}
    observations = {
        label: {
            "nativeDriver": "WebKitWebDriver",
            "nativeControl": "xdotool",
            "returnedToWebView": True,
            "initialActions": action_counts,
            "selectionActions": action_counts,
            "displayName": "synthetic-picker.md",
            "selectedItemText": "synthetic-picker.md",
        }
        for label in ("appimage", "deb")
    }
    evidence = tmp_path / "picker-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "status": overall_status,
                "tool": "tauri-driver+WebKitWebDriver+xdotool",
                "artifacts": [
                    {"name": appimage.name, "sha256": module.sha256(appimage), "sizeBytes": appimage.stat().st_size},
                    {"name": deb.name, "sha256": module.sha256(deb), "sizeBytes": deb.stat().st_size},
                ],
                "checks": [
                    {"id": "appimage_native_file_selection", "status": "passed"},
                    {"id": "deb_native_file_selection", "status": "passed"},
                ],
                "observations": observations,
            }
        ),
        encoding="utf-8",
    )

    status, _detail = module.verify_picker_evidence(evidence, appimage, deb)

    assert status == "failed"


def test_desktop_document_pickers_run_blocking_dialog_off_main_thread() -> None:
    source = (ROOT / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(
        encoding="utf-8"
    )
    assert "async fn select_document_files" in source
    assert "async fn select_document_folder" in source
    assert ".blocking_pick_files()" in source
    assert ".blocking_pick_folder()" in source


def test_all_desktop_blocking_file_dialog_commands_are_async() -> None:
    source = (ROOT / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(
        encoding="utf-8"
    )
    for command in (
        "save_workspace_backup",
        "save_diagnostics_archive",
        "select_workspace_backup",
        "select_document_files",
        "select_document_folder",
    ):
        assert f"async fn {command}" in source


def test_linux_release_runs_picker_inside_real_xvfb_display() -> None:
    build = (ROOT / "apps" / "desktop" / "scripts" / "build-linux-release.sh").read_text(
        encoding="utf-8"
    )
    assert "xvfb-run -a bash -c" in build
    assert "openbox --sm-disable" in build
    assert "wm_pid=$!" in build
    assert 'wait "${wm_pid}"' in build
    assert "python3 \"$@\"" in build
    assert '--deb "${DEB_FILES[0]}"' in build
    assert "--picker-evidence" in build


def test_linux_evidence_runs_real_legacy_workspace_migration() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for required in (
        "legacy_workspace_migration",
        '"schemaVersion": 1',
        'manifest.get("schemaVersion") == 2',
        "migration-backups",
        "PRAGMA user_version",
    ):
        assert required in source


def test_linux_smoke_requires_loopback_health_and_closes_exact_process_session() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'f"http://127.0.0.1:{port}/api/health"' in source
    assert 'status.get("status") != "ready"' in source
    assert "start_new_session=True" in source
    assert "os.killpg(process.pid, 15)" in source
    assert "os.killpg(process.pid, 9)" in source
    assert 'result = ("failed", "sidecar_port_remained_open")' in source
    assert 'f"verified_descendants_remained_{remaining_count}"' in source
    assert "process_identity" in source and "live_identities" in source
    assert "cleanup_deadline" in source
    assert 'result = ("failed", "descendant_query_failed")' in source
    assert "os.getpgid" in source
    assert "os.killpg" in source
    assert "pkill" not in source and "killall" not in source


def test_three_artifact_hashes_are_reproducible_and_summary_is_json_source(tmp_path: Path) -> None:
    module = _module()
    artifact = tmp_path / "agent-audit-sidecar"
    artifact.write_bytes(b"\x7fELF\x02\x01x86_64-test-artifact")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert module.sha256(artifact) == expected
    source = SCRIPT.read_text(encoding="utf-8")
    assert "summary.json" in source and "summary.md" in source and "checksums.txt" in source
    assert "productVersion" in source and "architecture" in source
    assert "sizeBytes" in source and "sha256" in source


def test_release_artifacts_must_exclude_ci_secret_service_probe() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'def appimage_excludes_probe(' in source
    assert '[str(appimage), "--appimage-extract"]' in source
    assert '"squashfs-root" / "usr" / "bin" / "secret_service_probe"' in source
    assert 'extracted / "usr" / "bin" / "secret_service_probe"' in source
    assert '"appimage_excludes_secret_service_probe"' in source
    assert '"deb_excludes_secret_service_probe"' in source
    assert '"ci_probe_packaged"' in source


def test_secret_service_probe_is_real_store_read_delete_and_ci_runs_nonzero_test_set() -> None:
    rust = RUST_PROBE.read_text(encoding="utf-8")
    assert "entry.set_password(&secret)" in rust
    assert "entry.get_password()" in rust
    assert "entry.delete_credential()" in rust
    assert "Error::NoEntry" in rust
    assert "secret_service_probe=passed" in rust
    assert "println!(\"{secret}" not in rust
    workflow = (ROOT / ".github" / "workflows" / "linux-release.yml").read_text(
        encoding="utf-8"
    )
    assert "dbus-x11" in workflow and "gnome-keyring" in workflow
    assert "dbus-run-session" in workflow
    assert "gnome-keyring-daemon" in workflow
    assert "cargo build" in workflow and "--example secret_service_probe --release" in workflow
    assert "apps/desktop/src-tauri/target/release/examples/secret_service_probe" in workflow
    assert "--login --components=secrets" in workflow
    assert "XDG_RUNTIME_DIR" in workflow and "GNOME_KEYRING_CONTROL" in workflow
    assert "/dev/urandom" in workflow and "od -An -N24 -tx1" in workflow
    assert "apps/desktop/src-tauri/target/release/examples/secret_service_probe" in workflow
    assert "bash apps/desktop/scripts/build-linux-release.sh" in workflow
    evidence = SCRIPT.read_text(encoding="utf-8")
    assert "dbus-run-session" not in evidence
    assert "gnome-keyring-daemon" not in evidence
    assert 'parser.add_argument("--secret-service-verified"' in evidence


def test_secret_service_probe_is_an_explicit_example_and_not_a_desktop_binary() -> None:
    old_auto_binary = ROOT / "apps" / "desktop" / "src-tauri" / "src" / "bin" / "secret_service_probe.rs"
    assert not old_auto_binary.exists()
    cargo = (ROOT / "apps" / "desktop" / "src-tauri" / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / ".github" / "workflows" / "linux-release.yml").read_text(
        encoding="utf-8"
    )
    tauri_config = (ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json").read_text(
        encoding="utf-8"
    )
    assert "src/bin/secret_service_probe" not in cargo
    assert "--example secret_service_probe --release" in workflow
    assert "target/release/examples/secret_service_probe" in workflow
    assert '"secret_service_probe"' not in tauri_config


def test_secret_service_fact_is_not_accepted_from_a_naked_environment_flag() -> None:
    build = (ROOT / "apps" / "desktop" / "scripts" / "build-linux-release.sh").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / ".github" / "workflows" / "linux-release.yml").read_text(
        encoding="utf-8"
    )
    assert "secret_service_probe" in build
    assert "AGENT_AUDIT_SECRET_SERVICE_VERIFIED" not in build
    assert "dbus-run-session" in workflow and "gnome-keyring-daemon" in workflow
    assert "build-linux-release.sh" in workflow
    assert "AGENT_AUDIT_SECRET_SERVICE_VERIFIED=1" not in workflow


def test_smoke_runtime_environment_is_allowlisted_and_does_not_inherit_secrets() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "for key, value in os.environ.items()" not in source
    assert "RUNTIME_ENV_ALLOWLIST" in source
    for forbidden in ("TOKEN", "SECRET", "PASSWORD"):
        assert forbidden in source


def test_deb_architecture_is_verified_as_amd64() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"Architecture"' in source
    assert '== "amd64"' in source


def test_desktop_smoke_returns_failed_when_process_start_cannot_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _module()

    def fail_start(*_args, **_kwargs):
        raise OSError("synthetic start failure")

    monkeypatch.setattr(subprocess, "Popen", fail_start)
    assert module.desktop_smoke(
        ["missing-desktop"],
        env={},
        manifest=tmp_path / "manifest.json",
        status_path=tmp_path / "sidecar.status.json",
    ) == ("failed", "desktop_start_OSError")
    source = SCRIPT.read_text(encoding="utf-8")
    assert '(output / "summary.json").write_text' in source
    assert '(output / "summary.md").write_text' in source
    assert '(output / "checksums.txt").write_text' in source


def test_desktop_smoke_waits_through_starting_until_terminal_ready_state() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'status.get("status") in {"ready", "failed", "stopped"}' in source
    assert "status_path.is_file() or process.poll() is not None" not in source


def test_process_identity_excludes_reused_pids_zombies_and_short_lived_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    identities = {(101, 10), (102, 20), (103, 30), (104, 40)}
    observed = {
        101: (101, 99),  # PID reused with a different starttime.
        102: None,  # Zombie is normalized to no live identity.
        103: None,  # Process exited before cleanup observation.
        104: (104, 40),  # Same process remains alive.
    }
    monkeypatch.setattr(module, "process_identity", lambda pid: observed[pid])
    assert module.live_identities(identities) == {(104, 40)}


def test_process_identity_reads_starttime_and_treats_zombie_as_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()

    class FakeStat:
        def __init__(self, text: str) -> None:
            self.text = text

        def read_text(self, **_kwargs) -> str:
            return self.text

    fields = ["S"] + ["0"] * 18 + ["4242"] + ["0"] * 4
    monkeypatch.setattr(module.Path, "read_text", lambda _self, **_kwargs: f"55 (worker) {' '.join(fields)}")
    assert module.process_identity(55) == (55, 4242)
    fields[0] = "Z"
    monkeypatch.setattr(module.Path, "read_text", lambda _self, **_kwargs: f"55 (worker) {' '.join(fields)}")
    assert module.process_identity(55) is None
