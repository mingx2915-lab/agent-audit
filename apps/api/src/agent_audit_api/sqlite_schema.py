"""Shared, versioned SQLite schema for Audit and Acceptance history."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .private_storage import prepare_private_sqlite


SQLITE_SCHEMA_VERSION = 2


class SQLiteSchemaError(RuntimeError):
    """Raised when a local history database cannot be migrated safely."""


class SQLiteSchemaManager:
    _VERSION_TABLES = {
        0: set(),
        1: {"audit_runs", "audit_replays"},
        2: {"audit_runs", "audit_replays", "acceptance_runs"},
    }
    _TABLE_COLUMNS = {
        "audit_runs": {
            "scan_id",
            "plan_id",
            "contract_id",
            "contract_version",
            "target_profile_id",
            "status",
            "stop_reason",
            "attempt_count",
            "finding_count",
            "started_at",
            "completed_at",
            "duration_ms",
            "scan_json",
            "plan_json",
            "contract_json",
            "target_profile_json",
            "runtime_json",
        },
        "audit_replays": {"scan_id", "replay_id", "created_at", "replay_json"},
        "acceptance_runs": {
            "run_id",
            "started_at",
            "completed_at",
            "status",
            "verdict",
            "contract_id",
            "contract_version",
            "readiness_status",
            "gate_status",
            "benchmark_case_count",
            "benchmark_matched_case_count",
            "finding_count",
            "guided_replay_status",
            "run_json",
        },
    }

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            prepare_private_sqlite(self.path)
            connection = sqlite3.connect(str(self.path))
            connection.row_factory = sqlite3.Row
            self.ensure(connection)
            return connection
        except (OSError, sqlite3.Error, SQLiteSchemaError) as exc:
            if connection is not None:
                connection.close()
            if isinstance(exc, SQLiteSchemaError):
                raise
            raise SQLiteSchemaError("unable to initialize history schema") from exc

    @staticmethod
    def version(connection: sqlite3.Connection) -> int:
        value = connection.execute("PRAGMA user_version").fetchone()[0]
        if type(value) is not int or value < 0:
            raise SQLiteSchemaError("history schema version is invalid")
        return value

    @classmethod
    def inspect(cls, connection: sqlite3.Connection) -> int:
        """Return and validate the declared schema version without writes."""

        version = cls.version(connection)
        if version > SQLITE_SCHEMA_VERSION:
            raise SQLiteSchemaError("history schema is newer than this application")
        cls._validate_known_tables(connection)
        required = cls._VERSION_TABLES[version]
        existing = cls._existing_tables(connection)
        missing = required - existing
        if missing:
            raise SQLiteSchemaError(
                "history schema is missing required tables: "
                + ", ".join(sorted(missing))
            )
        return version

    def ensure(self, connection: sqlite3.Connection) -> None:
        current = self.inspect(connection)
        if current == SQLITE_SCHEMA_VERSION:
            return
        try:
            connection.execute("BEGIN IMMEDIATE")
            while current < SQLITE_SCHEMA_VERSION:
                if current == 0:
                    self._to_v1(connection)
                elif current == 1:
                    self._to_v2(connection)
                else:  # pragma: no cover - guarded by sequential registry
                    raise SQLiteSchemaError("history migration step is unavailable")
                current += 1
                self._validate_known_tables(connection)
                connection.execute(f"PRAGMA user_version = {current}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    @classmethod
    def _validate_known_tables(cls, connection: sqlite3.Connection) -> None:
        existing = cls._existing_tables(connection)
        for table, required_columns in cls._TABLE_COLUMNS.items():
            if table not in existing:
                continue
            actual_columns = {
                row[1]
                for row in connection.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()
            }
            if actual_columns != required_columns:
                raise SQLiteSchemaError(
                    f"history table {table} has an incompatible schema"
                )

    @staticmethod
    def _existing_tables(connection: sqlite3.Connection) -> set[str]:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    @staticmethod
    def _to_v1(connection: sqlite3.Connection) -> None:
        for statement in (
            """CREATE TABLE IF NOT EXISTS audit_runs (
                scan_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                contract_version INTEGER NOT NULL,
                target_profile_id TEXT NOT NULL,
                status TEXT NOT NULL,
                stop_reason TEXT NOT NULL,
                attempt_count INTEGER NOT NULL,
                finding_count INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                scan_json TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                contract_json TEXT NOT NULL,
                target_profile_json TEXT NOT NULL,
                runtime_json TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS audit_replays (
                scan_id TEXT NOT NULL,
                replay_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                replay_json TEXT NOT NULL,
                PRIMARY KEY (scan_id, replay_id),
                FOREIGN KEY (scan_id) REFERENCES audit_runs(scan_id)
            )""",
            """CREATE INDEX IF NOT EXISTS idx_audit_runs_completed_at
                ON audit_runs(completed_at DESC, scan_id DESC)""",
            """CREATE INDEX IF NOT EXISTS idx_audit_replays_scan_created
                ON audit_replays(scan_id, created_at ASC, replay_id ASC)""",
        ):
            connection.execute(statement)

    @staticmethod
    def _to_v2(connection: sqlite3.Connection) -> None:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS acceptance_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                verdict TEXT NOT NULL,
                contract_id TEXT NOT NULL,
                contract_version INTEGER NOT NULL,
                readiness_status TEXT NOT NULL,
                gate_status TEXT NOT NULL,
                benchmark_case_count INTEGER NOT NULL,
                benchmark_matched_case_count INTEGER NOT NULL,
                finding_count INTEGER NOT NULL,
                guided_replay_status TEXT NOT NULL,
                run_json TEXT NOT NULL
            )"""
        )
        connection.execute(
            """CREATE INDEX IF NOT EXISTS idx_acceptance_runs_completed_at
                ON acceptance_runs(completed_at DESC, run_id DESC)"""
        )


__all__ = ["SQLITE_SCHEMA_VERSION", "SQLiteSchemaError", "SQLiteSchemaManager"]
