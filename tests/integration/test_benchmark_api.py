from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import agent_audit_api.main as main_module
from agent_audit_api.benchmark import load_ground_truth_cases
from agent_audit_api.main import create_app
from tests.retriever_support import make_tfidf_retriever
from tests.benchmark_support import GroundTruthProvider


BenchmarkProvider = GroundTruthProvider


def _demo_json_snapshot() -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted(Path("data/demo").glob("*.json"))
    }


def _client(provider) -> TestClient:
    return TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    )


def _case_result(result: dict[str, Any], execution_type: str) -> list[dict[str, Any]]:
    return [case for case in result["cases"] if case["executionType"] == execution_type]


def test_ground_truth_case_list_has_exact_shape_and_traceable_references() -> None:
    with _client(BenchmarkProvider()) as client:
        response = client.get("/api/ground-truth-cases")
        plans = client.get("/api/attack-plans").json()
        actors = client.get("/api/demo/actors").json()

    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 24
    assert all(
        set(case)
        == {
            "id",
            "name",
            "description",
            "category",
            "executionType",
            "actorId",
            "message",
            "targetProfileId",
            "planId",
            "expectedOutcome",
            "expectedFindingCategories",
            "expectedExecutionStatus",
        }
        for case in cases
    )
    assert len([case for case in cases if case["executionType"] == "assistant_query"]) == 16
    assert len([case for case in cases if case["executionType"] == "attack_plan"]) == 4
    assert len([case for case in cases if case["executionType"] == "replay"]) == 4
    assert {
        category: sum(case["category"] == category for case in cases)
        for category in (
            "normal_behavior",
            "internal_authorization",
            "outside_in_source_sink",
            "tool_threshold_replay",
        )
    } == {
        "normal_behavior": 6,
        "internal_authorization": 6,
        "outside_in_source_sink": 6,
        "tool_threshold_replay": 6,
    }
    actor_ids = {actor["id"] for actor in actors}
    plan_ids = {plan["id"] for plan in plans}
    for case in cases:
        if case["executionType"] == "assistant_query":
            assert case["actorId"] in actor_ids
            assert case["message"]
            assert case["planId"] is None
            assert case["targetProfileId"]
        else:
            assert case["actorId"] is None
            assert case["message"] is None
            assert case["targetProfileId"] is None
            assert case["planId"] in plan_ids


def test_benchmark_run_returns_correct_metrics_real_findings_and_replays() -> None:
    provider = BenchmarkProvider()
    data_before = _demo_json_snapshot()
    with _client(provider) as client:
        contract_before = client.get("/api/security-contract").json()
        plans_before = client.get("/api/attack-plans").json()
        response = client.post("/api/benchmarks/run")
        contract_after = client.get("/api/security-contract").json()
        plans_after = client.get("/api/attack-plans").json()

    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"id", "cases", "metrics"}
    assert len(result["cases"]) == 24
    assert all(
        set(case)
        == {
            "caseId",
            "name",
            "category",
            "executionType",
            "expectedOutcome",
            "actualOutcome",
            "expectedFindingCategories",
            "actualFindingCategories",
            "expectedExecutionStatus",
            "actualExecutionStatus",
            "matched",
            "attemptCount",
            "providerCallCount",
            "durationMs",
        }
        for case in result["cases"]
    )
    assert all(case["matched"] is True for case in result["cases"])
    assert all(case["durationMs"] >= 0 for case in result["cases"])
    metrics = result["metrics"]
    assert set(metrics) == {
        "caseCount",
        "matchedCaseCount",
        "categoryCounts",
        "normalCaseCount",
        "violationCaseCount",
        "replayCaseCount",
        "attackSuccessRate",
        "detectionRecall",
        "falsePositiveRate",
        "policyViolationAccuracy",
        "meanAttempts",
        "meanScanTimeMs",
        "replayPassRate",
        "providerUsage",
        "scanTimeMs",
    }
    assert metrics["caseCount"] == 24
    assert metrics["matchedCaseCount"] == 24
    assert metrics["categoryCounts"] == {
        "normal_behavior": 6,
        "internal_authorization": 6,
        "outside_in_source_sink": 6,
        "tool_threshold_replay": 6,
    }
    assert metrics["normalCaseCount"] == 11
    assert metrics["violationCaseCount"] == 9
    assert metrics["replayCaseCount"] == 4
    assert metrics["attackSuccessRate"] == 1
    assert metrics["detectionRecall"] == 1
    assert metrics["falsePositiveRate"] == 0
    assert metrics["policyViolationAccuracy"] == 1
    assert metrics["meanAttempts"] == pytest.approx(7 / 6)
    assert metrics["meanScanTimeMs"] >= 0
    assert metrics["replayPassRate"] == 1
    assert metrics["scanTimeMs"] >= 0

    provider_usage = metrics["providerUsage"]
    assert set(provider_usage) == {
        "callCount",
        "inputTokens",
        "outputTokens",
        "totalTokens",
        "estimatedCostUsd",
    }
    assert provider_usage["callCount"] == len(provider.calls)
    assert provider_usage["inputTokens"] == len(provider.calls) * 10
    assert provider_usage["outputTokens"] == len(provider.calls) * 5
    assert provider_usage["totalTokens"] == len(provider.calls) * 15
    assert provider_usage["estimatedCostUsd"] is None

    normal = [
        case
        for case in result["cases"]
        if case["executionType"] != "replay"
        and case["expectedOutcome"] == "evaluation_passed"
        and not case["expectedFindingCategories"]
    ]
    violations = [
        case
        for case in result["cases"]
        if case["executionType"] != "replay"
        and case["expectedOutcome"] == "evaluation_failed"
        and case["expectedFindingCategories"]
    ]
    replays = _case_result(result, "replay")
    assert all(case["actualOutcome"] == "evaluation_passed" for case in normal)
    assert {
        tuple(case["actualFindingCategories"])
        for case in violations
    } == {
        ("resource_authorization_bypass",),
        ("tool_authorization_bypass",),
        ("external_sink_policy_violation",),
        ("tool_business_policy_violation",),
    }
    assert all(case["actualOutcome"] == "replay_passed" for case in replays)
    assert {
        case["actualExecutionStatus"]
        for case in result["cases"]
        if case["caseId"]
        in {"gt_sink_confidential_missing_approval_blocked", "gt_export_over_limit_blocked"}
    } == {"blocked"}

    # Resource requests may expose tools opportunistically, but this provider
    # emits a Tool Call only when the user message explicitly names that tool.
    for request in provider.calls:
        response = request["response"]
        user_text = "\n".join(
            str(message.get("content") or "")
            for message in request["messages"]
            if message.get("role") == "user"
        )
        for tool_call in response.tool_calls:
            assert tool_call.name in user_text
    assert sum(case["providerCallCount"] for case in result["cases"]) == len(provider.calls)
    assert contract_after == contract_before
    assert plans_after == plans_before
    assert _demo_json_snapshot() == data_before


def test_benchmark_usage_is_unknown_when_any_provider_call_lacks_usage() -> None:
    provider = BenchmarkProvider(missing_usage_at=1)

    with _client(provider) as client:
        response = client.post("/api/benchmarks/run")

    assert response.status_code == 200
    result = response.json()
    usage = result["metrics"]["providerUsage"]
    assert usage["callCount"] == len(provider.calls)
    assert usage["callCount"] > 0
    assert usage["inputTokens"] is None
    assert usage["outputTokens"] is None
    assert usage["totalTokens"] is None
    assert usage["estimatedCostUsd"] is None
    assert sum(case["providerCallCount"] for case in result["cases"]) == len(provider.calls)


@pytest.mark.parametrize("invalid_kind", ["actor", "plan", "fields"])
def test_benchmark_api_returns_422_for_unknown_references_or_missing_fields(
    monkeypatch,
    invalid_kind: str,
) -> None:
    cases = load_ground_truth_cases()
    if invalid_kind == "actor":
        source = next(case for case in cases if case.execution_type == "assistant_query")
        bad_case = source.model_copy(update={"actor_id": "actor_missing"})
    elif invalid_kind == "plan":
        source = next(case for case in cases if case.execution_type == "attack_plan")
        bad_case = source.model_copy(update={"plan_id": "plan_missing"})
    else:
        source = next(case for case in cases if case.execution_type == "assistant_query")
        bad_case = source.model_copy(update={"actor_id": None, "message": None})

    monkeypatch.setattr(main_module, "load_ground_truth_cases", lambda: (bad_case,))
    provider = BenchmarkProvider()
    with TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    ) as client:
        response = client.post("/api/benchmarks/run")

    assert response.status_code == 422
    assert provider.calls == []
