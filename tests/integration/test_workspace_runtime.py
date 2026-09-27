"""F-026 integration coverage for Workspace-backed production assembly."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from agent_audit_api.attack_cases import load_attack_cases, load_target_profiles
from agent_audit_api.benchmark import load_ground_truth_cases
from agent_audit_api.demo_data import load_demo_data
import agent_audit_api.main as main_module
from agent_audit_api.main import create_app
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.workspace import WorkspaceService
from tests.benchmark_support import GroundTruthProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def _workspace(tmp_path: Path):
    return WorkspaceService().create(
        tmp_path / "workspace",
        "Workspace assembly test",
        seed_dir=DEMO_SEED,
    )


def _rewrite_json(path: Path, update) -> Any:
    payload = json.loads(path.read_text(encoding="utf-8"))
    update(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def test_each_loader_reads_the_explicit_workspace_directory(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _rewrite_json(
        workspace.actors_path,
        lambda records: records[0].update({"displayName": "Workspace actor"}),
    )
    _rewrite_json(
        workspace.documents_file_path,
        lambda records: records[0].update({"title": "Workspace document"}),
    )
    _rewrite_json(
        workspace.customers_path,
        lambda records: records[0].update({"name": "Workspace customer"}),
    )
    _rewrite_json(
        workspace.security_contract_path,
        lambda contract: contract.update({"name": "Workspace Contract"}),
    )
    _rewrite_json(
        workspace.attack_cases_path,
        lambda records: records[0].update({"name": "Workspace attack case"}),
    )
    _rewrite_json(
        workspace.target_profiles_path,
        lambda records: records[0].update({"name": "Workspace profile"}),
    )
    _rewrite_json(
        workspace.ground_truth_cases_path,
        lambda records: records[0].update({"name": "Workspace Ground Truth"}),
    )

    data = load_demo_data(workspace.documents_path)
    contract = load_security_contract(workspace.contract_path)
    attack_cases = load_attack_cases(workspace.cases_path)
    profiles = load_target_profiles(workspace.cases_path)
    ground_truth = load_ground_truth_cases(workspace.cases_path)

    assert data.actors[0].display_name == "Workspace actor"
    assert data.documents[0].title == "Workspace document"
    assert data.customers[0].name == "Workspace customer"
    assert contract.name == "Workspace Contract"
    assert attack_cases[0].name == "Workspace attack case"
    assert profiles[0].name == "Workspace profile"
    assert ground_truth[0].name == "Workspace Ground Truth"


def test_create_app_uses_one_workspace_for_all_catalogs_and_history(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _rewrite_json(
        workspace.actors_path,
        lambda records: records[0].update({"displayName": "Workspace actor"}),
    )
    _rewrite_json(
        workspace.documents_file_path,
        lambda records: records[0].update({"title": "Workspace document"}),
    )
    _rewrite_json(
        workspace.customers_path,
        lambda records: records[0].update({"name": "Workspace customer"}),
    )
    _rewrite_json(
        workspace.security_contract_path,
        lambda contract: contract.update({"name": "Workspace Contract"}),
    )
    _rewrite_json(
        workspace.attack_cases_path,
        lambda records: records[0].update({"name": "Workspace attack case"}),
    )
    _rewrite_json(
        workspace.target_profiles_path,
        lambda records: records[0].update({"name": "Workspace profile"}),
    )
    _rewrite_json(
        workspace.ground_truth_cases_path,
        lambda records: records[0].update({"name": "Workspace Ground Truth"}),
    )

    data = load_demo_data(workspace.documents_path)
    application = create_app(
        provider=GroundTruthProvider(),
        workspace=workspace,
        retriever=TfidfRetriever(data.documents),
    )

    assert application.state.workspace is workspace
    assert application.state.demo_data.actors[0].display_name == "Workspace actor"
    assert application.state.demo_data.documents[0].title == "Workspace document"
    assert application.state.demo_data.customers[0].name == "Workspace customer"
    assert application.state.security_contract.name == "Workspace Contract"
    assert application.state.attack_cases[0].name == "Workspace attack case"
    assert application.state.target_profiles[0].name == "Workspace profile"
    assert application.state.ground_truth_cases[0].name == "Workspace Ground Truth"
    assert application.state.history_repository.path == workspace.history_db_path
    assert application.state.acceptance_repository.path == workspace.history_db_path

    with TestClient(application) as client:
        assert client.get("/api/demo/actors").json()[0]["displayName"] == "Workspace actor"
        assert client.get("/api/security-contract").json()["name"] == "Workspace Contract"
        assert client.get("/api/attack-cases").json()[0]["name"] == "Workspace attack case"
        assert client.get("/api/ground-truth-cases").json()[0]["name"] == (
            "Workspace Ground Truth"
        )


def test_create_app_rejects_mixing_workspace_and_data_root(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)

    try:
        create_app(
            provider=GroundTruthProvider(),
            workspace=workspace,
            data_dir=workspace.documents_path,
            retriever=TfidfRetriever(load_demo_data(workspace.documents_path).documents),
        )
    except ValueError as exc:
        assert str(exc) == "workspace and data_dir cannot both be supplied"
    else:
        raise AssertionError("create_app accepted two competing data roots")


def test_default_history_uses_explicit_app_data_root_not_repository_layout(
    monkeypatch, tmp_path: Path
) -> None:
    app_home = tmp_path / "app-home"
    monkeypatch.setenv("AGENT_AUDIT_HOME", str(app_home))
    monkeypatch.delenv("AGENT_AUDIT_DB_PATH", raising=False)
    data = load_demo_data()

    application = create_app(
        provider=GroundTruthProvider(),
        retriever=TfidfRetriever(data.documents),
    )

    expected = app_home / "data" / "agent_audit.sqlite3"
    assert application.state.app_paths.data_dir == app_home / "data"
    assert application.state.history_repository.path == expected
    assert application.state.acceptance_repository.path == expected
    assert str(REPOSITORY_ROOT) not in str(expected)


def test_health_endpoint_is_a_model_free_loopback_readiness_signal(tmp_path: Path) -> None:
    provider = GroundTruthProvider()
    data = load_demo_data()
    application = create_app(
        provider=provider,
        retriever=TfidfRetriever(data.documents),
    )

    with TestClient(application) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "host": "127.0.0.1",
        "port": None,
        "detail": None,
    }
    assert provider.calls == []


def test_create_app_accepts_workspace_root_path_and_explicit_history_override(
    tmp_path: Path,
) -> None:
    workspace = _workspace(tmp_path)
    data = load_demo_data(workspace.documents_path)
    history_override = tmp_path / "separate-history.sqlite3"

    application = create_app(
        provider=GroundTruthProvider(),
        workspace=workspace.root,
        history_path=history_override,
        retriever=TfidfRetriever(data.documents),
    )

    assert application.state.workspace.root == workspace.root
    assert application.state.history_repository.path == history_override
    assert application.state.acceptance_repository.path == history_override


def test_benchmark_route_passes_the_same_workspace_to_runtime_assembly(
    monkeypatch, tmp_path: Path
) -> None:
    workspace = _workspace(tmp_path)
    data = load_demo_data(workspace.documents_path)
    captured: dict[str, object] = {}
    original_builder = main_module.build_benchmark_runtime

    def capture_builder(provider, **kwargs):
        captured.update(kwargs)
        return original_builder(provider, **kwargs)

    monkeypatch.setattr(main_module, "build_benchmark_runtime", capture_builder)
    application = create_app(
        provider=GroundTruthProvider(),
        workspace=workspace,
        retriever=TfidfRetriever(data.documents),
    )

    with TestClient(application) as client:
        response = client.post("/api/benchmarks/run")

    assert response.status_code == 200, response.text
    assert captured.get("workspace") is workspace
    assert captured["contract"] is application.state.security_contract
    assert captured["retriever"] is application.state.retriever
    assert captured["cases"] is application.state.ground_truth_cases
    assert captured["profiles"] is application.state.target_profiles
