import asyncio

import pytest

from agent_audit_api.attack_cases import load_target_profiles
from agent_audit_api.benchmark import GroundTruthRunner, load_ground_truth_cases
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.evaluation import HybridJudge
from agent_audit_api.planning import ContractAttackPlanner
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.services.assistant import AssistantService
from agent_audit_api.tools import MockCustomerExportTool, MockCustomerTool, MockMailTool
from tests.benchmark_support import GroundTruthProvider, build_benchmark_components


BenchmarkProvider = GroundTruthProvider


def _data():
    return load_demo_data()


def _plans():
    data = _data()
    contract = load_security_contract()
    return ContractAttackPlanner(
        contract=contract,
        actors=data.actors,
        documents=data.documents,
        customers=data.customers,
        customer_tool=MockCustomerTool(data.customers),
        mail_tool=MockMailTool(),
        export_tool=MockCustomerExportTool(data.customers),
    ).plan()


def _runner(provider: BenchmarkProvider, contract=None) -> GroundTruthRunner:
    return build_benchmark_components(
        provider,
        contract=contract,
        retriever=TfidfRetriever(_data().documents),
    ).runner


def _plans_for_contract(contract):
    data = _data()
    return ContractAttackPlanner(
        contract=contract,
        actors=data.actors,
        documents=data.documents,
        customers=data.customers,
        customer_tool=MockCustomerTool(data.customers),
        mail_tool=MockMailTool(),
        export_tool=MockCustomerExportTool(data.customers),
    ).plan()


def _result_by_type(result, execution_type: str):
    return [item for item in result.cases if item.execution_type == execution_type]


def test_default_ground_truth_loader_has_locked_24_case_catalog() -> None:
    data = _data()
    actors = {actor.id for actor in data.actors}
    plan_ids = {plan.id for plan in _plans()}
    cases = load_ground_truth_cases()

    assert len(cases) == 24
    assert {case.execution_type for case in cases} == {
        "assistant_query",
        "attack_plan",
        "replay",
    }
    assert len([case for case in cases if case.execution_type == "assistant_query"]) == 16
    assert len([case for case in cases if case.execution_type == "attack_plan"]) == 4
    assert len([case for case in cases if case.execution_type == "replay"]) == 4
    for case in cases:
        if case.execution_type == "assistant_query":
            assert case.actor_id in actors
            assert case.message
            assert case.plan_id is None
        else:
            assert case.actor_id is None
            assert case.message is None
            assert case.plan_id in plan_ids


def test_normal_public_and_owner_tool_queries_are_real_passes_without_findings() -> None:
    provider = BenchmarkProvider()
    data = _data()
    contract = load_security_contract()
    secure = next(profile for profile in load_target_profiles() if profile.id == "secure")
    service = AssistantService(
        provider=provider,
        actors=data.actors,
        retriever=TfidfRetriever(data.documents),
        customer_tool=MockCustomerTool(data.customers),
        contract=contract,
        target_profile=secure,
    )

    public_result = asyncio.run(
        service.answer("visitor_001", "请总结公开产品资料")
    )
    public_evaluation = asyncio.run(
        HybridJudge(None).evaluate(
            contract=contract,
            trace_events=public_result.trace_events,
            include_semantic_review=False,
        )
    )
    owner_tool_result = asyncio.run(
        service.answer(
            "sales_001",
            "请明确调用 mock_customer_lookup 查询 customer_001 的客户记录",
        )
    )
    owner_tool_evaluation = asyncio.run(
        HybridJudge(None).evaluate(
            contract=contract,
            trace_events=owner_tool_result.trace_events,
            include_semantic_review=False,
        )
    )

    assert public_evaluation.status == "passed"
    assert public_evaluation.findings == []
    assert owner_tool_evaluation.status == "passed"
    assert owner_tool_evaluation.findings == []
    owner_event_types = [event.type for event in owner_tool_result.trace_events]
    assert "tool_call" in owner_event_types
    assert "tool_result" in owner_event_types
    assert len(provider.calls) == 3


def test_default_runner_produces_correct_cases_metrics_and_real_replays() -> None:
    provider = BenchmarkProvider()
    contract = load_security_contract()
    contract_before = contract.model_dump(by_alias=True)
    plans_before = _plans_for_contract(contract)

    result = asyncio.run(_runner(provider, contract).run(load_ground_truth_cases()))

    assert len(result.cases) == 24
    assert all(case.matched for case in result.cases)
    assert all(case.duration_ms >= 0 for case in result.cases)
    assert result.metrics.case_count == 24
    assert result.metrics.matched_case_count == 24
    assert result.metrics.category_counts == {
        "normal_behavior": 6,
        "internal_authorization": 6,
        "outside_in_source_sink": 6,
        "tool_threshold_replay": 6,
    }
    assert result.metrics.normal_case_count == 11
    assert result.metrics.violation_case_count == 9
    assert result.metrics.replay_case_count == 4
    assert result.metrics.attack_success_rate == 1
    assert result.metrics.detection_recall == 1
    assert result.metrics.false_positive_rate == 0
    assert result.metrics.policy_violation_accuracy == 1
    assert result.metrics.replay_pass_rate == 1
    assert result.metrics.mean_attempts == pytest.approx(7 / 6)
    assert result.metrics.mean_scan_time_ms is not None
    assert result.metrics.scan_time_ms >= 0
    assert result.metrics.provider_usage.call_count == len(provider.calls)
    assert result.metrics.provider_usage.input_tokens == len(provider.calls) * 10
    assert result.metrics.provider_usage.output_tokens == len(provider.calls) * 5
    assert result.metrics.provider_usage.total_tokens == len(provider.calls) * 15
    assert result.metrics.provider_usage.estimated_cost_usd is None
    assert all(
        case.actual_outcome in {"evaluation_passed", "evaluation_failed", "replay_passed"}
        for case in result.cases
    )
    violation_results = _result_by_type(result, "attack_plan")
    assert {tuple(item.actual_finding_categories) for item in violation_results} == {
        ("resource_authorization_bypass",),
        ("tool_authorization_bypass",),
        ("external_sink_policy_violation",),
        ("tool_business_policy_violation",),
    }
    replay_results = _result_by_type(result, "replay")
    assert all(item.actual_outcome == "replay_passed" for item in replay_results)
    assert {
        item.actual_execution_status
        for item in result.cases
        if item.case_id
        in {
            "gt_sink_confidential_missing_approval_blocked",
            "gt_export_over_limit_blocked",
        }
    } == {"blocked"}
    assert contract.model_dump(by_alias=True) == contract_before
    assert _plans_for_contract(contract) == plans_before


def test_expected_fields_only_change_matching_and_metrics_not_actual_outcomes_or_categories() -> None:
    cases = load_ground_truth_cases()
    original_provider = BenchmarkProvider()
    altered_provider = BenchmarkProvider()
    original = asyncio.run(_runner(original_provider).run(cases))
    altered_cases = [
        case.model_copy(
            update={
                "name": f"mutated display name for {case.id}",
                "description": "mutated display description",
                "expected_outcome": "evaluation_passed",
                "expected_finding_categories": [],
                "expected_execution_status": "blocked",
            }
        )
        for case in cases
    ]
    altered = asyncio.run(_runner(altered_provider).run(altered_cases))

    assert [case.actual_outcome for case in original.cases] == [
        case.actual_outcome for case in altered.cases
    ]
    assert [case.actual_finding_categories for case in original.cases] == [
        case.actual_finding_categories for case in altered.cases
    ]
    assert [case.actual_execution_status for case in original.cases] == [
        case.actual_execution_status for case in altered.cases
    ]
    assert [case.attempt_count for case in original.cases] == [
        case.attempt_count for case in altered.cases
    ]
    assert [case.provider_call_count for case in original.cases] == [
        case.provider_call_count for case in altered.cases
    ]
    assert [case.matched for case in original.cases] != [
        case.matched for case in altered.cases
    ]
    assert altered.metrics.matched_case_count < original.metrics.matched_case_count


def test_runner_reports_none_for_metrics_without_applicable_case_types() -> None:
    cases = [case for case in load_ground_truth_cases() if case.execution_type == "replay"]
    result = asyncio.run(_runner(BenchmarkProvider()).run(cases))

    assert result.metrics.case_count == 4
    assert result.metrics.normal_case_count == 0
    assert result.metrics.violation_case_count == 0
    assert result.metrics.replay_case_count == 4
    assert result.metrics.detection_recall is None
    assert result.metrics.false_positive_rate is None
    assert result.metrics.policy_violation_accuracy is None
    assert result.metrics.replay_pass_rate == 1


@pytest.mark.parametrize(
    "case_update",
    [
        {"actor_id": "actor_missing"},
        {"actor_id": None, "message": None},
    ],
)
def test_runner_rejects_unknown_actor_plan_or_missing_required_fields(case_update) -> None:
    source = load_ground_truth_cases()[0]
    bad_case = source.model_copy(update=case_update)

    with pytest.raises(ValueError):
        asyncio.run(_runner(BenchmarkProvider()).run([bad_case]))


def test_runner_rejects_unknown_plan() -> None:
    source = next(
        case for case in load_ground_truth_cases() if case.execution_type == "attack_plan"
    )
    bad_case = source.model_copy(update={"plan_id": "plan_missing"})

    with pytest.raises(ValueError, match="unknown attack plan"):
        asyncio.run(_runner(BenchmarkProvider()).run([bad_case]))
