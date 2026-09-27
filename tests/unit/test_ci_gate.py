"""Deterministic unit coverage for the F-024 CI gate core."""

from __future__ import annotations

import asyncio
import json

import pytest

from agent_audit_api.benchmark_runtime import build_benchmark_runtime
from agent_audit_api.ci_gate import (
    ALL_CASES_MATCHED_CHECK_ID,
    CI_GATE_CHECK_IDS,
    CIGateResult,
    DETECTION_RECALL_CHECK_ID,
    FALSE_POSITIVE_RATE_CHECK_ID,
    POLICY_VIOLATION_ACCURACY_CHECK_ID,
    REPLAY_PASS_RATE_CHECK_ID,
    build_ci_gate_result,
    render_ci_gate_markdown,
    write_ci_gate_artifacts,
)
from tests.benchmark_support import GroundTruthProvider
from tests.retriever_support import make_tfidf_retriever


@pytest.fixture(scope="module")
def deterministic_benchmark():
    """Run the real 24-case chain once with the existing deterministic double."""

    provider = GroundTruthProvider()
    runtime = build_benchmark_runtime(
        provider,
        retriever=make_tfidf_retriever(),
    )
    result = asyncio.run(runtime.run())
    return runtime, result, provider


def test_shared_runtime_runs_fixed_catalog_and_preserves_injected_retriever() -> None:
    provider = GroundTruthProvider()
    retriever = make_tfidf_retriever()
    runtime = build_benchmark_runtime(provider, retriever=retriever)

    assert runtime.retriever is retriever
    assert len(runtime.cases) == 24
    assert len({case.id for case in runtime.cases}) == 24
    assert runtime.runtime_snapshot.retriever_engine == "tfidf"
    assert runtime.runtime_snapshot.provider.startswith("injected:")
    assert runtime.provider_usage_tracker.call_count == 0


def test_fixed_checks_are_derived_from_one_actual_benchmark_result(
    deterministic_benchmark,
) -> None:
    runtime, benchmark, _provider = deterministic_benchmark

    gate = build_ci_gate_result(
        benchmark,
        runtime.contract,
        runtime.runtime_snapshot,
        generated_at="2026-08-27T00:00:00Z",
    )

    assert [check.id for check in gate.checks] == list(CI_GATE_CHECK_IDS)
    assert gate.status == "passed"
    assert gate.failed_check_ids == []
    assert all(check.passed for check in gate.checks)
    assert [check.expected for check in gate.checks] == [True, 1, 0, 1, 1]
    assert len(benchmark.cases) == 24
    assert benchmark.metrics.case_count == 24
    assert benchmark.metrics.matched_case_count == 24


@pytest.mark.parametrize(
    ("metric_name", "bad_value", "check_id"),
    [
        ("matched_case_count", 23, ALL_CASES_MATCHED_CHECK_ID),
        ("detection_recall", 0.5, DETECTION_RECALL_CHECK_ID),
        ("false_positive_rate", 0.1, FALSE_POSITIVE_RATE_CHECK_ID),
        ("policy_violation_accuracy", 0.5, POLICY_VIOLATION_ACCURACY_CHECK_ID),
        ("replay_pass_rate", 0.5, REPLAY_PASS_RATE_CHECK_ID),
    ],
)
def test_any_fixed_check_failure_is_reported_precisely(
    deterministic_benchmark,
    metric_name: str,
    bad_value: float,
    check_id: str,
) -> None:
    runtime, benchmark, _provider = deterministic_benchmark
    bad_metrics = benchmark.metrics.model_copy(update={metric_name: bad_value})
    bad_benchmark = benchmark.model_copy(update={"metrics": bad_metrics})

    gate = build_ci_gate_result(bad_benchmark, runtime.contract, runtime.runtime_snapshot)

    assert gate.status == "failed"
    assert gate.failed_check_ids == [check_id]
    failed = next(check for check in gate.checks if check.id == check_id)
    assert failed.passed is False
    assert failed.actual == bad_value if metric_name != "matched_case_count" else failed.actual is False


def test_expected_case_fields_are_not_read_again_by_gate(
    deterministic_benchmark,
) -> None:
    """Changing catalog expectations alone cannot make the core re-evaluate a gate."""

    runtime, benchmark, _provider = deterministic_benchmark
    altered_cases = [
        case.model_copy(
            update={
                "expected_outcome": "evaluation_failed",
                "expected_finding_categories": ["resource_authorization_bypass"],
                "expected_execution_status": "blocked",
            }
        )
        for case in benchmark.cases
    ]
    benchmark_with_altered_expectations = benchmark.model_copy(update={"cases": altered_cases})

    gate = build_ci_gate_result(
        benchmark_with_altered_expectations,
        runtime.contract,
        runtime.runtime_snapshot,
    )

    assert gate.status == "passed"
    assert gate.failed_check_ids == []
    assert [check.actual for check in gate.checks] == [True, 1, 0, 1, 1]


def test_real_result_contains_finding_categories_replay_outcomes_and_status(
    deterministic_benchmark,
) -> None:
    _runtime, benchmark, _provider = deterministic_benchmark

    actual_categories = {
        category
        for case in benchmark.cases
        for category in case.actual_finding_categories
    }
    assert {
        "resource_authorization_bypass",
        "tool_authorization_bypass",
        "external_sink_policy_violation",
        "tool_business_policy_violation",
    } <= actual_categories

    replay_cases = [case for case in benchmark.cases if case.execution_type == "replay"]
    assert len(replay_cases) == 4
    assert {case.actual_outcome for case in replay_cases} == {"replay_passed"}
    assert {case.actual_execution_status for case in replay_cases} <= {"completed", "blocked"}
    assert {
        case.actual_execution_status
        for case in benchmark.cases
        if case.case_id
        in {"gt_sink_confidential_missing_approval_blocked", "gt_export_over_limit_blocked"}
    } == {"blocked"}


def test_unknown_provider_usage_is_null_and_does_not_fail_gate() -> None:
    provider = GroundTruthProvider(missing_usage_at=1)
    runtime = build_benchmark_runtime(provider, retriever=make_tfidf_retriever())
    benchmark = asyncio.run(runtime.run())

    usage = benchmark.metrics.provider_usage
    assert usage.call_count == len(provider.calls)
    assert usage.call_count > 0
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None
    assert usage.estimated_cost_usd is None

    gate = build_ci_gate_result(benchmark, runtime.contract, runtime.runtime_snapshot)
    assert gate.status == "passed"


def test_artifact_json_round_trips_as_camel_case_result_and_markdown_uses_same_result(
    deterministic_benchmark,
    tmp_path,
) -> None:
    runtime, benchmark, _provider = deterministic_benchmark
    gate = build_ci_gate_result(
        benchmark,
        runtime.contract,
        runtime.runtime_snapshot,
        generated_at="2026-08-27T00:00:00Z",
    )
    json_path, markdown_path = write_ci_gate_artifacts(gate, tmp_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "id",
        "generatedAt",
        "status",
        "contractId",
        "contractVersion",
        "runtimeSnapshot",
        "checks",
        "failedCheckIds",
        "benchmark",
    }
    restored = CIGateResult.model_validate(payload)
    assert restored == gate
    assert payload["runtimeSnapshot"]["retrieverEngine"] == "tfidf"
    assert payload["benchmark"]["metrics"]["providerUsage"]["estimatedCostUsd"] is None
    assert all(
        "actualFindingCategories" in case
        for case in payload["benchmark"]["cases"]
    )

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "- Status: **passed**" in markdown
    assert f"- Contract: `{runtime.contract.id}` (version {runtime.contract.version})" in markdown
    assert "| Provider | injected:GroundTruthProvider |" in markdown
    assert "| estimatedCostUsd | null |" in markdown
    for case in benchmark.cases:
        assert case.case_id in markdown
        for category in case.actual_finding_categories:
            assert category in markdown


def test_markdown_is_a_pure_projection_of_result_not_a_second_gate_evaluation(
    deterministic_benchmark,
) -> None:
    runtime, benchmark, _provider = deterministic_benchmark
    gate = build_ci_gate_result(benchmark, runtime.contract, runtime.runtime_snapshot)
    projected = gate.model_copy(
        update={
            "status": "failed",
            "failed_check_ids": ["synthetic_check"],
            "checks": [
                check.model_copy(update={"actual": "preserved-from-result", "passed": False})
                for check in gate.checks
            ],
        }
    )

    markdown = render_ci_gate_markdown(projected)

    assert "- Status: **failed**" in markdown
    assert "- Failed Check IDs: [\"synthetic_check\"]" in markdown
    assert markdown.count("preserved-from-result") == len(projected.checks)


def test_artifact_writer_preserves_unrelated_output_files_and_only_rewrites_two_fixed_names(
    deterministic_benchmark,
    tmp_path,
) -> None:
    runtime, benchmark, _provider = deterministic_benchmark
    gate = build_ci_gate_result(benchmark, runtime.contract, runtime.runtime_snapshot)
    unrelated = tmp_path / "keep-me.txt"
    unrelated.write_text("unrelated evidence", encoding="utf-8")

    write_ci_gate_artifacts(gate, tmp_path)
    first_unrelated = unrelated.stat().st_mtime_ns
    unrelated.write_text("unrelated evidence", encoding="utf-8")
    second_unrelated = unrelated.stat().st_mtime_ns
    write_ci_gate_artifacts(gate, tmp_path)

    assert unrelated.read_text(encoding="utf-8") == "unrelated evidence"
    assert first_unrelated <= second_unrelated
    assert {path.name for path in tmp_path.iterdir()} == {
        "keep-me.txt",
        "ci-gate.json",
        "ci-gate.md",
    }
