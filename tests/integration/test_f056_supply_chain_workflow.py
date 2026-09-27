from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "supply-chain-evidence.yml"
SUPPLY_CHAIN = ROOT / "apps" / "api" / "src" / "agent_audit_api" / "supply_chain.py"


def test_supply_chain_workflow_uses_pinned_tools_and_separate_runtimes() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "runs-on: ubuntu-24.04" in workflow
    assert "node-version: '20.19.0'" in workflow
    assert "python-version: '3.11.13'" in workflow
    assert "toolchain: '1.88.0'" in workflow
    assert "npm ci" in workflow
    assert "pip-audit==2.10.1" in workflow
    assert "cargo install cargo-audit --version 0.22.2 --locked" in workflow
    assert "--online" in workflow
    assert "--python-executable \"$target_python\"" in workflow
    assert "--pip-audit-python \"$audit_python\"" in workflow
    assert "--cargo-tool cargo" in workflow
    assert "--cargo-audit-tool \"$cargo_audit\"" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "if: always()" in workflow
    assert "if-no-files-found: error" in workflow
    assert "continue-on-error: true" not in workflow


def test_supply_chain_workflow_keeps_official_npm_registry_in_runner() -> None:
    assert '--registry=https://registry.npmjs.org' in SUPPLY_CHAIN.read_text(
        encoding="utf-8"
    )


def test_supply_chain_outputs_are_ignored() -> None:
    assert "artifacts/supply-chain-evidence/" in (
        ROOT / ".gitignore"
    ).read_text(encoding="utf-8")
