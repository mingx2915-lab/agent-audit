"""HTTP outcomes for expected policy stops; internal executors still raise."""
from typing import Literal

from .attack_cases import AttackCase
from .evaluation import TraceEvaluationResult
from .planning import AttackPlan
from .schemas import CamelModel, TraceEvent


class BlockedExecution(CamelModel):
    execution_status: Literal['blocked'] = 'blocked'
    query_result: None = None
    blocked_reason: str
    trace_events: list[TraceEvent]
    evaluation: TraceEvaluationResult


class BlockedCaseExecution(BlockedExecution):
    case: AttackCase


class BlockedPlanExecution(BlockedExecution):
    plan: AttackPlan
