import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_audit_api.attack_cases import AttackCaseExecutor, load_target_profiles
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.planning import AttackPlanExecutor, ContractAttackPlanner
from agent_audit_api.providers.base import LLMResponse, ToolCall
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.tools import (
    MockCustomerExportTool,
    MockCustomerTool,
    MockMailTool,
)


@dataclass
class FakeProvider:
    answer: str = "固定 Plan 测试回答"
    tool_call: ToolCall | None = None
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if self.tool_call is not None and len(self.calls) == 1:
            return LLMResponse(content="", tool_calls=(self.tool_call,))
        return LLMResponse(content=self.answer, tool_calls=())


def _data():
    return load_demo_data()


def _planner(contract=None) -> ContractAttackPlanner:
    data = _data()
    return ContractAttackPlanner(
        contract=contract or load_security_contract(),
        actors=data.actors,
        documents=data.documents,
        customers=data.customers,
        customer_tool=MockCustomerTool(data.customers),
        mail_tool=MockMailTool(),
        export_tool=MockCustomerExportTool(data.customers),
    )


def _case_executor(provider: FakeProvider, contract=None) -> AttackCaseExecutor:
    data = _data()
    return AttackCaseExecutor(
        provider=provider,
        actors=data.actors,
        retriever=TfidfRetriever(data.documents),
        customer_tool=MockCustomerTool(data.customers),
        contract=contract or load_security_contract(),
        profiles=load_target_profiles(),
    )


def _events(result) -> list[dict[str, Any]]:
    return [event.model_dump(by_alias=True) for event in result.query_result.trace_events]


def _context_ids(result, *, includes_tool_result: bool = False) -> set[str]:
    for event in _events(result):
        if (
            event["type"] == "sink"
            and event["details"].get("sinkType") == "model_context"
            and event["details"].get("includesToolResult") == includes_tool_result
        ):
            return set(event["details"]["documentIds"])
    raise AssertionError("model_context sink was not recorded")


def _plans_by_type(plans):
    return {plan.basis_type: plan for plan in plans}


def test_default_contract_generates_one_plan_for_each_supported_basis() -> None:
    contract = load_security_contract()
    plans = _planner(contract).plan()

    assert len(plans) == 4
    assert {plan.basis_type for plan in plans} == {
        "resource_owner_scope",
        "tool_owner_scope",
        "source_sink",
        "tool_record_limit",
    }
    assert {
        plan.basis_type: plan.attacker_type
        for plan in plans
    } == {
        "resource_owner_scope": "inside_out",
        "tool_owner_scope": "inside_out",
        "source_sink": "outside_in",
        "tool_record_limit": "inside_out",
    }
    assert all(plan.expected_finding_categories for plan in plans)


def test_plan_basis_actor_and_target_are_traceable_to_contract_assets() -> None:
    contract = load_security_contract()
    data = _data()
    actors = {actor.id: actor for actor in data.actors}
    documents = {document.id: document for document in data.documents}
    customers = {customer.id: customer for customer in data.customers}
    resource_rules = {
        rule.id: rule
        for rule in contract.resource_rules
        if rule.require_owner_match
    }
    tool_rules = {rule.id: rule for rule in contract.tool_rules}

    for plan in _planner(contract).plan():
        assert plan.actor_id in actors
        actor = actors[plan.actor_id]
        if plan.basis_type == "resource_owner_scope":
            assert plan.target_kind == "knowledge_document"
            assert plan.target_id in documents
            rule = resource_rules[plan.basis_rule_id]
            target = documents[plan.target_id]
            assert actor.role in rule.allowed_roles
            assert all(label in target.labels for label in rule.match_labels)
            assert actor.id != target.owner_id
        elif plan.basis_type == "tool_owner_scope":
            assert plan.target_kind == "customer_record"
            assert plan.target_id in customers
            rule = tool_rules[plan.basis_rule_id]
            target = customers[plan.target_id]
            assert actor.role in rule.allowed_roles
            assert actor.id != target.owner_id
        elif plan.basis_type == "source_sink":
            assert plan.target_kind == "external_sink"
            assert plan.target_id
            assert plan.basis_rule_id in {rule.id for rule in contract.sink_rules}
        elif plan.basis_type == "tool_record_limit":
            assert plan.target_kind == "customer_export"
            assert plan.target_id
            rule = tool_rules[plan.basis_rule_id]
            assert rule.max_records is not None
            assert actor.role in rule.allowed_roles
        else:  # pragma: no cover - keeps the supported basis set explicit
            raise AssertionError(f"unsupported plan basis: {plan.basis_type}")


@pytest.mark.parametrize(
    ("basis_type", "rule_collection"),
    [
        ("resource_owner_scope", "resource_rules"),
        ("tool_owner_scope", "tool_rules"),
    ],
)
def test_disabling_owner_match_rule_removes_plan_and_restoring_regenerates(
    basis_type: str,
    rule_collection: str,
) -> None:
    contract = load_security_contract()
    rules = list(getattr(contract, rule_collection))
    owner_rules = [rule for rule in rules if rule.require_owner_match]
    assert len(owner_rules) == 1
    disabled_rules = [
        rule.model_copy(
            update={"require_owner_match": False}
            if rule.id == owner_rules[0].id
            else {}
        )
        for rule in rules
    ]
    disabled_contract = contract.model_copy(update={rule_collection: disabled_rules})

    disabled_plans = _planner(disabled_contract).plan()
    assert all(plan.basis_type != basis_type for plan in disabled_plans)

    restored_plans = _planner(contract).plan()
    assert any(plan.basis_type == basis_type for plan in restored_plans)


def test_resource_plan_executes_retrieval_denial_context_and_resource_finding() -> None:
    provider = FakeProvider()
    contract = load_security_contract()
    plan = _plans_by_type(_planner(contract).plan())["resource_owner_scope"]
    result = asyncio.run(
        AttackPlanExecutor(_case_executor(provider, contract)).execute(plan)
    )
    events = _events(result)

    retrieval = next(event for event in events if event["type"] == "retrieval")
    assert plan.target_id in retrieval["details"]["documentIds"]
    assert any(
        event["type"] == "authorization"
        and event["details"].get("documentId") == plan.target_id
        and event["details"].get("decision") == "denied"
        for event in events
    )
    assert plan.target_id in _context_ids(result)
    assert any(
        finding.category == "resource_authorization_bypass"
        for finding in result.evaluation.findings
    )
    assert result.evaluation.status == "failed"
    assert result.evaluation.semantic_review.performed is False
    assert len(provider.calls) == 1


def test_tool_plan_executes_denied_tool_call_result_and_tool_finding() -> None:
    provider = FakeProvider(
        answer="工具计划最终回答",
        tool_call=ToolCall(
            id="call_plan_customer_002",
            name="mock_customer_lookup",
            arguments={"customerId": "customer_002"},
        ),
    )
    contract = load_security_contract()
    plan = _plans_by_type(_planner(contract).plan())["tool_owner_scope"]
    result = asyncio.run(
        AttackPlanExecutor(_case_executor(provider, contract)).execute(plan)
    )
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
    assert any(
        finding.category == "tool_authorization_bypass"
        for finding in result.evaluation.findings
    )
    assert result.evaluation.status == "failed"
    assert result.evaluation.semantic_review.performed is False
    assert len(provider.calls) == 2


@pytest.mark.parametrize("basis_type", ["resource_owner_scope", "tool_owner_scope"])
def test_expected_category_and_basis_rule_changes_do_not_change_evaluation(
    basis_type: str,
) -> None:
    contract = load_security_contract()
    plan = _plans_by_type(_planner(contract).plan())[basis_type]
    altered_plan = plan.model_copy(
        update={
            "expected_finding_categories": [],
            "basis_rule_id": "changed_only_for_test",
        }
    )

    original_provider = FakeProvider(
        tool_call=(
            ToolCall(
                id="call_original",
                name="mock_customer_lookup",
                arguments={"customerId": "customer_002"},
            )
            if basis_type == "tool_owner_scope"
            else None
        )
    )
    altered_provider = FakeProvider(
        tool_call=(
            ToolCall(
                id="call_altered",
                name="mock_customer_lookup",
                arguments={"customerId": "customer_002"},
            )
            if basis_type == "tool_owner_scope"
            else None
        )
    )
    original = asyncio.run(
        AttackPlanExecutor(_case_executor(original_provider, contract)).execute(plan)
    )
    altered = asyncio.run(
        AttackPlanExecutor(_case_executor(altered_provider, contract)).execute(altered_plan)
    )

    assert original.evaluation.status == altered.evaluation.status
    assert original.evaluation.findings == altered.evaluation.findings
    assert original.evaluation.contract_id == altered.evaluation.contract_id
    assert original.evaluation.contract_version == altered.evaluation.contract_version
