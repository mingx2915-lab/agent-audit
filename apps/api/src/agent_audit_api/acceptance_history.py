"""SQLite append-only storage for complete F-025 Acceptance Runs.

The table is deliberately separate from F-019 ``audit_runs``/``audit_replays``.
Both repositories may point at the same SQLite file, but neither operation
rewrites rows owned by the other history format.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol

from .acceptance import (
    AcceptanceRun,
    AcceptanceRunSummary,
    build_acceptance_summary,
)
from .sqlite_schema import SQLiteSchemaError, SQLiteSchemaManager


class AcceptanceRunRepository(Protocol):
    """Persistence boundary for immutable Acceptance Runs."""

    def save(self, run: AcceptanceRun) -> None:
        """Append one completed Run; never replace an existing ID."""

    def list(self, limit: int = 20) -> list[AcceptanceRunSummary]:
        """Return summaries in completion-time descending order."""

    def get(self, run_id: str) -> AcceptanceRun | None:
        """Return a complete Run, or ``None`` when its ID is unknown."""

    def previous(self, run_id: str) -> AcceptanceRun | None:
        """Return the immediately preceding historical Run, if any."""


class AcceptanceRunRepositoryError(RuntimeError):
    """Raised when the local Acceptance history store cannot complete an operation."""


def _json_payload(run: AcceptanceRun) -> str:
    try:
        return json.dumps(
            run.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise AcceptanceRunRepositoryError("acceptance run contains invalid JSON") from exc


def _parse_run(payload: str) -> AcceptanceRun:
    try:
        value = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AcceptanceRunRepositoryError("acceptance history contains invalid JSON") from exc
    try:
        return AcceptanceRun.model_validate(value)
    except ValueError as exc:
        raise AcceptanceRunRepositoryError(
            "acceptance history contains an invalid snapshot"
        ) from exc


class SQLiteAcceptanceRunRepository:
    """Store complete Acceptance Run snapshots in one local SQLite table."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        """Return the configured database path without opening it."""

        return self._path

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = SQLiteSchemaManager(self._path).connect()
            return connection
        except (OSError, sqlite3.Error, SQLiteSchemaError) as exc:
            if connection is not None:
                connection.close()
            raise AcceptanceRunRepositoryError(
                "unable to initialize acceptance history store"
            ) from exc

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string")

    def save(self, run: AcceptanceRun) -> None:
        if not isinstance(run, AcceptanceRun):
            raise TypeError("run must be an AcceptanceRun")
        if run.status != "completed":
            raise ValueError("only completed acceptance runs can be persisted")
        if run.verdict != run.ci_gate.status:
            raise ValueError("acceptance verdict must match ciGate status")
        summary = build_acceptance_summary(run)
        payload = _json_payload(run)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            with connection:
                connection.execute(
                    """
                    INSERT INTO acceptance_runs (
                        run_id, started_at, completed_at, status, verdict,
                        contract_id, contract_version, readiness_status, gate_status,
                        benchmark_case_count, benchmark_matched_case_count,
                        finding_count, guided_replay_status, run_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.id,
                        run.started_at,
                        run.completed_at,
                        run.status,
                        run.verdict,
                        summary.contract_id,
                        summary.contract_version,
                        summary.readiness_status,
                        summary.gate_status,
                        summary.benchmark_case_count,
                        summary.benchmark_matched_case_count,
                        summary.finding_count,
                        summary.guided_replay_status,
                        payload,
                    ),
                )
        except (AcceptanceRunRepositoryError, TypeError, ValueError):
            raise
        except (OSError, sqlite3.Error) as exc:
            # SQLite's UNIQUE/PRIMARY KEY failure is intentionally surfaced as
            # a repository error: append-only history never overwrites a row.
            raise AcceptanceRunRepositoryError(
                "unable to save acceptance run"
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    def list(self, limit: int = 20) -> list[AcceptanceRunSummary]:
        self._validate_limit(limit)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            rows = connection.execute(
                "SELECT run_json FROM acceptance_runs "
                "ORDER BY completed_at DESC, run_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [build_acceptance_summary(_parse_run(row["run_json"])) for row in rows]
        except (AcceptanceRunRepositoryError, TypeError, ValueError):
            raise
        except (OSError, sqlite3.Error) as exc:
            raise AcceptanceRunRepositoryError(
                "unable to list acceptance history"
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    def get(self, run_id: str) -> AcceptanceRun | None:
        self._validate_run_id(run_id)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            row = connection.execute(
                "SELECT run_json FROM acceptance_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            return _parse_run(row["run_json"])
        except (AcceptanceRunRepositoryError, TypeError, ValueError):
            raise
        except (OSError, sqlite3.Error) as exc:
            raise AcceptanceRunRepositoryError(
                "unable to read acceptance history"
            ) from exc
        finally:
            if connection is not None:
                connection.close()

    def previous(self, run_id: str) -> AcceptanceRun | None:
        """Return the next older row according to completion time and ID."""

        self._validate_run_id(run_id)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            current = connection.execute(
                "SELECT completed_at FROM acceptance_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if current is None:
                return None
            row = connection.execute(
                """
                SELECT run_json
                FROM acceptance_runs
                WHERE completed_at < ?
                   OR (completed_at = ? AND run_id < ?)
                ORDER BY completed_at DESC, run_id DESC
                LIMIT 1
                """,
                (current["completed_at"], current["completed_at"], run_id),
            ).fetchone()
            return None if row is None else _parse_run(row["run_json"])
        except (AcceptanceRunRepositoryError, TypeError, ValueError):
            raise
        except (OSError, sqlite3.Error) as exc:
            raise AcceptanceRunRepositoryError(
                "unable to read previous acceptance run"
            ) from exc
        finally:
            if connection is not None:
                connection.close()

__all__ = [
    "AcceptanceRunRepository",
    "AcceptanceRunRepositoryError",
    "SQLiteAcceptanceRunRepository",
]
