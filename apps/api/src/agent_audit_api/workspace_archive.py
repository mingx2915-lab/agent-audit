"""Portable Workspace backup, inspection, and copy-as-new restore support."""

from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import Field, field_validator

from .app_paths import AppPaths, resolve_app_paths
from .schemas import CamelModel
from .security_contract import SecurityContract
from .workspace import (
    HISTORY_DATABASE_FILENAME,
    MANIFEST_FILENAME,
    AuditWorkspace,
    WorkspaceError,
    WorkspaceManifest,
    WorkspaceService,
)


BACKUP_FORMAT_VERSION = 1
BACKUP_METADATA_FILENAME = "metadata.json"
BACKUP_WORKSPACE_PREFIX = "workspace/"
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _non_empty(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("workspace summary text must be non-empty")
    return value


def _safe_relative_directory(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("relativeDirectory must be a non-empty directory name")
    if "\\" in value or "/" in value:
        raise ValueError("relativeDirectory must be one directory name")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or posix.anchor
        or windows.anchor
        or posix.parts in ((), (".",), ("..",))
        or any(part in ("", ".", "..") for part in posix.parts)
    ):
        raise ValueError("relativeDirectory must be one safe relative directory name")
    return value


class WorkspaceArchiveError(ValueError):
    """Base class for errors that can be diagnosed at the API boundary."""


class WorkspaceArchiveWorkspaceError(WorkspaceArchiveError):
    """Raised when no active Workspace is available for an operation."""


class WorkspaceArchiveValidationError(WorkspaceArchiveError):
    """Raised when a backup is not a supported AgentAudit archive."""


class WorkspaceArchiveStorageError(RuntimeError):
    """Raised when local archive or Workspace storage cannot be completed."""


class WorkspaceSummary(CamelModel):
    """Portable identity for one Workspace below the application data root."""

    id: str
    name: str
    relative_directory: str
    contract_id: str
    contract_version: int = Field(gt=0)
    document_count: int = Field(ge=0)
    history_included: bool
    active: bool

    _validate_text = field_validator(
        "id", "name", "contract_id"
    )(_non_empty)
    _validate_relative_directory = field_validator("relative_directory")(
        _safe_relative_directory
    )


class WorkspaceBackupPreview(CamelModel):
    """Pure inspection result for one portable Workspace ZIP."""

    format_version: Literal[1] = 1
    workspace: WorkspaceSummary
    archive_size_bytes: int = Field(ge=1)
    created_at: str

    _validate_created_at = field_validator("created_at")(_non_empty)


class WorkspaceRestoreResult(CamelModel):
    """Result of restoring a validated archive as a new non-active Workspace."""

    workspace: WorkspaceSummary
    restored: Literal[True] = True
    restart_required: Literal[True] = True


@dataclass(frozen=True)
class _ArchiveSnapshot:
    summary: WorkspaceSummary
    created_at: str
    manifest: WorkspaceManifest
    members: dict[str, bytes]


def _member_name(name: str) -> str:
    """Validate and normalize one ZIP member without resolving a filesystem path."""

    if not isinstance(name, str) or not name or "\\" in name:
        raise WorkspaceArchiveValidationError("archive member path is not portable")
    trimmed = name[:-1] if name.endswith("/") else name
    path = PurePosixPath(trimmed)
    if (
        not trimmed
        or path.is_absolute()
        or PureWindowsPath(trimmed).is_absolute()
        or PureWindowsPath(trimmed).anchor
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise WorkspaceArchiveValidationError(
            "archive member path must be relative and stay inside the archive"
        )
    return "/".join(path.parts) + ("/" if name.endswith("/") else "")


def _json_object(raw: bytes, description: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceArchiveValidationError(f"{description} must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise WorkspaceArchiveValidationError(f"{description} must contain an object")
    return value


class WorkspaceArchiveService:
    """Create and restore complete portable Workspace snapshots.

    The service never changes the active Workspace during backup or Preview.
    Restore extracts into a temporary sibling, validates it through the normal
    Workspace loader, and only then renames it into the application workspaces
    directory.  The active application must be restarted/activated by Desktop
    after the returned relative directory is explicitly chosen by the user.
    """

    def __init__(
        self,
        workspace: AuditWorkspace | None,
        app_paths: AppPaths | None = None,
    ) -> None:
        self.workspace = workspace
        self.app_paths = app_paths if app_paths is not None else resolve_app_paths()

    @property
    def workspaces_root(self) -> Path:
        # ``default_workspace_dir`` is the platform-neutral source of truth
        # for the Desktop workspace root (home/workspaces on Windows, and the
        # XDG data root/workspaces on Linux).  Do not derive this from
        # ``data_dir``: Linux keeps XDG data and other app roots separate, and
        # the Desktop activation command resolves the same parent.
        return self.app_paths.default_workspace_dir.parent.expanduser().resolve()

    def _require_workspace(self) -> AuditWorkspace:
        if self.workspace is None:
            raise WorkspaceArchiveWorkspaceError("active Workspace is unavailable")
        return self.workspace

    def _relative_directory(self, root: Path) -> str:
        parent = self.workspaces_root
        try:
            relative = root.resolve().relative_to(parent)
            if len(relative.parts) == 1:
                return _safe_relative_directory(relative.name)
        except (ValueError, OSError):
            pass
        # Development/Test Workspaces may be explicitly placed elsewhere.  A
        # basename is still portable and does not disclose the source path.
        return _safe_relative_directory(root.name)

    @staticmethod
    def _read_json_file(path: Path, description: str) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceArchiveStorageError(f"unable to read {description}") from exc

    def _current_summary(self, *, active: bool) -> WorkspaceSummary:
        workspace = self._require_workspace()
        contract_payload = self._read_json_file(
            workspace.security_contract_path, "security contract"
        )
        try:
            contract = SecurityContract.model_validate(contract_payload)
        except ValueError as exc:
            raise WorkspaceArchiveStorageError("security contract is invalid") from exc
        documents = self._read_json_file(workspace.documents_file_path, "knowledge documents")
        if not isinstance(documents, list):
            raise WorkspaceArchiveStorageError("knowledge_documents.json must contain an array")
        return WorkspaceSummary(
            id=workspace.manifest.id,
            name=workspace.manifest.name,
            relative_directory=self._relative_directory(workspace.root),
            contract_id=contract.id,
            contract_version=contract.version,
            document_count=len(documents),
            history_included=workspace.history_database_path.is_file(),
            active=active,
        )

    def summary(self) -> WorkspaceSummary:
        """Return the current safe Workspace projection without touching history."""

        return self._current_summary(active=True)

    current_summary = summary

    @staticmethod
    def _sqlite_snapshot(path: Path) -> bytes:
        """Take a consistent copy of one SQLite database using the stdlib API."""

        temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        source: sqlite3.Connection | None = None
        destination: sqlite3.Connection | None = None
        try:
            temporary_directory = tempfile.TemporaryDirectory(prefix="agent-audit-backup-")
            destination_path = Path(temporary_directory.name) / HISTORY_DATABASE_FILENAME
            source = sqlite3.connect(str(path))
            destination = sqlite3.connect(str(destination_path))
            source.backup(destination)
            destination.commit()
            return destination_path.read_bytes()
        except (OSError, sqlite3.Error) as exc:
            raise WorkspaceArchiveStorageError(
                "unable to create a consistent SQLite history snapshot"
            ) from exc
        finally:
            if source is not None:
                source.close()
            if destination is not None:
                destination.close()
            if temporary_directory is not None:
                temporary_directory.cleanup()

    def _workspace_files(self) -> dict[str, bytes]:
        workspace = self._require_workspace()
        members: dict[str, bytes] = {}
        try:
            paths = sorted(workspace.root.rglob("*"), key=lambda path: path.as_posix())
        except OSError as exc:
            raise WorkspaceArchiveStorageError("unable to enumerate Workspace files") from exc
        for path in paths:
            if path.is_symlink():
                raise WorkspaceArchiveStorageError("Workspace cannot contain symbolic links")
            if not path.is_file():
                continue
            try:
                relative = path.relative_to(workspace.root).as_posix()
                _member_name(BACKUP_WORKSPACE_PREFIX + relative)
                history_prefix = f"{workspace.manifest.history_dir}/{HISTORY_DATABASE_FILENAME}"
                if relative in {f"{history_prefix}-wal", f"{history_prefix}-shm"}:
                    # The online backup below already contains a consistent
                    # view of SQLite.  WAL/SHM sidecars are connection state,
                    # not portable Workspace data, and restoring stale files
                    # could make a valid snapshot appear inconsistent.
                    continue
                if relative == f"{workspace.manifest.history_dir}/{HISTORY_DATABASE_FILENAME}":
                    payload = self._sqlite_snapshot(path)
                else:
                    payload = path.read_bytes()
            except WorkspaceArchiveError:
                raise
            except OSError as exc:
                raise WorkspaceArchiveStorageError(
                    f"unable to read Workspace file: {path.name}"
                ) from exc
            members[relative] = payload
        if MANIFEST_FILENAME not in members:
            raise WorkspaceArchiveStorageError("Workspace manifest is missing")
        return members

    def backup(self) -> bytes:
        """Return a standard ZIP containing the complete active Workspace."""

        summary = self._current_summary(active=False)
        created_at = _utc_now()
        members = self._workspace_files()
        metadata = {
            "formatVersion": BACKUP_FORMAT_VERSION,
            "createdAt": created_at,
            "workspace": summary.model_dump(mode="json", by_alias=True),
        }
        output = io.BytesIO()
        try:
            with zipfile.ZipFile(
                output,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                archive.writestr(
                    BACKUP_METADATA_FILENAME,
                    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                )
                for relative in sorted(members):
                    archive.writestr(BACKUP_WORKSPACE_PREFIX + relative, members[relative])
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            raise WorkspaceArchiveStorageError("unable to create Workspace backup") from exc
        payload = output.getvalue()
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise WorkspaceArchiveStorageError("Workspace backup is larger than supported")
        return payload

    create_backup = backup

    @staticmethod
    def _read_archive(archive_bytes: bytes) -> _ArchiveSnapshot:
        if not isinstance(archive_bytes, (bytes, bytearray)) or not archive_bytes:
            raise WorkspaceArchiveValidationError("Workspace backup must be a non-empty ZIP")
        if len(archive_bytes) > MAX_ARCHIVE_BYTES:
            raise WorkspaceArchiveValidationError("Workspace backup is larger than supported")

        try:
            archive = zipfile.ZipFile(io.BytesIO(bytes(archive_bytes)), mode="r")
        except (OSError, zipfile.BadZipFile) as exc:
            raise WorkspaceArchiveValidationError("Workspace backup is not a valid ZIP") from exc

        with archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ARCHIVE_MEMBERS:
                raise WorkspaceArchiveValidationError("Workspace backup has an invalid member count")
            seen: set[str] = set()
            metadata_raw: bytes | None = None
            members: dict[str, bytes] = {}
            total_size = 0
            for info in infos:
                normalized = _member_name(info.filename)
                if normalized in seen:
                    raise WorkspaceArchiveValidationError("Workspace backup has duplicate members")
                seen.add(normalized)
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise WorkspaceArchiveValidationError("Workspace backup cannot contain symbolic links")
                if info.file_size < 0:
                    raise WorkspaceArchiveValidationError("Workspace backup has an invalid member size")
                total_size += info.file_size
                if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise WorkspaceArchiveValidationError("Workspace backup is too large when expanded")
                if info.is_dir():
                    continue
                try:
                    content = archive.read(info)
                except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
                    raise WorkspaceArchiveValidationError("Workspace backup contains unreadable data") from exc
                if normalized == BACKUP_METADATA_FILENAME:
                    metadata_raw = content
                elif normalized.startswith(BACKUP_WORKSPACE_PREFIX):
                    relative = normalized[len(BACKUP_WORKSPACE_PREFIX) :]
                    if not relative:
                        raise WorkspaceArchiveValidationError("Workspace directory entry is invalid")
                    members[relative] = content
                else:
                    raise WorkspaceArchiveValidationError(
                        "Workspace backup may contain only metadata.json and workspace/"
                    )

        if metadata_raw is None:
            raise WorkspaceArchiveValidationError("Workspace backup metadata is missing")
        metadata = _json_object(metadata_raw, "backup metadata")
        if metadata.get("formatVersion") != BACKUP_FORMAT_VERSION:
            raise WorkspaceArchiveValidationError("Workspace backup format is unsupported")
        created_at = metadata.get("createdAt")
        if not isinstance(created_at, str) or not created_at.strip():
            raise WorkspaceArchiveValidationError("backup metadata createdAt is invalid")
        try:
            summary = WorkspaceSummary.model_validate(metadata.get("workspace"))
        except (TypeError, ValueError) as exc:
            raise WorkspaceArchiveValidationError("backup metadata workspace is invalid") from exc

        manifest_raw = members.get(MANIFEST_FILENAME)
        if manifest_raw is None:
            raise WorkspaceArchiveValidationError("Workspace manifest is missing")
        manifest_payload = _json_object(manifest_raw, "Workspace manifest")
        try:
            manifest = WorkspaceManifest.model_validate(manifest_payload)
        except ValueError as exc:
            raise WorkspaceArchiveValidationError("Workspace manifest is invalid") from exc
        if manifest.id != summary.id or manifest.name != summary.name:
            raise WorkspaceArchiveValidationError("backup metadata does not match Workspace manifest")

        required_members = {
            f"{manifest.documents_dir}/actors.json",
            f"{manifest.documents_dir}/knowledge_documents.json",
            f"{manifest.documents_dir}/customers.json",
            f"{manifest.contract_dir}/security_contract.json",
            f"{manifest.cases_dir}/attack_cases.json",
            f"{manifest.cases_dir}/target_profiles.json",
            f"{manifest.cases_dir}/ground_truth_cases.json",
        }
        missing = sorted(required_members - members.keys())
        if missing:
            raise WorkspaceArchiveValidationError(
                "Workspace backup is missing required files: " + ", ".join(missing)
            )
        contract_payload = _json_object(
            members[f"{manifest.contract_dir}/security_contract.json"],
            "security_contract.json",
        )
        try:
            contract = SecurityContract.model_validate(contract_payload)
        except ValueError as exc:
            raise WorkspaceArchiveValidationError("security_contract.json is invalid") from exc
        if contract.id != summary.contract_id or contract.version != summary.contract_version:
            raise WorkspaceArchiveValidationError("backup metadata does not match Security Contract")
        try:
            documents = json.loads(
                members[f"{manifest.documents_dir}/knowledge_documents.json"].decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceArchiveValidationError("knowledge_documents.json is invalid") from exc
        if not isinstance(documents, list) or len(documents) != summary.document_count:
            raise WorkspaceArchiveValidationError("backup metadata documentCount is invalid")
        history_member = f"{manifest.history_dir}/{HISTORY_DATABASE_FILENAME}"
        if summary.history_included != (history_member in members):
            raise WorkspaceArchiveValidationError("backup metadata historyIncluded is invalid")
        return _ArchiveSnapshot(
            summary=summary,
            created_at=created_at,
            manifest=manifest,
            members=members,
        )

    def preview(self, archive_bytes: bytes) -> WorkspaceBackupPreview:
        """Inspect a ZIP without creating files, changing state, or using a Provider."""

        self._require_workspace()
        snapshot = self._read_archive(archive_bytes)
        preview_summary = snapshot.summary.model_copy(update={"active": False})
        return WorkspaceBackupPreview(
            format_version=BACKUP_FORMAT_VERSION,
            workspace=preview_summary,
            archive_size_bytes=len(archive_bytes),
            created_at=snapshot.created_at,
        )

    inspect = preview

    def restore(self, archive_bytes: bytes) -> WorkspaceRestoreResult:
        """Restore a validated archive into a new application Workspace directory."""

        self._require_workspace()
        snapshot = self._read_archive(archive_bytes)
        parent = self.workspaces_root
        temporary_root: Path | None = None
        final_root: Path | None = None
        try:
            parent.mkdir(parents=True, exist_ok=True)
            temporary_root = Path(tempfile.mkdtemp(prefix=".workspace-restore-", dir=str(parent)))
            for directory_member in (
                snapshot.manifest.documents_dir,
                snapshot.manifest.contract_dir,
                snapshot.manifest.cases_dir,
                snapshot.manifest.history_dir,
                snapshot.manifest.exports_dir,
            ):
                (temporary_root / PurePosixPath(directory_member)).mkdir(
                    parents=True, exist_ok=True
                )
            for relative, content in snapshot.members.items():
                destination = (temporary_root / PurePosixPath(relative)).resolve()
                try:
                    destination.relative_to(temporary_root.resolve())
                except ValueError as exc:
                    raise WorkspaceArchiveValidationError(
                        "Workspace backup member escapes the temporary Workspace"
                    ) from exc
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            WorkspaceService(app_paths=self.app_paths).open(temporary_root)
            final_name = f"restored-{uuid.uuid4().hex[:12]}"
            final_root = parent / final_name
            temporary_root.replace(final_root)
            temporary_root = None
        except WorkspaceArchiveError:
            raise
        except (OSError, WorkspaceError) as exc:
            raise WorkspaceArchiveStorageError("unable to restore Workspace") from exc
        finally:
            if temporary_root is not None:
                shutil.rmtree(temporary_root, ignore_errors=True)
        assert final_root is not None
        restored_summary = snapshot.summary.model_copy(
            update={"relative_directory": final_root.name, "active": False}
        )
        return WorkspaceRestoreResult(workspace=restored_summary)

    restore_backup = restore


__all__ = [
    "BACKUP_FORMAT_VERSION",
    "BACKUP_METADATA_FILENAME",
    "BACKUP_WORKSPACE_PREFIX",
    "MAX_ARCHIVE_BYTES",
    "WorkspaceArchiveError",
    "WorkspaceArchiveService",
    "WorkspaceArchiveStorageError",
    "WorkspaceArchiveValidationError",
    "WorkspaceArchiveWorkspaceError",
    "WorkspaceBackupPreview",
    "WorkspaceRestoreResult",
    "WorkspaceSummary",
]
