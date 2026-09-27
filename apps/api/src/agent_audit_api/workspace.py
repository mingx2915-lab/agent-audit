"""Portable, manifest-backed Audit Workspace support."""

from __future__ import annotations

import json
import io
import os
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, ClassVar

from pydantic import Field, field_validator

from .app_paths import AppPaths, resolve_app_paths
from .private_storage import ensure_private_directory, prepare_private_sqlite
from .schemas import CamelModel
from .sqlite_schema import (
    SQLITE_SCHEMA_VERSION,
    SQLiteSchemaError,
    SQLiteSchemaManager,
)


MANIFEST_FILENAME = "agent-audit-workspace.json"
HISTORY_DATABASE_FILENAME = "agent_audit.sqlite3"
WORKSPACE_SCHEMA_VERSION = 2


class WorkspaceError(ValueError):
    """Raised when a Workspace cannot be created, opened, or resolved."""


def _validate_relative_directory(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("workspace directory must be a non-empty relative path")
    if "\\" in value:
        raise ValueError("workspace directory must use portable forward slashes")
    path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (
        path.is_absolute()
        or path.anchor
        or windows_path.is_absolute()
        or windows_path.anchor
    ):
        raise ValueError("workspace directory must be relative")
    if any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("workspace directory must not contain . or .. segments")
    return value


class WorkspaceManifest(CamelModel):
    """Portable Workspace metadata; directory members are always relative."""

    id: str
    name: str
    version: int = Field(default=1, gt=0)
    schema_version: int = Field(default=WORKSPACE_SCHEMA_VERSION, ge=1)
    documents_dir: str = "documents"
    contract_dir: str = "contract"
    cases_dir: str = "cases"
    history_dir: str = "history"
    exports_dir: str = "exports"

    _validate_directories = field_validator(
        "documents_dir",
        "contract_dir",
        "cases_dir",
        "history_dir",
        "exports_dir",
    )(_validate_relative_directory)

    @field_validator("id", "name")
    @classmethod
    def _validate_text(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("workspace id and name must be non-empty")
        return value


class AuditWorkspace:
    """Runtime view of a validated Workspace rooted at one absolute path."""

    _DATA_FILES: ClassVar[dict[str, tuple[str, str]]] = {
        "actors": ("documents_dir", "actors.json"),
        "documents": ("documents_dir", "knowledge_documents.json"),
        "customers": ("documents_dir", "customers.json"),
        "contract": ("contract_dir", "security_contract.json"),
        "attack_cases": ("cases_dir", "attack_cases.json"),
        "profiles": ("cases_dir", "target_profiles.json"),
        "ground_truth": ("cases_dir", "ground_truth_cases.json"),
    }

    def __init__(self, root: str | Path, manifest: WorkspaceManifest) -> None:
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise WorkspaceError("workspace root must be an existing directory")
        self.manifest = manifest
        self._validate_declared_paths()

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_FILENAME

    def _resolve_declared(self, member: str) -> Path:
        relative = getattr(self.manifest, member)
        candidate = (self.root / relative).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(f"workspace path escapes root: {member}") from exc
        return candidate

    def _validate_declared_paths(self) -> None:
        for member in (
            "documents_dir",
            "contract_dir",
            "cases_dir",
            "history_dir",
            "exports_dir",
        ):
            self._resolve_declared(member)

    @property
    def documents_path(self) -> Path:
        return self._resolve_declared("documents_dir")

    @property
    def contract_path(self) -> Path:
        return self._resolve_declared("contract_dir")

    @property
    def cases_path(self) -> Path:
        return self._resolve_declared("cases_dir")

    @property
    def history_path(self) -> Path:
        return self._resolve_declared("history_dir")

    @property
    def exports_path(self) -> Path:
        return self._resolve_declared("exports_dir")

    @property
    def history_database_path(self) -> Path:
        return self._resolve_file("history_dir", HISTORY_DATABASE_FILENAME)

    @property
    def history_db_path(self) -> Path:
        """Alias used by the API history repository assembly."""

        return self.history_database_path

    def _resolve_file(self, directory_member: str, filename: str) -> Path:
        if Path(filename).name != filename or filename in ("", ".", ".."):
            raise WorkspaceError("workspace file name must be a single relative name")
        directory = self._resolve_declared(directory_member)
        candidate = (directory / filename).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError("workspace file path escapes root") from exc
        return candidate

    def data_path(self, name: str) -> Path:
        """Resolve one declared business data file below this Workspace."""

        entry = self._DATA_FILES.get(name)
        if entry is None:
            raise WorkspaceError(f"unknown workspace data file: {name}")
        return self._resolve_file(*entry)

    @property
    def actors_path(self) -> Path:
        return self.data_path("actors")

    @property
    def documents_file_path(self) -> Path:
        return self.data_path("documents")

    @property
    def customers_path(self) -> Path:
        return self.data_path("customers")

    @property
    def security_contract_path(self) -> Path:
        return self.data_path("contract")

    @property
    def attack_cases_path(self) -> Path:
        return self.data_path("attack_cases")

    @property
    def target_profiles_path(self) -> Path:
        return self.data_path("profiles")

    @property
    def ground_truth_cases_path(self) -> Path:
        return self.data_path("ground_truth")


class WorkspaceService:
    """Create and open portable Workspaces without making security decisions."""

    _SEED_FILES: ClassVar[dict[str, tuple[str, str]]] = {
        "actors.json": ("documents_dir", "actors.json"),
        "knowledge_documents.json": ("documents_dir", "knowledge_documents.json"),
        "customers.json": ("documents_dir", "customers.json"),
        "security_contract.json": ("contract_dir", "security_contract.json"),
        "attack_cases.json": ("cases_dir", "attack_cases.json"),
        "target_profiles.json": ("cases_dir", "target_profiles.json"),
        "ground_truth_cases.json": ("cases_dir", "ground_truth_cases.json"),
    }

    def __init__(self, app_paths: AppPaths | None = None) -> None:
        self.app_paths = app_paths if app_paths is not None else resolve_app_paths()

    @staticmethod
    def _read_manifest(path: Path) -> WorkspaceManifest:
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkspaceError("unable to read agent-audit-workspace.json") from exc
        if not isinstance(payload, dict):
            raise WorkspaceError("agent-audit-workspace.json must contain an object")
        schema_version = payload.get("schemaVersion", 1)
        if type(schema_version) is not int or schema_version < 1:
            raise WorkspaceError("workspace schemaVersion is invalid")
        if schema_version > WORKSPACE_SCHEMA_VERSION:
            raise WorkspaceError("workspace schema is newer than this application")
        payload["schemaVersion"] = schema_version
        try:
            return WorkspaceManifest.model_validate(payload)
        except ValueError as exc:
            raise WorkspaceError("agent-audit-workspace.json is invalid") from exc

    @staticmethod
    def _write_manifest(path: Path, manifest: WorkspaceManifest) -> None:
        try:
            path.write_text(
                json.dumps(
                    manifest.model_dump(mode="json", by_alias=True),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise WorkspaceError("unable to write agent-audit-workspace.json") from exc

    def create(
        self,
        root: str | Path,
        name: str,
        seed_dir: str | Path | None = None,
    ) -> AuditWorkspace:
        """Create one Workspace and copy the fixed seed assets into it."""

        workspace_root = Path(root).expanduser().resolve()
        seed_root = Path(seed_dir).expanduser().resolve() if seed_dir is not None else None
        if seed_root is None or not seed_root.is_dir():
            raise WorkspaceError("seed directory must be an existing directory")
        missing_seed_files = [
            source_name
            for source_name in self._SEED_FILES
            if not (seed_root / source_name).is_file()
        ]
        if missing_seed_files:
            raise WorkspaceError(
                "seed file is missing: " + ", ".join(sorted(missing_seed_files))
            )
        if workspace_root.exists():
            if not workspace_root.is_dir():
                raise WorkspaceError("workspace root is not a directory")
            if any(workspace_root.iterdir()):
                raise WorkspaceError("workspace root must not already contain files")
        else:
            try:
                workspace_root.mkdir(parents=True)
            except OSError as exc:
                raise WorkspaceError("unable to create workspace root") from exc

        manifest = WorkspaceManifest(id=uuid.uuid4().hex, name=name)
        workspace = AuditWorkspace(workspace_root, manifest)

        try:
            for directory in (
                workspace.documents_path,
                workspace.contract_path,
                workspace.cases_path,
                workspace.history_path,
                workspace.exports_path,
            ):
                directory.mkdir(parents=True, exist_ok=True)
            ensure_private_directory(workspace.history_path)
            for source_name, (directory_member, destination_name) in self._SEED_FILES.items():
                source = seed_root / source_name
                destination = workspace._resolve_file(directory_member, destination_name)
                shutil.copy2(source, destination)
            self._write_manifest(workspace.manifest_path, manifest)
        except WorkspaceError:
            raise
        except OSError as exc:
            raise WorkspaceError("unable to initialize workspace files") from exc
        return workspace

    def open(self, root: str | Path) -> AuditWorkspace:
        """Open, validate, and migrate an existing Workspace when required."""

        workspace_root = Path(root).expanduser().resolve()
        if not workspace_root.exists() or not workspace_root.is_dir():
            raise WorkspaceError("workspace root must be an existing directory")
        manifest_path = workspace_root / MANIFEST_FILENAME
        manifest = self._read_manifest(manifest_path)
        workspace = self._validate_workspace_structure(workspace_root, manifest)
        database_path = workspace_root / manifest.history_dir / HISTORY_DATABASE_FILENAME
        try:
            ensure_private_directory(workspace.history_path)
            if database_path.exists():
                prepare_private_sqlite(database_path)
        except OSError as exc:
            raise WorkspaceError("unable to secure workspace history permissions") from exc
        database_version = self._database_version(database_path)
        if (
            manifest.schema_version < WORKSPACE_SCHEMA_VERSION
            or database_version < SQLITE_SCHEMA_VERSION
        ):
            self._migrate(workspace_root, manifest, database_path)
            manifest = self._read_manifest(manifest_path)
        return self._validate_workspace_structure(workspace_root, manifest)

    @staticmethod
    def _validate_workspace_structure(
        workspace_root: Path, manifest: WorkspaceManifest
    ) -> AuditWorkspace:
        workspace = AuditWorkspace(workspace_root, manifest)
        required_directories = (
            workspace.documents_path,
            workspace.contract_path,
            workspace.cases_path,
            workspace.history_path,
            workspace.exports_path,
        )
        missing_directories = [
            path.name for path in required_directories if not path.is_dir()
        ]
        if missing_directories:
            raise WorkspaceError(
                "workspace is missing required directories: "
                + ", ".join(sorted(missing_directories))
            )
        required_paths = (
            workspace.actors_path,
            workspace.documents_file_path,
            workspace.customers_path,
            workspace.security_contract_path,
            workspace.attack_cases_path,
            workspace.target_profiles_path,
            workspace.ground_truth_cases_path,
        )
        missing = [path.name for path in required_paths if not path.is_file()]
        if missing:
            raise WorkspaceError(
                "workspace is missing required files: " + ", ".join(sorted(missing))
            )
        return workspace

    @staticmethod
    def _database_version(path: Path) -> int:
        if not path.is_file():
            return SQLITE_SCHEMA_VERSION
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(str(path))
            version = SQLiteSchemaManager.inspect(connection)
        except SQLiteSchemaError as exc:
            message = str(exc)
            if "newer" in message:
                raise WorkspaceError(
                    "workspace history database is invalid: schema is newer than "
                    "this application"
                ) from exc
            raise WorkspaceError("workspace history database is invalid") from exc
        except sqlite3.Error as exc:
            raise WorkspaceError("workspace history database is invalid") from exc
        finally:
            if connection is not None:
                connection.close()
        if version > SQLITE_SCHEMA_VERSION:
            raise WorkspaceError("workspace history schema is newer than this application")
        return version

    def _migration_backup_path(
        self,
        manifest: WorkspaceManifest,
        workspace_source: int,
        sqlite_source: int,
        target: int,
    ) -> Path:
        safe_id = "".join(character for character in manifest.id if character.isalnum())
        if not safe_id:
            raise WorkspaceError("workspace id cannot name a migration backup")
        return self.app_paths.data_dir / "migration-backups" / (
            f"{safe_id}-workspace-v{workspace_source}-sqlite-v{sqlite_source}"
            f"-to-v{target}.zip"
        )

    @staticmethod
    def _sqlite_backup_bytes(path: Path) -> bytes:
        with tempfile.TemporaryDirectory(prefix="agent-audit-migration-") as raw:
            target = Path(raw) / HISTORY_DATABASE_FILENAME
            source = sqlite3.connect(str(path))
            destination = sqlite3.connect(str(target))
            try:
                source.backup(destination)
                destination.commit()
            finally:
                destination.close()
                source.close()
            return target.read_bytes()

    @staticmethod
    def _restore_sqlite_snapshot(path: Path, payload: bytes) -> None:
        """Restore one online-backup image through SQLite's backup API."""

        with tempfile.TemporaryDirectory(prefix="agent-audit-restore-") as raw:
            source_path = Path(raw) / HISTORY_DATABASE_FILENAME
            source_path.write_bytes(payload)
            source: sqlite3.Connection | None = None
            destination: sqlite3.Connection | None = None
            try:
                source = sqlite3.connect(str(source_path))
                prepare_private_sqlite(path)
                destination = sqlite3.connect(str(path))
                source.backup(destination)
                destination.commit()
            finally:
                if destination is not None:
                    destination.close()
                if source is not None:
                    source.close()

    def _backup_workspace(self, root: Path, history_relative: str) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*"), key=lambda value: value.as_posix()):
                if path.is_symlink():
                    raise WorkspaceError("workspace migration cannot back up symbolic links")
                if not path.is_file():
                    continue
                relative = path.relative_to(root).as_posix()
                if relative in {history_relative + "-wal", history_relative + "-shm"}:
                    continue
                content = (
                    self._sqlite_backup_bytes(path)
                    if relative == history_relative
                    else path.read_bytes()
                )
                archive.writestr(relative, content)
        return output.getvalue()

    @staticmethod
    def _restore_backup(
        root: Path,
        payload: bytes,
        *,
        manifest_relative: str,
        history_relative: str,
        database_existed_before: bool,
    ) -> None:
        """Restore the only files migration can modify from the online backup."""

        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            names = set(archive.namelist())
            required = {manifest_relative}
            if database_existed_before:
                required.add(history_relative)
            if not required <= names:
                raise WorkspaceError("workspace migration backup is incomplete")
            restore_members = (
                (history_relative, manifest_relative)
                if database_existed_before
                else (manifest_relative,)
            )
            for relative in restore_members:
                destination = (root / PurePosixPath(relative)).resolve()
                try:
                    destination.relative_to(root.resolve())
                except ValueError as exc:
                    raise WorkspaceError(
                        "workspace migration backup path escapes root"
                    ) from exc
                destination.parent.mkdir(parents=True, exist_ok=True)
                if relative == history_relative:
                    WorkspaceService._restore_sqlite_snapshot(
                        destination, archive.read(relative)
                    )
                    continue
                temporary = destination.with_name(destination.name + ".restore.tmp")
                temporary.write_bytes(archive.read(relative))
                try:
                    temporary.replace(destination)
                except OSError:
                    if relative != manifest_relative:
                        raise
                    # The original manifest has not changed when its final
                    # replace failed, so no second write is necessary.
                    if destination.read_bytes() != archive.read(relative):
                        raise
                    temporary.unlink()

    def _migrate(
        self, root: Path, manifest: WorkspaceManifest, database_path: Path
    ) -> None:
        source_version = manifest.schema_version
        database_existed_before = database_path.is_file()
        sqlite_source_version = (
            self._database_version(database_path) if database_existed_before else 0
        )
        history_relative = f"{manifest.history_dir}/{HISTORY_DATABASE_FILENAME}"
        backup_payload = self._backup_workspace(root, history_relative)
        backup_path = self._migration_backup_path(
            manifest,
            source_version,
            sqlite_source_version,
            WORKSPACE_SCHEMA_VERSION,
        )
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_backup = backup_path.with_suffix(".zip.tmp")
        try:
            temporary_backup.write_bytes(backup_payload)
            os.replace(temporary_backup, backup_path)
        except OSError as exc:
            if temporary_backup.exists():
                temporary_backup.unlink()
            raise WorkspaceError("unable to preserve workspace migration backup") from exc
        try:
            if database_path.is_file():
                connection = sqlite3.connect(str(database_path))
                try:
                    SQLiteSchemaManager(database_path).ensure(connection)
                finally:
                    connection.close()
            updated = manifest.model_copy(
                update={"schema_version": WORKSPACE_SCHEMA_VERSION}
            )
            manifest_temp = root / (MANIFEST_FILENAME + ".tmp")
            self._write_manifest(manifest_temp, updated)
            os.replace(manifest_temp, root / MANIFEST_FILENAME)
        except Exception as exc:
            manifest_temp = root / (MANIFEST_FILENAME + ".tmp")
            if manifest_temp.exists():
                manifest_temp.unlink()
            try:
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(database_path) + suffix)
                    if sidecar.exists():
                        sidecar.unlink()
                if not database_existed_before and database_path.exists():
                    database_path.unlink()
                self._restore_backup(
                    root,
                    backup_payload,
                    manifest_relative=MANIFEST_FILENAME,
                    history_relative=history_relative,
                    database_existed_before=database_existed_before,
                )
            except (OSError, WorkspaceError, zipfile.BadZipFile) as restore_exc:
                raise WorkspaceError(
                    "workspace migration failed and rollback could not complete; "
                    "backup was preserved"
                ) from restore_exc
            raise WorkspaceError("workspace migration failed; backup was preserved") from exc

    def list(self, root: str | Path | None = None) -> tuple[AuditWorkspace, ...]:
        """List valid child Workspaces in deterministic name order."""

        parent = Path(root).expanduser() if root is not None else self.app_paths.home_dir / "workspaces"
        if not parent.exists():
            return ()
        if not parent.is_dir():
            raise WorkspaceError("workspace list root is not a directory")
        workspaces: list[AuditWorkspace] = []
        for child in sorted(parent.iterdir(), key=lambda path: path.name.casefold()):
            if not child.is_dir() or not (child / MANIFEST_FILENAME).is_file():
                continue
            workspaces.append(self.open(child))
        return tuple(workspaces)

    def ensure_default(
        self,
        seed_dir: str | Path,
        *,
        root: str | Path | None = None,
        name: str = "Default Workspace",
    ) -> AuditWorkspace:
        """Open an existing default Workspace or seed it exactly once.

        ``root`` is an internal Desktop hook for the explicit ``--workspace``
        path.  An existing manifest is always opened without consulting or
        copying the seed; an empty/nonexistent root is initialized once.
        """

        workspace_root = (
            Path(root).expanduser().resolve()
            if root is not None
            else self.app_paths.default_workspace_dir
        )
        if workspace_root.exists():
            if not workspace_root.is_dir():
                raise WorkspaceError("workspace root is not a directory")
            if (workspace_root / MANIFEST_FILENAME).is_file():
                return self.open(workspace_root)
            if any(workspace_root.iterdir()):
                raise WorkspaceError(
                    "workspace root contains files but no valid manifest"
                )
        return self.create(workspace_root, name, seed_dir=seed_dir)


__all__ = [
    "AuditWorkspace",
    "HISTORY_DATABASE_FILENAME",
    "MANIFEST_FILENAME",
    "WORKSPACE_SCHEMA_VERSION",
    "WorkspaceError",
    "WorkspaceManifest",
    "WorkspaceService",
]
