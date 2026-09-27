"""Build one repository-owned release-evidence bundle.

This explicit script runs only the repository's controlled tests and build
checks.  It never configures a real Provider and uses a temporary
``AGENT_AUDIT_HOME``.  Rust and Desktop evidence are collected only when the
caller explicitly supplies the corresponding executable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
API_SRC = REPOSITORY_ROOT / "apps" / "api" / "src"
SCREENSHOT_NAMES = (
    "guided-not-run.png",
    "guided-critical-finding.png",
    "guided-replay-passed.png",
    "acceptance-run-summary.png",
)
SENSITIVE_ENV_PARTS = (
    "API_KEY",
    "AUTHORIZATION",
    "BEARER",
    "ACCESS_TOKEN",
    "CLIENT_SECRET",
    "PROVIDER_CREDENTIAL",
)

sys.path.insert(0, str(API_SRC))

from agent_audit_api.release_evidence import (  # noqa: E402
    ReleaseEvidenceError,
    ReleaseEvidenceInput,
    ReleaseEvidenceInputArtifact,
    ReleaseEvidenceRunner,
)
from agent_audit_api.supply_chain import SupplyChainSummary  # noqa: E402
from agent_audit_api.controlled_release_workflow import (  # noqa: E402
    build_controlled_release_workflow,
)


@dataclass(frozen=True)
class Check:
    id: str
    command: tuple[str, ...]
    provenance: Literal["real", "controlled_test"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run controlled repository checks and build one release-evidence bundle.",
        allow_abbrev=False,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--desktop-artifact", type=Path)
    parser.add_argument("--installer-artifact", type=Path)
    parser.add_argument("--sidecar-artifact", type=Path)
    parser.add_argument("--cargo", type=Path)
    parser.add_argument(
        "--supply-chain-evidence",
        type=Path,
        help="explicit F-056 supply-chain-evidence.v1 summary.json",
    )
    return parser


def _clean_environment(staging: Path) -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not any(part in key.upper() for part in SENSITIVE_ENV_PARTS)
        and not key.upper().startswith(
            ("DEEPSEEK_", "OPENAI_", "ANTHROPIC_", "OLLAMA_")
        )
    }
    environment["AGENT_AUDIT_HOME"] = str(staging / "agent-audit-home")
    environment["AGENT_AUDIT_EVIDENCE_SCREENSHOT_DIR"] = str(staging / "screenshots")
    environment["PYTHONPATH"] = str(API_SRC)
    environment.pop("AGENT_AUDIT_RUN_STABILITY", None)
    environment.pop("AGENT_AUDIT_LINUX_ARTIFACT", None)
    environment.pop("AGENT_AUDIT_DESKTOP_ARTIFACT", None)
    environment.pop("AGENT_AUDIT_LLM_PROVIDER", None)
    environment.pop("PROVIDER_API_KEY", None)
    return environment


def _run_check(check: Check, staging: Path, environment: dict[str, str]) -> ReleaseEvidenceInputArtifact:
    log_path = staging / f"{check.id}.txt"
    try:
        completed = subprocess.run(
            check.command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        status: Literal["passed", "failed"] = (
            "passed" if completed.returncode == 0 else "failed"
        )
        log = (
            f"command: {' '.join(check.command)}\nexitCode: {completed.returncode}\n\n"
            f"stdout:\n{completed.stdout}\n\nstderr:\n{completed.stderr}\n"
        )
    except OSError as exc:
        status = "failed"
        log = (
            f"command: {' '.join(check.command)}\nexitCode: unavailable\n\n"
            f"diagnostic: {type(exc).__name__}: {exc}\n"
        )
    for value, replacement in (
        (str(Path.home()), "<USER_HOME>"),
        (str(staging), "<STAGING>"),
    ):
        if value:
            log = log.replace(value, replacement)
            log = log.replace(value.replace("\\", "/"), replacement)
    log_path.write_text(log, encoding="utf-8")
    return ReleaseEvidenceInputArtifact(
        id=check.id,
        category="test",
        path=log_path.name,
        status=status,
        provenance=check.provenance,
    )


def _copy_screenshot_artifacts(staging: Path) -> list[ReleaseEvidenceInputArtifact]:
    artifacts: list[ReleaseEvidenceInputArtifact] = []
    screenshot_root = staging / "screenshots"
    for name in SCREENSHOT_NAMES:
        source = screenshot_root / name
        artifact_id = source.stem
        if source.is_file():
            artifacts.append(
                ReleaseEvidenceInputArtifact(
                    id=artifact_id,
                    category="screenshot",
                    path=source.relative_to(staging).as_posix(),
                    status="passed",
                    provenance="controlled_test",
                )
            )
        else:
            artifacts.append(
                ReleaseEvidenceInputArtifact(
                    id=artifact_id,
                    category="screenshot",
                    status="not_provided",
                    provenance="not_provided",
                )
            )
    return artifacts


def _repository_facts(environment: dict[str, str]) -> tuple[str | None, bool | None]:
    try:
        revision = subprocess.run(
            ("git", "rev-parse", "HEAD"),
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ("git", "status", "--porcelain"),
                cwd=REPOSITORY_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            ).stdout.strip()
        )
        return revision or None, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def _product_version() -> str:
    try:
        package = json.loads((REPOSITORY_ROOT / "package.json").read_text(encoding="utf-8"))
        tauri = json.loads(
            (REPOSITORY_ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseEvidenceError("unable to read product versions") from exc
    package_version = package.get("version")
    tauri_version = tauri.get("version")
    if (
        not isinstance(package_version, str)
        or not package_version.strip()
        or package_version != tauri_version
    ):
        raise ReleaseEvidenceError("package and Tauri product versions do not match")
    return package_version


def _controlled_workflow_artifacts(staging: Path) -> list[ReleaseEvidenceInputArtifact]:
    try:
        workflow = asyncio.run(
            build_controlled_release_workflow(staging / "controlled-workspace")
        )
    except ReleaseEvidenceError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        detail = str(exc).strip() or type(exc).__name__
        raise ReleaseEvidenceError(
            f"controlled release workflow failed: {detail}"
        ) from exc
    finding_status: Literal["passed", "failed"] = (
        "passed" if workflow.findings.findings else "failed"
    )
    replay_status: Literal["passed", "failed"] = (
        "passed" if workflow.replay_evidence.status == "passed" else "failed"
    )
    acceptance_status: Literal["passed", "failed"] = (
        "passed"
        if (
            workflow.acceptance_evidence.verdict == "passed"
            and workflow.acceptance_evidence.case_count == 24
            and workflow.acceptance_evidence.matched_case_count == 24
            and workflow.acceptance_evidence.mismatched_case_count == 0
            and workflow.acceptance_evidence.guided_replay_status == "passed"
        )
        else "failed"
    )
    outputs = (
        (
            "finding-json",
            "finding",
            "findings/finding.json",
            workflow.findings.model_dump(mode="json", by_alias=True),
            finding_status,
        ),
        (
            "finding-markdown",
            "finding",
            "findings/finding.md",
            workflow.finding_markdown,
            finding_status,
        ),
        (
            "replay-json",
            "replay",
            "replay/replay.json",
            workflow.replay_evidence.model_dump(mode="json", by_alias=True),
            replay_status,
        ),
        (
            "replay-markdown",
            "replay",
            "replay/replay.md",
            workflow.replay_markdown,
            replay_status,
        ),
        (
            "acceptance-json",
            "acceptance",
            "acceptance/acceptance.json",
            workflow.acceptance_evidence.model_dump(mode="json", by_alias=True),
            acceptance_status,
        ),
        (
            "acceptance-markdown",
            "acceptance",
            "acceptance/acceptance.md",
            workflow.acceptance_markdown,
            acceptance_status,
        ),
    )
    artifacts: list[ReleaseEvidenceInputArtifact] = []
    for artifact_id, category, relative, payload, status in outputs:
        path = staging / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = payload if isinstance(payload, str) else json.dumps(
            payload, ensure_ascii=False, indent=2
        )
        path.write_text(text.rstrip() + "\n", encoding="utf-8")
        artifacts.append(ReleaseEvidenceInputArtifact(
            id=artifact_id,
            category=category,
            path=relative,
            status=status,
            provenance="controlled_test",
        ))
    return artifacts


def _explicit_file(value: Path | None, label: str) -> Path | None:
    if value is None:
        return None
    if value.is_symlink():
        raise ReleaseEvidenceError(f"{label} must not be a symlink")
    try:
        resolved = value.resolve(strict=True)
    except OSError as exc:
        raise ReleaseEvidenceError(f"{label} is unavailable") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise ReleaseEvidenceError(f"{label} must be a regular file")
    return resolved


def _stage_desktop_artifact(
    staging: Path,
    source: Path | None,
    artifact_id: str,
) -> ReleaseEvidenceInputArtifact:
    if source is None:
        return ReleaseEvidenceInputArtifact(
            id=artifact_id,
            category="desktop",
            status="not_provided",
            provenance="not_provided",
        )
    destination = staging / "desktop-inputs" / f"{artifact_id}{source.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return ReleaseEvidenceInputArtifact(
        id=artifact_id,
        category="desktop",
        path=destination.relative_to(staging).as_posix(),
        status="passed",
        provenance="real",
    )


def _stage_supply_chain_evidence(
    staging: Path, source: Path | None
) -> ReleaseEvidenceInputArtifact | None:
    if source is None:
        return None
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        summary = SupplyChainSummary.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReleaseEvidenceError(
            "supply-chain evidence must be a valid supply-chain-evidence.v1 summary"
        ) from exc
    destination = staging / "supply-chain-inputs" / "summary.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    evidence_status: Literal["passed", "failed"] = (
        "passed" if summary.status == "passed" else "failed"
    )
    return ReleaseEvidenceInputArtifact(
        id="supply-chain-evidence",
        category="supply_chain",
        path=destination.relative_to(staging).as_posix(),
        status=evidence_status,
        provenance="real",
        label=f"F-056 supply-chain summary ({summary.status})",
    )


def _checks(args: argparse.Namespace) -> list[Check]:
    npm = shutil.which("npm") or "npm"
    npx = shutil.which("npx") or "npx"
    checks = [
        Check("python-pytest", (sys.executable, "-m", "pytest", "-q"), "controlled_test"),
        Check("npm-typecheck", (npm, "run", "typecheck"), "real"),
        Check("npm-build", (npm, "run", "build"), "real"),
        Check(
            "playwright-release-evidence",
            (
                npx,
                "playwright",
                "test",
                "tests/e2e/f051_release_evidence_screenshots.spec.ts",
                "--reporter=line",
            ),
            "controlled_test",
        ),
    ]
    if args.cargo is not None:
        cargo = str(args.cargo.resolve(strict=True))
        manifest = "apps/desktop/src-tauri/Cargo.toml"
        checks.extend(
            [
                Check("cargo-check", (cargo, "check", "--manifest-path", manifest), "real"),
                Check(
                    "cargo-test-lib",
                    (cargo, "test", "--lib", "--manifest-path", manifest),
                    "real",
                ),
            ]
        )
    return checks


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        desktop = _explicit_file(args.desktop_artifact, "desktop artifact")
        installer = _explicit_file(args.installer_artifact, "installer artifact")
        sidecar = _explicit_file(args.sidecar_artifact, "sidecar artifact")
        supply_chain = _explicit_file(
            args.supply_chain_evidence, "supply-chain evidence"
        )
        if args.cargo is not None:
            cargo = args.cargo.resolve(strict=True)
            if not cargo.is_file():
                raise ReleaseEvidenceError("cargo must be a regular executable file")

        with tempfile.TemporaryDirectory(prefix="agent-audit-release-evidence-") as temp:
            staging = Path(temp)
            environment = _clean_environment(staging)
            if args.cargo is not None:
                cargo_path = args.cargo.resolve(strict=True)
                environment["PATH"] = os.pathsep.join(
                    [str(cargo_path.parent), environment.get("PATH", "")]
                )
                environment["CARGO_TARGET_DIR"] = str(staging / "cargo-target")
            artifacts = [
                _run_check(check, staging, environment) for check in _checks(args)
            ]
            artifacts.extend(_controlled_workflow_artifacts(staging))
            artifacts.extend(_copy_screenshot_artifacts(staging))
            supply_chain_artifact = _stage_supply_chain_evidence(staging, supply_chain)
            if supply_chain_artifact is not None:
                artifacts.append(supply_chain_artifact)
            if args.cargo is None:
                for artifact_id in ("cargo-check", "cargo-test-lib"):
                    artifacts.append(
                        ReleaseEvidenceInputArtifact(
                            id=artifact_id,
                            category="test",
                            status="not_provided",
                            provenance="not_provided",
                        )
                    )
            artifacts.extend(
                [
                    _stage_desktop_artifact(staging, desktop, "desktop-executable"),
                    _stage_desktop_artifact(staging, installer, "windows-installer"),
                    _stage_desktop_artifact(staging, sidecar, "desktop-sidecar"),
                ]
            )
            if desktop is None:
                artifacts.append(
                    ReleaseEvidenceInputArtifact(
                        id="desktop-smoke-log",
                        category="test",
                        status="not_provided",
                        provenance="not_provided",
                    )
                )
            else:
                desktop_environment = dict(environment)
                desktop_environment["AGENT_AUDIT_DESKTOP_ARTIFACT"] = str(desktop)
                artifacts.append(
                    _run_check(
                        Check(
                            "desktop-smoke-log",
                            (
                                sys.executable,
                                "-m",
                                "pytest",
                                "tests/integration/test_desktop_configuration.py",
                                "-q",
                            ),
                            "real",
                        ),
                        staging,
                        desktop_environment,
                    )
                )
            revision, dirty = _repository_facts(environment)
            manifest = ReleaseEvidenceInput(
                product_version=_product_version(),
                git_revision=revision,
                dirty_worktree=dirty,
                artifacts=artifacts,
                boundaries=[
                    "Python 与浏览器业务证据来自受控 Test-only Provider，不代表真实企业模型稳定性。",
                    "未显式提供的 Rust、Desktop、Linux、真实企业 Gateway 与真实模型证据保持 not_provided 或 not_verified。",
                    "生成过程使用隔离 AGENT_AUDIT_HOME，未读取默认用户 Workspace。",
                ],
            )
            manifest_path = staging / "input-manifest.json"
            manifest_path.write_text(
                json.dumps(
                    manifest.model_dump(mode="json", by_alias=True),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            summary = ReleaseEvidenceRunner(args.output_dir, run_id=args.run_id).run(
                manifest_path
            )
        print(f"release-evidence: {summary.status} ({args.output_dir / summary.id})")
        return 1 if summary.status == "failed" else 0
    except (OSError, ValueError, ReleaseEvidenceError) as exc:
        message = str(exc).strip() or type(exc).__name__
        print(f"release-evidence: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
