import asyncio
from dataclasses import dataclass, field
from typing import Any

from agent_audit_api.attack_cases import AttackCaseExecutor, load_target_profiles
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.planning import AttackPlanExecutor, ContractAttackPlanner
from agent_audit_api.providers.base import LLMResponse, ToolCall
from agent_audit_api.replay import ReplayExecutor
from agent_audit_api.reporting import build_attack_chain_report
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.tools import MockCustomerTool


@dataclass
class ReplayProvider:
    """Return a Tool Call only for an explicitly exposed tool request."""

    answer: str = "报告测试最终回答"
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
                        id=f"call_report_{len(self.calls)}",
                        name="mock_customer_lookup",
                        arguments={"customerId": "customer_002"},
                    ),
                ),
            )
        return LLMResponse(content=self.answer, tool_calls=())


def _replay_fixture(basis_type: str):
    data = load_demo_data()
    contract = load_security_contract()
    provider = ReplayProvider()
    plan = next(
        plan
        for plan in ContractAttackPlanner(
            contract=contract,
            actors=data.actors,
            documents=data.documents,
            customers=data.customers,
            customer_tool=MockCustomerTool(data.customers),
        ).plan()
        if plan.basis_type == basis_type
    )
    case_executor = AttackCaseExecutor(
        provider=provider,
        actors=data.actors,
        retriever=TfidfRetriever(data.documents),
        customer_tool=MockCustomerTool(data.customers),
        contract=contract,
        profiles=load_target_profiles(),
    )
    replay = asyncio.run(
        ReplayExecutor(
            plan_executor=AttackPlanExecutor(case_executor),
            contract=contract,
        ).replay(plan)
    )
    return replay, provider, contract


def _detail_tokens(value: Any) -> list[str]:
    if isinstance(value, dict):
        tokens: list[str] = []
        for key, item in value.items():
            tokens.append(str(key))
            tokens.extend(_detail_tokens(item))
        return tokens
    if isinstance(value, (list, tuple)):
        tokens = []
        for item in value:
            tokens.extend(_detail_tokens(item))
        return tokens
    if isinstance(value, bool):
        return [str(value).lower()]
    if value is None:
        return []
    return [str(value)]


def _assert_markdown_trace(markdown: str, events) -> None:
    for event in events:
        assert str(event.sequence) in markdown
        assert event.type in markdown
        assert event.summary in markdown
        for token in _detail_tokens(event.details):
            assert token in markdown


def _assert_report_sections(markdown: str) -> None:
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


def test_resource_replay_report_contains_real_before_after_chain_and_is_pure() -> None:
    replay, provider, contract = _replay_fixture("resource_owner_scope")
    replay_before_dump = replay.model_dump(by_alias=True)
    calls_before = len(provider.calls)
    contract_before_dump = contract.model_dump(by_alias=True)

    report = build_attack_chain_report(replay)

    assert report.replay == replay
    assert report.replay.model_dump(by_alias=True) == replay_before_dump
    assert replay.model_dump(by_alias=True) == replay_before_dump
    assert len(provider.calls) == calls_before
    assert contract.model_dump(by_alias=True) == contract_before_dump
    assert report.id
    assert report.generated_at.endswith("Z")
    assert report.title
    assert report.executive_summary
    _assert_report_sections(report.markdown)
    _assert_markdown_trace(report.markdown, replay.before.trace_events)
    _assert_markdown_trace(report.markdown, replay.after.trace_events)

    assert replay.before.execution_status == "completed"
    assert replay.after.execution_status == "completed"
    assert replay.plan.target_id in {
        event.details.get("documentId")
        for event in replay.before.trace_events
        if event.type == "authorization"
    }
    assert any(
        replay.plan.target_id in event.details.get("documentIds", [])
        for event in replay.before.trace_events
        if event.type == "sink"
        and event.details.get("sinkType") == "model_context"
    )
    assert all(
        replay.plan.target_id not in event.details.get("documentIds", [])
        for event in replay.after.trace_events
        if event.type == "sink"
        and event.details.get("sinkType") == "model_context"
    )
    assert replay.before.evaluation.status == "failed"
    assert replay.after.evaluation.status == "passed"
    assert replay.plan.basis_rule_id in report.markdown
    for finding in replay.before.evaluation.findings:
        assert finding.category in report.markdown
        for sequence in finding.evidence_sequences:
            assert str(sequence) in report.markdown
        if finding.rule_id is not None:
            assert finding.rule_id in report.markdown


def test_tool_replay_report_preserves_blocked_after_facts_and_tool_trace() -> None:
    replay, provider, _ = _replay_fixture("tool_owner_scope")
    report = build_attack_chain_report(replay)
    before_types = [event.type for event in replay.before.trace_events]
    after_types = [event.type for event in replay.after.trace_events]

    assert report.replay == replay
    _assert_report_sections(report.markdown)
    _assert_markdown_trace(report.markdown, replay.before.trace_events)
    _assert_markdown_trace(report.markdown, replay.after.trace_events)
    assert replay.before.execution_status == "completed"
    assert replay.before.query_result is not None
    assert replay.after.execution_status == "blocked"
    assert replay.after.query_result is None
    assert replay.after.blocked_reason
    assert "tool_call" in before_types
    assert "tool_result" in before_types
    assert "tool_call" not in after_types
    assert "tool_result" not in after_types
    assert replay.before.evaluation.status == "failed"
    assert any(
        finding.category == "tool_authorization_bypass"
        for finding in replay.before.evaluation.findings
    )
    assert replay.after.evaluation.status == "passed"
    assert replay.after.evaluation.findings == []
    assert replay.after.blocked_reason in report.markdown
    assert "未生成模型回答" in report.markdown
    assert replay.plan.basis_rule_id in report.markdown
    assert len(provider.calls) == 3


def test_tampered_expected_and_display_fields_do_not_change_actual_report_conclusion() -> None:
    replay, _, _ = _replay_fixture("resource_owner_scope")
    altered_plan = replay.plan.model_copy(
        update={
            "name": "篡改后的 Plan 展示名称",
            "description": "篡改后的 Plan 展示描述",
            "expected_finding_categories": [],
        }
    )
    altered_replay = replay.model_copy(update={"plan": altered_plan})

    original_report = build_attack_chain_report(replay)
    altered_report = build_attack_chain_report(altered_replay)

    assert altered_report.replay == altered_replay
    assert altered_replay.model_dump(by_alias=True) != replay.model_dump(by_alias=True)
    assert altered_report.replay.before.evaluation == original_report.replay.before.evaluation
    assert altered_report.replay.after.evaluation == original_report.replay.after.evaluation
    assert altered_report.replay.before.evaluation.findings == (
        original_report.replay.before.evaluation.findings
    )
    assert altered_report.replay.status == original_report.replay.status
    assert altered_report.replay.before.evaluation.status == "failed"
    assert altered_report.replay.after.evaluation.status == "passed"
    for finding in original_report.replay.before.evaluation.findings:
        assert finding.category in altered_report.markdown
        for sequence in finding.evidence_sequences:
            assert str(sequence) in altered_report.markdown
