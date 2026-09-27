import asyncio
from dataclasses import dataclass, field
from typing import Any

from agent_audit_api.evaluation import ContractChecker, HybridJudge
from agent_audit_api.providers.base import LLMResponse, ProviderResponseError
from agent_audit_api.schemas import TraceEvent
from agent_audit_api.security_contract import (
    ContractRole,
    SecurityContract,
)


def _event(sequence: int, event_type: str, details: dict[str, Any]) -> TraceEvent:
    return TraceEvent(
        sequence=sequence,
        type=event_type,
        summary=f"{event_type} event",
        details=details,
        occurred_at="2026-08-26T00:00:00Z",
    )


def _contract() -> SecurityContract:
    return SecurityContract(
        id="contract_test",
        name="测试 Contract",
        version=1,
        roles=[ContractRole(id="sales", display_name="销售")],
        resource_rules=[],
        tool_rules=[],
    )


def _resource_denied_then_context(
    *,
    document_id: str = "doc_denied",
    rule_id: str | None = "resource_rule_1",
) -> list[TraceEvent]:
    return [
        _event(1, "input", {"actorId": "sales_001", "message": "query"}),
        _event(
            2,
            "authorization",
            {
                "actorId": "sales_001",
                "documentId": document_id,
                "decision": "denied",
                "ruleId": rule_id,
            },
        ),
        _event(
            3,
            "sink",
            {
                "sinkId": "model_context",
                "sinkType": "model_context",
                "documentIds": [document_id],
                "includesToolResult": False,
            },
        ),
        _event(4, "model_response", {"content": "answer", "toolCallCount": 0}),
        _event(
            5,
            "sink",
            {
                "sinkId": "actor_response",
                "sinkType": "actor_response",
                "actorId": "sales_001",
            },
        ),
    ]


def _tool_denied_then_call(
    *,
    tool_name: str = "mock_customer_lookup",
    rule_id: str | None = "tool_rule_1",
) -> list[TraceEvent]:
    return [
        _event(1, "input", {"actorId": "sales_001", "message": "query"}),
        _event(
            2,
            "authorization",
            {
                "actorId": "sales_001",
                "toolName": tool_name,
                "action": "read",
                "decision": "denied",
                "ruleId": rule_id,
            },
        ),
        _event(
            3,
            "tool_call",
            {"toolName": tool_name, "arguments": {"customerId": "customer_001"}},
        ),
        _event(4, "model_response", {"content": "answer", "toolCallCount": 1}),
    ]


def test_denied_document_followed_by_model_context_creates_resource_finding() -> None:
    findings = ContractChecker().check(_resource_denied_then_context())

    assert len(findings) == 1
    finding = findings[0]
    assert finding.id == "finding_001"
    assert finding.category == "resource_authorization_bypass"
    assert finding.severity == "high"
    assert finding.contract_basis == "explicit_rule"
    assert finding.rule_id == "resource_rule_1"
    assert finding.evidence_sequences == [2, 3]


def test_denied_document_without_later_context_has_no_finding() -> None:
    trace = _resource_denied_then_context()
    trace.pop(2)
    trace[-1] = _event(4, "model_response", {"content": "answer", "toolCallCount": 0})

    assert ContractChecker().check(trace) == []


def test_denied_tool_followed_by_tool_call_creates_tool_finding() -> None:
    findings = ContractChecker().check(_tool_denied_then_call())

    assert len(findings) == 1
    finding = findings[0]
    assert finding.id == "finding_001"
    assert finding.category == "tool_authorization_bypass"
    assert finding.severity == "high"
    assert finding.contract_basis == "explicit_rule"
    assert finding.rule_id == "tool_rule_1"
    assert finding.evidence_sequences == [2, 3]


def test_resource_and_tool_events_before_denial_do_not_create_findings() -> None:
    trace = [
        _event(
            1,
            "sink",
            {
                "sinkId": "model_context",
                "sinkType": "model_context",
                "documentIds": ["doc_before_denial"],
                "includesToolResult": False,
            },
        ),
        _event(
            2,
            "tool_call",
            {"toolName": "mock_customer_lookup", "arguments": {}},
        ),
        _event(
            3,
            "authorization",
            {
                "actorId": "sales_001",
                "documentId": "doc_before_denial",
                "decision": "denied",
                "ruleId": None,
            },
        ),
        _event(
            4,
            "authorization",
            {
                "actorId": "sales_001",
                "toolName": "mock_customer_lookup",
                "action": "read",
                "decision": "denied",
                "ruleId": None,
            },
        ),
    ]

    assert ContractChecker().check(trace) == []


def test_same_denied_resource_creates_one_finding_with_first_evidence() -> None:
    trace = _resource_denied_then_context(document_id="doc_repeat")
    trace.insert(
        3,
        _event(
            3,
            "sink",
            {
                "sinkId": "model_context",
                "sinkType": "model_context",
                "documentIds": ["doc_repeat"],
                "includesToolResult": False,
            },
        ),
    )
    for index, event in enumerate(trace, start=1):
        event.sequence = index

    findings = ContractChecker().check(trace)

    assert len(findings) == 1
    assert findings[0].evidence_sequences == [2, 3]


def test_same_denied_tool_creates_one_finding_with_first_evidence() -> None:
    trace = _tool_denied_then_call()
    trace.insert(
        3,
        _event(
            3,
            "tool_call",
            {"toolName": "mock_customer_lookup", "arguments": {}},
        ),
    )
    for index, event in enumerate(trace, start=1):
        event.sequence = index

    findings = ContractChecker().check(trace)

    assert len(findings) == 1
    assert findings[0].evidence_sequences == [2, 3]


def test_normal_f005_trace_is_passed() -> None:
    trace = [
        _event(1, "input", {"actorId": "sales_001", "message": "query"}),
        _event(
            2,
            "authorization",
            {
                "actorId": "sales_001",
                "documentId": "doc_allowed",
                "decision": "allowed",
                "ruleId": "resource_rule_1",
            },
        ),
        _event(
            3,
            "sink",
            {
                "sinkId": "model_context",
                "sinkType": "model_context",
                "documentIds": ["doc_allowed"],
                "includesToolResult": False,
            },
        ),
        _event(4, "model_response", {"content": "answer", "toolCallCount": 0}),
        _event(
            5,
            "sink",
            {
                "sinkId": "actor_response",
                "sinkType": "actor_response",
                "actorId": "sales_001",
            },
        ),
    ]

    assert ContractChecker().check(trace) == []


@dataclass
class FakeProvider:
    answer: str = "补充说明"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return LLMResponse(content=self.answer, tool_calls=())


class InvalidProvider:
    async def complete(self, messages, tools=None):
        return object()


def test_include_false_does_not_call_provider_and_returns_deterministic_result() -> None:
    provider = FakeProvider()
    result = asyncio.run(
        HybridJudge(provider).evaluate(
            contract=_contract(),
            trace_events=_resource_denied_then_context(),
            include_semantic_review=False,
        )
    )

    assert provider.calls == []
    assert result.status == "failed"
    assert len(result.findings) == 1
    assert result.semantic_review.performed is False
    assert result.semantic_review.explanation is None


def test_include_true_without_findings_does_not_call_provider() -> None:
    provider = FakeProvider()
    result = asyncio.run(
        HybridJudge(provider).evaluate(
            contract=_contract(),
            trace_events=[],
            include_semantic_review=True,
        )
    )

    assert provider.calls == []
    assert result.status == "passed"
    assert result.findings == []
    assert result.semantic_review.performed is False


def test_semantic_review_only_adds_explanation_and_preserves_findings() -> None:
    trace = _resource_denied_then_context()
    deterministic = asyncio.run(
        HybridJudge(FakeProvider()).evaluate(
            contract=_contract(),
            trace_events=trace,
            include_semantic_review=False,
        )
    )
    provider = FakeProvider(answer="该资源在拒绝授权后进入了模型上下文。")
    reviewed = asyncio.run(
        HybridJudge(provider).evaluate(
            contract=_contract(),
            trace_events=trace,
            include_semantic_review=True,
        )
    )

    assert len(provider.calls) == 1
    assert reviewed.status == deterministic.status
    assert reviewed.contract_id == deterministic.contract_id
    assert reviewed.contract_version == deterministic.contract_version
    assert reviewed.findings == deterministic.findings
    assert reviewed.semantic_review.performed is True
    assert reviewed.semantic_review.explanation == "该资源在拒绝授权后进入了模型上下文。"


def test_invalid_provider_response_is_rejected_by_hybrid_judge() -> None:
    try:
        asyncio.run(
            HybridJudge(InvalidProvider()).evaluate(
                contract=_contract(),
                trace_events=_resource_denied_then_context(),
                include_semantic_review=True,
            )
        )
    except ProviderResponseError as exc:
        assert "invalid" in str(exc).lower()
    else:
        raise AssertionError("invalid provider response must raise ProviderResponseError")
