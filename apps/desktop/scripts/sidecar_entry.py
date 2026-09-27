"""PyInstaller entry point for the local AgentAudit API Sidecar."""

from __future__ import annotations

import os
import sys


def _attach_inherited_stream(name: str, file_descriptor: int) -> None:
    """Keep Tauri's piped diagnostics available in a windowless PyInstaller process."""

    if getattr(sys, name) is not None:
        return
    try:
        stream = os.fdopen(file_descriptor, "w", buffering=1, closefd=False)
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    setattr(sys, name, stream)


_attach_inherited_stream("stdout", 1)
_attach_inherited_stream("stderr", 2)

from agent_audit_api.desktop_sidecar import main


if __name__ == "__main__":
    raise SystemExit(main())
