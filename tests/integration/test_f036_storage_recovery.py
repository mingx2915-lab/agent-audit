"""F-036 storage and Workspace recovery boundary tests.

The cases below deliberately use a fresh temporary directory for every test.
They hold a real SQLite transaction to exercise the production lock path and
mutate only test-owned snapshots to verify that corruption is reported rather
than repaired or silently replaced.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.acceptance import AcceptanceRunner
from agent_audit_api.acceptance_history import (
    AcceptanceRunRepositoryError,
    SQLiteAcceptanceRunRepository,
)
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.history import (
    AuditRunRepositoryError,
    SQLiteAuditRunRepository,
)
from agent_audit_api.main import create_app
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.workspace import MANIFEST_FILENAME, WorkspaceError, WorkspaceService
from tests.acceptance_support import (
    AcceptanceProvider,
    make_acceptance_embedding_retriever,
)
from tests.benchmark_support import GroundTruthProvider
from tests.retriever_support import make_tfidf_retriever
from tests.unit.test_history_repository import _detail as make_scan_detail
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.attack_cases import load_target_profiles


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


@pytest.mark.parametrize(
    ("manifest_payload", "message"),
    [
        (b"{not-json", "unable to read agent-audit-workspace.json"),
        (b"[]", "agent-audit-workspace.json must contain an object"),
        (b'{"id":"","name":"broken"}', "agent-audit-workspace.json is invalid"),
    ],
)
def test_corrupt_manifest_is_readable_and_never_repaired(
    tmp_path: Path,
    manifest_payload: bytes,
    message: str,
) -> None:
    workspace = WorkspaceService().create(
        tmp_path / "workspace",
        "F-036 manifest recovery",
        seed_dir=DEMO_SEED,
    )
    before_files = {
        path.relative_to(workspace.root): path.read_bytes()
        for path in workspace.root.rglob("*")
        if path.is_file() and path.name != MANIFEST_FILENAME
    }
    workspace.manifest_path.write_bytes(manifest_payload)

    with pytest.raises(WorkspaceError, match=message):
        WorkspaceService().open(workspace.root)

    assert workspace.manifest_path.read_bytes() == manifest_payload
    after_files = {
        path.relative_to(workspace.root): path.read_bytes()
        for path in workspace.root.rglob("*")
        if path.is_file() and path.name != MANIFEST_FILENAME
    }
    assert after_files == before_files


def _storage_app(
    path: Path,
    *,
    history_repository: SQLiteAuditRunRepository,
    acceptance_repository: SQLiteAcceptanceRunRepository,
) -> Any:
    return create_app(
        provider=GroundTruthProvider(),
        retriever=make_tfidf_retriever(),
        history_repository=history_repository,
        acceptance_repository=acceptance_repository,
        history_path=path,
    )


@pytest.mark.parametrize(
    ("kind", "endpoint", "detail"),
    [
        ("scan", "/api/scans", "unable to list audit history"),
        ("acceptance", "/api/acceptance-runs", "unable to list acceptance history"),
    ],
)
def test_sqlite_exclusive_lock_is_a_readable_error_and_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    endpoint: str,
    detail: str,
) -> None:
    path = tmp_path / "history" / "locked.sqlite3"
    history_repository = SQLiteAuditRunRepository(path)
    acceptance_repository = SQLiteAcceptanceRunRepository(path)
    if kind == "scan":
        history_repository.list()
    else:
        acceptance_repository.list()

    # The production repository intentionally uses sqlite3's default timeout.
    # Reduce only this test's connection wait so a held lock is deterministic
    # and does not make the normal suite slow.
    real_connect = sqlite3.connect

    def connect_with_short_test_timeout(database, *args, **kwargs):
        kwargs.setdefault("timeout", 0.05)
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr("agent_audit_api.history.sqlite3.connect", connect_with_short_test_timeout)
    application = _storage_app(
        path,
        history_repository=history_repository,
        acceptance_repository=acceptance_repository,
    )
    holder = real_connect(str(path), timeout=0.05)
    try:
        holder.execute("BEGIN EXCLUSIVE")
        with TestClient(application) as client:
            blocked = client.get(endpoint)
        assert blocked.status_code == 500, blocked.text
        assert blocked.json() == {"detail": detail}
    finally:
        holder.rollback()
        holder.close()

    # Releasing the real lock must make the same repository usable again; no
    # fallback empty store or replacement database is acceptable.
    with TestClient(application) as client:
        recovered = client.get(endpoint)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == []
    assert path.exists()


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows read-only ACL evidence requires a platform-specific fixture",
)
@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root can bypass POSIX read-only permission bits",
)
@pytest.mark.parametrize("kind", ["scan", "acceptance"])
def test_sqlite_read_only_file_remains_readable_and_rejects_save(
    tmp_path: Path,
    kind: str,
) -> None:
    path = tmp_path / f"{kind}.sqlite3"
    if kind == "scan":
        repository: Any = SQLiteAuditRunRepository(path)
        payload = make_scan_detail()
    else:
        repository = SQLiteAcceptanceRunRepository(path)
        payload = _make_acceptance_run()
    repository.list()
    original_mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(original_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    try:
        # The current schema requires no migration, so querying a read-only
        # store is valid. Exercise an actual write to check the error boundary.
        assert repository.list() == []
        with pytest.raises(
            (AuditRunRepositoryError, AcceptanceRunRepositoryError),
            match="unable to save",
        ):
            repository.save(payload)
    finally:
        path.chmod(original_mode)


@pytest.mark.parametrize(
    ("column", "operation", "payload", "message"),
    [
        ("scan_json", "get", "{not-json", "history contains invalid JSON"),
        ("scan_json", "get", "{}", "history contains an invalid snapshot"),
        ("runtime_json", "list", "{not-json", "history contains invalid JSON"),
    ],
)
def test_corrupt_scan_snapshot_keeps_row_and_exposes_diagnostic(
    tmp_path: Path,
    column: str,
    operation: str,
    payload: str,
    message: str,
) -> None:
    path = tmp_path / "scan-corruption.sqlite3"
    repository = SQLiteAuditRunRepository(path)
    detail = make_scan_detail()
    repository.save(detail)
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"UPDATE audit_runs SET {column} = ? WHERE scan_id = ?",
            (payload, detail.scan.id),
        )

    with pytest.raises(AuditRunRepositoryError, match=message):
        if operation == "get":
            repository.get(detail.scan.id)
        else:
            repository.list()

    with sqlite3.connect(path) as connection:
        stored = connection.execute(
            f"SELECT {column} FROM audit_runs WHERE scan_id = ?",
            (detail.scan.id,),
        ).fetchone()
    assert stored == (payload,)

    application = _storage_app(
        path,
        history_repository=repository,
        acceptance_repository=SQLiteAcceptanceRunRepository(path),
    )
    endpoint = (
        f"/api/scans/{detail.scan.id}" if operation == "get" else "/api/scans"
    )
    with TestClient(application) as client:
        response = client.get(endpoint)
    assert response.status_code == 500, response.text
    assert response.json() == {
        "detail": "unable to read audit history"
        if operation == "get"
        else "unable to list audit history"
    }


def _make_acceptance_run():
    data = load_demo_data()
    provider = AcceptanceProvider()
    runner = AcceptanceRunner(
        provider=provider,
        attack_provider=provider,
        retriever=make_acceptance_embedding_retriever(),
        tfidf_retriever=TfidfRetriever(data.documents),
        contract=load_security_contract(),
        profiles=load_target_profiles(),
        demo_data=data,
    )
    return asyncio.run(runner.run())


@pytest.mark.parametrize(
    ("payload", "message", "endpoint_kind"),
    [
        ("{not-json", "acceptance history contains invalid JSON", "get"),
        ("{}", "acceptance history contains an invalid snapshot", "list"),
    ],
)
def test_corrupt_acceptance_snapshot_keeps_row_and_exposes_diagnostic(
    tmp_path: Path,
    payload: str,
    message: str,
    endpoint_kind: str,
) -> None:
    path = tmp_path / "acceptance-corruption.sqlite3"
    repository = SQLiteAcceptanceRunRepository(path)
    run = _make_acceptance_run()
    repository.save(run)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE acceptance_runs SET run_json = ? WHERE run_id = ?",
            (payload, run.id),
        )

    with pytest.raises(AcceptanceRunRepositoryError, match=message):
        if endpoint_kind == "get":
            repository.get(run.id)
        else:
            repository.list()

    with sqlite3.connect(path) as connection:
        stored = connection.execute(
            "SELECT run_json FROM acceptance_runs WHERE run_id = ?",
            (run.id,),
        ).fetchone()
    assert stored == (payload,)

    application = _storage_app(
        path,
        history_repository=SQLiteAuditRunRepository(path),
        acceptance_repository=repository,
    )
    endpoint = (
        f"/api/acceptance-runs/{run.id}"
        if endpoint_kind == "get"
        else "/api/acceptance-runs"
    )
    with TestClient(application) as client:
        response = client.get(endpoint)
    assert response.status_code == 500, response.text
    assert response.json() == {
        "detail": "unable to read acceptance history"
        if endpoint_kind == "get"
        else "unable to list acceptance history"
    }
