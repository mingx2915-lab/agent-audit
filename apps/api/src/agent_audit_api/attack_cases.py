"""Fixed synthetic attack cases and their bounded execution adapter."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from .domain import DemoActor
from .evaluation import FindingCategory, HybridJudge, TraceEvaluationResult
from .providers.base import LLMProvider
from .retrieval import Retriever
from .schemas import AssistantQueryResult, CamelModel
from .security_contract import SecurityContract
from .services.assistant import AssistantService
from .target import TargetProfile
from .tools import MockCustomerExportTool, MockCustomerTool, MockMailTool


class AttackCase(CamelModel):
    """One fixed, repository-owned attacker scenario."""

    id: str
    name: str
    description: str
    attacker_type: Literal["outside_in", "inside_out"]
    actor_id: str
    message: str
    target_profile_id: str
    expected_finding_categories: list[FindingCategory]


class AttackExecutionResult(CamelModel):
    """The actual query trace and deterministic evaluation for one case."""

    case: AttackCase
    query_result: AssistantQueryResult
    evaluation: TraceEvaluationResult


class AttackCaseLoadError(ValueError):
    """Raised when fixed attack data is malformed or unavailable."""


class AttackCaseExecutionError(ValueError):
    """Raised when a fixed case cannot be executed with the supplied data."""


def _repo_root() -> Path:
    # attack_cases.py lives at <repo>/apps/api/src/agent_audit_api/.
    return Path(__file__).resolve().parents[4]


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise AttackCaseLoadError(f"unable to load {path.name}") from exc


def _load_list(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise AttackCaseLoadError(f"{path.name} must contain an array")
    if not all(isinstance(item, dict) for item in payload):
        raise AttackCaseLoadError(f"{path.name} items must be objects")
    return payload


def load_attack_cases(data_dir: str | Path | None = None) -> tuple[AttackCase, ...]:
    """Load fixed Outside-in and Inside-out cases from one data root."""

    directory = Path(data_dir) if data_dir is not None else _repo_root() / "data" / "demo"
    try:
        return tuple(AttackCase.model_validate(item) for item in _load_list(directory / "attack_cases.json"))
    except ValueError as exc:
        raise AttackCaseLoadError("attack_cases.json is invalid") from exc


def load_target_profiles(data_dir: str | Path | None = None) -> tuple[TargetProfile, ...]:
    """Load fixed secure and observe-only profiles from one data root."""

    directory = Path(data_dir) if data_dir is not None else _repo_root() / "data" / "demo"
    try:
        return tuple(
            TargetProfile.model_validate(item)
            for item in _load_list(directory / "target_profiles.json")
        )
    except ValueError as exc:
        raise AttackCaseLoadError("target_profiles.json is invalid") from exc


class AttackCaseExecutor:
    """Execute only a supplied fixed case against repository-owned actors/profiles."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        actors: Sequence[DemoActor],
        retriever: Retriever,
        customer_tool: MockCustomerTool,
        mail_tool: MockMailTool | None = None,
        export_tool: MockCustomerExportTool | None = None,
        contract: SecurityContract,
        profiles: Sequence[TargetProfile],
    ) -> None:
        self._provider = provider
        self._actors = {actor.id: actor for actor in actors}
        self._retriever = retriever
        self._customer_tool = customer_tool
        self._mail_tool = mail_tool
        self._export_tool = export_tool
        self._contract = contract
        self._profiles = {profile.id: profile for profile in profiles}
        if len(self._actors) != len(tuple(actors)):
            raise AttackCaseExecutionError("duplicate actor id")
        if len(self._profiles) != len(tuple(profiles)):
            raise AttackCaseExecutionError("duplicate target profile id")

    async def execute(self, case: AttackCase) -> AttackExecutionResult:
        """Run the case through the real Target Agent and offline Hybrid Judge."""

        if not isinstance(case, AttackCase):
            raise TypeError("case must be an AttackCase")
        actor = self._actors.get(case.actor_id)
        if actor is None:
            raise AttackCaseExecutionError("attack case references an unknown actor")
        profile = self._profiles.get(case.target_profile_id)
        if profile is None:
            raise AttackCaseExecutionError("attack case references an unknown target profile")

        service = AssistantService(
            provider=self._provider,
            actors=self._actors.values(),
            retriever=self._retriever,
            customer_tool=self._customer_tool,
            mail_tool=self._mail_tool,
            export_tool=self._export_tool,
            contract=self._contract,
            target_profile=profile,
        )
        query_result = await service.answer(actor.id, case.message)
        evaluation = await HybridJudge(None).evaluate(
            contract=self._contract,
            trace_events=query_result.trace_events,
            include_semantic_review=False,
        )
        return AttackExecutionResult(
            case=case,
            query_result=query_result,
            evaluation=evaluation,
        )

__all__ = [
    "AttackCase",
    "AttackCaseExecutionError",
    "AttackCaseExecutor",
    "AttackCaseLoadError",
    "AttackExecutionResult",
    "TargetProfile",
    "load_attack_cases",
    "load_target_profiles",
]
