"""F-025 fixed Acceptance Runner, projection and actual-evidence tests."""

from __future__ import annotations

import asyncio

import pytest

from agent_audit_api.acceptance import AcceptanceRunner, build_acceptance_comparison, build_acceptance_summary
from agent_audit_api.attack_cases import load_target_profiles
from agent_audit_api.benchmark import load_ground_truth_cases
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.providers.base import LLMResponse
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from tests.acceptance_support import AcceptanceProvider, make_acceptance_embedding_retriever


def _run(*, provider: AcceptanceProvider | None = None, cases=None):
    data = load_demo_data()
    active_provider = provider or AcceptanceProvider()
    return asyncio.run(
        AcceptanceRunner(
            provider=active_provider,
            attack_provider=active_provider,
            retriever=make_acceptance_embedding_retriever(),
            tfidf_retriever=TfidfRetriever(data.documents),
            contract=load_security_contract(),
            profiles=load_target_profiles(),
            demo_data=data,
            cases=cases,
        ).run()
    )


def test_fixed_runner_executes_every_required_real_child_chain() -> None:
    run = _run()

    assert run.status == "completed"
    assert run.verdict == run.ci_gate.status
    assert len(run.plan_snapshots) == 4
    assert len(run.profile_snapshots) == 4

    assert run.provider_readiness.status == "ready"
    assert [probe.id for probe in run.provider_readiness.target_provider.probes] == [
        "target.connectivity",
        "target.tool_calling",
    ]
    assert [probe.id for probe in run.provider_readiness.attack_provider.probes] == [
        "attack.connectivity",
        "attack.strict_json",
    ]
    assert len(run.provider_readiness.plan_compatibility) == 4

    retrieval = run.retrieval_evaluation
    assert retrieval.selected_engine == "embedding"
    assert retrieval.metrics.case_count == 6
    assert len(retrieval.cases) == 6
    assert all(case.tfidf_results and case.embedding_results for case in retrieval.cases)

    assert len(run.differential_audits) == 2
    assert all(
        audit.target_profile_id == audit.task.default_target_profile_id
        for audit in run.differential_audits
    )
    assert {audit.task.task_type for audit in run.differential_audits} == {
        "resource_access",
        "tool_access",
    }

    benchmark = run.ci_gate.benchmark
    assert len(benchmark.cases) == 24
    assert benchmark.metrics.case_count == 24
    assert set(benchmark.metrics.category_counts.values()) == {6}
    assert len(run.ci_gate.checks) == 5
    assert run.ci_gate.status in {"passed", "failed"}
    assert run.ci_gate.failed_check_ids == [
        check.id for check in run.ci_gate.checks if not check.passed
    ]

    assert run.guided_scan.plan_id == "plan_sink_confidential_external"
    assert run.guided_scan.attempts
    assert run.guided_scan.attempts[-1].evaluation.findings
    assert any(
        finding.category == "external_sink_policy_violation"
        for attempt in run.guided_scan.attempts
        for finding in attempt.evaluation.findings
    )
    assert run.guided_replay.plan.id == run.guided_scan.plan_id
    assert run.guided_replay.before.evaluation.status == "failed"
    assert run.guided_replay.after.evaluation.status == "passed"
    assert run.guided_replay.after.execution_status == "blocked"
    trace_types = {
        event.type
        for event in run.guided_scan.attempts[-1].query_result.trace_events
    }
    assert {"source", "retrieval", "authorization", "tool_call", "sink"} <= trace_types


def test_readiness_is_evidence_and_verdict_is_exactly_ci_gate_status() -> None:
    class PartialReadinessProvider(AcceptanceProvider):
        async def complete(self, messages, tools=None) -> LLMResponse:
            if self._contains(messages, "Connectivity probe"):
                # A structured readiness failure still allows the fixed
                # Acceptance children to run and must not become a Finding.
                return self._record(
                    messages,
                    tools,
                    LLMResponse(content="", usage=self._usage(len(self.calls) + 1)),
                )
            return await super().complete(messages, tools=tools)

    run = _run(provider=PartialReadinessProvider())

    assert run.provider_readiness.status == "partial"
    assert run.provider_readiness.target_provider.status == "partial"
    assert run.provider_readiness.attack_provider.status == "partial"
    assert run.verdict == run.ci_gate.status
    assert run.verdict == "passed"
    assert all(
        finding.category != "external_sink_policy_violation"
        or finding.rule_id is not None
        for attempt in run.guided_scan.attempts
        for finding in attempt.evaluation.findings
    )


def test_finding_categories_and_count_are_derived_from_actual_child_evidence() -> None:
    run = _run()
    categories = []
    finding_count = 0
    for audit in run.differential_audits:
        for row in audit.rows:
            finding_count += len(row.findings)
            categories.extend(finding.category for finding in row.findings)
    for case in run.ci_gate.benchmark.cases:
        finding_count += len(case.actual_finding_categories)
        categories.extend(case.actual_finding_categories)
    for attempt in run.guided_scan.attempts:
        finding_count += len(attempt.evaluation.findings)
        categories.extend(finding.category for finding in attempt.evaluation.findings)
    for attempt in (run.guided_replay.before, run.guided_replay.after):
        finding_count += len(attempt.evaluation.findings)
        categories.extend(finding.category for finding in attempt.evaluation.findings)

    assert run.finding_count == finding_count
    assert set(run.finding_categories) == set(categories)
    assert len(run.finding_categories) == len(set(run.finding_categories))


def test_expected_case_fields_do_not_change_actual_findings_or_outcomes() -> None:
    original_cases = load_ground_truth_cases()
    altered_cases = tuple(
        case.model_copy(
            update={
                "name": f"display-only-{case.id}",
                "expected_outcome": "evaluation_passed",
                "expected_finding_categories": [],
                "expected_execution_status": "completed",
            }
        )
        for case in original_cases
    )
    original = _run(cases=original_cases)
    altered = _run(cases=altered_cases)

    original_actual = [
        (
            case.actual_outcome,
            case.actual_finding_categories,
            case.actual_execution_status,
        )
        for case in original.ci_gate.benchmark.cases
    ]
    altered_actual = [
        (
            case.actual_outcome,
            case.actual_finding_categories,
            case.actual_execution_status,
        )
        for case in altered.ci_gate.benchmark.cases
    ]
    assert altered_actual == original_actual
    assert altered.finding_categories == original.finding_categories
    assert altered.finding_count == original.finding_count
    def differential_actual(audit):
        return [
            (
                row.actor.id,
                row.expected_decision,
                row.actual_decision,
                row.matched,
                row.execution_status,
                tuple(finding.category for finding in row.findings),
            )
            for row in audit.rows
        ]

    assert [differential_actual(audit) for audit in altered.differential_audits] == [
        differential_actual(audit) for audit in original.differential_audits
    ]


def test_runner_snapshots_mutable_contract_profiles_and_plans_before_provider_calls() -> None:
    contract = load_security_contract()
    profiles = list(load_target_profiles())

    class MutatingProvider(AcceptanceProvider):
        def __init__(self) -> None:
            super().__init__()
            self._contract = contract
            self._profiles = profiles
            self._mutated = False

        async def complete(self, messages, tools=None) -> LLMResponse:
            if not self._mutated:
                self._mutated = True
                self._contract.name = "mutated after snapshot"
                self._profiles[0].name = "mutated after snapshot"
            return await super().complete(messages, tools=tools)

    run = asyncio.run(
        AcceptanceRunner(
            provider=MutatingProvider(),
            retriever=make_acceptance_embedding_retriever(),
            tfidf_retriever=TfidfRetriever(load_demo_data().documents),
            contract=contract,
            profiles=profiles,
            demo_data=load_demo_data(),
        ).run()
    )

    assert run.contract_snapshot.name == load_security_contract().name
    assert run.profile_snapshots[0].name == "Secure Target Agent"
    assert [plan.id for plan in run.plan_snapshots] == [
        "plan_resource_customer_owner",
        "plan_sink_confidential_external",
        "plan_tool_customer_export_limit",
        "plan_tool_customer_owner_read",
    ]


def test_summary_and_first_comparison_have_no_fabricated_baseline() -> None:
    run = _run()
    summary = build_acceptance_summary(run)
    comparison = build_acceptance_comparison(run, None)

    assert summary.id == run.id
    assert summary.contract_id == run.contract_snapshot.id
    assert summary.gate_status == run.ci_gate.status
    assert summary.benchmark_case_count == 24
    assert comparison.previous is None
    assert comparison.gate_metric_deltas == []
    assert comparison.added_failed_check_ids == []
    assert comparison.resolved_failed_check_ids == []
    assert comparison.added_mismatched_case_ids == []
    assert comparison.resolved_mismatched_case_ids == []
    assert comparison.added_finding_categories == []
    assert comparison.resolved_finding_categories == []


def test_second_comparison_reports_full_metric_and_evidence_deltas() -> None:
    baseline = _run()
    previous = baseline.model_copy(
        deep=True,
        update={
            "id": "acceptance_previous",
            "verdict": "failed",
            "finding_categories": [
                "resource_authorization_bypass",
                "tool_authorization_bypass",
            ],
            "provider_readiness": baseline.provider_readiness.model_copy(
                deep=True,
                update={"status": "ready"},
            ),
        },
    )
    previous_cases = list(previous.ci_gate.benchmark.cases)
    previous_cases[0] = previous_cases[0].model_copy(update={"matched": False})
    previous_cases[1] = previous_cases[1].model_copy(update={"matched": False})
    previous_benchmark = previous.ci_gate.benchmark.model_copy(
        deep=True,
        update={
            "cases": previous_cases,
            "metrics": previous.ci_gate.benchmark.metrics.model_copy(
                update={
                    "matched_case_count": 22,
                    "detection_recall": 1.0,
                    "false_positive_rate": 0.0,
                    "policy_violation_accuracy": 0.8,
                    "replay_pass_rate": 0.8,
                }
            ),
        },
    )
    previous_gate = previous.ci_gate.model_copy(
        deep=True,
        update={
            "status": "failed",
            "failed_check_ids": [
                "policy_violation_accuracy",
                "replay_pass_rate",
            ],
            "benchmark": previous_benchmark,
        },
    )
    previous.ci_gate = previous_gate

    current = baseline.model_copy(
        deep=True,
        update={
            "id": "acceptance_current",
            "verdict": "failed",
            "contract_snapshot": baseline.contract_snapshot.model_copy(
                update={"name": "changed Contract snapshot", "version": 2}
            ),
            "runtime_snapshot": baseline.runtime_snapshot.model_copy(
                update={"model": "changed-test-model"}
            ),
            "provider_readiness": baseline.provider_readiness.model_copy(
                deep=True,
                update={"status": "partial"},
            ),
            "finding_categories": [
                "tool_authorization_bypass",
                "external_sink_policy_violation",
            ],
        },
    )
    current_cases = list(current.ci_gate.benchmark.cases)
    current_cases[0] = current_cases[0].model_copy(update={"matched": True})
    current_cases[1] = current_cases[1].model_copy(update={"matched": False})
    current_cases[2] = current_cases[2].model_copy(update={"matched": False})
    current_metrics = current.ci_gate.benchmark.metrics.model_copy(
        update={
            "matched_case_count": 22,
            "detection_recall": 0.5,
            "false_positive_rate": 0.1,
            "policy_violation_accuracy": 0.6,
            "replay_pass_rate": 0.55,
        }
    )
    current_benchmark = current.ci_gate.benchmark.model_copy(
        deep=True,
        update={"cases": current_cases, "metrics": current_metrics},
    )
    current_checks = []
    actual_values = {
        "all_cases_matched": False,
        "detection_recall": 0.5,
        "false_positive_rate": 0.1,
        "policy_violation_accuracy": 0.6,
        "replay_pass_rate": 0.55,
    }
    for check in current.ci_gate.checks:
        current_checks.append(
            check.model_copy(
                update={
                    "actual": actual_values[check.id],
                    "passed": check.id
                    not in {"all_cases_matched", "detection_recall", "false_positive_rate"},
                }
            )
        )
    current.ci_gate = current.ci_gate.model_copy(
        deep=True,
        update={
            "status": "failed",
            "checks": current_checks,
            "failed_check_ids": [
                "all_cases_matched",
                "detection_recall",
                "false_positive_rate",
            ],
            "benchmark": current_benchmark,
        },
    )

    comparison = build_acceptance_comparison(current, previous)

    assert comparison.previous is not None
    assert comparison.contract_changed is True
    assert comparison.runtime_changed is True
    assert comparison.readiness_changed is True
    assert comparison.gate_status_changed is False
    assert [delta.id for delta in comparison.gate_metric_deltas] == [
        "all_cases_matched",
        "detection_recall",
        "false_positive_rate",
        "policy_violation_accuracy",
        "replay_pass_rate",
    ]
    deltas = {delta.id: delta for delta in comparison.gate_metric_deltas}
    assert deltas["all_cases_matched"].delta == -1.0
    assert deltas["detection_recall"].delta == -0.5
    assert deltas["false_positive_rate"].delta == 0.1
    assert deltas["policy_violation_accuracy"].delta == pytest.approx(-0.2)
    assert deltas["replay_pass_rate"].delta == pytest.approx(-0.25)
    assert comparison.added_failed_check_ids == [
        "all_cases_matched",
        "detection_recall",
        "false_positive_rate",
    ]
    assert comparison.resolved_failed_check_ids == [
        "policy_violation_accuracy",
        "replay_pass_rate",
    ]
    assert comparison.added_mismatched_case_ids == [current_cases[2].case_id]
    assert comparison.resolved_mismatched_case_ids == [previous_cases[0].case_id]
    assert comparison.added_finding_categories == ["external_sink_policy_violation"]
    assert comparison.resolved_finding_categories == ["resource_authorization_bypass"]
