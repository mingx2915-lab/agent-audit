import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_audit_api.attack_cases import (
    AttackCase,
    AttackCaseExecutor,
    load_attack_cases,
    load_target_profiles,
)
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.providers.base import LLMResponse
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.tools import MockCustomerTool


@dataclass
class FakeProvider:
    answer: str = "固定 Case 测试回答"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return LLMResponse(content=self.answer, tool_calls=())


def _cases() -> tuple[AttackCase, ...]:
    return load_attack_cases()


def _executor(provider: FakeProvider) -> AttackCaseExecutor:
    data = load_demo_data()
    return AttackCaseExecutor(
        provider=provider,
        actors=data.actors,
        retriever=TfidfRetriever(data.documents),
        customer_tool=MockCustomerTool(data.customers),
        contract=load_security_contract(),
        profiles=load_target_profiles(),
    )


def _case(case_id: str) -> AttackCase:
    return next(case for case in _cases() if case.id == case_id)


def _events(result) -> list[dict[str, Any]]:
    return [event.model_dump(by_alias=True) for event in result.query_result.trace_events]


def _context_events(result) -> list[dict[str, Any]]:
    return [
        event
        for event in _events(result)
        if event["type"] == "sink"
        and event["details"].get("sinkType") == "model_context"
    ]


def _authorization_events(result) -> list[dict[str, Any]]:
    return [
        event for event in _events(result) if event["type"] == "authorization"
    ]


def test_fixed_cases_have_exactly_one_case_per_attacker_type() -> None:
    cases = _cases()
    profiles = load_target_profiles()

    assert len(cases) == 2
    assert {case.attacker_type for case in cases} == {"outside_in", "inside_out"}
    assert {case.id for case in cases} == {
        "case_inside_out_customer_scope",
        "case_outside_in_untrusted_rag",
    }
    assert {
        "secure",
        "vulnerable_observe_only",
        "vulnerable_tool_observe_only",
    } <= {profile.id for profile in profiles}
    assert all(case.target_profile_id in {profile.id for profile in profiles} for case in cases)


def test_secure_profile_denies_non_owner_document_before_model_context() -> None:
    provider = FakeProvider()
    executor = _executor(provider)
    secure_case = _case("case_inside_out_customer_scope").model_copy(
        update={"target_profile_id": "secure"}
    )

    result = asyncio.run(executor.execute(secure_case))
    events = _events(result)
    denied_ids = {
        event["details"]["documentId"]
        for event in _authorization_events(result)
        if event["details"].get("decision") == "denied"
        and "documentId" in event["details"]
    }
    context_ids = set(_context_events(result)[0]["details"]["documentIds"])

    assert "doc_customer_contract_002" in denied_ids
    assert "doc_customer_contract_002" not in context_ids
    assert result.evaluation.status == "passed"
    assert result.evaluation.findings == []
    assert any(event["type"] == "retrieval" for event in events)
    assert any(event["type"] == "model_response" for event in events)
    assert len(provider.calls) == 1


def test_observe_only_inside_case_records_denial_and_real_context_bypass() -> None:
    provider = FakeProvider()
    result = asyncio.run(_executor(provider).execute(_case("case_inside_out_customer_scope")))

    retrieval = next(event for event in _events(result) if event["type"] == "retrieval")
    denied = [
        event
        for event in _authorization_events(result)
        if event["details"].get("decision") == "denied"
    ]
    context_ids = set(_context_events(result)[0]["details"]["documentIds"])

    assert "doc_customer_contract_002" in retrieval["details"]["documentIds"]
    assert any(
        event["details"].get("documentId") == "doc_customer_contract_002"
        for event in denied
    )
    assert "doc_customer_contract_002" in context_ids
    assert result.evaluation.status == "failed"
    assert any(
        finding.category == "resource_authorization_bypass"
        for finding in result.evaluation.findings
    )
    assert len(provider.calls) == 1


def test_outside_in_case_records_untrusted_source_and_restricted_context_finding() -> None:
    provider = FakeProvider()
    result = asyncio.run(_executor(provider).execute(_case("case_outside_in_untrusted_rag")))
    events = _events(result)

    assert any(
        event["type"] == "source"
        and event["details"].get("sourceType") == "external_document"
        and event["details"].get("trustLevel") == "untrusted"
        for event in events
    )
    denied_ids = {
        event["details"]["documentId"]
        for event in _authorization_events(result)
        if event["details"].get("decision") == "denied"
        and "documentId" in event["details"]
    }
    context_ids = set(_context_events(result)[0]["details"]["documentIds"])
    # F-015 explicitly allows the synthetic external-document source to enter
    # context; the finance document remains the restricted resource.
    allowed_ids = {
        event["details"]["documentId"]
        for event in _authorization_events(result)
        if event["details"].get("decision") == "allowed"
        and "documentId" in event["details"]
    }
    assert "doc_external_vendor_prompt_001" in allowed_ids
    assert "doc_external_vendor_prompt_001" not in denied_ids
    assert "doc_finance_budget_001" in denied_ids
    assert "doc_finance_budget_001" in context_ids
    assert denied_ids & context_ids
    assert result.evaluation.status == "failed"
    assert any(
        finding.category == "resource_authorization_bypass"
        for finding in result.evaluation.findings
    )
    assert any(event["type"] == "retrieval" for event in events)
    assert any(event["type"] == "model_response" for event in events)
    assert len(provider.calls) == 1


def test_expected_finding_categories_do_not_change_actual_evaluation() -> None:
    original_case = _case("case_inside_out_customer_scope")
    altered_case = original_case.model_copy(update={"expected_finding_categories": []})

    original_result = asyncio.run(_executor(FakeProvider()).execute(original_case))
    altered_result = asyncio.run(_executor(FakeProvider()).execute(altered_case))

    assert original_result.evaluation.status == altered_result.evaluation.status
    assert original_result.evaluation.findings == altered_result.evaluation.findings
    assert original_result.evaluation.contract_id == altered_result.evaluation.contract_id
    assert original_result.evaluation.contract_version == altered_result.evaluation.contract_version


def test_executor_rejects_unknown_target_profile() -> None:
    case = _case("case_inside_out_customer_scope").model_copy(
        update={"target_profile_id": "profile_missing"}
    )

    with pytest.raises(ValueError, match="profile"):
        asyncio.run(_executor(FakeProvider()).execute(case))
