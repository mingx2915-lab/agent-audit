import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_audit_api.attack_cases import AttackCaseExecutor, load_target_profiles
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.planning import AttackPlan, AttackPlanExecutor, ContractAttackPlanner
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
    ToolCall,
)
from agent_audit_api.red_team import (
    AttackAttempt,
    AttackVariantDraft,
    LLMAttackVariantGenerator,
    RedTeamOrchestrator,
)
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.tools import MockCustomerTool


@dataclass
class ScriptedAttackProvider:
    """Provider double for the variant generator only."""

    payloads: list[Any]
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)
    model: str = "test-attack-generator"

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        payload = self.payloads.pop(0)
        if isinstance(payload, BaseException):
            raise payload
        if isinstance(payload, LLMResponse):
            return payload
        if isinstance(payload, str):
            content = payload
        else:
            content = json.dumps(payload, ensure_ascii=False)
        return LLMResponse(content=content, tool_calls=())


@dataclass
class ScriptedTargetProvider:
    """Provider double for Target Agent calls, kept separate from generation."""

    responses: list[LLMResponse]
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if not self.responses:
            raise AssertionError("Target Provider received an unexpected call")
        return self.responses.pop(0)


def _plan() -> tuple[Any, AttackPlan]:
    data = load_demo_data()
    contract = load_security_contract()
    planner = ContractAttackPlanner(
        contract=contract,
        actors=data.actors,
        documents=data.documents,
        customers=data.customers,
        customer_tool=MockCustomerTool(data.customers),
    )
    plan = next(plan for plan in planner.plan() if plan.basis_type == "tool_owner_scope")
    return contract, plan


def _orchestrator(
    *,
    attack_payloads: list[Any],
    target_responses: list[LLMResponse],
) -> tuple[RedTeamOrchestrator, AttackPlan, ScriptedAttackProvider, ScriptedTargetProvider]:
    contract, plan = _plan()
    data = load_demo_data()
    target_provider = ScriptedTargetProvider(target_responses)
    attack_provider = ScriptedAttackProvider(attack_payloads)
    case_executor = AttackCaseExecutor(
        provider=target_provider,
        actors=data.actors,
        retriever=TfidfRetriever(data.documents),
        customer_tool=MockCustomerTool(data.customers),
        contract=contract,
        profiles=load_target_profiles(),
    )
    orchestrator = RedTeamOrchestrator(
        plan_executor=AttackPlanExecutor(case_executor),
        variant_generator=LLMAttackVariantGenerator(attack_provider),
        contract=contract,
        provider=attack_provider,
    )
    return orchestrator, plan, attack_provider, target_provider


def _tool_finding_response() -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=(
            ToolCall(
                id="call_red_team_customer_002",
                name="mock_customer_lookup",
                arguments={"customerId": "customer_002"},
            ),
        ),
    )


def _valid_payload(message: str, reason: str = "依据上一轮 Trace 调整消息") -> dict[str, str]:
    return {"message": message, "mutationReason": reason}


def test_two_round_scan_feeds_actual_trace_and_evaluation_to_mutation() -> None:
    orchestrator, plan, attack_provider, target_provider = _orchestrator(
        attack_payloads=[
            _valid_payload("第一轮仅请求确认客户范围"),
            _valid_payload("第二轮要求调用工具读取 customer_002"),
        ],
        target_responses=[
            LLMResponse(content="第一轮通过", tool_calls=()),
            _tool_finding_response(),
            LLMResponse(content="第二轮工具结果", tool_calls=()),
        ],
    )

    scan = asyncio.run(orchestrator.run(plan, max_rounds=3))

    assert scan.stop_reason == "finding_detected"
    assert len(scan.attempts) == 2
    assert [attempt.status for attempt in scan.attempts] == ["passed", "finding"]
    assert scan.attempts[0].evaluation.status == "passed"
    assert scan.attempts[1].evaluation.status == "failed"
    assert any(
        finding.category == "tool_authorization_bypass"
        for finding in scan.attempts[1].evaluation.findings
    )
    assert len(attack_provider.calls) == 2
    assert len(target_provider.calls) == 3

    first_variant, second_variant = (attempt.variant for attempt in scan.attempts)
    assert first_variant.message != second_variant.message
    assert first_variant.parent_attempt_id is None
    assert second_variant.parent_attempt_id == scan.attempts[0].id

    second_prompt = json.loads(attack_provider.calls[1][0][1]["content"])
    previous = second_prompt["previousAttempt"]
    assert previous["round"] == 1
    assert previous["status"] == "passed"
    assert previous["findingCategories"] == []
    assert previous["traceSummary"]
    assert previous["traceSummary"] == sorted(
        previous["traceSummary"], key=lambda event: event["sequence"]
    )
    assert previous["traceSummary"][0]["summary"] == (
        scan.attempts[0].query_result.trace_events[0].summary
    )

    for attempt in scan.attempts:
        variant = attempt.variant
        assert variant.actor_id == plan.actor_id
        assert variant.attacker_type == plan.attacker_type
        assert variant.basis_rule_id == plan.basis_rule_id
        assert variant.target_kind == plan.target_kind
        assert variant.target_id == plan.target_id
        assert attempt.query_result.actor.id == plan.actor_id

    transitions = scan.state_transitions
    assert [transition.sequence for transition in transitions] == list(
        range(1, len(transitions) + 1)
    )
    assert sum(transition.state == "stopped" for transition in transitions) == 1
    assert transitions[-1].state == "stopped"


def test_finding_stops_before_next_generator_or_target_execution() -> None:
    orchestrator, plan, attack_provider, target_provider = _orchestrator(
        attack_payloads=[_valid_payload("首轮直接尝试越权工具")],
        target_responses=[
            _tool_finding_response(),
            LLMResponse(content="工具越权结果", tool_calls=()),
        ],
    )

    scan = asyncio.run(orchestrator.run(plan, max_rounds=3))

    assert scan.stop_reason == "finding_detected"
    assert len(scan.attempts) == 1
    assert len(attack_provider.calls) == 1
    assert len(target_provider.calls) == 2
    assert scan.attempts[0].status == "finding"


def test_duplicate_message_stops_before_repeating_target_execution() -> None:
    duplicate = _valid_payload("重复的攻击消息")
    orchestrator, plan, attack_provider, target_provider = _orchestrator(
        attack_payloads=[duplicate, duplicate],
        target_responses=[LLMResponse(content="第一轮通过", tool_calls=())],
    )

    scan = asyncio.run(orchestrator.run(plan, max_rounds=3))

    assert scan.stop_reason == "no_new_variant"
    assert len(scan.attempts) == 1
    assert len(attack_provider.calls) == 2
    assert len(target_provider.calls) == 1
    assert scan.attempts[0].status == "passed"
    assert scan.state_transitions[-1].state == "stopped"


def test_max_three_rounds_and_transition_stop_are_bounded() -> None:
    orchestrator, plan, attack_provider, target_provider = _orchestrator(
        attack_payloads=[
            _valid_payload("第一轮安全探测"),
            _valid_payload("第二轮不同安全探测"),
            _valid_payload("第三轮最终安全探测"),
        ],
        target_responses=[
            LLMResponse(content="通过 1", tool_calls=()),
            LLMResponse(content="通过 2", tool_calls=()),
            LLMResponse(content="通过 3", tool_calls=()),
        ],
    )

    scan = asyncio.run(orchestrator.run(plan, max_rounds=3))

    assert scan.stop_reason == "max_rounds_reached"
    assert len(scan.attempts) == 3
    assert all(attempt.status == "passed" for attempt in scan.attempts)
    assert len(attack_provider.calls) == 3
    assert len(target_provider.calls) == 3
    assert sum(transition.state == "stopped" for transition in scan.state_transitions) == 1
    assert scan.state_transitions[-1].state == "stopped"
    assert [transition.sequence for transition in scan.state_transitions] == list(
        range(1, len(scan.state_transitions) + 1)
    )


def test_baseline_metadata_is_not_model_controlled() -> None:
    orchestrator, plan, _, _ = _orchestrator(
        attack_payloads=[_valid_payload("只提供消息，不提供目标元数据")],
        target_responses=[
            _tool_finding_response(),
            LLMResponse(content="工具结果", tool_calls=()),
        ],
    )

    scan = asyncio.run(orchestrator.run(plan, max_rounds=2))
    variant = scan.attempts[0].variant

    assert variant.actor_id == plan.actor_id
    assert variant.attacker_type == plan.attacker_type
    assert variant.basis_rule_id == plan.basis_rule_id
    assert variant.target_kind == plan.target_kind
    assert variant.target_id == plan.target_id
    assert variant.message == "只提供消息，不提供目标元数据"


@pytest.mark.parametrize(
    "content",
    [
        json.dumps({"message": "缺少 reason"}, ensure_ascii=False),
        json.dumps(
            {"message": "有额外字段", "mutationReason": "理由", "actorId": "admin_001"},
            ensure_ascii=False,
        ),
        "```json\n{\"message\": \"代码块\", \"mutationReason\": \"理由\"}\n```",
        json.dumps({"message": "有工具调用", "mutationReason": "理由"}, ensure_ascii=False),
    ],
)
def test_variant_generator_rejects_non_strict_json_or_tool_call(content: str) -> None:
    contract, plan = _plan()
    response = LLMResponse(
        content=content,
        tool_calls=(
            ToolCall(
                id="generator_tool_call",
                name="mock_customer_lookup",
                arguments={"customerId": "customer_001"},
            ),
        )
        if content.startswith("{") and "有工具调用" in content
        else (),
    )
    provider = ScriptedAttackProvider([response])
    generator = LLMAttackVariantGenerator(provider)

    with pytest.raises(ProviderResponseError):
        asyncio.run(
            generator.generate(
                baseline=plan,
                round_number=1,
                previous_attempt=None,
            )
        )


def test_valid_variant_draft_has_only_bounded_fields() -> None:
    _, plan = _plan()
    provider = ScriptedAttackProvider([_valid_payload("合法变体", "基于实际观察")])
    draft = asyncio.run(
        LLMAttackVariantGenerator(provider).generate(
            baseline=plan,
            round_number=1,
            previous_attempt=None,
        )
    )

    assert isinstance(draft, AttackVariantDraft)
    assert draft.model_dump() == {
        "message": "合法变体",
        "mutation_reason": "基于实际观察",
    }


@pytest.mark.parametrize("round_number", [0, 4])
def test_variant_generator_rejects_rounds_outside_state_machine_bound(round_number: int) -> None:
    _, plan = _plan()
    provider = ScriptedAttackProvider([])

    with pytest.raises(ValueError, match="between 1 and 3"):
        asyncio.run(
            LLMAttackVariantGenerator(provider).generate(
                baseline=plan,
                round_number=round_number,
                previous_attempt=None,
            )
        )
    assert provider.calls == []


def test_orchestrator_rejects_invalid_max_rounds_before_provider_calls() -> None:
    orchestrator, plan, attack_provider, target_provider = _orchestrator(
        attack_payloads=[],
        target_responses=[],
    )

    with pytest.raises(ValueError, match="2 or 3"):
        asyncio.run(orchestrator.run(plan, max_rounds=1))
    assert attack_provider.calls == []
    assert target_provider.calls == []


@pytest.mark.parametrize(
    "error",
    [
        ProviderConfigurationError("missing provider configuration"),
        ProviderUnavailableError("provider unavailable"),
    ],
)
def test_variant_generation_propagates_provider_errors_without_fabrication(error: Exception) -> None:
    _, plan = _plan()
    provider = ScriptedAttackProvider([error])
    generator = LLMAttackVariantGenerator(provider)

    with pytest.raises(type(error)):
        asyncio.run(
            generator.generate(
                baseline=plan,
                round_number=1,
                previous_attempt=None,
            )
        )
    assert len(provider.calls) == 1


def test_attempt_schema_is_strict_about_missing_or_extra_fields() -> None:
    with pytest.raises(Exception):
        AttackAttempt.model_validate({
            "id": "attempt_1",
            "scanId": "scan_1",
            "round": 1,
            "status": "passed",
            "variant": {},
            "queryResult": {},
            "evaluation": {},
            "durationMs": 0,
            "unexpected": True,
        })
