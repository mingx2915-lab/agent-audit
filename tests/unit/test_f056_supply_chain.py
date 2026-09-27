from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_audit_api.supply_chain import (
    Component,
    FindingDecision,
    SupplyChainEvidenceRunner,
    license_category,
    normalize_findings,
    render_markdown,
)


ROOT = Path(__file__).resolve().parents[2]
PRODUCT_VERSION = "0.1.2"


def _runner(command: list[str], _cwd: Path, environment: dict[str, str]):
    assert all(token not in key.upper() for key in environment for token in ("TOKEN", "SECRET", "PASSWORD"))
    if command[0].endswith("python") or command[0].endswith("python.exe"):
        if any("site.getsitepackages" in part for part in command):
            return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")
        if any("importlib.metadata" in part for part in command):
            project = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8"))["project"]
            from packaging.requirements import Requirement
            dependencies = [Requirement(value).name for value in project["dependencies"]]
            payload = [
                {"name": "agent-audit-api", "version": PRODUCT_VERSION, "license_expression": None, "license": None, "classifiers": []},
                *[
                    {"name": name, "version": {"fastembed": "0.8.0", "fastapi": "0.115.0", "httpx": "0.27.0", "openai": "1.50.0", "packaging": "23.0", "uvicorn": "0.30.0"}[name.casefold()], "license_expression": "MIT", "license": None, "classifiers": []}
                    for name in dependencies
                ],
            ]
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")
        if command[-2:] == ["pip", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="pip 25.0\n", stderr="")
        project = tomllib.loads((ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        from packaging.requirements import Requirement
        dependencies = [Requirement(value).name for value in project["dependencies"]]
        installed = [{"metadata": {"name": "agent-audit-api", "version": PRODUCT_VERSION, "requires_dist": dependencies}}]
        versions = {"fastembed": "0.8.0", "fastapi": "0.115.0", "httpx": "0.27.0", "openai": "1.50.0", "packaging": "23.0", "uvicorn": "0.30.0"}
        installed.extend({"metadata": {"name": name, "version": versions[name.casefold()], "requires_dist": []}} for name in dependencies)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"installed": installed}), stderr="")
    if command[:2] == ["cargo", "metadata"]:
        assert "--offline" in command
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"workspace_members": [], "packages": []}), stderr="")
    if command == ["cargo", "--version"]:
        return subprocess.CompletedProcess(command, 0, stdout="cargo 1.88.0\n", stderr="")
    if command[-3:] == ["pip", "--version"] or command[-1:] == ["--version"]:
        return subprocess.CompletedProcess(command, 0, stdout="tool 1.0\n", stderr="")
    raise AssertionError(f"offline mode must not invoke vulnerability command: {command}")


@pytest.mark.parametrize(
    ("expression", "category"),
    [("MIT", "permissive"), ("LGPL-3.0-only", "weak_copyleft"),
     ("GPL-3.0-only", "strong_copyleft"), ("BUSL-1.1", "restricted"),
     (None, "unknown"), ("Made-Up-License", "unknown")],
)
def test_license_policy_is_explicit_and_unknown_is_not_inferred(expression, category) -> None:
    assert license_category(expression)[0] == category


def test_license_expression_with_unknown_token_stays_unknown() -> None:
    assert license_category("MIT OR Proprietary-Unknown")[0] == "unknown"


def test_acceptance_decision_requires_reason_owner_and_future_expiry() -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    FindingDecision(status="allowlisted", reason="reviewed", owner="security", expiry=future)
    for payload in (
        {"status": "allowlisted", "owner": "security", "expiry": future},
        {"status": "accepted", "reason": "reviewed", "expiry": future},
        {"status": "accepted", "reason": "reviewed", "owner": "security", "expiry": "2020-01-01T00:00:00Z"},
    ):
        with pytest.raises(ValidationError):
            FindingDecision.model_validate(payload)


def test_all_three_scanner_payloads_preserve_findings() -> None:
    installed = {"pkg": {"1.0"}}
    npm = normalize_findings("npm", {"vulnerabilities": {"pkg": {"range": "1.0.0", "via": [{"source": "ADV-N", "severity": "high"}]}}}, "npm", installed)
    python = normalize_findings("python", [{"name": "pkg", "version": "1.0", "vulns": [{"id": "ADV-P"}]}], "pypi", installed)
    cargo = normalize_findings("cargo", {"vulnerabilities": {"list": [{"package": {"name": "pkg", "version": "1.0"}, "advisory": {"id": "ADV-C", "severity": "critical"}}]}}, "rustsec", installed)
    assert [item.advisory for item in npm + python + cargo] == ["ADV-N", "ADV-P", "ADV-C"]
    assert python[0].severity == "unknown"


def test_npm_finding_uses_installed_version_not_advisory_range() -> None:
    findings = normalize_findings(
        "npm",
        {"vulnerabilities": {"pkg": {"range": "<2", "via": [{"source": "ADV", "severity": "high"}]}}},
        "npm",
        {"pkg": {"1.2.3"}},
    )
    assert findings[0].version == "1.2.3"


def test_npm_nested_and_scoped_nodes_preserve_each_installed_version(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": {
            "": {"name": "root", "version": "1"},
            "node_modules/pkg": {"version": "1.0.0", "license": "MIT"},
            "node_modules/parent/node_modules/pkg": {"version": "2.0.0", "license": "MIT"},
            "node_modules/@scope/name": {"version": "3.0.0", "license": "MIT"},
        }}), encoding="utf-8"
    )
    runner = SupplyChainEvidenceRunner(repository, tmp_path / "out", run_id="nodes")
    components, nodes = runner._npm_components()
    assert {(item.name, item.version) for item in components} == {
        ("pkg", "1.0.0"), ("pkg", "2.0.0"), ("@scope/name", "3.0.0")
    }
    findings = normalize_findings(
        "npm", {"vulnerabilities": {"pkg": {"range": "*", "nodes": [
            "node_modules/pkg", "node_modules/parent/node_modules/pkg"
        ], "via": [{"source": "ADV", "severity": "high"}]}}},
        "npm", {"pkg": {"1.0.0", "2.0.0"}}, npm_nodes=nodes,
    )
    assert {item.version for item in findings} == {"1.0.0", "2.0.0"}


def test_python_runtime_closure_excludes_build_tools_and_unrelated_packages(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    (repository / "apps" / "api").mkdir(parents=True)
    (repository / "apps" / "api" / "pyproject.toml").write_text(
        '[project]\nname="agent-audit-api"\nversion="0.1.2"\ndependencies=["runtime-a>=1"]\n',
        encoding="utf-8",
    )
    payload = {"installed": [
        {"metadata": {"name": "agent-audit-api", "version": "0.1.2", "requires_dist": ["runtime-a>=1"]}},
        {"metadata": {"name": "runtime-a", "version": "1.0", "requires_dist": []}},
        {"metadata": {"name": "pip", "version": "25", "requires_dist": []}},
        {"metadata": {"name": "setuptools", "version": "80", "requires_dist": []}},
        {"metadata": {"name": "pytest", "version": "9", "requires_dist": []}},
    ]}
    def commands(command, _cwd, _env):
        if any("site.getsitepackages" in part for part in command):
            return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")
        if any("importlib.metadata" in part for part in command):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps([
                    {"name": "agent-audit-api", "version": "0.1.2", "license_expression": None, "license": None, "classifiers": []},
                    {"name": "runtime-a", "version": "1.0", "license_expression": "MIT", "license": None, "classifiers": []},
                    {"name": "pip", "version": "25", "license_expression": "MIT", "license": None, "classifiers": []},
                    {"name": "setuptools", "version": "80", "license_expression": "MIT", "license": None, "classifiers": []},
                    {"name": "pytest", "version": "9", "license_expression": "MIT", "license": None, "classifiers": []},
                ]),
                stderr="",
            )
        if command[-2:] == ["pip", "--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="pip 25", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")
    runner = SupplyChainEvidenceRunner(repository, tmp_path / "out", command_runner=commands)
    components, _, _ = runner._python_components("python")
    assert {(item.name, item.version) for item in components} == {("runtime-a", "1.0")}
    assert components[0].license_expression == "MIT"


def test_python_stale_product_version_fails_inventory(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    (repository / "apps" / "api").mkdir(parents=True)
    (repository / "apps" / "api" / "pyproject.toml").write_text(
        '[project]\nname="agent-audit-api"\nversion="0.1.2"\ndependencies=[]\n', encoding="utf-8"
    )
    payload = {"installed": [{"metadata": {"name": "agent-audit-api", "version": "0.1.1", "requires_dist": []}}]}
    runner = SupplyChainEvidenceRunner(repository, tmp_path / "out", command_runner=lambda c, d, e: subprocess.CompletedProcess(c, 0, stdout=json.dumps(payload), stderr=""))
    with pytest.raises(RuntimeError, match="version"):
        runner._python_components("python")


def test_python_audit_ignores_rows_outside_runtime_closure_and_rejects_missing_runtime() -> None:
    payload = [
        {"name": "runtime-a", "version": "1.0", "vulns": [{"id": "ADV-R"}]},
        {"name": "pytest", "version": "9.0", "vulns": [{"id": "ADV-D"}]},
    ]
    findings = normalize_findings(
        "python", payload, "pypi", {"runtime-a": {"1.0"}}
    )
    assert [item.advisory for item in findings] == ["ADV-R"]
    with pytest.raises(ValueError):
        normalize_findings(
            "python", [{"name": "missing-runtime", "version": "1.0", "vulns": [{"id": "ADV-X"}]}],
            "pypi", {"runtime-a": {"1.0"}},
        )


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["passed", "findings"], "findings"),
        (["findings", "incomplete"], "incomplete"),
        (["incomplete", "failed"], "failed"),
        (["passed", "passed"], "passed"),
    ],
)
def test_overall_status_priority_is_failed_incomplete_findings_passed(
    statuses, expected, tmp_path: Path
) -> None:
    source = (ROOT / "apps" / "api" / "src" / "agent_audit_api" / "supply_chain.py").read_text(
        encoding="utf-8"
    )
    failed = source.index('if "failed" in statuses')
    incomplete = source.index('if "incomplete" in statuses')
    findings = source.index('if "findings" in statuses')
    assert failed < incomplete < findings
    priority = "failed" if "failed" in statuses else (
        "incomplete" if "incomplete" in statuses else (
            "findings" if "findings" in statuses else "passed"
        )
    )
    assert priority == expected


@pytest.mark.parametrize(
    ("returncode", "payload", "expected"),
    [(1, {"vulnerabilities": {"pkg": {"range": "1", "via": [{"source": "ADV"}]}}}, "findings"),
     (1, {"vulnerabilities": {}}, "incomplete"),
     (2, {"vulnerabilities": {"pkg": {"range": "1", "via": [{"source": "ADV"}]}}}, "incomplete")],
)
def test_scan_exit_codes_are_not_silently_promoted(returncode, payload, expected, tmp_path: Path) -> None:
    runner = SupplyChainEvidenceRunner(ROOT, tmp_path, run_id=f"exit-{returncode}")
    runner.command_runner = lambda command, cwd, env: subprocess.CompletedProcess(
        command, returncode if "audit" in command else 0,
        stdout=json.dumps(payload) if "audit" in command else "tool 1.0", stderr=""
    )
    _, fact = runner._scan("npm", ["npm", "audit"], False, {"pkg": {"1.0"}})
    assert fact.status == expected


def test_python_exit_one_is_clean_when_only_non_runtime_rows_have_findings(tmp_path: Path) -> None:
    payload = [
        {"name": "runtime-a", "version": "1.0", "vulns": []},
        {"name": "pip", "version": "24.0", "vulns": [{"id": "ADV-TOOL"}]},
    ]
    runner = SupplyChainEvidenceRunner(ROOT, tmp_path, run_id="python-tooling-only")
    runner.command_runner = lambda command, cwd, env: subprocess.CompletedProcess(
        command,
        1 if "pip_audit" in command else 0,
        stdout=json.dumps(payload) if "pip_audit" in command else "pip-audit 2.10.1",
        stderr="",
    )
    findings, fact = runner._scan(
        "python",
        ["python", "-m", "pip_audit"],
        False,
        {"runtime-a": {"1.0"}},
        version_command=["python", "-m", "pip_audit", "--version"],
    )
    assert findings == []
    assert fact.status == "passed"


def test_isolated_online_tools_keep_proxy_routing_without_unrelated_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9000")
    monkeypatch.setenv("AGENT_AUDIT_PROVIDER_CREDENTIAL", "must-not-cross-boundary")
    captured: dict[str, str] = {}

    def command_runner(command, cwd, environment):
        captured.update(environment)
        return subprocess.CompletedProcess(command, 0, stdout='{"vulnerabilities": {}}', stderr="")

    runner = SupplyChainEvidenceRunner(
        ROOT, tmp_path, run_id="proxy-routing", command_runner=command_runner
    )
    runner._command_json(["npm", "audit"], isolated_tool="npm")
    assert captured["HTTPS_PROXY"] == "http://127.0.0.1:9000"
    assert "AGENT_AUDIT_PROVIDER_CREDENTIAL" not in captured


@pytest.mark.parametrize(
    ("ecosystem", "expected"),
    [("npm", "npm audit"), ("python", "pip-audit"), ("cargo", "cargo-audit")],
)
def test_offline_tool_fact_never_exposes_explicit_tool_path(
    ecosystem, expected, tmp_path: Path
) -> None:
    runner = SupplyChainEvidenceRunner(ROOT, tmp_path, run_id=f"offline-{ecosystem}")
    _, fact = runner._scan(
        ecosystem,
        [r"C:\private-user\tools\scanner.exe", "audit"],
        True,
        {},
    )
    assert fact.name == expected
    assert "private-user" not in fact.model_dump_json()


def test_offline_bundle_covers_three_ecosystems_is_incomplete_and_is_same_source(tmp_path: Path) -> None:
    summary = SupplyChainEvidenceRunner(ROOT, tmp_path, run_id="offline", command_runner=_runner).run(
        python_executable="python", npm="npm", cargo="cargo", offline=True
    )
    assert summary.status == "incomplete"
    assert {item.ecosystem for item in summary.ecosystems} == {"npm", "python", "cargo"}
    assert all(item.status == "incomplete" for item in summary.ecosystems)
    run = tmp_path / "offline"
    assert json.loads((run / "summary.json").read_text(encoding="utf-8"))["status"] == summary.status
    assert render_markdown(summary) == (run / "summary.md").read_text(encoding="utf-8")
    for line in (run / "checksums.txt").read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        assert digest == hashlib.sha256((run / relative).read_bytes()).hexdigest()
        assert relative != "checksums.txt"


def test_tool_or_parse_failure_is_failed_and_never_zero_vulnerability_pass(tmp_path: Path) -> None:
    def broken(command, _cwd, _env):
        if command[:2] == ["cargo", "metadata"]:
            raise OSError("tool unavailable")
        if "inspect" in command:
            return subprocess.CompletedProcess(command, 0, stdout="not-json", stderr="")
        raise AssertionError("offline scan invoked")

    summary = SupplyChainEvidenceRunner(ROOT, tmp_path, run_id="failed", command_runner=broken).run(offline=True)
    assert summary.status == "failed"
    statuses = {item.ecosystem: item.status for item in summary.ecosystems}
    assert statuses["python"] == statuses["cargo"] == "failed"


def test_license_counts_review_required_and_tool_versions_are_recorded(tmp_path: Path) -> None:
    summary = SupplyChainEvidenceRunner(ROOT, tmp_path, run_id="facts", command_runner=_runner).run(
        python_executable="python", npm="npm", cargo="cargo", offline=True
    )
    npm = next(item for item in summary.ecosystems if item.ecosystem == "npm")
    assert npm.license_count == npm.component_count
    assert npm.review_required == (npm.unknown_license_count > 0)
    for ecosystem in summary.ecosystems:
        inventory = [tool for tool in ecosystem.tools if tool.status == "passed"]
        assert all(tool.version for tool in inventory)


def test_runner_rejects_nonempty_output_and_does_not_copy_repository_content(tmp_path: Path) -> None:
    output = tmp_path / "output"
    run = output / "same"
    run.mkdir(parents=True)
    (run / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="not empty"):
        SupplyChainEvidenceRunner(ROOT, output, run_id="same", command_runner=_runner).run()
    assert (run / "keep.txt").read_text(encoding="utf-8") == "keep"
