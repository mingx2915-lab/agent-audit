"""Regression coverage for complete Acceptance Runs in a packaged layout."""

from pathlib import Path

from fastapi.testclient import TestClient

from agent_audit_api import benchmark_runtime
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.main import create_app
from agent_audit_api.retrieval import EmbeddingRetriever, TfidfRetriever
from agent_audit_api.workspace import WorkspaceService
from tests.acceptance_support import AcceptanceProvider, DeterministicAcceptanceEmbedder


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def test_complete_acceptance_uses_workspace_demo_data_without_repo_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    workspace = WorkspaceService().create(
        tmp_path / "workspace",
        "Packaged Acceptance regression",
        seed_dir=DEMO_SEED,
    )
    data = load_demo_data(workspace.documents_path)
    application = create_app(
        provider=AcceptanceProvider(),
        workspace=workspace,
        retriever=EmbeddingRetriever(
            data.documents,
            embedder=DeterministicAcceptanceEmbedder(),
        ),
    )

    def fail_repository_fallback(*args, **kwargs):
        raise AssertionError("packaged Acceptance must use Workspace demo data")

    monkeypatch.setattr(benchmark_runtime, "load_demo_data", fail_repository_fallback)

    with TestClient(application) as client:
        response = client.post("/api/acceptance-runs", json={})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
