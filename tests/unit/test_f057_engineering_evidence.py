"""F-057 acceptance contracts for evidence closure.

These tests deliberately stay on the local evidence boundary.  They do not
start a service, call a Provider, or use a real enterprise system.  The
current F-056 release-4 evidence snapshot is represented by the two explicit
lists below: 18 RustSec findings and 22 Python unknown-license records.

The review-register test runs through the public
``build_supply_chain_review_register(summary)`` factory when it is available;
an explicit skip documents that integration point while the backend is being
assembled rather than treating a hand-built register as runner output.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import agent_audit_api.supply_chain as supply_chain
from agent_audit_api.release_evidence import ReleaseEvidenceRunner
from agent_audit_api.stability import run_stability_runner
from agent_audit_api.supply_chain import (
    Component,
    Finding,
    EcosystemResult,
    LicenseRecord,
    SupplyChainEvidenceRunner,
    SupplyChainReviewEntry,
    SupplyChainReviewRegister,
    SupplyChainSummary,
    ToolFact,
    load_supply_chain_review_register,
)


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_ID = "windows-20260831-release-4"
CURRENT_EVIDENCE_ID = "windows-20260831-release-5"

RUSTSEC_FINDINGS = (
    ("atk", "0.18.2", "RUSTSEC-2024-0413"),
    ("atk-sys", "0.18.2", "RUSTSEC-2024-0416"),
    ("gdk", "0.18.2", "RUSTSEC-2024-0412"),
    ("gdk-sys", "0.18.2", "RUSTSEC-2024-0418"),
    ("gdkwayland-sys", "0.18.2", "RUSTSEC-2024-0411"),
    ("gdkx11", "0.18.2", "RUSTSEC-2024-0417"),
    ("gdkx11-sys", "0.18.2", "RUSTSEC-2024-0414"),
    ("gtk", "0.18.2", "RUSTSEC-2024-0415"),
    ("gtk-sys", "0.18.2", "RUSTSEC-2024-0420"),
    ("gtk3-macros", "0.18.2", "RUSTSEC-2024-0419"),
    ("proc-macro-error", "1.0.4", "RUSTSEC-2024-0370"),
    ("ttf-parser", "0.25.1", "RUSTSEC-2026-0192"),
    ("unic-char-property", "0.9.0", "RUSTSEC-2025-0081"),
    ("unic-char-range", "0.9.0", "RUSTSEC-2025-0075"),
    ("unic-common", "0.9.0", "RUSTSEC-2025-0080"),
    ("unic-ucd-ident", "0.9.0", "RUSTSEC-2025-0100"),
    ("unic-ucd-version", "0.9.0", "RUSTSEC-2025-0098"),
    ("glib", "0.18.5", "RUSTSEC-2024-0429"),
)


def test_frozen_sidecar_recursively_includes_runtime_distribution_metadata() -> None:
    spec = (
        ROOT / "apps" / "desktop" / "scripts" / "agent-audit-sidecar.spec"
    ).read_text(encoding="utf-8")

    assert 'copy_metadata("agent-audit-api", recursive=True)' in spec

PYTHON_UNKNOWN_LICENSES = (
    ("annotated-doc", "0.0.5"),
    ("anyio", "4.14.2"),
    ("certifi", "2026.7.22"),
    ("charset-normalizer", "3.5.1"),
    ("click", "8.4.2"),
    ("fastapi", "0.141.1"),
    ("fsspec", "2026.7.0"),
    ("idna", "3.19"),
    ("jiter", "0.16.0"),
    ("numpy", "2.4.6"),
    ("packaging", "26.3"),
    ("pillow", "12.3.0"),
    ("py_rust_stemmers", "0.1.8"),
    ("pydantic", "2.13.4"),
    ("pydantic_core", "2.46.4"),
    ("sniffio", "1.3.1"),
    ("starlette", "1.6.0"),
    ("tqdm", "4.70.0"),
    ("typing-inspection", "0.4.4"),
    ("typing_extensions", "4.16.0"),
    ("urllib3", "2.7.0"),
    ("uvicorn", "0.52.4"),
)


def _finding_records() -> list[Finding]:
    return [
        Finding(
            ecosystem="cargo",
            package=package,
            version=version,
            advisory=advisory,
            severity="unknown",
            source="RustSec advisory database",
            impact="rustsec_warning:unsound"
            if advisory == "RUSTSEC-2024-0429"
            else "rustsec_warning:unmaintained",
        )
        for package, version, advisory in RUSTSEC_FINDINGS
    ]


def _license_records() -> list[LicenseRecord]:
    return [
        LicenseRecord(
            ecosystem="python",
            package=package,
            version=version,
            expression=None,
            category="unknown",
            policy="missing SPDX expression; no license inferred",
        )
        for package, version in PYTHON_UNKNOWN_LICENSES
    ]


def _review_entries() -> list[SupplyChainReviewEntry]:
    entries = [
        SupplyChainReviewEntry(
            stable_key=supply_chain.stable_finding_key(
                Finding(
                    ecosystem="cargo",
                    package=package,
                    version=version,
                    advisory=advisory,
                    severity="unknown",
                    source="RustSec advisory database",
                )
            ),
            kind="finding",
            ecosystem="cargo",
            package=package,
            version=version,
            advisory=advisory,
            evidence_source="cargo/vulnerabilities.json",
            source="RustSec advisory database",
        )
        for package, version, advisory in RUSTSEC_FINDINGS
    ]
    entries.extend(
        SupplyChainReviewEntry(
            stable_key=supply_chain.stable_license_key(
                LicenseRecord(
                    ecosystem="python",
                    package=package,
                    version=version,
                    expression=None,
                    category="unknown",
                    policy="missing SPDX expression; no license inferred",
                )
            ),
            kind="license",
            ecosystem="python",
            package=package,
            version=version,
            license_category="unknown",
            license_policy="missing SPDX expression; no license inferred",
            evidence_source="python/licenses.json",
            source="explicit Python resolved environment",
        )
        for package, version in PYTHON_UNKNOWN_LICENSES
    )
    return entries


def _expected_review_keys() -> set[str]:
    return {
        *(supply_chain.stable_finding_key(item) for item in _finding_records()),
        *(supply_chain.stable_license_key(item) for item in _license_records()),
    }


def test_f056_snapshot_has_exact_18_rustsec_and_22_unknown_license_review_items() -> None:
    """The review fixture is a set comparison, so omissions and duplicates are visible."""

    entries = _review_entries()
    register = SupplyChainReviewRegister(evidence_id=EVIDENCE_ID, items=entries)

    assert len(RUSTSEC_FINDINGS) == 18
    assert len(PYTHON_UNKNOWN_LICENSES) == 22
    assert len(entries) == 40
    assert len({entry.stable_key for entry in entries}) == 40
    assert {entry.stable_key for entry in register.items} == _expected_review_keys()
    assert sum(entry.kind == "finding" for entry in register.items) == 18
    assert sum(entry.kind == "license" for entry in register.items) == 22
    assert all(entry.status == "pending" for entry in register.items)
    assert all(entry.action == "review" for entry in register.items)

    findings = {(item.package, item.version, item.advisory) for item in register.items if item.kind == "finding"}
    licenses = {(item.package, item.version) for item in register.items if item.kind == "license"}
    assert findings == set(RUSTSEC_FINDINGS)
    assert licenses == set(PYTHON_UNKNOWN_LICENSES)


def test_review_register_rejects_duplicate_keys_and_mixed_kind_fields() -> None:
    entries = _review_entries()
    duplicate = entries + [entries[0].model_copy(deep=True)]
    with pytest.raises(ValidationError, match="stable keys must be unique"):
        SupplyChainReviewRegister(evidence_id=EVIDENCE_ID, items=duplicate)

    with pytest.raises(ValidationError, match="must not carry advisory"):
        SupplyChainReviewEntry(
            stable_key="python:license:bad:1.0",
            kind="license",
            ecosystem="python",
            package="bad",
            version="1.0",
            advisory="not-a-license-advisory",
            license_category="unknown",
            evidence_source="python/licenses.json",
            source="explicit Python resolved environment",
        )

    with pytest.raises(ValidationError, match="require advisory"):
        SupplyChainReviewEntry(
            stable_key="cargo:finding:missing:1.0",
            kind="finding",
            ecosystem="cargo",
            package="missing",
            version="1.0",
            evidence_source="cargo/vulnerabilities.json",
            source="RustSec advisory database",
        )


@pytest.mark.parametrize("status", ["accepted", "allowlisted"])
def test_accepted_or_allowlisted_review_requires_reason_owner_future_expiry(status: str) -> None:
    entry = _review_entries()[0]
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    accepted_payload = entry.model_dump()
    accepted_payload.update(
        {
            "status": status,
            "action": status,
            "reason": "GTK dependency is required by the supported Linux artifact",
            "owner": "platform-security",
            "due_date": future,
        }
    )
    accepted = SupplyChainReviewEntry.model_validate(accepted_payload)
    assert accepted.status == status
    assert accepted.reason and accepted.owner and accepted.due_date == future

    for missing in ("reason", "owner", "due_date"):
        payload: dict[str, Any] = entry.model_dump()
        payload.update(
            {
            "status": status,
            "action": status,
            "reason": "documented impact",
            "owner": "platform-security",
            "due_date": future,
            }
        )
        payload[missing] = None
        with pytest.raises(ValidationError):
            SupplyChainReviewEntry.model_validate(payload)

    with pytest.raises(ValidationError, match="future"):
        expired_payload = entry.model_dump()
        expired_payload.update(
            {
                "status": status,
                "action": status,
                "reason": "documented impact",
                "owner": "platform-security",
                "due_date": "2020-01-01T00:00:00Z",
            }
        )
        SupplyChainReviewEntry.model_validate(expired_payload)


def test_pending_review_cannot_be_marked_as_an_acceptance_action() -> None:
    entry = _review_entries()[0]
    with pytest.raises(ValidationError, match="pending reviews cannot use an acceptance action"):
        payload = entry.model_dump()
        payload["action"] = "allowlisted"
        SupplyChainReviewEntry.model_validate(payload)


def _unexecuted_target_manifest() -> dict[str, object]:
    return {
        "schemaVersion": "release-evidence-input.v1",
        "productVersion": "0.1.2",
        "gitRevision": "f057-test-revision",
        "dirtyWorktree": False,
        "platform": "test host",
        "pythonVersion": "3.11-test",
        "artifacts": [
            {
                "id": "clean-windows-install",
                "category": "desktop",
                "status": "not_verified",
                "provenance": "not_verified",
                "label": "clean Windows installation / upgrade / uninstall",
            },
            {
                "id": "debian-non-default-pointer",
                "category": "desktop",
                "status": "not_verified",
                "provenance": "not_verified",
                "label": "Debian non-default active Workspace pointer",
            },
            {
                "id": "real-enterprise-gateway",
                "category": "test",
                "status": "not_verified",
                "provenance": "not_verified",
                "label": "real enterprise Gateway and authorized credentials",
            },
        ],
        "boundaries": [
            "No clean Windows, Debian target, or real enterprise Gateway was executed in this test.",
        ],
    }


def test_unexecuted_clean_windows_debian_pointer_and_gateway_never_pass(tmp_path: Path) -> None:
    manifest = tmp_path / "input.json"
    manifest.write_text(json.dumps(_unexecuted_target_manifest()), encoding="utf-8")
    summary = ReleaseEvidenceRunner(tmp_path / "output", run_id="f057-targets").run(manifest)

    assert summary.status == "incomplete"
    assert summary.counts.passed == 0
    assert {artifact.id for artifact in summary.artifacts} == {
        "clean-windows-install",
        "debian-non-default-pointer",
        "real-enterprise-gateway",
    }
    assert all(artifact.status == "not_verified" for artifact in summary.artifacts)
    assert all(artifact.provenance == "not_verified" for artifact in summary.artifacts)
    assert all(artifact.path is None for artifact in summary.artifacts)


def test_stability_observation_declares_scope_and_does_not_claim_real_model_or_l4() -> None:
    evidence = asyncio.run(run_stability_runner(iterations=1, max_rounds=2))

    assert evidence.status == "passed"
    assert evidence.environment.deterministic is True
    assert evidence.environment.provider == "deterministic_test_provider"
    assert evidence.environment.retriever == "tfidf_test_retriever"
    assert evidence.environment.machine
    assert evidence.checks[0].iterations == 1
    assert evidence.observations.successful_workflows == 1
    assert evidence.observations.history_count == 1
    assert evidence.observations.dataset_document_count > 0
    assert evidence.observations.dataset_history_rows == 1
    assert evidence.observations.repetition_count == 1
    assert evidence.observations.duration_sample_count == 1
    assert evidence.observations.duration_p50_ms is not None
    assert evidence.observations.duration_p95_ms is not None
    assert evidence.observations.provider_call_count >= 1
    assert evidence.observations.memory_metric
    assert evidence.observations.memory_observation_method
    assert evidence.observations.database_observation_method
    assert evidence.observations.process_count == 1
    assert evidence.observations.handle_count is None
    limitations = "\n".join(evidence.limitations).casefold()
    assert "非真实模型" in limitations
    assert "tracemalloc" in limitations
    assert "不是硬件级" in limitations
    assert "长期稳定性结论" in limitations


def _write_f056_summary_fixture(tmp_path: Path) -> Path:
    evidence_dir = tmp_path / "f056-evidence"
    for ecosystem in ("npm", "python", "cargo"):
        (evidence_dir / ecosystem).mkdir(parents=True)

    findings = _finding_records()
    licenses = _license_records()
    for ecosystem in ("npm", "python", "cargo"):
        ecosystem_findings = [
            item.model_dump(mode="json", by_alias=True)
            for item in findings
            if item.ecosystem == ecosystem
        ]
        ecosystem_licenses = [
            item.model_dump(mode="json", by_alias=True)
            for item in licenses
            if item.ecosystem == ecosystem
        ]
        (evidence_dir / ecosystem / "vulnerabilities.json").write_text(
            json.dumps(ecosystem_findings), encoding="utf-8"
        )
        (evidence_dir / ecosystem / "licenses.json").write_text(
            json.dumps(ecosystem_licenses), encoding="utf-8"
        )
        (evidence_dir / ecosystem / "sbom.cdx.json").write_text(
            json.dumps({"bomFormat": "CycloneDX", "components": []}), encoding="utf-8"
        )

    def tool_fact(name: str) -> ToolFact:
        return ToolFact(
            name=name,
            version="test-1.0",
            status="passed",
            started_at="2026-08-31T00:00:00Z",
            completed_at="2026-08-31T00:00:01Z",
            data_source="synthetic F-056 fixture",
            data_source_status="available",
        )

    ecosystems = [
        EcosystemResult(
            ecosystem="npm",
            status="passed",
            source_kind="lockfile",
            lockfile=True,
            component_count=0,
            license_count=0,
            finding_count=0,
            pending_count=0,
            accepted_count=0,
            fixed_count=0,
            permissive_license_count=0,
            weak_copyleft_license_count=0,
            strong_copyleft_license_count=0,
            restricted_license_count=0,
            unknown_license_count=0,
            review_required=False,
            sbom="npm/sbom.cdx.json",
            licenses="npm/licenses.json",
            vulnerabilities="npm/vulnerabilities.json",
            tools=[tool_fact("npm audit")],
        ),
        EcosystemResult(
            ecosystem="python",
            status="passed",
            source_kind="resolved_environment",
            lockfile=False,
            component_count=22,
            license_count=22,
            finding_count=0,
            pending_count=0,
            accepted_count=0,
            fixed_count=0,
            permissive_license_count=0,
            weak_copyleft_license_count=0,
            strong_copyleft_license_count=0,
            restricted_license_count=0,
            unknown_license_count=22,
            review_required=True,
            sbom="python/sbom.cdx.json",
            licenses="python/licenses.json",
            vulnerabilities="python/vulnerabilities.json",
            tools=[tool_fact("pip-audit")],
        ),
        EcosystemResult(
            ecosystem="cargo",
            status="findings",
            source_kind="lockfile",
            lockfile=True,
            component_count=18,
            license_count=0,
            finding_count=18,
            pending_count=18,
            accepted_count=0,
            fixed_count=0,
            permissive_license_count=0,
            weak_copyleft_license_count=0,
            strong_copyleft_license_count=0,
            restricted_license_count=0,
            unknown_license_count=0,
            review_required=True,
            sbom="cargo/sbom.cdx.json",
            licenses="cargo/licenses.json",
            vulnerabilities="cargo/vulnerabilities.json",
            tools=[tool_fact("cargo-audit")],
        ),
    ]
    summary = SupplyChainSummary(
        id=EVIDENCE_ID,
        generated_at="2026-08-31T00:00:00Z",
        status="findings",
        ecosystems=ecosystems,
        findings=findings,
        boundaries=["Synthetic local fixture; no external tools or Provider."],
    )
    summary_path = evidence_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary.model_dump(mode="json", by_alias=True), indent=2),
        encoding="utf-8",
    )
    return summary_path


def test_review_factory_covers_the_exact_current_f056_evidence_set(tmp_path: Path) -> None:
    """Run exact-set coverage against the production factory once it is exposed."""

    factory = getattr(supply_chain, "build_supply_chain_review_register", None)
    if factory is None:
        pytest.skip(
            "F-057 backend integration pending: expose "
            "build_supply_chain_review_register(summary)"
        )
    summary_path = _write_f056_summary_fixture(tmp_path)
    register = factory(summary_path)
    assert isinstance(register, SupplyChainReviewRegister)
    assert register.evidence_id == EVIDENCE_ID
    assert len(register.items) == 40
    assert {entry.stable_key for entry in register.items} == _expected_review_keys()
    assert all(entry.status == "pending" for entry in register.items)
    assert all(entry.action == "review" for entry in register.items)
    assert {(entry.package, entry.version, entry.advisory) for entry in register.items if entry.kind == "finding"} == set(RUSTSEC_FINDINGS)
    assert {(entry.package, entry.version) for entry in register.items if entry.kind == "license"} == set(PYTHON_UNKNOWN_LICENSES)
    assert supply_chain.validate_supply_chain_review_register(summary_path, register) == register


def test_tracked_review_register_matches_current_triage_and_manual_license_resolution() -> None:
    register = load_supply_chain_review_register(
        ROOT / "data" / "demo" / "supply-chain-review.json"
    )

    assert register.evidence_id == CURRENT_EVIDENCE_ID
    assert len(register.items) == 19
    assert {entry.stable_key for entry in register.items} == {
        *{
            f"cargo:finding:{advisory}:{version}"
            for _package, version, advisory in RUSTSEC_FINDINGS
        },
        "python:license:py_rust_stemmers:0.1.8",
    }
    assert all(entry.status not in {"accepted", "allowlisted"} for entry in register.items)
    assert all(entry.impact != "not_assessed" for entry in register.items)
    assert all(entry.reachability != "not_assessed" for entry in register.items)
    assert all(entry.owner and entry.due_date and entry.reason for entry in register.items)
    assert all(entry.action != "review" for entry in register.items)

    glib = next(entry for entry in register.items if entry.package == "glib")
    assert glib.impact == "high"
    assert glib.reachability == "not_reachable"
    assert glib.action == "track_tauri_gtk_stack_migration"
    assert "VariantStrIter" in (glib.reason or "")

    ttf_parser = next(
        entry for entry in register.items if entry.package == "ttf-parser"
    )
    assert ttf_parser.reachability == "reachable"
    assert ttf_parser.action == "track_pdf_parser_upgrade_or_replacement"

    license_items = [entry for entry in register.items if entry.kind == "license"]
    assert len(license_items) == 1
    assert all(entry.license_category == "unknown" for entry in license_items)
    assert all(entry.license_expression is None for entry in license_items)
    assert license_items[0].package == "py_rust_stemmers"
    assert license_items[0].status == "fixed"
    assert license_items[0].impact == "none"
    assert license_items[0].reachability == "reachable"
    assert license_items[0].action == "verified_local_mit_license_text"
    assert "canonical MIT license text" in (license_items[0].reason or "")

    finding_items = [entry for entry in register.items if entry.kind == "finding"]
    assert len(finding_items) == 18
    withdrawn_advisories = {
        f"RUSTSEC-2024-{number:04d}"
        for number in range(411, 421)
    }
    withdrawn = [entry for entry in finding_items if entry.status == "fixed"]
    active = [entry for entry in finding_items if entry.status == "in_progress"]
    assert {entry.advisory for entry in withdrawn} == withdrawn_advisories
    assert all(entry.action == "record_rustsec_advisory_withdrawal" for entry in withdrawn)
    assert all("2026-08-14" in (entry.reason or "") for entry in withdrawn)
    assert len(active) == 8
    assert all(entry.status == "in_progress" for entry in active)
    assert all(
        entry.reachability == "reachable"
        for entry in finding_items
        if entry.package.startswith("unic-")
    )


def test_review_validator_rejects_missing_extra_and_stale_evidence_rows(tmp_path: Path) -> None:
    summary_path = _write_f056_summary_fixture(tmp_path)
    register = supply_chain.build_supply_chain_review_register(summary_path)

    missing = register.model_copy(update={"items": register.items[1:]})
    with pytest.raises(ValueError, match="item set differs"):
        supply_chain.validate_supply_chain_review_register(summary_path, missing)

    extra = SupplyChainReviewEntry(
        stable_key="cargo:finding:RUSTSEC-extra:9.9.9",
        kind="finding",
        ecosystem="cargo",
        package="fabricated",
        version="9.9.9",
        advisory="RUSTSEC-extra",
        evidence_source="cargo/vulnerabilities.json",
        source="RustSec advisory database",
    )
    fabricated = register.model_copy(update={"items": [*register.items, extra]})
    with pytest.raises(ValueError, match="item set differs"):
        supply_chain.validate_supply_chain_review_register(summary_path, fabricated)

    stale_item = register.items[0].model_copy(update={"package": "stale-package"})
    stale = register.model_copy(update={"items": [stale_item, *register.items[1:]]})
    with pytest.raises(ValueError, match="evidence fields differ"):
        supply_chain.validate_supply_chain_review_register(summary_path, stale)


def test_pending_unknown_license_keeps_supply_chain_summary_from_passing(
    tmp_path: Path,
) -> None:
    """A clean scanner result is not a passed release while review is pending."""

    def tool_fact(name: str) -> ToolFact:
        return ToolFact(
            name=name,
            version="test-1.0",
            status="passed",
            started_at="2026-08-31T00:00:00Z",
            completed_at="2026-08-31T00:00:01Z",
            data_source="synthetic local test double",
            data_source_status="available",
        )

    npm_component = Component(
        ecosystem="npm",
        name="npm-only",
        version="1.0.0",
        purl="pkg:npm/npm-only@1.0.0",
        source_kind="lockfile",
        lockfile=True,
        license_expression="MIT",
    )
    python_component = Component(
        ecosystem="python",
        name="unknown-license",
        version="1.0",
        purl="pkg:pypi/unknown-license@1.0",
        source_kind="resolved_environment",
        lockfile=False,
        license_expression=None,
    )
    cargo_component = Component(
        ecosystem="cargo",
        name="cargo-only",
        version="1.0.0",
        purl="pkg:cargo/cargo-only@1.0.0",
        source_kind="lockfile",
        lockfile=True,
        license_expression="MIT",
    )

    def command_runner(command, _cwd, _environment):
        if command[-1:] == ["--version"]:
            return subprocess.CompletedProcess(command, 0, stdout="tool 1.0\n", stderr="")
        if command[:2] == ["npm", "audit"]:
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps({"vulnerabilities": {}}), stderr=""
            )
        if "pip_audit" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps([{"name": "unknown-license", "version": "1.0", "vulns": []}]),
                stderr="",
            )
        if len(command) > 1 and command[1] == "audit":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"vulnerabilities": {"list": []}}),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    runner = SupplyChainEvidenceRunner(
        ROOT, tmp_path / "output", run_id="pending-license", command_runner=command_runner
    )
    runner._npm_components = lambda: (
        [npm_component],
        {"node_modules/npm-only": ("npm-only", "1.0.0")},
    )
    runner._python_components = lambda _python: (
        [python_component],
        tool_fact("pip inspect"),
        ["synthetic-site-packages"],
    )
    runner._cargo_components = lambda _cargo: ([cargo_component], tool_fact("cargo metadata"))

    summary = runner.run(
        python_executable="python",
        pip_audit_python="python",
        npm="npm",
        cargo_audit_tool="cargo-audit",
        offline=False,
    )

    python_result = next(item for item in summary.ecosystems if item.ecosystem == "python")
    assert python_result.review_required is True
    assert python_result.unknown_license_count == 1
    assert summary.status != "passed"
