from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "apps" / "desktop" / "scripts" / "windows_install_lifecycle_runner.py"


def test_real_windows_install_lifecycle_requires_explicit_inputs(tmp_path: Path) -> None:
    baseline_raw = os.environ.get("AGENT_AUDIT_WINDOWS_BASELINE_INSTALLER", "").strip()
    baseline_version = os.environ.get("AGENT_AUDIT_WINDOWS_BASELINE_VERSION", "").strip()
    upgrade_raw = os.environ.get("AGENT_AUDIT_WINDOWS_UPGRADE_INSTALLER", "").strip()
    upgrade_version = os.environ.get("AGENT_AUDIT_WINDOWS_UPGRADE_VERSION", "").strip()
    supplied = [baseline_raw, baseline_version, upgrade_raw, upgrade_version]
    if not any(supplied):
        pytest.skip("未提供两版 Windows NSIS 工件；默认测试不执行安装或卸载")
    if sys.platform != "win32":
        pytest.skip("Windows install lifecycle 仅在 Windows 执行")
    assert all(supplied), (
        "必须同时设置 AGENT_AUDIT_WINDOWS_BASELINE_INSTALLER/VERSION 与 "
        "AGENT_AUDIT_WINDOWS_UPGRADE_INSTALLER/VERSION"
    )
    baseline = Path(baseline_raw)
    upgrade = Path(upgrade_raw)
    assert baseline.is_file() and baseline.suffix.casefold() == ".exe"
    assert upgrade.is_file() and upgrade.suffix.casefold() == ".exe"

    sandbox = tmp_path.parent / f"f052sandbox{os.getpid()}"
    assert not sandbox.exists()
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--baseline-installer",
            str(baseline),
            "--baseline-version",
            baseline_version,
            "--upgrade-installer",
            str(upgrade),
            "--upgrade-version",
            upgrade_version,
            "--sandbox-root",
            str(sandbox),
        ],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    receipt = json.loads(completed.stdout.strip().splitlines()[-1])
    assert receipt["status"] == "passed"
    run_dir = sandbox / "evidence" / receipt["directory"]
    evidence = json.loads(
        (run_dir / "windows-install-lifecycle.json").read_text(encoding="utf-8")
    )
    assert evidence["status"] == "passed"
    assert any(
        check["id"] == "complete_install_upgrade_uninstall"
        and check["status"] == "passed"
        for check in evidence["checks"]
    )
    assert not (sandbox / "install").exists()
    assert (sandbox / "home" / "workspaces" / "default" / "agent-audit-workspace.json").is_file()
