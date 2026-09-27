<script setup lang="ts">
import { computed } from "vue";
import type {
  ActorRole,
  DifferentialAuditResult,
  DifferentialAuditRow,
  DifferentialDecision,
  DifferentialTargetKind,
  DifferentialTargetProfileId,
  DifferentialTask,
  DifferentialTaskType,
  Finding,
  FindingCategory,
  StartDifferentialAuditRequest,
  TraceEvent,
  TraceEventType,
} from "@agent-audit/contracts";

const props = withDefaults(
  defineProps<{
    tasks: DifferentialTask[];
    taskId: string;
    profileId: DifferentialTargetProfileId | "";
    tasksLoading?: boolean;
    tasksError?: string;
    auditResult?: DifferentialAuditResult | null;
    auditLoading?: boolean;
    auditError?: string;
    title?: string;
    titleId?: string;
  }>(),
  {
    tasksLoading: false,
    tasksError: "",
    auditResult: null,
    auditLoading: false,
    auditError: "",
    title: "身份对比验收",
    titleId: "differential-audit-title",
  },
);

const emit = defineEmits<{
  (event: "update:taskId", value: string): void;
  (event: "update:profileId", value: DifferentialTargetProfileId | ""): void;
  (event: "run", request: StartDifferentialAuditRequest): void;
}>();

const roleLabels: Record<ActorRole, string> = {
  visitor: "访客",
  employee: "员工",
  sales: "销售",
  hr: "人力资源",
  finance_manager: "财务经理",
  admin: "管理员",
};

const taskTypeLabels: Record<DifferentialTaskType, string> = {
  resource_access: "资源访问",
  tool_access: "工具访问",
};

const targetLabels: Record<DifferentialTargetKind, string> = {
  knowledge_document: "知识文档",
  customer_record: "客户记录",
};

const profileLabels: Record<DifferentialTargetProfileId, string> = {
  secure: "安全配置",
  vulnerable_observe_only: "资源观察配置",
  vulnerable_tool_observe_only: "工具观察配置",
};

const profileDescriptions: Record<DifferentialTargetProfileId, string> = {
  secure: "强制执行资源、工具与 Sink 授权",
  vulnerable_observe_only: "资源授权仅观察，不阻断执行",
  vulnerable_tool_observe_only: "工具授权仅观察，不阻断执行",
};

const decisionLabels: Record<DifferentialDecision, string> = {
  allowed: "允许",
  denied: "拒绝",
};

const findingCategoryLabels: Record<FindingCategory, string> = {
  resource_authorization_bypass: "资源授权绕过",
  tool_authorization_bypass: "工具授权绕过",
  external_sink_policy_violation: "外部 Sink 策略违规",
  tool_business_policy_violation: "工具业务约束违规",
};

const findingSeverityLabels: Record<Finding["severity"], string> = {
  high: "高危 High",
  critical: "严重 Critical",
};

const eventLabels: Record<TraceEventType, string> = {
  input: "输入",
  source: "来源 Source",
  retrieval: "检索",
  authorization: "授权",
  tool_call: "工具调用",
  tool_result: "工具结果",
  sink: "流向 Sink",
  model_response: "模型响应",
};

const traceEvidenceFields: ReadonlyArray<{ key: string; label: string }> = [
  { key: "trustLevel", label: "Source trust" },
  { key: "sourceTrustLevels", label: "Source trust levels" },
  { key: "resourceLabels", label: "Resource labels" },
  { key: "resourceIds", label: "Resource IDs" },
  { key: "documentIds", label: "Document IDs" },
  { key: "toolName", label: "Tool" },
  { key: "action", label: "Action" },
  { key: "arguments", label: "Tool args" },
  { key: "data", label: "Tool result" },
  { key: "sinkType", label: "Sink type" },
  { key: "sinkId", label: "Sink ID" },
  { key: "destination", label: "Destination" },
  { key: "external", label: "External" },
  { key: "approvalRequired", label: "Approval required" },
  { key: "approved", label: "Approval" },
  { key: "approvalGranted", label: "Approval granted" },
  { key: "recordCount", label: "Record count" },
  { key: "maxRecords", label: "Max records" },
  { key: "ruleId", label: "Rule ID" },
  { key: "authorizationDecision", label: "Authorization" },
  { key: "decision", label: "Decision" },
  { key: "reason", label: "Reason" },
];

const selectedTask = computed(() =>
  props.tasks.find((task) => task.id === props.taskId) ?? null,
);

const selectedProfileIsSupported = computed(() => {
  const task = selectedTask.value;
  return Boolean(
    task &&
      props.profileId &&
      task.supportedTargetProfileIds.includes(props.profileId as DifferentialTargetProfileId),
  );
});

const canRun = computed(
  () =>
    !props.tasksLoading &&
    !props.auditLoading &&
    Boolean(selectedTask.value) &&
    selectedProfileIsSupported.value,
);

/** Keep a result tied to the task/Profile that produced it.  Selection is
 * presentation state only; changing it never starts a request, and an older
 * result is hidden until the parent supplies a matching DTO. */
const visibleAuditResult = computed(() => {
  const result = props.auditResult;
  const task = selectedTask.value;
  if (!result || !task) {
    return null;
  }

  return result.task.id === task.id && result.targetProfileId === props.profileId ? result : null;
});

const statusKind = computed<"idle" | "loading" | "success" | "error">(() => {
  if (props.auditLoading) {
    return "loading";
  }
  if (props.auditError) {
    return "error";
  }
  if (visibleAuditResult.value) {
    return "success";
  }
  return "idle";
});

const statusLabel = computed(() => {
  const labels: Record<typeof statusKind.value, string> = {
    idle: "待运行",
    loading: "对比中",
    success: "已完成",
    error: "执行失败",
  };
  return labels[statusKind.value];
});

const resultFindingCategories = computed(() => {
  const result = visibleAuditResult.value;
  if (!result) {
    return [];
  }

  const categories = result.rows.flatMap((row) => row.findings.map((finding) => finding.category));
  return Array.from(new Set(categories));
});

function taskTypeLabel(task: DifferentialTask): string {
  return taskTypeLabels[task.taskType];
}

function targetLabel(kind: DifferentialTargetKind): string {
  return targetLabels[kind];
}

function profileLabel(profile: DifferentialTargetProfileId): string {
  return profileLabels[profile];
}

function profileDescription(profile: DifferentialTargetProfileId): string {
  return profileDescriptions[profile];
}

function decisionLabel(decision: DifferentialDecision): string {
  return `${decisionLabels[decision]} ${decision}`;
}

function decisionClass(decision: DifferentialDecision): string {
  return decision === "allowed" ? "is-allowed" : "is-denied";
}

function categoryLabel(category: FindingCategory): string {
  return findingCategoryLabels[category] ?? category;
}

function categoryCode(category: FindingCategory): string {
  return category;
}

function severityLabel(severity: Finding["severity"]): string {
  return findingSeverityLabels[severity];
}

function executionLabel(status: DifferentialAuditRow["executionStatus"]): string {
  return status === "completed" ? "已完成" : "已阻断";
}

function executionClass(status: DifferentialAuditRow["executionStatus"]): string {
  return status === "completed" ? "is-completed" : "is-blocked";
}

function eventLabel(type: TraceEventType): string {
  return eventLabels[type];
}

function eventClass(type: TraceEventType): string {
  if (type === "authorization") {
    return "is-warning";
  }
  if (type === "tool_call" || type === "sink") {
    return "is-danger";
  }
  if (type === "tool_result" || type === "model_response") {
    return "is-success";
  }
  return "is-primary";
}

function rowTraceEvents(row: DifferentialAuditRow): TraceEvent[] {
  return [...row.traceEvents].sort((left, right) => left.sequence - right.sequence);
}

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

function traceEvidenceRows(event: TraceEvent): Array<{ label: string; value: string }> {
  return traceEvidenceFields.flatMap(({ key, label }) => {
    const value = detailValueText(event.details[key]);
    return value ? [{ label, value }] : [];
  });
}

function hasDetails(event: TraceEvent): boolean {
  return Object.keys(event.details).length > 0;
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2) ?? "{}";
}

function formatOccurredAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function readSelectValue(event: Event): string {
  return (event.target as HTMLSelectElement).value;
}

function isProfileId(value: string): value is DifferentialTargetProfileId {
  return (
    value === "secure" ||
    value === "vulnerable_observe_only" ||
    value === "vulnerable_tool_observe_only"
  );
}

function selectTask(event: Event): void {
  emit("update:taskId", readSelectValue(event));
}

function selectProfile(event: Event): void {
  const value = readSelectValue(event);
  emit("update:profileId", isProfileId(value) ? value : "");
}

function runComparison(): void {
  const task = selectedTask.value;
  if (!task || !selectedProfileIsSupported.value || !props.profileId || props.auditLoading) {
    return;
  }

  emit("run", {
    taskId: task.id,
    targetProfileId: props.profileId,
  });
}
</script>

<template>
  <section
    class="differential-workspace"
    :aria-labelledby="props.titleId"
    data-testid="differential-audit-workspace"
  >
    <header class="differential-heading">
      <div class="differential-heading-copy">
        <p class="differential-kicker">QUALITY / ACTOR COMPARISON</p>
        <h2 :id="props.titleId">{{ props.title }}</h2>
        <p class="differential-lede">比较同一任务在不同角色下是否遵守权限边界。</p>
      </div>
      <div class="differential-heading-action">
        <span
          class="differential-status"
          :class="`is-${statusKind}`"
          data-testid="differential-status"
          aria-live="polite"
        >
          {{ statusLabel }}
        </span>
        <button
          class="differential-run"
          data-testid="differential-run"
          type="button"
          :disabled="!canRun"
          :aria-busy="props.auditLoading"
          @click="runComparison"
        >
          {{ props.auditLoading ? "对比中…" : "运行对比" }}
          <span aria-hidden="true">↗</span>
        </button>
      </div>
    </header>

    <div v-if="props.tasksError" class="differential-alert" data-testid="differential-tasks-error" role="alert">
      {{ props.tasksError }}
    </div>

    <div v-if="props.tasksLoading" class="differential-loading" data-testid="differential-tasks-loading" role="status" aria-live="polite">
      <span class="loading-mark" aria-hidden="true">…</span>
      <div>
        <strong>正在加载差分任务</strong>
        <p>任务与 Profile 就绪后即可运行对比。</p>
      </div>
    </div>

    <div v-else-if="props.tasks.length === 0" class="differential-empty" data-testid="differential-empty" role="status">
      <span class="empty-mark" aria-hidden="true">◎</span>
      <div>
        <strong>暂无可用的差分任务</strong>
        <p>当前 Workspace 没有可执行的标准化身份对比任务。</p>
      </div>
    </div>

    <template v-else-if="selectedTask">
      <div class="differential-selection" data-testid="differential-selection">
        <label class="differential-field" for="differential-task-select">
          <span>任务</span>
          <select
            id="differential-task-select"
            data-testid="differential-task-select"
            :value="props.taskId"
            :disabled="props.auditLoading"
            @change="selectTask"
          >
            <option v-for="task in props.tasks" :key="task.id" :value="task.id" :title="task.id">
              {{ task.name }}
            </option>
          </select>
        </label>

        <label class="differential-field" for="differential-profile-select">
          <span>Target Profile</span>
          <select
            id="differential-profile-select"
            data-testid="differential-profile-select"
            :value="props.profileId"
            :disabled="props.auditLoading"
            @change="selectProfile"
          >
            <option value="" disabled>选择 Profile</option>
            <option
              v-for="profile in selectedTask.supportedTargetProfileIds"
              :key="profile"
              :value="profile"
              :title="profileDescription(profile)"
            >
              {{ profileLabel(profile) }}
            </option>
          </select>
        </label>
      </div>

      <div class="differential-summary" data-testid="differential-summary">
        <article class="summary-item summary-goal" data-testid="differential-verification-target">
          <span class="summary-label">验证目标</span>
          <p>{{ selectedTask.description }}</p>
        </article>
        <article class="summary-item" data-testid="differential-actor-count">
          <span class="summary-label">Actor 数</span>
          <strong>{{ selectedTask.actorIds.length }}</strong>
          <span class="summary-muted">固定身份顺序</span>
        </article>
        <article class="summary-item" data-testid="differential-target">
          <span class="summary-label">Target</span>
          <strong>{{ targetLabel(selectedTask.targetKind) }}</strong>
          <span v-if="selectedTask.toolName" class="summary-muted">{{ selectedTask.toolName }}<span v-if="selectedTask.action"> · {{ selectedTask.action }}</span></span>
        </article>
        <article class="summary-item" data-testid="differential-category-summary">
          <span class="summary-label">类别摘要</span>
          <strong>{{ taskTypeLabel(selectedTask) }}</strong>
          <span class="summary-muted">{{ targetLabel(selectedTask.targetKind) }}</span>
        </article>
      </div>

      <details class="differential-technical" data-testid="differential-technical-details">
        <summary>查看技术详情</summary>
        <div class="technical-grid">
          <div>
            <span>Task ID</span>
            <code>{{ selectedTask.id }}</code>
          </div>
          <div>
            <span>Target Profile ID</span>
            <code>{{ props.profileId || "未选择" }}</code>
          </div>
          <div>
            <span>Target ID</span>
            <code>{{ selectedTask.targetId }}</code>
          </div>
          <div>
            <span>Actor IDs</span>
            <code>{{ selectedTask.actorIds.join(" · ") }}</code>
          </div>
          <div>
            <span>Supported Profiles</span>
            <code>{{ selectedTask.supportedTargetProfileIds.join(" · ") }}</code>
          </div>
          <div>
            <span>Tool / Action</span>
            <code>{{ selectedTask.toolName ?? "—" }} / {{ selectedTask.action ?? "—" }}</code>
          </div>
          <div class="technical-wide">
            <span>Message</span>
            <p>{{ selectedTask.message }}</p>
          </div>
        </div>
      </details>

      <div v-if="props.auditLoading" class="differential-loading differential-audit-loading" data-testid="differential-loading" role="status" aria-live="polite">
        <span class="loading-mark" aria-hidden="true">…</span>
        <div>
          <strong>正在执行身份对比</strong>
          <p>按任务声明的 Actor 顺序采集 Authorization、Tool 与完整 Trace。</p>
        </div>
      </div>

      <div v-else-if="props.auditError" class="differential-alert" data-testid="differential-audit-error" role="alert">
        {{ props.auditError }}
      </div>

      <section v-else-if="visibleAuditResult" class="differential-result" data-testid="differential-result" aria-live="polite">
        <header class="result-heading">
          <div>
            <p class="result-kicker">对比结果</p>
            <h3>{{ visibleAuditResult.status === "passed" ? "所有身份符合预期" : "发现身份决策差异" }}</h3>
            <p>本次结果由服务端 Contract 与每个 Actor 的实际 Trace 返回。</p>
          </div>
          <span class="result-status" :class="visibleAuditResult.status === 'passed' ? 'is-passed' : 'is-failed'">
            {{ visibleAuditResult.status === "passed" ? "通过" : "发现差异" }}
          </span>
        </header>

        <dl class="result-meta">
          <div>
            <dt>差异数</dt>
            <dd>{{ visibleAuditResult.mismatchCount }}</dd>
          </div>
          <div>
            <dt>Actor rows</dt>
            <dd>{{ visibleAuditResult.rows.length }}</dd>
          </div>
          <div>
            <dt>Target Profile</dt>
            <dd><code>{{ visibleAuditResult.targetProfileId }}</code></dd>
          </div>
          <div v-if="resultFindingCategories.length > 0" class="result-categories">
            <dt>Finding 类别</dt>
            <dd>
              <span v-for="category in resultFindingCategories" :key="category" class="category-chip">
                {{ categoryLabel(category) }}
              </span>
            </dd>
          </div>
        </dl>

        <div class="differential-rows" data-testid="differential-rows">
          <article
            v-for="row in visibleAuditResult.rows"
            :key="row.id"
            class="differential-row"
            :class="{ 'is-mismatch': !row.matched }"
            :data-testid="`differential-row-${row.id}`"
          >
            <header class="row-heading">
              <div class="row-actor">
                <span class="row-kicker">Actor</span>
                <h4>{{ row.actor.displayName }}</h4>
                <span>{{ roleLabels[row.actor.role] }}</span>
                <code>{{ row.actor.id }}</code>
              </div>
              <span
                class="match-status"
                :class="row.matched ? 'is-matched' : 'is-mismatch'"
                :data-testid="`differential-row-${row.id}-match`"
              >
                {{ row.matched ? "Matched · 符合" : "Mismatch · 不一致" }}
              </span>
            </header>

            <p class="row-target">
              <span>Target</span>
              <strong>{{ targetLabel(row.targetKind) }}</strong>
              <code>{{ row.targetId }}</code>
            </p>

            <dl class="row-decisions">
              <div :data-testid="`differential-row-${row.id}-expected`">
                <dt>Expected</dt>
                <dd><span class="decision-chip" :class="decisionClass(row.expectedDecision)">{{ decisionLabel(row.expectedDecision) }}</span></dd>
              </div>
              <div :data-testid="`differential-row-${row.id}-actual`">
                <dt>Actual</dt>
                <dd><span class="decision-chip" :class="decisionClass(row.actualDecision)">{{ decisionLabel(row.actualDecision) }}</span></dd>
              </div>
              <div :data-testid="`differential-row-${row.id}-matched`">
                <dt>Matched</dt>
                <dd><span class="match-value" :class="row.matched ? 'is-matched' : 'is-mismatch'">{{ row.matched ? "是 true" : "否 false" }}</span></dd>
              </div>
              <div>
                <dt>Execution</dt>
                <dd>
                  <span class="execution-value" :class="executionClass(row.executionStatus)">{{ executionLabel(row.executionStatus) }}</span>
                  <code v-if="row.queryId">queryId={{ row.queryId }}</code>
                </dd>
              </div>
              <div>
                <dt>Rule</dt>
                <dd><code>{{ row.ruleId ?? "default deny" }}</code></dd>
              </div>
              <div v-if="row.blockedReason">
                <dt>Blocked reason</dt>
                <dd>{{ row.blockedReason }}</dd>
              </div>
            </dl>

            <section
              class="row-evidence"
              data-testid="differential-row-findings"
              :aria-labelledby="`differential-finding-title-${row.id}`"
            >
              <div class="row-section-heading">
                <h5 :id="`differential-finding-title-${row.id}`">Finding</h5>
                <span>{{ row.findings.length }} items</span>
              </div>
              <div v-if="row.findings.length > 0" class="finding-list">
                <article
                  v-for="finding in row.findings"
                  :key="finding.id"
                  class="finding-item"
                  :data-testid="`differential-finding-${finding.id}`"
                >
                  <header>
                    <strong>{{ finding.title }}</strong>
                    <span class="finding-severity" :class="`is-${finding.severity}`">{{ severityLabel(finding.severity) }}</span>
                  </header>
                  <p>{{ finding.summary }}</p>
                  <dl>
                    <div><dt>Finding ID</dt><dd><code>{{ finding.id }}</code></dd></div>
                    <div><dt>Category</dt><dd><span>{{ categoryLabel(finding.category) }}</span><code>{{ categoryCode(finding.category) }}</code></dd></div>
                    <div><dt>Contract basis</dt><dd><code>{{ finding.contractBasis }}</code></dd></div>
                    <div><dt>Rule</dt><dd><code>{{ finding.ruleId ?? "default deny" }}</code></dd></div>
                    <div><dt>Evidence</dt><dd><code>{{ finding.evidenceSequences.join(" → ") || "—" }}</code></dd></div>
                  </dl>
                </article>
              </div>
              <p v-else class="row-none">无 Finding</p>
              <p v-if="row.evidenceSequences.length > 0" class="row-evidence-sequences">
                Row evidence <code>{{ row.evidenceSequences.join(" → ") }}</code>
              </p>
            </section>

            <section
              class="row-trace"
              data-testid="differential-row-trace"
              :aria-labelledby="`differential-trace-title-${row.id}`"
            >
              <div class="row-section-heading">
                <h5 :id="`differential-trace-title-${row.id}`">Trace</h5>
                <span>{{ row.traceEvents.length }} events</span>
              </div>
              <details
                v-if="row.traceEvents.length > 0"
                class="trace-details"
                :data-testid="`differential-trace-${row.id}`"
              >
                <summary>展开 Actor Trace</summary>
                <ol class="trace-list">
                  <li v-for="event in rowTraceEvents(row)" :key="`${row.id}-${event.sequence}-${event.type}-${event.occurredAt}`">
                    <div class="trace-event-heading">
                      <span class="trace-sequence">#{{ event.sequence }}</span>
                      <span class="event-type" :class="eventClass(event.type)">{{ eventLabel(event.type) }}</span>
                      <code>{{ event.type }}</code>
                      <time :datetime="event.occurredAt">{{ formatOccurredAt(event.occurredAt) }}</time>
                    </div>
                    <p class="trace-summary">{{ event.summary }}</p>
                    <div v-if="traceEvidenceRows(event).length > 0" class="trace-evidence">
                      <template v-for="evidence in traceEvidenceRows(event)" :key="`${row.id}-${event.sequence}-${evidence.label}`">
                        <span>{{ evidence.label }}</span>
                        <code>{{ evidence.value }}</code>
                      </template>
                    </div>
                    <pre v-if="hasDetails(event)">{{ formatDetails(event.details) }}</pre>
                  </li>
                </ol>
              </details>
              <p v-else class="row-none">无 Trace events</p>
            </section>
          </article>
        </div>
      </section>

      <div v-else class="differential-idle" data-testid="differential-idle" role="status" aria-live="polite">
        <span class="idle-mark" aria-hidden="true">◎</span>
        <div>
          <strong>尚无对比结果</strong>
          <p>选择任务和 Profile 后，点击“运行对比”查看各身份的实际决策与 Trace。</p>
        </div>
      </div>
    </template>

    <div v-else class="differential-empty differential-empty-selection" data-testid="differential-selection-empty" role="status">
      <span class="empty-mark" aria-hidden="true">◎</span>
      <div>
        <strong>请选择差分任务</strong>
        <p>任务列表已加载，但当前选择尚未对应可执行任务。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.differential-workspace {
  --dw-ink-strong: var(--ink-strong, #132238);
  --dw-ink: var(--ink, #24364d);
  --dw-ink-muted: var(--ink-muted, #64748b);
  --dw-ink-faint: var(--ink-faint, #72839a);
  --dw-line: var(--line, #dce5ef);
  --dw-line-bright: var(--line-bright, #c5d3e3);
  --dw-surface: var(--surface, #ffffff);
  --dw-surface-raised: var(--surface-raised, #f8fafc);
  --dw-action: var(--action-blue, #4f7cff);
  --dw-action-strong: var(--action-blue-strong, #345fe7);
  --dw-action-wash: var(--action-blue-wash, rgba(79, 124, 255, 0.1));
  --dw-risk: var(--risk-coral, #e05252);
  --dw-risk-strong: var(--risk-coral-strong, #c63d46);
  --dw-risk-wash: var(--risk-coral-wash, rgba(224, 82, 82, 0.1));
  --dw-evidence: var(--evidence-teal, #168f82);
  --dw-evidence-strong: var(--evidence-teal-strong, #08786e);
  --dw-evidence-wash: var(--evidence-teal-wash, rgba(22, 143, 130, 0.1));
  --dw-warning: var(--warning-amber, #b87512);
  --dw-warning-wash: var(--warning-amber-wash, rgba(230, 162, 60, 0.14));
  --dw-font-ui: var(--font-ui, Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
  --dw-font-code: var(--font-code, "SFMono-Regular", Consolas, "Liberation Mono", monospace);
  --dw-h1: var(--type-page-title-size, var(--f045-type-h1, var(--type-h1, var(--font-size-h1, 34px))));
  --dw-h2: var(--type-section-title-size, var(--f045-type-h2, var(--type-h2, var(--font-size-h2, 26px))));
  --dw-h3: var(--type-card-title-size, var(--f045-type-h3, var(--type-h3, var(--font-size-h3, 19px))));
  --dw-body: var(--type-body-size, var(--f045-type-body, var(--type-body, var(--font-size-body, 16px))));
  --dw-body-small: var(--type-body-small-size, var(--f045-type-body-small, var(--type-body-small, var(--font-size-body-small, 14px))));
  --dw-label: var(--type-label-size, var(--f045-type-label, var(--type-label, var(--font-size-label, 12px))));
  --dw-code: var(--type-code-size, var(--f045-type-code, var(--type-code, var(--font-size-code, 13px))));
  --dw-leading-heading: var(--type-heading-leading, var(--f045-leading-heading, 1.22));
  --dw-leading-body: var(--type-body-leading, var(--f045-leading-body, 1.62));
  --dw-leading-small: var(--type-body-small-leading, var(--f045-leading-small, 1.55));
  --dw-leading-label: var(--type-label-leading, var(--f045-leading-label, 1.35));
  --dw-leading-code: var(--type-code-leading, var(--f045-leading-code, 1.5));
  --dw-space-1: var(--f045-space-1, var(--space-1, 6px));
  --dw-space-2: var(--f045-space-2, var(--space-2, 10px));
  --dw-space-3: var(--f045-space-3, var(--space-3, 14px));
  --dw-space-4: var(--f045-space-4, var(--space-4, 18px));
  --dw-space-5: var(--f045-space-5, var(--space-5, 24px));
  --dw-space-6: var(--f045-space-6, var(--space-6, 32px));
  --dw-radius: var(--f045-radius, var(--radius-md, 14px));
  width: min(100%, var(--layout-evidence-max, var(--f045-content-wide, var(--content-wide, 1440px))));
  max-width: var(--layout-evidence-max, var(--f045-content-wide, var(--content-wide, 1440px)));
  min-width: 0;
  margin: 0 auto;
  color: var(--dw-ink);
  font-family: var(--dw-font-ui);
  font-size: var(--dw-body);
  line-height: var(--dw-leading-body);
}

.differential-heading,
.differential-selection,
.differential-summary,
.technical-grid,
.result-meta,
.row-decisions {
  min-width: 0;
}

.differential-heading {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: var(--dw-space-5);
  margin-bottom: var(--dw-space-4);
}

.differential-heading-copy,
.differential-heading-action {
  min-width: 0;
}

.differential-kicker,
.result-kicker,
.row-kicker,
.summary-label,
.differential-field > span,
.technical-grid > div > span,
.result-meta dt,
.row-decisions dt,
.finding-item dt,
.row-section-heading span {
  color: var(--dw-ink-muted);
  font-size: var(--dw-label);
  font-weight: 700;
  letter-spacing: 0.06em;
  line-height: var(--dw-leading-label);
}

.differential-kicker,
.result-kicker,
.row-kicker {
  margin: 0;
  color: var(--dw-action-strong);
  font-family: var(--dw-font-code);
  font-size: var(--dw-label);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.differential-heading h2 {
  margin: var(--dw-space-1) 0 0;
  color: var(--dw-ink-strong);
  font-size: var(--dw-h2);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: var(--dw-leading-heading);
}

.differential-lede,
.result-heading p,
.differential-idle p,
.differential-empty p,
.differential-loading p {
  margin: var(--dw-space-1) 0 0;
  color: var(--dw-ink-muted);
  font-size: var(--dw-body-small);
  line-height: var(--dw-leading-small);
}

.differential-heading-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--dw-space-3);
}

.differential-status,
.result-status,
.match-status,
.finding-severity,
.category-chip,
.decision-chip,
.execution-value,
.match-value,
.event-type {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  border-radius: 999px;
  font-size: var(--dw-body-small);
  font-weight: 700;
  line-height: var(--dw-leading-label);
}

.differential-status {
  padding: 6px 10px;
  color: var(--dw-ink-muted);
  background: var(--dw-surface-raised);
  border: 1px solid var(--dw-line);
  white-space: nowrap;
}

.differential-status.is-loading {
  color: var(--dw-warning);
  background: var(--dw-warning-wash);
}

.differential-status.is-success {
  color: var(--dw-evidence-strong);
  background: var(--dw-evidence-wash);
}

.differential-status.is-error {
  color: var(--dw-risk-strong);
  background: var(--dw-risk-wash);
}

.differential-run {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 10px 18px;
  color: #ffffff;
  background: var(--dw-action);
  border: 1px solid var(--dw-action);
  border-radius: 9px;
  box-shadow: 0 7px 16px rgba(79, 124, 255, 0.18);
  cursor: pointer;
  font: inherit;
  font-size: var(--dw-body-small);
  font-weight: 750;
  transition:
    background-color 140ms ease,
    border-color 140ms ease,
    box-shadow 140ms ease;
}

.differential-run:hover:not(:disabled),
.differential-run:focus-visible:not(:disabled) {
  background: var(--dw-action-strong);
  border-color: var(--dw-action-strong);
  box-shadow: 0 9px 20px rgba(79, 124, 255, 0.25);
}

.differential-run:disabled {
  color: rgba(36, 54, 77, 0.48);
  background: rgba(79, 124, 255, 0.25);
  border-color: rgba(79, 124, 255, 0.22);
  box-shadow: none;
  cursor: not-allowed;
}

.differential-run:focus-visible,
.differential-field select:focus-visible,
.differential-technical summary:focus-visible,
.trace-details summary:focus-visible {
  outline: 3px solid rgba(79, 124, 255, 0.25);
  outline-offset: 2px;
}

.differential-alert,
.differential-loading,
.differential-empty,
.differential-idle,
.differential-selection,
.differential-summary,
.differential-technical,
.differential-result {
  background: var(--dw-surface);
  border: 1px solid var(--dw-line);
  border-radius: var(--dw-radius);
}

.differential-alert {
  margin-bottom: var(--dw-space-3);
  padding: 12px 14px;
  color: var(--dw-risk-strong);
  background: var(--dw-risk-wash);
  border-color: rgba(224, 82, 82, 0.28);
  font-size: var(--dw-body-small);
  overflow-wrap: anywhere;
}

.differential-loading,
.differential-empty,
.differential-idle {
  display: flex;
  align-items: center;
  gap: var(--dw-space-3);
  min-height: 76px;
  padding: 16px 18px;
}

.differential-loading strong,
.differential-empty strong,
.differential-idle strong {
  color: var(--dw-ink-strong);
  font-size: var(--dw-body);
}

.loading-mark,
.empty-mark,
.idle-mark {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  place-items: center;
  color: var(--dw-action);
  border: 1px solid rgba(79, 124, 255, 0.32);
  border-radius: 50%;
  font-size: 17px;
  font-weight: 750;
}

.differential-empty-selection {
  margin-top: var(--dw-space-3);
}

.differential-selection {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(220px, 1fr);
  gap: var(--dw-space-4);
  padding: var(--dw-space-4);
}

.differential-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: var(--dw-space-1);
}

.differential-field > span {
  color: var(--dw-ink);
  font-weight: 700;
  letter-spacing: 0.02em;
}

.differential-field select {
  width: 100%;
  min-width: 0;
  height: 44px;
  padding: 0 12px;
  color: var(--dw-ink-strong);
  background: var(--dw-surface);
  border: 1px solid var(--dw-line-bright);
  border-radius: 8px;
  font: inherit;
  font-size: var(--dw-body);
  overflow: hidden;
  text-overflow: ellipsis;
}

.differential-field select:disabled {
  color: var(--dw-ink-muted);
  background: var(--dw-surface-raised);
  cursor: not-allowed;
}

.differential-summary {
  display: grid;
  grid-template-columns: minmax(0, 2fr) repeat(3, minmax(0, 1fr));
  gap: 0;
  margin-top: var(--dw-space-3);
  overflow: hidden;
}

.summary-item {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
  padding: 15px 16px;
  border-left: 1px solid var(--dw-line);
}

.summary-item:first-child {
  border-left: 0;
}

.summary-label {
  text-transform: uppercase;
}

.summary-item strong,
.summary-item p {
  margin: 0;
  color: var(--dw-ink-strong);
  font-size: var(--dw-body);
  font-weight: 700;
  overflow-wrap: anywhere;
}

.summary-goal p {
  font-weight: 550;
  line-height: var(--dw-leading-body);
}

.summary-muted {
  color: var(--dw-ink-muted);
  font-size: var(--dw-body-small);
  overflow-wrap: anywhere;
}

.differential-technical {
  margin-top: var(--dw-space-3);
  padding: 0 var(--dw-space-4);
}

.differential-technical summary,
.trace-details summary {
  padding: 13px 0;
  color: var(--dw-action-strong);
  cursor: pointer;
  font-size: var(--dw-body-small);
  font-weight: 700;
  list-style-position: inside;
}

.technical-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--dw-space-4);
  padding: 0 0 var(--dw-space-4);
  border-top: 1px solid var(--dw-line);
}

.technical-grid > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
  padding-top: var(--dw-space-3);
}

.technical-grid > div > span {
  color: var(--dw-ink-muted);
  font-family: var(--dw-font-code);
  font-size: var(--dw-label);
  font-weight: 600;
  letter-spacing: 0.02em;
}

code {
  color: var(--dw-evidence-strong);
  font-family: var(--dw-font-code);
  font-size: var(--dw-code);
  overflow-wrap: anywhere;
}

.technical-grid p {
  margin: 0;
  color: var(--dw-ink);
  font-size: var(--dw-body-small);
  line-height: var(--dw-leading-small);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.technical-wide {
  grid-column: 1 / -1;
}

.differential-audit-loading {
  margin-top: var(--dw-space-3);
}

.differential-result {
  margin-top: var(--dw-space-3);
  padding: var(--dw-space-4);
}

.result-heading,
.row-heading,
.row-section-heading {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--dw-space-3);
}

.result-heading > div,
.row-heading > div,
.finding-item header strong {
  min-width: 0;
}

.result-heading h3 {
  margin: var(--dw-space-1) 0 0;
  color: var(--dw-ink-strong);
  font-size: var(--dw-h3);
  line-height: var(--dw-leading-heading);
}

.result-status {
  flex: 0 0 auto;
  padding: 7px 11px;
}

.result-status.is-passed,
.match-status.is-matched,
.match-value.is-matched,
.execution-value.is-completed {
  color: var(--dw-evidence-strong);
  background: var(--dw-evidence-wash);
}

.result-status.is-failed,
.match-status.is-mismatch,
.match-value.is-mismatch {
  color: var(--dw-risk-strong);
  background: var(--dw-risk-wash);
}

.result-meta {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--dw-space-3);
  margin: var(--dw-space-4) 0 0;
  padding: var(--dw-space-3) 0;
  border-top: 1px solid var(--dw-line);
  border-bottom: 1px solid var(--dw-line);
}

.result-meta > div {
  min-width: 0;
}

.result-meta dt,
.row-decisions dt,
.finding-item dt {
  margin: 0;
  font-family: var(--dw-font-code);
  font-size: var(--dw-label);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.result-meta dd {
  margin: 5px 0 0;
  color: var(--dw-ink-strong);
  font-size: var(--dw-body);
  font-weight: 700;
  overflow-wrap: anywhere;
}

.result-categories dd {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.category-chip {
  padding: 4px 8px;
  color: var(--dw-risk-strong);
  background: var(--dw-risk-wash);
  font-size: var(--dw-body-small);
}

.differential-rows {
  display: grid;
  gap: var(--dw-space-4);
  margin-top: var(--dw-space-4);
}

.differential-row {
  min-width: 0;
  padding: var(--dw-space-4);
  background: var(--dw-surface-raised);
  border: 1px solid var(--dw-line);
  border-radius: 11px;
}

.differential-row.is-mismatch {
  border-color: rgba(224, 82, 82, 0.34);
  box-shadow: inset 3px 0 0 var(--dw-risk);
}

.row-actor {
  display: flex;
  min-width: 0;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 5px 9px;
}

.row-kicker {
  flex-basis: 100%;
}

.row-actor h4 {
  margin: 0;
  color: var(--dw-ink-strong);
  font-size: var(--dw-h3);
  line-height: var(--dw-leading-heading);
}

.row-actor > span:not(.row-kicker) {
  color: var(--dw-ink-muted);
  font-size: var(--dw-body-small);
}

.row-target {
  display: flex;
  min-width: 0;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin: var(--dw-space-3) 0 0;
  padding: 10px 0;
  color: var(--dw-ink-muted);
  border-top: 1px solid var(--dw-line);
  border-bottom: 1px solid var(--dw-line);
  font-size: var(--dw-body-small);
}

.row-target > span {
  font-family: var(--dw-font-code);
  font-size: var(--dw-label);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.row-target strong {
  color: var(--dw-ink);
  font-size: var(--dw-body);
}

.row-decisions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--dw-space-3);
  margin: var(--dw-space-3) 0 0;
}

.row-decisions > div {
  min-width: 0;
  padding: 11px 12px;
  background: var(--dw-surface);
  border: 1px solid var(--dw-line);
  border-radius: 8px;
}

.row-decisions dd {
  display: flex;
  min-width: 0;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px;
  margin: 7px 0 0;
  color: var(--dw-ink);
  font-size: var(--dw-body-small);
  overflow-wrap: anywhere;
}

.decision-chip,
.execution-value,
.match-value {
  padding: 4px 8px;
}

.decision-chip.is-allowed {
  color: var(--dw-evidence-strong);
  background: var(--dw-evidence-wash);
}

.decision-chip.is-denied {
  color: var(--dw-warning);
  background: var(--dw-warning-wash);
}

.execution-value.is-blocked {
  color: var(--dw-warning);
  background: var(--dw-warning-wash);
}

.row-evidence,
.row-trace {
  min-width: 0;
  margin-top: var(--dw-space-4);
  padding-top: var(--dw-space-3);
  border-top: 1px solid var(--dw-line);
}

.row-section-heading {
  align-items: baseline;
}

.row-section-heading h5 {
  margin: 0;
  color: var(--dw-ink-strong);
  font-size: var(--dw-body);
  font-weight: 750;
}

.row-section-heading span {
  font-family: var(--dw-font-code);
  font-size: var(--dw-label);
  font-weight: 600;
  letter-spacing: 0.03em;
}

.finding-list {
  display: grid;
  gap: var(--dw-space-3);
  margin-top: var(--dw-space-3);
}

.finding-item {
  min-width: 0;
  padding: var(--dw-space-3);
  background: var(--dw-risk-wash);
  border: 1px solid rgba(224, 82, 82, 0.24);
  border-left: 3px solid var(--dw-risk);
  border-radius: 8px;
}

.finding-item header {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--dw-space-2);
}

.finding-item header strong {
  color: var(--dw-ink-strong);
  font-size: var(--dw-body);
  line-height: var(--dw-leading-body);
  overflow-wrap: anywhere;
}

.finding-severity {
  flex: 0 0 auto;
  padding: 4px 7px;
  font-size: var(--dw-label);
}

.finding-severity.is-critical,
.finding-severity.is-high {
  color: var(--dw-risk-strong);
  background: var(--dw-risk-wash);
}

.finding-item > p {
  margin: 7px 0 0;
  color: var(--dw-ink);
  font-size: var(--dw-body-small);
  line-height: var(--dw-leading-small);
  overflow-wrap: anywhere;
}

.finding-item dl {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dw-space-2) var(--dw-space-4);
  margin: var(--dw-space-3) 0 0;
}

.finding-item dl > div {
  min-width: 0;
}

.finding-item dd {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 4px 8px;
  margin: 4px 0 0;
  color: var(--dw-ink);
  font-size: var(--dw-body-small);
  overflow-wrap: anywhere;
}

.row-none {
  margin: var(--dw-space-3) 0 0;
  color: var(--dw-ink-muted);
  font-size: var(--dw-body-small);
}

.row-evidence-sequences {
  margin: var(--dw-space-3) 0 0;
  color: var(--dw-ink-muted);
  font-size: var(--dw-body-small);
  overflow-wrap: anywhere;
}

.trace-details {
  margin-top: var(--dw-space-2);
  background: var(--dw-surface);
  border: 1px solid var(--dw-line);
  border-radius: 8px;
}

.trace-details summary {
  padding: 10px 12px;
}

.trace-list {
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0 12px;
  list-style: none;
}

.trace-list li {
  min-width: 0;
  padding: 13px 0;
  border-top: 1px solid var(--dw-line);
}

.trace-event-heading {
  display: flex;
  min-width: 0;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 9px;
}

.trace-sequence {
  color: var(--dw-evidence-strong);
  font-family: var(--dw-font-code);
  font-size: var(--dw-code);
  font-weight: 700;
}

.event-type {
  padding: 4px 7px;
  font-size: var(--dw-label);
}

.event-type.is-primary {
  color: var(--dw-action-strong);
  background: var(--dw-action-wash);
}

.event-type.is-warning {
  color: var(--dw-warning);
  background: var(--dw-warning-wash);
}

.event-type.is-danger {
  color: var(--dw-risk-strong);
  background: var(--dw-risk-wash);
}

.event-type.is-success {
  color: var(--dw-evidence-strong);
  background: var(--dw-evidence-wash);
}

.trace-event-heading time {
  margin-left: auto;
  color: var(--dw-ink-muted);
  font-family: var(--dw-font-code);
  font-size: var(--dw-label);
}

.trace-summary {
  margin: 8px 0 0;
  color: var(--dw-ink);
  font-size: var(--dw-body-small);
  line-height: var(--dw-leading-small);
  overflow-wrap: anywhere;
}

.trace-evidence {
  display: grid;
  grid-template-columns: minmax(110px, auto) minmax(0, 1fr);
  gap: 4px 10px;
  margin-top: 9px;
  color: var(--dw-ink-muted);
  font-size: var(--dw-body-small);
}

.trace-evidence code {
  min-width: 0;
  overflow-wrap: anywhere;
}

.trace-details pre {
  max-width: 100%;
  margin: 10px 0 0;
  padding: 10px;
  color: #d7e5f5;
  background: #0b2340;
  border-radius: 6px;
  font-family: var(--dw-font-code);
  font-size: var(--dw-code);
  line-height: var(--dw-leading-code);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}

@media (min-width: 1920px) {
  .differential-workspace {
    --dw-h2: var(--f045-type-h2-wide, var(--type-h2-wide, 29px));
    --dw-h3: var(--f045-type-h3-wide, var(--type-h3-wide, 21px));
    --dw-body: var(--f045-type-body-wide, var(--type-body-wide, 17px));
    --dw-body-small: var(--f045-type-body-small-wide, var(--type-body-small-wide, 15px));
    --dw-code: var(--f045-type-code-wide, var(--type-code-wide, 14px));
  }
}

@media (max-width: 1100px) {
  .differential-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .summary-item:nth-child(3) {
    border-left: 0;
    border-top: 1px solid var(--dw-line);
  }

  .summary-item:nth-child(4) {
    border-top: 1px solid var(--dw-line);
  }

  .technical-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .differential-heading {
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
  }

  .differential-heading-action {
    align-items: stretch;
    justify-content: flex-start;
    flex-direction: column;
  }

  .differential-run {
    width: 100%;
  }

  .differential-selection,
  .differential-summary,
  .technical-grid,
  .result-meta,
  .row-decisions {
    grid-template-columns: minmax(0, 1fr);
  }

  .summary-item,
  .summary-item:nth-child(3),
  .summary-item:nth-child(4) {
    border-top: 1px solid var(--dw-line);
    border-left: 0;
  }

  .summary-item:first-child {
    border-top: 0;
  }

  .technical-wide {
    grid-column: auto;
  }

  .result-heading,
  .row-heading {
    align-items: flex-start;
    flex-direction: column;
  }

  .result-status,
  .match-status {
    align-self: flex-start;
  }

  .finding-item dl {
    grid-template-columns: minmax(0, 1fr);
  }

  .trace-event-heading time {
    width: 100%;
    margin-left: 0;
  }

  .trace-evidence {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (prefers-reduced-motion: reduce) {
  .differential-run {
    transition: none;
  }
}
</style>
