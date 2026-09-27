#!/usr/bin/env python3
"""Verify explicit portable Workspace archives without reading user state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "api" / "src"))

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.workspace import WorkspaceService
from agent_audit_api.workspace_archive import WorkspaceArchiveService
from agent_audit_api.workspace import WORKSPACE_SCHEMA_VERSION
from agent_audit_api.sqlite_schema import SQLITE_SCHEMA_VERSION


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sqlite_facts(payload: bytes) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="agent-audit-archive-sqlite-") as raw:
        path = Path(raw) / "history.sqlite3"
        path.write_bytes(payload)
        connection = sqlite3.connect(path)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            counts = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in ("audit_runs", "audit_replays", "acceptance_runs")
            }
            marker = connection.execute(
                "SELECT scan_id FROM audit_runs ORDER BY scan_id LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
    return {
        "userVersion": version,
        "integrityCheck": integrity,
        "rowCounts": counts,
        "markerValue": marker[0] if marker else None,
    }


def archive_sqlite(snapshot) -> bytes:
    matches = [
        value
        for name, value in snapshot.members.items()
        if name.endswith("/agent_audit.sqlite3")
    ]
    if len(matches) != 1:
        raise ValueError("archive must contain one history database")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--archive", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--roundtrip-output-dir", type=Path, required=True)
    args = parser.parse_args()
    archives = [path.resolve(strict=True) for path in args.archive]
    if any(not path.is_file() or path.is_symlink() for path in archives):
        raise SystemExit("archives must be regular files")
    roundtrip_output = args.roundtrip_output_dir.resolve()
    if roundtrip_output.exists() and any(roundtrip_output.iterdir()):
        raise SystemExit("roundtrip output directory must be empty")
    roundtrip_output.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="agent-audit-archive-roundtrip-") as raw:
        paths = resolve_app_paths(Path(raw) / "app")
        seed = REPOSITORY_ROOT / "data" / "demo"
        active = WorkspaceService(paths).create(
            paths.default_workspace_dir, "Archive Roundtrip Active", seed_dir=seed
        )
        for archive_path in archives:
            payload = archive_path.read_bytes()
            snapshot = WorkspaceArchiveService._read_archive(payload)
            backup_root = paths.data_dir / "migration-backups"
            backups_before = set(backup_root.glob("*.zip")) if backup_root.is_dir() else set()
            restored = WorkspaceArchiveService(active, paths).restore(payload)
            target = paths.default_workspace_dir.parent / restored.workspace.relative_directory
            workspace = WorkspaceService(paths).open(target)
            service = WorkspaceArchiveService(workspace, paths)
            regenerated = service.backup()
            regenerated_snapshot = WorkspaceArchiveService._read_archive(regenerated)
            output_name = f"{archive_path.stem}.roundtrip.zip"
            output_path = roundtrip_output / output_name
            if output_path.exists():
                raise SystemExit("roundtrip output must not overwrite files")
            output_path.write_bytes(regenerated)
            source_sqlite = sqlite_facts(archive_sqlite(snapshot))
            post_sqlite = sqlite_facts(archive_sqlite(regenerated_snapshot))
            business_equal = {
                key: regenerated_snapshot.members.get(key) == value
                for key, value in snapshot.members.items()
                if not key.endswith("agent_audit.sqlite3")
            }
            with zipfile.ZipFile(output_path, "r") as archive:
                names = archive.namelist()
            wal_shm_excluded = all(
                not name.endswith(("-wal", "-shm")) for name in names
            )
            backups_after = set(backup_root.glob("*.zip")) if backup_root.is_dir() else set()
            migration_backup_count = len(backups_after - backups_before)
            passed = (
                snapshot.manifest.id == regenerated_snapshot.manifest.id
                and all(business_equal.values())
                and source_sqlite["integrityCheck"] == "ok"
                and post_sqlite["integrityCheck"] == "ok"
                and source_sqlite["rowCounts"] == post_sqlite["rowCounts"]
                and source_sqlite["markerValue"] == post_sqlite["markerValue"]
                and wal_shm_excluded
                and regenerated_snapshot.manifest.schema_version
                == WORKSPACE_SCHEMA_VERSION
                and post_sqlite["userVersion"] == SQLITE_SCHEMA_VERSION
            )
            results.append(
                {
                    "direction": "explicit-input-to-regenerated",
                    "input": archive_path.name,
                    "output": output_name,
                    "roundtripArchive": output_name,
                    "inputSha256": digest(payload),
                    "outputSha256": digest(regenerated),
                    "workspaceId": snapshot.manifest.id,
                    "sourceWorkspaceSchemaVersion": snapshot.manifest.schema_version,
                    "postWorkspaceSchemaVersion": regenerated_snapshot.manifest.schema_version,
                    "sourceSqliteUserVersion": source_sqlite["userVersion"],
                    "postSqliteUserVersion": post_sqlite["userVersion"],
                    "integrityCheck": post_sqlite["integrityCheck"],
                    "rowCounts": post_sqlite["rowCounts"],
                    "markerValue": post_sqlite["markerValue"],
                    "businessMembersEqual": business_equal,
                    "walShmExcluded": wal_shm_excluded,
                    "migrationBackupCount": migration_backup_count,
                    "passed": passed,
                }
            )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schemaVersion": 1, "results": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
