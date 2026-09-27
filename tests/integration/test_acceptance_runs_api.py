"""F-025 API integration coverage for fixed Acceptance Runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.acceptance import AcceptanceRun
from agent_audit_api.acceptance_history import (
    AcceptanceRunRepositoryError,
    SQLiteAcceptanceRunRepository,
)
from agent_audit_api.main import create_app
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderConfigurationError,
    ProviderUnavailableError,
)
from agent_audit_api.retrieval import RetrieverError, RetrieverMetadata
from agent_audit_api.history import SQLiteAuditRunRepository
from tests.acceptance_support import AcceptanceProvider, make_acceptance_embedding_retriever


def _client(
    path: Path,
    *,
    provider: Any | None = None,
    attack_provider: Any | None = None,
    contract=None,
    acceptance_repository=None,
    history_repository=None,
    retriever=None,
) -> TestClient:
    active_provider = provider or AcceptanceProvider()
    return TestClient(
        create_app(
            provider=active_provider,
            attack_provider=attack_provider or active_provider,
            retriever=retriever or make_acceptance_embedding_retriever(),
            contract=contract,
            history_repository=(
                history_repository
                if history_repository is not None
                else SQLiteAuditRunRepository(path)
            ),
            acceptance_repository=(
                acceptance_repository
                if acceptance_repository is not None
                else SQLiteAcceptanceRunRepository(path)
            ),
        )
    )


def _post_run(client: TestClient, body: Any = ...) -> dict[str, Any]:
    response = client.post("/api/acceptance-runs") if body is ... else client.post(
        "/api/acceptance-runs", json=body
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["verdict"] == payload["ciGate"]["status"]
    return payload


def test_post_acceptance_run_accepts_no_body_and_empty_object(tmp_path: Path) -> None:
    provider = AcceptanceProvider()
    with _client(tmp_path / "history.sqlite3", provider=provider) as client:
        without_body = _post_run(client)
        empty_object = _post_run(client, {})
        history = client.get("/api/acceptance-runs")

    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [
        empty_object["id"],
        without_body["id"],
    ]
    assert without_body["id"] != empty_object["id"]
    assert len(provider.calls) > 0


def test_post_acceptance_run_rejects_extra_body_without_provider_or_history_side_effect(
    tmp_path: Path,
) -> None:
    provider = AcceptanceProvider()
    with _client(tmp_path / "history.sqlite3", provider=provider) as client:
        response = client.post("/api/acceptance-runs", json={"unexpected": True})
        history = client.get("/api/acceptance-runs")

    assert response.status_code == 422
    assert history.status_code == 200
    assert history.json() == []
    assert provider.calls == []


def test_acceptance_list_detail_comparison_and_exports_are_complete_and_read_only(
    tmp_path: Path,
) -> None:
    provider = AcceptanceProvider()
    with _client(tmp_path / "history.sqlite3", provider=provider) as client:
        run = _post_run(client)
        run_id = run["id"]
        calls_after_post = len(provider.calls)

        summaries = client.get("/api/acceptance-runs?limit=1")
        detail = client.get(f"/api/acceptance-runs/{run_id}")
        comparison = client.get(f"/api/acceptance-runs/{run_id}/comparison")
        json_export = client.get(f"/api/acceptance-runs/{run_id}/evidence.json")
        markdown_export = client.get(f"/api/acceptance-runs/{run_id}/evidence.md")

        assert len(provider.calls) == calls_after_post

    assert summaries.status_code == 200
    assert len(summaries.json()) == 1
    assert summaries.json()[0]["id"] == run_id
    assert summaries.json()[0]["benchmarkCaseCount"] == 24
    assert summaries.json()[0]["guidedReplayStatus"] == "passed"

    assert detail.status_code == 200
    assert detail.json() == run
    validated = AcceptanceRun.model_validate(json_export.json())
    assert validated.model_dump(mode="json", by_alias=True) == run
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    assert json_export.headers["content-disposition"] == (
        f'attachment; filename="acceptance-run-{run_id}.json"'
    )

    assert markdown_export.status_code == 200
    assert markdown_export.headers["content-type"].startswith("text/markdown")
    assert markdown_export.headers["content-disposition"] == (
        f'attachment; filename="acceptance-run-{run_id}.md"'
    )
    assert run_id in markdown_export.text
    assert "SYNTHETIC / DEMO ONLY" in markdown_export.text
    assert "## Provider Readiness" in markdown_export.text
    assert "## CI Gate" in markdown_export.text
    assert "## Benchmark Cases" in markdown_export.text
    assert "## Guided Replay" in markdown_export.text

    assert comparison.status_code == 200
    assert comparison.json()["current"]["id"] == run_id
    assert comparison.json()["previous"] is None
    assert comparison.json()["gateMetricDeltas"] == []
    assert comparison.json()["addedFailedCheckIds"] == []
    assert comparison.json()["resolvedFindingCategories"] == []


def test_comparison_route_uses_the_complete_previous_run_snapshot(tmp_path: Path) -> None:
    provider = AcceptanceProvider()
    with _client(tmp_path / "history.sqlite3", provider=provider) as client:
        first = _post_run(client)
        second = _post_run(client)
        comparison = client.get(f"/api/acceptance-runs/{second['id']}/comparison")

    assert comparison.status_code == 200
    payload = comparison.json()
    assert payload["current"]["id"] == second["id"]
    assert payload["previous"]["id"] == first["id"]
    assert payload["previous"]["contractId"] == first["contractSnapshot"]["id"]
    assert payload["previous"]["benchmarkCaseCount"] == 24
    assert payload["previous"]["guidedReplayStatus"] == "passed"
    assert len(payload["gateMetricDeltas"]) == 5
    assert payload["addedFailedCheckIds"] == []
    assert payload["resolvedFailedCheckIds"] == []
    assert payload["addedMismatchedCaseIds"] == []
    assert payload["resolvedMismatchedCaseIds"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/acceptance-runs/acceptance_missing",
        "/api/acceptance-runs/acceptance_missing/comparison",
        "/api/acceptance-runs/acceptance_missing/evidence.json",
        "/api/acceptance-runs/acceptance_missing/evidence.md",
    ],
)
def test_unknown_acceptance_run_routes_return_404(tmp_path: Path, path: str) -> None:
    with _client(tmp_path / "history.sqlite3") as client:
        response = client.get(path)

    assert response.status_code == 404
    assert response.json()["detail"] == "unknown acceptance run"


@pytest.mark.parametrize("limit", [0, 101, "not-an-int"])
def test_acceptance_history_limit_is_bounded(tmp_path: Path, limit: Any) -> None:
    with _client(tmp_path / "history.sqlite3") as client:
        response = client.get("/api/acceptance-runs", params={"limit": limit})

    assert response.status_code == 422


def test_acceptance_snapshot_survives_active_contract_update_and_app_rebuild(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    first_provider = AcceptanceProvider()
    with _client(path, provider=first_provider) as client:
        run = _post_run(client)
        original_contract = client.get("/api/security-contract").json()
        changed_contract = json.loads(json.dumps(original_contract, ensure_ascii=False))
        changed_contract["name"] = "仅 active Contract 更新"
        changed_contract["version"] = original_contract["version"] + 1
        assert client.put("/api/security-contract", json=changed_contract).status_code == 200
        after_update = client.get(f"/api/acceptance-runs/{run['id']}")

    second_provider = AcceptanceProvider()
    with _client(path, provider=second_provider) as rebuilt:
        restored = rebuilt.get(f"/api/acceptance-runs/{run['id']}")
        restored_list = rebuilt.get("/api/acceptance-runs")

    assert after_update.status_code == 200
    assert after_update.json() == run
    assert restored.status_code == 200
    assert restored.json() == run
    assert restored_list.status_code == 200
    assert [item["id"] for item in restored_list.json()] == [run["id"]]
    assert second_provider.calls == []


def test_acceptance_and_scan_history_share_sqlite_without_overwriting_each_other(tmp_path: Path) -> None:
    path = tmp_path / "shared.sqlite3"
    provider = AcceptanceProvider()
    with _client(path, provider=provider) as client:
        plans = client.get("/api/attack-plans")
        assert plans.status_code == 200
        resource_plan = next(item for item in plans.json() if item["basisType"] == "resource_owner_scope")
        scan_response = client.post(
            "/api/scans",
            json={"planId": resource_plan["id"], "maxRounds": 3},
        )
        assert scan_response.status_code == 200, scan_response.text
        scan = scan_response.json()
        acceptance = _post_run(client)
        restored_scan = client.get(f"/api/scans/{scan['id']}")
        restored_acceptance = client.get(f"/api/acceptance-runs/{acceptance['id']}")

    assert restored_scan.status_code == 200
    assert restored_scan.json()["scan"] == scan
    assert restored_acceptance.status_code == 200
    assert restored_acceptance.json() == acceptance


def test_missing_required_source_sink_plan_returns_422_without_half_run(tmp_path: Path) -> None:
    from agent_audit_api.security_contract import load_security_contract

    contract = load_security_contract().model_copy(deep=True, update={"sink_rules": []})
    provider = AcceptanceProvider()
    with _client(tmp_path / "history.sqlite3", provider=provider, contract=contract) as client:
        response = client.post("/api/acceptance-runs", json={})
        history = client.get("/api/acceptance-runs")

    assert response.status_code == 422
    assert "plan_sink_confidential_external" in response.json()["detail"]
    assert history.status_code == 200
    assert history.json() == []
    assert provider.calls == []


class FailingAcceptanceRepository:
    def __init__(self, operation: str) -> None:
        self.operation = operation
        self.calls: list[str] = []

    def _fail(self, operation: str):
        self.calls.append(operation)
        raise AcceptanceRunRepositoryError(f"synthetic acceptance {operation} failure")

    def save(self, run):
        self._fail("save")

    def list(self, limit: int = 20):
        self._fail("list")

    def get(self, run_id: str):
        self._fail("get")

    def previous(self, run_id: str):
        self._fail("previous")


def test_repository_save_failure_maps_to_500_without_in_memory_fallback(tmp_path: Path) -> None:
    repository = FailingAcceptanceRepository("save")
    provider = AcceptanceProvider()
    with _client(
        tmp_path / "history.sqlite3",
        provider=provider,
        acceptance_repository=repository,
    ) as client:
        response = client.post("/api/acceptance-runs", json={})

    assert response.status_code == 500
    assert response.json()["detail"] == "unable to persist acceptance history"
    assert repository.calls == ["save"]
    assert provider.calls


@pytest.mark.parametrize(
    ("method", "path", "detail"),
    [
        ("get", "/api/acceptance-runs", "unable to list acceptance history"),
        ("get", "/api/acceptance-runs/acceptance_1", "unable to read acceptance history"),
        ("get", "/api/acceptance-runs/acceptance_1/evidence.json", "unable to read acceptance history"),
        ("get", "/api/acceptance-runs/acceptance_1/evidence.md", "unable to read acceptance history"),
        ("get", "/api/acceptance-runs/acceptance_1/comparison", "unable to compare acceptance history"),
    ],
)
def test_repository_read_failures_map_to_explicit_500(
    tmp_path: Path,
    method: str,
    path: str,
    detail: str,
) -> None:
    repository = FailingAcceptanceRepository("read")
    with _client(tmp_path / "history.sqlite3", acceptance_repository=repository) as client:
        response = getattr(client, method)(path)

    assert response.status_code == 500
    assert response.json()["detail"] == detail
    assert repository.calls


@dataclass
class FailingTargetProvider(AcceptanceProvider):
    failure: BaseException | None = None

    async def complete(self, messages, tools=None) -> LLMResponse:
        if self._contains(messages, "Connectivity probe") or self._contains(
            messages, "strict JSON readiness probe"
        ) or self._tool_names(tools) == {"agent_audit_readiness_probe"}:
            return await super().complete(messages, tools=tools)
        if self.failure is None:
            raise AssertionError("failure must be configured")
        raise self.failure


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (ProviderUnavailableError("synthetic acceptance provider unavailable"), 502),
        (ProviderConfigurationError("synthetic acceptance provider misconfigured"), 503),
    ],
)
def test_provider_failures_map_to_502_or_503_and_leave_no_history(
    tmp_path: Path,
    failure: BaseException,
    status: int,
) -> None:
    provider = FailingTargetProvider(failure=failure)
    attack_provider = AcceptanceProvider()
    with _client(
        tmp_path / "history.sqlite3",
        provider=provider,
        attack_provider=attack_provider,
    ) as client:
        response = client.post("/api/acceptance-runs", json={})
        history = client.get("/api/acceptance-runs")

    assert response.status_code == status
    detail = response.json()["detail"]
    assert any(term in detail for term in ("连接设置", "未完成", "未形成有效结论"))
    assert "重新" in detail
    assert str(failure) not in detail
    assert "synthetic" not in detail.lower()
    assert history.status_code == 200
    assert history.json() == []


class FailingRetriever:
    @property
    def metadata(self) -> RetrieverMetadata:
        return RetrieverMetadata(
            engine_id="embedding",
            model_name="test-failing-embedding",
            dimensions=512,
            indexed_document_count=7,
        )

    def search(self, query: str, limit: int = 3):
        raise RetrieverError("synthetic acceptance retriever failure")


def test_retriever_failure_maps_to_503_and_leaves_no_history(tmp_path: Path) -> None:
    provider = AcceptanceProvider()
    with _client(
        tmp_path / "history.sqlite3",
        provider=provider,
        retriever=FailingRetriever(),
    ) as client:
        response = client.post("/api/acceptance-runs", json={})
        history = client.get("/api/acceptance-runs")

    assert response.status_code == 503
    assert response.json()["detail"] == "synthetic acceptance retriever failure"
    assert history.status_code == 200
    assert history.json() == []
