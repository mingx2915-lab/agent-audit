"""F-051 one-click release-evidence orchestration without running full checks."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from agent_audit_api.release_evidence import ReleaseEvidenceError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "apps" / "api" / "scripts" / "build_release_evidence.py"


def _load_script() -> ModuleType:
    module_name = "f051_build_release_evidence"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_checks_are_fixed_and_screenshots_cover_four_real_page_states(tmp_path: Path) -> None:
    module = _load_script()
    args = module._parser().parse_args(["--output-dir", str(tmp_path)])

    checks = module._checks(args)

    assert [check.id for check in checks] == [
        "python-pytest",
        "npm-typecheck",
        "npm-build",
        "playwright-release-evidence",
    ]
    assert checks[0].command[1:] == ("-m", "pytest", "-q")
    assert Path(checks[1].command[0]).name.casefold() in {"npm", "npm.cmd"}
    assert checks[1].command[1:] == ("run", "typecheck")
    assert Path(checks[2].command[0]).name.casefold() in {"npm", "npm.cmd"}
    assert checks[2].command[1:] == ("run", "build")
    assert Path(checks[3].command[0]).name.casefold() in {"npx", "npx.cmd"}
    assert checks[3].command[1:] == (
        "playwright",
        "test",
        "tests/e2e/f051_release_evidence_screenshots.spec.ts",
        "--reporter=line",
    )
    assert module.SCREENSHOT_NAMES == (
        "guided-not-run.png",
        "guided-critical-finding.png",
        "guided-replay-passed.png",
        "acceptance-run-summary.png",
    )


def test_clean_environment_removes_provider_credentials_and_uses_isolated_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    secrets = {
        "PROVIDER_API_KEY": "provider-secret",
        "AGENT_AUDIT_LLM_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "deepseek-secret",
        "OPENAI_ACCESS_TOKEN": "openai-secret",
        "ANTHROPIC_AUTHORIZATION": "anthropic-secret",
        "OLLAMA_BEARER": "ollama-secret",
        "UNRELATED_PUBLIC_SETTING": "keep-me",
    }
    for key, value in secrets.items():
        monkeypatch.setenv(key, value)

    environment = module._clean_environment(tmp_path / "staging")

    assert environment["UNRELATED_PUBLIC_SETTING"] == "keep-me"
    assert environment["AGENT_AUDIT_HOME"] == str(tmp_path / "staging" / "agent-audit-home")
    assert environment["AGENT_AUDIT_EVIDENCE_SCREENSHOT_DIR"] == str(
        tmp_path / "staging" / "screenshots"
    )
    assert environment["PYTHONPATH"] == str(module.API_SRC)
    for key in secrets:
        if key != "UNRELATED_PUBLIC_SETTING":
            assert key not in environment


def test_product_version_is_read_from_package_and_must_match_tauri(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    repository = tmp_path / "repo"
    tauri_root = repository / "apps" / "desktop" / "src-tauri"
    tauri_root.mkdir(parents=True)
    (repository / "package.json").write_text('{"version": "7.8.9"}', encoding="utf-8")
    (tauri_root / "tauri.conf.json").write_text('{"version": "7.8.9"}', encoding="utf-8")
    monkeypatch.setattr(module, "REPOSITORY_ROOT", repository)

    assert module._product_version() == "7.8.9"

    (tauri_root / "tauri.conf.json").write_text('{"version": "7.8.10"}', encoding="utf-8")
    with pytest.raises(ReleaseEvidenceError, match="do not match"):
        module._product_version()


def _fake_run_factory(
    module: ModuleType,
    *,
    failed_check_id: str | None = None,
    create_screenshots: bool = True,
) -> tuple[Any, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def fake_run(command: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": tuple(command), **kwargs})
        environment = kwargs.get("env") or {}
        if tuple(command) == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(command, 0, stdout="deadbeef\n", stderr="")
        if tuple(command) == ("git", "status", "--porcelain"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        executable = Path(command[0]).name.casefold()
        tail = tuple(command[1:])
        if any("test_desktop_configuration.py" in part for part in tail):
            check_id = "desktop-smoke-log"
        elif tail == ("-m", "pytest", "-q"):
            check_id = "python-pytest"
        elif executable in {"npm", "npm.cmd"} and tail == ("run", "typecheck"):
            check_id = "npm-typecheck"
        elif executable in {"npm", "npm.cmd"} and tail == ("run", "build"):
            check_id = "npm-build"
        elif executable in {"npx", "npx.cmd"} and tail[:2] == ("playwright", "test"):
            check_id = "playwright-release-evidence"
        else:
            check_id = None
        if check_id == "playwright-release-evidence" and create_screenshots:
            screenshot_root = Path(environment["AGENT_AUDIT_EVIDENCE_SCREENSHOT_DIR"])
            screenshot_root.mkdir(parents=True, exist_ok=True)
            for name in module.SCREENSHOT_NAMES:
                (screenshot_root / name).write_bytes(b"synthetic-png-fixture")
        returncode = 1 if check_id == failed_check_id else 0
        return subprocess.CompletedProcess(
            command,
            returncode,
            stdout=f"{check_id or 'command'} output",
            stderr="synthetic failure" if returncode else "",
        )

    return fake_run, calls


def test_one_click_without_binaries_marks_all_three_not_provided_and_hides_staging_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    fake_run, calls = _fake_run_factory(module)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_product_version", lambda: "0.1.0")
    output = tmp_path / "output"

    result = module.main(["--output-dir", str(output), "--run-id", "orchestrated"])

    assert result == 0
    run_dir = output / "orchestrated"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    artifacts = {artifact["id"]: artifact for artifact in summary["artifacts"]}
    for artifact_id in ("desktop-executable", "windows-installer", "desktop-sidecar"):
        assert artifacts[artifact_id]["status"] == "not_provided"
        assert artifacts[artifact_id]["provenance"] == "not_provided"
        assert artifacts[artifact_id]["path"] is None
    assert artifacts["desktop-smoke-log"]["status"] == "not_provided"
    for screenshot in module.SCREENSHOT_NAMES:
        artifact = artifacts[Path(screenshot).stem]
        assert artifact["status"] == "passed"
        assert artifact["provenance"] == "controlled_test"
    expected_workflow_artifacts = {
        "finding-json": ("finding", "findings/finding-json.json"),
        "finding-markdown": ("finding", "findings/finding-markdown.md"),
        "replay-json": ("replay", "replay/replay-json.json"),
        "replay-markdown": ("replay", "replay/replay-markdown.md"),
        "acceptance-json": ("acceptance", "acceptance/acceptance-json.json"),
        "acceptance-markdown": ("acceptance", "acceptance/acceptance-markdown.md"),
    }
    for artifact_id, (category, relative_path) in expected_workflow_artifacts.items():
        artifact = artifacts[artifact_id]
        assert artifact["category"] == category
        assert artifact["status"] == "passed"
        assert artifact["provenance"] == "controlled_test"
        assert artifact["path"] == relative_path
        assert (run_dir / relative_path).is_file()
    finding = json.loads(
        (run_dir / "findings" / "finding-json.json").read_text(encoding="utf-8")
    )
    assert finding["planId"] == "plan_sink_confidential_external"
    assert any(
        item["category"] == "external_sink_policy_violation"
        and item["severity"] == "critical"
        for item in finding["findings"]
    )
    replay = json.loads(
        (run_dir / "replay" / "replay-json.json").read_text(encoding="utf-8")
    )
    assert replay["status"] == "passed"
    assert replay["scanId"] == finding["scanId"]
    assert replay["planId"] == finding["planId"]
    assert replay["before"]["evaluation"] == "failed"
    assert replay["before"]["findings"]
    assert replay["after"]["evaluation"] == "passed"
    assert replay["after"]["execution"] == "blocked"
    assert replay["after"]["findings"] == []
    acceptance = json.loads(
        (run_dir / "acceptance" / "acceptance-json.json").read_text(encoding="utf-8")
    )
    assert acceptance["status"] == "completed"
    assert acceptance["verdict"] == "passed"
    assert acceptance["caseCount"] == 24
    assert acceptance["matchedCaseCount"] == 24
    assert acceptance["mismatchedCaseCount"] == 0
    assert acceptance["findingCount"] > 0
    assert acceptance["guidedReplayStatus"] == "passed"
    bundle_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in run_dir.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md", ".html", ".txt"}
    )
    assert "agent-audit-release-evidence-" not in bundle_text
    assert calls


def test_explicit_binary_files_are_copied_and_checksummed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    fake_run, _ = _fake_run_factory(module)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_product_version", lambda: "0.1.0")
    desktop = tmp_path / "agent-audit-desktop.exe"
    installer = tmp_path / "agent-audit-setup.exe"
    sidecar = tmp_path / "agent-audit-sidecar.exe"
    for index, artifact in enumerate((desktop, installer, sidecar), start=1):
        artifact.write_bytes(f"binary-{index}".encode())
    output = tmp_path / "output"

    result = module.main(
        [
            "--output-dir",
            str(output),
            "--run-id",
            "with-binaries",
            "--desktop-artifact",
            str(desktop),
            "--installer-artifact",
            str(installer),
            "--sidecar-artifact",
            str(sidecar),
        ]
    )

    assert result == 0
    run_dir = output / "with-binaries"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    artifacts = {artifact["id"]: artifact for artifact in summary["artifacts"]}
    for artifact_id in ("desktop-executable", "windows-installer", "desktop-sidecar"):
        artifact = artifacts[artifact_id]
        assert artifact["status"] == "passed"
        assert artifact["provenance"] == "real"
        assert artifact["path"].startswith("desktop/")
        copied = run_dir / artifact["path"]
        assert copied.is_file()
        assert artifact["sizeBytes"] == copied.stat().st_size
        assert len(artifact["sha256"]) == 64
    assert artifacts["desktop-smoke-log"]["status"] == "passed"


def test_failed_check_still_writes_failed_bundle_and_returns_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    fake_run, _ = _fake_run_factory(module, failed_check_id="npm-build")
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_product_version", lambda: "0.1.0")
    output = tmp_path / "output"

    result = module.main(["--output-dir", str(output), "--run-id", "failed-check"])

    assert result == 1
    summary = json.loads((output / "failed-check" / "summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    npm_build = next(artifact for artifact in summary["artifacts"] if artifact["id"] == "npm-build")
    assert npm_build["status"] == "failed"


def test_bundle_error_returns_two_without_false_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    fake_run, _ = _fake_run_factory(module)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_product_version", lambda: "0.1.0")

    class BrokenRunner:
        def __init__(self, output_dir: Path, *, run_id: str | None = None) -> None:
            self.output_dir = output_dir
            self.run_id = run_id

        def run(self, input_manifest: Path) -> object:
            raise ReleaseEvidenceError("synthetic bundle failure")

    monkeypatch.setattr(module, "ReleaseEvidenceRunner", BrokenRunner)
    output = tmp_path / "output"

    result = module.main(["--output-dir", str(output), "--run-id", "bundle-error"])

    assert result == 2
    assert not (output / "bundle-error" / "summary.json").exists()


def test_controlled_workflow_error_returns_two_without_false_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()
    fake_run, _ = _fake_run_factory(module)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_product_version", lambda: "0.1.0")

    async def broken_workflow(_workspace: Path) -> object:
        raise RuntimeError("controlled workflow failed")

    monkeypatch.setattr(module, "build_controlled_release_workflow", broken_workflow)
    output = tmp_path / "output"

    result = module.main(["--output-dir", str(output), "--run-id", "workflow-error"])

    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert "controlled workflow failed" in captured.err
    assert not (output / "workflow-error" / "summary.json").exists()


def test_missing_external_command_is_failed_evidence_not_bundle_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    original_run = module.subprocess.run

    def missing_npm(command: tuple[str, ...], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if Path(command[0]).name.casefold() in {"npm", "npm.cmd"}:
            raise FileNotFoundError("npm command unavailable")
        if tuple(command) == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(command, 0, stdout="deadbeef\n", stderr="")
        if tuple(command) == ("git", "status", "--porcelain"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(module.subprocess, "run", missing_npm)
    monkeypatch.setattr(module, "_product_version", lambda: "0.1.0")
    output = tmp_path / "output"

    result = module.main(["--output-dir", str(output), "--run-id", "missing-command"])

    assert result == 1
    summary = json.loads((output / "missing-command" / "summary.json").read_text(encoding="utf-8"))
    failed_ids = {
        artifact["id"] for artifact in summary["artifacts"] if artifact["status"] == "failed"
    }
    assert failed_ids == {"npm-typecheck", "npm-build"}
    assert summary["status"] == "failed"


def test_explicit_binary_symlink_is_rejected_before_resolution_when_supported(
    tmp_path: Path,
) -> None:
    module = _load_script()
    target = tmp_path / "desktop.exe"
    target.write_bytes(b"desktop")
    link = tmp_path / "desktop-link.exe"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("current environment cannot create symlink without elevation")

    with pytest.raises(ReleaseEvidenceError, match="symlink"):
        module._explicit_file(link, "desktop artifact")


def _supply_chain_summary(status: str) -> dict[str, object]:
    ecosystems = []
    for ecosystem, source_kind, lockfile in (
        ("npm", "lockfile", True),
        ("python", "resolved_environment", False),
        ("cargo", "lockfile", True),
    ):
        ecosystems.append(
            {
                "ecosystem": ecosystem,
                "status": status,
                "sourceKind": source_kind,
                "lockfile": lockfile,
                "componentCount": 0,
                "licenseCount": 0,
                "permissiveLicenseCount": 0,
                "weakCopyleftLicenseCount": 0,
                "strongCopyleftLicenseCount": 0,
                "restrictedLicenseCount": 0,
                "findingCount": 0,
                "pendingCount": 0,
                "acceptedCount": 0,
                "fixedCount": 0,
                "unknownLicenseCount": 0,
                "reviewRequired": False,
                "sbom": f"{ecosystem}/sbom.cdx.json",
                "licenses": f"{ecosystem}/licenses.json",
                "vulnerabilities": f"{ecosystem}/vulnerabilities.json",
                "tools": [],
            }
        )
    return {
        "schemaVersion": "supply-chain-evidence.v1",
        "id": "supply-test",
        "generatedAt": "2026-08-31T00:00:00Z",
        "status": status,
        "ecosystems": ecosystems,
        "findings": [],
        "boundaries": ["No business content was read."],
    }


@pytest.mark.parametrize("supply_status", ["passed", "findings", "incomplete", "failed"])
def test_optional_supply_chain_summary_is_copied_and_never_false_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supply_status: str,
) -> None:
    module = _load_script()
    fake_run, _ = _fake_run_factory(module)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_product_version", lambda: "0.1.0")
    source = tmp_path / "supply-summary.json"
    source.write_text(json.dumps(_supply_chain_summary(supply_status)), encoding="utf-8")
    output = tmp_path / "output"

    result = module.main(
        [
            "--output-dir",
            str(output),
            "--run-id",
            f"supply-{supply_status}",
            "--supply-chain-evidence",
            str(source),
        ]
    )

    expected_result = 0 if supply_status == "passed" else 1
    assert result == expected_result
    run_dir = output / f"supply-{supply_status}"
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    artifact = next(
        item for item in summary["artifacts"] if item["id"] == "supply-chain-evidence"
    )
    assert artifact["category"] == "supply_chain"
    assert artifact["provenance"] == "real"
    assert artifact["status"] == ("passed" if supply_status == "passed" else "failed")
    copied = run_dir / artifact["path"]
    assert copied.is_file()
    assert json.loads(copied.read_text(encoding="utf-8"))["status"] == supply_status


def test_invalid_supply_chain_summary_fails_before_writing_release_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    fake_run, _ = _fake_run_factory(module)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_product_version", lambda: "0.1.0")
    source = tmp_path / "invalid-summary.json"
    source.write_text('{"schemaVersion":"wrong"}', encoding="utf-8")
    output = tmp_path / "output"

    result = module.main(
        [
            "--output-dir",
            str(output),
            "--run-id",
            "invalid-supply",
            "--supply-chain-evidence",
            str(source),
        ]
    )

    assert result == 2
    assert not (output / "invalid-supply" / "summary.json").exists()
