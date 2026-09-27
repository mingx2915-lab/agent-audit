"""F-029 native-shell boundary checks for backup selection and Workspace activation."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TAURI_ROOT = REPOSITORY_ROOT / "apps" / "desktop" / "src-tauri"


def _rust_source() -> str:
    return (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")


def test_native_backup_commands_keep_absolute_paths_inside_the_dialog_boundary() -> None:
    source = _rust_source()

    assert "fn save_workspace_backup(" in source
    assert "fn select_workspace_backup(" in source
    assert "blocking_save_file()" in source
    assert "blocking_pick_file()" in source
    assert "fs::write(&path, bytes)" in source
    assert "fs::read(&path)" in source
    assert "Ok(false)" in source
    assert "Ok(None)" in source
    assert "MAX_WORKSPACE_BACKUP_BYTES" in source
    assert 'add_filter("AgentAudit Workspace 备份", &["zip"])' in source

    # The renderer receives bytes or a cancellation result, never a selected
    # absolute path. Keep this assertion tied to the two command boundaries.
    save_start = source.index("fn save_workspace_backup(")
    select_start = source.index("fn select_workspace_backup(")
    activate_start = source.index("fn activate_workspace(")
    assert "PathBuf" not in source[save_start:select_start]
    assert "PathBuf" not in source[select_start:activate_start]


def test_activate_workspace_only_accepts_a_valid_child_and_restarts_owned_sidecar() -> None:
    source = _rust_source()

    assert "fn workspace_relative_path(value: &str)" in source
    assert "value.contains(" in source
    assert "WORKSPACE_DIRECTORY_NAME" in source
    assert "validated_workspace_path(&relative_directory)?" in source
    assert "persist_active_workspace(&relative_directory)?" in source
    assert "state.stop_child();" in source
    assert "state.set_launching();" in source
    assert "start_sidecar(app)" in source
    assert "fn active_workspace_pointer_path()" in source
    assert "relative_directory: String" in source
    assert "agent-audit-workspace.json" in source


def test_native_app_roots_match_windows_and_linux_path_semantics_and_pointer_is_relative() -> None:
    source = _rust_source()

    assert '#[cfg(windows)]\nconst APP_DIRECTORY_NAME: &str = "AgentAudit";' in source
    assert '#[cfg(not(windows))]\nconst APP_DIRECTORY_NAME: &str = "agent-audit";' in source

    persist_start = source.index("fn persist_active_workspace(")
    persist_end = source.index("fn sidecar_status_path()", persist_start)
    persist = source[persist_start:persist_end]
    assert "validated_workspace_path(relative_directory)?" in persist
    assert "relative_directory: normalized" in persist
    assert "relative_directory: relative_directory" not in persist
    assert "ActiveWorkspacePointer" in persist


def test_native_command_handler_registers_backup_and_activation_commands() -> None:
    source = _rust_source()
    handler_start = source.index("tauri::generate_handler!")
    handler = source[handler_start:]

    for command in (
        "save_workspace_backup",
        "select_workspace_backup",
        "activate_workspace",
    ):
        assert command in handler


def test_generated_backup_paths_and_binaries_are_not_source_or_external_browser_features() -> None:
    source = _rust_source()
    config = (TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8")

    assert 'const SIDECAR_HOST: &str = "127.0.0.1";' in source
    assert "http://example" not in source
    assert "open::that" not in source
    assert "tauri-plugin-opener" not in (TAURI_ROOT / "Cargo.toml").read_text(
        encoding="utf-8"
    )
    assert "ACTIVE_WORKSPACE_FILENAME" in source
    assert "active-workspace.json" in source
    assert "binaries/agent-audit-sidecar" in config
