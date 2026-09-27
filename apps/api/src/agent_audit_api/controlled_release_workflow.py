"""Explicit Test-only workflow used only by release evidence tooling."""

from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .acceptance import AcceptanceRun, AcceptanceRunner
from .acceptance_history import SQLiteAcceptanceRunRepository
from .attack_cases import load_target_profiles
from .demo_data import load_demo_data
from .history import (
    AuditRunDetail,
    AuditRuntimeSnapshot,
    PersistedReplay,
    SQLiteAuditRunRepository,
)
from .providers.base import LLMResponse, ProviderUsage, ToolCall
from .retrieval import EmbeddingRetriever, TfidfRetriever
from .schemas import CamelModel
from .security_contract import load_security_contract
from .stability import DeterministicStabilityProvider, run_stability_runner


READINESS_TOOL_NAME = "agent_audit_readiness_probe"
READINESS_NONCE = "agent-audit-readiness"
CONTROLLED_RETRIEVER_MODEL = "controlled_release_hash_embedder.v1"
_TOKEN_PATTERN = re.compile(
    r"[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*|[\u3400-\u4dbf\u4e00-\u9fff]"
)


@dataclass
class ReleaseEvidenceProvider(DeterministicStabilityProvider):
    """Test-only deterministic Provider for explicit release evidence."""

    model: str = "controlled-release-evidence-provider"
    provider_id = "controlled_release_test_provider"

    @staticmethod
    def _contains(messages: Any, phrase: str) -> bool:
        return any(
            phrase in str(message.get("content") or "")
            for message in messages
            if isinstance(message, Mapping)
        )

    async def complete(self, messages, tools=None) -> LLMResponse:
        call_number = len(self.calls) + 1
        tool_names = self._tool_names(tools)
        if READINESS_TOOL_NAME in tool_names:
            return self._record(messages, tools, LLMResponse(
                content=None,
                tool_calls=(ToolCall(
                    id=f"release_readiness_{call_number}",
                    name=READINESS_TOOL_NAME,
                    arguments={"nonce": READINESS_NONCE},
                ),),
                usage=self._usage(call_number),
            ))
        if self._contains(messages, "strict JSON readiness probe"):
            return self._record(messages, tools, LLMResponse(
                content=json.dumps({"status": "ready", "nonce": READINESS_NONCE}),
                usage=self._usage(call_number),
            ))
        if self._contains(messages, "Connectivity probe"):
            return self._record(messages, tools, LLMResponse(
                content="controlled release connectivity response",
                usage=self._usage(call_number),
            ))
        variant_payload = self._variant_payload(messages)
        if variant_payload is not None:
            baseline = variant_payload["baseline"]
            round_number = variant_payload.get("round", 1)
            if not isinstance(round_number, int):
                round_number = 1
            baseline_message = baseline.get("message")
            if not isinstance(baseline_message, str) or not baseline_message.strip():
                baseline_message = "执行固定合成 Source→Sink 验收"
            return self._record(
                messages,
                tools,
                LLMResponse(
                    content=json.dumps(
                        {
                            "message": f"{baseline_message}（deterministic round {round_number}）",
                            "mutationReason": "使用实际 Trace 前提下的固定 deterministic 变体",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    usage=self._usage(call_number),
                ),
            )
        user_text = self._user_text(messages)
        call: ToolCall | None = None
        if "mock_customer_lookup" in tool_names and "mock_customer_lookup" in user_text:
            customer_id = "customer_002" if "customer_002" in user_text else "customer_001"
            call = ToolCall(id=f"release_call_{call_number}", name="mock_customer_lookup",
                            arguments={"customerId": customer_id})
        elif "mock_mail_send" in tool_names and "mock_mail_send" in user_text:
            known_ids = (
                "doc_product_overview_001", "doc_finance_budget_001",
                "doc_external_vendor_prompt_001", "doc_demo_usage_guide_001",
                "doc_hr_handbook_001", "doc_customer_contract_001",
                "doc_customer_contract_002",
            )
            resource_ids = [item for item in known_ids if item in user_text]
            if "Atlas Vendor" in user_text and "doc_external_vendor_prompt_001" not in resource_ids:
                resource_ids.insert(0, "doc_external_vendor_prompt_001")
            if "财务预算" in user_text and "doc_finance_budget_001" not in resource_ids:
                resource_ids.append("doc_finance_budget_001")
            if not resource_ids:
                resource_ids.append("doc_product_overview_001")
            call = ToolCall(id=f"release_call_{call_number}", name="mock_mail_send",
                            arguments={"to": "audit@external-sink.demo.local" if "external-sink.demo.local" in user_text else "audit@nebula.demo.local",
                                       "subject": "synthetic release evidence", "body": "controlled evidence",
                                       "resourceIds": resource_ids,
                                       "approved": "approved=true" in user_text})
        elif "mock_customer_export" in tool_names and "mock_customer_export" in user_text:
            ids = ["customer_001"] + (["customer_002"] if "customer_002" in user_text else [])
            call = ToolCall(id=f"release_call_{call_number}", name="mock_customer_export",
                            arguments={"customerIds": ids,
                                       "destination": "external-sink://exports/customers.json" if "external-sink://" in user_text else "workspace://exports/customers.json",
                                       "approved": "approved=true" in user_text})
        if call is not None:
            return self._record(messages, tools, LLMResponse(
                content=None, tool_calls=(call,), usage=self._usage(call_number)
            ))
        # Keep the Test Double self-contained.  This is the deterministic
        # non-tool response for ordinary synthetic queries, not a fallback to
        # another Provider implementation.
        return self._record(
            messages,
            tools,
            LLMResponse(
                content="controlled release evidence provider response",
                usage=self._usage(call_number),
            ),
        )


@dataclass
class ReleaseEvidenceEmbedder:
    """Test-only deterministic 512-dimensional hashing vectorizer.

    Release evidence must not download or invoke the production embedding
    model.  This vectorizer still exercises the real ``EmbeddingRetriever``
    index/search boundary, while deriving both document and query vectors from
    their text with a cross-process stable hash.  It deliberately contains no
    fixed query/document mapping or expected-outcome lookup.
    """

    @staticmethod
    def _vector(text: str) -> tuple[float, ...]:
        values = [0.0] * 512
        tokens = Counter(token.casefold() for token in _TOKEN_PATTERN.findall(text))
        for token, count in tokens.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % len(values)
            values[index] += float(count)
        return tuple(values)

    def embed(self, documents: Sequence[str]) -> Iterable[Sequence[float]]:
        return tuple(self._vector(document) for document in documents)

    def query_embed(self, query: str) -> Iterable[Sequence[float]]:
        return (self._vector(query),)


class FindingEvidence(CamelModel):
    schema_version: str = "controlled-finding-evidence.v1"
    scan_id: str
    plan_id: str
    findings: list[dict[str, Any]]


class ReplayEvidence(CamelModel):
    schema_version: str = "controlled-replay-evidence.v1"
    id: str
    scan_id: str
    plan_id: str
    status: str
    before: dict[str, Any]
    after: dict[str, Any]


class AcceptanceEvidence(CamelModel):
    schema_version: str = "controlled-acceptance-evidence.v1"
    id: str
    status: str
    verdict: str
    case_count: int
    matched_case_count: int
    mismatched_case_count: int
    gate_checks: list[dict[str, str]]
    finding_count: int
    finding_categories: list[str]
    guided_scan_id: str
    guided_replay_status: str
    provider: str
    retriever: str


class ControlledReleaseWorkflow(CamelModel):
    schema_version: str = "controlled-release-workflow.v1"
    scan_id: str
    replay_id: str
    acceptance_id: str
    audit: AuditRunDetail
    replay: PersistedReplay
    findings: FindingEvidence
    replay_evidence: ReplayEvidence
    acceptance: AcceptanceRun
    acceptance_evidence: AcceptanceEvidence
    finding_markdown: str
    replay_markdown: str
    acceptance_markdown: str


def _finding_markdown(evidence: FindingEvidence) -> str:
    lines = ["# Controlled Finding Evidence", "", f"- Scan: `{evidence.scan_id}`",
             f"- Plan: `{evidence.plan_id}`", "", "| Category | Severity | Rule |", "|---|---|---|"]
    for finding in evidence.findings:
        lines.append(f"| {finding.get('category')} | {finding.get('severity')} | {finding.get('ruleId')} |")
    return "\n".join(lines) + "\n"


def _attempt_projection(attempt: Any) -> dict[str, Any]:
    return {
        "evaluation": attempt.evaluation.status,
        "execution": attempt.execution_status,
        "findings": [
            {
                "id": finding.id,
                "category": finding.category,
                "ruleId": finding.rule_id,
            }
            for finding in attempt.evaluation.findings
        ],
        "trace": [
            {"sequence": event.sequence, "eventType": event.type}
            for event in attempt.trace_events
        ],
    }


def _replay_markdown(evidence: ReplayEvidence) -> str:
    lines = ["# Controlled Replay Evidence", "", f"- Replay: `{evidence.id}`",
             f"- Scan: `{evidence.scan_id}`", f"- Plan: `{evidence.plan_id}`",
             f"- Status: `{evidence.status}`", ""]
    for label, attempt in (("Before", evidence.before), ("After", evidence.after)):
        lines.extend([f"## {label}", "", f"- Evaluation: `{attempt['evaluation']}`",
                      f"- Execution: `{attempt['execution']}`",
                      f"- Finding count: `{len(attempt['findings'])}`",
                      f"- Trace events: `{len(attempt['trace'])}`", ""])
    return "\n".join(lines)


def _acceptance_markdown(evidence: AcceptanceEvidence) -> str:
    lines = ["# Controlled Acceptance Evidence", "", f"- Acceptance: `{evidence.id}`",
             f"- Status: `{evidence.status}`", f"- Verdict: `{evidence.verdict}`",
             f"- Cases: `{evidence.case_count}`", f"- Matched: `{evidence.matched_case_count}`",
             f"- Mismatched: `{evidence.mismatched_case_count}`",
             f"- Findings: `{evidence.finding_count}`",
             f"- Finding categories: `{', '.join(evidence.finding_categories)}`",
             f"- Guided Scan: `{evidence.guided_scan_id}`",
             f"- Guided Replay: `{evidence.guided_replay_status}`",
             f"- Provider: `{evidence.provider}`", f"- Retriever: `{evidence.retriever}`",
             "", "## Gate checks", "", "| Check | Status |", "|---|---|"]
    lines.extend(f"| {item['id']} | {item['status']} |" for item in evidence.gate_checks)
    return "\n".join(lines) + "\n"


async def build_controlled_release_workflow(workspace_root: str | Path) -> ControlledReleaseWorkflow:
    """Run and persist the explicit Test-only release evidence workflow."""

    root = Path(workspace_root)
    provider = ReleaseEvidenceProvider()
    stability = await run_stability_runner(iterations=1, provider=provider, workspace_root=root)
    if stability.status != "passed" or not stability.iterations:
        raise RuntimeError("controlled release Scan/Replay failed")
    iteration = stability.iterations[0]
    from .workspace import WorkspaceService

    workspace = WorkspaceService().open(root)
    audit_repository = SQLiteAuditRunRepository(workspace.history_db_path)
    audit = audit_repository.get(iteration.scan_id or "")
    if (
        audit is None
        or iteration.scan_id is None
        or audit.scan.id != iteration.scan_id
        or len(audit.replays) != 1
    ):
        raise RuntimeError("controlled release Audit repository read-back failed")
    persisted_replay = audit.replays[0]
    _validate_controlled_scan(audit)
    _validate_persisted_replay(audit, persisted_replay)

    data = load_demo_data(workspace.documents_path)
    contract = load_security_contract(workspace.contract_path)
    profiles = load_target_profiles(workspace.cases_path)
    embedding = EmbeddingRetriever(data.documents, embedder=ReleaseEvidenceEmbedder())
    controlled_runtime_snapshot = AuditRuntimeSnapshot(
        provider=provider.provider_id,
        model=provider.model,
        retriever_engine=embedding.metadata.engine_id,
        retriever_model=CONTROLLED_RETRIEVER_MODEL,
        retriever_dimensions=embedding.metadata.dimensions,
        indexed_document_count=embedding.metadata.indexed_document_count,
    )
    acceptance = await AcceptanceRunner(
        provider=provider,
        attack_provider=provider,
        retriever=embedding,
        tfidf_retriever=TfidfRetriever(data.documents),
        contract=contract,
        profiles=profiles,
        demo_data=data,
        runtime_snapshot=controlled_runtime_snapshot,
    ).run()
    acceptance_repository = SQLiteAcceptanceRunRepository(workspace.history_db_path)
    acceptance_repository.save(acceptance)
    stored_acceptance = acceptance_repository.get(acceptance.id)
    if stored_acceptance is None or stored_acceptance.model_dump(mode="json") != acceptance.model_dump(mode="json"):
        raise RuntimeError("controlled release Acceptance repository read-back failed")
    finding_rows = [
        {
            "id": finding.id,
            "category": finding.category,
            "severity": finding.severity,
            "ruleId": finding.rule_id,
        }
        for attempt in audit.scan.attempts
        for finding in attempt.evaluation.findings
    ]
    _validate_controlled_acceptance(stored_acceptance, audit)
    finding_evidence = FindingEvidence(
        scan_id=audit.scan.id, plan_id=audit.plan_snapshot.id, findings=finding_rows
    )
    replay_evidence = ReplayEvidence(
        id=persisted_replay.id,
        scan_id=audit.scan.id,
        plan_id=audit.plan_snapshot.id,
        status=persisted_replay.replay.status,
        before=_attempt_projection(persisted_replay.replay.before),
        after=_attempt_projection(persisted_replay.replay.after),
    )
    benchmark = stored_acceptance.ci_gate.benchmark
    acceptance_evidence = AcceptanceEvidence(
        id=stored_acceptance.id,
        status=stored_acceptance.status,
        verdict=stored_acceptance.verdict,
        case_count=len(benchmark.cases),
        matched_case_count=benchmark.metrics.matched_case_count,
        mismatched_case_count=len(benchmark.cases) - benchmark.metrics.matched_case_count,
        gate_checks=[
            {"id": check.id, "status": "passed" if check.passed else "failed"}
            for check in stored_acceptance.ci_gate.checks
        ],
        finding_count=stored_acceptance.finding_count,
        finding_categories=list(stored_acceptance.finding_categories),
        guided_scan_id=stored_acceptance.guided_scan.id,
        guided_replay_status=stored_acceptance.guided_replay.status,
        provider=stored_acceptance.runtime_snapshot.provider,
        retriever=stored_acceptance.runtime_snapshot.retriever_engine,
    )
    return ControlledReleaseWorkflow(
        scan_id=audit.scan.id,
        replay_id=persisted_replay.id,
        acceptance_id=stored_acceptance.id,
        audit=audit,
        replay=persisted_replay,
        findings=finding_evidence,
        replay_evidence=replay_evidence,
        acceptance=stored_acceptance,
        acceptance_evidence=acceptance_evidence,
        finding_markdown=_finding_markdown(finding_evidence),
        replay_markdown=_replay_markdown(replay_evidence),
        acceptance_markdown=_acceptance_markdown(acceptance_evidence),
    )


def _validate_controlled_scan(audit: AuditRunDetail) -> None:
    """Require the exact release-demo Source→Sink Finding claim."""

    findings = [
        finding
        for attempt in audit.scan.attempts
        for finding in attempt.evaluation.findings
    ]
    if len(findings) != 1:
        raise RuntimeError("controlled release Scan must produce exactly one Finding")
    finding = findings[0]
    if (
        finding.category != "external_sink_policy_violation"
        or finding.severity != "critical"
        or finding.rule_id != "sink_external_message_confidential"
    ):
        raise RuntimeError("controlled release Scan Finding is not the expected Critical Sink violation")


def _validate_persisted_replay(
    audit: AuditRunDetail,
    persisted_replay: PersistedReplay,
) -> None:
    replay = persisted_replay.replay
    if replay.plan.id != audit.plan_snapshot.id or replay.plan.id != audit.scan.plan_id:
        raise RuntimeError("controlled release Replay plan does not match persisted Scan")
    if replay.status != "passed":
        raise RuntimeError("controlled release Replay did not pass")
    if replay.before.evaluation.status != "failed" or replay.after.evaluation.status != "passed":
        raise RuntimeError("controlled release Replay evaluations are inconsistent")
    if replay.after.execution_status != "blocked":
        raise RuntimeError("controlled release Replay after state was not blocked")


def _validate_controlled_acceptance(
    acceptance: AcceptanceRun,
    audit: AuditRunDetail,
) -> None:
    benchmark = acceptance.ci_gate.benchmark
    if acceptance.status != "completed" or len(benchmark.cases) != 24:
        raise RuntimeError("controlled release Acceptance must contain 24 completed cases")
    if acceptance.guided_scan.plan_id != audit.scan.plan_id:
        raise RuntimeError("controlled release Acceptance guided Scan plan does not match")
    if acceptance.guided_replay.plan.id != audit.plan_snapshot.id:
        raise RuntimeError("controlled release Acceptance guided Replay plan does not match")


__all__ = ["AcceptanceEvidence", "ControlledReleaseWorkflow", "FindingEvidence", "ReplayEvidence", "build_controlled_release_workflow"]
