"""Opt-in F-036 observation for append-only history growth.

Run explicitly with ``AGENT_AUDIT_RUN_STABILITY=1``.  The default pytest
collection skips this module so a normal developer loop never receives the
100/1000-row workload accidentally.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.acceptance import AcceptanceRunner, AcceptanceRun
from agent_audit_api.acceptance_history import SQLiteAcceptanceRunRepository
from agent_audit_api.attack_cases import load_target_profiles
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.history import AuditRunDetail, SQLiteAuditRunRepository
from agent_audit_api.main import create_app
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from tests.acceptance_support import AcceptanceProvider, make_acceptance_embedding_retriever
from tests.benchmark_support import GroundTruthProvider
from tests.retriever_support import make_tfidf_retriever
from tests.unit.test_history_repository import _detail as make_scan_detail


pytestmark = pytest.mark.skipif(
    os.environ.get("AGENT_AUDIT_RUN_STABILITY") != "1",
    reason="set AGENT_AUDIT_RUN_STABILITY=1 to run F-036 capacity observations",
)


def _make_acceptance_run() -> AcceptanceRun:
    data = load_demo_data()
    provider = AcceptanceProvider()
    return asyncio.run(
        AcceptanceRunner(
            provider=provider,
            attack_provider=provider,
            retriever=make_acceptance_embedding_retriever(),
            tfidf_retriever=TfidfRetriever(data.documents),
            contract=load_security_contract(),
            profiles=load_target_profiles(),
            demo_data=data,
        ).run()
    )


def _timestamp(index: int, *, completed: bool) -> str:
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    value = origin + timedelta(seconds=index * 2 + (1 if completed else 0))
    return value.isoformat().replace("+00:00", "Z")


def _scan_at(base: AuditRunDetail, index: int) -> AuditRunDetail:
    scan_id = f"f036-capacity-scan-{index:04d}"
    attempts = [
        attempt.model_copy(
            deep=True,
            update={
                "id": f"f036-capacity-attempt-{index:04d}-{position:02d}",
                "scan_id": scan_id,
                "variant": attempt.variant.model_copy(
                    deep=True,
                    update={"id": f"f036-capacity-variant-{index:04d}-{position:02d}"},
                ),
            },
        )
        for position, attempt in enumerate(base.scan.attempts)
    ]
    scan = base.scan.model_copy(
        deep=True,
        update={
            "id": scan_id,
            "started_at": _timestamp(index, completed=False),
            "completed_at": _timestamp(index, completed=True),
            "attempts": attempts,
        },
    )
    return base.model_copy(deep=True, update={"scan": scan})


def _acceptance_at(base: AcceptanceRun, index: int) -> AcceptanceRun:
    return base.model_copy(
        deep=True,
        update={
            "id": f"f036-capacity-acceptance-{index:04d}",
            "started_at": _timestamp(index, completed=False),
            "completed_at": _timestamp(index, completed=True),
        },
    )


def _measure_get(client: TestClient, endpoint: str) -> tuple[Any, float]:
    started = time.perf_counter()
    response = client.get(endpoint)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return response, elapsed_ms


def test_history_100_then_1000_rows_records_real_read_observations(tmp_path: Path) -> None:
    """Check bounded reads, ordering, old-row readability, and actual timings."""

    path = tmp_path / "history" / "capacity.sqlite3"
    history_repository = SQLiteAuditRunRepository(path)
    acceptance_repository = SQLiteAcceptanceRunRepository(path)
    base_scan = make_scan_detail(scan_id="f036-capacity-base")
    base_acceptance = _make_acceptance_run()
    scan_rows: list[AuditRunDetail] = []
    acceptance_rows: list[AcceptanceRun] = []

    application = create_app(
        provider=GroundTruthProvider(),
        retriever=make_tfidf_retriever(),
        history_repository=history_repository,
        acceptance_repository=acceptance_repository,
        history_path=path,
    )

    observations: dict[str, dict[str, float]] = {}
    with TestClient(application) as client:
        for index in range(100):
            detail = _scan_at(base_scan, index)
            history_repository.save(detail)
            scan_rows.append(detail)
            run = _acceptance_at(base_acceptance, index)
            acceptance_repository.save(run)
            acceptance_rows.append(run)

        scan_response, scan_100_ms = _measure_get(client, "/api/scans?limit=100")
        acceptance_response, acceptance_100_ms = _measure_get(
            client,
            "/api/acceptance-runs?limit=100",
        )
        assert scan_response.status_code == 200, scan_response.text
        assert acceptance_response.status_code == 200, acceptance_response.text
        assert len(scan_response.json()) == 100
        assert len(acceptance_response.json()) == 100
        assert scan_response.json()[0]["scanId"] == scan_rows[-1].scan.id
        assert acceptance_response.json()[0]["id"] == acceptance_rows[-1].id

        for index in range(100, 1000):
            detail = _scan_at(base_scan, index)
            history_repository.save(detail)
            scan_rows.append(detail)
            run = _acceptance_at(base_acceptance, index)
            acceptance_repository.save(run)
            acceptance_rows.append(run)

        scan_response, scan_1000_ms = _measure_get(client, "/api/scans?limit=100")
        acceptance_response, acceptance_1000_ms = _measure_get(
            client,
            "/api/acceptance-runs?limit=100",
        )
        assert scan_response.status_code == 200, scan_response.text
        assert acceptance_response.status_code == 200, acceptance_response.text
        latest_scans = scan_response.json()
        latest_acceptance = acceptance_response.json()
        assert len(latest_scans) == 100
        assert len(latest_acceptance) == 100
        assert latest_scans[0]["scanId"] == scan_rows[-1].scan.id
        assert latest_scans[-1]["scanId"] == scan_rows[-100].scan.id
        assert latest_acceptance[0]["id"] == acceptance_rows[-1].id
        assert latest_acceptance[-1]["id"] == acceptance_rows[-100].id

        old_scan, old_scan_ms = _measure_get(
            client,
            f"/api/scans/{scan_rows[0].scan.id}",
        )
        old_acceptance, old_acceptance_ms = _measure_get(
            client,
            f"/api/acceptance-runs/{acceptance_rows[0].id}",
        )
        assert old_scan.status_code == 200, old_scan.text
        assert old_acceptance.status_code == 200, old_acceptance.text
        assert old_scan.json()["scan"]["id"] == scan_rows[0].scan.id
        assert old_acceptance.json()["id"] == acceptance_rows[0].id

    with sqlite3.connect(path) as connection:
        scan_count = connection.execute("SELECT COUNT(*) FROM audit_runs").fetchone()[0]
        acceptance_count = connection.execute(
            "SELECT COUNT(*) FROM acceptance_runs"
        ).fetchone()[0]
    assert scan_count == 1000
    assert acceptance_count == 1000

    observations["list100"] = {
        "scanMs": scan_100_ms,
        "acceptanceMs": acceptance_100_ms,
    }
    observations["list1000"] = {
        "scanMs": scan_1000_ms,
        "acceptanceMs": acceptance_1000_ms,
    }
    observations["oldRowGet"] = {
        "scanMs": old_scan_ms,
        "acceptanceMs": old_acceptance_ms,
    }
    # This is an observation artifact, not a performance gate.  The test only
    # asserts correctness above and records the real wall-clock values here.
    print(
        "F-036 history capacity observation "
        + json.dumps(
            {
                "rows": {"scans": scan_count, "acceptance": acceptance_count},
                "observationsMs": observations,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
