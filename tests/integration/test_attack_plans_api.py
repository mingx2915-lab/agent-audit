from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse, ToolCall
from tests.retriever_support import make_tfidf_retriever


@dataclass
class FakeProvider:
    answer: str = "固定 Plan API 测试回答"
    tool_call: ToolCall | None = None
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if self.tool_call is not None and len(self.calls) == 1:
            return LLMResponse(content="", tool_calls=(self.tool_call,))
        return LLMResponse(content=self.answer, tool_calls=())


def _client(provider: FakeProvider) -> TestClient:
    return TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    )


def _plan_by_type(plans: list[dict[str, Any]], basis_type: str) -> dict[str, Any]:
    return next(plan for plan in plans if plan["basisType"] == basis_type)


def _events(result: dict[str, Any]) -> list[dict[str, Any]]:
    return result["queryResult"]["traceEvents"]


def _context_ids(events: list[dict[str, Any]], *, includes_tool_result: bool = False) -> set[str]:
    context = next(
        event
        for event in events
        if event["type"] == "sink"
        and event["details"].get("sinkType") == "model_context"
        and event["details"].get("includesToolResult") == includes_tool_result
    )
    return set(context["details"]["documentIds"])


def test_default_attack_plans_are_four_traceable_security_plans() -> None:
    with _client(FakeProvider()) as client:
        plans_response = client.get("/api/attack-plans")
        contract = client.get("/api/security-contract").json()
        actors = client.get("/api/demo/actors").json()

    assert plans_response.status_code == 200
    plans = plans_response.json()
    assert len(plans) == 4
    assert {plan["basisType"] for plan in plans} == {
        "resource_owner_scope",
        "tool_owner_scope",
        "source_sink",
        "tool_record_limit",
    }
    assert {
        plan["basisType"]: plan["attackerType"]
        for plan in plans
    } == {
        "resource_owner_scope": "inside_out",
        "tool_owner_scope": "inside_out",
        "source_sink": "outside_in",
        "tool_record_limit": "inside_out",
    }
    assert all(
        set(plan)
        == {
            "id",
            "name",
            "description",
            "basisType",
            "basisRuleId",
            "attackerType",
            "actorId",
            "targetKind",
            "targetId",
            "message",
            "targetProfileId",
            "expectedFindingCategories",
        }
        for plan in plans
    )

    actor_ids = {actor["id"] for actor in actors}
    resource_rule_ids = {
        rule["id"]
        for rule in contract["resourceRules"]
        if rule["requireOwnerMatch"]
    }
    tool_rule_ids = {
        rule["id"]
        for rule in contract["toolRules"]
        if rule["requireOwnerMatch"]
    }
    data = load_demo_data()
    document_ids = {document.id for document in data.documents}
    customer_ids = {customer.id for customer in data.customers}

    resource_plan = _plan_by_type(plans, "resource_owner_scope")
    tool_plan = _plan_by_type(plans, "tool_owner_scope")
    source_sink_plan = _plan_by_type(plans, "source_sink")
    export_plan = _plan_by_type(plans, "tool_record_limit")
    assert resource_plan["basisRuleId"] in resource_rule_ids
    assert tool_plan["basisRuleId"] in tool_rule_ids
    assert resource_plan["actorId"] in actor_ids
    assert tool_plan["actorId"] in actor_ids
    assert resource_plan["targetKind"] == "knowledge_document"
    assert resource_plan["targetId"] in document_ids
    assert tool_plan["targetKind"] == "customer_record"
    assert tool_plan["targetId"] in customer_ids
    assert source_sink_plan["targetKind"] == "external_sink"
    assert source_sink_plan["targetId"]
    assert export_plan["targetKind"] == "customer_export"
    assert export_plan["targetId"]


@pytest.mark.parametrize(
    ("basis_type", "rules_key"),
    [
        ("resource_owner_scope", "resourceRules"),
        ("tool_owner_scope", "toolRules"),
    ],
)
def test_contract_update_refreshes_derived_plans(
    basis_type: str,
    rules_key: str,
) -> None:
    with _client(FakeProvider()) as client:
        original_contract = client.get("/api/security-contract").json()
        changed_contract = deepcopy(original_contract)
        owner_rule = next(
            rule for rule in changed_contract[rules_key] if rule["requireOwnerMatch"]
        )
        owner_rule["requireOwnerMatch"] = False

        put_response = client.put("/api/security-contract", json=changed_contract)
        after_change = client.get("/api/attack-plans")
        restore_response = client.put("/api/security-contract", json=original_contract)
        after_restore = client.get("/api/attack-plans")

    assert put_response.status_code == 200
    assert all(plan["basisType"] != basis_type for plan in after_change.json())
    assert restore_response.status_code == 200
    assert any(plan["basisType"] == basis_type for plan in after_restore.json())


def test_resource_plan_execution_has_real_retrieval_denial_context_and_finding() -> None:
    provider = FakeProvider()
    with _client(provider) as client:
        plan = _plan_by_type(
            client.get("/api/attack-plans").json(), "resource_owner_scope"
        )
        response = client.post(f"/api/attack-plans/{plan['id']}/execute")

    assert response.status_code == 200
    result = response.json()
    events = _events(result)
    retrieval = next(event for event in events if event["type"] == "retrieval")
    assert plan["targetId"] in retrieval["details"]["documentIds"]
    assert any(
        event["type"] == "authorization"
        and event["details"].get("documentId") == plan["targetId"]
        and event["details"].get("decision") == "denied"
        for event in events
    )
    assert plan["targetId"] in _context_ids(events)
    assert result["evaluation"]["status"] == "failed"
    assert any(
        finding["category"] == "resource_authorization_bypass"
        for finding in result["evaluation"]["findings"]
    )
    assert result["evaluation"]["semanticReview"]["performed"] is False
    assert len(provider.calls) == 1


def test_tool_plan_execution_has_denied_tool_call_result_and_tool_finding() -> None:
    provider = FakeProvider(
        answer="工具计划最终回答",
        tool_call=ToolCall(
            id="call_plan_customer_002",
            name="mock_customer_lookup",
            arguments={"customerId": "customer_002"},
        ),
    )
    with _client(provider) as client:
        plan = _plan_by_type(
            client.get("/api/attack-plans").json(), "tool_owner_scope"
        )
        response = client.post(f"/api/attack-plans/{plan['id']}/execute")

    assert response.status_code == 200
    result = response.json()
    events = _events(result)
    assert any(
        event["type"] == "authorization"
        and event["details"].get("toolName") == "mock_customer_lookup"
        and event["details"].get("decision") == "denied"
        for event in events
    )
    tool_call = next(event for event in events if event["type"] == "tool_call")
    assert tool_call["details"] == {
        "toolName": "mock_customer_lookup",
        "arguments": {"customerId": "customer_002"},
    }
    tool_result = next(event for event in events if event["type"] == "tool_result")
    assert tool_result["details"]["success"] is True
    assert tool_result["details"]["data"]["customerId"] == "customer_002"
    assert result["evaluation"]["status"] == "failed"
    assert any(
        finding["category"] == "tool_authorization_bypass"
        for finding in result["evaluation"]["findings"]
    )
    assert result["evaluation"]["semanticReview"]["performed"] is False
    assert len(provider.calls) == 2


def test_default_assistant_query_remains_secure_after_planner_is_available() -> None:
    provider = FakeProvider()
    with _client(provider) as client:
        resource_plan = _plan_by_type(
            client.get("/api/attack-plans").json(), "resource_owner_scope"
        )
        response = client.post(
            "/api/assistant/queries",
            json={
                "actorId": resource_plan["actorId"],
                "message": resource_plan["message"],
            },
        )

    assert response.status_code == 200
    events = response.json()["traceEvents"]
    denied_ids = {
        event["details"]["documentId"]
        for event in events
        if event["type"] == "authorization"
        and event["details"].get("decision") == "denied"
        and "documentId" in event["details"]
    }
    assert resource_plan["targetId"] in denied_ids
    assert resource_plan["targetId"] not in _context_ids(events)
    assert len(provider.calls) == 1


def test_unknown_or_invalidated_plan_returns_404() -> None:
    with _client(FakeProvider()) as client:
        unknown_response = client.post("/api/attack-plans/plan_missing/execute")
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
            f"/api/attack-plans/{stale_plan['id']}/execute"
        )

    assert unknown_response.status_code == 404
    assert update_response.status_code == 200
    assert stale_response.status_code == 404
