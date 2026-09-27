<script setup lang="ts">
import { computed } from "vue";
import replayAfterConnectedUrl from "../assets/illustrations/replay-after-connected.webp";
import replayBeforeBlockedUrl from "../assets/illustrations/replay-before-blocked.webp";
import UserProblemCard, { type UserProblem } from "./UserProblemCard.vue";
import type {
  AttackPlanTargetKind,
  AttackerType,
  Finding,
  ReplayAttempt,
  ReplayResult,
  TraceEvent,
  TraceEventType,
} from "@agent-audit/contracts";

const props = defineProps<{
  replay: ReplayResult | null;
  loading: boolean;
  error: string;
  errorDetails?: string | null;
  disabled: boolean;
}>();

const emit = defineEmits<{
  (event: "run"): void;
}>();

const replayProblem = computed<UserProblem | null>(() => {
  if (!props.error) {
    return null;
  }

  return {
    stage: "模拟复测",
    title: "模拟复测没有完成",
    reason: "这次复测没有返回完整结果，参考配置尚未得到验证。",
    impact: "当前不能判断风险是否已被控制；原始检查结果不会被覆盖。",
    actionLabel: "再次复测",
    technicalDetails: props.errorDetails || props.error,
  };
});

const eventLabels: Record<TraceEventType, string> = {
  input: "输入",
  source: "内容来源",
  retrieval: "资料检索",
  authorization: "权限判断",
  tool_call: "工具动作",
  tool_result: "工具结果",
  sink: "数据去向",
  model_response: "模型响应",
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

const findingSeverityLabels: Record<Finding["severity"], string> = {
  high: "高危 High",
  critical: "严重 Critical",
};

type BlockedBeforeAction = true | false | null;

type ReplayAttemptFacts = {
  events: TraceEvent[];
  toolResultEvents: TraceEvent[];
  sinkEvents: TraceEvent[];
  externalSinkEvents: TraceEvent[];
  deniedAuthorizationEvents: TraceEvent[];
  actionEvents: TraceEvent[];
  blockedBeforeAction: BlockedBeforeAction;
  blockedBeforeActionEvidence: string;
};

type ReplayAttemptEntry = {
  key: "before" | "after";
  label: string;
  caption: string;
  attempt: ReplayAttempt;
  facts: ReplayAttemptFacts;
};

const replayAttemptEntries = computed<ReplayAttemptEntry[]>(() => {
  if (!props.replay) {
    return [];
  }

  return [
    {
      key: "before",
      label: "BEFORE",
      caption: "漏洞配置",
      attempt: props.replay.before,
      facts: replayAttemptFacts(props.replay.before),
    },
    {
      key: "after",
      label: "AFTER",
      caption: "参考配置模拟复测",
      attempt: props.replay.after,
      facts: replayAttemptFacts(props.replay.after),
    },
  ];
});

function traceEvents(attempt: ReplayAttempt): TraceEvent[] {
  return [...attempt.traceEvents].sort((left, right) => left.sequence - right.sequence);
}

function isDeniedAuthorization(event: TraceEvent): boolean {
  if (event.type !== "authorization") {
    return false;
  }

  return event.details.decision === "denied" || event.details.authorizationDecision === "denied";
}

function isExternalSink(event: TraceEvent): boolean {
  return event.type === "sink" && event.details.external === true;
}

function replayAttemptFacts(attempt: ReplayAttempt): ReplayAttemptFacts {
  const events = traceEvents(attempt);
  const toolResultEvents = events.filter((event) => event.type === "tool_result");
  const sinkEvents = events.filter((event) => event.type === "sink");
  const externalSinkEvents = events.filter(isExternalSink);
  const deniedAuthorizationEvents = events.filter(isDeniedAuthorization);
  const actionEvents = events.filter(
    (event) => event.type === "tool_call" || isExternalSink(event),
  );
  const reachedAction = actionEvents.length > 0 || toolResultEvents.length > 0;
  const blockedBeforeAction: BlockedBeforeAction =
    deniedAuthorizationEvents.length > 0 ? !reachedAction : null;

  let blockedBeforeActionEvidence = "Trace 未出现 denied 授权，暂不标记为动作前阻断。";
  if (blockedBeforeAction === true) {
    const deniedSummary = deniedAuthorizationEvents[0]?.summary ?? "授权被拒绝";
    blockedBeforeActionEvidence =
      `Trace 出现“${deniedSummary}”，且没有 tool_call、tool_result 或 external Sink。`;
  } else if (blockedBeforeAction === false) {
    const actionType = actionEvents[0]?.type ?? "tool_result";
    blockedBeforeActionEvidence =
      `Trace 已出现 ${actionType}，动作已经发生。`;
  }

  return {
    events,
    toolResultEvents,
    sinkEvents,
    externalSinkEvents,
    deniedAuthorizationEvents,
    actionEvents,
    blockedBeforeAction,
    blockedBeforeActionEvidence,
  };
}

function eventTypeLabel(type: TraceEventType): string {
  return eventLabels[type] ?? type;
}

function eventTone(type: TraceEventType): string {
  switch (type) {
    case "source":
    case "retrieval":
      return "is-primary";
    case "authorization":
      return "is-warning";
    case "tool_call":
    case "sink":
      return "is-danger";
    case "tool_result":
    case "model_response":
      return "is-success";
    default:
      return "is-info";
  }
}

function hasDetails(event: TraceEvent): boolean {
  return Object.keys(event.details).length > 0;
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2) ?? "{}";
}

function executionStatusLabel(status: ReplayAttempt["executionStatus"]): string {
  return status === "completed" ? "COMPLETED · 已完成" : "BLOCKED · 已阻断";
}

function evaluationStatusLabel(status: ReplayAttempt["evaluation"]["status"]): string {
  return status === "passed" ? "PASSED · 通过" : "FAILED · 失败";
}

function replayStatusLabel(status: ReplayResult["status"]): string {
  return status === "passed"
    ? "模拟复测通过 · REPLAY PASSED"
    : "模拟复测仍失败 · REPLAY FAILED";
}

function statusClass(status: "passed" | "failed" | "completed" | "blocked"): string {
  if (status === "passed" || status === "completed") {
    return "is-success";
  }
  if (status === "blocked") {
    return "is-warning";
  }
  return "is-danger";
}

function booleanLabel(value: boolean): string {
  return value ? "true · 开启" : "false · 关闭";
}

function actualEventLabel(count: number): string {
  return count > 0 ? "真实发生" : "未发生";
}

function blockedBeforeActionLabel(value: BlockedBeforeAction): string {
  if (value === true) {
    return "是 · 动作前阻断";
  }
  if (value === false) {
    return "否 · Trace 已到达动作";
  }
  return "未确认";
}

function blockedBeforeActionTone(value: BlockedBeforeAction): string {
  if (value === true) {
    return "is-warning";
  }
  if (value === false) {
    return "is-danger";
  }
  return "is-info";
}

function actionReachedLabel(facts: ReplayAttemptFacts): string {
  if (facts.actionEvents.length > 0) {
    return "是 · 观察到动作事件";
  }
  if (facts.toolResultEvents.length > 0) {
    return "是 · 观察到工具结果";
  }
  return "未观测到动作事件";
}

function findingSeverityLabel(severity: Finding["severity"]): string {
  return findingSeverityLabels[severity] ?? severity;
}

function findingRuleLabel(finding: Finding): string {
  return finding.ruleId ?? "null · default deny（默认拒绝）";
}

function formatEvidenceSequences(sequences: number[]): string {
  return sequences.length > 0 ? sequences.join(" → ") : "无";
}

function findingCategoryLabel(category: Finding["category"]): string {
  const labels: Record<Finding["category"], string> = {
    resource_authorization_bypass: "资源授权绕过",
    tool_authorization_bypass: "工具授权绕过",
    external_sink_policy_violation: "外部 Sink 策略违规",
    tool_business_policy_violation: "工具业务约束违规",
  };
  return labels[category] ?? category;
}
</script>

<template>
  <section id="guided-replay-section" class="guided-replay-comparison" data-testid="guided-replay-comparison">
    <UserProblemCard
      v-if="replayProblem"
      class="guided-replay-error"
      data-testid="guided-replay-problem"
      :problem="replayProblem"
      action-test-id="guided-replay-problem-action"
      @action="emit('run')"
    />

    <div v-if="props.loading" class="guided-replay-loading" aria-live="polite" aria-busy="true">
      <span class="guided-replay-label">正在复测</span>
      <p>使用同一攻击和参考配置进行模拟复测，等待 Trace。</p>
    </div>

    <template v-if="props.replay">
      <header class="guided-replay-header">
        <div>
          <p class="guided-replay-eyebrow">03 / 修复验证 · Replay</p>
          <h2>同一攻击，按参考配置再测</h2>
          <p class="guided-replay-subtitle">
            操作身份、保护对象和攻击消息不变；只比较真实执行结果。
          </p>
        </div>
        <div class="guided-replay-result" :class="statusClass(props.replay.status)">
          <span>Replay 结论</span>
          <strong>{{ replayStatusLabel(props.replay.status) }}</strong>
        </div>
      </header>

      <figure
        class="guided-replay-illustration"
        :class="{ 'is-passed': props.replay.status === 'passed' }"
        aria-hidden="true"
        data-testid="guided-replay-state-visual"
      >
        <img
          class="replay-state-image replay-state-before"
          :src="replayBeforeBlockedUrl"
          alt=""
          data-testid="guided-replay-before-visual"
          width="1600"
          height="640"
        />
        <img
          class="replay-state-image replay-state-after"
          :src="replayAfterConnectedUrl"
          alt=""
          data-testid="guided-replay-after-visual"
          width="1600"
          height="640"
        />
      </figure>

      <section class="guided-replay-plan" data-testid="guided-replay-plan" aria-labelledby="guided-replay-plan-title">
        <div class="guided-replay-plan-heading">
          <div>
            <span class="guided-replay-label">同一攻击计划</span>
            <h3 id="guided-replay-plan-title">{{ props.replay.plan.name }}</h3>
          </div>
          <code>{{ props.replay.plan.id }}</code>
        </div>
        <div class="guided-replay-plan-facts">
          <div>
            <span>执行身份</span>
            <strong>{{ props.replay.plan.actorId }}</strong>
            <small>{{ attackerTypeLabels[props.replay.plan.attackerType] }}</small>
          </div>
          <div>
            <span>保护对象</span>
            <strong>{{ props.replay.plan.targetId }}</strong>
            <small>{{ targetKindLabels[props.replay.plan.targetKind] }}</small>
          </div>
          <div class="guided-replay-message">
            <span>攻击消息</span>
            <p>{{ props.replay.plan.message }}</p>
          </div>
        </div>
      </section>

      <section class="guided-replay-remediation" data-testid="guided-replay-remediation">
        <div class="guided-replay-remediation-copy">
          <span class="guided-replay-label">修复参考 · 模拟配置</span>
          <strong>{{ props.replay.remediation.title }}</strong>
          <p>{{ props.replay.remediation.summary }}</p>
          <p class="guided-replay-advisory" data-testid="remediation-advisory">
            <strong>仅供参考：</strong>这是根据当前权限规则与本次过程记录给出的控制项参考，并在内置安全配置中模拟复测。软件不会修改企业系统，也不能替代安全、业务和运维人员的根因分析与变更审批。
          </p>
        </div>
        <dl class="guided-replay-configuration">
          <div>
            <dt>configurationPath</dt>
            <dd><code>{{ props.replay.remediation.configurationPath }}</code></dd>
          </div>
          <div>
            <dt>beforeValue</dt>
            <dd><code>{{ booleanLabel(props.replay.remediation.beforeValue) }}</code></dd>
          </div>
          <div>
            <dt>afterValue</dt>
            <dd><code>{{ booleanLabel(props.replay.remediation.afterValue) }}</code></dd>
          </div>
        </dl>
      </section>

      <div class="guided-replay-attempt-grid">
        <article
          v-for="entry in replayAttemptEntries"
          :key="entry.key"
          class="guided-replay-attempt"
          :class="`is-${entry.key}`"
          :data-testid="`guided-replay-${entry.key}`"
        >
          <header class="guided-replay-attempt-header">
            <div>
              <p class="guided-replay-attempt-label">{{ entry.label }} · {{ entry.caption }}</p>
          <p class="guided-replay-profile">参考配置编号 <code>{{ entry.attempt.profileId }}</code></p>
            </div>
            <span class="guided-replay-status" :class="statusClass(entry.attempt.executionStatus)">
              {{ executionStatusLabel(entry.attempt.executionStatus) }}
            </span>
          </header>

          <dl class="guided-replay-attempt-facts">
            <div>
              <dt>执行</dt>
              <dd><code>{{ entry.attempt.executionStatus }}</code><span>{{ executionStatusLabel(entry.attempt.executionStatus) }}</span></dd>
            </div>
            <div>
              <dt>结论</dt>
              <dd :class="statusClass(entry.attempt.evaluation.status)">
                <code>{{ entry.attempt.evaluation.status }}</code><span>{{ evaluationStatusLabel(entry.attempt.evaluation.status) }}</span>
              </dd>
            </div>
            <div>
              <dt>发现风险</dt>
              <dd><strong>{{ entry.attempt.evaluation.findings.length }}</strong><span>条</span></dd>
            </div>
            <div>
              <dt>过程记录</dt>
              <dd><strong>{{ entry.facts.events.length }}</strong><span>条</span></dd>
            </div>
            <div>
              <dt>工具结果</dt>
              <dd :class="entry.facts.toolResultEvents.length > 0 ? 'is-danger' : 'is-muted'">
                <strong>{{ actualEventLabel(entry.facts.toolResultEvents.length) }}</strong>
                <span>{{ entry.facts.toolResultEvents.length }} 条</span>
              </dd>
            </div>
            <div>
              <dt>数据去向</dt>
              <dd :class="entry.facts.sinkEvents.length > 0 ? 'is-danger' : 'is-muted'">
                <strong>{{ actualEventLabel(entry.facts.sinkEvents.length) }}</strong>
                <span>{{ entry.facts.sinkEvents.length }} 条记录</span>
              </dd>
            </div>
            <div>
              <dt>外部数据去向</dt>
              <dd :class="entry.facts.externalSinkEvents.length > 0 ? 'is-danger' : 'is-muted'">
                <strong>{{ actualEventLabel(entry.facts.externalSinkEvents.length) }}</strong>
                <span>{{ entry.facts.externalSinkEvents.length }} 条</span>
              </dd>
            </div>
            <div class="guided-replay-blocked-fact">
              <dt>阻断原因</dt>
              <dd><code>{{ entry.attempt.blockedReason ?? "未阻断" }}</code></dd>
            </div>
          </dl>

          <div class="guided-replay-action-fact" :class="blockedBeforeActionTone(entry.facts.blockedBeforeAction)">
            <div>
              <span class="guided-replay-label">动作边界</span>
              <strong>{{ entry.key === "after" ? `动作前阻断：${blockedBeforeActionLabel(entry.facts.blockedBeforeAction)}` : `动作是否到达：${actionReachedLabel(entry.facts)}` }}</strong>
            </div>
            <p>{{ entry.facts.blockedBeforeActionEvidence }}</p>
          </div>

          <div class="guided-replay-findings">
            <div class="guided-replay-subheading">
              <span>检测到的风险</span>
              <code>{{ entry.attempt.evaluation.findings.length }} 条</code>
            </div>
            <ul v-if="entry.attempt.evaluation.findings.length > 0" class="guided-replay-finding-list">
              <li v-for="finding in entry.attempt.evaluation.findings" :key="finding.id">
                <div class="guided-replay-finding-topline">
                  <span class="guided-replay-finding-severity">{{ findingSeverityLabel(finding.severity) }}</span>
                  <code>{{ findingCategoryLabel(finding.category) }}</code>
                </div>
                <strong>{{ finding.title }}</strong>
                <p>{{ finding.summary }}</p>
                <div class="guided-replay-finding-evidence">
                  <span>命中规则</span><code>{{ findingRuleLabel(finding) }}</code>
                  <span>证据序号</span><code>{{ formatEvidenceSequences(finding.evidenceSequences) }}</code>
                </div>
              </li>
            </ul>
            <p v-else class="guided-replay-no-findings">没有检测到 Finding。</p>
          </div>

          <details class="guided-replay-trace" :data-testid="`guided-replay-${entry.key}-trace`">
            <summary>查看过程记录（{{ entry.facts.events.length }} 条）</summary>
            <ol v-if="entry.facts.events.length > 0" class="guided-replay-trace-list">
              <li
                v-for="event in entry.facts.events"
                :key="`${entry.key}-${event.sequence}-${event.type}-${event.occurredAt}`"
                class="guided-replay-trace-event"
              >
                <div class="guided-replay-trace-event-heading">
                  <span class="guided-replay-trace-sequence">#{{ event.sequence }}</span>
                  <span class="guided-replay-event-type" :class="eventTone(event.type)">{{ eventTypeLabel(event.type) }}</span>
                  <code>{{ event.type }}</code>
                </div>
                <p>{{ event.summary }}</p>
                <details v-if="hasDetails(event)" class="guided-replay-event-details">
                  <summary>查看原始事件详情</summary>
                  <pre>{{ formatDetails(event.details) }}</pre>
                </details>
              </li>
            </ol>
            <p v-else class="guided-replay-trace-empty">无 Trace。</p>
          </details>
        </article>
      </div>
    </template>

    <div v-else class="guided-replay-empty" data-testid="guided-replay-empty">
      <span class="guided-replay-empty-mark">↻</span>
      <div>
        <p class="guided-replay-eyebrow">03 / 修复验证 · Replay</p>
        <h2>发现风险后，验证参考控制项</h2>
        <p>点击下方按钮，用同一身份和攻击消息比较原始配置与参考配置。先运行核心验收并发现风险，才能开始复测。</p>
          <p class="guided-replay-advisory" data-testid="remediation-advisory">
          <strong>仅供参考：</strong>软件提供的是基于当前权限规则的控制项参考和模拟复测，不会修改企业系统，不是企业系统根因结论，也不能替代安全、业务和运维人员的根因分析与变更审批。
        </p>
      </div>
      <button
        type="button"
        class="guided-run-replay"
        data-testid="guided-run-replay"
        :disabled="props.disabled"
        :aria-busy="props.loading"
        @click="emit('run')"
      >
        {{ props.loading ? "模拟 Replay 执行中…" : "运行模拟 Replay" }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.guided-replay-comparison {
  min-width: 0;
  margin-top: 16px;
  padding: 22px;
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.15);
}

.guided-replay-comparison * {
  min-width: 0;
}

.guided-replay-header,
.guided-replay-plan-heading,
.guided-replay-attempt-header,
.guided-replay-subheading,
.guided-replay-action-fact {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.guided-replay-eyebrow,
.guided-replay-label,
.guided-replay-subtitle,
.guided-replay-plan-heading h3,
.guided-replay-plan-heading code,
.guided-replay-remediation-copy strong,
.guided-replay-remediation-copy p,
.guided-replay-attempt-label,
.guided-replay-profile,
.guided-replay-action-fact p,
.guided-replay-findings p,
.guided-replay-finding-list,
.guided-replay-finding-list p,
.guided-replay-trace-event p,
.guided-replay-trace-empty,
.guided-replay-empty h2,
.guided-replay-empty p,
.guided-replay-error p,
.guided-replay-loading p {
  margin: 0;
}

.guided-replay-eyebrow,
.guided-replay-label {
  color: var(--accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.guided-replay-header h2,
.guided-replay-empty h2 {
  margin: 7px 0 0;
  color: var(--ink-strong);
  font-size: 20px;
  font-weight: 650;
  line-height: 1.35;
}

.guided-replay-subtitle {
  max-width: 720px;
  margin-top: 7px;
  color: var(--ink-muted);
  font-size: 11px;
  line-height: 1.6;
}

.guided-replay-result,
.guided-replay-status,
.guided-replay-event-type {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ink);
  border: 1px solid var(--line-bright);
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
}

.guided-replay-result {
  flex-shrink: 0;
  flex-direction: column;
  align-items: flex-end;
  padding: 8px 11px;
  font-size: 9px;
}

.guided-replay-result strong {
  font-size: 10px;
  letter-spacing: 0.04em;
}

.guided-replay-illustration {
  position: relative;
  margin: 17px 0 0;
  overflow: hidden;
  aspect-ratio: 13 / 5;
  background: #071a31;
  border: 1px solid var(--replay-line, var(--line));
  border-radius: 10px;
  box-shadow: 0 14px 32px rgba(6, 25, 49, 0.16);
}

.replay-state-image {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.replay-state-before {
  z-index: 1;
  opacity: 1;
}

.replay-state-after {
  z-index: 2;
  opacity: 0;
}

.guided-replay-illustration.is-passed .replay-state-before {
  animation: replay-before-fade 820ms 180ms ease-out both;
}

.guided-replay-illustration.is-passed .replay-state-after {
  animation: replay-after-fade 820ms 180ms ease-out both;
}

@keyframes replay-before-fade {
  0%,
  28% {
    opacity: 1;
  }

  100% {
    opacity: 0;
  }
}

@keyframes replay-after-fade {
  0%,
  28% {
    opacity: 0;
  }

  100% {
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .guided-replay-illustration.is-passed .replay-state-before,
  .guided-replay-illustration.is-passed .replay-state-after {
    animation: none;
  }

  .guided-replay-illustration.is-passed .replay-state-before {
    opacity: 0;
  }

  .guided-replay-illustration.is-passed .replay-state-after {
    opacity: 1;
  }
}

.guided-replay-result.is-success,
.guided-replay-status.is-success,
.guided-replay-event-type.is-success,
.guided-replay-action-fact.is-success {
  color: #9af5d8;
  border-color: rgba(110, 231, 197, 0.36);
  background: rgba(110, 231, 197, 0.08);
}

.guided-replay-result.is-danger,
.guided-replay-status.is-danger,
.guided-replay-event-type.is-danger,
.guided-replay-action-fact.is-danger {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.36);
  background: rgba(127, 29, 29, 0.18);
}

.guided-replay-status.is-warning,
.guided-replay-event-type.is-warning,
.guided-replay-action-fact.is-warning {
  color: #fed7aa;
  border-color: rgba(251, 146, 60, 0.36);
  background: rgba(251, 146, 60, 0.1);
}

.guided-replay-event-type.is-primary {
  color: #b5d7ff;
  border-color: rgba(96, 165, 250, 0.32);
  background: rgba(30, 64, 175, 0.18);
}

.guided-replay-event-type.is-info {
  color: var(--ink-muted);
  border-color: var(--line);
  background: rgba(160, 181, 207, 0.06);
}

.guided-replay-plan,
.guided-replay-remediation,
.guided-replay-attempt {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 10px;
}

.guided-replay-plan {
  margin-top: 17px;
  padding: 15px 16px;
  background: rgba(6, 14, 26, 0.38);
}

.guided-replay-plan-heading {
  align-items: baseline;
}

.guided-replay-plan-heading h3 {
  margin-top: 6px;
  color: var(--ink-strong);
  font-size: 14px;
  line-height: 1.4;
}

.guided-replay-plan-heading code,
.guided-replay-profile code,
.guided-replay-configuration code,
.guided-replay-subheading code,
.guided-replay-finding-topline code,
.guided-replay-finding-evidence code,
.guided-replay-trace-event-heading code,
.guided-replay-blocked-fact code {
  color: var(--accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
}

.guided-replay-plan-facts {
  display: grid;
  grid-template-columns: minmax(130px, 0.9fr) minmax(130px, 0.9fr) minmax(240px, 1.8fr);
  gap: 10px;
  margin-top: 13px;
}

.guided-replay-plan-facts > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
  padding: 10px 11px;
  background: rgba(24, 42, 68, 0.35);
  border: 1px solid var(--line);
  border-radius: 7px;
}

.guided-replay-plan-facts span,
.guided-replay-plan-facts small {
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.guided-replay-plan-facts strong {
  color: var(--ink-strong);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  overflow-wrap: anywhere;
}

.guided-replay-plan-facts small {
  color: var(--ink-muted);
  line-height: 1.4;
}

.guided-replay-message p {
  color: var(--ink);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.guided-replay-remediation {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(340px, 1.25fr);
  gap: 18px;
  align-items: center;
  margin-top: 12px;
  padding: 14px 16px;
  background: rgba(251, 146, 60, 0.08);
  border-color: rgba(251, 146, 60, 0.24);
}

.guided-replay-remediation-copy strong {
  display: block;
  margin-top: 6px;
  color: var(--ink-strong);
  font-size: 12px;
  line-height: 1.4;
}

.guided-replay-remediation-copy p {
  margin-top: 5px;
  color: var(--ink-muted);
  font-size: 10px;
  line-height: 1.55;
}

.guided-replay-advisory {
  margin-top: 10px;
  padding: 10px 12px;
  border-left: 3px solid var(--warning-amber, #d99a20);
  border-radius: 0 8px 8px 0;
  background: rgba(217, 154, 32, 0.1);
  color: var(--text-secondary, #4b5b72);
}

.guided-replay-configuration {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) repeat(2, minmax(96px, 0.65fr));
  gap: 8px;
  margin: 0;
}

.guided-replay-configuration > div {
  min-width: 0;
  padding: 9px 10px;
  background: rgba(6, 14, 26, 0.27);
  border: 1px solid rgba(251, 146, 60, 0.18);
  border-radius: 7px;
}

.guided-replay-configuration dt {
  color: #fdba74;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.guided-replay-configuration dd {
  margin: 6px 0 0;
  line-height: 1.45;
}

.guided-replay-configuration dd code {
  color: #fed7aa;
}

.guided-replay-attempt-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 15px;
}

.guided-replay-attempt {
  padding: 15px;
  background: rgba(6, 14, 26, 0.4);
}

.guided-replay-attempt.is-before {
  border-color: rgba(248, 113, 113, 0.27);
}

.guided-replay-attempt.is-after {
  border-color: rgba(110, 231, 197, 0.3);
}

.guided-replay-attempt-header {
  align-items: center;
  padding-bottom: 11px;
  border-bottom: 1px solid var(--line);
}

.guided-replay-attempt-label {
  color: var(--ink-strong);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.07em;
}

.guided-replay-profile {
  margin-top: 5px;
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.guided-replay-status {
  flex-shrink: 0;
  padding: 5px 8px;
  font-size: 9px;
  line-height: 1.35;
  white-space: nowrap;
}

.guided-replay-attempt-facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 13px 0 0;
}

.guided-replay-attempt-facts > div {
  min-width: 0;
  padding: 8px 9px;
  background: rgba(24, 42, 68, 0.32);
  border: 1px solid var(--line);
  border-radius: 7px;
}

.guided-replay-attempt-facts dt {
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.guided-replay-attempt-facts dd {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
  margin: 5px 0 0;
  color: var(--ink);
  font-size: 10px;
  line-height: 1.35;
}

.guided-replay-attempt-facts dd code {
  color: var(--ink-strong);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
}

.guided-replay-attempt-facts dd span {
  color: var(--ink-muted);
  font-size: 9px;
}

.guided-replay-attempt-facts dd strong {
  color: var(--ink-strong);
  font-size: 15px;
  line-height: 1;
}

.guided-replay-attempt-facts dd.is-danger strong,
.guided-replay-attempt-facts dd.is-danger code {
  color: #fca5a5;
}

.guided-replay-attempt-facts dd.is-muted strong {
  color: var(--ink-muted);
}

.guided-replay-blocked-fact {
  grid-column: span 2;
}

.guided-replay-blocked-fact dd code {
  color: #fdba74;
}

.guided-replay-action-fact {
  align-items: center;
  margin-top: 10px;
  padding: 10px 11px;
  border: 1px solid var(--line);
  border-radius: 7px;
}

.guided-replay-action-fact.is-warning {
  border-color: rgba(110, 231, 197, 0.33);
  background: rgba(110, 231, 197, 0.06);
}

.guided-replay-action-fact.is-danger {
  border-color: rgba(248, 113, 113, 0.24);
  background: rgba(127, 29, 29, 0.1);
}

.guided-replay-action-fact.is-info {
  color: var(--ink-muted);
  border-color: var(--line-bright);
  background: rgba(160, 181, 207, 0.06);
}

.guided-replay-action-fact > div {
  flex-shrink: 0;
}

.guided-replay-action-fact strong {
  display: block;
  margin-top: 5px;
  color: var(--ink-strong);
  font-size: 11px;
}

.guided-replay-action-fact p {
  color: var(--ink-muted);
  font-size: 10px;
  line-height: 1.5;
  text-align: right;
}

.guided-replay-findings {
  margin-top: 12px;
  padding-top: 11px;
  border-top: 1px solid var(--line);
}

.guided-replay-subheading {
  align-items: baseline;
  color: var(--ink-strong);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.guided-replay-subheading code {
  color: var(--ink-faint);
}

.guided-replay-finding-list {
  display: grid;
  gap: 7px;
  margin-top: 8px;
  padding: 0;
  list-style: none;
}

.guided-replay-finding-list li {
  padding: 9px 10px;
  background: rgba(127, 29, 29, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.2);
  border-left: 2px solid #f87171;
  border-radius: 6px;
}

.guided-replay-finding-topline {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
}

.guided-replay-finding-severity {
  padding: 3px 6px;
  color: #fecaca;
  border: 1px solid rgba(248, 113, 113, 0.28);
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
}

.guided-replay-finding-list li > strong {
  display: block;
  margin-top: 6px;
  color: var(--ink-strong);
  font-size: 10px;
  line-height: 1.45;
}

.guided-replay-finding-list li > p {
  margin-top: 4px;
  color: var(--ink-muted);
  font-size: 9px;
  line-height: 1.5;
}

.guided-replay-finding-evidence {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 4px 7px;
  align-items: baseline;
  margin-top: 7px;
  padding-top: 6px;
  color: var(--ink-faint);
  border-top: 1px solid var(--line);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
}

.guided-replay-finding-evidence code {
  color: #a8b8cc;
}

.guided-replay-no-findings {
  margin-top: 8px;
  color: var(--ink-muted);
  font-size: 10px;
}

.guided-replay-trace {
  margin-top: 12px;
  border-top: 1px solid var(--line);
}

.guided-replay-trace summary,
.guided-replay-event-details summary {
  cursor: pointer;
  color: var(--ink-muted);
  font-size: 10px;
}

.guided-replay-trace summary {
  padding-top: 10px;
  font-family: "SFMono-Regular", Consolas, monospace;
}

.guided-replay-trace-list {
  display: grid;
  gap: 6px;
  margin: 9px 0 0;
  padding: 0;
  list-style: none;
}

.guided-replay-trace-event {
  padding: 8px 9px;
  background: rgba(5, 13, 24, 0.45);
  border: 1px solid var(--line);
  border-radius: 6px;
}

.guided-replay-trace-event-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.guided-replay-trace-sequence {
  flex-shrink: 0;
  color: var(--accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.guided-replay-event-type {
  padding: 3px 6px;
  font-size: 8px;
  line-height: 1.3;
}

.guided-replay-trace-event-heading code {
  color: var(--ink-faint);
  font-size: 8px;
  overflow-wrap: anywhere;
}

.guided-replay-trace-event p {
  margin-top: 5px;
  color: var(--ink);
  font-size: 10px;
  line-height: 1.5;
}

.guided-replay-event-details {
  margin-top: 6px;
}

.guided-replay-event-details pre {
  max-width: 100%;
  margin: 6px 0 0;
  padding: 8px 9px;
  overflow-x: auto;
  color: #a8b8cc;
  background: rgba(5, 13, 24, 0.65);
  border: 1px solid var(--line);
  border-radius: 5px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.guided-replay-trace-empty {
  margin-top: 9px;
  color: var(--ink-faint);
  font-size: 10px;
}

.guided-replay-empty,
.guided-replay-error,
.guided-replay-loading {
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 9px;
}

.guided-replay-empty {
  background: rgba(6, 14, 26, 0.38);
}

.guided-replay-empty-mark {
  display: grid;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  place-items: center;
  color: var(--accent);
  background: var(--accent-wash);
  border: 1px solid rgba(110, 231, 197, 0.24);
  border-radius: 9px;
  font-size: 21px;
}

.guided-replay-empty h2 {
  margin-top: 5px;
  font-size: 15px;
}

.guided-replay-empty p,
.guided-replay-error p,
.guided-replay-loading p {
  margin-top: 5px;
  color: var(--ink-muted);
  font-size: 10px;
  line-height: 1.55;
}

.guided-run-replay {
  min-width: 176px;
  min-height: 36px;
  flex-shrink: 0;
  margin-left: auto;
  padding: 8px 14px;
  color: #061a1a;
  background: var(--accent);
  border: 0;
  border-radius: 7px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
}

.guided-run-replay:hover:not(:disabled) {
  background: #94f4d9;
}

.guided-run-replay:disabled {
  color: var(--ink-faint);
  background: rgba(160, 181, 207, 0.18);
  cursor: not-allowed;
}

.guided-replay-error {
  margin-bottom: 12px;
  align-items: flex-start;
  background: rgba(127, 29, 29, 0.12);
  border-color: rgba(248, 113, 113, 0.3);
}

.guided-replay-error .guided-replay-label {
  color: #fca5a5;
  flex-shrink: 0;
}

.guided-replay-error p {
  margin: 0;
  color: #fecaca;
  overflow-wrap: anywhere;
}

.guided-replay-loading {
  margin-bottom: 12px;
  align-items: flex-start;
  background: rgba(96, 165, 250, 0.08);
  border-color: rgba(96, 165, 250, 0.25);
}

.guided-replay-loading .guided-replay-label {
  color: #b5d7ff;
  flex-shrink: 0;
}

.guided-replay-loading p {
  margin: 0;
  color: #c7ddfb;
}

@media (max-width: 980px) {
  .guided-replay-remediation {
    grid-template-columns: 1fr;
  }

  .guided-replay-configuration {
    grid-template-columns: minmax(0, 1.5fr) repeat(2, minmax(100px, 0.75fr));
  }
}

@media (max-width: 760px) {
  .guided-replay-comparison {
    padding: 17px;
  }

  .guided-replay-header,
  .guided-replay-empty {
    align-items: flex-start;
    flex-direction: column;
  }

  .guided-replay-result {
    align-items: flex-start;
  }

  .guided-replay-plan-facts,
  .guided-replay-attempt-grid {
    grid-template-columns: 1fr;
  }

  .guided-replay-configuration {
    grid-template-columns: 1fr;
  }

  .guided-replay-attempt-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .guided-replay-blocked-fact {
    grid-column: span 2;
  }

  .guided-replay-action-fact {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .guided-replay-action-fact p {
    text-align: left;
  }

  .guided-run-replay {
    width: 100%;
    margin: 0;
  }
}

@media (max-width: 390px) {
  .guided-replay-comparison {
    padding: 14px;
  }

  .guided-replay-attempt-facts {
    grid-template-columns: 1fr;
  }

  .guided-replay-blocked-fact {
    grid-column: auto;
  }

  .guided-replay-attempt-header,
  .guided-replay-plan-heading,
  .guided-replay-subheading {
    align-items: flex-start;
    flex-direction: column;
    gap: 7px;
  }

  .guided-replay-status {
    white-space: normal;
  }

  .guided-replay-illustration {
    aspect-ratio: 3 / 2;
  }
}

/* F-032: make the remediation decision visible before the implementation details. */
.guided-replay-comparison {
  --replay-ink-strong: #132238;
  --replay-ink: #28384d;
  --replay-muted: #64748b;
  --replay-faint: #8a99ad;
  --replay-line: #dbe4ef;
  --replay-action: #4f7cff;
  --replay-risk: #ff5d5d;
  --replay-success: #25bfae;
  --replay-warning: #e6a23c;
  color: var(--replay-ink);
  background: #ffffff;
  border-color: var(--replay-line);
  box-shadow: 0 12px 32px rgba(24, 50, 83, 0.07);
}

.guided-replay-eyebrow,
.guided-replay-label {
  color: var(--replay-action);
}

.guided-replay-header h2,
.guided-replay-empty h2,
.guided-replay-plan-heading h3,
.guided-replay-remediation-copy strong,
.guided-replay-attempt-label,
.guided-replay-attempt-facts dd strong,
.guided-replay-finding-list li > strong {
  color: var(--replay-ink-strong);
}

.guided-replay-subtitle,
.guided-replay-profile,
.guided-replay-remediation-copy p,
.guided-replay-plan-facts small,
.guided-replay-attempt-facts dd span,
.guided-replay-action-fact p,
.guided-replay-findings p,
.guided-replay-finding-list li > p,
.guided-replay-no-findings,
.guided-replay-trace-empty,
.guided-replay-empty p,
.guided-replay-error p,
.guided-replay-loading p {
  color: var(--replay-muted);
}

.guided-replay-result,
.guided-replay-status,
.guided-replay-event-type {
  color: var(--replay-ink);
  border-color: var(--replay-line);
}

.guided-replay-result.is-success,
.guided-replay-status.is-success,
.guided-replay-event-type.is-success,
.guided-replay-action-fact.is-success,
.guided-replay-action-fact.is-warning {
  color: #117e72;
  background: #eafaf7;
  border-color: #9be0d7;
}

.guided-replay-result.is-danger,
.guided-replay-status.is-danger,
.guided-replay-event-type.is-danger,
.guided-replay-action-fact.is-danger {
  color: #b52e2e;
  background: #fff0f0;
  border-color: #ffb1b1;
}

.guided-replay-status.is-warning,
.guided-replay-event-type.is-warning {
  color: #94600f;
  background: #fff8e9;
  border-color: #f0ce8f;
}

.guided-replay-event-type.is-primary {
  color: #315fd7;
  background: #eef2ff;
  border-color: #cbd7ff;
}

.guided-replay-event-type.is-info {
  color: var(--replay-muted);
  background: #f5f7fa;
  border-color: var(--replay-line);
}

.guided-replay-plan,
.guided-replay-attempt {
  background: #f8fafc;
  border-color: var(--replay-line);
}

.guided-replay-plan-facts > div,
.guided-replay-attempt-facts > div {
  background: #ffffff;
  border-color: var(--replay-line);
}

.guided-replay-plan-heading code,
.guided-replay-profile code,
.guided-replay-configuration code,
.guided-replay-subheading code,
.guided-replay-finding-topline code,
.guided-replay-finding-evidence code,
.guided-replay-trace-event-heading code,
.guided-replay-blocked-fact code {
  color: #4169d8;
}

.guided-replay-remediation {
  background: #fff8e9;
  border-color: #f0ce8f;
}

.guided-replay-configuration > div {
  background: #ffffff;
  border-color: #f0ce8f;
}

.guided-replay-configuration dt {
  color: #94600f;
}

.guided-replay-configuration dd code,
.guided-replay-blocked-fact dd code {
  color: #9a650f;
}

.guided-replay-attempt.is-before {
  border-color: #ffcaca;
  box-shadow: 0 8px 20px rgba(255, 93, 93, 0.06);
}

.guided-replay-attempt.is-after {
  border-color: #9be0d7;
  box-shadow: 0 8px 20px rgba(37, 191, 174, 0.06);
}

.guided-replay-attempt-header,
.guided-replay-findings,
.guided-replay-trace {
  border-color: var(--replay-line);
}

.guided-replay-attempt-facts dt {
  color: var(--replay-faint);
}

.guided-replay-attempt-facts dd,
.guided-replay-trace-event p,
.guided-replay-message p {
  color: var(--replay-ink);
}

.guided-replay-attempt-facts dd code {
  color: var(--replay-ink-strong);
}

.guided-replay-attempt-facts dd.is-danger strong,
.guided-replay-attempt-facts dd.is-danger code {
  color: #c84242;
}

.guided-replay-attempt-facts dd.is-muted strong {
  color: var(--replay-muted);
}

.guided-replay-action-fact.is-info {
  color: var(--replay-muted);
  border-color: var(--replay-line);
  background: #f8fafc;
}

.guided-replay-finding-list li {
  background: #fff5f5;
  border-color: #ffcaca;
  border-left-color: var(--replay-risk);
}

.guided-replay-finding-severity {
  color: #b52e2e;
  border-color: #ffb1b1;
  background: #ffe7e7;
}

.guided-replay-finding-evidence {
  color: var(--replay-faint);
  border-color: var(--replay-line);
}

.guided-replay-trace summary,
.guided-replay-event-details summary {
  color: var(--replay-action);
}

.guided-replay-trace-event {
  background: #ffffff;
  border-color: var(--replay-line);
}

.guided-replay-trace-sequence {
  color: var(--replay-action);
}

.guided-replay-event-details pre {
  color: #dce8f8;
  background: #102c4f;
  border-color: #254a73;
}

.guided-replay-empty {
  background: #f8fafc;
  border-color: var(--replay-line);
}

.guided-replay-empty-mark {
  color: var(--replay-action);
  background: #eef2ff;
  border-color: #cbd7ff;
}

.guided-run-replay {
  color: #ffffff;
  background: var(--replay-action);
  box-shadow: 0 8px 18px rgba(79, 124, 255, 0.2);
}

.guided-run-replay:hover:not(:disabled) {
  background: #6d93ff;
}

.guided-run-replay:disabled {
  color: #8a99ad;
  background: #e8edf4;
}

.guided-replay-error {
  background: #fff1f1;
  border-color: #ffcaca;
}

.guided-replay-error .guided-replay-label {
  color: #b52e2e;
}

.guided-replay-error p {
  color: #9f3030;
}

.guided-replay-loading {
  background: #f1f8ff;
  border-color: #c8dcff;
}

.guided-replay-loading .guided-replay-label {
  color: #315fd7;
}

.guided-replay-loading p {
  color: #426487;
}

/* F-060: keep the comparison's conclusion and evidence readable first;
 * identifiers and raw event payloads retain the existing technical style. */
.guided-replay-eyebrow,
.guided-replay-label,
.guided-replay-plan-facts span,
.guided-replay-plan-facts small,
.guided-replay-attempt-label,
.guided-replay-profile,
.guided-replay-attempt-facts dt,
.guided-replay-subheading,
.guided-replay-finding-evidence span {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.guided-replay-header h2,
.guided-replay-empty h2 {
  font-size: var(--type-section-title-size, 23px);
  line-height: var(--type-heading-leading, 1.22);
}

.guided-replay-subtitle,
.guided-replay-remediation-copy p,
.guided-replay-advisory,
.guided-replay-action-fact p,
.guided-replay-finding-list li > p,
.guided-replay-trace-event p,
.guided-replay-trace-empty,
.guided-replay-empty p {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-result,
.guided-replay-result strong,
.guided-replay-status,
.guided-replay-event-type {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.guided-replay-plan-heading h3,
.guided-replay-remediation-copy strong,
.guided-replay-finding-list li > strong {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.guided-replay-message p,
.guided-replay-attempt-facts dd,
.guided-replay-attempt-facts dd span,
.guided-replay-no-findings {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-finding-severity {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-replay-trace summary,
.guided-replay-event-details summary {
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-error.user-problem-card {
  display: grid;
  align-items: stretch;
  padding: 16px 18px;
  color: var(--ink);
  background: #fff1f1;
  border-color: #ffcaca;
  font-family: var(--font-ui);
}

/* F-063: replay is a quiet evidence close.  The Before/After artwork remains
 * a real status-driven asset; all conclusions and controls stay outside it. */
.guided-replay-comparison {
  padding: 0;
  color: var(--ink);
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.guided-replay-comparison .guided-replay-header {
  align-items: flex-end;
  padding: 4px 0 16px;
  border-bottom: 1px solid var(--line);
}

.guided-replay-comparison .guided-replay-eyebrow,
.guided-replay-comparison .guided-replay-label {
  color: var(--action-blue-strong);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.guided-replay-comparison .guided-replay-header h2,
.guided-replay-comparison .guided-replay-empty h2 {
  color: var(--ink-strong);
  font-size: var(--type-section-title-size, 23px);
  line-height: var(--type-heading-leading, 1.22);
}

.guided-replay-comparison .guided-replay-subtitle,
.guided-replay-comparison .guided-replay-empty p,
.guided-replay-comparison .guided-replay-loading p,
.guided-replay-comparison .guided-replay-error p {
  color: var(--ink-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-result {
  align-items: flex-end;
  padding: 0 0 2px;
  color: var(--ink-muted);
  border: 0;
  border-radius: 0;
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-replay-comparison .guided-replay-result strong {
  color: var(--risk-coral-strong);
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
  letter-spacing: normal;
}

.guided-replay-comparison .guided-replay-result.is-success strong {
  color: var(--evidence-teal-strong);
}

.guided-replay-comparison .guided-replay-illustration {
  height: 160px;
  margin: var(--space-4) 0 0;
  aspect-ratio: auto;
  background: var(--surface-evidence);
  border: 1px solid var(--line-on-dark);
  border-radius: var(--radius-stage);
  box-shadow: var(--shadow-overlay);
}

.guided-replay-comparison .replay-state-image {
  object-position: center;
}

.guided-replay-comparison .guided-replay-plan,
.guided-replay-comparison .guided-replay-remediation {
  border-radius: var(--radius-card);
  box-shadow: none;
}

.guided-replay-comparison .guided-replay-plan {
  margin-top: var(--space-4);
  padding: 15px 16px;
  background: var(--surface);
  border-color: var(--line);
}

.guided-replay-comparison .guided-replay-plan-heading {
  padding-bottom: 11px;
  border-bottom: 1px solid var(--line);
}

.guided-replay-comparison .guided-replay-plan-heading h3 {
  color: var(--ink-strong);
  font-family: var(--font-ui);
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.guided-replay-comparison .guided-replay-plan-heading code,
.guided-replay-comparison .guided-replay-profile code,
.guided-replay-comparison .guided-replay-configuration code,
.guided-replay-comparison .guided-replay-subheading code,
.guided-replay-comparison .guided-replay-finding-topline code,
.guided-replay-comparison .guided-replay-finding-evidence code,
.guided-replay-comparison .guided-replay-trace-event-heading code,
.guided-replay-comparison .guided-replay-blocked-fact code {
  color: var(--action-blue-strong);
  font-family: var(--font-code, "SFMono-Regular", Consolas, monospace);
  font-size: var(--type-code-size, 13px);
}

.guided-replay-comparison .guided-replay-plan-facts {
  grid-template-columns: minmax(150px, 0.9fr) minmax(150px, 0.9fr) minmax(260px, 1.8fr);
  gap: 10px;
}

.guided-replay-comparison .guided-replay-plan-facts > div {
  padding: 10px 11px;
  background: #f8fafc;
  border-color: var(--line);
  border-radius: 6px;
}

.guided-replay-comparison .guided-replay-plan-facts span,
.guided-replay-comparison .guided-replay-plan-facts small {
  color: var(--ink-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-replay-comparison .guided-replay-plan-facts strong {
  color: var(--ink-strong);
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-message p {
  color: var(--ink);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-remediation {
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 1fr);
  margin-top: 12px;
  padding: 15px 16px;
  background: #fff8e9;
  border-color: #f0ce8f;
}

.guided-replay-comparison .guided-replay-remediation-copy strong {
  color: var(--ink-strong);
  font-family: var(--font-ui);
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.guided-replay-comparison .guided-replay-remediation-copy p,
.guided-replay-comparison .guided-replay-advisory {
  color: var(--ink-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-advisory {
  background: #fffdf6;
  border-left-color: #d99a20;
}

.guided-replay-comparison .guided-replay-configuration > div {
  padding: 10px 11px;
  background: #ffffff;
  border-color: #f0ce8f;
  border-radius: 6px;
}

.guided-replay-comparison .guided-replay-configuration dt {
  color: #94600f;
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-replay-comparison .guided-replay-configuration dd code {
  color: #9a650f;
}

.guided-replay-comparison .guided-replay-attempt-grid {
  gap: 12px;
  margin-top: 16px;
}

.guided-replay-comparison .guided-replay-attempt {
  padding: 16px;
  background: var(--surface);
  border-color: var(--line);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.guided-replay-comparison .guided-replay-attempt.is-before {
  border-top: 3px solid var(--risk-coral);
  border-color: #ffcaca;
  border-top-color: var(--risk-coral);
}

.guided-replay-comparison .guided-replay-attempt.is-after {
  border-top: 3px solid var(--evidence-teal);
  border-color: #9be0d7;
  border-top-color: var(--evidence-teal);
}

.guided-replay-comparison .guided-replay-attempt-header,
.guided-replay-comparison .guided-replay-findings,
.guided-replay-comparison .guided-replay-trace {
  border-color: var(--line);
}

.guided-replay-comparison .guided-replay-attempt-label,
.guided-replay-comparison .guided-replay-profile,
.guided-replay-comparison .guided-replay-attempt-facts dt,
.guided-replay-comparison .guided-replay-subheading,
.guided-replay-comparison .guided-replay-finding-evidence span {
  color: var(--ink-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.guided-replay-comparison .guided-replay-status {
  padding: 5px 8px;
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.guided-replay-comparison .guided-replay-attempt-facts {
  gap: 8px;
  margin-top: 14px;
}

.guided-replay-comparison .guided-replay-attempt-facts > div {
  padding: 9px 10px;
  background: #f8fafc;
  border-color: var(--line);
  border-radius: 6px;
}

.guided-replay-comparison .guided-replay-attempt-facts dd {
  color: var(--ink);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-attempt-facts dd code {
  color: var(--ink-strong);
}

.guided-replay-comparison .guided-replay-attempt-facts dd span {
  color: var(--ink-muted);
  font-size: var(--type-label-size, 12px);
}

.guided-replay-comparison .guided-replay-action-fact {
  margin-top: 11px;
  padding: 11px 12px;
  border-color: var(--line);
  border-radius: 6px;
}

.guided-replay-comparison .guided-replay-action-fact.is-warning {
  background: #eafaf7;
  border-color: #9be0d7;
}

.guided-replay-comparison .guided-replay-action-fact.is-danger {
  background: #fff0f0;
  border-color: #ffb1b1;
}

.guided-replay-comparison .guided-replay-action-fact strong {
  color: var(--ink-strong);
  font-size: var(--type-body-small-size, 13px);
}

.guided-replay-comparison .guided-replay-action-fact p {
  color: var(--ink-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-findings {
  margin-top: 14px;
  padding-top: 13px;
}

.guided-replay-comparison .guided-replay-finding-list li {
  padding: 11px 12px;
  background: #fff5f5;
  border-color: #ffcaca;
  border-left-color: var(--risk-coral);
  border-radius: 6px;
}

.guided-replay-comparison .guided-replay-finding-severity {
  color: #b52e2e;
  background: #ffe7e7;
  border-color: #ffb1b1;
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-replay-comparison .guided-replay-finding-list li > strong {
  color: var(--ink-strong);
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-finding-list li > p,
.guided-replay-comparison .guided-replay-no-findings {
  color: var(--ink-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-finding-evidence {
  color: var(--ink-faint);
  border-color: var(--line);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.guided-replay-comparison .guided-replay-trace summary,
.guided-replay-comparison .guided-replay-event-details summary {
  color: var(--action-blue-strong);
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-trace-event {
  padding: 9px 10px;
  background: #ffffff;
  border-color: var(--line);
  border-radius: 6px;
}

.guided-replay-comparison .guided-replay-trace-event p {
  color: var(--ink);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-trace-sequence {
  color: var(--action-blue-strong);
}

.guided-replay-comparison .guided-replay-empty,
.guided-replay-comparison .guided-replay-loading,
.guided-replay-comparison .guided-replay-error {
  background: #ffffff;
  border-color: var(--line);
  border-radius: 7px;
  box-shadow: none;
}

.guided-replay-comparison .guided-replay-empty-mark {
  color: var(--action-blue-strong);
  background: #eef2ff;
  border-color: #cbd7ff;
}

.guided-replay-comparison .guided-run-replay {
  min-height: 44px;
  color: #ffffff;
  background: var(--action-blue-strong);
  border-radius: var(--radius-control);
  box-shadow: none;
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 13px);
}

.guided-replay-comparison .guided-run-replay:hover:not(:disabled) {
  background: #345fe7;
}

@media (max-width: 760px) {
  .guided-replay-comparison .guided-replay-illustration {
    height: 140px;
  }

  .guided-replay-comparison .guided-replay-remediation {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 390px) {
  .guided-replay-comparison .guided-replay-header,
  .guided-replay-comparison .guided-replay-empty {
    align-items: flex-start;
  }

  .guided-replay-comparison .guided-replay-result {
    align-items: flex-start;
  }

  .guided-replay-comparison .guided-replay-illustration {
    height: 128px;
  }
}

/* F-063 visual pass 2: readable business evidence remains primary on mobile;
 * identifiers keep a copyable code treatment without becoming tiny metadata. */
.guided-replay-comparison .guided-replay-subtitle,
.guided-replay-comparison .guided-replay-empty p,
.guided-replay-comparison .guided-replay-loading p,
.guided-replay-comparison .guided-replay-error p,
.guided-replay-comparison .guided-replay-remediation-copy p,
.guided-replay-comparison .guided-replay-advisory,
.guided-replay-comparison .guided-replay-attempt-facts dd,
.guided-replay-comparison .guided-replay-action-fact p,
.guided-replay-comparison .guided-replay-finding-list li > p,
.guided-replay-comparison .guided-replay-no-findings,
.guided-replay-comparison .guided-replay-trace summary,
.guided-replay-comparison .guided-replay-event-details summary {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-replay-comparison .guided-replay-message p,
.guided-replay-comparison .guided-replay-plan-facts strong,
.guided-replay-comparison .guided-replay-action-fact strong,
.guided-replay-comparison .guided-replay-finding-list li > strong,
.guided-replay-comparison .guided-replay-trace-event p {
  font-size: max(16px, var(--type-body-size, 16px));
  line-height: var(--type-body-leading, 1.62);
}

.guided-replay-comparison .guided-replay-plan-heading code,
.guided-replay-comparison .guided-replay-profile code,
.guided-replay-comparison .guided-replay-configuration code,
.guided-replay-comparison .guided-replay-subheading code,
.guided-replay-comparison .guided-replay-finding-topline code,
.guided-replay-comparison .guided-replay-finding-evidence code,
.guided-replay-comparison .guided-replay-trace-event-heading code,
.guided-replay-comparison .guided-replay-blocked-fact code,
.guided-replay-comparison .guided-replay-attempt-facts dd code {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}

.guided-replay-comparison .guided-replay-trace-sequence,
.guided-replay-comparison .guided-replay-event-details pre {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}

.guided-replay-comparison .guided-replay-event-details pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 760px) {
  .guided-replay-comparison .guided-replay-plan-facts {
    grid-template-columns: 1fr;
  }
}

/* F-063 visual pass 3: replay evidence keeps a clear folded technical layer
 * with a 44px disclosure target and an explicit keyboard focus treatment. */
.guided-replay-comparison .guided-replay-trace > summary,
.guided-replay-comparison .guided-replay-event-details > summary {
  box-sizing: border-box;
  min-height: 44px;
  padding: 10px 12px 10px 32px;
  color: var(--action-blue-strong);
  border-radius: var(--radius-control, 8px);
  cursor: pointer;
  font-family: var(--font-ui);
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
  list-style: none;
  overflow-wrap: anywhere;
}

.guided-replay-comparison .guided-replay-trace > summary::-webkit-details-marker,
.guided-replay-comparison .guided-replay-event-details > summary::-webkit-details-marker {
  display: none;
}

.guided-replay-comparison .guided-replay-trace > summary::before,
.guided-replay-comparison .guided-replay-event-details > summary::before {
  position: absolute;
  margin-left: -20px;
  color: var(--action-blue-strong);
  content: "▸";
  font-size: 16px;
  line-height: 1;
}

.guided-replay-comparison .guided-replay-trace > summary,
.guided-replay-comparison .guided-replay-event-details > summary {
  position: relative;
}

.guided-replay-comparison .guided-replay-trace[open] > summary::before,
.guided-replay-comparison .guided-replay-event-details[open] > summary::before {
  content: "▾";
}

.guided-replay-comparison .guided-replay-trace > summary:hover,
.guided-replay-comparison .guided-replay-event-details > summary:hover {
  background: var(--surface-raised);
}

.guided-replay-comparison .guided-replay-trace > summary:focus-visible,
.guided-replay-comparison .guided-replay-event-details > summary:focus-visible {
  outline: 2px solid var(--action-blue-strong);
  outline-offset: 2px;
}

.guided-replay-comparison .guided-replay-plan-heading code,
.guided-replay-comparison .guided-replay-profile code,
.guided-replay-comparison .guided-replay-configuration code,
.guided-replay-comparison .guided-replay-subheading code,
.guided-replay-comparison .guided-replay-finding-topline code,
.guided-replay-comparison .guided-replay-finding-evidence code,
.guided-replay-comparison .guided-replay-trace-event-heading code,
.guided-replay-comparison .guided-replay-blocked-fact code,
.guided-replay-comparison .guided-replay-attempt-facts dd code {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.guided-replay-comparison .guided-replay-event-details pre {
  max-width: 100%;
  overflow-x: auto;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
