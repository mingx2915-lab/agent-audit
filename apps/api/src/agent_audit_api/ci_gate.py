"""Deterministic CI gate results and acceptance artifacts.

The gate is deliberately small: it evaluates five fixed checks from one
completed :class:`~agent_audit_api.benchmark.BenchmarkResult`.  Rendering and
writing only consume the resulting DTO; they never execute a benchmark or
re-evaluate a case.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .benchmark import BenchmarkResult
from .history import AuditRuntimeSnapshot
from .schemas import CamelModel
from .security_contract import SecurityContract


CIGateStatus = Literal["passed", "failed"]

ALL_CASES_MATCHED_CHECK_ID = "all_cases_matched"
DETECTION_RECALL_CHECK_ID = "detection_recall"
FALSE_POSITIVE_RATE_CHECK_ID = "false_positive_rate"
POLICY_VIOLATION_ACCURACY_CHECK_ID = "policy_violation_accuracy"
REPLAY_PASS_RATE_CHECK_ID = "replay_pass_rate"

CI_GATE_CHECK_IDS: tuple[str, ...] = (
    ALL_CASES_MATCHED_CHECK_ID,
    DETECTION_RECALL_CHECK_ID,
    FALSE_POSITIVE_RATE_CHECK_ID,
    POLICY_VIOLATION_ACCURACY_CHECK_ID,
    REPLAY_PASS_RATE_CHECK_ID,
)

class CIGateCheck(CamelModel):
    """One fixed CI gate check and the value observed in the benchmark."""

    id: str
    actual: Any
    expected: Any
    passed: bool


class CIGateResult(CamelModel):
    """Machine-readable result for one completed fixed benchmark gate."""

    id: str
    generated_at: str
    status: CIGateStatus
    contract_id: str
    contract_version: int
    runtime_snapshot: AuditRuntimeSnapshot
    checks: list[CIGateCheck]
    failed_check_ids: list[str]
    benchmark: BenchmarkResult


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _all_cases_matched(benchmark: BenchmarkResult) -> bool:
    """Return whether every executed case has a matching actual result.

    The case-level ``matched`` values and the result-level counts are both
    actual benchmark evidence.  Expected case fields are intentionally not
    read here.
    """

    case_count = len(benchmark.cases)
    return (
        case_count > 0
        and benchmark.metrics.case_count == case_count
        and benchmark.metrics.matched_case_count == case_count
        and all(case.matched for case in benchmark.cases)
    )


def _fixed_checks(benchmark: BenchmarkResult) -> list[CIGateCheck]:
    """Build the five checks in their stable output order."""

    actual_all_matched = _all_cases_matched(benchmark)
    actual_detection_recall = benchmark.metrics.detection_recall
    actual_false_positive_rate = benchmark.metrics.false_positive_rate
    actual_policy_accuracy = benchmark.metrics.policy_violation_accuracy
    actual_replay_pass_rate = benchmark.metrics.replay_pass_rate
    return [
        CIGateCheck(
            id=ALL_CASES_MATCHED_CHECK_ID,
            actual=actual_all_matched,
            expected=True,
            passed=actual_all_matched,
        ),
        CIGateCheck(
            id=DETECTION_RECALL_CHECK_ID,
            actual=actual_detection_recall,
            expected=1,
            passed=actual_detection_recall == 1,
        ),
        CIGateCheck(
            id=FALSE_POSITIVE_RATE_CHECK_ID,
            actual=actual_false_positive_rate,
            expected=0,
            passed=actual_false_positive_rate == 0,
        ),
        CIGateCheck(
            id=POLICY_VIOLATION_ACCURACY_CHECK_ID,
            actual=actual_policy_accuracy,
            expected=1,
            passed=actual_policy_accuracy == 1,
        ),
        CIGateCheck(
            id=REPLAY_PASS_RATE_CHECK_ID,
            actual=actual_replay_pass_rate,
            expected=1,
            passed=actual_replay_pass_rate == 1,
        ),
    ]


def build_ci_gate_result(
    benchmark: BenchmarkResult,
    contract: SecurityContract,
    runtime_snapshot: AuditRuntimeSnapshot,
    *,
    generated_at: str | None = None,
) -> CIGateResult:
    """Build a gate DTO from one completed benchmark and runtime snapshot.

    The caller supplies the active Contract and runtime snapshot so the
    artifact records exactly which configuration produced the benchmark.  No
    configurable threshold, case catalog, or target is accepted here: the
    checks and their expected values are fixed constants above.
    """

    checks = _fixed_checks(benchmark)
    failed_check_ids = [check.id for check in checks if not check.passed]
    return CIGateResult(
        id=f"ci_gate_{uuid.uuid4().hex[:12]}",
        generated_at=generated_at if generated_at is not None else _utc_now(),
        status="passed" if not failed_check_ids else "failed",
        contract_id=contract.id,
        contract_version=contract.version,
        runtime_snapshot=runtime_snapshot,
        checks=checks,
        failed_check_ids=failed_check_ids,
        benchmark=benchmark,
    )


def _markdown_cell(value: Any) -> str:
    """Format one DTO value without changing its semantic value."""

    if value is None:
        text = "null"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (list, tuple, dict)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_ci_gate_markdown(result: CIGateResult) -> str:
    """Render Markdown solely from the supplied :class:`CIGateResult`."""

    runtime = result.runtime_snapshot
    metrics = result.benchmark.metrics
    usage = metrics.provider_usage
    lines = [
        "# 知盾 AgentAudit CI Gate",
        "",
        f"- Status: **{result.status}**",
        f"- Gate ID: `{result.id}`",
        f"- Generated At: `{result.generated_at}`",
        f"- Contract: `{result.contract_id}` (version {result.contract_version})",
        "",
        "## Runtime",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Provider | {_markdown_cell(runtime.provider)} |",
        f"| Model | {_markdown_cell(runtime.model)} |",
        f"| Retriever | {_markdown_cell(runtime.retriever_engine)} |",
        f"| Retriever Model | {_markdown_cell(runtime.retriever_model)} |",
        f"| Retriever Dimensions | {_markdown_cell(runtime.retriever_dimensions)} |",
        f"| Indexed Documents | {_markdown_cell(runtime.indexed_document_count)} |",
        "",
        "## Fixed Checks",
        "",
        "| Check | Actual | Expected | Passed |",
        "|---|---:|---:|---:|",
    ]
    for check in result.checks:
        lines.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(check.id),
                    _markdown_cell(check.actual),
                    _markdown_cell(check.expected),
                    _markdown_cell(check.passed),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            f"- Failed Check IDs: {_markdown_cell(result.failed_check_ids)}",
            "",
            "## Benchmark Metrics",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
    )
    metric_values = (
        ("caseCount", metrics.case_count),
        ("matchedCaseCount", metrics.matched_case_count),
        ("normalCaseCount", metrics.normal_case_count),
        ("violationCaseCount", metrics.violation_case_count),
        ("replayCaseCount", metrics.replay_case_count),
        ("attackSuccessRate", metrics.attack_success_rate),
        ("detectionRecall", metrics.detection_recall),
        ("falsePositiveRate", metrics.false_positive_rate),
        ("policyViolationAccuracy", metrics.policy_violation_accuracy),
        ("meanAttempts", metrics.mean_attempts),
        ("meanScanTimeMs", metrics.mean_scan_time_ms),
        ("replayPassRate", metrics.replay_pass_rate),
        ("scanTimeMs", metrics.scan_time_ms),
        ("categoryCounts", metrics.category_counts),
    )
    for name, value in metric_values:
        lines.append(f"| {_markdown_cell(name)} | {_markdown_cell(value)} |")
    lines.extend(
        [
            "",
            "### Provider Usage",
            "",
            "| Metric | Value |",
            "|---|---:|",
            f"| callCount | {_markdown_cell(usage.call_count)} |",
            f"| inputTokens | {_markdown_cell(usage.input_tokens)} |",
            f"| outputTokens | {_markdown_cell(usage.output_tokens)} |",
            f"| totalTokens | {_markdown_cell(usage.total_tokens)} |",
            f"| estimatedCostUsd | {_markdown_cell(usage.estimated_cost_usd)} |",
            "",
            "## Cases",
            "",
            "| Case ID | Category | Type | Expected Outcome | Actual Outcome | "
            "Expected Finding Categories | Actual Finding Categories | Expected Status | "
            "Actual Status | Matched | Attempts | Provider Calls | Duration ms |",
            "|---|---|---|---|---|---|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for case in result.benchmark.cases:
        values: Sequence[Any] = (
            case.case_id,
            case.category,
            case.execution_type,
            case.expected_outcome,
            case.actual_outcome,
            case.expected_finding_categories,
            case.actual_finding_categories,
            case.expected_execution_status,
            case.actual_execution_status,
            case.matched,
            case.attempt_count,
            case.provider_call_count,
            case.duration_ms,
        )
        lines.append("| " + " | ".join(_markdown_cell(value) for value in values) + " |")
    return "\n".join(lines) + "\n"


CI_GATE_JSON_FILENAME = "ci-gate.json"
CI_GATE_MARKDOWN_FILENAME = "ci-gate.md"


class CIGateArtifactWriter:
    """Write the two fixed CI gate artifacts while preserving other files."""

    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def write(self, result: CIGateResult) -> tuple[Path, Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.output_dir / CI_GATE_JSON_FILENAME
        markdown_path = self.output_dir / CI_GATE_MARKDOWN_FILENAME
        payload = json.dumps(
            result.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        json_path.write_text(payload + "\n", encoding="utf-8")
        markdown_path.write_text(
            render_ci_gate_markdown(result),
            encoding="utf-8",
        )
        return json_path, markdown_path


def write_ci_gate_artifacts(
    result: CIGateResult,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Create/update only ``ci-gate.json`` and ``ci-gate.md`` in ``output_dir``."""

    return CIGateArtifactWriter(output_dir).write(result)


__all__ = [
    "ALL_CASES_MATCHED_CHECK_ID",
    "CI_GATE_CHECK_IDS",
    "CI_GATE_JSON_FILENAME",
    "CI_GATE_MARKDOWN_FILENAME",
    "CIGateArtifactWriter",
    "CIGateCheck",
    "CIGateResult",
    "CIGateStatus",
    "DETECTION_RECALL_CHECK_ID",
    "FALSE_POSITIVE_RATE_CHECK_ID",
    "POLICY_VIOLATION_ACCURACY_CHECK_ID",
    "REPLAY_PASS_RATE_CHECK_ID",
    "build_ci_gate_result",
    "render_ci_gate_markdown",
    "write_ci_gate_artifacts",
]
