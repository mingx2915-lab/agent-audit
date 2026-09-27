import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

import agent_audit_api.replay as replay_module
from agent_audit_api.attack_cases import AttackCaseExecutor, load_target_profiles
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.planning import AttackPlanExecutor, ContractAttackPlanner
from agent_audit_api.providers.base import LLMResponse, ToolCall
from agent_audit_api.replay import ReplayExecutor, build_remediation
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.tools import MockCustomerTool


@dataclass
class FakeProvider:
    answer: str = "固定 Replay 测试回答"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return LLMResponse(content=self.answer, tool_calls=())


@dataclass
class ToolReplayProvider:
    answer: str = "工具 Replay 最终回答"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if tools:
            return LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id=f"call_replay_{len(self.calls)}",
                        name="mock_customer_lookup",
                        arguments={"customerId": "customer_002"},
                    ),
                ),
            )
        return LLMResponse(content=self.answer, tool_calls=())


def _data():
    return load_demo_data()


def _plan(basis_type: str):
    data = _data()
    plans = ContractAttackPlanner(
        contract=load_security_contract(),
        actors=data.actors,
        documents=data.documents,
        customers=data.customers,
        customer_tool=MockCustomerTool(data.customers),
    ).plan()
    return next(plan for plan in plans if plan.basis_type == basis_type)


def _replay_executor(provider, contract):
    data = _data()
    case_executor = AttackCaseExecutor(
        provider=provider,
        actors=data.actors,
        retriever=TfidfRetriever(data.documents),
        customer_tool=MockCustomerTool(data.customers),
        contract=contract,
        profiles=load_target_profiles(),
    )
    return ReplayExecutor(
        plan_executor=AttackPlanExecutor(case_executor),
        contract=contract,
    )


def _events(attempt) -> list[dict[str, Any]]:
    return [event.model_dump(by_alias=True) for event in attempt.trace_events]


def _context_ids(events: list[dict[str, Any]], *, includes_tool_result: bool = False) -> set[str]:
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


def test_build_remediation_uses_exact_enforcement_path_and_values() -> None:
    resource = build_remediation(_plan("resource_owner_scope"))
    tool = build_remediation(_plan("tool_owner_scope"))

    assert resource.configuration_path == "targetProfile.enforceResourceAuthorization"
    assert resource.before_value is False
    assert resource.after_value is True
    assert resource.id and resource.title and resource.summary

    assert tool.configuration_path == "targetProfile.enforceToolAuthorization"
    assert tool.before_value is False
    assert tool.after_value is True
    assert tool.id and tool.title and tool.summary


def test_resource_replay_before_fails_and_secure_after_passes() -> None:
    contract = load_security_contract()
    plan = _plan("resource_owner_scope")
    contract_before = contract.model_dump(by_alias=True)
    provider = FakeProvider()

    result = asyncio.run(_replay_executor(provider, contract).replay(plan))
    before_events = _events(result.before)
    after_events = _events(result.after)

    assert result.status == "passed"
    assert result.plan == plan
    assert result.remediation == build_remediation(plan)
    assert result.before.profile_id == plan.target_profile_id
    assert result.before.execution_status == "completed"
    assert result.before.query_result is not None
    assert result.after.profile_id == "secure"
    assert result.after.execution_status == "completed"
    assert result.after.query_result is not None
    assert result.before.blocked_reason is None
    assert result.after.blocked_reason is None

    assert _input_details(before_events) == _input_details(after_events)
    assert _retrieval_details(before_events) == _retrieval_details(after_events)
    assert plan.target_id in _retrieval_details(before_events)["documentIds"]
    assert plan.target_id in _context_ids(before_events)
    assert plan.target_id not in _context_ids(after_events)
    assert any(
        event["type"] == "authorization"
        and event["details"].get("documentId") == plan.target_id
        and event["details"].get("decision") == "denied"
        for event in after_events
    )
    assert result.before.evaluation.status == "failed"
    assert any(
        finding.category == "resource_authorization_bypass"
        for finding in result.before.evaluation.findings
    )
    assert result.after.evaluation.status == "passed"
    assert result.after.evaluation.findings == []
    assert result.before.evaluation.semantic_review.performed is False
    assert result.after.evaluation.semantic_review.performed is False
    assert len(provider.calls) == 2
    assert contract.model_dump(by_alias=True) == contract_before


def test_tool_replay_blocks_after_denied_authorization_and_keeps_real_trace() -> None:
    contract = load_security_contract()
    plan = _plan("tool_owner_scope")
    contract_before = contract.model_dump(by_alias=True)
    provider = ToolReplayProvider()

    result = asyncio.run(_replay_executor(provider, contract).replay(plan))
    before_events = _events(result.before)
    after_events = _events(result.after)
    before_types = [event["type"] for event in before_events]
    after_types = [event["type"] for event in after_events]

    assert result.status == "passed"
    assert result.plan == plan
    assert result.remediation.configuration_path == (
        "targetProfile.enforceToolAuthorization"
    )
    assert result.before.profile_id == plan.target_profile_id
    assert result.before.execution_status == "completed"
    assert result.before.query_result is not None
    assert result.after.profile_id == "secure"
    assert result.after.execution_status == "blocked"
    assert result.after.query_result is None
    assert result.after.blocked_reason == (
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
    assert after_types[0:3] == ["input", "source", "retrieval"]
    assert result.before.evaluation.status == "failed"
    assert any(
        finding.category == "tool_authorization_bypass"
        for finding in result.before.evaluation.findings
    )
    assert result.after.evaluation.status == "passed"
    assert result.after.evaluation.findings == []
    assert result.after.evaluation.semantic_review.performed is False
    assert len(provider.calls) == 3
    assert provider.calls[0][1]
    assert provider.calls[1][1] is None
    assert provider.calls[2][1]
    assert contract.model_dump(by_alias=True) == contract_before


def test_tampered_remediation_and_plan_display_fields_do_not_change_replay_status(
    monkeypatch,
) -> None:
    contract = load_security_contract()
    plan = _plan("resource_owner_scope")
    altered_plan = plan.model_copy(
        update={
            "name": "篡改后的展示名称",
            "description": "篡改后的展示描述",
            "expected_finding_categories": [],
        }
    )
    actual_recommendation = build_remediation(plan)
    tampered_recommendation = actual_recommendation.model_copy(
        update={
            "id": "tampered-remediation",
            "title": "篡改后的建议",
            "summary": "篡改后的说明",
            "configuration_path": "targetProfile.enforceToolAuthorization",
            "before_value": True,
            "after_value": False,
        }
    )
    monkeypatch.setattr(
        replay_module,
        "build_remediation",
        lambda _plan: tampered_recommendation,
    )

    result = asyncio.run(
        _replay_executor(FakeProvider(), contract).replay(altered_plan)
    )

    assert result.status == "passed"
    assert result.before.evaluation.status == "failed"
    assert result.after.evaluation.status == "passed"
    assert result.before.evaluation.findings
    assert result.after.evaluation.findings == []
