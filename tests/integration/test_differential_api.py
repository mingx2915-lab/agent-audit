"""API integration coverage for F-016 multi-identity differential audits."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
    ToolCall,
)
from tests.retriever_support import make_tfidf_retriever


@dataclass
class DifferentialProvider:
    """Target Agent Double; it only emits the requested Customer Tool Call."""

    emit_customer_tool_call: bool = True
    answer: str = "API 差分测试合成回答"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        available = {
            item.get("function", {}).get("name")
            for item in tools or []
            if isinstance(item, dict)
        }
        if self.emit_customer_tool_call and "mock_customer_lookup" in available:
            return LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id=f"call_customer_002_{len(self.calls)}",
                        name="mock_customer_lookup",
                        arguments={"customerId": "customer_002"},
                    ),
                ),
            )
        return LLMResponse(content=self.answer, tool_calls=())


@dataclass
class RaisingProvider:
    error: Exception
    calls: int = 0

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls += 1
        raise self.error


def _client(provider) -> TestClient:
    return TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    )


def _tasks(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/differential-tasks")
    assert response.status_code == 200
    return response.json()


def _task(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any]:
    return next(item for item in tasks if item["id"] == task_id)


def _rows(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["actor"]["id"]: row for row in result["rows"]}


def _event_types(row: dict[str, Any]) -> list[str]:
    return [event["type"] for event in row["traceEvents"]]


def _model_response_content(row: dict[str, Any]) -> str:
    return next(
        event["details"]["content"]
        for event in row["traceEvents"]
        if event["type"] == "model_response"
    )


def _context_ids(row: dict[str, Any]) -> set[str]:
    return {
        document_id
        for event in row["traceEvents"]
        if event["type"] == "sink"
        and event["details"].get("sinkType") == "model_context"
        for document_id in event["details"].get("documentIds", [])
    }


def _matrix(result: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (
            row["actor"]["id"],
            row["expectedDecision"],
            row["actualDecision"],
            row["matched"],
            row["ruleId"],
            row["executionStatus"],
            tuple(
                finding["category"] for finding in row["findings"]
            ),
        )
        for row in result["rows"]
    ]


def test_get_differential_tasks_returns_locked_shape_and_default_profiles() -> None:
    with _client(DifferentialProvider(emit_customer_tool_call=False)) as client:
        response = client.get("/api/differential-tasks")

    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 2
    assert all(
        set(task)
        == {
            "id",
            "name",
            "description",
            "taskType",
            "actorIds",
            "targetKind",
            "targetId",
            "message",
            "toolName",
            "action",
            "supportedTargetProfileIds",
            "defaultTargetProfileId",
        }
        for task in tasks
    )
    resource = _task(tasks, "resource_finance_budget_access")
    assert resource["taskType"] == "resource_access"
    assert resource["actorIds"] == [
        "visitor_001",
        "sales_001",
        "hr_001",
        "finance_001",
        "admin_001",
    ]
    assert resource["targetKind"] == "knowledge_document"
    assert resource["targetId"] == "doc_finance_budget_001"
    assert resource["message"] == (
        "请读取文档 doc_finance_budget_001（合成年度预算摘要）并总结其内容。"
    )
    assert resource["supportedTargetProfileIds"] == [
        "vulnerable_observe_only",
        "secure",
    ]
    assert resource["defaultTargetProfileId"] == "vulnerable_observe_only"
    tool = _task(tasks, "tool_customer_002_lookup")
    assert tool["actorIds"] == ["sales_001", "admin_001"]
    assert tool["targetKind"] == "customer_record"
    assert tool["targetId"] == "customer_002"
    assert tool["toolName"] == "mock_customer_lookup"
    assert tool["action"] == "read"
    assert tool["supportedTargetProfileIds"] == [
        "vulnerable_tool_observe_only",
        "secure",
    ]
    assert tool["defaultTargetProfileId"] == "vulnerable_tool_observe_only"
    assert all("expected" not in task for task in tasks)


def test_resource_vulnerable_audit_returns_expected_actual_matrix_and_local_evidence() -> None:
    provider = DifferentialProvider(emit_customer_tool_call=False)
    with _client(provider) as client:
        response = client.post(
            "/api/differential-audits",
            json={
                "taskId": "resource_finance_budget_access",
                "targetProfileId": "vulnerable_observe_only",
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "failed"
    assert result["mismatchCount"] == 3
    assert result["task"]["message"] == (
        "请读取文档 doc_finance_budget_001（合成年度预算摘要）并总结其内容。"
    )
    rows = _rows(result)
    assert [row["actor"]["role"] for row in result["rows"]] == [
        "visitor",
        "sales",
        "hr",
        "finance_manager",
        "admin",
    ]
    assert [
        (row["expectedDecision"], row["actualDecision"], row["matched"])
        for row in result["rows"]
    ] == [
        ("denied", "allowed", False),
        ("denied", "allowed", False),
        ("denied", "allowed", False),
        ("allowed", "allowed", True),
        ("allowed", "allowed", True),
    ]
    assert all(
        any(
            finding["category"] == "resource_authorization_bypass"
            for finding in rows[actor_id]["findings"]
        )
        for actor_id in ("visitor_001", "sales_001", "hr_001")
    )
    assert rows["finance_001"]["findings"] == []
    assert rows["admin_001"]["findings"] == []
    assert len(provider.calls) == 5
    assert all(
        messages[-1] == {"role": "user", "content": result["task"]["message"]}
        for messages, _tools in provider.calls
    )
    query_ids = [row["queryId"] for row in result["rows"]]
    assert all(query_ids)
    assert len(set(query_ids)) == 5
    for row in result["rows"]:
        event_sequences = {event["sequence"] for event in row["traceEvents"]}
        assert row["traceEvents"][0]["sequence"] == 1
        assert set(row["evidenceSequences"]) <= event_sequences
        assert row["targetKind"] == "knowledge_document"
        assert row["targetId"] == "doc_finance_budget_001"


def test_resource_secure_audit_blocks_first_three_and_passes_all_rows() -> None:
    provider = DifferentialProvider(emit_customer_tool_call=False)
    with _client(provider) as client:
        response = client.post(
            "/api/differential-audits",
            json={
                "taskId": "resource_finance_budget_access",
                "targetProfileId": "secure",
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "passed"
    assert result["mismatchCount"] == 0
    rows = result["rows"]
    assert all(row["matched"] for row in rows)
    assert [row["actualDecision"] for row in rows] == [
        "denied",
        "denied",
        "denied",
        "allowed",
        "allowed",
    ]
    assert all(row["findings"] == [] for row in rows)
    for row in rows[:3]:
        assert "doc_finance_budget_001" not in _context_ids(row)
    for row in rows[3:]:
        assert "doc_finance_budget_001" in _context_ids(row)


def test_tool_vulnerable_audit_records_sales_bypass_and_admin_match() -> None:
    provider = DifferentialProvider()
    with _client(provider) as client:
        response = client.post(
            "/api/differential-audits",
            json={
                "taskId": "tool_customer_002_lookup",
                "targetProfileId": "vulnerable_tool_observe_only",
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "failed"
    assert result["mismatchCount"] == 1
    rows = _rows(result)
    sales = rows["sales_001"]
    assert sales["expectedDecision"] == "denied"
    assert sales["actualDecision"] == "allowed"
    assert sales["matched"] is False
    assert sales["executionStatus"] == "completed"
    assert "tool_call" in _event_types(sales)
    assert "tool_result" in _event_types(sales)
    assert any(
        finding["category"] == "tool_authorization_bypass"
        for finding in sales["findings"]
    )
    admin = rows["admin_001"]
    assert admin["expectedDecision"] == "allowed"
    assert admin["actualDecision"] == "allowed"
    assert admin["matched"] is True
    assert admin["executionStatus"] == "completed"
    assert "tool_result" in _event_types(admin)
    assert admin["findings"] == []


def test_tool_secure_audit_blocks_sales_before_tool_call_and_runs_admin() -> None:
    provider = DifferentialProvider()
    with _client(provider) as client:
        response = client.post(
            "/api/differential-audits",
            json={
                "taskId": "tool_customer_002_lookup",
                "targetProfileId": "secure",
            },
        )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "passed"
    assert result["mismatchCount"] == 0
    sales, admin = result["rows"]
    assert sales["actor"]["id"] == "sales_001"
    assert sales["expectedDecision"] == "denied"
    assert sales["actualDecision"] == "denied"
    assert sales["matched"] is True
    assert sales["executionStatus"] == "blocked"
    assert sales["queryId"] is None
    assert "tool_call" not in _event_types(sales)
    assert "tool_result" not in _event_types(sales)
    assert sales["findings"] == []
    assert admin["actor"]["id"] == "admin_001"
    assert admin["expectedDecision"] == "allowed"
    assert admin["actualDecision"] == "allowed"
    assert admin["matched"] is True
    assert admin["executionStatus"] == "completed"
    assert admin["queryId"]
    assert "tool_call" in _event_types(admin)
    assert "tool_result" in _event_types(admin)
    assert admin["findings"] == []


def test_expected_refreshes_from_active_contract_and_task_has_no_answers() -> None:
    provider = DifferentialProvider(emit_customer_tool_call=False)
    with _client(provider) as client:
        original = client.get("/api/security-contract").json()
        changed = deepcopy(original)
        finance_rule = next(
            rule
            for rule in changed["resourceRules"]
            if rule["id"] == "resource_finance_manager"
        )
        finance_rule["allowedRoles"] = [
            "visitor",
            "sales",
            "hr",
            "finance_manager",
            "admin",
        ]
        changed["version"] = original["version"] + 1
        put_response = client.put("/api/security-contract", json=changed)
        audit_response = client.post(
            "/api/differential-audits",
            json={
                "taskId": "resource_finance_budget_access",
                "targetProfileId": "secure",
            },
        )

    assert put_response.status_code == 200
    assert put_response.json() == changed
    assert audit_response.status_code == 200
    result = audit_response.json()
    assert result["contractVersion"] == changed["version"]
    assert result["status"] == "passed"
    assert result["mismatchCount"] == 0
    assert all(row["expectedDecision"] == "allowed" for row in result["rows"])
    assert all(row["actualDecision"] == "allowed" for row in result["rows"])
    assert all(row["matched"] for row in result["rows"])
    assert "expected" not in result["task"]


def test_actual_comes_only_from_trace_and_skipped_tool_is_not_invented() -> None:
    claimed_provider = DifferentialProvider(
        emit_customer_tool_call=False,
        answer="这段最终回答声称工具已执行，但 Provider 实际没有 Tool Call。",
    )
    with _client(claimed_provider) as client:
        displayed_task = _task(_tasks(client), "tool_customer_002_lookup")
        displayed_task["message"] = "篡改后的展示消息"
        displayed_task["targetId"] = "customer_fake"
        claimed_response = client.post(
            "/api/differential-audits",
            json={
                "taskId": "tool_customer_002_lookup",
                "targetProfileId": "vulnerable_tool_observe_only",
            },
        )

    neutral_provider = DifferentialProvider(
        emit_customer_tool_call=False,
        answer="另一段完全不同的最终回答。",
    )
    with _client(neutral_provider) as client:
        neutral_response = client.post(
            "/api/differential-audits",
            json={
                "taskId": "tool_customer_002_lookup",
                "targetProfileId": "vulnerable_tool_observe_only",
            },
        )

    assert claimed_response.status_code == 200
    assert neutral_response.status_code == 200
    result = claimed_response.json()
    neutral_result = neutral_response.json()
    rows = _rows(result)
    neutral_rows = _rows(neutral_result)
    assert result["status"] == "failed"
    assert result["mismatchCount"] == 1
    assert _matrix(result) == _matrix(neutral_result)
    assert _model_response_content(rows["admin_001"]) != _model_response_content(
        neutral_rows["admin_001"]
    )
    assert rows["sales_001"]["expectedDecision"] == "denied"
    assert rows["sales_001"]["actualDecision"] == "denied"
    assert rows["sales_001"]["matched"] is True
    assert rows["admin_001"]["expectedDecision"] == "allowed"
    assert rows["admin_001"]["actualDecision"] == "denied"
    assert rows["admin_001"]["matched"] is False
    assert all("tool_call" not in _event_types(row) for row in rows.values())
    assert all("tool_result" not in _event_types(row) for row in rows.values())
    assert all(row["findings"] == [] for row in rows.values())
    assert result["task"]["message"] != "篡改后的展示消息"
    assert result["task"]["targetId"] == "customer_002"
    assert len(claimed_provider.calls) == 2
    assert len(neutral_provider.calls) == 2


@pytest.mark.parametrize(
    "extra",
    [
        {"expected": "allowed"},
        {"actorIds": ["admin_001"]},
        {"message": "替换任务消息"},
    ],
)
def test_differential_request_rejects_extra_expected_actor_or_message_fields(
    extra: dict[str, object],
) -> None:
    provider = DifferentialProvider(emit_customer_tool_call=False)
    payload = {
        "taskId": "resource_finance_budget_access",
        "targetProfileId": "vulnerable_observe_only",
        **extra,
    }
    with _client(provider) as client:
        response = client.post("/api/differential-audits", json=payload)

    assert response.status_code == 422
    assert provider.calls == []


def test_unknown_task_is_404_and_unsupported_profile_is_422_without_provider_call() -> None:
    provider = DifferentialProvider(emit_customer_tool_call=False)
    with _client(provider) as client:
        unknown_task = client.post(
            "/api/differential-audits",
            json={"taskId": "task_missing", "targetProfileId": "secure"},
        )
        unsupported_profile = client.post(
            "/api/differential-audits",
            json={
                "taskId": "resource_finance_budget_access",
                "targetProfileId": "vulnerable_tool_observe_only",
            },
        )
        unknown_profile = client.post(
            "/api/differential-audits",
            json={
                "taskId": "resource_finance_budget_access",
                "targetProfileId": "profile_missing",
            },
        )

    assert unknown_task.status_code == 404
    assert unsupported_profile.status_code == 422
    assert unknown_profile.status_code == 422
    assert provider.calls == []


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (ProviderConfigurationError("missing provider configuration"), 503),
        (ProviderUnavailableError("provider unavailable"), 502),
        (ProviderResponseError("provider response invalid"), 502),
    ],
)
def test_provider_errors_return_status_without_partial_matrix(
    error: Exception,
    status: int,
) -> None:
    provider = RaisingProvider(error)
    with _client(provider) as client:
        response = client.post(
            "/api/differential-audits",
            json={
                "taskId": "resource_finance_budget_access",
                "targetProfileId": "vulnerable_observe_only",
            },
        )

    assert response.status_code == status
    assert "rows" not in response.json()
    assert provider.calls == 1


def test_existing_core_api_smoke_remains_available_with_differential_route() -> None:
    provider = DifferentialProvider(emit_customer_tool_call=False)
    with _client(provider) as client:
        contract = client.get("/api/security-contract")
        plans = client.get("/api/attack-plans")
        cases = client.get("/api/attack-cases")
        benchmark_cases = client.get("/api/ground-truth-cases")
        assistant = client.post(
            "/api/assistant/queries",
            json={"actorId": "sales_001", "message": "查询公开资料"},
        )

    assert contract.status_code == 200
    assert plans.status_code == 200
    assert cases.status_code == 200
    assert benchmark_cases.status_code == 200
    assert assistant.status_code == 200
    assert assistant.json()["queryId"]
