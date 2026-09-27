"""F-026 path and portable Workspace contract tests."""

from __future__ import annotations

import json
import sqlite3
import shutil
from pathlib import Path

import pytest

from agent_audit_api.app_paths import APP_HOME_ENV, resolve_app_paths
from agent_audit_api.workspace import (
    MANIFEST_FILENAME,
    WorkspaceError,
    WorkspaceManifest,
    WorkspaceService,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def test_explicit_app_home_override_is_deterministic_and_side_effect_free(tmp_path: Path) -> None:
    override = tmp_path / "agent-audit-home"
    paths = resolve_app_paths(override)

    assert paths.home_dir == override
    assert paths.config_dir == override / "config"
    assert paths.data_dir == override / "data"
    assert paths.runtime_dir == override / "data"
    assert paths.logs_dir == override / "logs"
    assert paths.default_workspace_dir == override / "workspaces" / "default"
    assert not override.exists()


def test_explicit_override_wins_over_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(APP_HOME_ENV, str(tmp_path / "from-env"))

    paths = resolve_app_paths(tmp_path / "explicit")

    assert paths.home_dir == tmp_path / "explicit"


def test_windows_default_uses_localappdata_without_using_a_repository_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # ``resolve_app_paths`` only consults the platform branch while resolving;
    # patching ``sys.platform`` makes the Windows semantic test portable.
    import agent_audit_api.app_paths as app_paths_module

    local_app_data = tmp_path / "LocalAppData"
    monkeypatch.setattr(app_paths_module.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv(APP_HOME_ENV, raising=False)

    paths = resolve_app_paths()

    assert paths.home_dir == local_app_data / "AgentAudit"
    assert paths.default_workspace_dir == local_app_data / "AgentAudit" / "workspaces" / "default"
    assert REPOSITORY_ROOT not in paths.home_dir.parents


def test_linux_default_uses_split_xdg_config_data_and_state_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import agent_audit_api.app_paths as app_paths_module

    config_home = tmp_path / "xdg-config"
    data_home = tmp_path / "xdg-data"
    state_home = tmp_path / "xdg-state"
    monkeypatch.setattr(app_paths_module.sys, "platform", "linux")
    monkeypatch.delenv(APP_HOME_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))

    paths = resolve_app_paths()

    assert paths.home_dir == data_home / "agent-audit"
    assert paths.data_dir == data_home / "agent-audit"
    assert paths.runtime_dir == state_home / "agent-audit"
    assert paths.config_dir == config_home / "agent-audit"
    assert paths.logs_dir == state_home / "agent-audit"
    assert paths.default_workspace_dir == data_home / "agent-audit" / "workspaces" / "default"
    assert REPOSITORY_ROOT not in paths.home_dir.parents


def test_linux_default_xdg_paths_have_standard_home_fallbacks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import agent_audit_api.app_paths as app_paths_module

    fake_home = tmp_path / "user-home"
    monkeypatch.setattr(app_paths_module.sys, "platform", "linux")
    monkeypatch.setattr(
        app_paths_module.Path,
        "home",
        classmethod(lambda cls: fake_home),
    )
    monkeypatch.delenv(APP_HOME_ENV, raising=False)
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(name, raising=False)

    paths = resolve_app_paths()

    assert paths.config_dir == fake_home / ".config" / "agent-audit"
    assert paths.data_dir == fake_home / ".local" / "share" / "agent-audit"
    assert paths.runtime_dir == fake_home / ".local" / "state" / "agent-audit"
    assert paths.logs_dir == fake_home / ".local" / "state" / "agent-audit"
    assert paths.default_workspace_dir == paths.data_dir / "workspaces" / "default"
    assert paths.home_dir == paths.data_dir


def test_workspace_create_writes_relative_manifest_and_all_seed_assets(tmp_path: Path) -> None:
    root = tmp_path / "workspace"

    workspace = WorkspaceService().create(root, "测试 Workspace", seed_dir=DEMO_SEED)

    assert workspace.root == root.resolve()
    assert workspace.manifest_path == root / MANIFEST_FILENAME
    manifest_payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert manifest_payload["name"] == "测试 Workspace"
    assert manifest_payload["version"] == 1
    assert manifest_payload["schemaVersion"] == 2
    for field in ("documentsDir", "contractDir", "casesDir", "historyDir", "exportsDir"):
        value = manifest_payload[field]
        assert not Path(value).is_absolute()
        assert ".." not in Path(value).parts
        assert str(root) not in value

    assert workspace.actors_path.is_file()
    assert workspace.documents_file_path.is_file()
    assert workspace.customers_path.is_file()
    assert workspace.security_contract_path.is_file()
    assert workspace.attack_cases_path.is_file()
    assert workspace.target_profiles_path.is_file()
    assert workspace.ground_truth_cases_path.is_file()
    assert workspace.history_database_path.parent == workspace.history_path
    assert workspace.exports_path.is_dir()


def test_workspace_move_can_be_reopened_without_original_absolute_path(tmp_path: Path) -> None:
    original = tmp_path / "first-location" / "workspace"
    moved = tmp_path / "second-location" / "workspace"
    service = WorkspaceService()
    workspace = service.create(original, "可移动 Workspace", seed_dir=DEMO_SEED)
    old_contract = workspace.security_contract_path.read_text(encoding="utf-8")
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        connection.execute("PRAGMA journal_mode = DELETE")
        from agent_audit_api.sqlite_schema import SQLiteSchemaManager

        SQLiteSchemaManager(workspace.history_database_path).ensure(connection)
        connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('history sentinel')")
        connection.commit()
    finally:
        connection.close()

    moved.parent.mkdir(parents=True)
    original.rename(moved)
    reopened = service.open(moved)

    assert reopened.root == moved.resolve()
    assert reopened.security_contract_path.read_text(encoding="utf-8") == old_contract
    with sqlite3.connect(reopened.history_database_path) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == "history sentinel"
    manifest_text = reopened.manifest_path.read_text(encoding="utf-8")
    assert str(original) not in manifest_text
    assert str(moved) not in manifest_text


def test_ensure_default_creates_once_and_never_overwrites_contract_or_history(tmp_path: Path) -> None:
    app_home = tmp_path / "app-home"
    service = WorkspaceService(resolve_app_paths(app_home))
    first = service.ensure_default(DEMO_SEED)
    first_contract = json.loads(first.security_contract_path.read_text(encoding="utf-8"))
    first_contract["name"] = "管理员已确认的 Contract"
    first.security_contract_path.write_text(
        json.dumps(first_contract, ensure_ascii=False), encoding="utf-8"
    )
    connection = sqlite3.connect(first.history_database_path)
    try:
        connection.execute("PRAGMA journal_mode = DELETE")
        from agent_audit_api.sqlite_schema import SQLiteSchemaManager

        SQLiteSchemaManager(first.history_database_path).ensure(connection)
        connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('existing history')")
        connection.commit()
    finally:
        connection.close()

    second = service.ensure_default(tmp_path / "missing-seed")

    assert second.root == first.root
    assert json.loads(second.security_contract_path.read_text(encoding="utf-8"))["name"] == (
        "管理员已确认的 Contract"
    )
    with sqlite3.connect(second.history_database_path) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == "existing history"


def test_workspace_rejects_path_escape_and_unknown_data_file(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    workspace = WorkspaceService().create(root, "安全 Workspace", seed_dir=DEMO_SEED)
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload["documentsDir"] = "../outside"
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorkspaceError, match="invalid"):
        WorkspaceService().open(root)

    valid = WorkspaceService().create(tmp_path / "valid", "有效 Workspace", seed_dir=DEMO_SEED)
    with pytest.raises(WorkspaceError, match="unknown workspace data file"):
        valid.data_path("secrets")


def test_workspace_create_rejects_nonempty_existing_root(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "user-file.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(WorkspaceError, match="must not already contain files"):
        WorkspaceService().create(root, "不可覆盖", seed_dir=DEMO_SEED)


@pytest.mark.parametrize(
    "documents_dir",
    ("/absolute/documents", r"C:\absolute\documents", r"nested\documents"),
)
def test_manifest_rejects_nonportable_directory_paths(documents_dir: str) -> None:
    with pytest.raises(ValueError, match="relative|forward slashes"):
        WorkspaceManifest(
            id="portable-workspace",
            name="Portable Workspace",
            documents_dir=documents_dir,
        )


def test_workspace_create_validates_complete_seed_before_creating_root(tmp_path: Path) -> None:
    incomplete_seed = tmp_path / "incomplete-seed"
    shutil.copytree(DEMO_SEED, incomplete_seed)
    (incomplete_seed / "ground_truth_cases.json").unlink()
    root = tmp_path / "workspace"

    with pytest.raises(WorkspaceError, match="seed file is missing"):
        WorkspaceService().create(root, "Incomplete Seed", seed_dir=incomplete_seed)

    assert not root.exists()


def test_workspace_declared_nested_directories_remain_under_root(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    workspace = WorkspaceService().create(root, "嵌套目录 Workspace", seed_dir=DEMO_SEED)
    manifest = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    manifest["documentsDir"] = "data/documents"
    # Moving the existing seed directory and manifest field exercises the
    # manifest-relative resolution instead of assuming fixed directory names.
    (root / "data").mkdir()
    shutil.move(str(root / "documents"), str(root / "data" / "documents"))
    workspace.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    reopened = WorkspaceService().open(root)

    assert reopened.documents_path == (root / "data" / "documents").resolve()
    assert reopened.actors_path.is_file()
