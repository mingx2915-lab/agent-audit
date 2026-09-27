"""SQLite-backed Red-Team scan history for the local demo application."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Literal, Protocol

from .planning import AttackPlan
from .red_team import RedTeamScan
from .replay import ReplayResult
from .retrieval import RetrieverEngineId
from .schemas import CamelModel
from .security_contract import SecurityContract
from .sqlite_schema import SQLiteSchemaError, SQLiteSchemaManager


class TargetProfileSnapshot(CamelModel):
    id: str
    name: str
    enforce_resource_authorization: bool
    enforce_tool_authorization: bool
    enforce_sink_authorization: bool


class AuditRuntimeSnapshot(CamelModel):
    provider: str
    model: str | None
    retriever_engine: RetrieverEngineId
    retriever_model: str | None
    retriever_dimensions: int | None
    indexed_document_count: int


class PersistedReplay(CamelModel):
    id: str
    created_at: str
    replay: ReplayResult


class EmptyReplayRequest(CamelModel):
    """Strict empty body required by the history Replay endpoint."""


class AuditRunSummary(CamelModel):
    scan_id: str
    plan_id: str
    contract_id: str
    contract_version: int
    target_profile_id: str
    status: Literal["completed"]
    stop_reason: Literal[
        "finding_detected",
        "no_new_variant",
        "max_rounds_reached",
    ]
    attempt_count: int
    finding_count: int
    replay_count: int
    started_at: str
    completed_at: str
    duration_ms: float
    runtime_snapshot: AuditRuntimeSnapshot


class AuditRunDetail(CamelModel):
    scan: RedTeamScan
    plan_snapshot: AttackPlan
    contract_snapshot: SecurityContract
    target_profile_snapshot: TargetProfileSnapshot
    runtime_snapshot: AuditRuntimeSnapshot
    replays: list[PersistedReplay]


class AuditRunRepository(Protocol):
    """Persistence boundary for immutable scan details and append-only replays."""

    def save(self, detail: AuditRunDetail) -> None:
        """Persist one completed scan detail without replacing existing rows."""

    def list(self, limit: int = 20) -> list[AuditRunSummary]:
        """Return recent scan summaries in completion-time descending order."""

    def get(self, scan_id: str) -> AuditRunDetail | None:
        """Return one persisted scan detail, or ``None`` when it is unknown."""

    def append_replay(self, scan_id: str, persisted_replay: PersistedReplay) -> None:
        """Append one replay to a known scan without mutating prior rows."""


class AuditRunRepositoryError(RuntimeError):
    """Raised when the local history store cannot complete an operation."""


def _json_payload(value: CamelModel) -> str:
    return json.dumps(
        value.model_dump(by_alias=True),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _json_value(value: str, model_type: type[CamelModel]) -> CamelModel:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AuditRunRepositoryError("history contains invalid JSON") from exc
    try:
        return model_type.model_validate(payload)
    except ValueError as exc:
        raise AuditRunRepositoryError("history contains an invalid snapshot") from exc


class SQLiteAuditRunRepository:
    """Store complete scan snapshots in one local SQLite database.

    The constructor is intentionally side-effect free.  The database file and
    parent directory are created only when a read or write first opens the
    repository.
    """

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
            raise AuditRunRepositoryError("unable to initialize audit history store") from exc

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

    @staticmethod
    def _finding_count(scan: RedTeamScan) -> int:
        return sum(len(attempt.evaluation.findings) for attempt in scan.attempts)

    @staticmethod
    def _summary(
        *,
        scan: RedTeamScan,
        runtime_snapshot: AuditRuntimeSnapshot,
        replay_count: int,
        finding_count: int | None = None,
    ) -> AuditRunSummary:
        return AuditRunSummary(
            scan_id=scan.id,
            plan_id=scan.plan_id,
            contract_id=scan.contract_id,
            contract_version=scan.contract_version,
            target_profile_id=scan.target_profile_id,
            status=scan.status,
            stop_reason=scan.stop_reason,
            attempt_count=len(scan.attempts),
            finding_count=(
                SQLiteAuditRunRepository._finding_count(scan)
                if finding_count is None
                else finding_count
            ),
            replay_count=replay_count,
            started_at=scan.started_at,
            completed_at=scan.completed_at,
            duration_ms=scan.duration_ms,
            runtime_snapshot=runtime_snapshot,
        )

    def save(self, detail: AuditRunDetail) -> None:
        if not isinstance(detail, AuditRunDetail):
            raise TypeError("detail must be an AuditRunDetail")
        if detail.scan.status != "completed":
            raise ValueError("only completed scans can be persisted")
        if detail.scan.plan_id != detail.plan_snapshot.id:
            raise ValueError("scan and plan snapshot ids do not match")
        if detail.scan.contract_id != detail.contract_snapshot.id:
            raise ValueError("scan and contract snapshot ids do not match")
        if detail.scan.contract_version != detail.contract_snapshot.version:
            raise ValueError("scan and contract snapshot versions do not match")
        if detail.scan.target_profile_id != detail.target_profile_snapshot.id:
            raise ValueError("scan and target profile snapshot ids do not match")
        if detail.replays:
            raise ValueError("replays must be appended after the scan is persisted")
        try:
            connection = self._connect()
            with connection:
                connection.execute(
                    """
                    INSERT INTO audit_runs (
                        scan_id, plan_id, contract_id, contract_version,
                        target_profile_id, status, stop_reason, attempt_count,
                        finding_count, started_at, completed_at, duration_ms,
                        scan_json, plan_json, contract_json,
                        target_profile_json, runtime_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        detail.scan.id,
                        detail.scan.plan_id,
                        detail.scan.contract_id,
                        detail.scan.contract_version,
                        detail.scan.target_profile_id,
                        detail.scan.status,
                        detail.scan.stop_reason,
                        len(detail.scan.attempts),
                        self._finding_count(detail.scan),
                        detail.scan.started_at,
                        detail.scan.completed_at,
                        detail.scan.duration_ms,
                        _json_payload(detail.scan),
                        _json_payload(detail.plan_snapshot),
                        _json_payload(detail.contract_snapshot),
                        _json_payload(detail.target_profile_snapshot),
                        _json_payload(detail.runtime_snapshot),
                    ),
                )
        except (AuditRunRepositoryError, TypeError, ValueError):
            raise
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            raise AuditRunRepositoryError("unable to save audit scan") from exc
        finally:
            if "connection" in locals():
                connection.close()

    def list(self, limit: int = 20) -> list[AuditRunSummary]:
        self._validate_limit(limit)
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            rows = connection.execute(
                """
                SELECT
                    audit_runs.scan_id,
                    audit_runs.plan_id,
                    audit_runs.contract_id,
                    audit_runs.contract_version,
                    audit_runs.target_profile_id,
                    audit_runs.status,
                    audit_runs.stop_reason,
                    audit_runs.attempt_count,
                    audit_runs.finding_count,
                    audit_runs.started_at,
                    audit_runs.completed_at,
                    audit_runs.duration_ms,
                    audit_runs.runtime_json,
                    COUNT(audit_replays.replay_id) AS replay_count
                FROM audit_runs
                LEFT JOIN audit_replays
                    ON audit_replays.scan_id = audit_runs.scan_id
                GROUP BY audit_runs.scan_id
                ORDER BY audit_runs.completed_at DESC, audit_runs.scan_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            summaries: list[AuditRunSummary] = []
            for row in rows:
                runtime = _json_value(row["runtime_json"], AuditRuntimeSnapshot)
                assert isinstance(runtime, AuditRuntimeSnapshot)
                summaries.append(
                    AuditRunSummary(
                        scan_id=row["scan_id"],
                        plan_id=row["plan_id"],
                        contract_id=row["contract_id"],
                        contract_version=row["contract_version"],
                        target_profile_id=row["target_profile_id"],
                        status=row["status"],
                        stop_reason=row["stop_reason"],
                        attempt_count=row["attempt_count"],
                        finding_count=row["finding_count"],
                        replay_count=row["replay_count"],
                        started_at=row["started_at"],
                        completed_at=row["completed_at"],
                        duration_ms=row["duration_ms"],
                        runtime_snapshot=runtime,
                    )
                )
            return summaries
        except (AuditRunRepositoryError, TypeError, ValueError):
            raise
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            raise AuditRunRepositoryError("unable to list audit history") from exc
        finally:
            if connection is not None:
                connection.close()

    def get(self, scan_id: str) -> AuditRunDetail | None:
        if not isinstance(scan_id, str) or not scan_id.strip():
            raise ValueError("scan_id must be a non-empty string")
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            row = connection.execute(
                "SELECT scan_json, plan_json, contract_json, target_profile_json, runtime_json "
                "FROM audit_runs WHERE scan_id = ?",
                (scan_id,),
            ).fetchone()
            if row is None:
                return None
            scan = _json_value(row["scan_json"], RedTeamScan)
            plan = _json_value(row["plan_json"], AttackPlan)
            contract = _json_value(row["contract_json"], SecurityContract)
            target_profile = _json_value(
                row["target_profile_json"], TargetProfileSnapshot
            )
            runtime = _json_value(row["runtime_json"], AuditRuntimeSnapshot)
            replay_rows = connection.execute(
                "SELECT replay_id, created_at, replay_json FROM audit_replays "
                "WHERE scan_id = ? ORDER BY created_at ASC, audit_replays.rowid ASC",
                (scan_id,),
            ).fetchall()
            replays: list[PersistedReplay] = []
            for replay_row in replay_rows:
                replay = _json_value(replay_row["replay_json"], ReplayResult)
                assert isinstance(replay, ReplayResult)
                replays.append(
                    PersistedReplay(
                        id=replay_row["replay_id"],
                        created_at=replay_row["created_at"],
                        replay=replay,
                    )
                )
            assert isinstance(scan, RedTeamScan)
            assert isinstance(plan, AttackPlan)
            assert isinstance(contract, SecurityContract)
            assert isinstance(target_profile, TargetProfileSnapshot)
            assert isinstance(runtime, AuditRuntimeSnapshot)
            return AuditRunDetail(
                scan=scan,
                plan_snapshot=plan,
                contract_snapshot=contract,
                target_profile_snapshot=target_profile,
                runtime_snapshot=runtime,
                replays=replays,
            )
        except (AuditRunRepositoryError, TypeError, ValueError):
            raise
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            raise AuditRunRepositoryError("unable to read audit history") from exc
        finally:
            if connection is not None:
                connection.close()

    def append_replay(self, scan_id: str, persisted_replay: PersistedReplay) -> None:
        if not isinstance(scan_id, str) or not scan_id.strip():
            raise ValueError("scan_id must be a non-empty string")
        if not isinstance(persisted_replay, PersistedReplay):
            raise TypeError("persisted_replay must be a PersistedReplay")
        try:
            connection = self._connect()
            with connection:
                exists = connection.execute(
                    "SELECT 1 FROM audit_runs WHERE scan_id = ?",
                    (scan_id,),
                ).fetchone()
                if exists is None:
                    raise KeyError("unknown scan")
                connection.execute(
                    "INSERT INTO audit_replays (scan_id, replay_id, created_at, replay_json) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        scan_id,
                        persisted_replay.id,
                        persisted_replay.created_at,
                        _json_payload(persisted_replay.replay),
                    ),
                )
        except (AuditRunRepositoryError, TypeError, ValueError, KeyError):
            raise
        except (OSError, sqlite3.Error, json.JSONDecodeError) as exc:
            raise AuditRunRepositoryError("unable to append audit replay") from exc
        finally:
            if "connection" in locals():
                connection.close()


__all__ = [
    "AuditRunDetail",
    "AuditRunRepository",
    "AuditRunRepositoryError",
    "AuditRunSummary",
    "AuditRuntimeSnapshot",
    "EmptyReplayRequest",
    "PersistedReplay",
    "SQLiteAuditRunRepository",
    "TargetProfileSnapshot",
]
