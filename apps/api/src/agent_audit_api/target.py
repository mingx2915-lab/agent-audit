"""Execution profile for the controlled Target Agent."""

from __future__ import annotations

from .schemas import CamelModel


class TargetProfile(CamelModel):
    """Explicitly control whether observed authorization denials are enforced."""

    id: str
    name: str
    enforce_resource_authorization: bool
    enforce_tool_authorization: bool
    enforce_sink_authorization: bool = True


__all__ = ["TargetProfile"]
