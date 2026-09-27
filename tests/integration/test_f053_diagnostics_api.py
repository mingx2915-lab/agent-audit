from __future__ import annotations

import io
import json
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.main import create_app
from tests.retriever_support import make_tfidf_retriever


HEADER = "X-AgentAudit-Operation-Id"


def _client(tmp_path: Path) -> TestClient:
    paths = resolve_app_paths(tmp_path / "app")
    return TestClient(
        create_app(
            app_paths=paths,
            retriever=make_tfidf_retriever(),
        )
    )


def test_preview_is_read_only_get_and_export_is_explicit_post(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        preview = client.get("/api/diagnostics/preview")
        assert preview.status_code == 200
        assert re.fullmatch(r"[0-9a-f]{32}", preview.headers[HEADER])
        body = preview.json()
        assert body["localOnly"] is True
        assert body["suggestedFilename"].endswith(".zip")
        assert "凭据与环境变量中的 Secret" in body["excluded"]
        assert "本地" in body["disclaimer"]
        assert "不会上传" in body["disclaimer"]
        assert "仅供" in body["disclaimer"] and "排障" in body["disclaimer"]
        assert "不构成根因" in body["disclaimer"]
        assert client.get("/api/diagnostics/export").status_code == 405

        exported = client.post("/api/diagnostics/export")
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "application/zip"
        assert exported.headers[HEADER] != preview.headers[HEADER]
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        assert manifest["operationId"] == exported.headers[HEADER]


def test_client_cannot_choose_operation_id_and_concurrent_requests_are_isolated(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        forged = "f" * 32

        def call(index: int) -> tuple[str, str]:
            response = client.get(
                "/api/diagnostics/preview",
                headers={HEADER: forged, "X-Request-Id": f"client-{index}"},
            )
            assert response.status_code == 200
            return response.headers[HEADER], response.json()["suggestedFilename"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(call, range(16)))
    operation_ids = [item[0] for item in results]
    assert len(set(operation_ids)) == 16
    assert forged not in operation_ids
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in operation_ids)


def test_export_rejection_is_422_without_leaking_runtime_secret(tmp_path: Path) -> None:
    secret = "Authorization: Bearer never-return-this-secret"
    with _client(tmp_path) as client:
        client.app.state.diagnostics.runtime_supplier = lambda: {"unsafe": secret}
        response = client.post("/api/diagnostics/export")
    assert response.status_code == 422
    assert secret not in response.text
    assert "credential" in response.json()["detail"]
    assert re.fullmatch(r"[0-9a-f]{32}", response.headers[HEADER])
