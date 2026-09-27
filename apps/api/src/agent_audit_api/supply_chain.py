"""Explicit, local supply-chain evidence generation for locked repository inputs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import uuid
from urllib.parse import quote
from datetime import date, datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Literal
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from pydantic import AliasChoices, ConfigDict, Field, field_validator, model_validator

from .schemas import CamelModel


Ecosystem = Literal["npm", "python", "cargo"]
StepStatus = Literal["passed", "findings", "incomplete", "failed"]
LicenseCategory = Literal[
    "permissive", "weak_copyleft", "strong_copyleft", "restricted", "unknown"
]
REVIEW_SCHEMA_VERSION = "supply-chain-review.v1"
DEFAULT_REVIEW_EVIDENCE_ID = "windows-20260831-release-4"
ReviewKind = Literal["finding", "license"]
ReviewStatus = Literal["pending", "in_progress", "fixed", "accepted", "allowlisted"]
ReviewImpact = Literal[
    "not_assessed", "unknown", "none", "low", "medium", "high", "critical"
]
ReviewReachability = Literal["not_assessed", "unknown", "reachable", "not_reachable"]
DEFAULT_OUTPUT_DIR = Path("artifacts/supply-chain-evidence")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SEVERITIES = {"critical", "high", "medium", "low", "unknown"}
_LICENSE_RISK = {
    "unknown": 0,
    "permissive": 1,
    "weak_copyleft": 2,
    "strong_copyleft": 3,
    "restricted": 4,
}
_LICENSE_POLICY: dict[str, LicenseCategory] = {
    "0BSD": "permissive", "Apache-2.0": "permissive", "BSD-2-Clause": "permissive",
    "BSD-3-Clause": "permissive", "ISC": "permissive", "MIT": "permissive",
    "MIT-0": "permissive", "CC0-1.0": "permissive", "Unicode-3.0": "permissive",
    "Zlib": "permissive", "Unlicense": "permissive", "LLVM-exception": "permissive",
    "MIT-CMU": "permissive", "PSF-2.0": "permissive",
    "MPL-2.0": "weak_copyleft", "LGPL-2.1-only": "weak_copyleft",
    "LGPL-2.1-or-later": "weak_copyleft", "LGPL-3.0-only": "weak_copyleft",
    "LGPL-3.0-or-later": "weak_copyleft", "GPL-2.0-only": "strong_copyleft",
    "GPL-2.0-or-later": "strong_copyleft", "GPL-3.0-only": "strong_copyleft",
    "GPL-3.0-or-later": "strong_copyleft", "AGPL-3.0-only": "strong_copyleft",
    "AGPL-3.0-or-later": "strong_copyleft", "SSPL-1.0": "restricted",
    "BUSL-1.1": "restricted", "UNLICENSED": "restricted",
}
_PYTHON_LEGACY_LICENSES = {
    "MIT License": "MIT",
    "3-Clause BSD License": "BSD-3-Clause",
    "Apache 2.0": "Apache-2.0",
    "Apache License": "Apache-2.0",
    "Apache License, Version 2.0": "Apache-2.0",
}
_PYTHON_LICENSE_CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
}
_PYTHON_DISTRIBUTION_METADATA_SCRIPT = """\
import importlib.metadata as metadata
import json

items = []
for distribution in metadata.distributions():
    package_metadata = distribution.metadata
    name = package_metadata.get("Name")
    if not name:
        continue
    items.append({
        "name": name,
        "version": distribution.version,
        "license_expression": package_metadata.get("License-Expression"),
        "license": package_metadata.get("License"),
        "classifiers": package_metadata.get_all("Classifier", []),
    })
print(json.dumps(items))
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON keys must be unique")
        result[key] = value
    return result


def _validate_decision_text(value: str | None) -> None:
    if value is None:
        return
    if any(ord(character) < 32 for character in value):
        raise ValueError("decision text must not contain control characters")
    if re.search(
        r"(?i)(?:api[ _-]?key|authorization|credential|token|password|secret)\s*[:=]",
        value,
    ):
        raise ValueError("decision text contains a credential-shaped field")
    if re.search(r"(?i)(?:[A-Z]:\\|\\\\[^\\\s]+\\[^\\\s]+|(?<![A-Za-z0-9])/(?:[^/\s]+/)+[^/\s]*)", value):
        raise ValueError("decision text contains an absolute path")


def _review_relative_path(value: str, *, label: str) -> PurePosixPath:
    """Validate a review artifact locator without resolving user paths."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or path.anchor
        or any(part in {"", ".", ".."} for part in path.parts)
        or re.match(r"^[A-Za-z]:", normalized)
    ):
        raise ValueError(f"{label} must be a relative POSIX path")
    return path


def _parse_review_datetime(value: str, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an ISO date or timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_review_date(value: str, *, label: str) -> datetime:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{label} is invalid") from exc
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{label} is invalid")
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


class ToolFact(CamelModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    name: str
    version: str | None = None
    status: StepStatus
    started_at: str
    completed_at: str
    data_source: str
    data_source_status: str
    data_source_updated_at: str | None = None
    detail: str | None = None


class Component(CamelModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    ecosystem: Ecosystem
    name: str
    version: str
    purl: str
    source_kind: Literal["lockfile", "resolved_environment"]
    lockfile: bool
    license_expression: str | None = None


class LicenseRecord(CamelModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    ecosystem: Ecosystem
    package: str
    version: str
    expression: str | None
    category: LicenseCategory
    policy: str


class FindingDecision(CamelModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    status: Literal["pending", "fixed", "accepted", "allowlisted"] = "pending"
    reason: str | None = None
    owner: str | None = None
    expiry: str | None = None

    @model_validator(mode="after")
    def validate_acceptance(self) -> "FindingDecision":
        if self.status in {"accepted", "allowlisted"}:
            if not self.reason or not self.reason.strip() or not self.owner or not self.owner.strip():
                raise ValueError("accepted decisions require reason and owner")
            if not self.expiry:
                raise ValueError("accepted decisions require expiry")
            try:
                expiry = datetime.fromisoformat(self.expiry.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("decision expiry is invalid") from exc
            if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
                raise ValueError("decision expiry must be a future timestamp")
        return self


class Finding(CamelModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    ecosystem: Ecosystem
    package: str
    version: str
    advisory: str
    severity: str
    source: str
    status: str = "pending"
    impact: str = "not_assessed"
    decision: FindingDecision = Field(default_factory=FindingDecision)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        normalized = value.casefold()
        return normalized if normalized in _SEVERITIES else "unknown"


class SupplyChainReviewEntry(CamelModel):
    """One human-reviewable item projected from a supply-chain evidence run.

    This is deliberately separate from :class:`FindingDecision`: a license
    record has no advisory and a vulnerability decision does not capture
    reachability.  Generated entries are always ``pending`` and
    ``not_assessed``; changing those values is an explicit reviewer action.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    stable_key: str = Field(
        validation_alias=AliasChoices("stable_key", "stableKey", "key")
    )
    kind: ReviewKind
    ecosystem: Ecosystem
    package: str
    version: str
    advisory: str | None = None
    license_expression: str | None = None
    license_category: LicenseCategory | None = None
    license_policy: str | None = None
    evidence_source: str
    source: str
    observed_impact: str | None = None
    impact: ReviewImpact = "not_assessed"
    reachability: ReviewReachability = "not_assessed"
    owner: str | None = None
    status: ReviewStatus = "pending"
    action: str = "review"
    due_date: str | None = None
    reason: str | None = None

    @property
    def key(self) -> str:
        """Compatibility alias for callers that refer to the stable key as ``key``."""

        return self.stable_key

    @field_validator(
        "stable_key", "package", "version", "evidence_source", "source", "action"
    )
    @classmethod
    def review_text_must_be_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("review text must not be empty")
        if any(ord(character) < 32 for character in value):
            raise ValueError("review text must not contain control characters")
        return value

    @field_validator(
        "reason", "owner", "observed_impact", "license_policy", "source", "license_expression"
    )
    @classmethod
    def review_optional_text_is_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("review text must not be empty")
        _validate_decision_text(value)
        return value

    @field_validator("evidence_source")
    @classmethod
    def evidence_source_is_relative(cls, value: str) -> str:
        _review_relative_path(value, label="evidence_source")
        return PurePosixPath(value.replace("\\", "/")).as_posix()

    @field_validator("due_date")
    @classmethod
    def due_date_is_iso(cls, value: str | None) -> str | None:
        if value is None:
            return None
        _parse_review_date(value, label="due_date")
        return value

    @model_validator(mode="after")
    def validate_kind_and_action(self) -> "SupplyChainReviewEntry":
        if self.kind == "finding":
            if not self.advisory or not self.advisory.strip():
                raise ValueError("finding review entries require advisory")
            if self.license_category is not None:
                raise ValueError("finding review entries must not carry license category")
        else:
            if self.advisory is not None:
                raise ValueError("license review entries must not carry advisory")
            if self.license_category != "unknown":
                raise ValueError(
                    "license review entries must preserve unknown license category"
                )
        if self.status in {"accepted", "allowlisted"}:
            if not self.reason or not self.owner or not self.due_date:
                raise ValueError(
                    "accepted or allowlisted reviews require reason, owner, and due_date"
                )
            expiry = _parse_review_datetime(self.due_date, label="due_date")
            if expiry <= datetime.now(timezone.utc):
                raise ValueError("accepted or allowlisted due_date must be in the future")
            if self.action.casefold() != self.status:
                raise ValueError(
                    "accepted or allowlisted reviews require a matching action"
                )
        if self.status == "fixed" and not self.owner:
            raise ValueError("fixed reviews require owner")
        if self.status in {"pending", "in_progress"} and self.action.casefold() in {
            "accept",
            "accepted",
            "allowlist",
            "allowlisted",
        }:
            raise ValueError("pending reviews cannot use an acceptance action")
        return self


class SupplyChainReviewRegister(CamelModel):
    """Machine-readable review register tied to one immutable summary."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["supply-chain-review.v1"] = REVIEW_SCHEMA_VERSION
    evidence_id: str
    summary_path: str = "summary.json"
    generated_at: str = Field(default_factory=utc_now)
    items: list[SupplyChainReviewEntry]
    boundaries: list[str] = Field(default_factory=lambda: [
        "Generated entries remain pending until an explicit human review action.",
        "Unknown license metadata is not converted into an SPDX or distribution conclusion.",
        "Impact and reachability are not assessed by the scanner.",
    ])

    @field_validator("summary_path")
    @classmethod
    def summary_path_is_relative(cls, value: str) -> str:
        _review_relative_path(value, label="summary_path")
        return PurePosixPath(value.replace("\\", "/")).as_posix()

    @model_validator(mode="after")
    def review_keys_are_unique(self) -> "SupplyChainReviewRegister":
        keys = [item.stable_key for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("review stable keys must be unique")
        return self


class EcosystemResult(CamelModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    ecosystem: Ecosystem
    status: StepStatus
    source_kind: Literal["lockfile", "resolved_environment"]
    lockfile: bool
    component_count: int = Field(ge=0)
    license_count: int = Field(ge=0)
    finding_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    fixed_count: int = Field(ge=0)
    permissive_license_count: int = Field(ge=0)
    weak_copyleft_license_count: int = Field(ge=0)
    strong_copyleft_license_count: int = Field(ge=0)
    restricted_license_count: int = Field(ge=0)
    unknown_license_count: int = Field(ge=0)
    review_required: bool
    sbom: str
    licenses: str
    vulnerabilities: str
    tools: list[ToolFact]


class SupplyChainSummary(CamelModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_version: Literal["supply-chain-evidence.v1"] = "supply-chain-evidence.v1"
    id: str
    generated_at: str
    status: StepStatus
    ecosystems: list[EcosystemResult]
    findings: list[Finding]
    boundaries: list[str]


CommandRunner = Callable[[list[str], Path, dict[str, str]], subprocess.CompletedProcess[str]]


def default_command_runner(
    command: list[str], cwd: Path, environment: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=cwd, env=environment, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )


def license_category(expression: str | None) -> tuple[LicenseCategory, str]:
    if not expression or not expression.strip():
        return "unknown", "missing SPDX expression; no license inferred"
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", expression)
    tokens = [token for token in tokens if token.upper() not in {"AND", "OR", "WITH"}]
    categories = [_LICENSE_POLICY.get(token, "unknown") for token in tokens]
    if not categories:
        return "unknown", "unrecognized SPDX expression; no license inferred"
    if "unknown" in categories:
        return "unknown", "expression contains an unknown SPDX token; no license inferred"
    category = max(categories, key=lambda value: _LICENSE_RISK[value])
    return category, "composite SPDX expression uses highest-risk token category"


def _python_license_expression(*metadata_sources: dict[str, Any]) -> str | None:
    for metadata in metadata_sources:
        expression = metadata.get("license_expression")
        if isinstance(expression, str) and expression.strip():
            return expression.strip()
    for metadata in metadata_sources:
        legacy = metadata.get("license")
        if not isinstance(legacy, str) or not legacy.strip():
            continue
        normalized = _PYTHON_LEGACY_LICENSES.get(legacy.strip(), legacy.strip())
        if license_category(normalized)[0] != "unknown":
            return normalized
    mapped: set[str] = set()
    for metadata in metadata_sources:
        classifiers = metadata.get("classifier") or metadata.get("classifiers") or []
        if isinstance(classifiers, list):
            mapped.update(
                _PYTHON_LICENSE_CLASSIFIERS[item]
                for item in classifiers
                if isinstance(item, str) and item in _PYTHON_LICENSE_CLASSIFIERS
            )
    return next(iter(mapped)) if len(mapped) == 1 else None


def cyclonedx(ecosystem: Ecosystem, components: list[Component]) -> dict[str, Any]:
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {"timestamp": utc_now(), "component": {"type": "application", "name": "agent-audit"}},
        "components": [
            {"type": "library", "name": item.name, "version": item.version,
             "purl": item.purl, "licenses": ([{"expression": item.license_expression}]
             if item.license_expression else [])}
            for item in components
        ],
    }


def _safe_environment(
    *, tool_home: Path | None = None, npm: bool = False, cargo_audit: bool = False
) -> dict[str, str]:
    environment = {
        key: os.environ[key]
        for key in (
            "PATH", "LANG", "LC_ALL", "SYSTEMROOT", "WINDIR",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        )
        if key in os.environ
    }
    environment["PYTHONUTF8"] = "1"
    if tool_home is not None:
        for key in ("HOME", "USERPROFILE", "TMP", "TEMP", "XDG_CACHE_HOME"):
            environment[key] = str(tool_home)
        if npm:
            npm_user_config = tool_home / "empty-npmrc"
            npm_user_config.write_text("", encoding="utf-8")
            environment["NPM_CONFIG_USERCONFIG"] = str(npm_user_config)
            environment["NPM_CONFIG_CACHE"] = str(tool_home / "npm-cache")
        if cargo_audit:
            environment["CARGO_HOME"] = str(tool_home / "cargo-home")
    return environment


class SupplyChainEvidenceRunner:
    def __init__(
        self, repository_root: str | Path, output_dir: str | Path, *,
        run_id: str | None = None, command_runner: CommandRunner = default_command_runner,
    ) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.output_dir = Path(output_dir)
        self.run_id = run_id or f"supply_{uuid.uuid4().hex[:12]}"
        self.command_runner = command_runner
        if not _SAFE_ID.fullmatch(self.run_id):
            raise ValueError("run_id is invalid")

    def _command_json(
        self, command: list[str], *,
        isolated_tool: Literal["npm", "python", "cargo-audit"] | None = None
    ) -> tuple[int | None, Any | None, str | None]:
        try:
            if isolated_tool is None:
                completed = self.command_runner(
                    command, self.repository_root, _safe_environment()
                )
            else:
                with tempfile.TemporaryDirectory(prefix="agent-audit-supply-tool-") as directory:
                    completed = self.command_runner(
                        command,
                        self.repository_root,
                        _safe_environment(
                            tool_home=Path(directory),
                            npm=isolated_tool == "npm",
                            cargo_audit=isolated_tool == "cargo-audit",
                        ),
                    )
        except OSError as exc:
            return None, None, type(exc).__name__
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return (
                completed.returncode,
                None,
                "parse_error" if completed.returncode == 0 else None,
            )
        return completed.returncode, payload, None

    def _tool_version(
        self,
        command: list[str],
        name: str,
        *,
        isolated_tool: Literal["npm", "python", "cargo-audit"] | None = None,
    ) -> str | None:
        try:
            if isolated_tool is None:
                completed = self.command_runner(
                    command, self.repository_root, _safe_environment()
                )
            else:
                with tempfile.TemporaryDirectory(prefix="agent-audit-supply-version-") as directory:
                    completed = self.command_runner(
                        command,
                        self.repository_root,
                        _safe_environment(
                            tool_home=Path(directory),
                            npm=isolated_tool == "npm",
                            cargo_audit=isolated_tool == "cargo-audit",
                        ),
                    )
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        match = re.search(r"(?<!\d)(\d+\.\d+(?:\.\d+)?(?:[-+][A-Za-z0-9.-]+)?)", completed.stdout)
        return match.group(1) if match else None

    def _npm_components(self) -> tuple[list[Component], dict[str, tuple[str, str]]]:
        payload = json.loads((self.repository_root / "package-lock.json").read_text(encoding="utf-8"))
        if payload.get("lockfileVersion") != 3 or not isinstance(payload.get("packages"), dict):
            raise ValueError("package-lock v3 is required")
        result = []
        node_inventory: dict[str, tuple[str, str]] = {}
        for path, item in payload["packages"].items():
            if item.get("link") is True:
                continue
            marker = "node_modules/"
            if marker not in path:
                continue
            name = path.rsplit(marker, 1)[1]
            if not name or name.startswith("node_modules/"):
                continue
            version = item.get("version")
            if not isinstance(version, str):
                continue
            license_expression = item.get("license") if isinstance(item.get("license"), str) else None
            result.append(Component(ecosystem="npm", name=name, version=version,
                purl=f"pkg:npm/{quote(name, safe='/')}@{quote(version, safe='')}", source_kind="lockfile",
                lockfile=True, license_expression=license_expression))
            node_inventory[path] = (name, version)
        return sorted(result, key=lambda item: (item.name.casefold(), item.version)), node_inventory

    def _cargo_components(self, cargo: str) -> tuple[list[Component], ToolFact]:
        started = utc_now()
        code, payload, error = self._command_json([cargo, "metadata", "--locked", "--offline", "--format-version", "1", "--manifest-path", "apps/desktop/src-tauri/Cargo.toml"])
        if code != 0 or error or not isinstance(payload, dict):
            raise RuntimeError(f"cargo_metadata_{error or f'exit_{code}'}")
        workspace = set(payload.get("workspace_members", []))
        components = []
        for package in payload.get("packages", []):
            if package.get("id") in workspace:
                continue
            name, version = package.get("name"), package.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            components.append(Component(ecosystem="cargo", name=name, version=version,
                purl=f"pkg:cargo/{name}@{version}", source_kind="lockfile", lockfile=True,
                license_expression=package.get("license") if isinstance(package.get("license"), str) else None))
        fact = ToolFact(name="cargo metadata", version=self._tool_version([cargo, "--version"], "cargo"), status="passed", started_at=started,
            completed_at=utc_now(), data_source="Cargo.lock", data_source_status="available")
        return sorted(components, key=lambda item: (item.name.casefold(), item.version)), fact

    def _python_components(self, python: str) -> tuple[list[Component], ToolFact, list[str]]:
        started = utc_now()
        code, payload, error = self._command_json([python, "-m", "pip", "inspect", "--local"])
        if code != 0 or error or not isinstance(payload, dict):
            raise RuntimeError(f"pip_inspect_{error or f'exit_{code}'}")
        installed: dict[str, tuple[str, dict[str, Any]]] = {}
        for package in payload.get("installed", []):
            metadata = package.get("metadata", {})
            name, version = metadata.get("name"), metadata.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                continue
            installed[canonicalize_name(name)] = (version, metadata)
        root_name = canonicalize_name("agent-audit-api")
        if root_name not in installed:
            raise RuntimeError("pip_inspect_product_missing")
        pyproject = tomllib.loads(
            (self.repository_root / "apps/api/pyproject.toml").read_text(encoding="utf-8")
        )
        project = pyproject.get("project")
        if not isinstance(project, dict):
            raise RuntimeError("python_project_metadata_invalid")
        project_version = project.get("version")
        root_requirements = project.get("dependencies")
        if (
            not isinstance(project_version, str)
            or not isinstance(root_requirements, list)
            or not all(isinstance(item, str) for item in root_requirements)
        ):
            raise RuntimeError("python_project_metadata_invalid")
        installed_root_version, _ = installed[root_name]
        if installed_root_version != project_version:
            raise RuntimeError("pip_inspect_product_version_mismatch")
        selected: set[str] = set()
        marker_environment = default_environment()
        marker_environment["extra"] = ""
        pending_requirements = list(root_requirements)
        expanded: set[str] = set()
        while pending_requirements:
            raw_requirement = pending_requirements.pop()
            try:
                requirement = Requirement(raw_requirement)
            except ValueError as exc:
                raise RuntimeError("pip_inspect_requirement_invalid") from exc
            if requirement.marker and not requirement.marker.evaluate(marker_environment):
                continue
            dependency = canonicalize_name(requirement.name)
            if dependency not in installed:
                raise RuntimeError("pip_inspect_runtime_dependency_missing")
            installed_version, _ = installed[dependency]
            if requirement.specifier and installed_version not in requirement.specifier:
                raise RuntimeError("pip_inspect_runtime_dependency_version_mismatch")
            selected.add(dependency)
            if dependency in expanded:
                continue
            expanded.add(dependency)
            _, dependency_metadata = installed[dependency]
            dependency_requirements = dependency_metadata.get("requires_dist") or []
            if not isinstance(dependency_requirements, list) or not all(
                isinstance(item, str) for item in dependency_requirements
            ):
                raise RuntimeError("pip_inspect_requirements_invalid")
            pending_requirements.extend(dependency_requirements)
        # The repository project is the trust root, but is not a third-party SBOM component.
        selected.discard(root_name)
        metadata_code, metadata_payload, metadata_error = self._command_json(
            [python, "-c", _PYTHON_DISTRIBUTION_METADATA_SCRIPT]
        )
        if (
            metadata_code != 0
            or metadata_error
            or not isinstance(metadata_payload, list)
        ):
            raise RuntimeError(
                f"python_distribution_metadata_{metadata_error or f'exit_{metadata_code}'}"
            )
        distribution_metadata: dict[str, tuple[str, dict[str, Any]]] = {}
        for item in metadata_payload:
            if not isinstance(item, dict):
                raise RuntimeError("python_distribution_metadata_invalid")
            name, version = item.get("name"), item.get("version")
            if not isinstance(name, str) or not isinstance(version, str):
                raise RuntimeError("python_distribution_metadata_invalid")
            normalized_name = canonicalize_name(name)
            if normalized_name not in selected:
                continue
            if normalized_name in distribution_metadata:
                raise RuntimeError("python_distribution_metadata_duplicate")
            distribution_metadata[normalized_name] = (version, item)
        components = []
        for package_name in selected:
            version, metadata = installed[package_name]
            name = metadata["name"]
            distribution = distribution_metadata.get(package_name)
            if distribution is None or distribution[0] != version:
                raise RuntimeError("python_distribution_metadata_version_mismatch")
            expression = _python_license_expression(metadata, distribution[1])
            components.append(Component(ecosystem="python", name=name, version=version,
                purl=f"pkg:pypi/{name.casefold().replace('_', '-')}@{version}",
                source_kind="resolved_environment", lockfile=False, license_expression=expression))
        site_code, site_payload, site_error = self._command_json(
            [python, "-c", "import json,site; print(json.dumps(site.getsitepackages()))"]
        )
        if site_code != 0 or site_error or not isinstance(site_payload, list) or not all(
            isinstance(item, str) for item in site_payload
        ):
            raise RuntimeError(f"python_sites_{site_error or f'exit_{site_code}'}")
        fact = ToolFact(name="pip inspect", version=self._tool_version([python, "-m", "pip", "--version"], "pip"), status="passed", started_at=started,
            completed_at=utc_now(), data_source="explicit Python resolved environment",
            data_source_status="available")
        return sorted(components, key=lambda item: (item.name.casefold(), item.version)), fact, site_payload

    @staticmethod
    def _decisions(path: Path | None, repository_root: Path) -> dict[tuple[str, str, str, str], FindingDecision]:
        if path is None:
            return {}
        if path.is_symlink():
            raise ValueError("decisions must be a regular repository file")
        resolved = path.resolve(strict=True)
        resolved.relative_to(repository_root)
        if not resolved.is_file():
            raise ValueError("decisions must be a regular repository file")
        payload = json.loads(resolved.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
        if not isinstance(payload, list):
            raise ValueError("decisions must contain an array")
        result = {}
        for item in payload:
            if set(item) != {"ecosystem", "package", "version", "advisory", "decision"}:
                raise ValueError("decision entry fields are invalid")
            key = (item["ecosystem"], item["package"], item["version"], item["advisory"])
            if key in result:
                raise ValueError("decision keys must be unique")
            decision = FindingDecision.model_validate(item["decision"])
            for value in (decision.reason, decision.owner):
                _validate_decision_text(value)
            result[key] = decision
        return result

    def _scan(self, ecosystem: Ecosystem, command: list[str], offline: bool,
              installed_versions: dict[str, set[str]], *,
              version_command: list[str] | None = None,
              npm_nodes: dict[str, tuple[str, str]] | None = None) -> tuple[list[Finding], ToolFact]:
        started = utc_now()
        source = {"npm": "npm registry advisory database", "python": "PyPI advisory database", "cargo": "RustSec advisory database"}[ecosystem]
        tool_name = {
            "npm": "npm audit",
            "python": "pip-audit",
            "cargo": "cargo-audit",
        }[ecosystem]
        version_command = version_command or [command[0], "--version"]
        if offline:
            return [], ToolFact(name=tool_name, status="incomplete", started_at=started,
                completed_at=utc_now(), data_source=source, data_source_status="offline_not_queried")
        isolation = {
            "npm": "npm",
            "python": "python",
            "cargo": "cargo-audit",
        }[ecosystem]
        code, payload, error = self._command_json(command, isolated_tool=isolation)
        if error or payload is None:
            return [], ToolFact(name=tool_name, status="incomplete", started_at=started,
                completed_at=utc_now(), data_source=source,
                data_source_status="invalid_response" if error == "parse_error" else "query_failed",
                detail=error or f"exit_{code}",
                version=self._tool_version(
                    version_command, command[0], isolated_tool=isolation
                ))
        try:
            findings = normalize_findings(
                ecosystem, payload, source, installed_versions, npm_nodes=npm_nodes
            )
        except (ValueError, KeyError, TypeError):
            return [], ToolFact(name=tool_name, status="incomplete", started_at=started,
                completed_at=utc_now(), data_source=source, data_source_status="invalid_response", detail="schema_error",
                version=self._tool_version(
                    version_command, command[0], isolated_tool=isolation
                ))
        findings_exit = code == 1 or (ecosystem == "cargo" and code == 0)
        clean_exit = code == 0 or (ecosystem == "python" and code == 1)
        status: StepStatus = (
            "findings"
            if findings and findings_exit
            else ("passed" if not findings and clean_exit else "incomplete")
        )
        data_source_updated_at = None
        if ecosystem == "cargo":
            database = payload.get("database") if isinstance(payload, dict) else None
            if database is not None:
                if not isinstance(database, dict):
                    return [], ToolFact(
                        name="cargo-audit", status="incomplete", started_at=started,
                        completed_at=utc_now(), data_source=source,
                        data_source_status="invalid_response", detail="schema_error",
                        version=self._tool_version(
                            version_command, command[0], isolated_tool=isolation
                        ),
                    )
                last_updated = database.get("last-updated")
                if last_updated is not None:
                    if not isinstance(last_updated, str):
                        return [], ToolFact(
                            name="cargo-audit", status="incomplete", started_at=started,
                            completed_at=utc_now(), data_source=source,
                            data_source_status="invalid_response", detail="schema_error",
                            version=self._tool_version(
                                version_command, command[0], isolated_tool=isolation
                            ),
                        )
                    try:
                        datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                    except ValueError:
                        return [], ToolFact(
                            name="cargo-audit", status="incomplete", started_at=started,
                            completed_at=utc_now(), data_source=source,
                            data_source_status="invalid_response", detail="schema_error",
                            version=self._tool_version(
                                version_command, command[0], isolated_tool=isolation
                            ),
                        )
                    data_source_updated_at = last_updated
        return findings, ToolFact(name=tool_name, status=status, started_at=started,
            completed_at=utc_now(), data_source=source, data_source_status="queried",
            data_source_updated_at=data_source_updated_at,
            version=self._tool_version(
                version_command, command[0], isolated_tool=isolation
            ))

    def run(self, *, python_executable: str = sys.executable,
            pip_audit_python: str | None = None, npm: str = "npm", cargo: str = "cargo",
            cargo_audit_tool: str | None = None, offline: bool = True,
            decisions: Path | None = None) -> SupplyChainSummary:
        run_dir = self.output_dir / self.run_id
        if run_dir.exists() and any(run_dir.iterdir()):
            raise ValueError("supply-chain run directory is not empty")
        run_dir.mkdir(parents=True, exist_ok=True)
        decision_map = self._decisions(decisions, self.repository_root)
        ecosystem_results: list[EcosystemResult] = []
        all_findings: list[Finding] = []
        specs = [
            ("npm", self._npm_components, [npm, "audit", "--registry=https://registry.npmjs.org", "--json"]),
            ("python", lambda: self._python_components(python_executable), None),
            ("cargo", lambda: self._cargo_components(cargo), None),
        ]
        for ecosystem, component_builder, scan_command in specs:
            eco_dir = run_dir / ecosystem
            eco_dir.mkdir()
            tools: list[ToolFact] = []
            try:
                built = component_builder()
                python_sites: list[str] = []
                npm_nodes: dict[str, tuple[str, str]] | None = None
                if ecosystem == "python":
                    components, fact, python_sites = built
                    tools.append(fact)
                elif ecosystem == "npm":
                    components, npm_nodes = built
                elif isinstance(built, tuple):
                    components, fact = built
                    tools.append(fact)
                else:
                    components = built
                licenses = [LicenseRecord(ecosystem=ecosystem, package=item.name,
                    version=item.version, expression=item.license_expression,
                    category=license_category(item.license_expression)[0],
                    policy=license_category(item.license_expression)[1]) for item in components]
                installed_versions: dict[str, set[str]] = {}
                for component in components:
                    normalized_name = (
                        canonicalize_name(component.name)
                        if ecosystem == "python"
                        else component.name.casefold()
                    )
                    installed_versions.setdefault(normalized_name, set()).add(component.version)
                if ecosystem == "python":
                    if pip_audit_python is None:
                        findings, scan_fact = [], ToolFact(
                            name="pip-audit", status="incomplete", started_at=utc_now(),
                            completed_at=utc_now(), data_source="PyPI advisory database",
                            data_source_status=(
                                "offline_not_queried" if offline else "tool_not_provided"
                            ),
                        )
                    else:
                        python_scan_command = [pip_audit_python, "-m", "pip_audit", "--format", "json", "--progress-spinner", "off"]
                        for site_path in python_sites:
                            python_scan_command.extend(["--path", site_path])
                        findings, scan_fact = self._scan(
                            ecosystem,
                            python_scan_command,
                            offline,
                            installed_versions,
                            version_command=[pip_audit_python, "-m", "pip_audit", "--version"],
                        )
                else:
                    if ecosystem == "cargo" and cargo_audit_tool is None:
                        findings, scan_fact = [], ToolFact(name="cargo-audit", status="incomplete",
                            started_at=utc_now(), completed_at=utc_now(), data_source="RustSec advisory database",
                            data_source_status=("offline_not_queried" if offline else "tool_not_provided"))
                    else:
                        actual_command = scan_command or [cargo_audit_tool, "audit", "--json", "--file", "apps/desktop/src-tauri/Cargo.lock"]
                        version_command = (
                            [npm, "--version"]
                            if ecosystem == "npm"
                            else [cargo_audit_tool, "--version"]
                        )
                        findings, scan_fact = self._scan(
                            ecosystem,
                            actual_command,
                            offline,
                            installed_versions,
                            version_command=version_command,
                            npm_nodes=npm_nodes,
                        )
                tools.append(scan_fact)
                for finding in findings:
                    finding.decision = decision_map.get(
                        (finding.ecosystem, finding.package, finding.version, finding.advisory),
                        FindingDecision(),
                    )
                    finding.status = finding.decision.status
                all_findings.extend(findings)
                unresolved = [item for item in findings if item.decision.status in {"pending", "fixed"}]
                status: StepStatus = (
                    "findings"
                    if unresolved
                    else ("passed" if scan_fact.status == "findings" else scan_fact.status)
                )
                pending_count = sum(item.decision.status == "pending" for item in findings)
                fixed_count = sum(item.decision.status == "fixed" for item in findings)
                accepted_count = sum(item.decision.status in {"accepted", "allowlisted"} for item in findings)
                license_counts = {
                    category: sum(item.category == category for item in licenses)
                    for category in _LICENSE_RISK
                }
                unknown_license_count = sum(item.category == "unknown" for item in licenses)
                (eco_dir / "sbom.cdx.json").write_text(json.dumps(cyclonedx(ecosystem, components), indent=2) + "\n", encoding="utf-8")
                (eco_dir / "licenses.json").write_text(json.dumps([item.model_dump(mode="json", by_alias=True) for item in licenses], indent=2) + "\n", encoding="utf-8")
                (eco_dir / "vulnerabilities.json").write_text(json.dumps([item.model_dump(mode="json", by_alias=True) for item in findings], indent=2) + "\n", encoding="utf-8")
                ecosystem_results.append(EcosystemResult(ecosystem=ecosystem, status=status,
                    source_kind="resolved_environment" if ecosystem == "python" else "lockfile",
                    lockfile=ecosystem != "python", component_count=len(components),
                    license_count=len(licenses), finding_count=len(findings),
                    pending_count=pending_count, accepted_count=accepted_count,
                    fixed_count=fixed_count,
                    permissive_license_count=license_counts["permissive"],
                    weak_copyleft_license_count=license_counts["weak_copyleft"],
                    strong_copyleft_license_count=license_counts["strong_copyleft"],
                    restricted_license_count=license_counts["restricted"],
                    unknown_license_count=unknown_license_count,
                    review_required=bool(
                        unresolved
                        or license_counts["weak_copyleft"]
                        or license_counts["strong_copyleft"]
                        or license_counts["restricted"]
                        or unknown_license_count
                    ),
                    sbom=f"{ecosystem}/sbom.cdx.json", licenses=f"{ecosystem}/licenses.json",
                    vulnerabilities=f"{ecosystem}/vulnerabilities.json", tools=tools))
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                failure_payload = {"status": "failed", "errorType": type(exc).__name__}
                for name in ("sbom.cdx.json", "licenses.json", "vulnerabilities.json"):
                    (eco_dir / name).write_text(
                        json.dumps(failure_payload, indent=2) + "\n", encoding="utf-8"
                    )
                ecosystem_results.append(EcosystemResult(ecosystem=ecosystem, status="failed",
                    source_kind="resolved_environment" if ecosystem == "python" else "lockfile",
                    lockfile=ecosystem != "python", component_count=0, license_count=0,
                    finding_count=0, pending_count=0, accepted_count=0, fixed_count=0,
                    permissive_license_count=0, weak_copyleft_license_count=0,
                    strong_copyleft_license_count=0, restricted_license_count=0,
                    unknown_license_count=0, review_required=True,
                    sbom=f"{ecosystem}/sbom.cdx.json",
                    licenses=f"{ecosystem}/licenses.json", vulnerabilities=f"{ecosystem}/vulnerabilities.json",
                    tools=[ToolFact(name="dependency inventory", status="failed", started_at=utc_now(), completed_at=utc_now(), data_source="explicit repository input", data_source_status="failed", detail=type(exc).__name__)]))
        statuses = [item.status for item in ecosystem_results]
        review_required = any(item.review_required for item in ecosystem_results)
        overall: StepStatus = (
            "failed"
            if "failed" in statuses
            else (
                "incomplete"
                if "incomplete" in statuses
                else (
                    "findings"
                    if "findings" in statuses or review_required
                    else "passed"
                )
            )
        )
        summary = SupplyChainSummary(id=self.run_id, generated_at=utc_now(), status=overall,
            ecosystems=ecosystem_results, findings=all_findings,
            boundaries=["Python inventory is a resolved environment, not a lockfile.",
                        "Offline mode does not claim that dependencies have no vulnerabilities.",
                        "No Provider, enterprise Workspace, credential, or business content was read."])
        (run_dir / "summary.json").write_text(json.dumps(summary.model_dump(mode="json", by_alias=True), indent=2) + "\n", encoding="utf-8")
        (run_dir / "summary.md").write_text(render_markdown(summary), encoding="utf-8")
        files = sorted(path for path in run_dir.rglob("*") if path.is_file() and path.name != "checksums.txt")
        (run_dir / "checksums.txt").write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(run_dir).as_posix()}\n" for path in files), encoding="utf-8")
        return summary


def _review_token(value: str) -> str:
    return quote(value, safe="-._~")


def _review_package_token(ecosystem: Ecosystem, package: str) -> str:
    normalized = canonicalize_name(package) if ecosystem == "python" else package
    return _review_token(normalized)


def finding_review_key(
    ecosystem: Ecosystem, package: str, version: str, advisory: str
) -> str:
    """Return the readable, deterministic key for one vulnerability finding."""

    # Advisory identifiers are the stable upstream identity for a finding;
    # the observed version keeps the same advisory in different releases
    # distinct, while the package remains an explicit row field.
    return f"{ecosystem}:finding:{_review_token(advisory)}:{_review_token(version)}"


def license_review_key(ecosystem: Ecosystem, package: str, version: str) -> str:
    """Return the readable, deterministic key for one license review item."""

    return f"{ecosystem}:license:{_review_token(package)}:{_review_token(version)}"


def stable_finding_key(finding: Finding) -> str:
    return finding_review_key(
        finding.ecosystem, finding.package, finding.version, finding.advisory
    )


def stable_license_key(record: LicenseRecord) -> str:
    return license_review_key(record.ecosystem, record.package, record.version)


def _summary_file(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_symlink():
        raise ValueError("supply-chain summary must be a regular file")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError("supply-chain summary is unavailable") from exc
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError("supply-chain summary must be a regular file")
    return resolved


def _summary_locator(path: str | Path | None) -> str:
    """Return a non-sensitive locator suitable for a portable register."""

    if path is None:
        return "summary.json"
    raw = str(path).replace("\\", "/")
    if Path(path).is_absolute() or re.match(r"^[A-Za-z]:/", raw) or raw.startswith("//"):
        return PurePosixPath(raw).name
    return _review_relative_path(raw, label="summary_path").as_posix()


def load_supply_chain_summary(path: str | Path) -> SupplyChainSummary:
    """Load and validate one explicit F-056 summary JSON file."""

    summary_path = _summary_file(path)
    try:
        payload = json.loads(
            summary_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        return SupplyChainSummary.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("supply-chain summary"):
            raise
        raise ValueError("supply-chain summary is invalid") from exc


def _coerce_summary(
    summary: SupplyChainSummary | dict[str, Any] | str | Path,
    summary_path: str | Path | None,
) -> tuple[SupplyChainSummary, Path | None]:
    if isinstance(summary, (str, Path)):
        if summary_path is not None:
            raise ValueError("summary_path must not be repeated")
        resolved = _summary_file(summary)
        return load_supply_chain_summary(resolved), resolved
    resolved = _summary_file(summary_path) if summary_path is not None else None
    if isinstance(summary, SupplyChainSummary):
        return summary, resolved
    try:
        return SupplyChainSummary.model_validate(summary), resolved
    except (TypeError, ValueError) as exc:
        raise ValueError("supply-chain summary is invalid") from exc


def _review_evidence_file(summary_path: Path, value: str, *, label: str) -> tuple[str, Path]:
    relative = _review_relative_path(value, label=label)
    root = summary_path.parent.resolve(strict=True)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} must not traverse a symlink")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} is unavailable or outside the summary directory") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} must reference a regular file")
    return relative.as_posix(), resolved


def _load_json_array(path: Path, *, label: str) -> list[Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if not isinstance(payload, list):
        raise ValueError(f"{label} must contain an array")
    return payload


def _ecosystem_result(summary: SupplyChainSummary, ecosystem: Ecosystem) -> EcosystemResult:
    matches = [item for item in summary.ecosystems if item.ecosystem == ecosystem]
    if len(matches) != 1:
        raise ValueError(f"summary must contain one {ecosystem} ecosystem result")
    return matches[0]


def _finding_source_map(
    summary: SupplyChainSummary, summary_path: Path | None
) -> dict[Ecosystem, str]:
    result: dict[Ecosystem, str] = {}
    for ecosystem in ("npm", "python", "cargo"):
        item = _ecosystem_result(summary, ecosystem)
        source = item.vulnerabilities
        if summary_path is not None:
            source, _ = _review_evidence_file(
                summary_path, source, label=f"{ecosystem} vulnerability evidence"
            )
        else:
            source = _review_relative_path(
                source, label=f"{ecosystem} vulnerability evidence"
            ).as_posix()
        result[ecosystem] = source
    return result


def _license_records_by_ecosystem(
    summary: SupplyChainSummary, summary_path: Path | None
) -> dict[Ecosystem, tuple[str, list[LicenseRecord]]]:
    result: dict[Ecosystem, tuple[str, list[LicenseRecord]]] = {}
    for ecosystem in ("npm", "python", "cargo"):
        ecosystem_result = _ecosystem_result(summary, ecosystem)
        source = ecosystem_result.licenses
        if summary_path is None:
            if ecosystem_result.unknown_license_count:
                raise ValueError(
                    "summary_path is required to register unknown license records"
                )
            result[ecosystem] = (
                _review_relative_path(
                    source, label=f"{ecosystem} license evidence"
                ).as_posix(),
                [],
            )
            continue
        relative, source_path = _review_evidence_file(
            summary_path, source, label=f"{ecosystem} license evidence"
        )
        records = [
            LicenseRecord.model_validate(item)
            for item in _load_json_array(source_path, label=f"{ecosystem} license evidence")
        ]
        unknown_count = sum(item.category == "unknown" for item in records)
        if unknown_count != ecosystem_result.unknown_license_count:
            raise ValueError(
                f"{ecosystem} license evidence unknown count does not match summary"
            )
        result[ecosystem] = (relative, records)
    return result


def _validate_finding_evidence(
    summary: SupplyChainSummary, summary_path: Path | None
) -> dict[Ecosystem, str]:
    sources = _finding_source_map(summary, summary_path)
    if summary_path is None:
        return sources
    summary_by_key = {stable_finding_key(item): item for item in summary.findings}
    if len(summary_by_key) != len(summary.findings):
        raise ValueError("summary finding keys must be unique")
    for ecosystem in ("npm", "python", "cargo"):
        _, path = _review_evidence_file(
            summary_path,
            _ecosystem_result(summary, ecosystem).vulnerabilities,
            label=f"{ecosystem} vulnerability evidence",
        )
        source_findings = [
            Finding.model_validate(item)
            for item in _load_json_array(path, label=f"{ecosystem} vulnerability evidence")
        ]
        source_by_key = {stable_finding_key(item): item for item in source_findings}
        if len(source_by_key) != len(source_findings):
            raise ValueError(f"{ecosystem} vulnerability evidence keys must be unique")
        expected_keys = {
            key for key, item in summary_by_key.items() if item.ecosystem == ecosystem
        }
        if set(source_by_key) != expected_keys:
            raise ValueError(
                f"{ecosystem} vulnerability evidence does not match summary findings"
            )
        for key in expected_keys:
            expected = summary_by_key[key]
            actual = source_by_key[key]
            if (
                actual.severity,
                actual.source,
                actual.impact,
            ) != (expected.severity, expected.source, expected.impact):
                raise ValueError(
                    f"{ecosystem} vulnerability evidence differs from summary"
                )
    return sources


def _expected_review_entries(
    summary: SupplyChainSummary,
    summary_path: Path | None,
    *,
    owner: str | None = None,
    due_date: str | None = None,
) -> list[SupplyChainReviewEntry]:
    finding_sources = _validate_finding_evidence(summary, summary_path)
    license_data = _license_records_by_ecosystem(summary, summary_path)
    entries: list[SupplyChainReviewEntry] = []
    for finding in summary.findings:
        entries.append(
            SupplyChainReviewEntry(
                stable_key=stable_finding_key(finding),
                kind="finding",
                ecosystem=finding.ecosystem,
                package=finding.package,
                version=finding.version,
                advisory=finding.advisory,
                evidence_source=finding_sources[finding.ecosystem],
                source=finding.source,
                observed_impact=finding.impact,
                owner=owner,
                due_date=due_date,
            )
        )
    for ecosystem in ("npm", "python", "cargo"):
        source, records = license_data[ecosystem]
        for record in records:
            if record.category != "unknown":
                continue
            entries.append(
                SupplyChainReviewEntry(
                    stable_key=stable_license_key(record),
                    kind="license",
                    ecosystem=record.ecosystem,
                    package=record.package,
                    version=record.version,
                    license_expression=record.expression,
                    license_category="unknown",
                    license_policy=record.policy,
                    evidence_source=source,
                    source="package metadata",
                    owner=owner,
                    due_date=due_date,
                )
            )
    entries.sort(key=lambda item: item.stable_key)
    if len({item.stable_key for item in entries}) != len(entries):
        raise ValueError("review stable keys must be unique")
    return entries


def build_supply_chain_review_register(
    summary: SupplyChainSummary | dict[str, Any] | str | Path | list[Finding] | tuple[Finding, ...],
    licenses: list[LicenseRecord] | tuple[LicenseRecord, ...] | None = None,
    *,
    summary_path: str | Path | None = None,
    owner: str | None = None,
    due_date: str | None = None,
    evidence_id: str | None = None,
) -> SupplyChainReviewRegister:
    """Build a pending review register from one F-056 summary and its evidence.

    ``summary_path`` is required when the summary reports unknown licenses so
    the package/version rows can be checked against the referenced license
    artifact rather than reconstructed from a count.
    """

    if owner is not None and not owner.strip():
        raise ValueError("review owner must not be empty")
    if (owner is None) != (due_date is None):
        raise ValueError("review owner and due_date must be provided together")
    if due_date is not None:
        _parse_review_date(due_date, label="due_date")
    if isinstance(summary, (list, tuple)):
        if licenses is None:
            raise ValueError("license records are required for record-based registration")
        if summary_path is not None:
            raise ValueError("summary_path is not supported for record-based registration")
        findings = [Finding.model_validate(item) for item in summary]
        license_records = [LicenseRecord.model_validate(item) for item in licenses]
        items: list[SupplyChainReviewEntry] = []
        for finding in findings:
            items.append(
                SupplyChainReviewEntry(
                    stable_key=stable_finding_key(finding),
                    kind="finding",
                    ecosystem=finding.ecosystem,
                    package=finding.package,
                    version=finding.version,
                    advisory=finding.advisory,
                    evidence_source=f"{finding.ecosystem}/vulnerabilities.json",
                    source=finding.source,
                    observed_impact=finding.impact,
                    owner=owner,
                    due_date=due_date,
                )
            )
        for record in license_records:
            if record.category != "unknown":
                continue
            items.append(
                SupplyChainReviewEntry(
                    stable_key=stable_license_key(record),
                    kind="license",
                    ecosystem=record.ecosystem,
                    package=record.package,
                    version=record.version,
                    license_expression=record.expression,
                    license_category="unknown",
                    license_policy=record.policy,
                    evidence_source=f"{record.ecosystem}/licenses.json",
                    source="package metadata",
                    owner=owner,
                    due_date=due_date,
                )
            )
        items.sort(key=lambda item: item.stable_key)
        return SupplyChainReviewRegister(
            evidence_id=evidence_id or DEFAULT_REVIEW_EVIDENCE_ID,
            items=items,
        )
    if licenses is not None:
        raise ValueError("licenses are only accepted with record-based registration")
    if evidence_id is not None:
        raise ValueError("evidence_id is only accepted with record-based registration")
    summary_value, resolved_summary_path = _coerce_summary(summary, summary_path)
    items = _expected_review_entries(
        summary_value,
        resolved_summary_path,
        owner=owner,
        due_date=due_date,
    )
    locator_source: str | Path | None
    if isinstance(summary, (str, Path)):
        locator_source = summary
    else:
        locator_source = summary_path
    locator = _summary_locator(locator_source)
    return SupplyChainReviewRegister(
        evidence_id=summary_value.id,
        summary_path=locator,
        items=items,
    )


def _review_identity(item: SupplyChainReviewEntry) -> tuple[Any, ...]:
    return (
        item.stable_key,
        item.kind,
        item.ecosystem,
        item.package,
        item.version,
        item.advisory,
        item.license_expression,
        item.license_category,
        item.license_policy,
        item.evidence_source,
        item.source,
        item.observed_impact,
    )


def validate_supply_chain_review_register(
    summary: SupplyChainSummary | dict[str, Any] | str | Path,
    register: SupplyChainReviewRegister | dict[str, Any] | str | Path,
    *,
    summary_path: str | Path | None = None,
) -> SupplyChainReviewRegister:
    """Validate an edited register against the exact current evidence set.

    The function raises ``ValueError`` for stale, missing, duplicated, or
    fabricated rows and returns the validated DTO for callers that want to
    continue rendering it.
    """

    summary_value, resolved_summary_path = _coerce_summary(summary, summary_path)
    if isinstance(register, (str, Path)):
        register_path = _summary_file(register)
        try:
            payload = json.loads(
                register_path.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            )
            actual = SupplyChainReviewRegister.model_validate(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError("supply-chain review register is invalid") from exc
    else:
        try:
            actual = (
                register
                if isinstance(register, SupplyChainReviewRegister)
                else SupplyChainReviewRegister.model_validate(register)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("supply-chain review register is invalid") from exc
    expected = build_supply_chain_review_register(
        summary_value, summary_path=resolved_summary_path
    )
    if actual.evidence_id != expected.evidence_id:
        raise ValueError("review register evidence_id does not match summary")
    locators = {expected.summary_path}
    locator_source: str | Path | None
    if isinstance(summary, (str, Path)):
        locator_source = summary
    else:
        locator_source = summary_path
    if locator_source is not None:
        locators.add(_summary_locator(locator_source))
    if actual.summary_path not in locators:
        raise ValueError("review register summary_path does not match summary")
    expected_by_key = {item.stable_key: item for item in expected.items}
    actual_by_key = {item.stable_key: item for item in actual.items}
    if set(actual_by_key) != set(expected_by_key):
        missing = sorted(set(expected_by_key) - set(actual_by_key))
        extra = sorted(set(actual_by_key) - set(expected_by_key))
        raise ValueError(f"review register item set differs (missing={missing}, extra={extra})")
    for key, expected_item in expected_by_key.items():
        if _review_identity(actual_by_key[key]) != _review_identity(expected_item):
            raise ValueError(f"review register evidence fields differ for {key}")
    return actual


def is_supply_chain_review_register_valid(
    summary: SupplyChainSummary | dict[str, Any] | str | Path,
    register: SupplyChainReviewRegister | dict[str, Any] | str | Path,
    *,
    summary_path: str | Path | None = None,
) -> bool:
    try:
        validate_supply_chain_review_register(
            summary, register, summary_path=summary_path
        )
    except ValueError:
        return False
    return True


def write_supply_chain_review_register(
    register: SupplyChainReviewRegister,
    output_path: str | Path,
    *,
    markdown_path: str | Path | None = None,
    overwrite: bool = False,
) -> tuple[Path, Path | None]:
    """Write JSON and an optional Markdown projection without implicit overwrite."""

    if not isinstance(register, SupplyChainReviewRegister):
        raise TypeError("register must be a SupplyChainReviewRegister")
    json_path = Path(output_path)
    md_path = Path(markdown_path) if markdown_path is not None else None
    targets = [json_path] + ([md_path] if md_path is not None else [])
    if not overwrite and any(path.exists() for path in targets):
        raise ValueError("review register output already exists")
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(
            register.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if md_path is not None:
        md_path.write_text(render_supply_chain_review_markdown(register), encoding="utf-8")
    return json_path, md_path


def load_supply_chain_review_register(path: str | Path) -> SupplyChainReviewRegister:
    register_path = _summary_file(path)
    try:
        payload = json.loads(
            register_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
        return SupplyChainReviewRegister.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("supply-chain review register is invalid") from exc


def render_supply_chain_review_markdown(register: SupplyChainReviewRegister) -> str:
    lines = [
        "# AgentAudit Supply Chain Review Register",
        "",
        f"- Evidence: `{register.evidence_id}`",
        f"- Summary: `{register.summary_path}`",
        f"- Generated: `{register.generated_at}`",
        "",
        "| Stable key | Kind | Package | Version | Evidence source | Impact | Reachability | Owner | Status | Action | Due date |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for item in register.items:
        values = (
            item.stable_key,
            item.kind,
            item.package,
            item.version,
            item.evidence_source,
            item.impact,
            item.reachability,
            item.owner or "—",
            item.status,
            item.action,
            item.due_date or "—",
        )
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in values) + " |")
    lines.extend(["", "## Boundaries", ""])
    lines.extend(f"- {boundary}" for boundary in register.boundaries)
    lines.append("")
    return "\n".join(lines)


def normalize_findings(
    ecosystem: Ecosystem,
    payload: Any,
    source: str,
    installed_versions: dict[str, set[str]],
    *,
    npm_nodes: dict[str, tuple[str, str]] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if ecosystem == "npm":
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("vulnerabilities"), dict)
        ):
            raise ValueError("npm audit schema is invalid")
        seen: set[tuple[str, str, str]] = set()
        for package, item in payload["vulnerabilities"].items():
            if not isinstance(package, str) or not isinstance(item, dict):
                raise ValueError("npm audit vulnerability is invalid")
            node_versions: set[str] = set()
            nodes = item.get("nodes")
            if nodes is None and npm_nodes is None:
                versions = installed_versions.get(package.casefold(), set())
                if len(versions) != 1:
                    raise ValueError("npm audit nodes are required for multiple versions")
                node_versions.update(versions)
            else:
                if not isinstance(nodes, list) or not all(isinstance(node, str) for node in nodes):
                    raise ValueError("npm audit nodes are invalid")
                for node in nodes:
                    if npm_nodes is None or node not in npm_nodes:
                        raise ValueError("npm audit node is not installed")
                    node_name, node_version = npm_nodes[node]
                    if node_name.casefold() != package.casefold():
                        raise ValueError("npm audit node package is inconsistent")
                    node_versions.add(node_version)
            if not node_versions:
                raise ValueError("npm audit package is not installed")
            advisories = item.get("via")
            if not isinstance(advisories, list):
                raise ValueError("npm audit advisories are invalid")
            for advisory in advisories:
                if not isinstance(advisory, dict):
                    continue
                advisory_id = str(advisory.get("source", advisory.get("url", "unknown")))
                for installed_version in sorted(node_versions):
                    key = (package.casefold(), installed_version, advisory_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append(Finding(
                        ecosystem="npm",
                        package=package,
                        version=installed_version,
                        advisory=advisory_id,
                        severity=str(advisory.get("severity", item.get("severity", "unknown"))),
                        source=source,
                    ))
    elif ecosystem == "python":
        if not isinstance(payload, (dict, list)):
            raise ValueError("pip-audit schema is invalid")
        rows = payload.get("dependencies", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("pip-audit dependencies are invalid")
        observed_inventory: set[tuple[str, str]] = set()
        for item in rows:
            if not isinstance(item, dict):
                raise ValueError("pip-audit dependency is invalid")
            if "skip_reason" in item:
                if set(item) != {"name", "skip_reason"} or not isinstance(
                    item.get("name"), str
                ) or not isinstance(item.get("skip_reason"), str):
                    raise ValueError("pip-audit skipped dependency is invalid")
                if canonicalize_name(item["name"]) in installed_versions:
                    raise ValueError("pip-audit skipped a product dependency")
                continue
            package, version = item.get("name"), item.get("version")
            if not isinstance(package, str) or not isinstance(version, str):
                raise ValueError("pip-audit dependency is invalid")
            advisories = item.get("vulns")
            if not isinstance(advisories, list):
                raise ValueError("pip-audit vulnerabilities are invalid")
            normalized_name = canonicalize_name(package)
            inventory_versions = installed_versions.get(normalized_name)
            if inventory_versions is None:
                for advisory in advisories:
                    if not isinstance(advisory, dict) or not isinstance(
                        advisory.get("id"), str
                    ):
                        raise ValueError("pip-audit advisory is invalid")
                continue
            if version not in inventory_versions:
                raise ValueError("pip-audit dependency does not match inventory")
            observed_inventory.add((normalized_name, version))
            for advisory in advisories:
                if not isinstance(advisory, dict) or not isinstance(advisory.get("id"), str):
                    raise ValueError("pip-audit advisory is invalid")
                findings.append(Finding(
                    ecosystem="python", package=package, version=version,
                    advisory=advisory["id"], severity="unknown", source=source,
                ))
        expected_inventory = {
            (canonicalize_name(package), version)
            for package, versions in installed_versions.items()
            for version in versions
        }
        if not expected_inventory.issubset(observed_inventory):
            raise ValueError("pip-audit response omitted a product dependency")
    else:
        if not isinstance(payload, dict) or not isinstance(payload.get("vulnerabilities"), dict) or not isinstance(payload["vulnerabilities"].get("list"), list):
            raise ValueError("cargo-audit schema is invalid")
        def cargo_finding(item: Any, impact: str) -> Finding:
            if not isinstance(item, dict):
                raise ValueError("cargo-audit vulnerability is invalid")
            advisory = item.get("advisory", {})
            package = item.get("package", {})
            package_name, package_version = package.get("name"), package.get("version")
            if (
                not isinstance(package_name, str)
                or not isinstance(package_version, str)
                or package_version not in installed_versions.get(package_name.casefold(), set())
                or not isinstance(advisory, dict)
                or not isinstance(advisory.get("id"), str)
            ):
                raise ValueError("cargo-audit finding does not match inventory")
            return Finding(
                ecosystem="cargo", package=package_name, version=package_version,
                advisory=advisory["id"],
                severity=str(advisory.get("severity", "unknown")), source=source,
                impact=impact,
            )

        for item in payload["vulnerabilities"]["list"]:
            findings.append(cargo_finding(item, "vulnerability"))
        warnings = payload.get("warnings", {})
        if not isinstance(warnings, dict):
            raise ValueError("cargo-audit warnings are invalid")
        for warning_kind, warning_items in warnings.items():
            if not isinstance(warning_kind, str) or not isinstance(warning_items, list):
                raise ValueError("cargo-audit warning group is invalid")
            for item in warning_items:
                findings.append(cargo_finding(item, f"rustsec_warning:{warning_kind}"))
    return findings


def render_markdown(summary: SupplyChainSummary) -> str:
    lines = ["# AgentAudit Supply Chain Evidence", "", f"- Run: `{summary.id}`",
             f"- Generated: `{summary.generated_at}`", f"- Status: `{summary.status}`", "",
             "| Ecosystem | Status | Components | Licenses | Permissive | Weak copyleft | Strong copyleft | Restricted | Unknown | Findings | Pending | Accepted | Fixed | Review |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    lines.extend(
        f"| {item.ecosystem} | {item.status} | {item.component_count} | {item.license_count} | {item.permissive_license_count} | {item.weak_copyleft_license_count} | {item.strong_copyleft_license_count} | {item.restricted_license_count} | {item.unknown_license_count} | {item.finding_count} | {item.pending_count} | {item.accepted_count} | {item.fixed_count} | {item.review_required} |"
        for item in summary.ecosystems
    )
    lines.extend(["", "## Findings", "", "| Ecosystem | Package | Version | Advisory | Severity | Impact | Status |", "|---|---|---|---|---|---|---|"])
    lines.extend(f"| {item.ecosystem} | {item.package} | {item.version} | {item.advisory} | {item.severity} | {item.impact} | {item.status} |" for item in summary.findings)
    lines.extend(["", "## Boundaries", ""] + [f"- {item}" for item in summary.boundaries] + [""])
    return "\n".join(lines)


__all__ = [
    "Component",
    "EcosystemResult",
    "Finding",
    "FindingDecision",
    "LicenseRecord",
    "REVIEW_SCHEMA_VERSION",
    "SupplyChainEvidenceRunner",
    "SupplyChainReviewEntry",
    "SupplyChainReviewRegister",
    "SupplyChainSummary",
    "ToolFact",
    "build_supply_chain_review_register",
    "finding_review_key",
    "is_supply_chain_review_register_valid",
    "license_review_key",
    "license_category",
    "load_supply_chain_review_register",
    "load_supply_chain_summary",
    "normalize_findings",
    "render_markdown",
    "render_supply_chain_review_markdown",
    "stable_finding_key",
    "stable_license_key",
    "validate_supply_chain_review_register",
    "write_supply_chain_review_register",
]
