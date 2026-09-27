"""Deterministic remediation reference and same-plan simulated replay."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from .evaluation import HybridJudge, TraceEvaluationResult
from .planning import AttackPlan, AttackPlanExecutionResult, AttackPlanExecutor
from .schemas import AssistantQueryResult, CamelModel, TraceEvent
from .security_contract import SecurityContract
from .services.assistant import ToolAuthorizationError


ConfigurationPath = Literal[
    "targetProfile.enforceResourceAuthorization",
    "targetProfile.enforceToolAuthorization",
    "targetProfile.enforceSinkAuthorization",
]


class RemediationRecommendation(CamelModel):
    id: str
    title: str
    summary: str
    configuration_path: ConfigurationPath
    before_value: bool
    after_value: bool


class ReplayAttempt(CamelModel):
    profile_id: str
    execution_status: Literal["completed", "blocked"]
    query_result: AssistantQueryResult | None
    trace_events: list[TraceEvent]
    evaluation: TraceEvaluationResult
    blocked_reason: str | None


class ReplayResult(CamelModel):
    id: str
    plan: AttackPlan
    remediation: RemediationRecommendation
    before: ReplayAttempt
    after: ReplayAttempt
    status: Literal["passed", "failed"]


def build_remediation(plan: AttackPlan) -> RemediationRecommendation:
    """Build a Contract-based enforcement reference for simulated replay."""

    if plan.basis_type == "resource_owner_scope":
        return RemediationRecommendation(
            id=f"remediation_{plan.id}",
            title="开启资源授权阻断",
            summary="将资源授权 enforcement 从 false 调整为 true，阻止 denied 文档进入模型上下文。",
            configuration_path="targetProfile.enforceResourceAuthorization",
            before_value=False,
            after_value=True,
        )
    if plan.basis_type == "source_sink":
        return RemediationRecommendation(
            id=f"remediation_{plan.id}",
            title="开启外部 Sink 授权阻断",
            summary="将 Sink authorization enforcement 从 false 调整为 true，阻止未批准或不可信来源驱动的外部动作。",
            configuration_path="targetProfile.enforceSinkAuthorization",
            before_value=False,
            after_value=True,
        )
    if plan.basis_type == "tool_record_limit":
        return RemediationRecommendation(
            id=f"remediation_{plan.id}",
            title="开启工具业务约束阻断",
            summary="将 Tool authorization enforcement 从 false 调整为 true，阻止超过 maxRecords 的批量导出。",
            configuration_path="targetProfile.enforceToolAuthorization",
            before_value=False,
            after_value=True,
        )
    return RemediationRecommendation(
        id=f"remediation_{plan.id}",
        title="开启工具授权阻断",
        summary="将工具授权 enforcement 从 false 调整为 true，阻止 denied Tool Call 执行。",
        configuration_path="targetProfile.enforceToolAuthorization",
        before_value=False,
        after_value=True,
    )


class ReplayExecutor:
    """Run the same plan first with its profile and then with ``secure``."""

    def __init__(
        self,
        *,
        plan_executor: AttackPlanExecutor,
        contract: SecurityContract,
    ) -> None:
        self._plan_executor = plan_executor
        self._contract = contract

    @staticmethod
    def _copy_trace(events: Sequence[TraceEvent]) -> list[TraceEvent]:
        return [event.model_copy(deep=True) for event in events]

    async def _attempt(self, plan: AttackPlan) -> ReplayAttempt:
        try:
            result: AttackPlanExecutionResult = await self._plan_executor.execute(plan)
        except ToolAuthorizationError as exc:
            trace_events = tuple(exc.trace_events)
            evaluation = await HybridJudge(None).evaluate(
                contract=self._contract,
                trace_events=trace_events,
                include_semantic_review=False,
            )
            return ReplayAttempt(
                profile_id=plan.target_profile_id,
                execution_status="blocked",
                query_result=None,
                trace_events=self._copy_trace(trace_events),
                evaluation=evaluation,
                blocked_reason=str(exc),
            )

        return ReplayAttempt(
            profile_id=plan.target_profile_id,
            execution_status="completed",
            query_result=result.query_result,
            trace_events=self._copy_trace(result.query_result.trace_events),
            evaluation=result.evaluation,
            blocked_reason=None,
        )

    async def replay(self, plan: AttackPlan) -> ReplayResult:
        """Replay without mutating the supplied plan or active Contract."""

        if not isinstance(plan, AttackPlan):
            raise TypeError("plan must be an AttackPlan")
        before = await self._attempt(plan)
        after_plan = plan.model_copy(update={"target_profile_id": "secure"})
        after = await self._attempt(after_plan)
        status: Literal["passed", "failed"] = (
            "passed"
            if before.evaluation.status == "failed"
            and after.evaluation.status == "passed"
            else "failed"
        )
        return ReplayResult(
            id=f"replay_{plan.id}",
            plan=plan,
            remediation=build_remediation(plan),
            before=before,
            after=after,
            status=status,
        )


__all__ = [
    "RemediationRecommendation",
    "ReplayAttempt",
    "ReplayExecutor",
    "ReplayResult",
    "build_remediation",
]
