"""Offline, explicit release-evidence bundle generation.

The generator never runs a Provider, Acceptance, or Workspace workflow.  It
copies only regular files explicitly listed by an input manifest and projects
one structured summary into JSON, Markdown, and HTML.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import platform as platform_module
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .schemas import CamelModel


RELEASE_EVIDENCE_INPUT_VERSION = "release-evidence-input.v1"
RELEASE_EVIDENCE_VERSION = "release-evidence.v1"
DEFAULT_RELEASE_EVIDENCE_OUTPUT_DIR = Path("artifacts/release-evidence")

EvidenceProvenance = Literal[
    "real", "controlled_test", "not_provided", "not_verified"
]
EvidenceStatus = Literal[
    "passed", "failed", "not_run", "not_provided", "not_verified"
]
EvidenceCategory = Literal[
    "test", "screenshot", "finding", "replay", "acceptance", "desktop", "supply_chain"
]

_CATEGORY_DIRS: dict[EvidenceCategory, str] = {
    "test": "tests",
    "screenshot": "screenshots",
    "finding": "findings",
    "replay": "replay",
    "acceptance": "acceptance",
    "desktop": "desktop",
    "supply_chain": "supply-chain",
}
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_SENSITIVE_KEY = re.compile(
    r"(?i)(authorization|x-api-key|api[_-]?key|access[_-]?token|client[_-]?secret|password)"
)
_AUTHORIZATION_VALUE = re.compile(r"(?i)\bauthorization\s*[:=]\s*[^\s,;]+")
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+\-/=]{8,}")
_API_KEY_VALUE = re.compile(
    r"(?i)\b(?:x-api-key|api[_-]?key|access[_-]?token|client[_-]?secret|password)"
    r"\s*[:=]\s*['\"]?[^\s,'\";}]{4,}"
)
_TEXT_SUFFIXES = {
    ".json", ".md", ".txt", ".html", ".htm", ".xml", ".yaml", ".yml",
    ".csv", ".log",
}


class ReleaseEvidenceError(RuntimeError):
    """Raised when an evidence bundle violates an explicit trust boundary."""


class ReleaseEvidenceInputArtifact(CamelModel):
    id: str
    category: EvidenceCategory
    path: str | None = None
    status: EvidenceStatus
    provenance: EvidenceProvenance
    label: str | None = None

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _SAFE_RUN_ID.fullmatch(value):
            raise ValueError("artifact id must use letters, digits, dot, dash, or underscore")
        return value

    @model_validator(mode="after")
    def validate_path_for_status(self) -> "ReleaseEvidenceInputArtifact":
        if self.status in {"not_run", "not_provided", "not_verified"}:
            if self.path is not None:
                raise ValueError("not_* evidence must not reference an artifact file")
        elif self.path is None:
            raise ValueError("passed or failed evidence requires an artifact file")
        if self.status in {"passed", "failed"} and self.provenance in {
            "not_provided",
            "not_verified",
        }:
            raise ValueError("passed or failed evidence requires real or controlled_test provenance")
        if self.status == "not_provided" and self.provenance != "not_provided":
            raise ValueError("not_provided status requires not_provided provenance")
        if self.status == "not_verified" and self.provenance != "not_verified":
            raise ValueError("not_verified status requires not_verified provenance")
        if self.status == "not_run" and self.provenance not in {
            "controlled_test",
            "not_verified",
        }:
            raise ValueError("not_run evidence requires controlled_test or not_verified provenance")
        return self


class ReleaseEvidenceInput(CamelModel):
    schema_version: Literal["release-evidence-input.v1"] = RELEASE_EVIDENCE_INPUT_VERSION
    product_version: str | None = None
    git_revision: str | None = None
    dirty_worktree: bool | None = None
    platform: str | None = None
    python_version: str | None = None
    artifacts: list[ReleaseEvidenceInputArtifact] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def artifact_ids_must_be_unique(self) -> "ReleaseEvidenceInput":
        ids = [artifact.id for artifact in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("artifact ids must be unique")
        return self


class ReleaseEvidenceArtifact(CamelModel):
    id: str
    category: EvidenceCategory
    path: str | None = None
    status: EvidenceStatus
    provenance: EvidenceProvenance
    label: str | None = None
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class ReleaseEvidenceEnvironment(CamelModel):
    product_version: str | None = None
    git_revision: str | None = None
    dirty_worktree: bool | None = None
    platform: str
    python_version: str


class ReleaseEvidenceCounts(CamelModel):
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    not_run: int = Field(ge=0)
    not_provided: int = Field(ge=0)
    not_verified: int = Field(ge=0)


class ReleaseEvidenceSummary(CamelModel):
    schema_version: Literal["release-evidence.v1"] = RELEASE_EVIDENCE_VERSION
    id: str
    generated_at: str
    status: Literal["passed", "failed", "incomplete"]
    environment: ReleaseEvidenceEnvironment
    counts: ReleaseEvidenceCounts
    artifacts: list[ReleaseEvidenceArtifact]
    boundaries: list[str]


class ReleaseEvidenceManifest(CamelModel):
    schema_version: Literal["release-evidence.v1"] = RELEASE_EVIDENCE_VERSION
    run_id: str
    summary: str = "summary.json"
    environment: str = "environment.json"
    markdown: str = "summary.md"
    html: str = "summary.html"
    checksums: str = "checksums.txt"
    artifacts: list[str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_input_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseEvidenceError("artifact path must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or path.anchor or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseEvidenceError("artifact path must stay within the input manifest directory")
    if re.match(r"^[A-Za-z]:", normalized):
        raise ReleaseEvidenceError("artifact path must be relative")
    return path


def _contains_reparse_or_symlink(root: Path, relative: PurePosixPath) -> bool:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
        try:
            if current.exists() and current.stat(follow_symlinks=False).st_file_attributes & 0x400:
                return True
        except AttributeError:
            pass
    return False


def _validate_source_file(root: Path, value: str) -> Path:
    relative = _relative_input_path(value)
    if _contains_reparse_or_symlink(root, relative):
        raise ReleaseEvidenceError("artifact path must not traverse a symlink or reparse point")
    source = root.joinpath(*relative.parts)
    try:
        resolved_root = root.resolve(strict=True)
        resolved_source = source.resolve(strict=True)
    except OSError as exc:
        raise ReleaseEvidenceError("artifact file is unavailable") from exc
    try:
        resolved_source.relative_to(resolved_root)
    except ValueError as exc:
        raise ReleaseEvidenceError("artifact path escapes the input manifest directory") from exc
    if not resolved_source.is_file():
        raise ReleaseEvidenceError("artifact path must reference a regular file")
    return resolved_source


def _reject_sensitive_text(text: str, *, user_home: str | None) -> None:
    if user_home and user_home.strip() and user_home.casefold() in text.casefold():
        raise ReleaseEvidenceError("evidence contains the current user home path")
    if _AUTHORIZATION_VALUE.search(text) or _BEARER_VALUE.search(text) or _API_KEY_VALUE.search(text):
        raise ReleaseEvidenceError("evidence contains an authentication secret")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if _SENSITIVE_KEY.search(str(key)) and item not in {None, "", False}:
                    raise ReleaseEvidenceError("evidence contains a sensitive structured field")
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)


def _validate_text_artifact(path: Path, *, user_home: str | None) -> None:
    if path.suffix.casefold() not in _TEXT_SUFFIXES:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseEvidenceError("text evidence must be readable UTF-8") from exc
    _reject_sensitive_text(text, user_home=user_home)


def _counts(artifacts: list[ReleaseEvidenceArtifact]) -> ReleaseEvidenceCounts:
    statuses = [artifact.status for artifact in artifacts]
    return ReleaseEvidenceCounts(
        total=len(statuses),
        passed=statuses.count("passed"),
        failed=statuses.count("failed"),
        not_run=statuses.count("not_run"),
        not_provided=statuses.count("not_provided"),
        not_verified=statuses.count("not_verified"),
    )


def _overall_status(counts: ReleaseEvidenceCounts) -> Literal["passed", "failed", "incomplete"]:
    if counts.failed:
        return "failed"
    if counts.not_run or counts.not_provided or counts.not_verified:
        return "incomplete"
    return "passed"


def _json_text(value: CamelModel) -> str:
    return json.dumps(
        value.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
    ) + "\n"


def render_release_evidence_markdown(summary: ReleaseEvidenceSummary) -> str:
    lines = [
        "# AgentAudit Release Evidence",
        "",
        f"- Run: `{summary.id}`",
        f"- Generated: `{summary.generated_at}`",
        f"- Status: `{summary.status}`",
        f"- Product: `{summary.environment.product_version or 'not_provided'}`",
        f"- Git Revision: `{summary.environment.git_revision or 'not_provided'}`",
        f"- Dirty Worktree: `{summary.environment.dirty_worktree if summary.environment.dirty_worktree is not None else 'not_provided'}`",
        f"- Platform: `{summary.environment.platform}`",
        f"- Python: `{summary.environment.python_version}`",
        "",
        "## Counts",
        "",
        f"- Total: `{summary.counts.total}`",
        f"- Passed: `{summary.counts.passed}`",
        f"- Failed: `{summary.counts.failed}`",
        f"- Not Run: `{summary.counts.not_run}`",
        f"- Not Provided: `{summary.counts.not_provided}`",
        f"- Not Verified: `{summary.counts.not_verified}`",
        "",
        "## Evidence",
        "",
        "| ID | Category | Status | Provenance | Artifact |",
        "|---|---|---|---|---|",
    ]
    for artifact in summary.artifacts:
        label = (artifact.label or artifact.id).replace("|", "\\|")
        path = artifact.path or "—"
        lines.append(
            f"| {label} | {artifact.category} | {artifact.status} | "
            f"{artifact.provenance} | `{path}` |"
        )
    lines.extend(["", "## Boundaries", ""])
    lines.extend(f"- {boundary}" for boundary in summary.boundaries)
    lines.append("")
    return "\n".join(lines)


def render_release_evidence_html(summary: ReleaseEvidenceSummary) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(artifact.label or artifact.id)}</td>"
        f"<td>{html.escape(artifact.category)}</td>"
        f"<td>{html.escape(artifact.status)}</td>"
        f"<td>{html.escape(artifact.provenance)}</td>"
        f"<td><code>{html.escape(artifact.path or '—')}</code></td>"
        "</tr>"
        for artifact in summary.artifacts
    )
    boundaries = "".join(f"<li>{html.escape(item)}</li>" for item in summary.boundaries)
    product = summary.environment.product_version or "not_provided"
    revision = summary.environment.git_revision or "not_provided"
    dirty = (
        str(summary.environment.dirty_worktree).lower()
        if summary.environment.dirty_worktree is not None
        else "not_provided"
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentAudit Release Evidence</title><style>
body{{font-family:system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#0b203a;background:#f4f7fb}}
main{{background:#fff;border:1px solid #d9e2ef;border-radius:18px;padding:32px}}table{{border-collapse:collapse;width:100%}}
th,td{{border-bottom:1px solid #d9e2ef;padding:12px;text-align:left}}code{{overflow-wrap:anywhere}}
</style></head><body><main><h1>AgentAudit Release Evidence</h1>
<p>Run <code>{html.escape(summary.id)}</code> · Status <strong>{html.escape(summary.status)}</strong></p>
<p>Generated {html.escape(summary.generated_at)}</p>
<dl><dt>Product</dt><dd><code>{html.escape(product)}</code></dd><dt>Git revision</dt><dd><code>{html.escape(revision)}</code></dd>
<dt>Dirty worktree</dt><dd><code>{dirty}</code></dd><dt>Platform</dt><dd><code>{html.escape(summary.environment.platform)}</code></dd>
<dt>Python</dt><dd><code>{html.escape(summary.environment.python_version)}</code></dd></dl>
<h2>Counts</h2><ul><li>Total: {summary.counts.total}</li><li>Passed: {summary.counts.passed}</li><li>Failed: {summary.counts.failed}</li>
<li>Not run: {summary.counts.not_run}</li><li>Not provided: {summary.counts.not_provided}</li><li>Not verified: {summary.counts.not_verified}</li></ul>
<h2>Evidence</h2><table><thead><tr><th>ID</th><th>Category</th><th>Status</th><th>Provenance</th><th>Artifact</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Boundaries</h2><ul>{boundaries}</ul></main></body></html>"""


def _write_release_evidence_bundle(summary: ReleaseEvidenceSummary, run_dir: str | Path) -> Path:
    """Write final projections after the runner has reserved an empty run."""
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary_path = root / "summary.json"
    summary_path.write_text(_json_text(summary), encoding="utf-8")
    (root / "summary.md").write_text(render_release_evidence_markdown(summary), encoding="utf-8")
    (root / "summary.html").write_text(render_release_evidence_html(summary), encoding="utf-8")
    (root / "environment.json").write_text(_json_text(summary.environment), encoding="utf-8")
    manifest = ReleaseEvidenceManifest(
        run_id=summary.id,
        artifacts=[artifact.path for artifact in summary.artifacts if artifact.path is not None],
    )
    (root / "manifest.json").write_text(_json_text(manifest), encoding="utf-8")
    checksum_files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.name != "checksums.txt"
    )
    checksum_lines = [
        f"{_sha256(path)}  {path.relative_to(root).as_posix()}" for path in checksum_files
    ]
    (root / "checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return root


class ReleaseEvidenceRunner:
    """Build one immutable release-evidence run from one explicit manifest."""

    def __init__(self, output_dir: str | Path, *, run_id: str | None = None) -> None:
        self.output_dir = Path(output_dir)
        self.run_id = run_id or f"release_{uuid.uuid4().hex[:12]}"
        if not _SAFE_RUN_ID.fullmatch(self.run_id):
            raise ValueError("run_id must use letters, digits, dot, dash, or underscore")

    def run(self, input_manifest: str | Path) -> ReleaseEvidenceSummary:
        manifest_path = Path(input_manifest)
        try:
            manifest_root = manifest_path.parent.resolve(strict=True)
            manifest_file = manifest_path.resolve(strict=True)
        except OSError as exc:
            raise ReleaseEvidenceError("input manifest is unavailable") from exc
        if manifest_file.parent != manifest_root or manifest_file.is_symlink() or not manifest_file.is_file():
            raise ReleaseEvidenceError("input manifest must be a regular file")
        try:
            manifest_text = manifest_file.read_text(encoding="utf-8")
            _reject_sensitive_text(manifest_text, user_home=str(Path.home()))
            manifest = ReleaseEvidenceInput.model_validate_json(manifest_text)
        except ReleaseEvidenceError:
            raise
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ReleaseEvidenceError("input manifest is invalid") from exc

        run_dir = self.output_dir / self.run_id
        if run_dir.exists() and any(run_dir.iterdir()):
            raise ReleaseEvidenceError("release evidence run directory is not empty")

        sources: list[tuple[ReleaseEvidenceInputArtifact, Path | None]] = []
        for artifact in manifest.artifacts:
            source = None
            try:
                if artifact.path is not None:
                    source = _validate_source_file(manifest_root, artifact.path)
                    _validate_text_artifact(source, user_home=str(Path.home()))
            except ReleaseEvidenceError as exc:
                raise ReleaseEvidenceError(f"artifact {artifact.id}: {exc}") from exc
            sources.append((artifact, source))

        run_dir.mkdir(parents=True, exist_ok=True)
        output_artifacts: list[ReleaseEvidenceArtifact] = []
        try:
            for artifact, source in sources:
                output_path: Path | None = None
                if source is not None:
                    category_dir = run_dir / _CATEGORY_DIRS[artifact.category]
                    category_dir.mkdir(parents=True, exist_ok=True)
                    output_path = category_dir / f"{artifact.id}{source.suffix.lower()}"
                    shutil.copyfile(source, output_path)
                output_artifacts.append(
                    ReleaseEvidenceArtifact(
                        id=artifact.id,
                        category=artifact.category,
                        path=output_path.relative_to(run_dir).as_posix() if output_path else None,
                        status=artifact.status,
                        provenance=artifact.provenance,
                        label=artifact.label,
                        sha256=_sha256(output_path) if output_path else None,
                        size_bytes=output_path.stat().st_size if output_path else None,
                    )
                )
            counts = _counts(output_artifacts)
            summary = ReleaseEvidenceSummary(
                id=self.run_id,
                generated_at=_utc_now(),
                status=_overall_status(counts),
                environment=ReleaseEvidenceEnvironment(
                    product_version=manifest.product_version,
                    git_revision=manifest.git_revision,
                    dirty_worktree=manifest.dirty_worktree,
                    platform=manifest.platform or platform_module.platform(),
                    python_version=manifest.python_version or platform_module.python_version(),
                ),
                counts=counts,
                artifacts=output_artifacts,
                boundaries=manifest.boundaries,
            )
            _write_release_evidence_bundle(summary, run_dir)
            return summary
        except Exception:
            for name in ("summary.json", "summary.md", "summary.html", "manifest.json", "environment.json", "checksums.txt"):
                try:
                    (run_dir / name).unlink(missing_ok=True)
                except OSError:
                    pass
            raise


__all__ = [
    "DEFAULT_RELEASE_EVIDENCE_OUTPUT_DIR",
    "EvidenceCategory",
    "EvidenceProvenance",
    "EvidenceStatus",
    "ReleaseEvidenceArtifact",
    "ReleaseEvidenceCounts",
    "ReleaseEvidenceEnvironment",
    "ReleaseEvidenceError",
    "ReleaseEvidenceInput",
    "ReleaseEvidenceInputArtifact",
    "ReleaseEvidenceManifest",
    "ReleaseEvidenceRunner",
    "ReleaseEvidenceSummary",
    "render_release_evidence_html",
    "render_release_evidence_markdown",
]
