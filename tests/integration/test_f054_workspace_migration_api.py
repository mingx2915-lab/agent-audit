from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.main import create_app
from agent_audit_api.workspace import WorkspaceService
from tests.retriever_support import make_tfidf_retriever


ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = ROOT / "data" / "demo"


def _legacy_child(tmp_path: Path, name: str = "restored-legacy"):
    paths = resolve_app_paths(tmp_path / "app")
    root = paths.default_workspace_dir.parent / name
    workspace = WorkspaceService(paths).create(root, "Legacy", seed_dir=DEMO_SEED)
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    payload.pop("schemaVersion")
    workspace.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with sqlite3.connect(workspace.history_database_path) as connection:
        connection.execute("CREATE TABLE marker(value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('preserved')")
        connection.execute("PRAGMA user_version = 0")
    return paths, workspace


def test_activation_preparation_migrates_selected_child_without_writing_active_pointer(
    tmp_path: Path,
) -> None:
    paths, legacy = _legacy_child(tmp_path)
    pointer = paths.config_dir / "active-workspace.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text('{"relativeDirectory":"default"}', encoding="utf-8")
    before_pointer = pointer.read_bytes()
    client = TestClient(
        create_app(app_paths=paths, retriever=make_tfidf_retriever())
    )

    with client:
        response = client.post(
            "/api/workspace/activation-preparations",
            json={"relativeDirectory": legacy.root.name},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "prepared": True,
        "relativeDirectory": legacy.root.name,
        "workspaceSchemaVersion": 2,
        "sqliteSchemaVersion": 2,
    }
    assert pointer.read_bytes() == before_pointer
    with sqlite3.connect(legacy.history_database_path) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone()[0] == "preserved"


def test_activation_preparation_failure_does_not_change_active_pointer(tmp_path: Path) -> None:
    paths, legacy = _legacy_child(tmp_path, "future")
    manifest = json.loads(legacy.manifest_path.read_text(encoding="utf-8"))
    manifest["schemaVersion"] = 99
    legacy.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    pointer = paths.config_dir / "active-workspace.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text('{"relativeDirectory":"default"}', encoding="utf-8")
    before = pointer.read_bytes()
    with TestClient(create_app(app_paths=paths, retriever=make_tfidf_retriever())) as client:
        response = client.post(
            "/api/workspace/activation-preparations",
            json={"relativeDirectory":"future"},
        )
    assert response.status_code == 422
    assert "newer" in response.json()["detail"]
    assert pointer.read_bytes() == before


def test_activation_preparation_rejects_non_child_paths(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    with TestClient(create_app(app_paths=paths, retriever=make_tfidf_retriever())) as client:
        for value in ("", ".", "..", "nested/child", r"nested\child", "C:drive"):
            response = client.post(
                "/api/workspace/activation-preparations",
                json={"relativeDirectory": value},
            )
            assert response.status_code == 422
