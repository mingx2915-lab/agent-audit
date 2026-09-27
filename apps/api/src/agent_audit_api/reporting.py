"""Pure attack-chain report generation from a completed ReplayResult."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from .replay import ReplayAttempt, ReplayResult
from .schemas import CamelModel, TraceEvent


class AttackChainReport(CamelModel):
    """A structured report and its deterministic Markdown representation."""

    id: str
    generated_at: str
    title: str
    executive_summary: str
    replay: ReplayResult
    markdown: str


def _generated_at() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _trace_events(attempt: ReplayAttempt) -> list[TraceEvent]:
    """Return a stable sequence-ordered copy of an attempt's events."""

    return sorted(attempt.trace_events, key=lambda event: event.sequence)


def _event_value(details: Mapping[str, Any], key: str) -> str | None:
    value = details.get(key)
    return value if isinstance(value, str) and value else None


def _document_ids(events: Sequence[TraceEvent]) -> list[str]:
    identifiers: list[str] = []
    for event in events:
        document_id = _event_value(event.details, "documentId")
        if document_id is not None:
            identifiers.append(document_id)
        document_ids = event.details.get("documentIds")
        if isinstance(document_ids, list):
            identifiers.extend(
                value for value in document_ids if isinstance(value, str) and value
            )
    return _unique(identifiers)


def _coverage_rows(attempts: Sequence[ReplayAttempt]) -> list[tuple[str, int, str]]:
    events = [event for attempt in attempts for event in _trace_events(attempt)]

    source_events = [event for event in events if event.type == "source"]
    source_ids = _unique(
        identifier
        for event in source_events
        for identifier in (
            _event_value(event.details, "sourceId"),
            _event_value(event.details, "documentId"),
        )
        if identifier is not None
    )

    resource_ids = _document_ids(events)
    authorization_events = [event for event in events if event.type == "authorization"]
    authorization_ids: list[str] = []
    for event in authorization_events:
        details = event.details
        identifier = _event_value(details, "documentId") or _event_value(
            details, "toolName"
        )
        if identifier is None:
            identifier = "authorization"
        decision = _event_value(details, "decision")
        rule_id = _event_value(details, "ruleId")
        suffix = ", ".join(
            part
            for part in (
                f"decision={decision}" if decision is not None else None,
                f"ruleId={rule_id}" if rule_id is not None else None,
            )
            if part is not None
        )
        authorization_ids.append(f"{identifier} ({suffix})" if suffix else identifier)

    tool_events = [
        event for event in events if event.type in {"tool_call", "tool_result"}
    ]
    tool_ids = _unique(
        _event_value(event.details, "toolName") or event.type for event in tool_events
    )

    sink_events = [event for event in events if event.type == "sink"]
    sink_ids = _unique(
        _event_value(event.details, "sinkId")
        or _event_value(event.details, "sinkType")
        or event.type
        for event in sink_events
    )

    return [
        ("Source", len(source_events), ", ".join(source_ids) if source_ids else "无"),
        ("Resource", len(resource_ids), ", ".join(resource_ids) if resource_ids else "无"),
        (
            "Authorization",
            len(authorization_events),
            ", ".join(_unique(authorization_ids)) if authorization_ids else "无",
        ),
        ("Tool", len(tool_events), ", ".join(tool_ids) if tool_ids else "无"),
        ("Sink", len(sink_events), ", ".join(sink_ids) if sink_ids else "无"),
    ]


def _finding_markdown(attempt: ReplayAttempt) -> str:
    findings = attempt.evaluation.findings
    if not findings:
        return "无"
    lines: list[str] = []
    for finding in findings:
        evidence = ", ".join(str(sequence) for sequence in finding.evidence_sequences)
        lines.append(
            "- "
            f"`{finding.id}` category=`{finding.category}` "
            f"ruleId=`{finding.rule_id or 'null'}` "
            f"evidenceSequences=`[{evidence}]`"
        )
        lines.append(f"  - 标题：{finding.title}")
        lines.append(f"  - 摘要：{finding.summary}")
        lines.append(
            f"  - severity=`{finding.severity}` contractBasis=`{finding.contract_basis}`"
        )
    return "\n".join(lines)


def _query_result_markdown(attempt: ReplayAttempt) -> list[str]:
    if attempt.query_result is None:
        lines = ["- QueryResult：`null`（未生成模型回答）"]
        if attempt.blocked_reason is not None:
            lines.append(f"- blockedReason：{attempt.blocked_reason}")
        return lines
    return [
        "- QueryResult：已生成模型回答",
        f"- Actor：`{attempt.query_result.actor.id}`",
        f"- Answer：{attempt.query_result.answer}",
    ]


def _attempt_markdown(label: str, attempt: ReplayAttempt) -> list[str]:
    lines = [
        f"## {label}",
        f"- Profile：`{attempt.profile_id}`",
        f"- Execution status：`{attempt.execution_status}`",
        f"- Evaluation：`{attempt.evaluation.status}`",
        f"- Actual Finding 数：{len(attempt.evaluation.findings)}",
        "",
        "### 实际 Finding",
        _finding_markdown(attempt),
        "",
        "### Query Result",
        *_query_result_markdown(attempt),
        "",
        "### 完整 Trace",
    ]
    events = _trace_events(attempt)
    if not events:
        lines.append("无")
        return lines
    for event in events:
        lines.append(
            f"- `#{event.sequence}` `{event.type}` {event.summary} "
            f"(occurredAt=`{event.occurred_at}`)"
        )
        lines.append(f"  - details: `{_stable_json(event.details)}`")
    return lines


def _executive_summary(replay: ReplayResult) -> str:
    before = replay.before
    after = replay.after
    return (
        f"BEFORE execution={before.execution_status}，Evaluation={before.evaluation.status}，"
        f"实际 Finding={len(before.evaluation.findings)}；"
        f"AFTER execution={after.execution_status}，Evaluation={after.evaluation.status}，"
        f"实际 Finding={len(after.evaluation.findings)}；"
        f"Replay={replay.status}。"
    )


def _markdown(replay: ReplayResult, generated_at: str) -> str:
    plan = replay.plan
    coverage = _coverage_rows((replay.before, replay.after))
    lines = [
        f"# {plan.name}",
        "",
        "SYNTHETIC / DEMO ONLY",
        "",
        "## 执行摘要",
        _executive_summary(replay),
        "",
        "## 计划与业务边界",
        "",
        "| Actor | Attacker | Rule basis | Target |",
        "| --- | --- | --- | --- |",
        (
            f"| `{plan.actor_id}` | `{plan.attacker_type}` | "
            f"`{plan.basis_type}` / `{plan.basis_rule_id}` | "
            f"`{plan.target_kind}` / `{plan.target_id}` |"
        ),
        "",
        "## Evidence Coverage",
        "",
        "| Evidence | Count | Identifiers |",
        "| --- | ---: | --- |",
    ]
    lines.extend(f"| {kind} | {count} | {identifiers} |" for kind, count, identifiers in coverage)
    lines.extend(
        [
            "",
            "## 修复参考与模拟复测",
            "",
            (
                "> **仅供参考：** 以下控制项根据当前 Security Contract 与本次 Trace 生成，"
                "After 只是在内置 `secure` Profile 中进行模拟复测。软件不会修改企业系统，"
                "该结果不能替代安全、业务和运维人员的根因分析、影响评估与变更审批。"
            ),
            "",
            "| Configuration path | Before | After |",
            "| --- | --- | --- |",
            (
                f"| `{replay.remediation.configuration_path}` | "
                f"`{str(replay.remediation.before_value).lower()}` | "
                f"`{str(replay.remediation.after_value).lower()}` |"
            ),
            (
                f"\n`{str(replay.remediation.before_value).lower()}` "
                f"→ `{str(replay.remediation.after_value).lower()}`"
            ),
            "",
        ]
    )
    lines.extend(_attempt_markdown("BEFORE 实际结果", replay.before))
    lines.extend(["", *_attempt_markdown("AFTER 实际结果", replay.after)])
    lines.extend(
        [
            "",
            "## Replay 结论",
            f"- status：`{replay.status}`",
            f"- BEFORE actual Evaluation：`{replay.before.evaluation.status}`",
            f"- AFTER actual Evaluation：`{replay.after.evaluation.status}`",
            f"- 生成时间：`{generated_at}`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_attack_chain_report(replay: ReplayResult) -> AttackChainReport:
    """Build a report using only actual facts carried by ``replay``."""

    generated_at = _generated_at()
    return AttackChainReport(
        id=f"report_{replay.id}",
        generated_at=generated_at,
        title=f"{replay.plan.name} Replay 报告",
        executive_summary=_executive_summary(replay),
        replay=replay,
        markdown=_markdown(replay, generated_at),
    )


__all__ = ["AttackChainReport", "build_attack_chain_report"]
