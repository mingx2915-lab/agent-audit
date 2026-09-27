"""Explicit local stability evidence for the controlled AgentAudit target.

This module intentionally owns only the F-036 deterministic workflow soak.  It
does not add another scanner or another policy evaluator: every scan, Finding,
Replay, and history write goes through the production ``AttackPlanExecutor``,
``RedTeamOrchestrator``, ``ReplayExecutor`` and SQLite repository.

The runner is never imported by application startup.  Callers must invoke it
explicitly (the ``agent-audit stability`` CLI command is the supported entry
point), and its default provider is a clearly identified deterministic Test
Double.  The resulting JSON is the only evidence source; Markdown is a pure
projection of the same DTO.
"""

from __future__ import annotations

import json
import platform as platform_module
import sys
import tempfile
import time
import tracemalloc
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Iterator, Literal

from pydantic import Field

from .app_paths import resolve_app_paths
from .attack_cases import AttackCaseExecutor, load_target_profiles
from .demo_data import DemoData, load_demo_data
from .evaluation import FindingCategory
from .history import (
    AuditRunDetail,
    AuditRuntimeSnapshot,
    PersistedReplay,
    SQLiteAuditRunRepository,
    TargetProfileSnapshot,
)
from .planning import AttackPlan, AttackPlanExecutor, ContractAttackPlanner
from .providers.base import (
    LLMProvider,
    LLMResponse,
    ProviderError,
    ProviderUsage,
    ToolCall,
)
from .red_team import LLMAttackVariantGenerator, RedTeamOrchestrator, RedTeamScan
from .replay import ReplayExecutor, ReplayResult
from .retrieval import Retriever, TfidfRetriever
from .schemas import CamelModel
from .security_contract import SecurityContract, load_security_contract
from .tools import MockCustomerTool, MockMailTool
from .workspace import AuditWorkspace, WorkspaceError, WorkspaceService


DEFAULT_STABILITY_OUTPUT_DIR = Path("artifacts/acceptance/generated")
STABILITY_JSON_SUFFIX = ".json"
STABILITY_MARKDOWN_SUFFIX = ".md"
STABILITY_CHECK_ID = "workflow_soak"
DEFAULT_ITERATIONS = 10
MAX_ITERATIONS = 100
MAX_LONG_SOAK_ITERATIONS = 1_000


@dataclass
class DeterministicStabilityProvider:
    """A local, deterministic Provider used only by explicit F-036 runs.

    The marker is deliberately part of the public class contract.  A stability
    run refuses an injected provider without ``deterministic is True`` so a
    real model cannot accidentally be reported as deterministic evidence.
    """

    model: str = "deterministic-stability-provider"
    calls: list[dict[str, Any]] = field(default_factory=list)

    deterministic: ClassVar[bool] = True
    provider_id: ClassVar[str] = "deterministic_test_provider"

    @staticmethod
    def _tool_names(tools: Any) -> set[str]:
        names: set[str] = set()
        for tool in tools or ():
            if not isinstance(tool, Mapping):
                continue
            function = tool.get("function")
            if isinstance(function, Mapping):
                name = function.get("name")
                if isinstance(name, str) and name.strip():
                    names.add(name)
        return names

    @staticmethod
    def _user_text(messages: Sequence[Mapping[str, Any]]) -> str:
        return "\n".join(
            str(message.get("content") or "")
            for message in messages
            if isinstance(message, Mapping) and message.get("role") == "user"
        )

    @staticmethod
    def _variant_payload(messages: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
        if not messages:
            return None
        candidate = messages[-1].get("content") if isinstance(messages[-1], Mapping) else None
        if not isinstance(candidate, str):
            return None
        try:
            payload = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping) or not isinstance(payload.get("baseline"), Mapping):
            return None
        return payload

    @staticmethod
    def _mail_resource_ids(_: str) -> list[str]:
        """Return the two fixed synthetic resources for the source-sink plan."""

        return [
            "doc_external_vendor_prompt_001",
            "doc_finance_budget_001",
        ]

    @staticmethod
    def _usage(call_number: int) -> ProviderUsage:
        # Fixed usage is observation data for this Test Double, not a claim
        # about any real model's tokenization or cost.
        return ProviderUsage(
            input_tokens=10 + call_number,
            output_tokens=5,
            total_tokens=15 + call_number,
        )

    def _record(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, object]] | None,
        response: LLMResponse,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": tuple(dict(message) for message in messages),
                "tools": tuple(dict(tool) for tool in tools or ()),
                "response": response,
            }
        )
        return response

    async def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        """Return one fixed variant, Tool Call, or final text response."""

        call_number = len(self.calls) + 1
        variant_payload = self._variant_payload(messages)
        if variant_payload is not None:
            baseline = variant_payload["baseline"]
            round_number = variant_payload.get("round", 1)
            if not isinstance(round_number, int):
                round_number = 1
            baseline_message = baseline.get("message")
            if not isinstance(baseline_message, str) or not baseline_message.strip():
                baseline_message = "执行固定合成 Source→Sink 验收"
            response = LLMResponse(
                content=json.dumps(
                    {
                        "message": f"{baseline_message}（deterministic round {round_number}）",
                        "mutationReason": "使用实际 Trace 前提下的固定 deterministic 变体",
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                usage=self._usage(call_number),
            )
            return self._record(messages, tools, response)

        user_text = self._user_text(messages)
        tool_names = self._tool_names(tools)
        if "mock_mail_send" in tool_names and "mock_mail_send" in user_text:
            response = LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id=f"call_stability_{call_number}",
                        name="mock_mail_send",
                        arguments={
                            "to": "audit@external-sink.demo.local",
                            "subject": "合成稳定性验收摘要",
                            "body": "Deterministic stability evidence",
                            "resourceIds": self._mail_resource_ids(user_text),
                            "approved": False,
                        },
                    ),
                ),
                usage=self._usage(call_number),
            )
        else:
            response = LLMResponse(
                content="deterministic stability provider response",
                tool_calls=(),
                usage=self._usage(call_number),
            )
        return self._record(messages, tools, response)


class StabilityConfigurationError(ValueError):
    """Raised when the fixed F-036 runtime cannot be assembled."""


class StabilityInvariantError(RuntimeError):
    """Raised when actual Scan/Trace/Replay evidence violates F-036 invariants."""


class StabilityHistoryError(RuntimeError):
    """Raised when a completed workflow cannot be verified in SQLite history."""


class StabilityFailure(CamelModel):
    """One safe, categorised failure from one attempted iteration."""

    iteration: int = Field(ge=1)
    stage: str
    category: str
    error_type: str
    detail: str | None = None


class StabilityIteration(CamelModel):
    """A compact projection of one real workflow and its history verification."""

    iteration: int = Field(ge=1)
    status: Literal["passed", "failed"]
    plan_id: str
    scan_id: str | None = None
    replay_id: str | None = None
    replay_result_id: str | None = None
    scan_stop_reason: str | None = None
    attempt_count: int = Field(default=0, ge=0)
    trace_event_count: int = Field(default=0, ge=0)
    finding_count: int = Field(default=0, ge=0)
    finding_categories: list[FindingCategory] = Field(default_factory=list)
    source_sink_finding: bool = False
    replay_status: Literal["passed", "failed"] | None = None
    replay_before_evaluation: Literal["passed", "failed"] | None = None
    replay_after_evaluation: Literal["passed", "failed"] | None = None
    replay_after_execution: Literal["completed", "blocked"] | None = None
    history_persisted: bool = False
    history_count: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0.0, ge=0)
    failure: StabilityFailure | None = None


class StabilityCheck(CamelModel):
    """One explicit F-036 check; the core runner currently has one check."""

    id: str
    status: Literal["passed", "failed", "skipped"]
    iterations: int = Field(ge=1)
    completed_iterations: int = Field(ge=0)
    failures: list[StabilityFailure] = Field(default_factory=list)


class StabilityEnvironment(CamelModel):
    """Non-sensitive environment facts safe to place in a portable artifact."""

    platform: str
    machine: str = platform_module.machine()
    python: str
    artifact: str | None = None
    provider: str = "deterministic_test_provider"
    retriever: str = "tfidf_test_retriever"
    workspace: Literal["temporary", "explicit"] = "temporary"
    deterministic: bool = True


class StabilityObservations(CamelModel):
    """Measured values and counts; no unmeasured performance claim is made."""

    duration_ms: float = Field(ge=0)
    duration_p50_ms: float | None = Field(default=None, ge=0)
    duration_p95_ms: float | None = Field(default=None, ge=0)
    duration_sample_count: int = Field(default=0, ge=0)
    repetition_count: int = Field(default=0, ge=0)
    memory_start_bytes: int | None = Field(default=None, ge=0)
    memory_end_bytes: int | None = Field(default=None, ge=0)
    memory_metric: str = "python_tracemalloc_current_bytes"
    memory_observation_method: str = (
        "tracemalloc.get_traced_memory current allocation at runner start/end"
    )
    handle_count: int | None = Field(default=None, ge=0)
    handle_observation_method: str = (
        "not_collected: no cross-platform operating-system handle sampler"
    )
    process_count: int | None = Field(default=None, ge=0)
    process_observation_method: str = (
        "runner process only; no child process is spawned by Core StabilityRunner"
    )
    dataset_document_count: int = Field(default=0, ge=0)
    dataset_history_rows: int = Field(default=0, ge=0)
    history_source: str = "temporary_sqlite"
    database_observation_method: str = (
        "SQLiteAuditRunRepository.save/append_replay plus list(limit) and get read-back"
    )
    history_count: int = Field(ge=0)
    provider_call_count: int = Field(ge=0)
    successful_workflows: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    replay_pass_count: int = Field(ge=0)


class StabilityEvidence(CamelModel):
    """Complete JSON source of truth for one explicit stability run."""

    id: str
    started_at: str
    completed_at: str
    status: Literal["passed", "failed"]
    environment: StabilityEnvironment
    checks: list[StabilityCheck]
    observations: StabilityObservations
    iterations: list[StabilityIteration]
    failures: list[StabilityFailure]
    limitations: list[str]


@dataclass(frozen=True)
class _StabilityDependencies:
    contract: SecurityContract
    retriever: Retriever
    plan: AttackPlan
    orchestrator: RedTeamOrchestrator
    replay_executor: ReplayExecutor
    history: SQLiteAuditRunRepository
    runtime_snapshot: AuditRuntimeSnapshot
    target_profile_snapshot: TargetProfileSnapshot


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_detail(exc: BaseException) -> str | None:
    """Keep only messages from known safe, local error boundaries."""

    if not isinstance(exc, (ProviderError, StabilityInvariantError, StabilityHistoryError, WorkspaceError)):
        return None
    text = str(exc).strip()
    return text or None


def _failure(
    iteration: int,
    stage: str,
    exc: BaseException,
) -> StabilityFailure:
    if isinstance(exc, ProviderError):
        category = "provider_error"
    elif isinstance(exc, (StabilityHistoryError, OSError)):
        category = "history_error"
    elif isinstance(exc, WorkspaceError):
        category = "workspace_error"
    elif isinstance(exc, StabilityInvariantError):
        category = "workflow_invariant"
    else:
        category = "workflow_error"
    return StabilityFailure(
        iteration=max(1, iteration),
        stage=stage,
        category=category,
        error_type=type(exc).__name__,
        detail=_safe_detail(exc),
    )


def _target_profile_snapshot(profile: Any) -> TargetProfileSnapshot:
    return TargetProfileSnapshot(
        id=profile.id,
        name=profile.name,
        enforce_resource_authorization=profile.enforce_resource_authorization,
        enforce_tool_authorization=profile.enforce_tool_authorization,
        enforce_sink_authorization=profile.enforce_sink_authorization,
    )


def _runtime_snapshot(
    provider: object,
    retriever: Retriever,
) -> AuditRuntimeSnapshot:
    metadata = retriever.metadata
    return AuditRuntimeSnapshot(
        provider=getattr(provider, "provider_id"),
        model=getattr(provider, "model", None),
        retriever_engine=metadata.engine_id,
        retriever_model=metadata.model_name,
        retriever_dimensions=metadata.dimensions,
        indexed_document_count=metadata.indexed_document_count,
    )


def _findings(scan: RedTeamScan) -> list[Any]:
    return [
        finding
        for attempt in scan.attempts
        for finding in attempt.evaluation.findings
    ]


def _trace_event_count(scan: RedTeamScan) -> int:
    return sum(
        len(attempt.query_result.trace_events)
        for attempt in scan.attempts
    )


def _validate_actual_scan(scan: RedTeamScan, plan: AttackPlan) -> None:
    if scan.status != "completed":
        raise StabilityInvariantError("scan did not complete")
    if scan.plan_id != plan.id:
        raise StabilityInvariantError("scan plan id does not match the fixed plan")
    if scan.target_profile_id != plan.target_profile_id:
        raise StabilityInvariantError("scan target profile does not match the fixed plan")
    if not scan.attempts:
        raise StabilityInvariantError("scan produced no actual attempt")
    events = [
        event
        for attempt in scan.attempts
        for event in attempt.query_result.trace_events
    ]
    event_types = {event.type for event in events}
    required_types = {"source", "retrieval", "authorization", "tool_call", "sink"}
    if not required_types.issubset(event_types):
        missing = ", ".join(sorted(required_types - event_types))
        raise StabilityInvariantError(f"source-to-sink Trace is missing: {missing}")
    findings = _findings(scan)
    if not any(finding.category == "external_sink_policy_violation" for finding in findings):
        raise StabilityInvariantError("actual source-to-sink Finding was not produced")
    if not any(
        event.type == "sink"
        and event.details.get("sinkType") == "external_message"
        and event.details.get("external") is True
        for event in events
    ):
        raise StabilityInvariantError("actual external Mock Mail Sink was not executed")


def _validate_actual_replay(replay: ReplayResult, plan: AttackPlan) -> None:
    if replay.plan.id != plan.id:
        raise StabilityInvariantError("replay plan id does not match the scan plan")
    if replay.status != "passed":
        raise StabilityInvariantError("same-plan replay did not pass")
    if replay.before.evaluation.status != "failed":
        raise StabilityInvariantError("replay before state did not contain a Finding")
    if replay.after.evaluation.status != "passed":
        raise StabilityInvariantError("replay after evaluation did not pass")
    if replay.after.execution_status != "blocked":
        raise StabilityInvariantError("replay after state was not blocked")


def _memory_start() -> tuple[bool, int | None]:
    try:
        started_here = not tracemalloc.is_tracing()
        if started_here:
            tracemalloc.start()
        return started_here, tracemalloc.get_traced_memory()[0]
    except RuntimeError:
        return False, None


def _memory_end(started_here: bool) -> int | None:
    try:
        value = tracemalloc.get_traced_memory()[0] if tracemalloc.is_tracing() else None
    except RuntimeError:
        value = None
    if started_here and tracemalloc.is_tracing():
        tracemalloc.stop()
    return value


def _percentile(values: list[float], fraction: float) -> float | None:
    """Return a linearly interpolated percentile for one run's observations."""

    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 2)


class StabilityRunner:
    """Run the existing Guided Scan/Finding/Replay chain repeatedly.

    ``iterations`` is intentionally bounded to 1..100 by default.  An explicit
    ``long_soak`` caller may raise that bound to 1,000 for release evidence.  A
    failed iteration is recorded once and the runner continues with the next
    iteration; it is never retried.

    ``workspace_root`` is an explicit test-injection seam only.  The CLI never
    exposes it; a valid existing manifest is opened, while a non-empty root
    without a manifest is rejected by ``WorkspaceService`` rather than
    overwritten.
    """

    def __init__(
        self,
        iterations: int = DEFAULT_ITERATIONS,
        *,
        max_rounds: Literal[2, 3] = 3,
        provider: LLMProvider | None = None,
        retriever: Retriever | None = None,
        workspace_root: str | Path | None = None,
        long_soak: bool = False,
    ) -> None:
        iteration_limit = MAX_LONG_SOAK_ITERATIONS if long_soak else MAX_ITERATIONS
        if type(iterations) is not int or not 1 <= iterations <= iteration_limit:
            raise ValueError(
                f"iterations must be an integer between 1 and {iteration_limit}"
            )
        if max_rounds not in (2, 3):
            raise ValueError("max_rounds must be 2 or 3")
        active_provider = provider if provider is not None else DeterministicStabilityProvider()
        if getattr(active_provider, "deterministic", False) is not True:
            raise ValueError(
                "stability runner requires a provider explicitly marked deterministic"
            )
        provider_id = getattr(active_provider, "provider_id", None)
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError(
                "stability runner requires a non-empty public provider_id"
            )
        self.iterations = iterations
        self.max_rounds = max_rounds
        self.provider = active_provider
        self.provider_id = provider_id
        self.retriever = retriever
        self.long_soak = long_soak
        self.workspace_root = Path(workspace_root).expanduser() if workspace_root is not None else None

    @staticmethod
    def _seed_dir() -> Path:
        return Path(__file__).resolve().parents[4] / "data" / "demo"

    @contextmanager
    def _workspace(self) -> Iterator[AuditWorkspace]:
        seed_dir = self._seed_dir()
        if self.workspace_root is not None:
            service = WorkspaceService()
            root = self.workspace_root
            if (root / "agent-audit-workspace.json").is_file():
                yield service.open(root)
            else:
                yield service.create(root, "F-036 Stability Workspace", seed_dir=seed_dir)
            return

        # The default path is always a fresh app home and Workspace.  It never
        # consults or mutates the user's normal AGENT_AUDIT_HOME/default DB.
        with tempfile.TemporaryDirectory(prefix="agent-audit-stability-") as temp_root:
            isolated_home = Path(temp_root) / "app-home"
            app_paths = resolve_app_paths(isolated_home)
            service = WorkspaceService(app_paths)
            workspace = service.ensure_default(
                seed_dir,
                root=app_paths.default_workspace_dir,
                name="F-036 Stability Workspace",
            )
            yield workspace

    def _build_dependencies(self, workspace: AuditWorkspace) -> _StabilityDependencies:
        data = load_demo_data(workspace.documents_path)
        contract = load_security_contract(workspace.contract_path)
        profiles = tuple(load_target_profiles(workspace.cases_path))
        retriever = self.retriever if self.retriever is not None else TfidfRetriever(data.documents)
        customer_tool = MockCustomerTool(data.customers)
        mail_tool = MockMailTool()
        plans = ContractAttackPlanner(
            contract=contract,
            actors=data.actors,
            documents=data.documents,
            customers=data.customers,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
        ).plan()
        plan = next(
            (candidate for candidate in plans if candidate.id == "plan_sink_confidential_external"),
            None,
        )
        if plan is None:
            raise StabilityConfigurationError(
                "fixed source-to-sink stability plan is unavailable"
            )
        profile = next((candidate for candidate in profiles if candidate.id == plan.target_profile_id), None)
        if profile is None:
            raise StabilityConfigurationError(
                "fixed source-to-sink target profile is unavailable"
            )
        case_executor = AttackCaseExecutor(
            provider=self.provider,
            actors=data.actors,
            retriever=retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            contract=contract,
            profiles=profiles,
        )
        plan_executor = AttackPlanExecutor(case_executor)
        return _StabilityDependencies(
            contract=contract,
            retriever=retriever,
            plan=plan,
            orchestrator=RedTeamOrchestrator(
                plan_executor=plan_executor,
                variant_generator=LLMAttackVariantGenerator(self.provider),
                contract=contract,
                provider=self.provider,
            ),
            replay_executor=ReplayExecutor(
                plan_executor=plan_executor,
                contract=contract,
            ),
            history=SQLiteAuditRunRepository(workspace.history_db_path),
            runtime_snapshot=_runtime_snapshot(self.provider, retriever),
            target_profile_snapshot=_target_profile_snapshot(profile),
        )

    @staticmethod
    def _iteration_projection(
        *,
        iteration: int,
        plan: AttackPlan,
        scan: RedTeamScan | None,
        replay: ReplayResult | None,
        persisted_replay: PersistedReplay | None,
        history_persisted: bool,
        history_count: int,
        duration_ms: float,
        failure: StabilityFailure | None,
    ) -> StabilityIteration:
        findings = _findings(scan) if scan is not None else []
        categories: list[FindingCategory] = []
        for finding in findings:
            if finding.category not in categories:
                categories.append(finding.category)
        trace_count = _trace_event_count(scan) if scan is not None else 0
        return StabilityIteration(
            iteration=iteration,
            status="passed" if failure is None else "failed",
            plan_id=plan.id,
            scan_id=scan.id if scan is not None else None,
            replay_id=persisted_replay.id if persisted_replay is not None else None,
            replay_result_id=replay.id if replay is not None else None,
            scan_stop_reason=scan.stop_reason if scan is not None else None,
            attempt_count=len(scan.attempts) if scan is not None else 0,
            trace_event_count=trace_count,
            finding_count=len(findings),
            finding_categories=categories,
            source_sink_finding="external_sink_policy_violation" in categories,
            replay_status=replay.status if replay is not None else None,
            replay_before_evaluation=(
                replay.before.evaluation.status if replay is not None else None
            ),
            replay_after_evaluation=(
                replay.after.evaluation.status if replay is not None else None
            ),
            replay_after_execution=(
                replay.after.execution_status if replay is not None else None
            ),
            history_persisted=history_persisted,
            history_count=history_count,
            duration_ms=duration_ms,
            failure=failure,
        )

    async def run(self) -> StabilityEvidence:
        """Run the explicit deterministic workflow soak and return one DTO."""

        started_at = _utc_now()
        started_clock = time.perf_counter()
        tracing_started_here, memory_start = _memory_start()
        iterations: list[StabilityIteration] = []
        failures: list[StabilityFailure] = []
        successful_workflows = 0
        finding_count = 0
        replay_pass_count = 0
        persisted_count = 0
        history_count = 0
        duration_samples: list[float] = []
        dataset_document_count = 0
        workspace_mode: Literal["temporary", "explicit"] = (
            "explicit" if self.workspace_root is not None else "temporary"
        )

        try:
            with self._workspace() as workspace:
                dependencies = self._build_dependencies(workspace)
                dataset_document_count = dependencies.retriever.metadata.indexed_document_count
                for iteration_number in range(1, self.iterations + 1):
                    iteration_started = time.perf_counter()
                    scan: RedTeamScan | None = None
                    replay: ReplayResult | None = None
                    persisted_replay: PersistedReplay | None = None
                    iteration_failure: StabilityFailure | None = None
                    stage = "scan"
                    try:
                        scan = await dependencies.orchestrator.run(
                            dependencies.plan.model_copy(deep=True),
                            max_rounds=self.max_rounds,
                        )
                        _validate_actual_scan(scan, dependencies.plan)
                        stage = "replay"
                        replay = await dependencies.replay_executor.replay(
                            dependencies.plan.model_copy(deep=True)
                        )
                        _validate_actual_replay(replay, dependencies.plan)
                        stage = "history"
                        detail = AuditRunDetail(
                            scan=scan,
                            plan_snapshot=dependencies.plan.model_copy(deep=True),
                            contract_snapshot=dependencies.contract.model_copy(deep=True),
                            target_profile_snapshot=dependencies.target_profile_snapshot.model_copy(
                                deep=True
                            ),
                            runtime_snapshot=dependencies.runtime_snapshot.model_copy(deep=True),
                            replays=[],
                        )
                        dependencies.history.save(detail)
                        persisted_replay = PersistedReplay(
                            id=f"stability_replay_{uuid.uuid4().hex[:12]}",
                            created_at=_utc_now(),
                            replay=replay,
                        )
                        dependencies.history.append_replay(scan.id, persisted_replay)
                        stored = dependencies.history.get(scan.id)
                        if stored is None or len(stored.replays) != 1:
                            raise StabilityHistoryError(
                                "persisted scan/replay could not be read back"
                            )
                        persisted_count += 1
                        history_count = persisted_count
                        successful_workflows += 1
                        finding_count += len(_findings(scan))
                        replay_pass_count += int(replay.status == "passed")
                    except Exception as exc:
                        iteration_failure = _failure(iteration_number, stage, exc)
                        failures.append(iteration_failure)
                    duration_ms = round(
                        max(0.0, (time.perf_counter() - iteration_started) * 1000),
                        2,
                    )
                    duration_samples.append(duration_ms)
                    iterations.append(
                        self._iteration_projection(
                            iteration=iteration_number,
                            plan=dependencies.plan,
                            scan=scan,
                            replay=replay,
                            persisted_replay=persisted_replay,
                            history_persisted=iteration_failure is None and persisted_replay is not None,
                            history_count=history_count,
                            duration_ms=duration_ms,
                            failure=iteration_failure,
                        )
                    )

                try:
                    recent_history_count = len(
                        dependencies.history.list(limit=min(MAX_ITERATIONS, self.iterations))
                    )
                    if recent_history_count != min(MAX_ITERATIONS, persisted_count):
                        raise StabilityHistoryError(
                            "persisted history summary count is inconsistent"
                        )
                    history_count = persisted_count
                except Exception as exc:
                    final_failure = _failure(self.iterations, "history_summary", exc)
                    failures.append(final_failure)
        finally:
            memory_end = _memory_end(tracing_started_here)

        completed_at = _utc_now()
        check = StabilityCheck(
            id=STABILITY_CHECK_ID,
            status="passed" if not failures and successful_workflows == self.iterations else "failed",
            iterations=self.iterations,
            completed_iterations=successful_workflows,
            failures=failures,
        )
        status: Literal["passed", "failed"] = "passed" if check.status == "passed" else "failed"
        retriever_label = "tfidf_test_retriever"
        if "dependencies" in locals() and dependencies.retriever.engine_id != "tfidf":
            retriever_label = f"deterministic_{dependencies.retriever.engine_id}_retriever"
        return StabilityEvidence(
            id=f"stability_{uuid.uuid4().hex[:12]}",
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            environment=StabilityEnvironment(
                platform=sys.platform or platform_module.system(),
                machine=platform_module.machine(),
                python=platform_module.python_version(),
                artifact=None,
                provider=self.provider_id,
                retriever=retriever_label,
                workspace=workspace_mode,
                deterministic=True,
            ),
            checks=[check],
            observations=StabilityObservations(
                duration_ms=round(max(0.0, (time.perf_counter() - started_clock) * 1000), 2),
                duration_p50_ms=_percentile(duration_samples, 0.50),
                duration_p95_ms=_percentile(duration_samples, 0.95),
                duration_sample_count=len(duration_samples),
                repetition_count=self.iterations,
                memory_start_bytes=memory_start,
                memory_end_bytes=memory_end,
                handle_count=None,
                process_count=1,
                dataset_document_count=dataset_document_count,
                dataset_history_rows=history_count,
                history_count=history_count,
                provider_call_count=len(getattr(self.provider, "calls", ())),
                successful_workflows=successful_workflows,
                finding_count=finding_count,
                replay_pass_count=replay_pass_count,
            ),
            iterations=iterations,
            failures=failures,
            limitations=[
                f"非真实模型稳定性：本次使用明确标记的 {self.provider_id}，不代表 Ollama、DeepSeek 或其他真实模型的稳定性。",
                "Core Runner 未执行 Desktop/Sidecar artifact 生命周期；该证据由显式 Desktop Runner 单独提供。",
                "memory 字段是 Python tracemalloc 当前分配观察值，不是进程 working set 或系统级内存保证。",
                "p50/p95 仅对本次运行的逐轮 wall-clock duration 样本做线性插值，不是硬件级、SLO 或长期稳定性结论。",
                "handle_count 未采集；process_count 仅表示本 Runner 进程，不包含系统其他进程。",
                "默认 Workspace 与 SQLite 均为本次运行创建的临时隔离副本，运行结束后不保留。",
            ],
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


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines.extend(
        "| " + " | ".join(_markdown_cell(value) for value in row) + " |"
        for row in rows
    )
    return lines


def render_stability_markdown(evidence: StabilityEvidence) -> str:
    """Render Markdown only from the supplied JSON-equivalent Evidence DTO."""

    lines = [
        "# 知盾 AgentAudit Stability Run",
        "",
        f"非真实模型稳定性：本工件使用明确标记的 `{evidence.environment.provider}`，不代表 Ollama、DeepSeek 或其他真实模型的稳定性。",
        "",
        "## Run",
        "",
    ]
    lines.extend(
        _markdown_table(
            ("Field", "Value"),
            (
                ("ID", evidence.id),
                ("Status", evidence.status),
                ("Started At", evidence.started_at),
                ("Completed At", evidence.completed_at),
            ),
        )
    )
    lines.extend(["", "## Environment", ""])
    lines.extend(
        _markdown_table(
            ("Field", "Value"),
            (
                ("Platform", evidence.environment.platform),
                ("Python", evidence.environment.python),
                ("Provider", evidence.environment.provider),
                ("Retriever", evidence.environment.retriever),
                ("Workspace", evidence.environment.workspace),
                ("Artifact", evidence.environment.artifact),
            ),
        )
    )
    lines.extend(
        [
            "",
            "本次默认使用本地 `tfidf_test_retriever` 作为确定性测试索引，不代表生产 Embedding Retriever 性能。",
            "",
            "## Checks",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            ("Check", "Status", "Iterations", "Completed", "Failures"),
            tuple(
                (check.id, check.status, check.iterations, check.completed_iterations, len(check.failures))
                for check in evidence.checks
            ),
        )
    )
    lines.extend(["", "## Observations", ""])
    observation_values = (
        ("durationMs", evidence.observations.duration_ms),
        ("durationP50Ms", evidence.observations.duration_p50_ms),
        ("durationP95Ms", evidence.observations.duration_p95_ms),
        ("durationSampleCount", evidence.observations.duration_sample_count),
        ("repetitionCount", evidence.observations.repetition_count),
        ("memoryStartBytes", evidence.observations.memory_start_bytes),
        ("memoryEndBytes", evidence.observations.memory_end_bytes),
        ("memoryMetric", evidence.observations.memory_metric),
        ("memoryObservationMethod", evidence.observations.memory_observation_method),
        ("handleCount", evidence.observations.handle_count),
        ("handleObservationMethod", evidence.observations.handle_observation_method),
        ("processCount", evidence.observations.process_count),
        ("processObservationMethod", evidence.observations.process_observation_method),
        ("datasetDocumentCount", evidence.observations.dataset_document_count),
        ("datasetHistoryRows", evidence.observations.dataset_history_rows),
        ("historySource", evidence.observations.history_source),
        ("databaseObservationMethod", evidence.observations.database_observation_method),
        ("historyCount", evidence.observations.history_count),
        ("providerCallCount", evidence.observations.provider_call_count),
        ("successfulWorkflows", evidence.observations.successful_workflows),
        ("findingCount", evidence.observations.finding_count),
        ("replayPassCount", evidence.observations.replay_pass_count),
    )
    lines.extend(_markdown_table(("Metric", "Value"), observation_values))
    lines.extend(["", "## Iterations", ""])
    lines.extend(
        _markdown_table(
            ("#", "Status", "Scan ID", "Replay ID", "Finding", "Replay", "History", "Duration ms"),
            tuple(
                (
                    item.iteration,
                    item.status,
                    item.scan_id,
                    item.replay_id,
                    "source_sink" if item.source_sink_finding else "none",
                    item.replay_status,
                    item.history_count,
                    item.duration_ms,
                )
                for item in evidence.iterations
            ),
        )
    )
    lines.extend(["", "## Failures", ""])
    if evidence.failures:
        lines.extend(
            _markdown_table(
                ("Iteration", "Stage", "Category", "Error", "Detail"),
                tuple(
                    (failure.iteration, failure.stage, failure.category, failure.error_type, failure.detail)
                    for failure in evidence.failures
                ),
            )
        )
    else:
        lines.append("无失败记录。")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in evidence.limitations)
    lines.append("")
    return "\n".join(lines)


class StabilityArtifactWriter:
    """Write only the JSON source and Markdown projection for one run."""

    def __init__(self, output_dir: str | Path = DEFAULT_STABILITY_OUTPUT_DIR) -> None:
        self.output_dir = Path(output_dir)

    def write(self, evidence: StabilityEvidence) -> tuple[Path, Path]:
        if not isinstance(evidence, StabilityEvidence):
            raise TypeError("evidence must be a StabilityEvidence")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.output_dir / f"{evidence.id}{STABILITY_JSON_SUFFIX}"
        markdown_path = self.output_dir / f"{evidence.id}{STABILITY_MARKDOWN_SUFFIX}"
        payload = json.dumps(
            evidence.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        json_path.write_text(payload + "\n", encoding="utf-8")
        markdown_path.write_text(render_stability_markdown(evidence), encoding="utf-8")
        return json_path, markdown_path


def write_stability_artifacts(
    evidence: StabilityEvidence,
    output_dir: str | Path = DEFAULT_STABILITY_OUTPUT_DIR,
) -> tuple[Path, Path]:
    """Write the two F-036 artifacts while preserving unrelated files."""

    return StabilityArtifactWriter(output_dir).write(evidence)


async def run_stability_runner(
    *,
    iterations: int = DEFAULT_ITERATIONS,
    max_rounds: Literal[2, 3] = 3,
    provider: LLMProvider | None = None,
    retriever: Retriever | None = None,
    workspace_root: str | Path | None = None,
    long_soak: bool = False,
) -> StabilityEvidence:
    """Convenience entrypoint for callers that want one explicit run."""

    return await StabilityRunner(
        iterations=iterations,
        max_rounds=max_rounds,
        provider=provider,
        retriever=retriever,
        workspace_root=workspace_root,
        long_soak=long_soak,
    ).run()


__all__ = [
    "DEFAULT_ITERATIONS",
    "DEFAULT_STABILITY_OUTPUT_DIR",
    "MAX_ITERATIONS",
    "MAX_LONG_SOAK_ITERATIONS",
    "STABILITY_CHECK_ID",
    "STABILITY_JSON_SUFFIX",
    "STABILITY_MARKDOWN_SUFFIX",
    "DeterministicStabilityProvider",
    "StabilityArtifactWriter",
    "StabilityCheck",
    "StabilityConfigurationError",
    "StabilityEnvironment",
    "StabilityEvidence",
    "StabilityFailure",
    "StabilityHistoryError",
    "StabilityInvariantError",
    "StabilityIteration",
    "StabilityObservations",
    "StabilityRunner",
    "render_stability_markdown",
    "run_stability_runner",
    "write_stability_artifacts",
]
