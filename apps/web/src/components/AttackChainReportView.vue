<script setup lang="ts">
import { computed } from "vue";
import type {
  AttackChainReport,
  AttackPlanBasisType,
  AttackPlanTargetKind,
  AttackerType,
  Finding,
  ReplayAttempt,
  TraceEvent,
  TraceEventType,
} from "@agent-audit/contracts";

const props = defineProps<{
  report: AttackChainReport;
}>();

const eventLabels: Record<TraceEventType, string> = {
  input: "输入",
  source: "来源",
  retrieval: "检索",
  authorization: "权限判断",
  tool_call: "工具调用",
  tool_result: "工具结果",
  sink: "数据流向",
  model_response: "模型响应",
};

const findingCategoryLabels: Record<Finding["category"], string> = {
  resource_authorization_bypass: "资源授权绕过",
  tool_authorization_bypass: "工具授权绕过",
  external_sink_policy_violation: "外部数据流向策略违规",
  tool_business_policy_violation: "工具业务约束违规",
};

const findingSeverityLabels: Record<Finding["severity"], string> = {
  high: "高风险 · HIGH",
  critical: "严重风险 · CRITICAL",
};

const attackPlanBasisLabels: Record<AttackPlanBasisType, string> = {
  resource_owner_scope: "资源归属匹配",
  tool_owner_scope: "工具归属匹配",
  source_sink: "来源到数据去向",
  tool_record_limit: "工具记录数上限",
};

const targetKindLabels: Record<AttackPlanTargetKind, string> = {
  knowledge_document: "知识文档",
  customer_record: "客户记录",
  external_sink: "外部数据去向",
  customer_export: "客户数据导出",
};

const attackerTypeLabels: Record<AttackerType, string> = {
  outside_in: "外部不可信内容",
  inside_out: "内部合法身份滥用",
};

const replayAttempts = computed(() => [
  {
    key: "before",
    label: "修复前 · BEFORE · 漏洞配置",
    attempt: props.report.replay.before,
  },
  {
    key: "after",
    label: "修复后 · AFTER · 修复配置",
    attempt: props.report.replay.after,
  },
]);

function eventTypeLabel(type: TraceEventType): string {
  return eventLabels[type] ?? type;
}

function eventTone(type: TraceEventType): "primary" | "success" | "warning" | "danger" | "info" {
  switch (type) {
    case "source":
    case "retrieval":
      return "primary";
    case "authorization":
      return "warning";
    case "tool_call":
    case "sink":
      return "danger";
    case "tool_result":
    case "model_response":
      return "success";
    default:
      return "info";
  }
}

function traceEvents(attempt: ReplayAttempt): TraceEvent[] {
  return [...attempt.traceEvents].sort((left, right) => left.sequence - right.sequence);
}

function hasDetails(event: TraceEvent): boolean {
  return Object.keys(event.details).length > 0;
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2) ?? "{}";
}

type TraceEvidenceRow = {
  label: string;
  value: string;
};

type TraceEvidenceSummary = {
  flow: string;
  sourceTrustLevels: string[];
  resourceIds: string[];
  resourceLabels: string[];
  destinations: string[];
  external: string[];
  approvals: string[];
  recordCounts: string[];
  maxRecords: string[];
  ruleIds: string[];
};

const traceEvidenceFields: ReadonlyArray<{ key: string; label: string }> = [
  { key: "trustLevel", label: "来源可信度" },
  { key: "sourceTrustLevels", label: "来源可信等级" },
  { key: "resourceLabels", label: "资源标签" },
  { key: "resourceIds", label: "资源 ID" },
  { key: "documentIds", label: "文档 ID" },
  { key: "toolName", label: "工具" },
  { key: "action", label: "动作" },
  { key: "arguments", label: "工具参数" },
  { key: "data", label: "工具结果" },
  { key: "sinkType", label: "流向类型" },
  { key: "sinkId", label: "流向 ID" },
  { key: "destination", label: "目标地址" },
  { key: "external", label: "是否外部" },
  { key: "approvalRequired", label: "是否需要审批" },
  { key: "approved", label: "是否审批" },
  { key: "approvalGranted", label: "审批结果" },
  { key: "recordCount", label: "记录数量" },
  { key: "maxRecords", label: "数量上限" },
  { key: "ruleId", label: "规则 ID" },
  { key: "authorizationDecision", label: "权限结论" },
  { key: "decision", label: "判断结果" },
  { key: "reason", label: "判断理由" },
  { key: "beforeValue", label: "修复前" },
  { key: "afterValue", label: "修复后" },
];

function detailValueText(value: unknown): string | null {
  if (typeof value === "string") {
    return value.trim() || null;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value !== null && typeof value === "object") {
    const serialized = JSON.stringify(value);
    return serialized && serialized !== "{}" ? serialized : null;
  }
  return null;
}

function detailValueParts(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => detailValueParts(item));
  }

  const text = detailValueText(value);
  return text ? [text] : [];
}

function uniqueEvidenceValues(values: string[]): string[] {
  return values.filter((value, index) => values.indexOf(value) === index);
}

function collectDetailValues(events: TraceEvent[], keys: string[]): string[] {
  return uniqueEvidenceValues(
    events.flatMap((event) =>
      keys.flatMap((key) => detailValueParts(event.details[key])),
    ),
  );
}

function endpointText(
  details: Record<string, unknown>,
  typeKey: "sourceType" | "sinkType",
  idKey: "sourceId" | "sinkId",
): string | null {
  const type = detailValueText(details[typeKey]);
  const id = detailValueText(details[idKey]);
  return type && id ? `${type}/${id}` : null;
}

function traceEvidenceRows(event: TraceEvent): TraceEvidenceRow[] {
  return traceEvidenceFields.flatMap(({ key, label }) => {
    const value = detailValueText(event.details[key]);
    return value ? [{ label, value }] : [];
  });
}

function traceEvidenceSummary(events: TraceEvent[]): TraceEvidenceSummary {
  const sourceTrustLevels = collectDetailValues(events, ["sourceTrustLevels", "trustLevel"]);
  const destinations = collectDetailValues(events, ["destination"]);
  const sinkEndpoints = uniqueEvidenceValues(
    events
      .filter((event) => event.type === "sink")
      .map((event) => endpointText(event.details, "sinkType", "sinkId"))
      .filter((value): value is string => value !== null),
  );
  const sourceEndpoints = uniqueEvidenceValues(
    events
      .filter((event) => event.type === "source")
      .map((event) => endpointText(event.details, "sourceType", "sourceId"))
      .filter((value): value is string => value !== null),
  );

  return {
    flow: `${sourceEndpoints.join(" / ") || "来源"} → ${
      sinkEndpoints.join(" / ") || destinations.join(" / ") || "数据去向"
    }`,
    sourceTrustLevels,
    resourceIds: collectDetailValues(events, ["resourceIds", "documentIds"]),
    resourceLabels: collectDetailValues(events, ["resourceLabels"]),
    destinations,
    external: collectDetailValues(events, ["external"]),
    approvals: collectDetailValues(events, [
      "approvalRequired",
      "approved",
      "approvalGranted",
    ]),
    recordCounts: collectDetailValues(events, ["recordCount"]),
    maxRecords: collectDetailValues(events, ["maxRecords"]),
    ruleIds: collectDetailValues(events, ["ruleId"]),
  };
}

function traceEvidenceSummaryRows(events: TraceEvent[]): TraceEvidenceRow[] {
  const summary = traceEvidenceSummary(events);
  const recordValues =
    summary.recordCounts.length > 0 || summary.maxRecords.length > 0
      ? [`${summary.recordCounts.join(" · ") || "—"} / ${summary.maxRecords.join(" · ") || "—"}`]
      : [];
  const fields: Array<{ label: string; values: string[] }> = [
    { label: "来源可信等级", values: summary.sourceTrustLevels },
    { label: "资源 ID", values: summary.resourceIds },
    { label: "资源标签", values: summary.resourceLabels },
    { label: "目标地址", values: summary.destinations },
    { label: "是否外部", values: summary.external },
    { label: "审批", values: summary.approvals },
    { label: "记录数（实际 / 上限）", values: recordValues },
    { label: "规则 ID", values: summary.ruleIds },
  ];
  return fields.flatMap(({ label, values }) =>
    values.length > 0 ? [{ label, value: values.join(" · ") }] : [],
  );
}

function findingCategoryLabel(category: Finding["category"]): string {
  return findingCategoryLabels[category] ?? category;
}

function findingSeverityLabel(severity: Finding["severity"]): string {
  return findingSeverityLabels[severity] ?? severity;
}

function findingRuleLabel(finding: Finding): string {
  return finding.ruleId ?? "默认拒绝 · default deny";
}

function evaluationStatusLabel(status: ReplayAttempt["evaluation"]["status"]): string {
  return status === "passed" ? "通过 · PASSED" : "未通过 · FAILED";
}

function evaluationStatusType(
  status: ReplayAttempt["evaluation"]["status"],
): "success" | "danger" {
  return status === "passed" ? "success" : "danger";
}

function executionStatusLabel(status: ReplayAttempt["executionStatus"]): string {
  return status === "completed" ? "已完成 · COMPLETED" : "已阻断 · BLOCKED";
}

function executionStatusType(
  status: ReplayAttempt["executionStatus"],
): "success" | "warning" {
  return status === "completed" ? "success" : "warning";
}

function booleanLabel(value: boolean): string {
  return value ? "是 · true" : "否 · false";
}

function formatGeneratedAt(generatedAt: string): string {
  const date = new Date(generatedAt);
  if (Number.isNaN(date.getTime())) {
    return generatedAt;
  }

  return date.toLocaleString("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function downloadMarkdown(): void {
  const blob = new Blob([props.report.markdown], {
    type: "text/markdown;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${props.report.id}.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <el-card class="attack-chain-report-card" shadow="never">
    <div class="report-header">
      <div>
        <p class="report-kicker">攻击链报告</p>
        <h2>{{ props.report.title }}</h2>
        <p class="report-meta">
          <code>{{ props.report.id }}</code>
          <span>生成于 {{ formatGeneratedAt(props.report.generatedAt) }}</span>
        </p>
      </div>
      <div class="report-header-actions">
        <el-tag
          :type="props.report.replay.status === 'passed' ? 'success' : 'danger'"
          effect="plain"
        >
          {{ props.report.replay.status === "passed" ? "Replay 通过 · PASSED" : "Replay 未通过 · FAILED" }}
        </el-tag>
        <el-button class="report-download-button" type="primary" @click="downloadMarkdown">
          下载报告
        </el-button>
      </div>
    </div>

    <div class="report-executive-summary">
      <span class="report-label">结论摘要</span>
      <p>{{ props.report.executiveSummary }}</p>
    </div>

    <div class="report-plan-grid">
      <div>
        <span class="report-label">攻击计划</span>
        <strong>{{ props.report.replay.plan.name }}</strong>
        <code>{{ props.report.replay.plan.id }}</code>
      </div>
      <div>
        <span class="report-label">操作人 / 视角</span>
        <code>{{ props.report.replay.plan.actorId }}</code>
        <span>{{ attackerTypeLabels[props.report.replay.plan.attackerType] ?? props.report.replay.plan.attackerType }}</span>
      </div>
      <div>
        <span class="report-label">规则依据</span>
        <code>{{ props.report.replay.plan.basisRuleId }}</code>
        <span>{{ attackPlanBasisLabels[props.report.replay.plan.basisType] }}</span>
      </div>
      <div>
        <span class="report-label">目标</span>
        <code>{{ props.report.replay.plan.targetId }}</code>
        <span>{{ targetKindLabels[props.report.replay.plan.targetKind] ?? props.report.replay.plan.targetKind }}</span>
      </div>
    </div>

    <div class="report-remediation">
      <div>
        <span class="report-label">修复参考 · 模拟配置</span>
        <strong>{{ props.report.replay.remediation.title }}</strong>
        <p>{{ props.report.replay.remediation.summary }}</p>
        <p class="report-remediation-advisory" data-testid="report-remediation-advisory">
          <strong>仅供参考：</strong>该控制项来自当前 Security Contract 与本次 Trace，并只在内置 secure Profile 中完成模拟复测。它不是企业系统根因结论，不会修改生产配置，落地前仍需人工核查和变更审批。
        </p>
      </div>
      <div class="report-remediation-change">
        <code>{{ props.report.replay.remediation.configurationPath }}</code>
        <span>
          模拟前 {{ booleanLabel(props.report.replay.remediation.beforeValue) }}
          →
          模拟后 {{ booleanLabel(props.report.replay.remediation.afterValue) }}
        </span>
      </div>
    </div>

    <div class="report-attempt-grid">
      <article
        v-for="replayAttempt in replayAttempts"
        :key="replayAttempt.key"
        class="report-attempt"
      >
        <div class="report-attempt-header">
          <div>
            <p class="report-attempt-label">{{ replayAttempt.label }}</p>
            <p class="report-attempt-profile">
              配置 Profile <code>{{ replayAttempt.attempt.profileId }}</code>
            </p>
          </div>
          <el-tag
            :type="executionStatusType(replayAttempt.attempt.executionStatus)"
            effect="plain"
            size="small"
          >
            {{ executionStatusLabel(replayAttempt.attempt.executionStatus) }}
          </el-tag>
        </div>

        <dl class="report-attempt-facts">
          <div>
            <dt>执行</dt>
            <dd>{{ executionStatusLabel(replayAttempt.attempt.executionStatus) }}</dd>
          </div>
          <div>
            <dt>结论</dt>
            <dd>
              <el-tag
                :type="evaluationStatusType(replayAttempt.attempt.evaluation.status)"
                effect="plain"
                size="small"
              >
                {{ evaluationStatusLabel(replayAttempt.attempt.evaluation.status) }}
              </el-tag>
            </dd>
          </div>
          <div>
            <dt>风险发现</dt>
            <dd>{{ replayAttempt.attempt.evaluation.findings.length }}</dd>
          </div>
        </dl>

        <div v-if="replayAttempt.attempt.traceEvents.length > 0" class="report-trace">
          <div class="report-trace-heading">
            <p class="report-subheading">攻击路径</p>
            <code>{{ traceEvidenceSummary(replayAttempt.attempt.traceEvents).flow }}</code>
          </div>
          <div class="report-finding-evidence">
            <template
              v-for="row in traceEvidenceSummaryRows(replayAttempt.attempt.traceEvents)"
              :key="`${replayAttempt.key}-summary-${row.label}`"
            >
              <span>{{ row.label }}</span>
              <code>{{ row.value }}</code>
            </template>
          </div>
        </div>

        <div v-if="replayAttempt.attempt.queryResult" class="report-answer">
          <span class="report-label">模型回答</span>
          <p>{{ replayAttempt.attempt.queryResult.answer }}</p>
        </div>
        <div v-else class="report-blocked-answer">
          <code>queryResult = null</code>
          <p>执行在授权边界被阻断，没有模型回答。</p>
          <span v-if="replayAttempt.attempt.blockedReason">
            阻断原因：{{ replayAttempt.attempt.blockedReason }}
          </span>
        </div>

        <div class="report-findings">
          <p class="report-subheading">发现的问题 Finding</p>
          <div v-if="replayAttempt.attempt.evaluation.findings.length > 0" class="report-finding-list">
            <article
              v-for="finding in replayAttempt.attempt.evaluation.findings"
              :key="finding.id"
              class="report-finding"
            >
              <div class="report-finding-topline">
                <el-tag type="danger" effect="plain" size="small">{{ findingSeverityLabel(finding.severity) }}</el-tag>
                <span class="report-finding-category">{{ findingCategoryLabel(finding.category) }}</span>
                <code>{{ finding.category }}</code>
              </div>
              <strong>{{ finding.title }}</strong>
              <p>{{ finding.summary }}</p>
              <div class="report-finding-evidence">
                <span>命中规则</span>
                <code>{{ findingRuleLabel(finding) }}</code>
                <span>证据序号</span>
                <code>{{ finding.evidenceSequences.join(" → ") }}</code>
              </div>
            </article>
          </div>
          <p v-else class="report-no-findings">暂未发现风险 Finding</p>
        </div>

        <details class="report-trace report-trace-details">
          <summary class="report-trace-heading">
            <p class="report-subheading">完整执行记录 Trace</p>
            <code>{{ replayAttempt.attempt.traceEvents.length }} 条</code>
          </summary>
          <ol v-if="traceEvents(replayAttempt.attempt).length > 0" class="report-trace-list">
            <li
              v-for="event in traceEvents(replayAttempt.attempt)"
              :key="`${replayAttempt.key}-${event.sequence}-${event.type}-${event.occurredAt}`"
              class="report-trace-node"
            >
              <div class="report-trace-node-header">
                <span class="report-trace-sequence">#{{ event.sequence }}</span>
                <el-tag :type="eventTone(event.type)" effect="plain" size="small">
                  {{ eventTypeLabel(event.type) }}
                </el-tag>
                <code>{{ event.type }}</code>
              </div>
              <p>{{ event.summary }}</p>
              <div v-if="traceEvidenceRows(event).length > 0" class="report-finding-evidence">
                <template v-for="row in traceEvidenceRows(event)" :key="`${replayAttempt.key}-${event.sequence}-${row.label}`">
                  <span>{{ row.label }}</span>
                  <code>{{ row.value }}</code>
                </template>
              </div>
              <details v-if="hasDetails(event)" class="report-event-details">
                <summary>查看原始事件详情</summary>
                <pre>{{ formatDetails(event.details) }}</pre>
              </details>
            </li>
          </ol>
          <p v-else class="report-trace-empty">暂无 Trace 记录</p>
        </details>
      </article>
    </div>
  </el-card>
</template>

<style scoped>
.attack-chain-report-card {
  margin-top: 16px;
  overflow: hidden;
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 15px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.15);
}

.attack-chain-report-card :deep(.el-card__body) {
  padding: 26px;
}

.report-header,
.report-attempt-header,
.report-trace-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.report-kicker,
.report-label,
.report-meta,
.report-executive-summary p,
.report-remediation p,
.report-attempt-label,
.report-attempt-profile,
.report-answer p,
.report-blocked-answer p,
.report-blocked-answer span,
.report-subheading,
.report-no-findings,
.report-trace-empty,
.report-trace-node p {
  margin: 0;
}

.report-kicker,
.report-label,
.report-subheading {
  color: var(--accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.report-header h2 {
  margin: 7px 0 0;
  color: var(--ink-strong);
  font-size: 20px;
  font-weight: 600;
  line-height: 1.35;
}

.report-header-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 10px;
}

.report-download-button.el-button {
  height: 35px;
  margin: 0;
  color: #061a1a;
  background: var(--accent);
  border: 0;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 700;
}

.report-download-button.el-button:hover {
  color: #061a1a;
  background: #94f4d9;
}

.report-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.report-meta code,
.report-plan-grid code,
.report-remediation-change code,
.report-attempt-profile code,
.report-finding code,
.report-trace-heading code,
.report-trace-node-header code {
  color: var(--accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
}

.report-executive-summary {
  margin-top: 20px;
  padding: 15px 17px;
  background: var(--accent-wash);
  border: 1px solid rgba(110, 231, 197, 0.2);
  border-radius: 8px;
}

.report-executive-summary p {
  margin-top: 8px;
  color: var(--ink-strong);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.report-plan-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 15px;
}

.report-plan-grid > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
  padding: 12px 13px;
  background: rgba(6, 14, 26, 0.42);
  border: 1px solid var(--line);
  border-radius: 8px;
}

.report-plan-grid strong {
  color: var(--ink-strong);
  font-size: 12px;
  line-height: 1.4;
}

.report-plan-grid span:not(.report-label) {
  color: var(--ink-muted);
  font-size: 10px;
  line-height: 1.4;
}

.report-remediation {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-top: 15px;
  padding: 15px 17px;
  background: rgba(251, 146, 60, 0.08);
  border: 1px solid rgba(251, 146, 60, 0.2);
  border-radius: 8px;
}

.report-remediation > div:first-child {
  min-width: 0;
}

.report-remediation strong {
  display: block;
  margin-top: 7px;
  color: var(--ink-strong);
  font-size: 13px;
}

.report-remediation p {
  margin-top: 6px;
  color: var(--ink-muted);
  font-size: 11px;
  line-height: 1.55;
}

.report-remediation .report-remediation-advisory {
  margin-top: 10px;
  padding: 10px 12px;
  border-left: 3px solid #d99a20;
  border-radius: 0 8px 8px 0;
  background: rgba(217, 154, 32, 0.1);
}

.report-remediation-change {
  display: flex;
  min-width: 245px;
  flex-shrink: 0;
  flex-direction: column;
  gap: 7px;
  text-align: right;
}

.report-remediation-change span {
  color: #fed7aa;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
}

.report-attempt-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 18px;
}

.report-attempt {
  min-width: 0;
  padding: 17px;
  background: rgba(6, 14, 26, 0.42);
  border: 1px solid var(--line);
  border-radius: 9px;
}

.report-attempt:last-child {
  border-color: rgba(110, 231, 197, 0.25);
}

.report-attempt-header {
  padding-bottom: 13px;
  border-bottom: 1px solid var(--line);
}

.report-attempt-label {
  color: var(--ink-strong);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.report-attempt-profile {
  margin-top: 6px;
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.report-attempt-facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 15px 0 0;
}

.report-attempt-facts div {
  min-width: 0;
}

.report-attempt-facts dt {
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.report-attempt-facts dd {
  margin: 6px 0 0;
  color: var(--ink);
  font-size: 10px;
  line-height: 1.4;
}

.report-attempt-facts dd :deep(.el-tag) {
  max-width: 100%;
  height: auto;
  white-space: normal;
}

.report-answer,
.report-blocked-answer {
  margin-top: 15px;
  padding: 12px 13px;
  border-radius: 7px;
}

.report-answer {
  background: rgba(110, 231, 197, 0.07);
  border: 1px solid rgba(110, 231, 197, 0.16);
}

.report-blocked-answer {
  background: rgba(251, 146, 60, 0.08);
  border: 1px solid rgba(251, 146, 60, 0.2);
}

.report-answer p,
.report-blocked-answer p {
  margin-top: 7px;
  color: var(--ink);
  font-size: 11px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.report-blocked-answer > code,
.report-blocked-answer span {
  color: #fdba74;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.report-blocked-answer span {
  display: block;
  margin-top: 7px;
}

.report-findings {
  margin-top: 16px;
}

.report-finding-list {
  display: grid;
  gap: 9px;
  margin-top: 9px;
}

.report-finding {
  padding: 12px 13px;
  background: rgba(127, 29, 29, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.2);
  border-left: 2px solid #f87171;
  border-radius: 7px;
}

.report-finding-topline {
  display: flex;
  align-items: center;
  gap: 8px;
}

.report-finding > strong {
  display: block;
  margin-top: 8px;
  color: var(--ink-strong);
  font-size: 11px;
  line-height: 1.45;
}

.report-finding > p {
  margin: 5px 0 0;
  color: var(--ink-muted);
  font-size: 10px;
  line-height: 1.55;
}

.report-finding-evidence {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 5px 9px;
  align-items: baseline;
  margin-top: 9px;
  padding-top: 8px;
  color: var(--ink-faint);
  border-top: 1px solid var(--line);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.report-finding-evidence code {
  color: #a8b8cc;
}

.report-no-findings,
.report-trace-empty {
  margin-top: 9px;
  color: var(--ink-faint);
  font-size: 10px;
}

.report-trace {
  margin-top: 17px;
  padding-top: 15px;
  border-top: 1px solid var(--line);
}

.report-trace-heading {
  align-items: baseline;
}

.report-trace-heading code {
  color: var(--ink-faint);
}

.report-trace-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.report-trace-node {
  min-width: 0;
  padding: 10px 11px;
  background: rgba(5, 13, 24, 0.45);
  border: 1px solid var(--line);
  border-radius: 7px;
}

.report-trace-node-header {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.report-trace-sequence {
  flex-shrink: 0;
  color: var(--accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.report-trace-node-header code {
  color: var(--ink-faint);
  flex-shrink: 0;
}

.report-trace-node > p {
  margin-top: 7px;
  color: var(--ink);
  font-size: 11px;
  line-height: 1.55;
}

.report-trace-node pre {
  max-width: 100%;
  margin: 8px 0 0;
  padding: 9px 10px;
  overflow-x: auto;
  color: #a8b8cc;
  background: rgba(5, 13, 24, 0.65);
  border: 1px solid var(--line);
  border-radius: 5px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 860px) {
  .report-plan-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .attack-chain-report-card :deep(.el-card__body) {
    padding: 22px;
  }

  .report-header,
  .report-remediation {
    align-items: flex-start;
    flex-direction: column;
  }

  .report-header-actions {
    width: 100%;
    justify-content: space-between;
  }

  .report-download-button.el-button {
    flex: 1;
  }

  .report-plan-grid,
  .report-attempt-grid {
    grid-template-columns: 1fr;
  }

  .report-remediation-change {
    min-width: 0;
    text-align: left;
  }

  .report-attempt-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .report-trace-node-header {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}

/* F-032: reports stay readable on a light surface; risk and remediation keep distinct tones. */
.attack-chain-report-card {
  --report-ink-strong: #132238;
  --report-ink: #28384d;
  --report-muted: #64748b;
  --report-faint: #8a99ad;
  --report-line: #dbe4ef;
  --report-action: #4f7cff;
  --report-risk: #ff5d5d;
  --report-success: #25bfae;
  color: var(--report-ink);
  background: #ffffff;
  border-color: var(--report-line);
  box-shadow: 0 12px 32px rgba(24, 50, 83, 0.07);
}

.attack-chain-report-card :deep(.el-card__body) {
  background: #ffffff;
}

.report-kicker,
.report-label,
.report-subheading {
  color: var(--report-action);
}

.report-header h2,
.report-plan-grid strong,
.report-remediation strong,
.report-attempt-label,
.report-finding > strong {
  color: var(--report-ink-strong);
}

.report-meta,
.report-plan-grid span:not(.report-label),
.report-remediation p,
.report-attempt-profile,
.report-answer p,
.report-blocked-answer p,
.report-no-findings,
.report-trace-empty,
.report-trace-node > p {
  color: var(--report-muted);
}

.report-header-actions .report-download-button.el-button {
  color: #315fd7;
  background: #ffffff;
  border: 1px solid #b7c8ff;
  box-shadow: none;
}

.report-header-actions .report-download-button.el-button:hover {
  color: #244cb4;
  background: #f1f4ff;
}

.report-executive-summary {
  background: #0b2340;
  border-color: #0b2340;
  box-shadow: 0 8px 20px rgba(11, 35, 64, 0.12);
}

.report-executive-summary .report-label {
  color: #8feadd;
}

.report-executive-summary p {
  color: #f4f8ff;
}

.report-plan-grid > div,
.report-attempt {
  background: #f8fafc;
  border-color: var(--report-line);
}

.report-plan-grid code,
.report-remediation-change code,
.report-attempt-profile code,
.report-finding code,
.report-trace-heading code,
.report-trace-node-header code {
  color: #4169d8;
}

.report-remediation {
  background: #fff8e9;
  border-color: #f0ce8f;
}

.report-remediation-change span {
  color: #94600f;
}

.report-attempt:first-child {
  border-color: #ffcaca;
  box-shadow: 0 8px 20px rgba(255, 93, 93, 0.05);
}

.report-attempt:last-child {
  border-color: #9be0d7;
  box-shadow: 0 8px 20px rgba(37, 191, 174, 0.05);
}

.report-attempt-header,
.report-trace {
  border-color: var(--report-line);
}

.report-attempt-facts dt {
  color: var(--report-faint);
}

.report-attempt-facts dd {
  color: var(--report-ink);
}

.report-answer {
  background: #eafaf7;
  border-color: #9be0d7;
}

.report-blocked-answer {
  background: #fff0f0;
  border-color: #ffcaca;
}

.report-blocked-answer > code,
.report-blocked-answer span {
  color: #b52e2e;
}

.report-finding {
  background: #fff5f5;
  border-color: #ffcaca;
  border-left-color: var(--report-risk);
}

.report-finding-evidence {
  color: var(--report-faint);
  border-color: var(--report-line);
}

.report-finding-evidence code {
  color: #4169d8;
}

.report-trace-node {
  background: #ffffff;
  border-color: var(--report-line);
}

.report-trace-sequence {
  color: var(--report-action);
}

.report-trace-node pre {
  color: #dce8f8;
  background: #102c4f;
  border-color: #254a73;
}

/* F-061: surface the decision first; leave IDs and raw JSON in code styling. */
.report-kicker,
.report-label,
.report-subheading {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.report-meta {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.report-executive-summary p,
.report-remediation p,
.report-answer p,
.report-blocked-answer p,
.report-finding > p,
.report-trace-node > p {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.report-executive-summary p {
  font-size: var(--type-body-size, 15px);
  line-height: var(--type-body-leading, 1.62);
}

.report-plan-grid strong,
.report-remediation strong,
.report-finding > strong {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-size, 15px);
  line-height: var(--type-heading-leading, 1.22);
}

.report-plan-grid span:not(.report-label),
.report-remediation-change span {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.report-attempt-label {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
  letter-spacing: normal;
  line-height: var(--type-body-small-leading, 1.55);
}

.report-attempt-profile {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
}

.report-attempt-facts dt,
.report-finding-evidence > span {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.report-attempt-facts dd {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.report-blocked-answer span,
.report-no-findings,
.report-trace-empty {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.report-finding-category {
  color: var(--report-ink, #28384d);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.status-pill,
.audit-status {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.report-finding-evidence {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.report-trace-sequence {
  font-size: var(--type-label-size, 12px);
}

@media (max-width: 480px) {
  .report-attempt-facts {
    grid-template-columns: 1fr;
  }
}

/* F-063: generated reports use the shared evidence hierarchy while remaining a
 * pure projection of their DTO. */
.attack-chain-report-card {
  margin-top: 26px;
  color: var(--ink);
  background: var(--surface);
  border-color: var(--line);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.attack-chain-report-card :deep(.el-card__body) {
  padding: 0;
  background: var(--surface);
}

.attack-chain-report-card .report-header {
  align-items: flex-end;
  padding: 22px 24px 17px;
  border-bottom: 1px solid var(--line);
}

.attack-chain-report-card .report-kicker,
.attack-chain-report-card .report-label,
.attack-chain-report-card .report-subheading,
.attack-chain-report-card .report-meta,
.attack-chain-report-card .report-attempt-label,
.attack-chain-report-card .report-attempt-profile,
.attack-chain-report-card .report-attempt-facts dt,
.attack-chain-report-card .report-finding-evidence > span {
  color: var(--ink-muted);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.attack-chain-report-card .report-kicker,
.attack-chain-report-card .report-label,
.attack-chain-report-card .report-subheading {
  color: var(--action-blue-strong);
}

.attack-chain-report-card .report-header h2 {
  color: var(--ink-strong);
  font-size: var(--type-section-title-size, 23px);
  line-height: var(--type-heading-leading, 1.22);
}

.attack-chain-report-card .report-meta {
  margin-top: 9px;
}

.attack-chain-report-card .report-meta code,
.attack-chain-report-card .report-plan-grid code,
.attack-chain-report-card .report-remediation-change code,
.attack-chain-report-card .report-attempt-profile code,
.attack-chain-report-card .report-finding code,
.attack-chain-report-card .report-trace-heading code,
.attack-chain-report-card .report-trace-node-header code {
  color: var(--action-blue-strong);
  font-family: var(--font-code, "SFMono-Regular", Consolas, monospace);
  font-size: var(--type-code-size, 13px);
}

.attack-chain-report-card .report-header-actions .report-download-button.el-button {
  min-height: 44px;
  color: var(--action-blue-strong);
  background: var(--surface);
  border: 1px solid var(--line-bright);
  border-radius: var(--radius-control);
  box-shadow: none;
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
}

.attack-chain-report-card .report-executive-summary {
  margin: 0;
  padding: 17px 24px;
  background: #fff7f7;
  border: 0;
  border-left: 4px solid var(--risk-coral);
  border-radius: 0;
  box-shadow: none;
}

.attack-chain-report-card .report-executive-summary .report-label {
  color: var(--risk-coral);
}

.attack-chain-report-card .report-executive-summary p {
  color: var(--ink-strong);
  font-size: var(--type-body-size, 15px);
  line-height: var(--type-body-leading, 1.62);
}

.attack-chain-report-card .report-plan-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  margin: 0;
  padding: 0 8px;
  border-bottom: 1px solid var(--line);
}

.attack-chain-report-card .report-plan-grid > div {
  position: relative;
  min-height: 100px;
  padding: 17px 16px;
  background: #ffffff;
  border: 0;
  border-radius: 0;
}

.attack-chain-report-card .report-plan-grid > div:not(:last-child)::after {
  position: absolute;
  top: 17px;
  right: 0;
  bottom: 17px;
  width: 1px;
  background: var(--line);
  content: "";
}

.attack-chain-report-card .report-plan-grid strong {
  color: var(--ink-strong);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-size, 15px);
  line-height: var(--type-heading-leading, 1.22);
}

.attack-chain-report-card .report-plan-grid span:not(.report-label) {
  color: var(--ink-muted);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.attack-chain-report-card .report-remediation {
  align-items: center;
  margin: 16px 24px 0;
  padding: 15px 16px;
  background: #fff8e9;
  border: 1px solid #f0ce8f;
  border-radius: 7px;
}

.attack-chain-report-card .report-remediation strong {
  color: var(--ink-strong);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.attack-chain-report-card .report-remediation p,
.attack-chain-report-card .report-remediation-change span {
  color: var(--ink-muted);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.attack-chain-report-card .report-remediation .report-remediation-advisory {
  background: #fffdf6;
  border-left-color: #d99a20;
}

.attack-chain-report-card .report-attempt-grid {
  gap: 12px;
  margin: 16px 24px 24px;
}

.attack-chain-report-card .report-attempt {
  padding: 16px;
  background: var(--surface);
  border-color: var(--line);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.attack-chain-report-card .report-attempt:first-child {
  border-top: 3px solid var(--risk-coral);
  border-color: #ffcaca;
  border-top-color: var(--risk-coral);
}

.attack-chain-report-card .report-attempt:last-child {
  border-top: 3px solid var(--evidence-teal);
  border-color: #9be0d7;
  border-top-color: var(--evidence-teal);
}

.attack-chain-report-card .report-attempt-header,
.attack-chain-report-card .report-trace {
  border-color: var(--line);
}

.attack-chain-report-card .report-attempt-facts dd {
  color: var(--ink);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.attack-chain-report-card .report-answer,
.attack-chain-report-card .report-blocked-answer {
  padding: 12px 13px;
  border-radius: 6px;
}

.attack-chain-report-card .report-answer {
  background: #eafaf7;
  border-color: #9be0d7;
}

.attack-chain-report-card .report-blocked-answer {
  background: #fff0f0;
  border-color: #ffcaca;
}

.attack-chain-report-card .report-answer p,
.attack-chain-report-card .report-blocked-answer p,
.attack-chain-report-card .report-finding > p,
.attack-chain-report-card .report-trace-node > p {
  color: var(--ink);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.attack-chain-report-card .report-findings {
  margin-top: 16px;
}

.attack-chain-report-card .report-finding {
  padding: 12px 13px;
  background: #fff5f5;
  border-color: #ffcaca;
  border-left: 3px solid var(--risk-coral);
  border-radius: 6px;
}

.attack-chain-report-card .report-finding > strong {
  color: var(--ink-strong);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.attack-chain-report-card .report-finding-category {
  color: var(--ink-muted);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.attack-chain-report-card .report-finding-evidence {
  color: var(--ink-faint);
  border-color: var(--line);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.attack-chain-report-card .report-trace-node {
  padding: 10px 11px;
  background: #ffffff;
  border-color: var(--line);
  border-radius: 6px;
}

.attack-chain-report-card .report-trace-sequence {
  color: var(--action-blue-strong);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
}

.attack-chain-report-card .report-trace-node pre {
  color: #dce8f8;
  background: #102c4f;
  border-color: #254a73;
}

/* F-063 visual pass 2: keep generated reports useful for a judge at first
 * glance while preserving every raw Trace/event payload behind details. */
.attack-chain-report-card .report-trace-details > summary {
  position: relative;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding-left: 16px;
  cursor: pointer;
  list-style: none;
}

.attack-chain-report-card .report-trace-details > summary::-webkit-details-marker {
  display: none;
}

.attack-chain-report-card .report-trace-details > summary::before {
  position: absolute;
  top: 0;
  left: 0;
  color: var(--action-blue-strong);
  content: "▸";
}

.attack-chain-report-card .report-trace-details[open] > summary::before {
  content: "▾";
}

.attack-chain-report-card .report-trace-details[open] > summary {
  margin-bottom: 10px;
}

.attack-chain-report-card .report-event-details {
  margin-top: 9px;
}

.attack-chain-report-card .report-event-details > summary {
  color: var(--action-blue-strong);
  cursor: pointer;
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.attack-chain-report-card .report-event-details > summary::-webkit-details-marker {
  color: var(--action-blue-strong);
}

.attack-chain-report-card .report-executive-summary p,
.attack-chain-report-card .report-answer p,
.attack-chain-report-card .report-blocked-answer p,
.attack-chain-report-card .report-finding > p,
.attack-chain-report-card .report-trace-node > p {
  font-size: max(16px, var(--type-body-size, 16px));
  line-height: var(--type-body-leading, 1.62);
}

.attack-chain-report-card .report-plan-grid span:not(.report-label),
.attack-chain-report-card .report-remediation p,
.attack-chain-report-card .report-remediation-change span,
.attack-chain-report-card .report-attempt-facts dd {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.attack-chain-report-card .report-plan-grid strong,
.attack-chain-report-card .report-finding > strong {
  font-size: max(16px, var(--type-body-size, 16px));
  line-height: var(--type-body-leading, 1.62);
}

.attack-chain-report-card .report-meta code,
.attack-chain-report-card .report-plan-grid code,
.attack-chain-report-card .report-remediation-change code,
.attack-chain-report-card .report-attempt-profile code,
.attack-chain-report-card .report-finding code,
.attack-chain-report-card .report-trace-heading code,
.attack-chain-report-card .report-trace-node-header code,
.attack-chain-report-card .report-trace-node pre {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}

@media (max-width: 760px) {
  .attack-chain-report-card :deep(.el-card__body) {
    padding: 0;
  }

  .attack-chain-report-card .report-header,
  .attack-chain-report-card .report-executive-summary {
    padding-left: 16px;
    padding-right: 16px;
  }

  .attack-chain-report-card .report-plan-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 0;
  }

  .attack-chain-report-card .report-plan-grid > div {
    min-height: 92px;
    padding: 13px 14px;
  }

  .attack-chain-report-card .report-plan-grid > div:nth-child(2)::after {
    display: none;
  }

  .attack-chain-report-card .report-plan-grid > div:nth-child(-n + 2) {
    border-bottom: 1px solid var(--line);
  }

  .attack-chain-report-card .report-remediation {
    margin-left: 16px;
    margin-right: 16px;
  }

  .attack-chain-report-card .report-attempt-grid {
    margin-left: 16px;
    margin-right: 16px;
    margin-bottom: 16px;
  }
}

@media (max-width: 480px) {
  .attack-chain-report-card .report-plan-grid {
    grid-template-columns: 1fr;
  }

  .attack-chain-report-card .report-plan-grid > div,
  .attack-chain-report-card .report-plan-grid > div:nth-child(-n + 2) {
    min-height: 0;
    border-bottom: 1px solid var(--line);
  }

  .attack-chain-report-card .report-plan-grid > div:not(:last-child)::after {
    display: none;
  }

  .attack-chain-report-card .report-plan-grid > div:last-child {
    border-bottom: 0;
  }
}

/* F-063 visual pass 3: keep report disclosures discoverable and touch-safe;
 * raw Trace remains available without competing with the report conclusion. */
.attack-chain-report-card .report-trace-details > summary,
.attack-chain-report-card .report-event-details > summary {
  box-sizing: border-box;
  min-height: 44px;
  padding: 10px 12px 10px 32px;
  color: var(--action-blue-strong);
  border-radius: var(--radius-control, 8px);
  cursor: pointer;
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
  list-style: none;
  overflow-wrap: anywhere;
}

.attack-chain-report-card .report-trace-details > summary::-webkit-details-marker,
.attack-chain-report-card .report-event-details > summary::-webkit-details-marker {
  display: none;
}

.attack-chain-report-card .report-trace-details > summary::before,
.attack-chain-report-card .report-event-details > summary::before {
  position: absolute;
  margin-left: -20px;
  color: var(--action-blue-strong);
  content: "▸";
  font-size: 16px;
  line-height: 1;
}

.attack-chain-report-card .report-trace-details > summary,
.attack-chain-report-card .report-event-details > summary {
  position: relative;
}

.attack-chain-report-card .report-trace-details[open] > summary::before,
.attack-chain-report-card .report-event-details[open] > summary::before {
  content: "▾";
}

.attack-chain-report-card .report-trace-details > summary:hover,
.attack-chain-report-card .report-event-details > summary:hover {
  background: var(--surface-raised);
}

.attack-chain-report-card .report-trace-details > summary:focus-visible,
.attack-chain-report-card .report-event-details > summary:focus-visible {
  outline: 2px solid var(--action-blue-strong);
  outline-offset: 2px;
}

.attack-chain-report-card .report-meta code,
.attack-chain-report-card .report-plan-grid code,
.attack-chain-report-card .report-remediation-change code,
.attack-chain-report-card .report-attempt-profile code,
.attack-chain-report-card .report-finding code,
.attack-chain-report-card .report-trace-heading code,
.attack-chain-report-card .report-trace-node-header code {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.attack-chain-report-card .report-trace-node pre {
  max-width: 100%;
  overflow-x: auto;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
