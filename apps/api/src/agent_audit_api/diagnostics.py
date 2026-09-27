"""Strict allowlist diagnostics bundle for local operational support."""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from pydantic import Field

from .app_paths import AppPaths
from .schemas import CamelModel
from .workspace import AuditWorkspace


SIDECAR_STATUS_NAME = "sidecar.status.json"
LOG_LIMIT_BYTES = 4 * 1024 * 1024
TEXT_LIMIT_BYTES = 5 * 1024 * 1024
SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(?:authorization|x-api-key|api[_-]?key|credential|secret|password|access_token|refresh_token|token)\s*[:=]\s*\S+"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)
USER_HOME_PATTERNS = (
    re.compile(r"(?i)(?:[A-Z]:[\\/]+Users|[\\/]{2,}[^\\/]+[\\/]+Users)[\\/]+[^\\/\s\"']+"),
    re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users)/[^/\s\"']+"),
)
EXCLUDED = [
    "凭据与环境变量中的 Secret",
    "Provider 连接设置",
    "SQLite 数据库",
    "业务 JSON 与文档正文",
    "Prompt、Provider 响应、Trace、Finding 与 Replay 正文",
]
DISCLAIMER = (
    "诊断包全程在本地生成且不会上传，仅供运维排障；"
    "不构成根因判断、Finding 或安全结论。"
)


class DiagnosticExportError(RuntimeError):
    """Raised when the bundle cannot satisfy its disclosure boundary."""


class DiagnosticCategory(CamelModel):
    id: str
    label: str
    available: bool
    count: int = Field(ge=0)


class DiagnosticPreview(CamelModel):
    included: list[DiagnosticCategory]
    excluded: list[str]
    local_only: bool = True
    suggested_filename: str
    disclaimer: str = DISCLAIMER


class DiagnosticFile(CamelModel):
    path: str
    category: str
    size_bytes: int = Field(ge=0)
    sha256: str


class DiagnosticManifest(CamelModel):
    schema_version: int = 1
    created_at: str
    operation_id: str
    product_version: str
    included: list[DiagnosticCategory]
    excluded: list[str]
    runtime: dict[str, Any]
    sidecar: dict[str, Any] | None
    workspace: dict[str, Any] | None
    files: list[DiagnosticFile]
    disclaimer: str = DISCLAIMER


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _relative_member(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise DiagnosticExportError("diagnostic member path is not a safe relative path")
    return path.as_posix()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _safe_text(raw: bytes) -> bytes:
    if len(raw) > TEXT_LIMIT_BYTES:
        raise DiagnosticExportError("diagnostic text exceeds the export boundary")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiagnosticExportError("diagnostic text is not UTF-8") from exc
    homes = {str(Path.home()), str(Path.home()).replace("\\", "/")}
    if any(home and home in text for home in homes) or any(
        pattern.search(text) for pattern in USER_HOME_PATTERNS
    ):
        raise DiagnosticExportError("diagnostic text contains the current user home path")
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise DiagnosticExportError("diagnostic text contains a credential-shaped value")
    return raw


class DiagnosticBundleService:
    def __init__(
        self,
        app_paths: AppPaths,
        *,
        workspace: AuditWorkspace | None = None,
        runtime_supplier: Callable[[], dict[str, Any]] | None = None,
        product_version: str,
    ) -> None:
        self.app_paths = app_paths
        self.workspace = workspace
        self.runtime_supplier = runtime_supplier or self._default_runtime
        self.product_version = product_version

    def _log_files(self) -> list[Path]:
        if not self.app_paths.logs_dir.is_dir():
            return []
        result: list[Path] = []
        root = self.app_paths.logs_dir.resolve()
        for candidate in sorted(self.app_paths.logs_dir.glob("agent-audit.jsonl*")):
            if candidate.is_symlink() or not candidate.is_file():
                raise DiagnosticExportError("diagnostic log is not a regular local file")
            resolved = candidate.resolve()
            try:
                resolved.relative_to(root)
            except ValueError as exc:
                raise DiagnosticExportError("diagnostic log escapes logs_dir") from exc
            if candidate.stat().st_size > LOG_LIMIT_BYTES:
                raise DiagnosticExportError("diagnostic log exceeds the export boundary")
            result.append(candidate)
        return result

    def _sidecar(self) -> dict[str, Any] | None:
        path = self.app_paths.runtime_dir / SIDECAR_STATUS_NAME
        if not path.is_file() or path.is_symlink():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DiagnosticExportError("sidecar status metadata is unreadable") from exc
        if not isinstance(payload, dict):
            raise DiagnosticExportError("sidecar status metadata is invalid")
        detail = payload.get("detail")
        return {
            "status": payload.get("status"),
            "host": payload.get("host"),
            "port": payload.get("port"),
            "errorType": type(detail).__name__ if detail is not None else None,
        }

    def _workspace(self) -> dict[str, Any] | None:
        if self.workspace is None:
            return None
        manifest = self.workspace.manifest
        return {
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
            "documentsDir": manifest.documents_dir,
            "contractDir": manifest.contract_dir,
            "casesDir": manifest.cases_dir,
            "historyDir": manifest.history_dir,
            "exportsDir": manifest.exports_dir,
        }

    def _default_runtime(self) -> dict[str, Any]:
        return {
            "platform": sys.platform,
            "os": platform.system(),
            "osRelease": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "pid": os.getpid(),
        }

    def preview(self) -> DiagnosticPreview:
        logs = self._log_files()
        sidecar = self._sidecar()
        workspace = self._workspace()
        included = [
            DiagnosticCategory(id="logs", label="有界结构化日志", available=bool(logs), count=len(logs)),
            DiagnosticCategory(id="runtime", label="运行环境元数据", available=True, count=1),
            DiagnosticCategory(id="sidecar", label="Sidecar 状态元数据", available=sidecar is not None, count=int(sidecar is not None)),
            DiagnosticCategory(id="workspace", label="Workspace manifest 元数据", available=workspace is not None, count=int(workspace is not None)),
        ]
        return DiagnosticPreview(
            included=included,
            excluded=list(EXCLUDED),
            suggested_filename=f"agent-audit-diagnostics-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.zip",
        )

    def build(self, operation_id: str) -> bytes:
        if not operation_id or not re.fullmatch(r"[0-9a-f]{32}", operation_id):
            raise DiagnosticExportError("operation ID is invalid")
        preview = self.preview()
        members: dict[str, tuple[str, bytes]] = {}
        for index, path in enumerate(self._log_files(), start=1):
            members[f"logs/runtime-{index}.jsonl"] = ("logs", _safe_text(path.read_bytes()))
        runtime = self.runtime_supplier()
        sidecar = self._sidecar()
        workspace = self._workspace()
        members["runtime.json"] = ("runtime", _safe_text(_json_bytes(runtime)))
        if sidecar is not None:
            members["sidecar/status.json"] = ("sidecar", _safe_text(_json_bytes(sidecar)))
        if workspace is not None:
            members["workspace/manifest.json"] = ("workspace", _safe_text(_json_bytes(workspace)))
        files = [
            DiagnosticFile(
                path=_relative_member(name),
                category=category,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
            for name, (category, content) in sorted(members.items())
        ]
        manifest = DiagnosticManifest(
            created_at=_now(),
            operation_id=operation_id,
            product_version=self.product_version,
            included=preview.included,
            excluded=preview.excluded,
            runtime=runtime,
            sidecar=sidecar,
            workspace=workspace,
            files=files,
        )
        manifest_bytes = _safe_text(_json_bytes(manifest.model_dump(by_alias=True)))
        readme = self._readme(manifest)
        members["manifest.json"] = ("manifest", manifest_bytes)
        members["README.md"] = ("manifest", _safe_text(readme.encode("utf-8")))
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, (_, content) in sorted(members.items()):
                archive.writestr(_relative_member(name), content)
        return output.getvalue()

    @staticmethod
    def _readme(manifest: DiagnosticManifest) -> str:
        lines = [
            "# AgentAudit 本地诊断包",
            "",
            manifest.disclaimer,
            "",
            f"- Operation ID：`{manifest.operation_id}`",
            f"- 生成时间：`{manifest.created_at}`",
            f"- 产品版本：`{manifest.product_version}`",
            "",
            "## 包含内容",
            "",
        ]
        lines.extend(
            f"- {item.label}：{'可用' if item.available else '不可用'}（{item.count}）"
            for item in manifest.included
        )
        lines.extend(["", "## 明确排除", ""])
        lines.extend(f"- {item}" for item in manifest.excluded)
        lines.extend(["", "本诊断包全程在本地生成，未上传到任何外部服务，仅供排障。\n"])
        return "\n".join(lines)


__all__ = [
    "DiagnosticBundleService",
    "DiagnosticCategory",
    "DiagnosticExportError",
    "DiagnosticFile",
    "DiagnosticManifest",
    "DiagnosticPreview",
]
