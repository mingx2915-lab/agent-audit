"""F-029 unit coverage for portable Workspace backup and restore."""

from __future__ import annotations

import io
import json
import sqlite3
import stat
import zipfile
from pathlib import Path

import pytest

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.workspace import MANIFEST_FILENAME, WorkspaceError, WorkspaceService
from agent_audit_api.workspace_archive import (
    BACKUP_METADATA_FILENAME,
    BACKUP_WORKSPACE_PREFIX,
    WorkspaceArchiveService,
    WorkspaceArchiveStorageError,
    WorkspaceArchiveValidationError,
    WorkspaceBackupPreview,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def _workspace(tmp_path: Path):
    paths = resolve_app_paths(tmp_path / "app-home")
    root = paths.default_workspace_dir
    workspace = WorkspaceService(paths).create(root, "备份测试 Workspace", seed_dir=DEMO_SEED)
    return paths, workspace


def _seed_history(workspace) -> None:
    with sqlite3.connect(workspace.history_database_path) as connection:
        connection.execute("CREATE TABLE audit_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO audit_marker(value) VALUES (?)", ("scan-001",))
        connection.commit()
    workspace.history_database_path.with_name(
        f"{workspace.history_database_path.name}-wal"
    ).write_bytes(b"must not be archived")
    workspace.history_database_path.with_name(
        f"{workspace.history_database_path.name}-shm"
    ).write_bytes(b"must not be archived")


def _zip_bytes(entries: dict[str, bytes | zipfile.ZipInfo]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            if isinstance(content, zipfile.ZipInfo):
                archive.writestr(content, b"link")
            else:
                archive.writestr(name, content)
    return output.getvalue()


def test_backup_contains_complete_portable_workspace_and_restores_as_new_copy(
    tmp_path: Path,
) -> None:
    paths, workspace = _workspace(tmp_path)
    _seed_history(workspace)
    (workspace.exports_path / "acceptance-report.md").write_text(
        "本地验收报告", encoding="utf-8"
    )

    service = WorkspaceArchiveService(workspace, app_paths=paths)
    payload = service.backup()

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert BACKUP_METADATA_FILENAME in names
        assert f"{BACKUP_WORKSPACE_PREFIX}{MANIFEST_FILENAME}" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}documents/actors.json" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}documents/knowledge_documents.json" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}documents/customers.json" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}contract/security_contract.json" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}cases/attack_cases.json" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}cases/target_profiles.json" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}cases/ground_truth_cases.json" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}history/agent_audit.sqlite3" in names
        assert f"{BACKUP_WORKSPACE_PREFIX}history/agent_audit.sqlite3-wal" not in names
        assert f"{BACKUP_WORKSPACE_PREFIX}history/agent_audit.sqlite3-shm" not in names
        assert f"{BACKUP_WORKSPACE_PREFIX}exports/acceptance-report.md" in names
        assert all(not Path(name).is_absolute() for name in names)
        archive_bytes = b"".join(archive.read(name) for name in sorted(names))

    # The archive has no source-machine path in its names or metadata.
    assert str(workspace.root).encode() not in archive_bytes
    assert str(paths.home_dir).encode() not in archive_bytes

    preview = service.preview(payload)
    assert isinstance(preview, WorkspaceBackupPreview)
    assert preview.format_version == 1
    assert preview.workspace.id == workspace.manifest.id
    assert preview.workspace.active is False
    assert preview.workspace.document_count == len(
        json.loads(workspace.documents_file_path.read_text(encoding="utf-8"))
    )
    assert preview.workspace.history_included is True
    assert preview.archive_size_bytes == len(payload)

    restored = service.restore(payload)
    assert restored.restored is True
    assert restored.restart_required is True
    assert restored.workspace.active is False
    assert restored.workspace.relative_directory.startswith("restored-")
    restored_root = paths.default_workspace_dir.parent / restored.workspace.relative_directory
    restored_workspace = WorkspaceService(paths).open(restored_root)

    assert restored_workspace.manifest.id == workspace.manifest.id
    assert restored_workspace.security_contract_path.read_bytes() == (
        workspace.security_contract_path.read_bytes()
    )
    assert restored_workspace.documents_file_path.read_bytes() == (
        workspace.documents_file_path.read_bytes()
    )
    assert restored_workspace.attack_cases_path.read_bytes() == workspace.attack_cases_path.read_bytes()
    assert (restored_workspace.exports_path / "acceptance-report.md").read_text(
        encoding="utf-8"
    ) == "本地验收报告"
    with sqlite3.connect(restored_workspace.history_database_path) as connection:
        assert connection.execute("SELECT value FROM audit_marker").fetchone() == ("scan-001",)

    # Restore is copy-as-new and never changes the active Workspace.
    assert workspace.manifest_path.is_file()
    assert not (workspace.root / "restored").exists()
    assert sorted(path.name for path in paths.default_workspace_dir.parent.iterdir()) == [
        "default",
        restored.workspace.relative_directory,
    ]
    # Restore must follow AppPaths.default_workspace_dir, never recreate the
    # old data/workspaces location (which could make a bad implementation
    # appear portable while splitting the active Workspace tree).
    assert not (paths.data_dir / "workspaces").exists()


def test_preview_is_read_only_and_restore_failure_leaves_no_listable_half_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths, workspace = _workspace(tmp_path)
    service = WorkspaceArchiveService(workspace, app_paths=paths)
    payload = service.backup()
    before = {
        path.relative_to(workspace.root).as_posix(): path.read_bytes()
        for path in workspace.root.rglob("*")
        if path.is_file()
    }

    service.preview(payload)
    after_preview = {
        path.relative_to(workspace.root).as_posix(): path.read_bytes()
        for path in workspace.root.rglob("*")
        if path.is_file()
    }
    assert after_preview == before
    assert [path.name for path in paths.default_workspace_dir.parent.iterdir()] == ["default"]

    def fail_open(*_args, **_kwargs):
        raise WorkspaceError("synthetic Workspace validation failure")

    monkeypatch.setattr("agent_audit_api.workspace_archive.WorkspaceService.open", fail_open)
    with pytest.raises(WorkspaceArchiveStorageError, match="unable to restore Workspace"):
        service.restore(payload)
    assert [path.name for path in paths.default_workspace_dir.parent.iterdir()] == ["default"]
    assert not any(
        path.name.startswith(".workspace-restore-")
        for path in paths.default_workspace_dir.parent.iterdir()
    )


@pytest.mark.parametrize(
    "payload_factory",
    [
        lambda _valid: b"not a zip",
        lambda _valid: _zip_bytes({"metadata.json": b"{}"}),
        lambda valid: _rewrite_metadata(valid, {"formatVersion": 999}),
        lambda valid: _remove_member(valid, "workspace/agent-audit-workspace.json"),
        lambda valid: _add_member(valid, "workspace/../outside.txt", b"escape"),
        lambda valid: _add_symlink(valid, "workspace/documents/link.txt"),
    ],
)
def test_preview_rejects_invalid_archive_without_creating_workspace(
    payload_factory,
    tmp_path: Path,
) -> None:
    paths, workspace = _workspace(tmp_path)
    service = WorkspaceArchiveService(workspace, app_paths=paths)
    valid = service.backup()
    payload = payload_factory(valid)

    with pytest.raises(WorkspaceArchiveValidationError):
        service.preview(payload)
    assert [path.name for path in paths.default_workspace_dir.parent.iterdir()] == ["default"]


def _archive_entries(payload: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}


def _build_archive(entries: dict[str, bytes]) -> bytes:
    return _zip_bytes(entries)


def _rewrite_metadata(payload: bytes, update: dict[str, object]) -> bytes:
    entries = _archive_entries(payload)
    metadata = json.loads(entries[BACKUP_METADATA_FILENAME].decode("utf-8"))
    metadata.update(update)
    entries[BACKUP_METADATA_FILENAME] = json.dumps(metadata).encode("utf-8")
    return _build_archive(entries)


def _remove_member(payload: bytes, member: str) -> bytes:
    entries = _archive_entries(payload)
    entries.pop(member, None)
    return _build_archive(entries)


def _add_member(payload: bytes, member: str, content: bytes) -> bytes:
    entries = _archive_entries(payload)
    entries[member] = content
    return _build_archive(entries)


def _add_symlink(payload: bytes, member: str) -> bytes:
    entries = _archive_entries(payload)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
        info = zipfile.ZipInfo(member)
        info.create_system = 3
        info.external_attr = stat.S_IFLNK << 16
        archive.writestr(info, b"link")
    return output.getvalue()


def test_backup_storage_error_does_not_create_or_replace_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths, workspace = _workspace(tmp_path)
    service = WorkspaceArchiveService(workspace, app_paths=paths)

    monkeypatch.setattr(
        service,
        "_workspace_files",
        lambda: (_ for _ in ()).throw(WorkspaceArchiveStorageError("synthetic read failure")),
    )
    with pytest.raises(WorkspaceArchiveStorageError, match="synthetic read failure"):
        service.backup()
    assert [path.name for path in paths.default_workspace_dir.parent.iterdir()] == ["default"]


def test_relative_directory_contract_rejects_absolute_or_nested_paths() -> None:
    from agent_audit_api.workspace_archive import WorkspaceSummary

    for value in ("../outside", "folder/name", r"C:\\outside", "/tmp/outside", ""):
        with pytest.raises(ValueError):
            WorkspaceSummary(
                id="workspace-1",
                name="Workspace",
                relative_directory=value,
                contract_id="contract-1",
                contract_version=1,
                document_count=0,
                history_included=False,
                active=False,
            )
