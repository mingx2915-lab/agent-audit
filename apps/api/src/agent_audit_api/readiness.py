"""Explicit Provider readiness probes for the controlled demo target.

Readiness is an observable compatibility check, not a security decision or a
new execution gate.  Every probe makes one real call to the Provider assigned
to its role.  Provider failures are recorded on the probe; unexpected
exceptions are deliberately allowed to propagate so that programming errors do
not get reported as model compatibility evidence.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import Field

from .planning import AttackPlan
from .provider_diagnostics import provider_error_diagnostic
from .providers.base import LLMProvider, LLMResponse, ProviderError, ProviderResponseError
from .red_team import provider_metadata
from .schemas import CamelModel


ProbeId = Literal[
    "target.connectivity",
    "target.tool_calling",
    "attack.connectivity",
    "attack.strict_json",
]
ProbeStatus = Literal["passed", "failed"]
ProviderRole = Literal["target", "attack"]
ProviderRoleStatus = Literal["ready", "partial", "unavailable"]
PlanCompatibilityStatus = Literal["compatible", "incompatible"]


class ProviderProbeResult(CamelModel):
    """Result of one strict, single-call Provider probe."""

    id: ProbeId
    status: ProbeStatus
    duration_ms: float = Field(ge=0)
    detail: str | None = None


class ProviderRoleReadiness(CamelModel):
    """Readiness summary for one isolated Provider role."""

    role: ProviderRole
    provider: str
    model: str | None
    status: ProviderRoleStatus
    probes: list[ProviderProbeResult]


class PlanCompatibilityResult(CamelModel):
    """Compatibility of one active Contract-derived Attack Plan."""

    plan_id: str
    basis_type: str
    status: PlanCompatibilityStatus
    required_probe_ids: list[ProbeId]
    failed_probe_ids: list[ProbeId]


class ProviderReadinessResult(CamelModel):
    """Complete non-persistent result returned by one readiness run."""

    id: str
    checked_at: str
    status: ProviderRoleStatus
    target_provider: ProviderRoleReadiness
    attack_provider: ProviderRoleReadiness
    plan_compatibility: list[PlanCompatibilityResult]


class EmptyProviderReadinessRequest(CamelModel):
    """Strict empty request body for the explicit readiness endpoint."""


_READINESS_NONCE = "agent-audit-readiness"
_READINESS_TOOL_NAME = "agent_audit_readiness_probe"

_READINESS_TOOL: Mapping[str, object] = {
    "type": "function",
    "function": {
        "name": _READINESS_TOOL_NAME,
        "description": "Synthetic tool used only to verify native Tool Calling support.",
        "parameters": {
            "type": "object",
            "properties": {
                "nonce": {
                    "type": "string",
                },
            },
            "required": ["nonce"],
            "additionalProperties": False,
        },
    },
}

_CONNECTIVITY_MESSAGES: tuple[dict[str, str], ...] = (
    {
        "role": "system",
        "content": (
            "You are responding to an AgentAudit Provider readiness probe. "
            "Return a short non-empty text response."
        ),
    },
    {
        "role": "user",
        "content": "Connectivity probe: respond with any non-empty text.",
    },
)

_TOOL_CALLING_MESSAGES: tuple[dict[str, str], ...] = (
    {
        "role": "system",
        "content": (
            "You are responding to an AgentAudit Tool Calling readiness probe. "
            "Call the supplied synthetic tool exactly once with the requested nonce."
        ),
    },
    {
        "role": "user",
        "content": (
            "Call agent_audit_readiness_probe exactly once with "
            '{"nonce":"agent-audit-readiness"}.'
        ),
    },
)

_STRICT_JSON_MESSAGES: tuple[dict[str, str], ...] = (
    {
        "role": "system",
        "content": (
            "You are responding to an AgentAudit strict JSON readiness probe. "
            "Return only the exact bare JSON object requested by the user, with "
            "no Markdown or explanation."
        ),
    },
    {
        "role": "user",
        "content": (
            'Return exactly {"status":"ready","nonce":"agent-audit-readiness"} '
            "as a bare JSON object."
        ),
    },
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_ms(started: float) -> float:
    """Return a non-negative, compact duration for one probe."""

    return round(max(0.0, (time.perf_counter() - started) * 1000), 2)


def _strict_json_object(content: str) -> dict[str, Any]:
    """Parse one strict JSON object without repairing or extracting output."""

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        payload = json.loads(content, parse_constant=reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProviderResponseError(
            "attack strict JSON probe response must be one strict JSON object"
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderResponseError(
            "attack strict JSON probe response must be a JSON object"
        )
    return payload


def _role_status(probes: Sequence[ProviderProbeResult]) -> ProviderRoleStatus:
    passed = sum(probe.status == "passed" for probe in probes)
    if passed == len(probes):
        return "ready"
    if passed == 0:
        return "unavailable"
    return "partial"


def _overall_status(
    target_status: ProviderRoleStatus,
    attack_status: ProviderRoleStatus,
) -> ProviderRoleStatus:
    if target_status == "ready" and attack_status == "ready":
        return "ready"
    if target_status == "unavailable" and attack_status == "unavailable":
        return "unavailable"
    return "partial"


def _required_probe_ids(basis_type: str) -> tuple[ProbeId, ...]:
    """Map each active Plan category to its fixed Provider requirements."""

    if basis_type == "resource_owner_scope":
        return (
            "target.connectivity",
            "attack.connectivity",
            "attack.strict_json",
        )
    return (
        "target.connectivity",
        "target.tool_calling",
        "attack.connectivity",
        "attack.strict_json",
    )


class ProviderReadinessRunner:
    """Run isolated Target and Attack Provider probes and derive compatibility."""

    def __init__(
        self,
        target_provider: LLMProvider,
        attack_provider: LLMProvider,
        plans: Sequence[AttackPlan],
    ) -> None:
        self._target_provider = target_provider
        self._attack_provider = attack_provider
        self._plans = tuple(plans)

    async def _run_probe(
        self,
        *,
        provider: LLMProvider,
        probe_id: ProbeId,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, object]] | None,
    ) -> ProviderProbeResult:
        started = time.perf_counter()
        provider_kind, _ = provider_metadata(provider)
        try:
            response = await provider.complete(messages, tools=tools)
            self._validate_probe_response(probe_id, response)
        except ProviderError as exc:
            return ProviderProbeResult(
                id=probe_id,
                status="failed",
                duration_ms=_duration_ms(started),
                detail=provider_error_diagnostic(
                    exc,
                    stage="readiness",
                    provider_kind=provider_kind,
                    probe_id=probe_id,
                ),
            )
        return ProviderProbeResult(
            id=probe_id,
            status="passed",
            duration_ms=_duration_ms(started),
        )

    @staticmethod
    def _validate_probe_response(probe_id: ProbeId, response: object) -> None:
        if not isinstance(response, LLMResponse):
            raise ProviderResponseError("provider returned an invalid response")

        if probe_id in ("target.connectivity", "attack.connectivity"):
            if response.tool_calls:
                raise ProviderResponseError(
                    f"{probe_id} probe received an unexpected Tool Call"
                )
            if not isinstance(response.content, str) or not response.content.strip():
                raise ProviderResponseError(
                    f"{probe_id} probe response content is empty"
                )
            return

        if probe_id == "target.tool_calling":
            if len(response.tool_calls) != 1:
                raise ProviderResponseError(
                    "target.tool_calling probe requires exactly one Tool Call"
                )
            tool_call = response.tool_calls[0]
            if tool_call.name != _READINESS_TOOL_NAME:
                raise ProviderResponseError(
                    "target.tool_calling probe returned an unexpected tool"
                )
            if dict(tool_call.arguments) != {"nonce": _READINESS_NONCE}:
                raise ProviderResponseError(
                    "target.tool_calling probe arguments do not match the nonce"
                )
            return

        if response.tool_calls:
            raise ProviderResponseError(
                "attack.strict_json probe received an unexpected Tool Call"
            )
        if not isinstance(response.content, str) or not response.content:
            raise ProviderResponseError(
                "attack.strict_json probe response content is empty"
            )
        payload = _strict_json_object(response.content)
        if payload != {"status": "ready", "nonce": _READINESS_NONCE}:
            raise ProviderResponseError(
                "attack.strict_json probe response fields do not match the required object"
            )

    async def run(self) -> ProviderReadinessResult:
        """Execute all four probes once and derive role/plan statuses."""

        target_probes = [
            await self._run_probe(
                provider=self._target_provider,
                probe_id="target.connectivity",
                messages=_CONNECTIVITY_MESSAGES,
                tools=None,
            ),
            await self._run_probe(
                provider=self._target_provider,
                probe_id="target.tool_calling",
                messages=_TOOL_CALLING_MESSAGES,
                tools=[_READINESS_TOOL],
            ),
        ]
        attack_probes = [
            await self._run_probe(
                provider=self._attack_provider,
                probe_id="attack.connectivity",
                messages=_CONNECTIVITY_MESSAGES,
                tools=None,
            ),
            await self._run_probe(
                provider=self._attack_provider,
                probe_id="attack.strict_json",
                messages=_STRICT_JSON_MESSAGES,
                tools=None,
            ),
        ]

        target_name, target_model = provider_metadata(self._target_provider)
        attack_name, attack_model = provider_metadata(self._attack_provider)
        target_readiness = ProviderRoleReadiness(
            role="target",
            provider=target_name,
            model=target_model,
            status=_role_status(target_probes),
            probes=target_probes,
        )
        attack_readiness = ProviderRoleReadiness(
            role="attack",
            provider=attack_name,
            model=attack_model,
            status=_role_status(attack_probes),
            probes=attack_probes,
        )
        probes_by_id = {
            probe.id: probe for probe in (*target_probes, *attack_probes)
        }
        plan_compatibility: list[PlanCompatibilityResult] = []
        for plan in self._plans:
            required = _required_probe_ids(plan.basis_type)
            failed = tuple(
                probe_id
                for probe_id in required
                if probes_by_id[probe_id].status == "failed"
            )
            plan_compatibility.append(
                PlanCompatibilityResult(
                    plan_id=plan.id,
                    basis_type=plan.basis_type,
                    status="compatible" if not failed else "incompatible",
                    required_probe_ids=list(required),
                    failed_probe_ids=list(failed),
                )
            )

        return ProviderReadinessResult(
            id=f"readiness_{uuid.uuid4().hex}",
            checked_at=_utc_now(),
            status=_overall_status(target_readiness.status, attack_readiness.status),
            target_provider=target_readiness,
            attack_provider=attack_readiness,
            plan_compatibility=plan_compatibility,
        )


__all__ = [
    "EmptyProviderReadinessRequest",
    "PlanCompatibilityResult",
    "ProviderProbeResult",
    "ProviderReadinessResult",
    "ProviderReadinessRunner",
    "ProviderRoleReadiness",
]
