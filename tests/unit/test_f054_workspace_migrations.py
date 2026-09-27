from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.sqlite_schema import SQLITE_SCHEMA_VERSION, SQLiteSchemaError
from agent_audit_api.workspace import (
    MANIFEST_FILENAME,
    WORKSPACE_SCHEMA_VERSION,
    WorkspaceError,
    WorkspaceService,
)


ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = ROOT / "data" / "demo"


def _legacy_workspace(tmp_path: Path):
    paths = resolve_app_paths(tmp_path / "app")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "Legacy Workspace", seed_dir=DEMO_SEED
    )
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload.pop("schemaVersion")
    workspace.manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with sqlite3.connect(workspace.history_database_path) as connection:
        connection.execute("CREATE TABLE legacy_marker(value TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO legacy_marker VALUES ('scan-and-acceptance-source')")
        connection.execute("PRAGMA user_version = 0")
    (workspace.exports_path / "report.md").write_text("legacy export", encoding="utf-8")
    return paths, workspace


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_legacy_manifest_and_unversioned_sqlite_migrate_with_complete_backup(tmp_path: Path) -> None:
    paths, legacy = _legacy_workspace(tmp_path)
    wal = legacy.history_database_path.with_name(legacy.history_database_path.name + "-wal")
    shm = legacy.history_database_path.with_name(legacy.history_database_path.name + "-shm")
    wal.write_bytes(b"not an archive member")
    shm.write_bytes(b"not an archive member")

    migrated = WorkspaceService(paths).open(legacy.root)

    assert migrated.manifest.schema_version == WORKSPACE_SCHEMA_VERSION == 2
    with sqlite3.connect(migrated.history_database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SQLITE_SCHEMA_VERSION == 2
        assert connection.execute("SELECT value FROM legacy_marker").fetchone()[0] == (
            "scan-and-acceptance-source"
        )
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"audit_runs", "audit_replays", "acceptance_runs"} <= tables

    backups = list((paths.data_dir / "migration-backups").glob("*.zip"))
    assert len(backups) == 1
    with zipfile.ZipFile(backups[0]) as archive:
        names = set(archive.namelist())
        assert MANIFEST_FILENAME in names
        assert "documents/knowledge_documents.json" in names
        assert "contract/security_contract.json" in names
        assert "cases/attack_cases.json" in names
        assert "history/agent_audit.sqlite3" in names
        assert "exports/report.md" in names
        assert all(not name.endswith(("-wal", "-shm")) for name in names)
        manifest = json.loads(archive.read(MANIFEST_FILENAME))
        assert "schemaVersion" not in manifest
        backup_db = tmp_path / "backup.sqlite3"
        backup_db.write_bytes(archive.read("history/agent_audit.sqlite3"))
    with sqlite3.connect(backup_db) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT value FROM legacy_marker").fetchone()[0] == (
            "scan-and-acceptance-source"
        )


def test_migrated_workspace_reopen_is_idempotent(tmp_path: Path) -> None:
    paths, legacy = _legacy_workspace(tmp_path)
    service = WorkspaceService(paths)
    first = service.open(legacy.root)
    backup_dir = paths.data_dir / "migration-backups"
    first_backups = {path.name: _sha(path) for path in backup_dir.glob("*.zip")}
    manifest_hash = _sha(first.manifest_path)
    database_hash = _sha(first.history_database_path)
    with sqlite3.connect(first.history_database_path) as connection:
        row_counts = {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("legacy_marker", "audit_runs", "audit_replays", "acceptance_runs")
        }

    second = service.open(first.root)

    assert _sha(second.manifest_path) == manifest_hash
    assert _sha(second.history_database_path) == database_hash
    assert {path.name: _sha(path) for path in backup_dir.glob("*.zip")} == first_backups
    with sqlite3.connect(second.history_database_path) as connection:
        assert {
            table: connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in row_counts
        } == row_counts


def test_legacy_manifest_without_history_database_migrates_without_creating_one(
    tmp_path: Path,
) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "No History", seed_dir=DEMO_SEED
    )
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload.pop("schemaVersion")
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    assert not workspace.history_database_path.exists()

    migrated = WorkspaceService(paths).open(workspace.root)

    assert migrated.manifest.schema_version == 2
    assert not migrated.history_database_path.exists()
    backup = next((paths.data_dir / "migration-backups").glob("*.zip"))
    with zipfile.ZipFile(backup) as archive:
        assert MANIFEST_FILENAME in archive.namelist()
        assert "history/agent_audit.sqlite3" not in archive.namelist()


def test_manifest_failure_without_history_database_restores_manifest_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "No History Failure", seed_dir=DEMO_SEED
    )
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload.pop("schemaVersion")
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest_before = workspace.manifest_path.read_bytes()
    original_replace = __import__("os").replace

    def fail_manifest_replace(source, destination) -> None:
        if Path(destination).name == MANIFEST_FILENAME:
            raise OSError("synthetic final manifest failure")
        original_replace(source, destination)

    import agent_audit_api.workspace as workspace_module

    monkeypatch.setattr(workspace_module.os, "replace", fail_manifest_replace)
    with pytest.raises(WorkspaceError, match="migration failed"):
        WorkspaceService(paths).open(workspace.root)

    assert workspace.manifest_path.read_bytes() == manifest_before
    assert not workspace.history_database_path.exists()
    backup = next((paths.data_dir / "migration-backups").glob("*.zip"))
    with zipfile.ZipFile(backup) as archive:
        assert "history/agent_audit.sqlite3" not in archive.namelist()


@pytest.mark.parametrize("missing_kind", ["file", "directory"])
def test_legacy_workspace_missing_required_member_is_rejected_before_migration(
    tmp_path: Path, missing_kind: str
) -> None:
    paths, workspace = _legacy_workspace(tmp_path)
    if missing_kind == "file":
        workspace.documents_file_path.unlink()
    else:
        import shutil

        shutil.rmtree(workspace.cases_path)
    manifest_before = workspace.manifest_path.read_bytes()
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        version_before = connection.execute("PRAGMA user_version").fetchone()[0]
        rows_before = connection.execute("SELECT * FROM legacy_marker").fetchall()
    finally:
        connection.close()

    with pytest.raises(WorkspaceError, match="missing required"):
        WorkspaceService(paths).open(workspace.root)

    assert workspace.manifest_path.read_bytes() == manifest_before
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version_before
        assert connection.execute("SELECT * FROM legacy_marker").fetchall() == rows_before
    finally:
        connection.close()
    assert not (paths.data_dir / "migration-backups").exists()


@pytest.mark.parametrize("schema_version", [0, "2", 3])
def test_invalid_or_future_workspace_schema_is_rejected_without_writes(
    tmp_path: Path, schema_version: object
) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "Future Workspace", seed_dir=DEMO_SEED
    )
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload["schemaVersion"] = schema_version
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    before = workspace.manifest_path.read_bytes()

    with pytest.raises(WorkspaceError, match="schemaVersion is invalid|newer"):
        WorkspaceService(paths).open(workspace.root)

    assert workspace.manifest_path.read_bytes() == before
    assert not (paths.data_dir / "migration-backups").exists()


def test_future_and_corrupt_sqlite_are_diagnostic_and_unchanged(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "Database Workspace", seed_dir=DEMO_SEED
    )
    with sqlite3.connect(workspace.history_database_path) as connection:
        connection.execute("PRAGMA user_version = 99")
        connection.execute("CREATE TABLE preserved(value TEXT)")
        connection.execute("INSERT INTO preserved VALUES ('keep')")
    before = workspace.history_database_path.read_bytes()
    with pytest.raises(WorkspaceError, match="invalid|newer"):
        WorkspaceService(paths).open(workspace.root)
    assert workspace.history_database_path.read_bytes() == before

    workspace.history_database_path.write_bytes(b"not a sqlite database")
    corrupt = workspace.history_database_path.read_bytes()
    with pytest.raises((WorkspaceError, sqlite3.DatabaseError, SQLiteSchemaError)):
        WorkspaceService(paths).open(workspace.root)
    assert workspace.history_database_path.read_bytes() == corrupt


def test_unversioned_database_with_wrong_known_columns_is_not_upgraded(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "Wrong Columns", seed_dir=DEMO_SEED
    )
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload.pop("schemaVersion")
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        connection.execute("CREATE TABLE audit_runs(scan_id TEXT PRIMARY KEY, wrong TEXT)")
        connection.execute("INSERT INTO audit_runs VALUES ('scan-preserved', 'wrong-shape')")
        connection.execute("PRAGMA user_version = 0")
        connection.commit()
    finally:
        connection.close()
    manifest_before = workspace.manifest_path.read_bytes()

    with pytest.raises(WorkspaceError, match="invalid|migration failed"):
        WorkspaceService(paths).open(workspace.root)

    assert workspace.manifest_path.read_bytes() == manifest_before
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT * FROM audit_runs").fetchall() == [
            ("scan-preserved", "wrong-shape")
        ]
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='acceptance_runs'"
        ).fetchone() is None
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("user_version", "statements", "missing"),
    [
        (1, (), "audit_runs"),
        (
            2,
            (
                "CREATE TABLE audit_runs(scan_id TEXT PRIMARY KEY)",
                "CREATE TABLE audit_replays(scan_id TEXT, replay_id TEXT, created_at TEXT, replay_json TEXT)",
            ),
            "acceptance_runs",
        ),
    ],
)
def test_declared_sqlite_version_with_missing_required_tables_is_rejected_without_writes(
    tmp_path: Path, user_version: int, statements: tuple[str, ...], missing: str
) -> None:
    paths = resolve_app_paths(tmp_path / f"app-{user_version}")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir, "Missing Table", seed_dir=DEMO_SEED
    )
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload["schemaVersion"] = 1 if user_version == 1 else 2
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        for statement in statements:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version = {user_version}")
        connection.commit()
    finally:
        connection.close()
    manifest_before = workspace.manifest_path.read_bytes()
    database_before = workspace.history_database_path.read_bytes()

    with pytest.raises(WorkspaceError, match="invalid|migration failed"):
        WorkspaceService(paths).open(workspace.root)

    assert workspace.manifest_path.read_bytes() == manifest_before
    assert workspace.history_database_path.read_bytes() == database_before
    connection = sqlite3.connect(workspace.history_database_path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == user_version
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (missing,)
        ).fetchone() is None
    finally:
        connection.close()


def test_combined_migration_failure_restores_manifest_database_and_rows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths, legacy = _legacy_workspace(tmp_path)
    manifest_before = legacy.manifest_path.read_bytes()
    original_replace = __import__("os").replace

    def fail_manifest_replace(source, destination) -> None:
        if Path(destination).name == MANIFEST_FILENAME:
            raise OSError("synthetic final manifest failure")
        original_replace(source, destination)

    import agent_audit_api.workspace as workspace_module

    monkeypatch.setattr(workspace_module.os, "replace", fail_manifest_replace)
    with pytest.raises(WorkspaceError, match="migration failed"):
        WorkspaceService(paths).open(legacy.root)

    assert legacy.manifest_path.read_bytes() == manifest_before
    with sqlite3.connect(legacy.history_database_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT value FROM legacy_marker").fetchone()[0] == (
            "scan-and-acceptance-source"
        )
    backups = list((paths.data_dir / "migration-backups").glob("*.zip"))
    assert len(backups) == 1
