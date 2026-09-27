"""Opt-in smoke for a real Linux desktop bundle.

The repository does not manufacture a Linux bundle during normal test runs.
This test is intentionally skipped unless a build pipeline supplies the exact
artifact path, so a static Tauri configuration can never count as a launch
verification.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Linux desktop artifact smoke is Linux-only")
def test_real_linux_desktop_artifact_initializes_default_workspace() -> None:
    artifact_value = os.environ.get("AGENT_AUDIT_LINUX_ARTIFACT", "").strip()
    if not artifact_value:
        pytest.skip("set AGENT_AUDIT_LINUX_ARTIFACT to a real Linux desktop artifact")

    artifact = Path(artifact_value).expanduser().resolve()
    assert artifact.is_file(), f"Linux desktop artifact does not exist: {artifact}"
    assert "sidecar" not in artifact.stem.lower(), "Linux smoke requires the desktop bundle, not its Sidecar"

    with tempfile.TemporaryDirectory(prefix="agent-audit-linux-desktop-smoke-") as temporary_home:
        app_home = Path(temporary_home) / "app-home"
        manifest = app_home / "workspaces" / "default" / "agent-audit-workspace.json"
        process = subprocess.Popen(
            [str(artifact)],
            cwd=artifact.parent,
            env={**os.environ, "AGENT_AUDIT_HOME": str(app_home)},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if manifest.is_file() or process.poll() is not None:
                    break
                time.sleep(0.25)
            assert process.poll() is None, "Linux desktop artifact exited before initializing Workspace"
            assert manifest.is_file(), "Linux desktop artifact did not initialize its default Workspace"
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=8)

