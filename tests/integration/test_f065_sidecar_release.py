"""Clean-machine startup regression checks with real Uvicorn."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from fastapi.testclient import TestClient
from agent_audit_api.desktop_sidecar import _install_lifecycle_status
from agent_audit_api.main import create_app


def test_occupied_port_keeps_failed_status_and_reason(tmp_path):
    env = os.environ.copy()
    env["AGENT_AUDIT_HOME"] = str(tmp_path / "home")
    env["PYTHONIOENCODING"] = "utf-8"
    ready = tmp_path / "ready.json"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = subprocess.run(
            [sys.executable, "-m", "agent_audit_api.desktop_sidecar",
             "--workspace", str(tmp_path / "workspace"), "--port", str(port),
             "--ready-file", str(ready)],
            env=env, capture_output=True, encoding="utf-8", timeout=30,
        )
    status = json.loads(ready.read_text(encoding="utf-8"))
    assert result.returncode != 0
    assert status["status"] == "failed"
    assert status["port"] == port
    assert status["detail"] and ("10048" in status["detail"] or "98" in status["detail"])


def test_sidecar_health_returns_configured_listening_port():
    app = create_app()
    _install_lifecycle_status(app, ready_file=None, port=18123)
    with TestClient(app) as client:
        assert client.get("/api/health").json()["port"] == 18123
