from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse, ToolCall
from tests.retriever_support import make_tfidf_retriever


@dataclass
class ReplayProvider:
    answer: str = "报告 API 测试最终回答"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        user_text = "\n".join(
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "user"
        )
        if tools and "mock_customer_lookup" in user_text:
            return LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id=f"call_report_api_{len(self.calls)}",
                        name="mock_customer_lookup",
                        arguments={"customerId": "customer_002"},
                    ),
                ),
            )
        return LLMResponse(content=self.answer, tool_calls=())


def _client(provider: ReplayProvider) -> TestClient:
    return TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    )


def _plan_by_type(plans: list[dict[str, Any]], basis_type: str) -> dict[str, Any]:
    return next(plan for plan in plans if plan["basisType"] == basis_type)


def _detail_tokens(value: Any) -> list[str]:
    if isinstance(value, dict):
        tokens: list[str] = []
        for key, item in value.items():
            tokens.append(str(key))
            tokens.extend(_detail_tokens(item))
        return tokens
    if isinstance(value, list):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_detail_tokens(item))
        return tokens
    if isinstance(value, bool):
        return [str(value).lower()]
    if value is None:
        return []
    return [str(value)]


def _assert_markdown_facts(markdown: str, result: dict[str, Any]) -> None:
    for section in (
        "SYNTHETIC / DEMO ONLY",
        "Actor",
        "Source",
        "Resource",
        "Authorization",
        "Tool",
        "Sink",
        "Rule",
        "Finding",
        "修复",
        "仅供参考",
        "不会修改企业系统",
        "不能替代",
        "BEFORE",
        "AFTER",
        "Replay",
    ):
        assert section in markdown
    for attempt_key in ("before", "after"):
        for event in result[attempt_key]["traceEvents"]:
            assert str(event["sequence"]) in markdown
            assert event["type"] in markdown
            assert event["summary"] in markdown
            for token in _detail_tokens(event["details"]):
                assert token in markdown
    plan = result["plan"]
    assert plan["basisRuleId"] in markdown
    for finding in result["before"]["evaluation"]["findings"]:
        assert finding["category"] in markdown
        for sequence in finding["evidenceSequences"]:
            assert str(sequence) in markdown
        if finding["ruleId"] is not None:
            assert finding["ruleId"] in markdown


@pytest.mark.parametrize("basis_type", ["resource_owner_scope", "tool_owner_scope"])
def test_report_api_uses_real_replay_artifact_without_more_provider_calls(
    basis_type: str,
) -> None:
    provider = ReplayProvider()
    with _client(provider) as client:
        contract_before = client.get("/api/security-contract").json()
        plans_before = client.get("/api/attack-plans").json()
        plan = _plan_by_type(plans_before, basis_type)
        replay_response = client.post(f"/api/attack-plans/{plan['id']}/replay")
        replay_payload = replay_response.json()
        replay_snapshot = deepcopy(replay_payload)
        calls_before_report = len(provider.calls)
        report_response = client.post(
            "/api/attack-chain-reports",
            json=replay_payload,
        )
        contract_after = client.get("/api/security-contract").json()
        plans_after = client.get("/api/attack-plans").json()

    assert replay_response.status_code == 200
    assert report_response.status_code == 200
    result = report_response.json()
    assert set(result) == {
        "id",
        "generatedAt",
        "title",
        "executiveSummary",
        "replay",
        "markdown",
    }
    assert result["replay"] == replay_snapshot
    assert replay_payload == replay_snapshot
    assert result["generatedAt"].endswith("Z")
    assert result["title"]
    assert result["executiveSummary"]
    assert len(provider.calls) == calls_before_report
    assert contract_after == contract_before
    assert plans_after == plans_before
    _assert_markdown_facts(result["markdown"], result["replay"])

    if basis_type == "resource_owner_scope":
        target_id = plan["targetId"]
        before_contexts = [
            event
            for event in replay_snapshot["before"]["traceEvents"]
            if event["type"] == "sink"
            and event["details"].get("sinkType") == "model_context"
        ]
        after_contexts = [
            event
            for event in replay_snapshot["after"]["traceEvents"]
            if event["type"] == "sink"
            and event["details"].get("sinkType") == "model_context"
        ]
        assert any(target_id in event["details"]["documentIds"] for event in before_contexts)
        assert all(target_id not in event["details"]["documentIds"] for event in after_contexts)
    else:
        before_types = [event["type"] for event in replay_snapshot["before"]["traceEvents"]]
        after_types = [event["type"] for event in replay_snapshot["after"]["traceEvents"]]
        assert "tool_call" in before_types
        assert "tool_result" in before_types
        assert replay_snapshot["after"]["executionStatus"] == "blocked"
        assert replay_snapshot["after"]["queryResult"] is None
        assert "tool_call" not in after_types
        assert "tool_result" not in after_types
        assert replay_snapshot["after"]["blockedReason"] in result["markdown"]
        assert "未生成模型回答" in result["markdown"]


def test_report_api_rejects_invalid_replay_result_body() -> None:
    provider = ReplayProvider()
    with _client(provider) as client:
        response = client.post("/api/attack-chain-reports", json={})

    assert response.status_code == 422
    assert provider.calls == []
