from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse, ToolCall
from tests.retriever_support import make_tfidf_retriever


@dataclass
class FakeProvider:
    answer: str = "固定 Replay API 回答"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return LLMResponse(content=self.answer, tool_calls=())


@dataclass
class ToolReplayProvider:
    answer: str = "工具 Replay API 最终回答"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if tools:
            return LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id=f"call_api_replay_{len(self.calls)}",
                        name="mock_customer_lookup",
                        arguments={"customerId": "customer_002"},
                    ),
                ),
            )
        return LLMResponse(content=self.answer, tool_calls=())


def _client(provider) -> TestClient:
    return TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    )


def _plan_by_type(plans: list[dict[str, Any]], basis_type: str) -> dict[str, Any]:
    return next(plan for plan in plans if plan["basisType"] == basis_type)


def _events(attempt: dict[str, Any]) -> list[dict[str, Any]]:
    return attempt["traceEvents"]


def _context_ids(
    events: list[dict[str, Any]], *, includes_tool_result: bool = False
) -> set[str]:
    context = next(
        event
        for event in events
        if event["type"] == "sink"
        and event["details"].get("sinkType") == "model_context"
        and event["details"].get("includesToolResult") == includes_tool_result
    )
    return set(context["details"]["documentIds"])


def _input_details(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(event["details"] for event in events if event["type"] == "input")


def _retrieval_details(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(
        event["details"] for event in events if event["type"] == "retrieval"
    )


def test_resource_replay_api_returns_failed_before_and_passed_after() -> None:
    provider = FakeProvider()
    with _client(provider) as client:
        original_contract = client.get("/api/security-contract").json()
        plans_before = client.get("/api/attack-plans").json()
        plan = _plan_by_type(plans_before, "resource_owner_scope")
        response = client.post(f"/api/attack-plans/{plan['id']}/replay")
        contract_after = client.get("/api/security-contract").json()
        plans_after = client.get("/api/attack-plans").json()

    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"id", "plan", "remediation", "before", "after", "status"}
    assert result["status"] == "passed"
    assert result["plan"] == plan
    assert result["remediation"]["configurationPath"] == (
        "targetProfile.enforceResourceAuthorization"
    )
    assert result["remediation"]["beforeValue"] is False
    assert result["remediation"]["afterValue"] is True

    before = result["before"]
    after = result["after"]
    assert before["profileId"] == plan["targetProfileId"]
    assert before["executionStatus"] == "completed"
    assert before["queryResult"] is not None
    assert before["blockedReason"] is None
    assert after["profileId"] == "secure"
    assert after["executionStatus"] == "completed"
    assert after["queryResult"] is not None
    assert after["blockedReason"] is None

    before_events = _events(before)
    after_events = _events(after)
    assert _input_details(before_events) == _input_details(after_events)
    assert _retrieval_details(before_events) == _retrieval_details(after_events)
    assert plan["targetId"] in _context_ids(before_events)
    assert plan["targetId"] not in _context_ids(after_events)
    assert any(
        event["type"] == "authorization"
        and event["details"].get("documentId") == plan["targetId"]
        and event["details"].get("decision") == "denied"
        for event in after_events
    )
    assert before["evaluation"]["status"] == "failed"
    assert any(
        finding["category"] == "resource_authorization_bypass"
        for finding in before["evaluation"]["findings"]
    )
    assert after["evaluation"]["status"] == "passed"
    assert after["evaluation"]["findings"] == []
    assert before["evaluation"]["semanticReview"]["performed"] is False
    assert after["evaluation"]["semanticReview"]["performed"] is False
    assert len(provider.calls) == 2
    assert contract_after == original_contract
    assert plans_after == plans_before


def test_tool_replay_api_blocks_after_denied_authorization_without_tool_events() -> None:
    provider = ToolReplayProvider()
    with _client(provider) as client:
        original_contract = client.get("/api/security-contract").json()
        plan = _plan_by_type(
            client.get("/api/attack-plans").json(), "tool_owner_scope"
        )
        response = client.post(f"/api/attack-plans/{plan['id']}/replay")
        contract_after = client.get("/api/security-contract").json()

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "passed"
    assert result["remediation"]["configurationPath"] == (
        "targetProfile.enforceToolAuthorization"
    )
    assert result["remediation"]["beforeValue"] is False
    assert result["remediation"]["afterValue"] is True

    before = result["before"]
    after = result["after"]
    before_events = _events(before)
    after_events = _events(after)
    before_types = [event["type"] for event in before_events]
    after_types = [event["type"] for event in after_events]
    assert before["profileId"] == plan["targetProfileId"]
    assert before["executionStatus"] == "completed"
    assert before["queryResult"] is not None
    assert after["profileId"] == "secure"
    assert after["executionStatus"] == "blocked"
    assert after["queryResult"] is None
    assert after["blockedReason"] == (
        "actor is not authorized to use Mock Customer Tool"
    )
    assert _input_details(before_events) == _input_details(after_events)
    assert _retrieval_details(before_events) == _retrieval_details(after_events)
    assert any(
        event["type"] == "authorization"
        and event["details"].get("toolName") == "mock_customer_lookup"
        and event["details"].get("decision") == "denied"
        for event in before_events
    )
    assert "tool_call" in before_types
    assert "tool_result" in before_types
    assert any(
        event["type"] == "authorization"
        and event["details"].get("toolName") == "mock_customer_lookup"
        and event["details"].get("decision") == "denied"
        for event in after_events
    )
    assert "tool_call" not in after_types
    assert "tool_result" not in after_types
    assert before["evaluation"]["status"] == "failed"
    assert any(
        finding["category"] == "tool_authorization_bypass"
        for finding in before["evaluation"]["findings"]
    )
    assert after["evaluation"]["status"] == "passed"
    assert after["evaluation"]["findings"] == []
    assert after["evaluation"]["semanticReview"]["performed"] is False
    assert len(provider.calls) == 3
    assert provider.calls[0][1]
    assert provider.calls[1][1] is None
    assert provider.calls[2][1]
    assert contract_after == original_contract


def test_unknown_or_invalidated_plan_replay_returns_404() -> None:
    with _client(FakeProvider()) as client:
        unknown_response = client.post(
            "/api/attack-plans/plan_missing/replay"
        )
        original_contract = client.get("/api/security-contract").json()
        stale_plan = _plan_by_type(
            client.get("/api/attack-plans").json(), "resource_owner_scope"
        )
        changed_contract = deepcopy(original_contract)
        owner_rule = next(
            rule
            for rule in changed_contract["resourceRules"]
            if rule["requireOwnerMatch"]
        )
        owner_rule["requireOwnerMatch"] = False
        update_response = client.put("/api/security-contract", json=changed_contract)
        stale_response = client.post(
            f"/api/attack-plans/{stale_plan['id']}/replay"
        )

    assert unknown_response.status_code == 404
    assert update_response.status_code == 200
    assert stale_response.status_code == 404


def test_default_secure_assistant_still_returns_original_tool_403() -> None:
    provider = ToolReplayProvider()
    with _client(provider) as client:
        response = client.post(
            "/api/assistant/queries",
            json={
                "actorId": "sales_001",
                "message": "请查询 customer_002 的客户记录",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "actor is not authorized to use Mock Customer Tool"
    )
    assert len(provider.calls) == 1
