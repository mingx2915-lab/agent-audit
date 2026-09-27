from __future__ import annotations

import io
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.workspace import WorkspaceService
from agent_audit_api.workspace_archive import WorkspaceArchiveService


ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = ROOT / "data" / "demo"
LINUX_RELEASE_SCRIPT = ROOT / "apps" / "desktop" / "scripts" / "build-linux-release.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "linux-release.yml"
ROUNDTRIP_SCRIPT = ROOT / "apps" / "api" / "scripts" / "verify_workspace_archive_roundtrip.py"
CARGO_MANIFEST = ROOT / "apps" / "desktop" / "src-tauri" / "Cargo.toml"
TAURI_CONFIG = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"


def test_linux_release_script_builds_and_smokes_real_three_artifact_set() -> None:
    source = LINUX_RELEASE_SCRIPT.read_text(encoding="utf-8")
    evidence = (LINUX_RELEASE_SCRIPT.parent / "linux_artifact_evidence.py").read_text(
        encoding="utf-8"
    )
    combined = source + evidence
    for required in (
        "build-sidecar.sh",
        "x86_64-unknown-linux-gnu",
        ".deb",
        ".AppImage",
        "agent-audit-sidecar",
        "--appimage-extract-and-run",
        "xvfb-run -a bash -c",
        "openbox --sm-disable",
        "wm_pid=$!",
        "--deb",
        "--appimage",
        "--sidecar",
        "127.0.0.1",
        "sha256",
        "checksums",
    ):
        assert required in combined
    assert "linux_artifact_evidence.py" in source
    assert 'TAURI_LINUX_CONFIG="${REPOSITORY_ROOT}/apps/desktop/src-tauri/tauri.linux.conf.json"' in source
    assert '--config "${TAURI_LINUX_CONFIG}"' in source
    assert "--config apps/desktop/src-tauri/tauri.linux.conf.json" not in source
    assert "--secret-service-verified" in combined
    assert "wine" not in source.casefold()
    assert "cross" not in source.casefold()


def test_linux_workflow_uses_real_ubuntu_runner_and_never_treats_skips_as_passes() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    cargo_manifest = (ROOT / "apps" / "desktop" / "src-tauri" / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    assert "runs-on: ubuntu-" in source
    assert "toolchain: '1.88.0'" in source
    assert 'rust-version = "1.88.0"' in cargo_manifest
    for required in (
        "libwebkit2gtk",
        "libxdo",
        "libayatana-appindicator",
        "librsvg",
        "xvfb",
        "openbox",
        "x11-utils",
        "build-linux-release.sh",
        "upload-artifact",
    ):
        assert required in source.casefold()
    assert "continue-on-error: true" not in source
    assert "wine" not in source.casefold()
    assert "dbus-x11" in source and "gnome-keyring" in source
    assert "dbus-run-session" in source
    assert "gnome-keyring-daemon" in source
    assert "xauth" in source
    assert "cargo build" in source and "--example secret_service_probe --release" in source
    assert "apps/desktop/src-tauri/target/release/examples/secret_service_probe" in source
    assert "--login --components=secrets" in source
    assert "XDG_RUNTIME_DIR" in source and "GNOME_KEYRING_CONTROL" in source
    assert "/dev/urandom" in source and "od -An -N24 -tx1" in source
    assert "AGENT_AUDIT_SECRET_SERVICE_VERIFIED=1" not in source
    assert "export PYTHON_BIN=python" in source
    assert "apps/desktop/src-tauri/target/release/examples/secret_service_probe" in source
    sidecar_build = source.index("bash apps/desktop/scripts/build-sidecar.sh")
    secret_probe = source.index("cargo build --manifest-path")
    full_build = source.index("bash apps/desktop/scripts/build-linux-release.sh")
    assert sidecar_build < secret_probe < full_build
    assert source.index("export PYTHON_BIN=python") < source.index("dbus-run-session -- sh -c")
    sidecar_source = (
        ROOT / "apps" / "desktop" / "scripts" / "build-sidecar.sh"
    ).read_text(encoding="utf-8")
    assert 'PYINSTALLER_CONFIG_DIR:-' in sidecar_source


def test_desktop_package_selects_main_binary_while_probe_is_explicit() -> None:
    cargo = CARGO_MANIFEST.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'default-run = "agent-audit-desktop"' in cargo
    assert "--example secret_service_probe" in workflow


def test_linux_workflow_preserves_toolchain_cache_while_isolating_secret_home() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'original_home="$HOME"' in workflow
    assert 'export HOME="$root/home"' in workflow
    assert 'export CARGO_HOME="${CARGO_HOME:-$original_home/.cargo}"' in workflow
    assert 'export RUSTUP_HOME="${RUSTUP_HOME:-$original_home/.rustup}"' in workflow
    assert 'export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$original_home/.cache}"' in workflow
    assert 'export PATH="$CARGO_HOME/bin:$PATH"' in workflow
    assert workflow.index('original_home="$HOME"') < workflow.index(
        'export HOME="$root/home"'
    )


def test_appimage_runtime_is_pinned_and_passed_to_official_plugin() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    build = LINUX_RELEASE_SCRIPT.read_text(encoding="utf-8")
    assert "LDAI_RUNTIME_FILE" in workflow
    assert (
        "https://github.com/AppImage/type2-runtime/releases/download/20251108/"
        "runtime-x86_64"
    ) in workflow
    assert (
        "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d"
    ) in workflow
    assert "curl --fail --location" in workflow
    assert "sha256sum --check --status" in workflow
    assert 'chmod 755 "$appimage_runtime"' in workflow
    assert workflow.index("LDAI_RUNTIME_FILE") < workflow.index(
        'export HOME="$root/home"'
    )
    assert "--appimage-extract-and-run" in build


def test_bundle_icons_include_linux_png_and_existing_platform_brand_assets() -> None:
    config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    icons = config["bundle"]["icon"]
    assert isinstance(icons, list)
    assert "icons/icon.ico" in icons
    assert "icons/icon.icns" in icons
    png_names = [name for name in icons if name.casefold().endswith(".png")]
    assert png_names
    for relative in icons:
        assert (TAURI_CONFIG.parent / relative).is_file()
    png_checks: list[tuple[bool, bool, bool]] = []
    for relative in png_names:
        with Image.open(TAURI_CONFIG.parent / relative) as image:
            alpha = image.getchannel("A") if image.mode == "RGBA" else None
            corners = (
                ()
                if alpha is None
                else (
                    alpha.getpixel((0, 0)),
                    alpha.getpixel((image.width - 1, 0)),
                    alpha.getpixel((0, image.height - 1)),
                    alpha.getpixel((image.width - 1, image.height - 1)),
                )
            )
            png_checks.append(
                (
                    image.width == image.height,
                    image.mode == "RGBA",
                    bool(corners) and all(value == 0 for value in corners),
                )
            )
    assert any(all(check) for check in png_checks)


def test_linux_bundle_uses_ascii_package_name_without_changing_window_title() -> None:
    base = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
    linux = json.loads(
        (TAURI_CONFIG.parent / "tauri.linux.conf.json").read_text(encoding="utf-8")
    )
    package_name = linux["productName"]
    assert re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", package_name)
    assert package_name == "agent-audit"
    assert base["productName"] == "知盾 AgentAudit"
    assert base["app"]["windows"][0]["title"] == "知盾 AgentAudit"


def test_workspace_archive_is_platform_neutral_and_migration_compatible(tmp_path: Path) -> None:
    windows_paths = resolve_app_paths(tmp_path / "windows-home")
    windows_workspace = WorkspaceService(windows_paths).create(
        windows_paths.default_workspace_dir,
        "Windows Source",
        seed_dir=DEMO_SEED,
    )
    contract_bytes = windows_workspace.security_contract_path.read_bytes()
    documents_bytes = windows_workspace.documents_file_path.read_bytes()
    connection = sqlite3.connect(windows_workspace.history_database_path)
    try:
        from agent_audit_api.sqlite_schema import SQLiteSchemaManager

        SQLiteSchemaManager(windows_workspace.history_database_path).ensure(connection)
        connection.execute("CREATE TABLE platform_marker(value TEXT)")
        connection.execute("INSERT INTO platform_marker VALUES ('windows-to-linux')")
        connection.commit()
    finally:
        connection.close()

    archive = WorkspaceArchiveService(
        windows_workspace, app_paths=windows_paths
    ).backup()
    with zipfile.ZipFile(io.BytesIO(archive)) as payload:
        names = payload.namelist()
        assert len(names) == len(set(names))
        assert all(
            not name.startswith(("/", "\\")) and ".." not in Path(name).parts
            for name in names
        )
        assert all(not name.endswith(("-wal", "-shm")) for name in names)

    linux_paths = resolve_app_paths(tmp_path / "linux-home")
    linux_active = WorkspaceService(linux_paths).create(
        linux_paths.default_workspace_dir, "Linux Active", seed_dir=DEMO_SEED
    )
    result = WorkspaceArchiveService(linux_active, app_paths=linux_paths).restore(archive)
    restored_root = (
        linux_paths.default_workspace_dir.parent / result.workspace.relative_directory
    )
    restored = WorkspaceService(linux_paths).open(restored_root)
    assert restored.manifest.schema_version == 2
    assert restored.security_contract_path.read_bytes() == contract_bytes
    assert restored.documents_file_path.read_bytes() == documents_bytes
    connection = sqlite3.connect(restored.history_database_path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT value FROM platform_marker").fetchone()[0] == (
            "windows-to-linux"
        )
    finally:
        connection.close()

    linux_archive = WorkspaceArchiveService(restored, app_paths=linux_paths).backup()
    roundtrip = WorkspaceArchiveService(
        windows_workspace, app_paths=windows_paths
    ).restore(linux_archive)
    roundtrip_root = (
        windows_paths.default_workspace_dir.parent
        / roundtrip.workspace.relative_directory
    )
    windows_again = WorkspaceService(windows_paths).open(roundtrip_root)
    assert windows_again.security_contract_path.read_bytes() == contract_bytes
    assert windows_again.documents_file_path.read_bytes() == documents_bytes
    connection = sqlite3.connect(windows_again.history_database_path)
    try:
        assert connection.execute("SELECT value FROM platform_marker").fetchone()[0] == (
            "windows-to-linux"
        )
    finally:
        connection.close()


def test_archive_roundtrip_script_writes_machine_evidence_and_regenerated_zip(
    tmp_path: Path,
) -> None:
    paths = resolve_app_paths(tmp_path / "source-home")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "Roundtrip Source", seed_dir=DEMO_SEED
    )
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        from agent_audit_api.sqlite_schema import SQLiteSchemaManager

        SQLiteSchemaManager(workspace.history_database_path).ensure(connection)
        connection.execute(
            "INSERT INTO audit_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "archive-marker", "plan", "contract", 1, "profile", "completed",
                "completed", 1, 0, "start", "end", 1.0, "{}", "{}", "{}", "{}", "{}",
            ),
        )
        connection.commit()
    finally:
        connection.close()
    input_archive = tmp_path / "linux-source.zip"
    input_archive.write_bytes(WorkspaceArchiveService(workspace, paths).backup())
    evidence = tmp_path / "roundtrip.json"
    roundtrip_dir = tmp_path / "roundtrip-artifacts"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROUNDTRIP_SCRIPT),
            "--archive",
            str(input_archive),
            "--output",
            str(evidence),
            "--roundtrip-output-dir",
            str(roundtrip_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(evidence.read_text(encoding="utf-8"))["results"][0]
    regenerated = roundtrip_dir / "linux-source.roundtrip.zip"
    assert regenerated.is_file()
    assert result["input"] == input_archive.name
    assert result["output"] == regenerated.name
    assert result["outputSha256"] == hashlib.sha256(regenerated.read_bytes()).hexdigest()
    assert result["postWorkspaceSchemaVersion"] == 2
    assert result["postSqliteUserVersion"] == 2
    assert result["integrityCheck"] == "ok"
    assert result["rowCounts"]["audit_runs"] == 1
    assert result["markerValue"] == "archive-marker"
    assert result["walShmExcluded"] is True
    assert result["migrationBackupCount"] >= 0
    assert result["passed"] is True


def test_linux_roundtrip_helper_writes_rebackup_without_overwriting_input(
    tmp_path: Path,
) -> None:
    paths = resolve_app_paths(tmp_path / "source-home")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "Portable Source", seed_dir=DEMO_SEED
    )
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        from agent_audit_api.sqlite_schema import SQLiteSchemaManager

        SQLiteSchemaManager(workspace.history_database_path).ensure(connection)
        connection.execute("CREATE TABLE portable_marker(value TEXT)")
        connection.execute("INSERT INTO portable_marker VALUES ('linux-rebackup')")
        connection.commit()
    finally:
        connection.close()
    archive_path = tmp_path / "windows-source.zip"
    archive_path.write_bytes(WorkspaceArchiveService(workspace, app_paths=paths).backup())
    original = archive_path.read_bytes()
    output_dir = tmp_path / "linux-rebackup"
    evidence_path = tmp_path / "roundtrip.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(ROUNDTRIP_SCRIPT),
            "--archive",
            str(archive_path),
            "--output",
            str(evidence_path),
            "--roundtrip-output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert archive_path.read_bytes() == original
    generated = list(output_dir.glob("*.zip"))
    assert len(generated) == 1
    assert generated[0].name == "windows-source.roundtrip.zip"
    assert generated[0].parent == output_dir
    with zipfile.ZipFile(generated[0]) as payload:
        names = payload.namelist()
        assert len(names) == len(set(names))
        assert all(not name.startswith(("/", "\\")) and ".." not in Path(name).parts for name in names)
        assert all(not name.endswith(("-wal", "-shm")) for name in names)
        database_names = [
            name for name in names if name.endswith("/history/agent_audit.sqlite3")
        ]
        assert len(database_names) == 1
        database = tmp_path / "roundtrip.sqlite3"
        database.write_bytes(payload.read(database_names[0]))
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        assert connection.execute("SELECT value FROM portable_marker").fetchone() == (
            "linux-rebackup",
        )
        assert connection.execute("SELECT count(*) FROM audit_runs").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM audit_replays").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM acceptance_runs").fetchone() == (0,)
    finally:
        connection.close()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["results"][0]["roundtripArchive"] == generated[0].name
