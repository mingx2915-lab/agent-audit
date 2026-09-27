"""Security Contract schema, loader, and deterministic authorization evaluator."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, StrictBool, field_validator, model_validator

from .schemas import ActorRole, CamelModel


def _non_empty(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty")
    return value


def _non_empty_strings(value: list[str]) -> list[str]:
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("must contain non-empty strings")
    return value


class ContractRole(CamelModel):
    id: ActorRole
    display_name: str

    _validate_display_name = field_validator("display_name")(_non_empty)


class ResourceRule(CamelModel):
    id: str
    description: str
    match_labels: list[str]
    allowed_roles: list[ActorRole]
    require_owner_match: StrictBool

    _validate_id = field_validator("id", "description")(_non_empty)
    _validate_labels = field_validator("match_labels")(_non_empty_strings)


class ToolRule(CamelModel):
    id: str
    description: str
    tool_name: str
    action: str
    allowed_roles: list[ActorRole]
    require_owner_match: StrictBool
    max_records: int | None = Field(default=None, ge=1)
    require_approval: StrictBool = False

    _validate_text = field_validator("id", "description", "tool_name", "action")(_non_empty)


SinkType = Literal["external_message", "customer_export"]


class SinkRule(CamelModel):
    """Deterministic policy for one controlled Tool/Sink destination."""

    id: str
    description: str
    sink_type: SinkType
    match_labels: list[str]
    allowed_roles: list[ActorRole]
    allow_external: StrictBool
    require_approval: StrictBool
    blocked_source_trust_levels: list[str]

    _validate_text = field_validator("id", "description")(_non_empty)
    _validate_labels = field_validator(
        "match_labels", "blocked_source_trust_levels"
    )(_non_empty_strings)


class SecurityContract(CamelModel):
    id: str
    name: str
    version: int = Field(gt=0)
    roles: list[ContractRole]
    resource_rules: list[ResourceRule]
    tool_rules: list[ToolRule]
    sink_rules: list[SinkRule] = Field(default_factory=list)

    _validate_text = field_validator("id", "name")(_non_empty)

    @model_validator(mode="after")
    def validate_rule_references_and_ids(self) -> "SecurityContract":
        role_ids = [role.id for role in self.roles]
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("duplicate role id")
        known_roles = set(role_ids)

        rule_ids = [
            rule.id
            for rule in [*self.resource_rules, *self.tool_rules, *self.sink_rules]
        ]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("duplicate rule id")
        for rule in [*self.resource_rules, *self.tool_rules, *self.sink_rules]:
            unknown_roles = set(rule.allowed_roles) - known_roles
            if unknown_roles:
                unknown = ", ".join(sorted(unknown_roles))
                raise ValueError(f"unknown allowed role: {unknown}")
        return self


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    rule_id: str | None
    reason: str | None = None
    max_records: int | None = None
    require_approval: bool = False


class ContractEvaluator:
    """Evaluate resource and tool access using only the active contract."""

    def __init__(self, contract: SecurityContract) -> None:
        self.contract = contract

    def authorize_resource(
        self,
        *,
        actor_role: str,
        actor_id: str,
        resource_labels: Sequence[str],
        resource_owner_id: str | None,
    ) -> AuthorizationDecision:
        labels = set(resource_labels)
        for rule in self.contract.resource_rules:
            if not all(label in labels for label in rule.match_labels):
                continue
            if actor_role not in rule.allowed_roles:
                continue
            if rule.require_owner_match and actor_id != resource_owner_id:
                continue
            return AuthorizationDecision(allowed=True, rule_id=rule.id, reason="allowed")
        return AuthorizationDecision(allowed=False, rule_id=None, reason="no_matching_rule")

    def authorize_tool(
        self,
        *,
        actor_role: str,
        actor_id: str,
        tool_name: str,
        action: str,
        resource_owner_id: str | None,
        record_count: int | None = None,
        approved: bool = False,
    ) -> AuthorizationDecision:
        for rule in self.contract.tool_rules:
            if rule.tool_name != tool_name or rule.action != action:
                continue
            if actor_role not in rule.allowed_roles:
                continue
            if rule.require_owner_match and actor_id != resource_owner_id:
                continue
            if rule.max_records is not None and (
                record_count is not None and record_count > rule.max_records
            ):
                return AuthorizationDecision(
                    allowed=False,
                    rule_id=rule.id,
                    reason="max_records_exceeded",
                    max_records=rule.max_records,
                    require_approval=rule.require_approval,
                )
            if rule.require_approval and not approved:
                return AuthorizationDecision(
                    allowed=False,
                    rule_id=rule.id,
                    reason="approval_required",
                    max_records=rule.max_records,
                    require_approval=rule.require_approval,
                )
            return AuthorizationDecision(
                allowed=True,
                rule_id=rule.id,
                reason="allowed",
                max_records=rule.max_records,
                require_approval=rule.require_approval,
            )
        return AuthorizationDecision(allowed=False, rule_id=None, reason="no_matching_rule")

    def authorize_sink(
        self,
        *,
        actor_role: str,
        sink_type: str,
        destination: str,
        external: bool,
        resource_labels: Sequence[str],
        source_trust_levels: Sequence[str],
        approved: bool,
    ) -> AuthorizationDecision:
        """Evaluate destination, lineage labels/trust and approval deterministically."""

        labels = set(resource_labels)
        trust_levels = set(source_trust_levels)
        candidates = sorted(
            (
                rule
                for rule in self.contract.sink_rules
                if rule.sink_type == sink_type
                and all(label in labels for label in rule.match_labels)
            ),
            key=lambda rule: (-len(rule.match_labels), rule.id),
        )
        if not candidates:
            return AuthorizationDecision(
                allowed=False,
                rule_id=None,
                reason="no_matching_rule",
            )
        role_candidates = [rule for rule in candidates if actor_role in rule.allowed_roles]
        if not role_candidates:
            return AuthorizationDecision(
                allowed=False,
                rule_id=candidates[0].id,
                reason="role_not_allowed",
            )
        for rule in role_candidates:
            if external and not rule.allow_external:
                return AuthorizationDecision(
                    allowed=False,
                    rule_id=rule.id,
                    reason="external_destination_blocked",
                )
            if trust_levels.intersection(rule.blocked_source_trust_levels):
                return AuthorizationDecision(
                    allowed=False,
                    rule_id=rule.id,
                    reason="blocked_source_trust",
                )
            if rule.require_approval and not approved:
                return AuthorizationDecision(
                    allowed=False,
                    rule_id=rule.id,
                    reason="approval_required",
                )
            return AuthorizationDecision(allowed=True, rule_id=rule.id, reason="allowed")

    def can_expose_tool(
        self,
        *,
        actor_role: str,
        tool_name: str,
        action: str,
    ) -> bool:
        """Return whether at least one contract rule can authorize this actor/tool."""

        return any(
            rule.tool_name == tool_name
            and rule.action == action
            and actor_role in rule.allowed_roles
            for rule in self.contract.tool_rules
        )


class ContractLoadError(ValueError):
    """Raised when the fixed synthetic Contract cannot be loaded."""


def _repo_root() -> Path:
    # security_contract.py lives at <repo>/apps/api/src/agent_audit_api/.
    return Path(__file__).resolve().parents[4]


def load_security_contract(data_dir: str | Path | None = None) -> SecurityContract:
    """Load a Contract from one data root; updates remain process-local."""

    directory = Path(data_dir) if data_dir is not None else _repo_root() / "data" / "demo"
    path = directory / "security_contract.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload: Any = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractLoadError("unable to load security_contract.json") from exc
    if not isinstance(payload, dict):
        raise ContractLoadError("security_contract.json must contain an object")
    try:
        return SecurityContract.model_validate(payload)
    except ValueError as exc:
        raise ContractLoadError("security_contract.json is invalid") from exc


__all__ = [
    "ActorRole",
    "AuthorizationDecision",
    "ContractEvaluator",
    "ContractLoadError",
    "ContractRole",
    "ResourceRule",
    "SecurityContract",
    "SinkRule",
    "SinkType",
    "ToolRule",
    "load_security_contract",
]
