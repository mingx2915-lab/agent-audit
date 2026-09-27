"""Unit coverage for immutable SQLite Scan history and append-only Replay."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agent_audit_api.attack_cases import load_target_profiles
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.evaluation import Finding, SemanticReview, TraceEvaluationResult
from agent_audit_api.history import (
    AuditRunDetail,
    AuditRunRepositoryError,
    AuditRuntimeSnapshot,
    PersistedReplay,
    SQLiteAuditRunRepository,
    TargetProfileSnapshot,
)
from agent_audit_api.planning import ContractAttackPlanner
from agent_audit_api.red_team import (
    AttackAttempt,
    AttackVariant,
    RedTeamScan,
    ScanStateTransition,
)
from agent_audit_api.replay import ReplayAttempt, ReplayResult, build_remediation
from agent_audit_api.schemas import Actor, AssistantQueryResult, TraceEvent
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.tools import MockCustomerExportTool, MockCustomerTool, MockMailTool


def _plan():
    data = load_demo_data()
    contract = load_security_contract()
    return next(
        plan
        for plan in ContractAttackPlanner(
            contract=contract,
            actors=data.actors,
            documents=data.documents,
            customers=data.customers,
            customer_tool=MockCustomerTool(data.customers),
            mail_tool=MockMailTool(),
            export_tool=MockCustomerExportTool(data.customers),
        ).plan()
        if plan.basis_type == "resource_owner_scope"
    )


def _detail(
    *,
    scan_id: str = "scan_history_001",
    completed_at: str = "2026-08-27T08:00:00Z",
    replays: list[PersistedReplay] | None = None,
) -> AuditRunDetail:
    data = load_demo_data()
    contract = load_security_contract()
    plan = _plan()
    profile = next(profile for profile in load_target_profiles() if profile.id == "secure")
    trace_events = [
        TraceEvent(
            sequence=1,
            type="input",
            summary="Received synthetic scan input",
            details={"actorId": plan.actor_id, "message": plan.message},
            occurred_at="2026-08-27T08:00:00Z",
        ),
        TraceEvent(
            sequence=2,
            type="authorization",
            summary="Synthetic denied resource authorization",
            details={
                "actorId": plan.actor_id,
                "documentId": plan.target_id,
                "decision": "denied",
                "ruleId": "resource_customer_owner",
            },
            occurred_at="2026-08-27T08:00:00Z",
        ),
    ]
    query_result = AssistantQueryResult(
        query_id="query_history_001",
        actor=Actor(id="sales_001", display_name="销售一号", role="sales"),
        answer="合成扫描回答",
        trace_events=trace_events,
    )
    finding = Finding(
        id="finding_history_001",
        category="resource_authorization_bypass",
        severity="high",
        title="被拒绝资源进入上下文",
        summary="Synthetic finding",
        contract_basis="explicit_rule",
        rule_id="resource_customer_owner",
        evidence_sequences=[2],
    )
    evaluation = TraceEvaluationResult(
        status="failed",
        contract_id=contract.id,
        contract_version=contract.version,
        findings=[finding],
        semantic_review=SemanticReview(performed=False, explanation=None),
    )
    variant = AttackVariant(
        id="variant_history_001",
        parent_attempt_id=None,
        round=1,
        actor_id=plan.actor_id,
        attacker_type=plan.attacker_type,
        basis_rule_id=plan.basis_rule_id,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
        message=plan.message,
        mutation_reason="依据合成 Trace 的固定测试变体",
    )
    scan = RedTeamScan(
        id=scan_id,
        plan_id=plan.id,
        contract_id=contract.id,
        contract_version=contract.version,
        target_profile_id=profile.id,
        provider="injected:HistoryProvider",
        model=None,
        max_rounds=2,
        status="completed",
        stop_reason="finding_detected",
        state_transitions=[
            ScanStateTransition(
                sequence=1,
                state="profiling",
                summary="读取固定测试计划",
                occurred_at="2026-08-27T08:00:00Z",
            ),
            ScanStateTransition(
                sequence=2,
                state="stopped",
                summary="发现合成 Finding",
                occurred_at=completed_at,
            ),
        ],
        attempts=[
            AttackAttempt(
                id="attempt_history_001",
                scan_id=scan_id,
                round=1,
                status="finding",
                variant=variant,
                query_result=query_result,
                evaluation=evaluation,
                duration_ms=12.34,
            )
        ],
        started_at="2026-08-27T07:59:59Z",
        completed_at=completed_at,
        duration_ms=23.45,
    )
    return AuditRunDetail(
        scan=scan,
        plan_snapshot=plan,
        contract_snapshot=contract,
        target_profile_snapshot=TargetProfileSnapshot(
            id=profile.id,
            name=profile.name,
            enforce_resource_authorization=profile.enforce_resource_authorization,
            enforce_tool_authorization=profile.enforce_tool_authorization,
            enforce_sink_authorization=profile.enforce_sink_authorization,
        ),
        runtime_snapshot=AuditRuntimeSnapshot(
            provider="injected:HistoryProvider",
            model=None,
            retriever_engine="tfidf",
            retriever_model=None,
            retriever_dimensions=None,
            indexed_document_count=len(data.documents),
        ),
        replays=list(replays or []),
    )


def _replay(detail: AuditRunDetail, replay_id: str, created_at: str) -> PersistedReplay:
    scan = detail.scan
    plan = detail.plan_snapshot
    secure_attempt = ReplayAttempt(
        profile_id="secure",
        execution_status="blocked",
        query_result=None,
        trace_events=scan.attempts[0].query_result.trace_events,
        evaluation=scan.attempts[0].evaluation.model_copy(update={"status": "passed", "findings": []}),
        blocked_reason="synthetic secure replay block",
    )
    before_attempt = ReplayAttempt(
        profile_id=plan.target_profile_id,
        execution_status="completed",
        query_result=scan.attempts[0].query_result,
        trace_events=scan.attempts[0].query_result.trace_events,
        evaluation=scan.attempts[0].evaluation,
        blocked_reason=None,
    )
    replay = ReplayResult(
        id=replay_id,
        plan=plan,
        remediation=build_remediation(plan),
        before=before_attempt,
        after=secure_attempt,
        status="passed",
    )
    return PersistedReplay(id=replay_id, created_at=created_at, replay=replay)


def test_repository_constructor_is_side_effect_free_and_first_use_initializes_schema(tmp_path) -> None:
    path = tmp_path / "nested" / "audit.sqlite3"
    repository = SQLiteAuditRunRepository(path)

    assert repository.path == path
    assert not path.exists()
    assert repository.list() == []
    assert path.exists()


def test_save_get_roundtrip_preserves_every_nested_pydantic_field(tmp_path) -> None:
    repository = SQLiteAuditRunRepository(tmp_path / "audit.sqlite3")
    original = _detail()

    repository.save(original)
    restored = repository.get(original.scan.id)

    assert restored is not None
    assert restored.model_dump() == original.model_dump()
    assert restored.model_dump(by_alias=True) == original.model_dump(by_alias=True)
    assert isinstance(restored.scan.attempts[0], AttackAttempt)
    assert isinstance(restored.scan.attempts[0].variant, AttackVariant)
    assert isinstance(restored.scan.attempts[0].query_result.trace_events[0], TraceEvent)
    assert isinstance(restored.scan.attempts[0].evaluation.findings[0], Finding)
    assert isinstance(restored.contract_snapshot, type(original.contract_snapshot))
    assert isinstance(restored.target_profile_snapshot, TargetProfileSnapshot)
    assert isinstance(restored.runtime_snapshot, AuditRuntimeSnapshot)
    assert restored.replays == []


def test_list_is_completion_descending_and_limit_is_bounded(tmp_path) -> None:
    repository = SQLiteAuditRunRepository(tmp_path / "audit.sqlite3")
    details = [
        _detail(scan_id="scan_001", completed_at="2026-08-27T08:00:01Z"),
        _detail(scan_id="scan_002", completed_at="2026-08-27T08:00:03Z"),
        _detail(scan_id="scan_003", completed_at="2026-08-27T08:00:02Z"),
    ]
    for detail in details:
        repository.save(detail)

    summaries = repository.list(limit=2)

    assert [summary.scan_id for summary in summaries] == ["scan_002", "scan_003"]
    assert all(summary.attempt_count == 1 for summary in summaries)
    assert all(summary.finding_count == 1 for summary in summaries)
    assert all(summary.replay_count == 0 for summary in summaries)
    for limit in (0, 101, True, 1.0):
        with pytest.raises(ValueError, match="between 1 and 100"):
            repository.list(limit=limit)


def test_duplicate_scan_does_not_overwrite_original_detail(tmp_path) -> None:
    repository = SQLiteAuditRunRepository(tmp_path / "audit.sqlite3")
    original = _detail()
    repository.save(original)
    replacement = original.model_copy(
        update={
            "scan": original.scan.model_copy(update={"duration_ms": 999.0}),
        }
    )

    with pytest.raises(AuditRunRepositoryError):
        repository.save(replacement)

    restored = repository.get(original.scan.id)
    assert restored is not None
    assert restored.scan.duration_ms == original.scan.duration_ms


def test_append_replay_is_ordered_duplicate_safe_and_does_not_overwrite_scan(tmp_path) -> None:
    repository = SQLiteAuditRunRepository(tmp_path / "audit.sqlite3")
    detail = _detail()
    repository.save(detail)
    first = _replay(detail, "replay_z", "2026-08-27T08:00:01Z")
    second = _replay(detail, "replay_a", "2026-08-27T08:00:01Z")

    repository.append_replay(detail.scan.id, first)
    repository.append_replay(detail.scan.id, second)
    with pytest.raises(AuditRunRepositoryError):
        repository.append_replay(detail.scan.id, first)
    with pytest.raises(KeyError, match="unknown scan"):
        repository.append_replay("scan_missing", first)

    restored = repository.get(detail.scan.id)
    assert restored is not None
    assert [item.replay.id for item in restored.replays] == ["replay_z", "replay_a"]
    assert [item.model_dump() for item in restored.replays] == [
        first.model_dump(),
        second.model_dump(),
    ]
    assert restored.scan.model_dump() == detail.scan.model_dump()
    assert restored.plan_snapshot.model_dump() == detail.plan_snapshot.model_dump()


def test_save_rejects_prepopulated_replays_and_mismatched_snapshots(tmp_path) -> None:
    repository = SQLiteAuditRunRepository(tmp_path / "audit.sqlite3")
    detail = _detail()
    replay = _replay(detail, "replay_001", "2026-08-27T08:00:01Z")

    with pytest.raises(ValueError, match="replays must be appended"):
        repository.save(detail.model_copy(update={"replays": [replay]}))
    with pytest.raises(TypeError, match="AuditRunDetail"):
        repository.save(object())
    with pytest.raises(ValueError, match="plan snapshot ids"):
        repository.save(
            detail.model_copy(
                update={
                    "scan": detail.scan.model_copy(update={"plan_id": "plan_other"}),
                }
            )
        )


def test_repository_errors_are_explicit_and_never_silently_fall_back(tmp_path, monkeypatch) -> None:
    repository = SQLiteAuditRunRepository(tmp_path / "audit.sqlite3")

    def fail_connect():
        raise AuditRunRepositoryError("synthetic storage failure")

    monkeypatch.setattr(repository, "_connect", fail_connect)

    with pytest.raises(AuditRunRepositoryError, match="synthetic storage failure"):
        repository.list()
    with pytest.raises(AuditRunRepositoryError, match="synthetic storage failure"):
        repository.get("scan_history_001")
    with pytest.raises(AuditRunRepositoryError, match="synthetic storage failure"):
        repository.save(_detail())


def test_sqlite_payload_is_structured_json_and_contains_no_credentials(tmp_path) -> None:
    path = tmp_path / "audit.sqlite3"
    repository = SQLiteAuditRunRepository(path)
    detail = _detail()
    repository.save(detail)
    replay = _replay(detail, "replay_secret_check", "2026-08-27T08:00:01Z")
    repository.append_replay(detail.scan.id, replay)

    with sqlite3.connect(path) as connection:
        values = connection.execute(
            "SELECT scan_json, plan_json, contract_json, target_profile_json, runtime_json "
            "FROM audit_runs UNION ALL SELECT replay_json, '', '', '', '' FROM audit_replays"
        ).fetchall()
    raw = json.dumps(values, ensure_ascii=False).encode("utf-8")
    assert b"sk-test-api-key" not in raw
    assert b"Authorization: Bearer" not in raw
    assert b"Bearer test-secret" not in raw
