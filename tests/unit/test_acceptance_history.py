"""F-025 SQLite Acceptance Run persistence and immutability tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_audit_api.acceptance import AcceptanceRunner
from agent_audit_api.acceptance_history import (
    AcceptanceRunRepositoryError,
    SQLiteAcceptanceRunRepository,
)
from agent_audit_api.attack_cases import load_target_profiles
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.history import SQLiteAuditRunRepository
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from tests.acceptance_support import AcceptanceProvider, make_acceptance_embedding_retriever
from tests.unit.test_history_repository import _detail as scan_detail


@pytest.fixture(scope="module")
def acceptance_run():
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


def test_constructor_is_side_effect_free_and_first_use_initializes_schema(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "acceptance.sqlite3"
    assert not path.parent.exists()
    repository = SQLiteAcceptanceRunRepository(path)

    assert repository.path == path
    assert not path.parent.exists()
    assert not path.exists()
    assert repository.list() == []
    assert path.exists()


def test_full_roundtrip_preserves_complete_acceptance_snapshot(acceptance_run, tmp_path: Path) -> None:
    repository = SQLiteAcceptanceRunRepository(tmp_path / "acceptance.sqlite3")

    repository.save(acceptance_run)
    restored = repository.get(acceptance_run.id)

    assert restored is not None
    assert restored.model_dump(mode="json") == acceptance_run.model_dump(mode="json")
    assert restored.model_dump(mode="json", by_alias=True) == acceptance_run.model_dump(
        mode="json", by_alias=True
    )
    assert len(restored.plan_snapshots) == 4
    assert len(restored.profile_snapshots) == 4
    assert len(restored.differential_audits) == 2
    assert len(restored.retrieval_evaluation.cases) == 6
    assert len(restored.ci_gate.benchmark.cases) == 24
    assert restored.guided_scan.plan_id == "plan_sink_confidential_external"
    assert restored.guided_replay.plan.id == restored.guided_scan.plan_id


def test_save_is_append_only_duplicate_id_does_not_overwrite(acceptance_run, tmp_path: Path) -> None:
    repository = SQLiteAcceptanceRunRepository(tmp_path / "acceptance.sqlite3")
    repository.save(acceptance_run)
    replacement = acceptance_run.model_copy(update={"duration_ms": 999999.0})

    with pytest.raises(AcceptanceRunRepositoryError):
        repository.save(replacement)

    restored = repository.get(acceptance_run.id)
    assert restored is not None
    assert restored.duration_ms == acceptance_run.duration_ms


def test_list_get_and_previous_are_completion_ordered_and_bounded(acceptance_run, tmp_path: Path) -> None:
    repository = SQLiteAcceptanceRunRepository(tmp_path / "acceptance.sqlite3")
    first = acceptance_run.model_copy(
        deep=True,
        update={
            "id": "acceptance_001",
            "started_at": "2026-08-27T08:00:00Z",
            "completed_at": "2026-08-27T08:00:01Z",
        },
    )
    second = acceptance_run.model_copy(
        deep=True,
        update={
            "id": "acceptance_002",
            "started_at": "2026-08-27T08:00:02Z",
            "completed_at": "2026-08-27T08:00:03Z",
        },
    )
    third = acceptance_run.model_copy(
        deep=True,
        update={
            "id": "acceptance_003",
            "started_at": "2026-08-27T08:00:01Z",
            "completed_at": "2026-08-27T08:00:02Z",
        },
    )
    for run in (first, second, third):
        repository.save(run)

    assert [summary.id for summary in repository.list(limit=2)] == [
        "acceptance_002",
        "acceptance_003",
    ]
    assert repository.get("acceptance_missing") is None
    previous = repository.previous("acceptance_002")
    assert previous is not None
    assert previous.id == "acceptance_003"
    previous = repository.previous("acceptance_003")
    assert previous is not None
    assert previous.id == "acceptance_001"
    assert repository.previous("acceptance_001") is None
    for limit in (0, 101, True, 1.0):
        with pytest.raises(ValueError, match="between 1 and 100"):
            repository.list(limit=limit)


def test_saved_snapshot_cannot_be_changed_by_active_objects_or_returned_mutation(
    acceptance_run,
    tmp_path: Path,
) -> None:
    repository = SQLiteAcceptanceRunRepository(tmp_path / "acceptance.sqlite3")
    repository.save(acceptance_run)

    active_copy = acceptance_run.model_copy(deep=True)
    active_copy.contract_snapshot.name = "changed active Contract"
    active_copy.plan_snapshots[0].name = "changed active Plan"
    fetched = repository.get(acceptance_run.id)
    assert fetched is not None
    original = repository.get(acceptance_run.id)
    assert original is not None
    fetched.contract_snapshot.name = "changed fetched object"
    fetched.finding_categories.clear()

    restored_again = repository.get(acceptance_run.id)
    assert restored_again is not None
    assert restored_again.contract_snapshot.name == original.contract_snapshot.name
    assert restored_again.plan_snapshots[0].name == original.plan_snapshots[0].name
    assert restored_again.finding_categories == original.finding_categories


def test_acceptance_table_shares_sqlite_without_touching_scan_history(acceptance_run, tmp_path: Path) -> None:
    path = tmp_path / "shared.sqlite3"
    acceptance_repository = SQLiteAcceptanceRunRepository(path)
    scan_repository = SQLiteAuditRunRepository(path)
    detail = scan_detail(scan_id="scan_kept_when_acceptance_saved")

    scan_repository.save(detail)
    acceptance_repository.save(acceptance_run)

    restored_scan = scan_repository.get(detail.scan.id)
    restored_acceptance = acceptance_repository.get(acceptance_run.id)
    assert restored_scan is not None
    assert restored_scan.model_dump(mode="json") == detail.model_dump(mode="json")
    assert restored_acceptance is not None
    assert restored_acceptance.id == acceptance_run.id
    assert [item.id for item in acceptance_repository.list()] == [acceptance_run.id]


def test_sqlite_payload_contains_no_provider_credentials(acceptance_run, tmp_path: Path) -> None:
    path = tmp_path / "acceptance.sqlite3"
    SQLiteAcceptanceRunRepository(path).save(acceptance_run)
    payload = path.read_bytes()

    assert b"sk-test-api-key" not in payload
    assert b"Authorization: Bearer test-secret" not in payload
    assert b"api_key" not in payload
    assert b"credential" not in payload


def test_repository_rejects_prepopulated_or_invalid_acceptance_runs(acceptance_run, tmp_path: Path) -> None:
    repository = SQLiteAcceptanceRunRepository(tmp_path / "acceptance.sqlite3")

    with pytest.raises(ValueError, match="only completed"):
        repository.save(acceptance_run.model_copy(update={"status": "running"}))

    with pytest.raises(ValueError, match="non-empty"):
        repository.get("")
    with pytest.raises(ValueError, match="non-empty"):
        repository.previous("   ")
