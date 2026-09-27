"""F-019 API integration tests for persisted Scan history and Replay."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.history import (
    AuditRunRepositoryError,
    SQLiteAuditRunRepository,
)
from agent_audit_api.main import create_app
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderResponseError,
    ProviderUnavailableError,
)
from tests.retriever_support import make_tfidf_retriever


@dataclass
class ScanVariantProvider:
    """Return strict message-only variants derived from the supplied baseline."""

    calls: list[tuple[Any, Any]] = field(default_factory=list)
    model: str = "test-history-variant-generator"
    api_key: str = "sk-test-api-key"
    authorization_header: str = "Authorization: Bearer test-secret"

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if not messages:
            raise AssertionError("variant generator received no messages")
        payload = json.loads(messages[-1]["content"])
        baseline = payload["baseline"]
        return LLMResponse(
            content=json.dumps(
                {
                    "message": f"{baseline['message']}（固定历史测试变体）",
                    "mutationReason": "根据上一轮真实 Trace 生成固定测试变体",
                },
                ensure_ascii=False,
            )
        )


@dataclass
class ScanTargetProvider:
    """Complete Target Agent calls without real models or Tool Calls."""

    calls: list[tuple[Any, Any]] = field(default_factory=list)
    failure: BaseException | None = None

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if self.failure is not None:
            raise self.failure
        return LLMResponse(content="固定历史 Target Agent 回答")


class FailingHistoryRepository:
    def __init__(self, operation: str) -> None:
        self.operation = operation
        self.calls: list[str] = []

    def _fail(self, operation: str):
        self.calls.append(operation)
        raise AuditRunRepositoryError(f"synthetic history {operation} failure")

    def save(self, detail):
        self._fail("save")

    def list(self, limit: int = 20):
        self._fail("list")

    def get(self, scan_id: str):
        self._fail("get")

    def append_replay(self, scan_id: str, persisted_replay):
        self._fail("append_replay")


class FailingAppendRepository:
    """Delegate scan storage, but fail only when the replay append is attempted."""

    def __init__(self, path: Path) -> None:
        self._delegate = SQLiteAuditRunRepository(path)
        self.calls: list[str] = []

    def save(self, detail) -> None:
        self.calls.append("save")
        self._delegate.save(detail)

    def list(self, limit: int = 20):
        self.calls.append("list")
        return self._delegate.list(limit)

    def get(self, scan_id: str):
        self.calls.append("get")
        return self._delegate.get(scan_id)

    def append_replay(self, scan_id: str, persisted_replay) -> None:
        self.calls.append("append_replay")
        raise AuditRunRepositoryError("synthetic history append_replay failure")


def _client(
    path: Path,
    *,
    target_provider: ScanTargetProvider | None = None,
    variant_provider: ScanVariantProvider | None = None,
    history_repository=None,
) -> TestClient:
    return TestClient(
        create_app(
            provider=target_provider or ScanTargetProvider(),
            attack_provider=variant_provider or ScanVariantProvider(),
            retriever=make_tfidf_retriever(),
            history_repository=(
                history_repository
                if history_repository is not None
                else SQLiteAuditRunRepository(path)
            ),
        )
    )


def _resource_plan(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/attack-plans")
    assert response.status_code == 200
    return next(
        plan for plan in response.json() if plan["basisType"] == "resource_owner_scope"
    )


def _start_resource_scan(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = _resource_plan(client)
    response = client.post(
        "/api/scans",
        json={"planId": plan["id"], "maxRounds": 3},
    )
    assert response.status_code == 200, response.text
    return plan, response.json()


def test_runtime_metadata_reads_injected_provider_and_tfidf_without_model_calls(tmp_path) -> None:
    target_provider = ScanTargetProvider()
    variant_provider = ScanVariantProvider()

    with _client(
        tmp_path / "history.sqlite3",
        target_provider=target_provider,
        variant_provider=variant_provider,
    ) as client:
        response = client.get("/api/runtime")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "injected:ScanVariantProvider",
        "model": "test-history-variant-generator",
        "retrieverEngine": "tfidf",
        "retrieverModel": None,
        "retrieverDimensions": None,
        "indexedDocumentCount": 7,
    }
    assert target_provider.calls == []
    assert variant_provider.calls == []


def test_scan_success_persists_complete_attempt_trace_finding_and_snapshots(tmp_path) -> None:
    path = tmp_path / "runtime" / "history.sqlite3"
    target_provider = ScanTargetProvider()
    variant_provider = ScanVariantProvider()

    assert not path.exists()
    with _client(
        path,
        target_provider=target_provider,
        variant_provider=variant_provider,
    ) as client:
        assert not path.exists()
        plan, scan = _start_resource_scan(client)
        contract = client.get("/api/security-contract").json()
        detail_response = client.get(f"/api/scans/{scan['id']}")
        summaries_response = client.get("/api/scans")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert path.exists()
    assert detail["scan"] == scan
    assert detail["planSnapshot"] == plan
    assert detail["contractSnapshot"] == contract
    assert detail["targetProfileSnapshot"] == {
        "id": plan["targetProfileId"],
        "name": "Vulnerable Observe-only Target Agent",
        "enforceResourceAuthorization": False,
        "enforceToolAuthorization": True,
        "enforceSinkAuthorization": True,
    }
    assert detail["runtimeSnapshot"] == {
        "provider": "injected:ScanVariantProvider",
        "model": "test-history-variant-generator",
        "retrieverEngine": "tfidf",
        "retrieverModel": None,
        "retrieverDimensions": None,
        "indexedDocumentCount": 7,
    }
    assert detail["replays"] == []

    assert len(scan["attempts"]) == 1
    attempt = scan["attempts"][0]
    assert attempt["scanId"] == scan["id"]
    assert attempt["variant"]["actorId"] == plan["actorId"]
    assert attempt["variant"]["targetId"] == plan["targetId"]
    assert attempt["queryResult"]["traceEvents"]
    assert all(
        set(event) == {"sequence", "type", "summary", "details", "occurredAt"}
        for event in attempt["queryResult"]["traceEvents"]
    )
    assert attempt["evaluation"]["status"] == "failed"
    assert attempt["evaluation"]["findings"]
    assert any(
        finding["category"] == "resource_authorization_bypass"
        for finding in attempt["evaluation"]["findings"]
    )
    summary = next(
        summary for summary in summaries_response.json() if summary["scanId"] == scan["id"]
    )
    assert summary["attemptCount"] == 1
    assert summary["findingCount"] == len(attempt["evaluation"]["findings"])
    assert summary["replayCount"] == 0
    assert len(variant_provider.calls) == 1
    assert len(target_provider.calls) == 1

    database_bytes = path.read_bytes()
    assert b"sk-test-api-key" not in database_bytes
    assert b"Authorization: Bearer test-secret" not in database_bytes


def test_failed_scan_is_not_saved_and_does_not_leave_history(tmp_path) -> None:
    path = tmp_path / "history.sqlite3"
    target_provider = ScanTargetProvider(
        failure=ProviderUnavailableError("synthetic target provider failure")
    )
    with _client(path, target_provider=target_provider) as client:
        plan = _resource_plan(client)
        failed = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 3},
        )
        history = client.get("/api/scans")

    assert failed.status_code == 502
    detail = failed.json()["detail"]
    assert any(term in detail for term in ("无法识别", "未形成有效结论", "未完成"))
    assert "重新" in detail
    assert "synthetic target provider failure" not in detail
    assert history.status_code == 200
    assert history.json() == []


def test_history_list_detail_404_and_limit_validation(tmp_path) -> None:
    path = tmp_path / "history.sqlite3"
    with _client(path) as client:
        for _ in range(2):
            _start_resource_scan(client)
        assert client.get("/api/scans?limit=1").status_code == 200
        assert len(client.get("/api/scans?limit=1").json()) == 1
        assert client.get("/api/scans?limit=0").status_code == 422
        assert client.get("/api/scans?limit=101").status_code == 422
        assert client.get("/api/scans?limit=not-an-int").status_code == 422
        assert client.get("/api/scans/scan_missing").status_code == 404
        assert client.get("/api/scans/scan_missing").json()["detail"] == "unknown scan"


def test_history_survives_rebuilt_app_and_active_contract_update(tmp_path) -> None:
    path = tmp_path / "history.sqlite3"
    first_target = ScanTargetProvider()
    first_variant = ScanVariantProvider()
    with _client(
        path,
        target_provider=first_target,
        variant_provider=first_variant,
    ) as client:
        plan, scan = _start_resource_scan(client)
        original_contract = client.get("/api/security-contract").json()
        changed_contract = json.loads(json.dumps(original_contract, ensure_ascii=False))
        changed_contract["name"] = "当前 active Contract 已更新"
        changed_contract["version"] = original_contract["version"] + 1
        updated = client.put("/api/security-contract", json=changed_contract)
        detail_after_update = client.get(f"/api/scans/{scan['id']}")

    assert updated.status_code == 200
    assert updated.json()["name"] == "当前 active Contract 已更新"
    assert detail_after_update.status_code == 200
    assert detail_after_update.json()["contractSnapshot"] == original_contract
    assert detail_after_update.json()["scan"] == scan
    assert detail_after_update.json()["scan"]["attempts"][0]["evaluation"] == scan[
        "attempts"
    ][0]["evaluation"]

    second_target = ScanTargetProvider()
    with _client(path, target_provider=second_target) as rebuilt_client:
        history = rebuilt_client.get("/api/scans")
        restored = rebuilt_client.get(f"/api/scans/{scan['id']}")

    assert history.status_code == 200
    assert [item["scanId"] for item in history.json()] == [scan["id"]]
    assert restored.status_code == 200
    assert restored.json() == detail_after_update.json()
    assert second_target.calls == []


def test_persisted_replay_uses_saved_plan_contract_and_appends_across_restart(tmp_path) -> None:
    path = tmp_path / "history.sqlite3"
    target_provider = ScanTargetProvider()
    with _client(path, target_provider=target_provider) as client:
        plan, scan = _start_resource_scan(client)
        original_detail = client.get(f"/api/scans/{scan['id']}").json()
        changed_contract = json.loads(
            json.dumps(client.get("/api/security-contract").json(), ensure_ascii=False)
        )
        changed_contract["name"] = "active-only contract"
        changed_contract["version"] += 1
        saved_resource_rule = next(
            rule
            for rule in changed_contract["resourceRules"]
            if rule["id"] == plan["basisRuleId"]
        )
        saved_resource_rule["requireOwnerMatch"] = False
        assert client.put("/api/security-contract", json=changed_contract).status_code == 200
        active_plans = client.get("/api/attack-plans")
        assert active_plans.status_code == 200
        assert plan["id"] not in {item["id"] for item in active_plans.json()}

        invalid_body = client.post(
            f"/api/scans/{scan['id']}/replays",
            json={"unexpected": True},
        )
        assert invalid_body.status_code == 422
        assert len(target_provider.calls) == 1

        first = client.post(f"/api/scans/{scan['id']}/replays", json={})
        second = client.post(f"/api/scans/{scan['id']}/replays", json={})
        after_replays = client.get(f"/api/scans/{scan['id']}")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["id"] != second_payload["id"]
    assert first_payload["replay"]["id"] == second_payload["replay"]["id"]
    assert first_payload["replay"]["id"] == f"replay_{plan['id']}"
    assert first_payload["replay"]["plan"] == plan
    assert second_payload["replay"]["plan"] == plan
    assert first_payload["replay"]["status"] == "passed"
    assert second_payload["replay"]["status"] == "passed"
    for payload in (first_payload, second_payload):
        replay = payload["replay"]
        assert replay["before"]["evaluation"]["status"] == "failed"
        assert replay["before"]["evaluation"]["findings"]
        assert replay["before"]["traceEvents"]
        assert replay["after"]["evaluation"]["status"] == "passed"
        assert replay["after"]["evaluation"]["findings"] == []
        assert replay["after"]["traceEvents"]
    assert after_replays.status_code == 200
    replay_history = after_replays.json()["replays"]
    assert [item["id"] for item in replay_history] == [
        first_payload["id"],
        second_payload["id"],
    ]
    assert original_detail["planSnapshot"] == first_payload["replay"]["plan"]
    assert after_replays.json()["contractSnapshot"] == original_detail["contractSnapshot"]
    assert len(target_provider.calls) == 5

    with _client(path, target_provider=ScanTargetProvider()) as rebuilt_client:
        restored = rebuilt_client.get(f"/api/scans/{scan['id']}")
    assert restored.status_code == 200
    assert [item["id"] for item in restored.json()["replays"]] == [
        first_payload["id"],
        second_payload["id"],
    ]


@pytest.mark.parametrize(
    ("method", "path", "expected_detail"),
    [
        ("get", "/api/scans", "unable to list audit history"),
        ("get", "/api/scans/scan_1", "unable to read audit history"),
    ],
)
def test_repository_read_failures_map_to_explicit_http_errors(
    tmp_path,
    method: str,
    path: str,
    expected_detail: str,
) -> None:
    repository = FailingHistoryRepository("read")
    with _client(
        tmp_path / "history.sqlite3",
        history_repository=repository,
    ) as client:
        response = getattr(client, method)(path)

    assert response.status_code == 500
    assert response.json()["detail"] == expected_detail
    assert repository.calls


def test_repository_save_failure_has_no_in_memory_fallback(tmp_path) -> None:
    repository = FailingHistoryRepository("save")
    target_provider = ScanTargetProvider()
    variant_provider = ScanVariantProvider()
    with _client(
        tmp_path / "history.sqlite3",
        target_provider=target_provider,
        variant_provider=variant_provider,
        history_repository=repository,
    ) as client:
        plan = _resource_plan(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 3},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "unable to persist audit scan"
    assert repository.calls == ["save"]
    assert len(target_provider.calls) == 1
    assert len(variant_provider.calls) == 1


def test_repository_append_failure_has_no_in_memory_replay_fallback(tmp_path) -> None:
    repository = FailingAppendRepository(tmp_path / "history.sqlite3")
    target_provider = ScanTargetProvider()
    with _client(
        tmp_path / "history.sqlite3",
        target_provider=target_provider,
        history_repository=repository,
    ) as client:
        _, scan = _start_resource_scan(client)
        response = client.post(f"/api/scans/{scan['id']}/replays", json={})

    assert response.status_code == 500
    assert response.json()["detail"] == "unable to append audit replay"
    assert repository.calls[-2:] == ["get", "append_replay"]
    assert len(target_provider.calls) == 3
