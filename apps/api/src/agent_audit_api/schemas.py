"""HTTP request and response schemas for the demo API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ActorRole = Literal[
    "visitor",
    "employee",
    "sales",
    "hr",
    "finance_manager",
    "admin",
]


def to_camel(value: str) -> str:
    """Convert an internal snake_case field name to the API's camelCase form."""

    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )


class Actor(CamelModel):
    id: str
    display_name: str
    role: ActorRole


class TraceEvent(CamelModel):
    sequence: int
    type: Literal[
        "input",
        "source",
        "retrieval",
        "authorization",
        "tool_call",
        "tool_result",
        "sink",
        "model_response",
    ]
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str


class AssistantQueryRequest(CamelModel):
    actor_id: str
    message: str

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")
        return value


class AssistantQueryResult(CamelModel):
    query_id: str
    actor: Actor
    answer: str
    trace_events: list[TraceEvent]


class DesktopRuntimeStatus(CamelModel):
    """Diagnostic state exchanged between the Desktop shell and Sidecar."""

    status: Literal["starting", "ready", "failed", "stopped"]
    host: str = "127.0.0.1"
    port: int | None = Field(default=None, ge=1, le=65535)
    detail: str | None = None
