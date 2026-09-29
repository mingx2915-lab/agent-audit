"""固定 Acceptance Run 的编排、证据摘要与纯函数投影。

F-025 只把现有的确定性验收链路组织成一个可持久化的结果。这里不引入
新的安全判定：Provider Readiness 仍是兼容性证据，最终 verdict 直接来自
同一次固定 Benchmark 生成的 ``CIGateResult``。
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Literal

from .attack_cases import AttackCaseExecutor
from .benchmark import (
    GROUND_TRUTH_CASE_IDS,
    BenchmarkResult,
    GroundTruthCase,
    load_ground_truth_cases,
)
from .benchmark_runtime import build_benchmark_runtime
from .ci_gate import CIGateResult, build_ci_gate_result
from .demo_data import DemoData, load_demo_data
from .differential import (
    DifferentialAuditResult,
    DifferentialAuditRunner,
    build_differential_tasks,
)
from .evaluation import FindingCategory
from .history import AuditRuntimeSnapshot, TargetProfileSnapshot
from .planning import AttackPlan, AttackPlanExecutor, ContractAttackPlanner
from .providers.base import LLMProvider
from .red_team import (
    LLMAttackVariantGenerator,
    RedTeamOrchestrator,
    RedTeamScan,
    provider_metadata,
)
from .readiness import ProviderReadinessResult, ProviderReadinessRunner
from .replay import ReplayExecutor, ReplayResult
from .retrieval import Retriever
from .retrieval_evaluation import (
    RetrievalEvaluationResult,
    RetrievalEvaluationRunner,
)
from .schemas import CamelModel
from .security_contract import SecurityContract
from .target import TargetProfile
from .tools import MockCustomerExportTool, MockCustomerTool, MockMailTool


AcceptanceStatus = Literal["completed"]
AcceptanceVerdict = Literal["passed", "failed"]


class AcceptanceRun(CamelModel):
    """一次完整固定验收的不可变 DTO 快照。"""

    id: str
    started_at: str
    completed_at: str
    duration_ms: float
    status: AcceptanceStatus
    verdict: AcceptanceVerdict
    contract_snapshot: SecurityContract
    plan_snapshots: list[AttackPlan]
    profile_snapshots: list[TargetProfileSnapshot]
    runtime_snapshot: AuditRuntimeSnapshot
    provider_readiness: ProviderReadinessResult
    retrieval_evaluation: RetrievalEvaluationResult
    differential_audits: list[DifferentialAuditResult]
    ci_gate: CIGateResult
    guided_scan: RedTeamScan
    guided_replay: ReplayResult
    finding_categories: list[FindingCategory]
    finding_count: int = 0


class AcceptanceRunSummary(CamelModel):
    """历史列表和对比使用的轻量 Acceptance Run 投影。"""

    id: str
    started_at: str
    completed_at: str
    duration_ms: float
    status: AcceptanceStatus
    verdict: AcceptanceVerdict
    contract_id: str
    contract_version: int
    runtime_snapshot: AuditRuntimeSnapshot
    readiness_status: Literal["ready", "partial", "unavailable"]
    gate_status: Literal["passed", "failed"]
    benchmark_case_count: int
    benchmark_matched_case_count: int
    finding_count: int
    finding_categories: list[FindingCategory]
    guided_replay_status: Literal["passed", "failed"]


class AcceptanceMetricDelta(CamelModel):
    """一个固定 Gate 指标在两次 Run 间的前值、现值和差值。"""

    id: str
    previous: bool | float | None
    current: bool | float | None
    delta: float | None


class AcceptanceRunComparison(CamelModel):
    """当前 Run 与前一历史 Run 的确定性差异。"""

    current: AcceptanceRunSummary
    previous: AcceptanceRunSummary | None
    contract_changed: bool
    runtime_changed: bool
    readiness_changed: bool
    gate_status_changed: bool
    gate_metric_deltas: list[AcceptanceMetricDelta]
    added_failed_check_ids: list[str]
    resolved_failed_check_ids: list[str]
    added_mismatched_case_ids: list[str]
    resolved_mismatched_case_ids: list[str]
    added_finding_categories: list[FindingCategory]
    resolved_finding_categories: list[FindingCategory]


class EmptyAcceptanceRunRequest(CamelModel):
    """Acceptance Run 只允许无 body 或空 JSON object。"""


class AcceptanceConfigurationError(ValueError):
    """Raised when repository-owned fixed acceptance inputs are unavailable."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _runtime_snapshot(provider: object, retriever: Retriever) -> AuditRuntimeSnapshot:
    provider_name, model = provider_metadata(provider)
    metadata = retriever.metadata
    return AuditRuntimeSnapshot(
        provider=provider_name,
        model=model,
        retriever_engine=metadata.engine_id,
        retriever_model=metadata.model_name,
        retriever_dimensions=metadata.dimensions,
        indexed_document_count=metadata.indexed_document_count,
    )


def _target_profile_snapshot(profile: TargetProfile) -> TargetProfileSnapshot:
    return TargetProfileSnapshot(
        id=profile.id,
        name=profile.name,
        enforce_resource_authorization=profile.enforce_resource_authorization,
        enforce_tool_authorization=profile.enforce_tool_authorization,
        enforce_sink_authorization=profile.enforce_sink_authorization,
    )


def _copy_profiles(profiles: Sequence[TargetProfile]) -> tuple[TargetProfile, ...]:
    return tuple(profile.model_copy(deep=True) for profile in profiles)


def _copy_plans(plans: Sequence[AttackPlan]) -> tuple[AttackPlan, ...]:
    return tuple(plan.model_copy(deep=True) for plan in plans)


def _unique_categories(categories: Sequence[FindingCategory]) -> list[FindingCategory]:
    unique: list[FindingCategory] = []
    seen: set[FindingCategory] = set()
    for category in categories:
        if category in seen:
            continue
        seen.add(category)
        unique.append(category)
    return unique


def _finding_facts(
    differential_audits: Sequence[DifferentialAuditResult],
    benchmark: BenchmarkResult,
    guided_scan: RedTeamScan,
    guided_replay: ReplayResult,
) -> tuple[int, list[FindingCategory]]:
    """Collect only actual findings from each executed child result."""

    categories: list[FindingCategory] = []
    finding_count = 0
    for audit in differential_audits:
        for row in audit.rows:
            finding_count += len(row.findings)
            categories.extend(finding.category for finding in row.findings)
    for case in benchmark.cases:
        finding_count += len(case.actual_finding_categories)
        categories.extend(case.actual_finding_categories)
    for attempt in guided_scan.attempts:
        finding_count += len(attempt.evaluation.findings)
        categories.extend(finding.category for finding in attempt.evaluation.findings)
    for attempt in (guided_replay.before, guided_replay.after):
        finding_count += len(attempt.evaluation.findings)
        categories.extend(finding.category for finding in attempt.evaluation.findings)
    return finding_count, _unique_categories(categories)


class AcceptanceRunner:
    """串行执行仓库固定的 Acceptance Run 子验收。"""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        retriever: Retriever,
        tfidf_retriever: Retriever,
        contract: SecurityContract,
        profiles: Sequence[TargetProfile],
        attack_provider: LLMProvider | None = None,
        demo_data: DemoData | None = None,
        customer_tool: MockCustomerTool | None = None,
        mail_tool: MockMailTool | None = None,
        export_tool: MockCustomerExportTool | None = None,
        cases: Sequence[GroundTruthCase] | None = None,
        plans: Sequence[AttackPlan] | None = None,
        runtime_snapshot: AuditRuntimeSnapshot | None = None,
    ) -> None:
        self._provider = provider
        self._attack_provider = attack_provider if attack_provider is not None else provider
        self._retriever = retriever
        self._tfidf_retriever = tfidf_retriever
        self._contract = contract
        self._profiles = _copy_profiles(profiles)
        self._demo_data = demo_data if demo_data is not None else load_demo_data()
        self._customer_tool = (
            customer_tool
            if customer_tool is not None
            else MockCustomerTool(self._demo_data.customers)
        )
        self._mail_tool = (
            mail_tool if mail_tool is not None else MockMailTool()
        )
        self._export_tool = (
            export_tool
            if export_tool is not None
            else MockCustomerExportTool(self._demo_data.customers)
        )
        self._cases = tuple(cases) if cases is not None else None
        self._plans = _copy_plans(plans) if plans is not None else None
        self._runtime_snapshot = runtime_snapshot

    def _snapshot_inputs(
        self,
    ) -> tuple[
        SecurityContract,
        tuple[AttackPlan, ...],
        tuple[TargetProfileSnapshot, ...],
        tuple[TargetProfile, ...],
        AuditRuntimeSnapshot,
    ]:
        """Deep-copy all mutable configuration before the first Provider call."""

        contract = self._contract.model_copy(deep=True)
        if self._plans is None:
            plans = ContractAttackPlanner(
                contract=contract,
                actors=self._demo_data.actors,
                documents=self._demo_data.documents,
                customers=self._demo_data.customers,
                customer_tool=self._customer_tool,
                mail_tool=self._mail_tool,
                export_tool=self._export_tool,
            ).plan()
            plans = _copy_plans(plans)
        else:
            plans = _copy_plans(self._plans)
        profiles = _copy_profiles(self._profiles)
        profile_snapshots = tuple(_target_profile_snapshot(profile) for profile in profiles)
        runtime_snapshot = (
            self._runtime_snapshot.model_copy(deep=True)
            if self._runtime_snapshot is not None
            else _runtime_snapshot(self._attack_provider, self._retriever)
        )
        return contract, plans, profile_snapshots, profiles, runtime_snapshot

    @staticmethod
    def _required_plan(plans: Sequence[AttackPlan], plan_id: str) -> AttackPlan:
        plan = next((candidate for candidate in plans if candidate.id == plan_id), None)
        if plan is None:
            raise AcceptanceConfigurationError(
                f"required acceptance plan is unavailable: {plan_id}"
            )
        return plan

    @staticmethod
    def _validate_fixed_cases(cases: Sequence[GroundTruthCase]) -> tuple[GroundTruthCase, ...]:
        if len(cases) != 24:
            raise AcceptanceConfigurationError(
                "acceptance benchmark requires the fixed 24 Ground Truth cases"
            )
        case_ids = [case.id for case in cases]
        if len(case_ids) != len(set(case_ids)) or set(case_ids) != set(GROUND_TRUTH_CASE_IDS):
            raise AcceptanceConfigurationError(
                "acceptance benchmark cases do not match the fixed catalog"
            )
        category_counts = {
            category: sum(1 for case in cases if case.category == category)
            for category in (
                "normal_behavior",
                "internal_authorization",
                "outside_in_source_sink",
                "tool_threshold_replay",
            )
        }
        if any(count != 6 for count in category_counts.values()):
            raise AcceptanceConfigurationError(
                "acceptance benchmark requires six cases per category"
            )
        return tuple(case.model_copy(deep=True) for case in cases)

    async def run(self) -> AcceptanceRun:
        started_at = _utc_now()
        started_clock = time.perf_counter()
        (
            contract,
            plans,
            profile_snapshots,
            profiles,
            runtime_snapshot,
        ) = self._snapshot_inputs()
        guided_plan = self._required_plan(
            plans,
            "plan_sink_confidential_external",
        )
        profile_ids = {profile.id for profile in profiles}
        if "secure" not in profile_ids:
            raise AcceptanceConfigurationError("secure target profile is unavailable")
        if guided_plan.target_profile_id not in profile_ids:
            raise AcceptanceConfigurationError(
                f"target profile is unavailable: {guided_plan.target_profile_id}"
            )
        cases = self._validate_fixed_cases(
            self._cases
            if self._cases is not None
            else load_ground_truth_cases()
        )

        # 1) Readiness is evidence only and must not become the verdict.
        readiness = await ProviderReadinessRunner(
            target_provider=self._provider,
            attack_provider=self._attack_provider,
            plans=plans,
        ).run()

        # 2) The retrieval runner owns the repository's fixed six queries.
        retrieval = RetrievalEvaluationRunner(
            tfidf_retriever=self._tfidf_retriever,
            embedding_retriever=self._retriever,
        ).run()

        # 3) Both differential tasks use their repository-defined default Profile.
        tasks = build_differential_tasks(
            actors=self._demo_data.actors,
            documents=self._demo_data.documents,
            customers=self._demo_data.customers,
            customer_tool=self._customer_tool,
        )
        if len(tasks) != 2:
            raise AcceptanceConfigurationError(
                "acceptance requires exactly two differential tasks"
            )
        differential_runner = DifferentialAuditRunner(
            provider=self._provider,
            actors=self._demo_data.actors,
            documents=self._demo_data.documents,
            customers=self._demo_data.customers,
            retriever=self._retriever,
            customer_tool=self._customer_tool,
            mail_tool=self._mail_tool,
            export_tool=self._export_tool,
            contract=contract,
            profiles=profiles,
        )
        differential_audits = [
            await differential_runner.run(task, task.default_target_profile_id)
            for task in tasks
        ]

        # 4) Benchmark and CI Gate share the exact contract/plan/profile/runtime
        # snapshots.  The runtime wraps the same underlying Provider/Retriever.
        benchmark_runtime = build_benchmark_runtime(
            self._provider,
            contract=contract,
            retriever=self._retriever,
            cases=cases,
            profiles=profiles,
            plans=plans,
            demo_data=self._demo_data,
        )
        benchmark = await benchmark_runtime.run()
        ci_gate = build_ci_gate_result(
            benchmark,
            contract,
            runtime_snapshot,
        )

        # 5) Guided Source→Sink scan and same-plan remediation Replay.
        case_executor = AttackCaseExecutor(
            provider=self._provider,
            actors=self._demo_data.actors,
            retriever=self._retriever,
            customer_tool=self._customer_tool,
            mail_tool=self._mail_tool,
            export_tool=self._export_tool,
            contract=contract,
            profiles=profiles,
        )
        plan_executor = AttackPlanExecutor(case_executor)
        scan = await RedTeamOrchestrator(
            plan_executor=plan_executor,
            variant_generator=LLMAttackVariantGenerator(self._attack_provider),
            contract=contract,
            provider=self._attack_provider,
        ).run(guided_plan, max_rounds=3)
        guided_replay = await ReplayExecutor(
            plan_executor=plan_executor,
            contract=contract,
        ).replay(guided_plan)

        finding_count, finding_categories = _finding_facts(
            differential_audits,
            benchmark,
            scan,
            guided_replay,
        )
        completed_at = _utc_now()
        return AcceptanceRun(
            id=f"acceptance_{uuid.uuid4().hex[:12]}",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(max(0.0, (time.perf_counter() - started_clock) * 1000), 2),
            status="completed",
            verdict=ci_gate.status,
            contract_snapshot=contract,
            plan_snapshots=list(plans),
            profile_snapshots=list(profile_snapshots),
            runtime_snapshot=runtime_snapshot,
            provider_readiness=readiness,
            retrieval_evaluation=retrieval,
            differential_audits=differential_audits,
            ci_gate=ci_gate,
            guided_scan=scan,
            guided_replay=guided_replay,
            finding_categories=finding_categories,
            finding_count=finding_count,
        )


def build_acceptance_summary(run: AcceptanceRun) -> AcceptanceRunSummary:
    """纯函数：从保存的完整 Run 投影历史摘要。"""

    benchmark = run.ci_gate.benchmark
    return AcceptanceRunSummary(
        id=run.id,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_ms=run.duration_ms,
        status=run.status,
        verdict=run.verdict,
        contract_id=run.contract_snapshot.id,
        contract_version=run.contract_snapshot.version,
        runtime_snapshot=run.runtime_snapshot.model_copy(deep=True),
        readiness_status=run.provider_readiness.status,
        gate_status=run.ci_gate.status,
        benchmark_case_count=benchmark.metrics.case_count,
        benchmark_matched_case_count=benchmark.metrics.matched_case_count,
        finding_count=run.finding_count,
        finding_categories=list(run.finding_categories),
        guided_replay_status=run.guided_replay.status,
    )


_GATE_METRICS: tuple[str, ...] = (
    "all_cases_matched",
    "detection_recall",
    "false_positive_rate",
    "policy_violation_accuracy",
    "replay_pass_rate",
)


def _gate_metric_values(run: AcceptanceRun) -> dict[str, bool | float | None]:
    checks = {check.id: check.actual for check in run.ci_gate.checks}
    metrics = run.ci_gate.benchmark.metrics
    return {
        "all_cases_matched": checks.get("all_cases_matched"),
        "detection_recall": metrics.detection_recall,
        "false_positive_rate": metrics.false_positive_rate,
        "policy_violation_accuracy": metrics.policy_violation_accuracy,
        "replay_pass_rate": metrics.replay_pass_rate,
    }


def _metric_delta(
    previous: bool | float | None,
    current: bool | float | None,
) -> float | None:
    if previous is None or current is None:
        return None
    if isinstance(previous, bool) and isinstance(current, bool):
        return float(int(current) - int(previous))
    if isinstance(previous, (int, float)) and isinstance(current, (int, float)):
        return float(current) - float(previous)
    return None


def _model_payload(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json", by_alias=True)


def _summary_runtime_changed(
    current: AcceptanceRunSummary,
    previous: AcceptanceRunSummary,
) -> bool:
    return _model_payload(current.runtime_snapshot) != _model_payload(previous.runtime_snapshot)


def _summary_contract_changed(
    current_run: AcceptanceRun,
    previous_run: AcceptanceRun,
) -> bool:
    return current_run.contract_snapshot.model_dump(mode="json", by_alias=True) != previous_run.contract_snapshot.model_dump(
        mode="json", by_alias=True
    )


def _mismatched_case_ids(run: AcceptanceRun) -> list[str]:
    return sorted(case.case_id for case in run.ci_gate.benchmark.cases if not case.matched)


def _failed_check_ids(run: AcceptanceRun) -> list[str]:
    return sorted(run.ci_gate.failed_check_ids)


def build_acceptance_comparison(
    current: AcceptanceRun,
    previous: AcceptanceRun | None,
) -> AcceptanceRunComparison:
    """纯函数：比较保存的 Run，不读取 active Contract 或调用 Provider。"""

    current_summary = build_acceptance_summary(current)
    if previous is None:
        return AcceptanceRunComparison(
            current=current_summary,
            previous=None,
            contract_changed=False,
            runtime_changed=False,
            readiness_changed=False,
            gate_status_changed=False,
            gate_metric_deltas=[],
            added_failed_check_ids=[],
            resolved_failed_check_ids=[],
            added_mismatched_case_ids=[],
            resolved_mismatched_case_ids=[],
            added_finding_categories=[],
            resolved_finding_categories=[],
        )

    previous_run = previous
    previous_summary = build_acceptance_summary(previous)

    current_metrics = _gate_metric_values(current)
    previous_metrics = _gate_metric_values(previous_run)
    deltas = [
        AcceptanceMetricDelta(
            id=metric_id,
            previous=previous_metrics.get(metric_id),
            current=current_metrics.get(metric_id),
            delta=_metric_delta(
                previous_metrics.get(metric_id),
                current_metrics.get(metric_id),
            ),
        )
        for metric_id in _GATE_METRICS
    ]
    current_failed = set(_failed_check_ids(current))
    current_mismatched = set(_mismatched_case_ids(current))
    current_categories = set(current.finding_categories)
    previous_categories = set(previous_summary.finding_categories)
    previous_failed = set(_failed_check_ids(previous_run))
    previous_mismatched = set(_mismatched_case_ids(previous_run))
    return AcceptanceRunComparison(
        current=current_summary,
        previous=previous_summary,
        contract_changed=_summary_contract_changed(
            current,
            previous_run,
        ),
        runtime_changed=_summary_runtime_changed(current_summary, previous_summary),
        readiness_changed=(
            current_summary.readiness_status != previous_summary.readiness_status
        ),
        gate_status_changed=current_summary.gate_status != previous_summary.gate_status,
        gate_metric_deltas=deltas,
        added_failed_check_ids=sorted(current_failed - previous_failed),
        resolved_failed_check_ids=sorted(previous_failed - current_failed),
        added_mismatched_case_ids=sorted(current_mismatched - previous_mismatched),
        resolved_mismatched_case_ids=sorted(previous_mismatched - current_mismatched),
        added_finding_categories=sorted(current_categories - previous_categories),
        resolved_finding_categories=sorted(previous_categories - current_categories),
    )


def _markdown_cell(value: Any) -> str:
    if value is None:
        text = "null"
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (list, tuple, dict)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = str(value)
    return text.replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def render_acceptance_markdown(run: AcceptanceRun) -> str:
    """纯函数：只从保存的 Acceptance Run 生成交付 Markdown。"""

    summary = build_acceptance_summary(run)
    runtime = run.runtime_snapshot
    readiness = run.provider_readiness
    benchmark = run.ci_gate.benchmark
    lines = [
        "# 知盾 AgentAudit Acceptance Run",
        "",
        "SYNTHETIC / DEMO ONLY",
        "",
        "## Run",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| ID | `{_markdown_cell(run.id)}` |",
        f"| Status | `{_markdown_cell(run.status)}` |",
        f"| Verdict | `{_markdown_cell(run.verdict)}` |",
        f"| Started At | `{_markdown_cell(run.started_at)}` |",
        f"| Completed At | `{_markdown_cell(run.completed_at)}` |",
        f"| Duration ms | `{_markdown_cell(run.duration_ms)}` |",
        "",
        "## Contract and Runtime",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Contract | `{_markdown_cell(run.contract_snapshot.id)}` |",
        f"| Contract Version | `{_markdown_cell(run.contract_snapshot.version)}` |",
        f"| Provider | `{_markdown_cell(runtime.provider)}` |",
        f"| Model | `{_markdown_cell(runtime.model)}` |",
        f"| Retriever | `{_markdown_cell(runtime.retriever_engine)}` |",
        f"| Retriever Model | `{_markdown_cell(runtime.retriever_model)}` |",
        f"| Retriever Dimensions | `{_markdown_cell(runtime.retriever_dimensions)}` |",
        f"| Indexed Documents | `{_markdown_cell(runtime.indexed_document_count)}` |",
        "",
        "## Provider Readiness",
        "",
        f"- Status: `{_markdown_cell(readiness.status)}`",
        f"- Target Provider: `{_markdown_cell(readiness.target_provider.provider)}` / `{_markdown_cell(readiness.target_provider.model)}`",
        f"- Attack Provider: `{_markdown_cell(readiness.attack_provider.provider)}` / `{_markdown_cell(readiness.attack_provider.model)}`",
        "",
        "| Probe | Status | Detail |",
        "|---|---|---|",
    ]
    for role in (readiness.target_provider, readiness.attack_provider):
        for probe in role.probes:
            lines.append(
                f"| {_markdown_cell(probe.id)} | {_markdown_cell(probe.status)} | {_markdown_cell(probe.detail)} |"
            )
    lines.extend(
        [
            "",
            "## Retrieval Evaluation",
            "",
            f"- Fixed Query Count: `{_markdown_cell(run.retrieval_evaluation.metrics.case_count)}`",
            f"- Embedding Top-1 Hits: `{_markdown_cell(run.retrieval_evaluation.metrics.embedding_top1_hits)}`",
            f"- Embedding MRR: `{_markdown_cell(run.retrieval_evaluation.metrics.embedding_mrr)}`",
            "",
            "## CI Gate",
            "",
            f"- Status: `{_markdown_cell(run.ci_gate.status)}`",
            f"- Failed Check IDs: `{_markdown_cell(run.ci_gate.failed_check_ids)}`",
            "",
            "| Check | Actual | Expected | Passed |",
            "|---|---|---|---|",
        ]
    )
    for check in run.ci_gate.checks:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (check.id, check.actual, check.expected, check.passed)
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Benchmark Cases",
            "",
            f"- Cases: `{_markdown_cell(summary.benchmark_case_count)}`",
            f"- Matched: `{_markdown_cell(summary.benchmark_matched_case_count)}`",
            "",
            "| Case ID | Category | Actual Outcome | Actual Finding Categories | Status | Matched |",
            "|---|---|---|---|---|---|",
        ]
    )
    for case in benchmark.cases:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    case.case_id,
                    case.category,
                    case.actual_outcome,
                    case.actual_finding_categories,
                    case.actual_execution_status,
                    case.matched,
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Differential Audits",
            "",
        ]
    )
    for audit in run.differential_audits:
        lines.extend(
            [
                f"### {_markdown_cell(audit.task.id)}",
                f"- Profile: `{_markdown_cell(audit.target_profile_id)}`",
                f"- Status: `{_markdown_cell(audit.status)}`",
                f"- Mismatches: `{_markdown_cell(audit.mismatch_count)}`",
            ]
        )
        for row in audit.rows:
            lines.append(
                f"- `{_markdown_cell(row.id)}` expected=`{_markdown_cell(row.expected_decision)}` "
                f"actual=`{_markdown_cell(row.actual_decision)}` matched=`{_markdown_cell(row.matched)}`"
            )
    lines.extend(
        [
            "",
            "## Findings",
            "",
            f"- Count: `{_markdown_cell(run.finding_count)}`",
            f"- Categories: `{_markdown_cell(run.finding_categories)}`",
            "",
            "## Guided Scan",
            "",
            f"- Plan: `{_markdown_cell(run.guided_scan.plan_id)}`",
            f"- Status: `{_markdown_cell(run.guided_scan.status)}`",
            f"- Stop Reason: `{_markdown_cell(run.guided_scan.stop_reason)}`",
            f"- Attempts: `{_markdown_cell(len(run.guided_scan.attempts))}`",
            "",
            "## Guided Replay",
            "",
            f"- Plan: `{_markdown_cell(run.guided_replay.plan.id)}`",
            f"- Status: `{_markdown_cell(run.guided_replay.status)}`",
            f"- BEFORE: execution=`{_markdown_cell(run.guided_replay.before.execution_status)}` evaluation=`{_markdown_cell(run.guided_replay.before.evaluation.status)}`",
            f"- AFTER: execution=`{_markdown_cell(run.guided_replay.after.execution_status)}` evaluation=`{_markdown_cell(run.guided_replay.after.evaluation.status)}`",
            "",
            "## Snapshot JSON",
            "",
            "```json",
            json.dumps(run.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "AcceptanceConfigurationError",
    "AcceptanceMetricDelta",
    "AcceptanceRun",
    "AcceptanceRunComparison",
    "AcceptanceRunSummary",
    "AcceptanceRunner",
    "EmptyAcceptanceRunRequest",
    "build_acceptance_comparison",
    "build_acceptance_summary",
    "render_acceptance_markdown",
]
