"""F-029 API integration coverage for Workspace backup and copy-as-new restore."""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import agent_audit_api.main as main_module
from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.main import create_app
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.workspace import WorkspaceService
from agent_audit_api.workspace_archive import WorkspaceArchiveStorageError
from tests.benchmark_support import GroundTruthProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def _workspace(tmp_path: Path):
    paths = resolve_app_paths(tmp_path / "app-home")
    workspace = WorkspaceService(paths).create(
        paths.default_workspace_dir,
        "API Backup Workspace",
        seed_dir=DEMO_SEED,
    )
    return paths, workspace


def _seed_history(workspace) -> None:
    with sqlite3.connect(workspace.history_database_path) as connection:
        connection.execute("CREATE TABLE audit_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO audit_marker(value) VALUES (?)", ("api-scan-001",))
        connection.commit()
    workspace.history_database_path.with_name(
        f"{workspace.history_database_path.name}-wal"
    ).write_bytes(b"must not be archived")
    workspace.history_database_path.with_name(
        f"{workspace.history_database_path.name}-shm"
    ).write_bytes(b"must not be archived")


def _client(paths, workspace=None, provider: GroundTruthProvider | None = None) -> tuple[TestClient, GroundTruthProvider]:
    active_provider = provider or GroundTruthProvider()
    data = load_demo_data(workspace.documents_path if workspace is not None else None)
    application = create_app(
        provider=active_provider,
        workspace=workspace,
        app_paths=paths,
        retriever=TfidfRetriever(data.documents),
    )
    return TestClient(application), active_provider


def _backup(client: TestClient) -> bytes:
    response = client.get("/api/workspace/backups/current")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/zip")
    assert "attachment" in response.headers.get("content-disposition", "")
    return response.content


def test_workspace_summary_and_download_are_model_free_and_portable(tmp_path: Path) -> None:
    paths, workspace = _workspace(tmp_path)
    (workspace.exports_path / "api-export.json").write_text(
        '{"source":"api-test"}\n', encoding="utf-8"
    )
    provider = GroundTruthProvider()
    client, provider = _client(paths, workspace, provider)

    with client:
        summary_response = client.get("/api/workspace")
        backup = _backup(client)

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["id"] == workspace.manifest.id
    assert summary["name"] == "API Backup Workspace"
    assert summary["relativeDirectory"] == "default"
    assert summary["active"] is True
    assert summary["historyIncluded"] is False
    assert provider.calls == []

    with zipfile.ZipFile(io.BytesIO(backup)) as archive:
        names = archive.namelist()
        assert "metadata.json" in names
        assert "workspace/agent-audit-workspace.json" in names
        assert "workspace/documents/actors.json" in names
        assert "workspace/documents/knowledge_documents.json" in names
        assert "workspace/documents/customers.json" in names
        assert "workspace/contract/security_contract.json" in names
        assert "workspace/cases/attack_cases.json" in names
        assert "workspace/cases/target_profiles.json" in names
        assert "workspace/cases/ground_truth_cases.json" in names
        assert "workspace/exports/api-export.json" in names
        assert "workspace/history/agent_audit.sqlite3-wal" not in names
        assert "workspace/history/agent_audit.sqlite3-shm" not in names
        assert all(not Path(name).is_absolute() for name in names)
        contents = b"".join(archive.read(name) for name in names if not name.endswith("/"))
    assert str(paths.home_dir).encode() not in contents
    assert str(workspace.root).encode() not in contents


def test_preview_is_pure_and_restore_creates_new_workspace_without_overwriting_active(
    tmp_path: Path,
) -> None:
    paths, workspace = _workspace(tmp_path)
    _seed_history(workspace)
    provider = GroundTruthProvider()
    client, provider = _client(paths, workspace, provider)

    with client:
        backup = _backup(client)
        before_contract = workspace.security_contract_path.read_bytes()
        before_workspace_names = sorted(
            path.name for path in paths.default_workspace_dir.parent.iterdir()
        )
        preview_response = client.post(
            "/api/workspace/backups/previews",
            content=backup,
            headers={"Content-Type": "application/zip"},
        )
        after_preview_names = sorted(
            path.name for path in paths.default_workspace_dir.parent.iterdir()
        )
        restore_response = client.post(
            "/api/workspace/restores",
            content=backup,
            headers={"Content-Type": "application/zip"},
        )
        current_after_restore = client.get("/api/workspace")

    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["formatVersion"] == 1
    assert preview["workspace"]["id"] == workspace.manifest.id
    assert preview["workspace"]["active"] is False
    assert preview["workspace"]["historyIncluded"] is True
    assert after_preview_names == before_workspace_names
    assert provider.calls == []

    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    assert restored["restored"] is True
    assert restored["restartRequired"] is True
    assert restored["workspace"]["id"] == workspace.manifest.id
    assert restored["workspace"]["active"] is False
    relative_directory = restored["workspace"]["relativeDirectory"]
    assert relative_directory.startswith("restored-")
    assert "/" not in relative_directory and "\\" not in relative_directory

    restored_root = paths.default_workspace_dir.parent / relative_directory
    restored_workspace = WorkspaceService(paths).open(restored_root)
    assert restored_workspace.security_contract_path.read_bytes() == before_contract
    with sqlite3.connect(restored_workspace.history_database_path) as connection:
        assert connection.execute("SELECT value FROM audit_marker").fetchone() == (
            "api-scan-001",
        )
    assert workspace.security_contract_path.read_bytes() == before_contract
    assert sorted(path.name for path in paths.default_workspace_dir.parent.iterdir()) == [
        "default",
        relative_directory,
    ]
    # The canonical Workspace root is home/workspaces; data/workspaces must
    # not become a second restore tree.
    assert not (paths.data_dir / "workspaces").exists()
    assert current_after_restore.status_code == 200
    assert current_after_restore.json()["relativeDirectory"] == "default"
    assert current_after_restore.json()["active"] is True


def test_restored_workspace_can_be_opened_by_a_rebuilt_app_with_same_contract_and_history(
    tmp_path: Path,
) -> None:
    paths, workspace = _workspace(tmp_path)
    _seed_history(workspace)
    first_client, _ = _client(paths, workspace)
    with first_client:
        backup = _backup(first_client)
        restored_payload = first_client.post(
            "/api/workspace/restores",
            content=backup,
            headers={"Content-Type": "application/zip"},
        ).json()

    restored_root = paths.default_workspace_dir.parent / restored_payload["workspace"]["relativeDirectory"]
    rebuilt_client, provider = _client(paths, WorkspaceService(paths).open(restored_root))
    with rebuilt_client:
        current = rebuilt_client.get("/api/workspace")
        catalog = rebuilt_client.get("/api/workspace/documents")

    assert current.status_code == 200
    assert current.json()["id"] == workspace.manifest.id
    assert current.json()["historyIncluded"] is True
    assert catalog.status_code == 200
    assert len(catalog.json()["documents"]) == current.json()["documentCount"]
    assert provider.calls == []


def _archive_with_entries(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_invalid_zip_path_and_content_type_are_422_and_leave_no_restore_directory(
    tmp_path: Path,
) -> None:
    paths, workspace = _workspace(tmp_path)
    client, provider = _client(paths, workspace)
    with client:
        assert client.post(
            "/api/workspace/backups/previews",
            content=b"not zip",
            headers={"Content-Type": "application/octet-stream"},
        ).status_code == 422
        invalid_path_zip = _archive_with_entries(
            {"metadata.json": b"{}", "workspace/../outside.txt": b"escape"}
        )
        response = client.post(
            "/api/workspace/backups/previews",
            content=invalid_path_zip,
            headers={"Content-Type": "application/zip"},
        )
        restore_response = client.post(
            "/api/workspace/restores",
            content=b"not zip",
            headers={"Content-Type": "application/zip"},
        )

    assert response.status_code == 422
    assert restore_response.status_code == 422
    assert response.json()["detail"]
    assert sorted(path.name for path in paths.default_workspace_dir.parent.iterdir()) == ["default"]
    assert provider.calls == []


@pytest.mark.parametrize("path", [
    "/api/workspace",
    "/api/workspace/backups/current",
])
def test_workspace_operations_without_active_workspace_are_409(
    tmp_path: Path,
    path: str,
) -> None:
    paths = resolve_app_paths(tmp_path / "app-home")
    client, provider = _client(paths)
    with client:
        response = client.get(path)
    assert response.status_code == 409
    assert provider.calls == []


def test_preview_and_restore_without_active_workspace_are_409(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path / "app-home")
    client, provider = _client(paths)
    with client:
        preview = client.post(
            "/api/workspace/backups/previews",
            content=b"not zip",
            headers={"Content-Type": "application/zip"},
        )
        restore = client.post(
            "/api/workspace/restores",
            content=b"not zip",
            headers={"Content-Type": "application/zip"},
        )
    assert preview.status_code == 409
    assert restore.status_code == 409
    assert provider.calls == []


def test_storage_error_is_reported_without_in_memory_or_filesystem_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    paths, workspace = _workspace(tmp_path)
    client, provider = _client(paths, workspace)

    def fail_backup(_service: Any) -> bytes:
        raise WorkspaceArchiveStorageError("synthetic backup storage failure")

    monkeypatch.setattr(main_module.WorkspaceArchiveService, "backup", fail_backup)
    with client:
        response = client.get("/api/workspace/backups/current")
        history = client.get("/api/scans")

    assert response.status_code == 500
    assert response.json()["detail"] == "synthetic backup storage failure"
    assert history.status_code == 200
    assert history.json() == []
    assert provider.calls == []
