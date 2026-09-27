from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("AGENT_AUDIT_RUN_SUPPLY_CHAIN") != "1",
    reason="real official advisory queries require explicit opt-in",
)
def test_real_online_supply_chain_audit_is_explicit(tmp_path: Path) -> None:
    names = {
        "python": "AGENT_AUDIT_SUPPLY_CHAIN_PYTHON",
        "pip_audit": "AGENT_AUDIT_SUPPLY_CHAIN_PIP_AUDIT_PYTHON",
        "cargo": "AGENT_AUDIT_SUPPLY_CHAIN_CARGO",
        "cargo_audit": "AGENT_AUDIT_SUPPLY_CHAIN_CARGO_AUDIT",
    }
    tools = {key: os.environ.get(name) for key, name in names.items()}
    missing = [name for key, name in names.items() if not tools[key]]
    if missing:
        pytest.fail(
            "explicit online audit requires tool path environment variables: "
            + ", ".join(missing)
        )
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "apps" / "api" / "scripts" / "build_supply_chain_evidence.py"),
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "real-online-audit",
            "--online",
            "--python-executable",
            tools["python"],
            "--pip-audit-python",
            tools["pip_audit"],
            "--cargo-tool",
            tools["cargo"],
            "--cargo-audit-tool",
            tools["cargo_audit"],
        ],
        cwd=ROOT,
        check=False,
    )
    assert completed.returncode in {0, 1}
    assert (tmp_path / "real-online-audit" / "summary.json").is_file()
