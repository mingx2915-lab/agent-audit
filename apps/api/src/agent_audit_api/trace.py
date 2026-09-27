"""Request-scoped Trace event collector."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .schemas import TraceEvent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TraceCollector:
    """Assign ordered UTC events without interpreting authorization semantics."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(
        self,
        event_type: str,
        summary: str,
        details: dict[str, Any],
    ) -> TraceEvent:
        event = TraceEvent(
            sequence=len(self._events) + 1,
            type=event_type,  # type: ignore[arg-type]
            summary=summary,
            details=deepcopy(details),
            occurred_at=_utc_now(),
        )
        self._events.append(event)
        return event.model_copy(deep=True)

    def snapshot(self) -> list[TraceEvent]:
        """Return a new list preserving the collector's event order."""

        return [event.model_copy(deep=True) for event in self._events]


__all__ = ["TraceCollector"]
