<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import AcceptanceRunsView from "./components/AcceptanceRunsView.vue";
import AttackChainReportView from "./components/AttackChainReportView.vue";
import AttackPlansWorkspace from "./components/AttackPlansWorkspace.vue";
import BlockedExecutionView from "./components/BlockedExecutionView.vue";
import DifferentialAuditWorkspace from "./components/DifferentialAuditWorkspace.vue";
import DocumentImportView from "./components/DocumentImportView.vue";
import EnterpriseOnboardingView from "./components/EnterpriseOnboardingView.vue";
import GuidedAuditFlow from "./components/GuidedAuditFlow.vue";
import GuidedReplayComparison from "./components/GuidedReplayComparison.vue";
import LocalDiagnosticsView from "./components/LocalDiagnosticsView.vue";
import ProviderReadinessView from "./components/ProviderReadinessView.vue";
import ProviderSetupView from "./components/ProviderSetupView.vue";
import SecurityContractEditor from "./components/SecurityContractEditor.vue";
import WorkspaceOperationsView from "./components/WorkspaceOperationsView.vue";
import { apiFetch } from "./api";
import brandMarkUrl from "./assets/agent-audit-mark.png";
import type {
  Actor,
  ActorRole,
  AttackerType,
  AttackAttempt,
  AttackCase,
  AttackExecutionResult,
  BlockedExecution,
  AttackPlan,
  AttackPlanExecutionResult,
  AssistantQueryRequest,
  AssistantQueryResult,
  AttackChainReport,
  AuditRunDetail,
  AuditRuntimeSnapshot,
  AuditRunSummary,
  PersistedReplay,
  BenchmarkResult,
  DifferentialAuditResult,
  DifferentialTargetProfileId,
  DifferentialTask,
  DocumentCatalog,
  DocumentImportResult,
  EmptyProviderReadinessRequest,
  Finding,
  GroundTruthCategory,
  GroundTruthCase,
  GroundTruthExecutionStatus,
  GroundTruthExecutionType,
  GroundTruthOutcome,
  ProviderReadinessResult,
  ProviderSetupState,
  RedTeamScan,
  ReplayAttempt,
  ReplayResult,
  RetrievalEngineId,
  RetrievalEvaluationCaseResult,
  RetrievalEvaluationResult,
  RetrievalRankedDocument,
  ScanState,
  ScanStopReason,
  SecurityContract,
  SecurityContractPreview,
  StartPersistedReplayRequest,
  StartDifferentialAuditRequest,
  StartScanRequest,
  TraceEvent,
  TraceEventType,
  TraceEvaluationRequest,
  TraceEvaluationResult,
} from "@agent-audit/contracts";

type WorkspaceId = "guided" | "setup" | "live" | "findings";
type DisplayScale = "standard" | "large";
type OnboardingPath = "demo" | "custom";
type OnboardingTask = "provider" | "documents" | "contract" | "audit" | "result";

class ApiResponseError extends Error {
  readonly status: number;
  readonly operationId: string | null;

  constructor(status: number, detail: string, operationId: string | null) {
    super(detail || `请求失败（${status}）`);
    this.name = "ApiResponseError";
    this.status = status;
    this.operationId = operationId;
  }
}

const DISPLAY_SCALE_STORAGE_KEY = "agent-audit.display-scale";

function readDisplayScale(): DisplayScale {
  if (typeof window === "undefined") {
    return "large";
  }
  return window.localStorage.getItem(DISPLAY_SCALE_STORAGE_KEY) === "standard"
    ? "standard"
    : "large";
}

const displayScale = ref<DisplayScale>(readDisplayScale());

function setDisplayScale(scale: DisplayScale): void {
  displayScale.value = scale;
  document.documentElement.dataset.displayScale = scale;
  window.localStorage.setItem(DISPLAY_SCALE_STORAGE_KEY, scale);
}

if (typeof document !== "undefined") {
  document.documentElement.dataset.displayScale = displayScale.value;
}

const workspaceOptions: Array<{
  id: WorkspaceId;
  index: string;
  label: string;
  caption: string;
}> = [
  {
    id: "guided",
    index: "01",
    label: "核心验收",
    caption: "发现风险 · 模拟复测",
  },
  {
    id: "setup",
    index: "02",
    label: "设置与计划",
    caption: "连接 · 规则 · 资料",
  },
  {
    id: "live",
    index: "03",
    label: "扫描记录",
    caption: "状态 · Trace · 历史",
  },
  {
    id: "findings",
    index: "04",
    label: "验收证据",
    caption: "Finding · 对比 · 导出",
  },
];

const activeWorkspace = ref<WorkspaceId>("guided");
const onboardingPath = ref<OnboardingPath | null>(null);

const actors = ref<Actor[]>([]);
const selectedActorId = ref("");
const message = ref("");
const result = ref<AssistantQueryResult | null>(null);

const actorsLoading = ref(false);
const queryLoading = ref(false);
const actorsError = ref("");
const queryError = ref("");

const securityContract = ref<SecurityContract | null>(null);
const contractLoading = ref(false);
const contractSaving = ref(false);
const contractPreview = ref<SecurityContractPreview | null>(null);
const contractPreviewLoading = ref(false);
const contractError = ref("");
const contractNotice = ref("");

const evaluation = ref<TraceEvaluationResult | null>(null);
const evaluationTraceEvents = ref<TraceEvent[]>([]);
const evaluationLoading = ref(false);
const evaluationError = ref("");
const semanticReviewLoading = ref(false);
const semanticReviewError = ref("");

const attackCases = ref<AttackCase[]>([]);
const attackCasesLoading = ref(false);
const attackCasesError = ref("");
const attackExecutionError = ref("");
const blockedCaseResult = ref<BlockedExecution | null>(null);
const blockedPlanResult = ref<BlockedExecution | null>(null);
const executingCaseId = ref("");

const attackPlans = ref<AttackPlan[]>([]);
const attackPlansLoading = ref(false);
const attackPlansError = ref("");
const attackPlanExecutionError = ref("");
const executingPlanId = ref("");
const scanPlanId = ref("");
const guidedSelectionPlanId = ref("");
const scanMaxRounds = ref<2 | 3>(3);
const redTeamScan = ref<RedTeamScan | null>(null);
const scanLoading = ref(false);
const scanError = ref("");
const scanErrorDetails = ref("");
const scanHistory = ref<AuditRunSummary[]>([]);
const scanHistoryLoading = ref(false);
const scanHistoryError = ref("");
const selectedScanId = ref("");
const selectedScanDetail = ref<AuditRunDetail | null>(null);
const scanDetailLoading = ref(false);
const scanDetailError = ref("");
const persistedReplayLoading = ref(false);
const persistedReplayError = ref("");
const runtimeSnapshot = ref<AuditRuntimeSnapshot | null>(null);
const runtimeLoading = ref(false);
const runtimeError = ref("");
const providerSetupState = ref<ProviderSetupState | null>(null);
const providerSetupLoading = ref(true);
const documentCatalog = ref<DocumentCatalog | null>(null);
const documentCatalogLoaded = ref(false);
let scanRequestToken = 0;
let scanHistoryRequestToken = 0;
let scanDetailRequestToken = 0;
let persistedReplayRequestToken = 0;
let runtimeRequestToken = 0;
const differentialTasks = ref<DifferentialTask[]>([]);
const differentialTasksLoading = ref(false);
const differentialTasksError = ref("");
const differentialTaskId = ref("");
const differentialProfileId = ref<DifferentialTargetProfileId | "">("");
const differentialAuditResult = ref<DifferentialAuditResult | null>(null);
const differentialAuditLoading = ref(false);
const differentialAuditError = ref("");
let differentialRequestToken = 0;
const retrievalEvaluationResult = ref<RetrievalEvaluationResult | null>(null);
const retrievalEvaluationLoading = ref(false);
const retrievalEvaluationError = ref("");
let retrievalEvaluationRequestToken = 0;
const replayResult = ref<ReplayResult | null>(null);
const replayLoading = ref(false);
const replayError = ref("");
const replayErrorDetails = ref("");
const replayPlanId = ref("");
const attackChainReport = ref<AttackChainReport | null>(null);
const attackChainReportLoading = ref(false);
const attackChainReportError = ref("");

const groundTruthCases = ref<GroundTruthCase[]>([]);
const groundTruthCasesLoading = ref(false);
const groundTruthCasesError = ref("");
const benchmarkResult = ref<BenchmarkResult | null>(null);
const benchmarkLoading = ref(false);
const benchmarkError = ref("");
let benchmarkRequestToken = 0;

const providerReadinessResult = ref<ProviderReadinessResult | null>(null);
const providerReadinessLoading = ref(false);
const providerReadinessError = ref("");

const guidedPlan = computed(
  () =>
    (guidedSelectionPlanId.value
      ? attackPlans.value.find((plan) => plan.id === guidedSelectionPlanId.value)
      : undefined) ?? attackPlans.value.find((plan) => plan.basisType === "source_sink") ?? null,
);

const singleAttackPlan = computed<AttackPlan | null>(() =>
  attackPlans.value.length === 1 ? attackPlans.value[0] ?? null : null,
);

const onboardingUserDocumentCount = computed(
  () =>
    documentCatalog.value?.documents.filter(
      (document) => !document.labels.some((label) => label.toUpperCase() === "SYNTHETIC"),
    ).length ?? 0,
);

const onboardingHasAudit = computed(
  () =>
    Boolean(
      redTeamScan.value &&
        guidedPlan.value &&
        redTeamScan.value.planId === guidedPlan.value.id,
    ),
);

const onboardingTask = computed<OnboardingTask | null>(() => {
  if (onboardingPath.value === null) {
    return null;
  }

  if (providerSetupLoading.value || providerSetupState.value?.configured !== true) {
    return "provider";
  }

  if (onboardingPath.value === "demo") {
    if (!guidedPlan.value) {
      return "contract";
    }
    return onboardingHasAudit.value ? "result" : "audit";
  }

  if (!documentCatalogLoaded.value || onboardingUserDocumentCount.value === 0) {
    return "documents";
  }
  if (attackPlansLoading.value || !guidedPlan.value) {
    return "contract";
  }
  return onboardingHasAudit.value ? "result" : "audit";
});

const guidedHasFinding = computed(() =>
  Boolean(
    guidedPlan.value &&
      redTeamScan.value?.planId === guidedPlan.value.id &&
      redTeamScan.value.attempts.some((attempt) => attempt.evaluation.findings.length > 0),
  ),
);

const roleLabels: Record<ActorRole, string> = {
  visitor: "访客",
  employee: "员工",
  sales: "销售",
  hr: "人力资源",
  finance_manager: "财务经理",
  admin: "管理员",
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

const attackerTypeLabels: Record<AttackerType, string> = {
  outside_in: "Outside-in · 外部攻击",
  inside_out: "Inside-out · 内部滥用",
};

const scanStateLabels: Record<ScanState, string> = {
  profiling: "目标画像",
  contract_analysis: "Contract 分析",
  goal_selection: "目标选择",
  variant_generation: "变体生成",
  execution: "攻击执行",
  trace_observation: "Trace 观察",
  mutate: "受控变异",
  stopped: "已停止",
};

const scanStopReasonLabels: Record<ScanStopReason, string> = {
  finding_detected: "发现 Finding",
  no_new_variant: "没有新变体",
  max_rounds_reached: "达到轮数上限",
};

const executionTypeLabels: Record<GroundTruthExecutionType, string> = {
  assistant_query: "Assistant Query",
  attack_plan: "Attack Plan",
  replay: "Replay",
};

const groundTruthOutcomeLabels: Record<GroundTruthOutcome, string> = {
  evaluation_passed: "Evaluation passed",
  evaluation_failed: "Evaluation failed",
  replay_passed: "Replay passed",
  replay_failed: "Replay failed",
};

const selectedActor = computed(() =>
  actors.value.find((actor) => actor.id === selectedActorId.value),
);

const replayAttempts = computed(() => {
  if (!replayResult.value) {
    return [];
  }

  return replayAttemptEntries(replayResult.value);
});

function replayAttemptEntries(replay: ReplayResult) {
  return [
    {
      key: "before",
      label: "BEFORE · 漏洞配置",
      attempt: replay.before,
    },
    {
      key: "after",
      label: "AFTER · 安全 Profile 模拟",
      attempt: replay.after,
    },
  ];
}

function persistedReplayAttempts(replay: ReplayResult) {
  return replayAttemptEntries(replay);
}

const groundTruthTypeSummary = computed(() => {
  const types: GroundTruthExecutionType[] = ["assistant_query", "attack_plan", "replay"];
  return types
    .map((type) => ({
      type,
      count: groundTruthCases.value.filter((groundTruthCase) => groundTruthCase.executionType === type)
        .length,
    }))
    .filter((summary) => summary.count > 0);
});

const groundTruthCategoryOrder: GroundTruthCategory[] = [
  "normal_behavior",
  "internal_authorization",
  "outside_in_source_sink",
  "tool_threshold_replay",
];

const groundTruthCategoryLabels: Record<GroundTruthCategory, string> = {
  normal_behavior: "正常行为",
  internal_authorization: "内部业务越权",
  outside_in_source_sink: "Outside-in / Source→Sink",
  tool_threshold_replay: "工具阈值与 Replay",
};

const groundTruthExecutionStatusLabels: Record<GroundTruthExecutionStatus, string> = {
  completed: "COMPLETED · 已完成",
  blocked: "BLOCKED · 已阻断",
};

const groundTruthCategorySummary = computed(() =>
  groundTruthCategoryOrder.map((category) => ({
    category,
    count: groundTruthCases.value.filter((groundTruthCase) => groundTruthCase.category === category)
      .length,
  })),
);

const benchmarkCategorySummary = computed(() => {
  if (benchmarkResult.value) {
    const backendCounts = benchmarkResult.value.metrics.categoryCounts;
    return groundTruthCategoryOrder.map((category) => ({
      category,
      count: backendCounts[category],
    }));
  }

  return groundTruthCategoryOrder.map((category) => ({
    category,
    count:
      groundTruthCategorySummary.value.find((summary) => summary.category === category)?.count ?? 0,
  }));
});

const sortedTraceEvents = computed(() => {
  const traceEvents = result.value?.traceEvents ?? [];
  return [...traceEvents].sort((left, right) => left.sequence - right.sequence);
});

const sortedScanTransitions = computed(() => {
  const transitions = redTeamScan.value?.stateTransitions ?? [];
  return [...transitions].sort((left, right) => left.sequence - right.sequence);
});

const scanUiStatus = computed<"idle" | "loading" | "success" | "error">(() => {
  if (scanLoading.value) {
    return "loading";
  }
  if (scanError.value) {
    return "error";
  }
  if (redTeamScan.value) {
    return "success";
  }
  return "idle";
});

const showUnifiedScanEmpty = computed(
  () =>
    !scanLoading.value &&
    !scanError.value &&
    !redTeamScan.value &&
    !scanHistoryLoading.value &&
    !scanHistoryError.value &&
    scanHistory.value.length === 0,
);

const scanUiStatusLabels: Record<"idle" | "loading" | "success" | "error", string> = {
  idle: "IDLE · 待启动",
  loading: "RUNNING · 执行中",
  success: "COMPLETED · 已完成",
  error: "ERROR · 执行失败",
};

const differentialStatusMessages: Record<number, string> = {
  404: "任务或目标 Profile 不存在（404）",
  422: "所选 Profile 不受当前任务支持（422）",
  502: "Provider 响应错误（502），请检查 Provider 日志",
  503: "Provider 未配置或暂不可用（503）",
};

const retrievalEngineLabels: Record<RetrievalEngineId, string> = {
  tfidf: "TF-IDF · lexical baseline",
  embedding: "Embedding · selected engine",
};

const retrievalEvaluationStatusMessages: Record<number, string> = {
  503: "Embedding 模型未配置或暂不可用（503），请检查本地 Embedding 模型/缓存与 API 日志",
};

const retrievalEvaluationUiStatus = computed<"idle" | "loading" | "success" | "error">(() => {
  if (retrievalEvaluationLoading.value) {
    return "loading";
  }
  if (retrievalEvaluationError.value) {
    return "error";
  }
  if (retrievalEvaluationResult.value) {
    return "success";
  }
  return "idle";
});

const retrievalEvaluationUiStatusLabels: Record<
  "idle" | "loading" | "success" | "error",
  string
> = {
  idle: "IDLE · 待运行",
  loading: "RUNNING · 对比中",
  success: "COMPLETED · 对比完成",
  error: "ERROR · 执行失败",
};

const canSubmit = computed(
  () =>
    !actorsLoading.value &&
    !queryLoading.value &&
    Boolean(selectedActorId.value) &&
    Boolean(message.value.trim()),
);

const selectedDifferentialTask = computed(() =>
  differentialTasks.value.find((task) => task.id === differentialTaskId.value),
);

function eventTypeLabel(type: TraceEventType): string {
  return eventLabels[type];
}

function eventTone(type: TraceEventType):
  | "primary"
  | "success"
  | "warning"
  | "danger"
  | "info" {
  switch (type) {
    case "source":
      return "primary";
    case "retrieval":
      return "primary";
    case "authorization":
      return "warning";
    case "tool_call":
      return "danger";
    case "tool_result":
      return "success";
    case "sink":
      return "danger";
    case "model_response":
      return "success";
    default:
      return "info";
  }
}

function formatOccurredAt(occurredAt: string): string {
  const date = new Date(occurredAt);
  if (Number.isNaN(date.getTime())) {
    return occurredAt;
  }

  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatHistoryDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function hasDetails(event: TraceEvent): boolean {
  return Object.keys(event.details).length > 0;
}

function detailText(details: Record<string, unknown>, key: string): string | null {
  const value = details[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function endpointText(
  details: Record<string, unknown>,
  typeKey: "sourceType" | "sinkType",
  idKey: "sourceId" | "sinkId",
): string | null {
  const type = detailText(details, typeKey);
  const id = detailText(details, idKey);
  if (!type || !id) {
    return null;
  }

  return `${type}/${id}`;
}

function flowSummary(event: TraceEvent): string | null {
  if (event.type !== "source" && event.type !== "sink") {
    return null;
  }

  const source = endpointText(event.details, "sourceType", "sourceId");
  const sink = endpointText(event.details, "sinkType", "sinkId");
  if (source && sink) {
    return `${source} → ${sink}`;
  }
  if (event.type === "source" && source) {
    return `来源 ${source}`;
  }
  if (event.type === "sink" && sink) {
    return `流向 ${sink}`;
  }

  return null;
}

function formatDetails(details: Record<string, unknown>): string {
  return JSON.stringify(details, null, 2) ?? "{}";
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "{}";
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
  { key: "beforeValue", label: "Before" },
  { key: "afterValue", label: "After" },
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

function traceEvidenceRows(event: TraceEvent): TraceEvidenceRow[] {
  return traceEvidenceFields.flatMap(({ key, label }) => {
    const value = detailValueText(event.details[key]);
    return value ? [{ label, value }] : [];
  });
}

function traceEvidenceSummary(events: TraceEvent[]): TraceEvidenceSummary {
  const sourceTrustLevels = collectDetailValues(events, ["sourceTrustLevels", "trustLevel"]);
  const resourceIds = collectDetailValues(events, ["resourceIds", "documentIds"]);
  const resourceLabels = collectDetailValues(events, ["resourceLabels"]);
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
    flow: `${sourceEndpoints.join(" / ") || "Source"} → ${
      sinkEndpoints.join(" / ") || destinations.join(" / ") || "Sink"
    }`,
    sourceTrustLevels,
    resourceIds,
    resourceLabels,
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
    { label: "Source trust", values: summary.sourceTrustLevels },
    { label: "Resource IDs", values: summary.resourceIds },
    { label: "Resource labels", values: summary.resourceLabels },
    { label: "Destination", values: summary.destinations },
    { label: "External", values: summary.external },
    { label: "Approval", values: summary.approvals },
    { label: "Records (actual / max)", values: recordValues },
    { label: "Rule IDs", values: summary.ruleIds },
  ];
  return fields.flatMap(({ label, values }) =>
    values.length > 0 ? [{ label, value: values.join(" · ") }] : [],
  );
}

const findingCategoryLabels: Record<Finding["category"], string> = {
  resource_authorization_bypass: "资源授权绕过",
  tool_authorization_bypass: "工具授权绕过",
  external_sink_policy_violation: "外部 Sink 策略违规",
  tool_business_policy_violation: "工具业务约束违规",
};

const findingSeverityLabels: Record<Finding["severity"], string> = {
  high: "高危 High",
  critical: "严重 Critical",
};

function findingCategoryLabel(category: Finding["category"]): string {
  return `${findingCategoryLabels[category]} · ${category}`;
}

function findingSeverityLabel(severity: Finding["severity"]): string {
  return findingSeverityLabels[severity];
}

function findingRuleLabel(finding: Finding): string {
  return finding.ruleId ?? "default deny（默认拒绝）";
}

function attackerTypeLabel(type: AttackerType): string {
  return attackerTypeLabels[type];
}

function attackerTypeTone(type: AttackerType): "primary" | "warning" {
  return type === "outside_in" ? "primary" : "warning";
}

function planPolicySummary(plan: AttackPlan): string | null {
  if (!securityContract.value) {
    return null;
  }

  const toolRule = securityContract.value.toolRules.find((rule) => rule.id === plan.basisRuleId);
  if (toolRule) {
    const parts = [`maxRecords=${toolRule.maxRecords ?? "—"}`];
    if (toolRule.requireApproval) {
      parts.push("approval required");
    }
    return parts.join(" · ");
  }

  const sinkRule = securityContract.value.sinkRules?.find((rule) => rule.id === plan.basisRuleId);
  if (sinkRule) {
    const parts = [`external=${booleanLabel(sinkRule.allowExternal)}`];
    if (sinkRule.requireApproval) {
      parts.push("approval required");
    }
    if (sinkRule.blockedSourceTrustLevels.length > 0) {
      parts.push(`blocked trust=${sinkRule.blockedSourceTrustLevels.join(", ")}`);
    }
    if (sinkRule.matchLabels.length > 0) {
      parts.push(`labels=${sinkRule.matchLabels.join(", ")}`);
    }
    return parts.join(" · ");
  }

  return null;
}

function replayExecutionStatusLabel(status: ReplayAttempt["executionStatus"]): string {
  return status === "completed" ? "COMPLETED · 已完成" : "BLOCKED · 已阻断";
}

function replayExecutionStatusType(
  status: ReplayAttempt["executionStatus"],
): "success" | "warning" {
  return status === "completed" ? "success" : "warning";
}

function booleanLabel(value: boolean): string {
  return value ? "true" : "false";
}

function evaluationStatusLabel(status: TraceEvaluationResult["status"]): string {
  return status === "passed" ? "PASSED · 通过" : "FAILED · 失败";
}

function evaluationStatusType(
  status: TraceEvaluationResult["status"],
): "success" | "danger" {
  return status === "passed" ? "success" : "danger";
}

function executionTypeLabel(type: GroundTruthExecutionType): string {
  return executionTypeLabels[type];
}

function groundTruthOutcomeLabel(outcome: GroundTruthOutcome): string {
  return groundTruthOutcomeLabels[outcome];
}

function groundTruthCategoryLabel(category: GroundTruthCategory): string {
  return groundTruthCategoryLabels[category];
}

function groundTruthExecutionStatusLabel(status: GroundTruthExecutionStatus): string {
  return groundTruthExecutionStatusLabels[status];
}

function benchmarkPercentageLabel(value: number | null): string {
  return value === null ? "null · unavailable" : formatPercentage(value);
}

function benchmarkNullableNumberLabel(value: number | null): string {
  return value === null ? "null · unavailable" : formatDurationMs(value);
}

function benchmarkNullableDurationLabel(value: number | null): string {
  return value === null ? "null · unavailable" : `${formatDurationMs(value)} ms`;
}

function providerUsageLabel(value: number | null): string {
  return value === null ? "null · unavailable" : String(value);
}

function estimatedCostLabel(value: number | null): string {
  return value === null ? "null · unavailable" : `$${value.toFixed(4)}`;
}

function findingCategoriesLabel(categories: Finding["category"][]): string {
  if (categories.length === 0) {
    return "—";
  }

  return categories
    .map((category) => findingCategoryLabels[category] ?? category)
    .join("、");
}

function formatPercentage(value: number | null): string {
  return value === null ? "N/A" : `${(value * 100).toFixed(1)}%`;
}

function scanStateLabel(state: ScanState): string {
  return scanStateLabels[state];
}

function scanStateTone(
  state: ScanState,
): "primary" | "success" | "warning" | "danger" | "info" {
  switch (state) {
    case "profiling":
    case "contract_analysis":
    case "goal_selection":
      return "info";
    case "variant_generation":
    case "mutate":
      return "primary";
    case "execution":
    case "trace_observation":
      return "warning";
    case "stopped":
      return "success";
    default:
      return "info";
  }
}

function scanStopReasonLabel(reason: ScanStopReason): string {
  return scanStopReasonLabels[reason];
}

function scanStopReasonTone(reason: ScanStopReason): "success" | "warning" | "danger" {
  switch (reason) {
    case "finding_detected":
      return "danger";
    case "no_new_variant":
      return "warning";
    case "max_rounds_reached":
      return "success";
    default:
      return "warning";
  }
}

function formatDurationMs(value: number): string {
  if (!Number.isFinite(value)) {
    return String(value);
  }

  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, "");
}

function redTeamScanPayload(payload: unknown): RedTeamScan {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Red-Team Scan 响应格式无效");
  }

  const candidate = payload as Partial<RedTeamScan>;
  if (
    typeof candidate.id !== "string" ||
    candidate.status !== "completed" ||
    !Array.isArray(candidate.stateTransitions) ||
    !Array.isArray(candidate.attempts)
  ) {
    throw new Error("Red-Team Scan 响应缺少状态转换或 Attempt");
  }

  return payload as RedTeamScan;
}

function isAuditRuntimeSnapshot(value: unknown): value is AuditRuntimeSnapshot {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<AuditRuntimeSnapshot>;
  return (
    typeof candidate.provider === "string" &&
    (candidate.model === null || typeof candidate.model === "string") &&
    (candidate.retrieverEngine === "embedding" || candidate.retrieverEngine === "tfidf") &&
    (candidate.retrieverModel === null || typeof candidate.retrieverModel === "string") &&
    (candidate.retrieverDimensions === null || typeof candidate.retrieverDimensions === "number") &&
    typeof candidate.indexedDocumentCount === "number" &&
    Number.isInteger(candidate.indexedDocumentCount) &&
    candidate.indexedDocumentCount >= 0
  );
}

function providerSetupPayload(payload: unknown): ProviderSetupState {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Provider 设置响应格式无效");
  }

  const candidate = payload as Partial<ProviderSetupState>;
  if (
    typeof candidate.configured !== "boolean" ||
    (candidate.settings !== null &&
      (typeof candidate.settings !== "object" || Array.isArray(candidate.settings))) ||
    typeof candidate.credentialConfigured !== "boolean" ||
    !isAuditRuntimeSnapshot(candidate.runtimeSnapshot)
  ) {
    throw new Error("Provider 设置响应缺少连接或 Runtime 状态");
  }

  return payload as ProviderSetupState;
}

function isAuditRunSummary(value: unknown): value is AuditRunSummary {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<AuditRunSummary>;
  return (
    typeof candidate.scanId === "string" &&
    typeof candidate.planId === "string" &&
    typeof candidate.contractId === "string" &&
    typeof candidate.contractVersion === "number" &&
    typeof candidate.targetProfileId === "string" &&
    candidate.status === "completed" &&
    (candidate.stopReason === "finding_detected" ||
      candidate.stopReason === "no_new_variant" ||
      candidate.stopReason === "max_rounds_reached") &&
    typeof candidate.attemptCount === "number" &&
    Number.isInteger(candidate.attemptCount) &&
    candidate.attemptCount >= 0 &&
    typeof candidate.findingCount === "number" &&
    Number.isInteger(candidate.findingCount) &&
    candidate.findingCount >= 0 &&
    typeof candidate.replayCount === "number" &&
    Number.isInteger(candidate.replayCount) &&
    candidate.replayCount >= 0 &&
    typeof candidate.startedAt === "string" &&
    typeof candidate.completedAt === "string" &&
    typeof candidate.durationMs === "number" &&
    Number.isFinite(candidate.durationMs) &&
    isAuditRuntimeSnapshot(candidate.runtimeSnapshot)
  );
}

function auditRunSummaryPayload(payload: unknown): AuditRunSummary[] {
  if (!Array.isArray(payload) || !payload.every(isAuditRunSummary)) {
    throw new Error("Scan 历史列表响应格式无效");
  }

  return payload;
}

function auditRunDetailPayload(payload: unknown): AuditRunDetail {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Scan 历史详情响应格式无效");
  }

  const candidate = payload as Partial<AuditRunDetail>;
  if (
    !candidate.scan ||
    typeof candidate.scan.id !== "string" ||
    !candidate.planSnapshot ||
    typeof candidate.planSnapshot.id !== "string" ||
    !candidate.contractSnapshot ||
    typeof candidate.contractSnapshot.id !== "string" ||
    !candidate.targetProfileSnapshot ||
    typeof candidate.targetProfileSnapshot.id !== "string" ||
    !candidate.runtimeSnapshot ||
    !isAuditRuntimeSnapshot(candidate.runtimeSnapshot) ||
    !Array.isArray(candidate.replays) ||
    !candidate.replays.every(isPersistedReplay)
  ) {
    throw new Error("Scan 历史详情缺少不可变快照或 Replay 历史");
  }

  return payload as AuditRunDetail;
}

function isPersistedReplay(value: unknown): value is PersistedReplay {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<PersistedReplay>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.createdAt === "string" &&
    Boolean(candidate.replay) &&
    typeof candidate.replay?.id === "string"
  );
}

function persistedReplayPayload(payload: unknown): PersistedReplay {
  if (!isPersistedReplay(payload)) {
    throw new Error("持久化 Replay 响应格式无效");
  }

  return payload;
}

function attemptTraceEvents(attempt: AttackAttempt): TraceEvent[] {
  return [...attempt.queryResult.traceEvents].sort((left, right) => left.sequence - right.sequence);
}

function differentialTaskPayload(payload: unknown): DifferentialTask[] {
  if (!Array.isArray(payload)) {
    throw new Error("Multi-Identity Differential 任务响应格式无效");
  }

  return payload as DifferentialTask[];
}

function differentialAuditPayload(
  payload: unknown,
  taskId: string,
  targetProfileId: DifferentialTargetProfileId,
): DifferentialAuditResult {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Multi-Identity Differential 响应格式无效");
  }

  const candidate = payload as Partial<DifferentialAuditResult>;
  if (
    typeof candidate.id !== "string" ||
    !candidate.task ||
    candidate.task.id !== taskId ||
    candidate.targetProfileId !== targetProfileId ||
    (candidate.status !== "passed" && candidate.status !== "failed") ||
    typeof candidate.contractId !== "string" ||
    typeof candidate.contractVersion !== "number" ||
    typeof candidate.mismatchCount !== "number" ||
    !Array.isArray(candidate.rows)
  ) {
    throw new Error("Multi-Identity Differential 响应缺少当前任务的矩阵证据");
  }

  return payload as DifferentialAuditResult;
}

function invalidateDifferentialAudit(): void {
  differentialRequestToken += 1;
  differentialAuditResult.value = null;
  differentialAuditError.value = "";
  differentialAuditLoading.value = false;
}

function handleDifferentialTaskChange(): void {
  invalidateDifferentialAudit();
  differentialProfileId.value = selectedDifferentialTask.value?.defaultTargetProfileId ?? "";
}

function updateDifferentialTask(taskId: string): void {
  differentialTaskId.value = taskId;
  handleDifferentialTaskChange();
}

function handleDifferentialProfileChange(): void {
  invalidateDifferentialAudit();
}

function updateDifferentialProfile(profileId: DifferentialTargetProfileId | ""): void {
  differentialProfileId.value = profileId;
  handleDifferentialProfileChange();
}

function retrievalEngineLabel(engine: RetrievalEngineId): string {
  return retrievalEngineLabels[engine];
}

function retrievalRankLabel(rank: number | null): string {
  return rank === null ? "未出现在 Top-3" : `#${rank}`;
}

function retrievalScoreLabel(score: number): string {
  return Number.isFinite(score) ? score.toFixed(4) : String(score);
}

function retrievalMetricLabel(value: number): string {
  return Number.isFinite(value) ? value.toFixed(4) : String(value);
}

function isRetrievalRank(value: unknown): value is number | null {
  return (
    value === null ||
    (typeof value === "number" && Number.isInteger(value) && value > 0)
  );
}

function isRetrievalRankedDocument(value: unknown): value is RetrievalRankedDocument {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<RetrievalRankedDocument>;
  return (
    typeof candidate.rank === "number" &&
    Number.isInteger(candidate.rank) &&
    candidate.rank > 0 &&
    typeof candidate.documentId === "string" &&
    typeof candidate.title === "string" &&
    typeof candidate.score === "number" &&
    Number.isFinite(candidate.score)
  );
}

function isRetrievalEvaluationCaseResult(value: unknown): value is RetrievalEvaluationCaseResult {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  const candidate = value as Partial<RetrievalEvaluationCaseResult>;
  return (
    typeof candidate.caseId === "string" &&
    typeof candidate.query === "string" &&
    typeof candidate.expectedDocumentId === "string" &&
    Array.isArray(candidate.tfidfResults) &&
    candidate.tfidfResults.every(isRetrievalRankedDocument) &&
    Array.isArray(candidate.embeddingResults) &&
    candidate.embeddingResults.every(isRetrievalRankedDocument) &&
    isRetrievalRank(candidate.tfidfExpectedRank) &&
    isRetrievalRank(candidate.embeddingExpectedRank)
  );
}

function retrievalEvaluationPayload(payload: unknown): RetrievalEvaluationResult {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Retrieval Evaluation 响应格式无效");
  }

  const candidate = payload as Partial<RetrievalEvaluationResult>;
  const metrics = candidate.metrics;
  if (
    typeof candidate.id !== "string" ||
    candidate.selectedEngine !== "embedding" ||
    typeof candidate.modelName !== "string" ||
    typeof candidate.dimensions !== "number" ||
    !Number.isFinite(candidate.dimensions) ||
    typeof candidate.indexedDocumentCount !== "number" ||
    !Number.isInteger(candidate.indexedDocumentCount) ||
    candidate.indexedDocumentCount < 0 ||
    !Array.isArray(candidate.cases) ||
    !candidate.cases.every(isRetrievalEvaluationCaseResult) ||
    !metrics ||
    !Number.isInteger(metrics.caseCount) ||
    metrics.caseCount < 0 ||
    !Number.isInteger(metrics.tfidfTop1Hits) ||
    metrics.tfidfTop1Hits < 0 ||
    !Number.isInteger(metrics.embeddingTop1Hits) ||
    metrics.embeddingTop1Hits < 0 ||
    typeof metrics.tfidfMrr !== "number" ||
    !Number.isFinite(metrics.tfidfMrr) ||
    typeof metrics.embeddingMrr !== "number" ||
    !Number.isFinite(metrics.embeddingMrr)
  ) {
    throw new Error("Retrieval Evaluation 响应缺少完整排名或指标证据");
  }

  return payload as RetrievalEvaluationResult;
}

async function loadAttackCases(): Promise<void> {
  attackCasesLoading.value = true;
  attackCasesError.value = "";

  try {
    const response = await apiFetch("/api/attack-cases");
    if (!response.ok) {
      throw await responseError(response);
    }

    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) {
      throw new Error("固定 Attack Case 响应格式无效");
    }

    attackCases.value = payload as AttackCase[];
  } catch (error) {
    attackCasesError.value = error instanceof Error ? error.message : "Attack Case 加载失败";
  } finally {
    attackCasesLoading.value = false;
  }
}

async function loadAttackPlans(): Promise<void> {
  attackPlansLoading.value = true;
  attackPlansError.value = "";

  try {
    const response = await apiFetch("/api/attack-plans");
    if (!response.ok) {
      throw await responseError(response);
    }

    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) {
      throw new Error("Attack Plan 响应格式无效");
    }

    attackPlans.value = payload as AttackPlan[];
    if (!attackPlans.value.some((plan) => plan.id === guidedSelectionPlanId.value)) {
      guidedSelectionPlanId.value = "";
    }
    if (!attackPlans.value.some((plan) => plan.id === scanPlanId.value)) {
      scanPlanId.value = attackPlans.value[0]?.id ?? "";
    }
  } catch (error) {
    attackPlansError.value = error instanceof Error ? error.message : "Attack Plan 加载失败";
  } finally {
    attackPlansLoading.value = false;
  }
}

async function loadScanHistory(preferredScanId?: string): Promise<void> {
  const requestToken = ++scanHistoryRequestToken;
  scanHistoryLoading.value = true;
  scanHistoryError.value = "";

  try {
    const response = await apiFetch("/api/scans?limit=20");
    if (!response.ok) {
      throw await responseError(response);
    }

    const summaries = auditRunSummaryPayload(await response.json());
    if (requestToken !== scanHistoryRequestToken) {
      return;
    }

    scanHistory.value = summaries;
    if (preferredScanId) {
      selectedScanId.value = preferredScanId;
    } else if (
      selectedScanId.value &&
      !summaries.some((summary) => summary.scanId === selectedScanId.value)
    ) {
      selectedScanId.value = "";
      selectedScanDetail.value = null;
      redTeamScan.value = null;
    }
  } catch (error) {
    if (requestToken !== scanHistoryRequestToken) {
      return;
    }

    scanHistoryError.value = error instanceof Error ? error.message : "Scan 历史加载失败";
  } finally {
    if (requestToken === scanHistoryRequestToken) {
      scanHistoryLoading.value = false;
    }
  }
}

async function loadRuntime(): Promise<void> {
  if (runtimeLoading.value) {
    return;
  }

  const requestToken = ++runtimeRequestToken;
  runtimeLoading.value = true;
  runtimeError.value = "";

  try {
    const response = await apiFetch("/api/runtime");
    if (!response.ok) {
      throw await responseError(response);
    }

    const payload: unknown = await response.json();
    if (!isAuditRuntimeSnapshot(payload)) {
      throw new Error("Runtime 响应格式无效");
    }
    if (requestToken !== runtimeRequestToken) {
      return;
    }

    runtimeSnapshot.value = payload;
  } catch (error) {
    if (requestToken !== runtimeRequestToken) {
      return;
    }

    runtimeError.value = error instanceof Error ? error.message : "Runtime 加载失败";
  } finally {
    if (requestToken === runtimeRequestToken) {
      runtimeLoading.value = false;
    }
  }
}

async function loadProviderSetupState(): Promise<void> {
  providerSetupLoading.value = true;

  try {
    const response = await apiFetch("/api/provider-setup");
    if (!response.ok) {
      throw await responseError(response);
    }

    providerSetupState.value = providerSetupPayload(await response.json());
  } catch {
    // ProviderSetupView renders the detailed boundary error. The onboarding
    // only needs to know that the connection has not been confirmed here.
    providerSetupState.value = null;
  } finally {
    providerSetupLoading.value = false;
  }
}

async function handleProviderSetupSaved(state: ProviderSetupState): Promise<void> {
  providerSetupState.value = state;
  runtimeSnapshot.value = state.runtimeSnapshot;
  providerReadinessResult.value = null;
  providerReadinessError.value = "";
  void loadRuntime();
  // Saving replaces the tall connection panel with the next task. Restore
  // the user's place in the workflow after Vue has rendered that task.
  await nextTick();
  const nextTask = document.querySelector<HTMLElement>(".enterprise-onboarding-next");
  nextTask?.scrollIntoView({ behavior: "auto", block: "start" });
  nextTask?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
}

function handleDocumentCatalog(catalog: DocumentCatalog): void {
  documentCatalog.value = catalog;
  documentCatalogLoaded.value = true;
}

async function handleDocumentsImported(_result: DocumentImportResult): Promise<void> {
  // The commit response is the source of truth for the first-run CTA. Refresh
  // the existing planner endpoint so the normal Scan route executes that same
  // real plan rather than a client-side approximation.
  await loadAttackPlans();
}

async function focusWorkspace(selector: string, workspace: WorkspaceId): Promise<void> {
  activeWorkspace.value = workspace;
  await nextTick();
  document.querySelector<HTMLElement>(selector)?.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

function handleOnboardingPathChange(path: OnboardingPath | null): void {
  // Choosing a path is a local presentation decision. The first business
  // request for that path comes from the mounted step that needs it.
  onboardingPath.value = path;
}

type OnboardingAction =
  | "connect-provider"
  | "add-documents"
  | "open-contract"
  | "run-guided-audit";

async function handleOnboardingAction(action: OnboardingAction): Promise<void> {
  if (action === "connect-provider") {
    await focusWorkspace(".provider-setup", "guided");
    return;
  }

  if (action === "add-documents") {
    await focusWorkspace(".document-import", "guided");
    return;
  }

  if (action === "open-contract") {
    await focusWorkspace(".contract-section", "setup");
    return;
  }

  await runGuidedScan();
}

async function startImportedGuidedAudit(planId: string): Promise<void> {
  if (scanLoading.value) {
    return;
  }

  activeWorkspace.value = "guided";
  await loadAttackPlans();
  const plan = attackPlans.value.find((candidate) => candidate.id === planId);
  if (!plan) {
    attackPlansError.value = "导入后的 Plan 尚未出现在当前 Contract 结果中，请打开 Contract Preview 检查缺口。";
    await focusWorkspace(".contract-section", "setup");
    return;
  }

  guidedSelectionPlanId.value = plan.id;
  scanPlanId.value = plan.id;
  replayResult.value = null;
  replayError.value = "";
  replayErrorDetails.value = "";
  await runRedTeamScan(false);
}

function openContractFromImport(): void {
  void focusWorkspace(".contract-section", "setup");
}

async function loadScanDetail(scanId: string): Promise<void> {
  const requestToken = ++scanDetailRequestToken;
  selectedScanId.value = scanId;
  scanDetailLoading.value = true;
  scanDetailError.value = "";
  persistedReplayError.value = "";
  selectedScanDetail.value = null;
  if (redTeamScan.value?.id !== scanId) {
    redTeamScan.value = null;
  }

  try {
    const response = await apiFetch(`/api/scans/${encodeURIComponent(scanId)}`);
    if (!response.ok) {
      throw await responseError(response);
    }

    const detail = auditRunDetailPayload(await response.json());
    if (requestToken !== scanDetailRequestToken || selectedScanId.value !== scanId) {
      return;
    }

    selectedScanDetail.value = detail;
    redTeamScan.value = detail.scan;
    replayResult.value = null;
    attackChainReport.value = null;
    attackChainReportError.value = "";
  } catch (error) {
    if (requestToken !== scanDetailRequestToken || selectedScanId.value !== scanId) {
      return;
    }

    scanDetailError.value = error instanceof Error ? error.message : "Scan 历史详情加载失败";
  } finally {
    if (requestToken === scanDetailRequestToken) {
      scanDetailLoading.value = false;
    }
  }
}

async function selectScanHistory(scanId: string): Promise<void> {
  activeWorkspace.value = "live";
  await loadScanDetail(scanId);
}

function showSelectedScanFindings(): void {
  if (selectedScanDetail.value) {
    activeWorkspace.value = "findings";
  }
}

async function replayPersistedScan(): Promise<void> {
  const detail = selectedScanDetail.value;
  if (!detail || persistedReplayLoading.value) {
    return;
  }

  const scanId = detail.scan.id;
  const requestToken = ++persistedReplayRequestToken;
  const request: StartPersistedReplayRequest = {};
  persistedReplayLoading.value = true;
  persistedReplayError.value = "";
  activeWorkspace.value = "findings";

  try {
    const response = await apiFetch(
      `/api/scans/${encodeURIComponent(scanId)}/replays`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      },
    );

    if (!response.ok) {
      throw await responseError(response);
    }

    const persistedReplay = persistedReplayPayload(await response.json());
    if (
      requestToken !== persistedReplayRequestToken ||
      selectedScanDetail.value?.scan.id !== scanId
    ) {
      return;
    }

    selectedScanDetail.value = {
      ...selectedScanDetail.value,
      replays: [...selectedScanDetail.value.replays, persistedReplay],
    };
    replayResult.value = persistedReplay.replay;
    attackChainReport.value = null;
    attackChainReportError.value = "";
    activeWorkspace.value = "findings";
    await loadScanHistory(scanId);
  } catch (error) {
    if (
      requestToken !== persistedReplayRequestToken ||
      selectedScanDetail.value?.scan.id !== scanId
    ) {
      return;
    }

    persistedReplayError.value =
      error instanceof Error ? error.message : "历史 Scan Replay 执行失败";
  } finally {
    if (requestToken === persistedReplayRequestToken) {
      persistedReplayLoading.value = false;
    }
  }
}

async function loadDifferentialTasks(): Promise<void> {
  differentialTasksLoading.value = true;
  differentialTasksError.value = "";

  try {
    const response = await apiFetch("/api/differential-tasks");
    if (!response.ok) {
      throw await responseError(response, differentialStatusMessages);
    }

    const tasks = differentialTaskPayload(await response.json());
    differentialTasks.value = tasks;
    const selectedTask =
      tasks.find((task) => task.id === differentialTaskId.value) ?? tasks[0];
    differentialTaskId.value = selectedTask?.id ?? "";
    differentialProfileId.value = selectedTask?.defaultTargetProfileId ?? "";
  } catch (error) {
    differentialTasksError.value =
      error instanceof Error ? error.message : "Multi-Identity Differential 任务加载失败";
  } finally {
    differentialTasksLoading.value = false;
  }
}

async function loadGroundTruthCases(): Promise<void> {
  groundTruthCasesLoading.value = true;
  groundTruthCasesError.value = "";

  try {
    const response = await apiFetch("/api/ground-truth-cases");
    if (!response.ok) {
      throw await responseError(response);
    }

    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) {
      throw new Error("Ground Truth Case 响应格式无效");
    }

    groundTruthCases.value = payload as GroundTruthCase[];
  } catch (error) {
    groundTruthCasesError.value =
      error instanceof Error ? error.message : "Ground Truth Case 加载失败";
  } finally {
    groundTruthCasesLoading.value = false;
  }
}

async function runBenchmark(): Promise<void> {
  if (benchmarkLoading.value) {
    return;
  }

  const requestToken = ++benchmarkRequestToken;
  benchmarkLoading.value = true;
  benchmarkError.value = "";
  benchmarkResult.value = null;

  try {
    const response = await apiFetch("/api/benchmarks/run", {
      method: "POST",
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    const resultPayload = (await response.json()) as BenchmarkResult;
    if (requestToken !== benchmarkRequestToken) {
      return;
    }

    benchmarkResult.value = resultPayload;
  } catch (error) {
    if (requestToken !== benchmarkRequestToken) {
      return;
    }

    benchmarkError.value = error instanceof Error ? error.message : "质量基准运行失败";
  } finally {
    if (requestToken === benchmarkRequestToken) {
      benchmarkLoading.value = false;
    }
  }
}

async function runRedTeamScan(openLiveWorkspace = true): Promise<void> {
  if (scanLoading.value) {
    return;
  }

  if (!scanPlanId.value) {
    scanError.value = "请选择一个当前 Security Contract 派生的 Attack Plan";
    scanErrorDetails.value = scanError.value;
    redTeamScan.value = null;
    return;
  }

  const requestToken = ++scanRequestToken;
  scanLoading.value = true;
  scanError.value = "";
  scanErrorDetails.value = "";
  redTeamScan.value = null;
  selectedScanDetail.value = null;
  selectedScanId.value = "";
  scanDetailError.value = "";

  const request: StartScanRequest = {
    planId: scanPlanId.value,
    maxRounds: scanMaxRounds.value,
  };

  try {
    const response = await apiFetch("/api/scans", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    const scan = redTeamScanPayload(await response.json());
    if (requestToken !== scanRequestToken) {
      return;
    }

    redTeamScan.value = scan;
    selectedScanId.value = scan.id;
    if (openLiveWorkspace) {
      activeWorkspace.value = "live";
    }
    await loadScanHistory(scan.id);
    if (requestToken !== scanRequestToken) {
      return;
    }
    await loadScanDetail(scan.id);
  } catch (error) {
    if (requestToken !== scanRequestToken) {
      return;
    }

    scanError.value = error instanceof Error ? error.message : "Red-Team Scan 执行失败";
    scanErrorDetails.value = technicalErrorDetails(error, scanError.value);
  } finally {
    if (requestToken === scanRequestToken) {
      scanLoading.value = false;
    }
  }
}

async function runGuidedScan(): Promise<void> {
  const plan = guidedPlan.value;
  if (!plan) {
    scanError.value = "当前 Security Contract 未派生 Source→Sink 核心验收计划";
    scanErrorDetails.value = scanError.value;
    return;
  }

  scanPlanId.value = plan.id;
  replayResult.value = null;
  replayError.value = "";
  replayErrorDetails.value = "";
  await runRedTeamScan(false);
}

async function runDifferentialAudit(): Promise<void> {
  if (differentialAuditLoading.value) {
    return;
  }

  const taskId = differentialTaskId.value;
  const targetProfileId = differentialProfileId.value;
  if (!taskId || !targetProfileId) {
    differentialAuditError.value = "请选择差分任务和该任务支持的 Target Profile";
    differentialAuditResult.value = null;
    return;
  }

  const requestToken = ++differentialRequestToken;
  differentialAuditLoading.value = true;
  differentialAuditError.value = "";
  differentialAuditResult.value = null;

  const request: StartDifferentialAuditRequest = {
    taskId,
    targetProfileId,
  };

  try {
    const response = await apiFetch("/api/differential-audits", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw await responseError(response, differentialStatusMessages);
    }

    const auditResult = differentialAuditPayload(
      await response.json(),
      taskId,
      targetProfileId,
    );
    if (
      requestToken !== differentialRequestToken ||
      differentialTaskId.value !== taskId ||
      differentialProfileId.value !== targetProfileId
    ) {
      return;
    }

    differentialAuditResult.value = auditResult;
  } catch (error) {
    if (
      requestToken !== differentialRequestToken ||
      differentialTaskId.value !== taskId ||
      differentialProfileId.value !== targetProfileId
    ) {
      return;
    }

    differentialAuditError.value =
      error instanceof Error ? error.message : "Multi-Identity Differential 执行失败";
  } finally {
    if (requestToken === differentialRequestToken) {
      differentialAuditLoading.value = false;
    }
  }
}

async function runRetrievalEvaluation(): Promise<void> {
  if (retrievalEvaluationLoading.value) {
    return;
  }

  const requestToken = ++retrievalEvaluationRequestToken;
  retrievalEvaluationLoading.value = true;
  retrievalEvaluationError.value = "";
  retrievalEvaluationResult.value = null;

  try {
    const response = await apiFetch("/api/retrieval-evaluations", {
      method: "POST",
    });

    if (!response.ok) {
      throw await responseError(response, retrievalEvaluationStatusMessages);
    }

    const resultPayload = retrievalEvaluationPayload(await response.json());
    if (requestToken !== retrievalEvaluationRequestToken) {
      return;
    }

    retrievalEvaluationResult.value = resultPayload;
  } catch (error) {
    if (requestToken !== retrievalEvaluationRequestToken) {
      return;
    }

    retrievalEvaluationError.value =
      error instanceof Error ? error.message : "Retrieval Evaluation 执行失败";
  } finally {
    if (requestToken === retrievalEvaluationRequestToken) {
      retrievalEvaluationLoading.value = false;
    }
  }
}

async function executeAttackCase(attackCase: AttackCase): Promise<void> {
  blockedCaseResult.value = null;
  executingCaseId.value = attackCase.id;
  attackExecutionError.value = "";
  result.value = null;
  evaluation.value = null;
  evaluationTraceEvents.value = [];
  evaluationError.value = "";
  semanticReviewError.value = "";
  queryError.value = "";

  try {
    const response = await apiFetch(`/api/attack-cases/${attackCase.id}/execute`, {
      method: "POST",
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    const payload = (await response.json()) as AttackExecutionResult;
    result.value = payload.queryResult;
    evaluation.value = payload.evaluation;
    evaluationTraceEvents.value = payload.queryResult ? payload.queryResult.traceEvents : payload.traceEvents;
    blockedCaseResult.value = payload.queryResult === null ? payload : null;
    if (blockedCaseResult.value) {
      await nextTick();
      document.getElementById("case-execution-outcome")?.scrollIntoView({ block: "start" });
    }
  } catch (error) {
    attackExecutionError.value =
      error instanceof Error ? error.message : "Attack Case 执行失败";
  } finally {
    executingCaseId.value = "";
  }
}

async function executeAttackPlan(plan: AttackPlan): Promise<void> {
  blockedPlanResult.value = null;
  executingPlanId.value = plan.id;
  attackPlanExecutionError.value = "";
  result.value = null;
  evaluation.value = null;
  evaluationTraceEvents.value = [];
  evaluationError.value = "";
  semanticReviewError.value = "";
  queryError.value = "";

  try {
    const response = await apiFetch(`/api/attack-plans/${plan.id}/execute`, {
      method: "POST",
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    const payload = (await response.json()) as AttackPlanExecutionResult;
    result.value = payload.queryResult;
    evaluation.value = payload.evaluation;
    evaluationTraceEvents.value = payload.queryResult ? payload.queryResult.traceEvents : payload.traceEvents;
    blockedPlanResult.value = payload.queryResult === null ? payload : null;
    if (blockedPlanResult.value) {
      await nextTick();
      document.getElementById("plan-execution-outcome")?.scrollIntoView({ block: "start" });
    }
  } catch (error) {
    attackPlanExecutionError.value =
      error instanceof Error ? error.message : "Attack Plan 执行失败";
  } finally {
    executingPlanId.value = "";
  }
}

async function replayAttackPlan(plan: AttackPlan): Promise<void> {
  replayPlanId.value = plan.id;
  replayError.value = "";
  replayErrorDetails.value = "";
  replayResult.value = null;
  attackChainReport.value = null;
  attackChainReportError.value = "";

  try {
    const response = await apiFetch(`/api/attack-plans/${plan.id}/replay`, {
      method: "POST",
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    replayResult.value = (await response.json()) as ReplayResult;
  } catch (error) {
    replayError.value = error instanceof Error ? error.message : "Replay 执行失败";
    replayErrorDetails.value = technicalErrorDetails(error, replayError.value);
  } finally {
    replayPlanId.value = "";
  }
}

async function runGuidedReplay(): Promise<void> {
  const plan = guidedPlan.value;
  if (!plan || !guidedHasFinding.value) {
    return;
  }

  await replayAttackPlan(plan);
}

async function runProviderReadiness(): Promise<void> {
  if (providerReadinessLoading.value) {
    return;
  }

  providerReadinessLoading.value = true;
  providerReadinessError.value = "";
  providerReadinessResult.value = null;
  const request: EmptyProviderReadinessRequest = {};

  try {
    const response = await apiFetch("/api/provider-readiness", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    providerReadinessResult.value = (await response.json()) as ProviderReadinessResult;
  } catch (error) {
    providerReadinessError.value =
      error instanceof Error ? error.message : "Provider 就绪检查失败";
  } finally {
    providerReadinessLoading.value = false;
  }
}

async function generateAttackChainReport(): Promise<void> {
  const replay = replayResult.value;
  if (!replay || attackChainReportLoading.value) {
    return;
  }

  attackChainReportLoading.value = true;
  attackChainReportError.value = "";
  attackChainReport.value = null;

  try {
    const response = await apiFetch("/api/attack-chain-reports", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(replay),
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    attackChainReport.value = (await response.json()) as AttackChainReport;
  } catch (error) {
    attackChainReportError.value =
      error instanceof Error ? error.message : "攻击链报告生成失败";
  } finally {
    attackChainReportLoading.value = false;
  }
}

async function evaluateTrace(traceEvents: TraceEvent[]): Promise<void> {
  evaluationLoading.value = true;
  evaluationError.value = "";
  semanticReviewError.value = "";
  evaluationTraceEvents.value = traceEvents;
  evaluation.value = null;

  const request: TraceEvaluationRequest = {
    traceEvents,
    includeSemanticReview: false,
  };

  try {
    const response = await apiFetch("/api/evaluations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    evaluation.value = (await response.json()) as TraceEvaluationResult;
  } catch (error) {
    evaluationError.value = error instanceof Error ? error.message : "Trace 评估失败";
  } finally {
    evaluationLoading.value = false;
  }
}

async function requestSemanticReview(): Promise<void> {
  if (!evaluation.value || evaluation.value.findings.length === 0) {
    return;
  }

  semanticReviewLoading.value = true;
  semanticReviewError.value = "";

  const request: TraceEvaluationRequest = {
    traceEvents: evaluationTraceEvents.value,
    includeSemanticReview: true,
  };

  try {
    const response = await apiFetch("/api/evaluations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    const reviewedResult = (await response.json()) as TraceEvaluationResult;
    if (evaluation.value) {
      evaluation.value = {
        ...evaluation.value,
        semanticReview: reviewedResult.semanticReview,
      };
    }
  } catch (error) {
    semanticReviewError.value =
      error instanceof Error ? error.message : "语义解释请求失败";
  } finally {
    semanticReviewLoading.value = false;
  }
}

async function responseError(
  response: Response,
  statusMessages: Record<number, string> = {},
): Promise<ApiResponseError> {
  let detail = "";
  try {
    const payload: unknown = await response.json();
    if (
      payload !== null &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) {
      detail = payload.detail;
    }
  } catch {
    // The status code remains the useful boundary error when the body is not JSON.
  }

  return new ApiResponseError(
    response.status,
    detail || statusMessages[response.status] || `请求失败（${response.status}）`,
    response.headers.get("X-AgentAudit-Operation-Id"),
  );
}

function technicalErrorDetails(error: unknown, fallback: string): string {
  if (error instanceof ApiResponseError) {
    const operation = error.operationId ? `\noperation ID: ${error.operationId}` : "";
    return `HTTP ${error.status}${operation}\n${error.message}`;
  }
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

async function loadActors(): Promise<void> {
  actorsLoading.value = true;
  actorsError.value = "";

  try {
    const response = await apiFetch("/api/demo/actors");
    if (!response.ok) {
      throw await responseError(response);
    }

    const payload: unknown = await response.json();
    if (!Array.isArray(payload)) {
      throw new Error("角色列表响应格式无效");
    }

    actors.value = payload as Actor[];
    if (!selectedActorId.value && actors.value.length > 0) {
      selectedActorId.value = actors.value[0].id;
    }
  } catch (error) {
    actorsError.value = error instanceof Error ? error.message : "角色加载失败";
  } finally {
    actorsLoading.value = false;
  }
}

function contractPayload(payload: unknown): SecurityContract {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("Security Contract 响应格式无效");
  }

  return payload as SecurityContract;
}

async function loadSecurityContract(): Promise<void> {
  contractLoading.value = true;
  contractError.value = "";

  try {
    const response = await apiFetch("/api/security-contract");
    if (!response.ok) {
      throw await responseError(response);
    }

    const payload = contractPayload(await response.json());
    securityContract.value = payload;
    contractPreview.value = null;
  } catch (error) {
    contractError.value = error instanceof Error ? error.message : "Security Contract 加载失败";
  } finally {
    contractLoading.value = false;
  }
}

function cancelContractEdit(): void {
  contractPreview.value = null;
  contractError.value = "";
  contractNotice.value = "";
}

async function previewSecurityContract(candidate: SecurityContract): Promise<void> {
  if (contractPreviewLoading.value || contractSaving.value) {
    return;
  }

  contractPreviewLoading.value = true;
  contractPreview.value = null;
  contractError.value = "";
  contractNotice.value = "";

  try {
    const response = await apiFetch("/api/security-contract/previews", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(candidate),
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    contractPreview.value = (await response.json()) as SecurityContractPreview;
  } catch (error) {
    contractError.value = error instanceof Error ? error.message : "Contract 影响预览失败";
  } finally {
    contractPreviewLoading.value = false;
  }
}

async function saveSecurityContract(candidate: SecurityContract): Promise<void> {
  if (contractSaving.value) {
    return;
  }

  contractSaving.value = true;
  contractError.value = "";
  contractNotice.value = "";
  const appliedPreview = contractPreview.value;

  try {
    const response = await apiFetch("/api/security-contract", {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(candidate),
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    const savedContract = contractPayload(await response.json());
    securityContract.value = savedContract;
    await loadAttackPlans();
    contractPreview.value = null;
    const changedPaths = appliedPreview?.fieldChanges.map((change) => change.path) ?? [];
    const planImpactCount = appliedPreview?.planChanges.length ?? 0;
    contractNotice.value = changedPaths.length
      ? `Contract 已保存：${changedPaths.join("、")}；Plan 变化 ${planImpactCount} 项。仅对当前 Demo 进程生效。`
      : `Contract 已保存：无字段变化，Plan 变化 ${planImpactCount} 项。仅对当前 Demo 进程生效。`;
  } catch (error) {
    contractError.value = error instanceof Error ? error.message : "Security Contract 保存失败";
  } finally {
    contractSaving.value = false;
  }
}

async function submitQuery(): Promise<void> {
  const trimmedMessage = message.value.trim();
  if (!selectedActorId.value || !trimmedMessage) {
    queryError.value = "请选择 Actor 并输入问题";
    return;
  }

  queryLoading.value = true;
  queryError.value = "";
  result.value = null;
  evaluation.value = null;
  evaluationTraceEvents.value = [];
  evaluationError.value = "";
  semanticReviewError.value = "";

  const request: AssistantQueryRequest = {
    actorId: selectedActorId.value,
    message: trimmedMessage,
  };

  try {
    const response = await apiFetch("/api/assistant/queries", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw await responseError(response);
    }

    const queryResult = (await response.json()) as AssistantQueryResult;
    result.value = queryResult;
    await evaluateTrace(queryResult.traceEvents);
  } catch (error) {
    queryError.value = error instanceof Error ? error.message : "查询失败";
  } finally {
    queryLoading.value = false;
  }
}

onMounted(() => {
  void loadActors();
  void loadProviderSetupState();
  void loadSecurityContract();
  void loadAttackCases();
  void loadAttackPlans();
  void loadRuntime();
  void loadScanHistory();
  void loadDifferentialTasks();
  void loadGroundTruthCases();
});
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-lockup">
        <img class="brand-mark" :src="brandMarkUrl" alt="" aria-hidden="true" />
        <div>
          <p class="brand-name">知盾 <span>AgentAudit</span></p>
          <p class="brand-caption">企业知识助手业务权限安全验收</p>
        </div>
      </div>
      <div class="topbar-tools">
        <div class="display-scale-control" role="group" aria-label="界面大小">
          <span class="display-scale-label">界面大小</span>
          <button
            type="button"
            :class="{ 'is-active': displayScale === 'standard' }"
            :aria-pressed="displayScale === 'standard'"
            data-testid="display-scale-standard"
            @click="setDisplayScale('standard')"
          >
            标准
          </button>
          <button
            type="button"
            :class="{ 'is-active': displayScale === 'large' }"
            :aria-pressed="displayScale === 'large'"
            data-testid="display-scale-large"
            @click="setDisplayScale('large')"
          >
            大字
          </button>
        </div>
        <div class="environment-chip">
          <span class="status-dot"></span>
          <span>本地演示环境</span>
        </div>
      </div>
    </header>

    <nav class="workspace-nav" aria-label="主要工作区">
      <button
        v-for="workspace in workspaceOptions"
        :key="workspace.id"
        type="button"
        class="workspace-nav-item"
        :class="{ 'is-active': activeWorkspace === workspace.id }"
        :aria-label="workspace.label"
        :aria-current="activeWorkspace === workspace.id ? 'page' : undefined"
        @click="activeWorkspace = workspace.id"
      >
        <span class="workspace-nav-index">{{ workspace.index }}</span>
        <span class="workspace-nav-copy">
          <strong>{{ workspace.label }}</strong>
          <small>{{ workspace.caption }}</small>
        </span>
      </button>
    </nav>

    <main class="page-content">
      <div
        v-if="activeWorkspace === 'guided'"
        class="workspace-pane guided-workspace"
        data-testid="workspace-guided"
      >
        <EnterpriseOnboardingView
          :selected-path="onboardingPath"
          :provider-configured="providerSetupState?.configured === true"
          :document-catalog="documentCatalog"
          :contract="securityContract"
          :plans="attackPlans"
          :guided-plan="guidedPlan"
          :scan="redTeamScan"
          :provider-loading="providerSetupLoading"
          :catalog-loading="!documentCatalogLoaded"
          :plans-loading="attackPlansLoading"
          :scan-loading="scanLoading"
          @action="handleOnboardingAction"
          @path-change="handleOnboardingPathChange"
          @reset="handleOnboardingPathChange(null)"
        />

        <template v-if="onboardingPath !== null">
          <ProviderSetupView
            v-if="onboardingTask === 'provider'"
            @saved="handleProviderSetupSaved"
          />

          <DocumentImportView
            v-if="onboardingTask === 'documents'"
            :actors="actors"
            @catalog="handleDocumentCatalog"
            @imported="handleDocumentsImported"
            @start-guided-audit="startImportedGuidedAudit"
            @open-contract="openContractFromImport"
          />

          <template v-if="onboardingTask === 'audit' || onboardingTask === 'result'">
            <GuidedAuditFlow
              :class="{ 'has-real-scan': Boolean(redTeamScan) }"
              :plan="guidedPlan"
              :scan="redTeamScan"
              :runtime="runtimeSnapshot"
              :loading="scanLoading || attackPlansLoading"
              :error="scanError || attackPlansError"
              :error-details="scanErrorDetails || attackPlansError"
              :error-source="scanError ? 'scan' : attackPlansError ? 'plan' : null"
              @start="runGuidedScan"
              @retry="loadAttackPlans"
            />

            <GuidedReplayComparison
              :replay="replayResult"
              :loading="Boolean(replayPlanId)"
              :error="replayError"
              :error-details="replayErrorDetails"
              :disabled="!guidedPlan || !guidedHasFinding || scanLoading || Boolean(replayPlanId)"
              @run="runGuidedReplay"
            />

            <ProviderReadinessView
              v-if="onboardingTask === 'result'"
              :result="providerReadinessResult"
              :loading="providerReadinessLoading"
              :error="providerReadinessError"
              @run="runProviderReadiness"
            />

            <section class="guided-advanced-links" aria-labelledby="guided-advanced-title">
              <div>
                <p class="section-kicker">更多证据</p>
                <h2 id="guided-advanced-title">需要更多证据？</h2>
                <p>深入查看规则、过程记录、历史结果和质量评测。</p>
              </div>
              <div class="guided-advanced-actions">
                <button type="button" @click="activeWorkspace = 'setup'">查看权限规则与检查计划</button>
                <button type="button" @click="activeWorkspace = 'live'">查看完整过程记录</button>
                <button type="button" @click="activeWorkspace = 'findings'">查看全部验收证据</button>
              </div>
            </section>
          </template>
        </template>
      </div>

      <div
        v-if="activeWorkspace === 'setup'"
        class="workspace-pane setup-workspace"
        data-testid="workspace-setup"
      >
      <section class="hero-section setup-illustrated-heading" aria-labelledby="page-title">
        <svg class="setup-plan-art" viewBox="0 0 260 150" aria-hidden="true">
          <ellipse cx="138" cy="129" rx="94" ry="12" fill="#1f7280" opacity=".06" />
          <path d="M38 100L125 145L229 87" fill="none" stroke="#bed5df" />
          <path d="M83 44H47V93H82M175 43H215V94H177" fill="none" stroke="#7fbcbf" stroke-width="1.5" stroke-dasharray="3 5" />
          <rect x="92" y="16" width="86" height="108" rx="10" fill="#e7f0f8" stroke="#adc7d7" />
          <rect x="82" y="10" width="86" height="108" rx="10" fill="#fff" stroke="#9fbfd0" />
          <rect x="98" y="27" width="31" height="5" rx="2" fill="#a2bbc9" />
          <g fill="#e9f6f3" stroke="#5aa99e"><rect x="98" y="45" width="12" height="12" rx="3"/><rect x="98" y="67" width="12" height="12" rx="3"/><rect x="98" y="89" width="12" height="12" rx="3"/></g>
          <path d="M120 51H151M120 73H143M120 95H150" stroke="#a9c1d0" stroke-width="3" stroke-linecap="round" />
          <circle cx="45" cy="45" r="17" fill="#edf5ff" stroke="#b6cde6"/><circle cx="45" cy="41" r="5" fill="#7b9fcc"/><path d="M36 54Q45 43 54 54" fill="#7b9fcc"/>
          <path d="M211 77L230 84V101Q230 115 211 124Q192 115 192 101V84Z" fill="#dff3ef" stroke="#76b9b1"/><path d="M204 98H218M211 91V105" stroke="#278b82" stroke-width="2"/>
          <circle cx="47" cy="93" r="4" fill="#5eaea6"/><circle cx="215" cy="43" r="4" fill="#829fcd"/>
        </svg>
        <div class="eyebrow">测试工作台 / Security Contract</div>
        <h1 id="page-title">先确认，再开始测试</h1>
        <p>内置场景快速看风险，自定义计划验证业务边界。权限规则与执行证据始终可查。</p>
        <button class="workspace-return" type="button" @click="activeWorkspace = 'guided'">第一次使用？进入引导验收 →</button>
      </section>
      <nav class="workspace-section-nav" aria-label="设置页目录" data-testid="setup-section-nav">
        <a href="#settings-provider">模型连接</a>
        <a href="#cases-title">攻击场景</a>
        <a href="#attack-plans-workspace-title">测试计划</a>
        <a href="#manual-query-title">手动查询</a>
        <a href="#security-contract-editor-title">权限规则</a>
        <a href="#setup-scan-title">高级运行</a>
        <a href="#workspace-operations-title">本地运维</a>
      </nav>

      <div id="settings-provider">
        <ProviderSetupView @saved="handleProviderSetupSaved" />
      </div>

      <section class="cases-section" aria-labelledby="cases-title">
        <div class="cases-heading">
          <div>
            <p class="section-kicker">双攻击者模型 / 内部越权 + 外部注入</p>
            <h2 id="cases-title">两条攻击路径</h2>
          </div>
          <span class="cases-count">2 条 · 合成靶场</span>
        </div>

        <el-alert
          v-if="attackCasesError"
          class="cases-alert"
          :title="attackCasesError"
          type="error"
          :closable="false"
        />
        <el-alert
          v-if="attackExecutionError"
          class="cases-alert"
          :title="attackExecutionError"
          type="error"
          :closable="false"
        />

        <BlockedExecutionView v-if="blockedCaseResult" id="case-execution-outcome" :outcome="blockedCaseResult" />
        <el-card class="cases-panel" shadow="never">
          <div v-if="attackCasesLoading" class="cases-loading">
            <el-skeleton :rows="5" animated />
          </div>
          <div v-else-if="attackCases.length > 0" class="case-grid">
            <article
              v-for="attackCase in attackCases"
              :key="attackCase.id"
              class="case-card"
              :data-testid="`fixed-case-${attackCase.id}`"
            >
              <div class="case-topline">
                <el-tag :type="attackerTypeTone(attackCase.attackerType)" effect="plain" size="small">
                  {{ attackerTypeLabel(attackCase.attackerType) }}
                </el-tag>
                <code>{{ attackCase.id }}</code>
              </div>
              <h3>{{ attackCase.name }}</h3>
              <p class="case-description">{{ attackCase.description }}</p>
              <dl class="case-facts">
                <div>
                  <dt>Actor</dt>
                  <dd><code>{{ attackCase.actorId }}</code></dd>
                </div>
                <div>
                  <dt>Target Profile</dt>
                  <dd><code>{{ attackCase.targetProfileId }}</code></dd>
                </div>
              </dl>
              <blockquote class="case-message">“{{ attackCase.message }}”</blockquote>
              <div class="case-expectations">
                <span>预期风险类型</span>
                <div>
                  <el-tag
                    v-for="category in attackCase.expectedFindingCategories"
                    :key="category"
                    class="case-category-tag"
                    data-testid="fixed-case-category"
                    type="info"
                    effect="plain"
                    size="small"
                  >
                    {{ findingCategoryLabels[category] }}
                  </el-tag>
                </div>
              </div>
              <el-button
                class="case-execute-button"
                type="primary"
                :loading="executingCaseId === attackCase.id"
                :disabled="Boolean(executingCaseId)"
                @click="executeAttackCase(attackCase)"
              >
                {{ executingCaseId === attackCase.id ? "执行中" : "执行固定 Case" }}
              </el-button>
            </article>
          </div>
          <el-empty v-else description="暂时无法读取固定 Case" />
        </el-card>
      </section>

      <AttackPlansWorkspace
        :plans="attackPlans"
        :loading="attackPlansLoading"
        :error="attackPlansError || attackPlanExecutionError"
        :selected-plan-id="redTeamScan?.planId ?? null"
        :executing-plan-id="executingPlanId"
        :replaying-plan-id="replayPlanId"
        :actions-disabled="attackChainReportLoading"
        :current-scan="redTeamScan"
        :policy-summary="planPolicySummary"
        @execute="executeAttackPlan"
        @replay="replayAttackPlan"
      />
      <BlockedExecutionView v-if="blockedPlanResult" id="plan-execution-outcome" :outcome="blockedPlanResult" />

      </div>

      <div
        v-else-if="activeWorkspace === 'live'"
        class="workspace-pane live-workspace"
        data-testid="workspace-live"
      >

      <section
        v-if="showUnifiedScanEmpty"
        class="scan-records-empty"
        aria-labelledby="scan-records-empty-title"
        data-testid="scan-history"
      >
        <div class="scan-records-empty-heading">
          <div>
            <p class="section-kicker">执行档案 / Scan · Trace</p>
            <h2 id="scan-records-empty-title">还没有扫描记录</h2>
            <p>完成一次核心验收后，这里会保存攻击过程与可复核证据。</p>
          </div>
          <span class="scan-records-empty-status">0 RECORDS</span>
        </div>

        <div
          class="scan-records-empty-panel"
          role="status"
          aria-live="polite"
          data-testid="scan-records-empty"
        >
          <div class="scan-records-empty-flow" aria-hidden="true">
            <span class="scan-records-empty-node is-active"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M16 16L21 21M11 7V15M7 11H15"/></svg>扫描 Scan</span>
            <span class="scan-records-empty-line"></span>
            <span class="scan-records-empty-node"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7H18M14 3L18 7L14 11M20 17H6M10 13L6 17L10 21"/></svg>尝试 Attempt</span>
            <span class="scan-records-empty-line"></span>
            <span class="scan-records-empty-node"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3H15L20 8V21H7ZM15 3V8H20M10 12H17M10 16H17"/></svg>证据 Trace</span>
            <span class="scan-records-empty-line"></span>
            <span class="scan-records-empty-node"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3L21 7V13Q21 19 12 22Q3 19 3 13V7Z M12 8V13M12 16V17"/></svg>风险 Finding</span>
          </div>

          <div class="scan-records-empty-copy">
            <span class="scan-records-empty-index">01</span>
            <div>
              <h3>从一条真实验收链路开始</h3>
              <p>选择测试计划并运行后，状态、Attempt、Trace 和 Finding 会自动归档到这里。</p>
            </div>
          </div>

          <div class="scan-records-empty-actions">
            <el-button
              type="primary"
              data-testid="scan-empty-start"
              @click="activeWorkspace = 'guided'"
            >
              去核心验收 <span class="button-arrow" aria-hidden="true">↗</span>
            </el-button>
            <el-button
              plain
              :loading="scanHistoryLoading"
              :disabled="scanHistoryLoading"
              data-testid="scan-empty-refresh"
              @click="loadScanHistory()"
            >
              刷新记录
            </el-button>
          </div>
        </div>
      </section>

      <section v-else class="scan-section" aria-labelledby="scan-title">
        <div class="scan-heading">
          <div>
            <p class="section-kicker">SCAN / TRACE</p>
            <h2 id="scan-title">本次扫描</h2>
            <p class="scan-subtitle">查看运行状态、每轮 Attempt 和完整 Trace。</p>
          </div>
          <el-tag
            class="scan-status"
            data-testid="scan-status"
            :type="
              scanUiStatus === 'success'
                ? 'success'
                : scanUiStatus === 'error'
                  ? 'danger'
                  : scanUiStatus === 'loading'
                    ? 'warning'
                    : 'info'
            "
            effect="dark"
          >
            {{ scanUiStatusLabels[scanUiStatus] }}
          </el-tag>
        </div>

        <el-alert
          v-if="scanError"
          class="scan-alert"
          :title="scanError"
          type="error"
          :closable="false"
        />

        <el-card class="scan-card" shadow="never">
          <div v-if="scanLoading" class="scan-loading" role="status" aria-live="polite">
            <el-skeleton :rows="5" animated />
            <p>正在生成受控攻击变体并执行真实 Target Agent…</p>
          </div>

          <div v-else-if="scanUiStatus === 'error'" class="scan-error-state" role="alert">
            <span class="scan-state-mark">!</span>
            <div>
              <h3>Scan 未完成</h3>
              <p>请先处理上方错误，再重新启动。</p>
            </div>
          </div>

          <template v-else-if="redTeamScan">
            <div class="scan-overview">
              <div>
                <p class="scan-id">
                  Scan <code>{{ redTeamScan.id }}</code>
                  <span>Plan {{ redTeamScan.planId }}</span>
                </p>
                <p class="scan-caption">
                  {{ scanStopReasonLabel(redTeamScan.stopReason) }} · 最终状态 {{ redTeamScan.status }}
                </p>
              </div>
              <el-tag :type="scanStopReasonTone(redTeamScan.stopReason)" effect="plain">
                {{ scanStopReasonLabel(redTeamScan.stopReason) }}
              </el-tag>
            </div>

            <dl class="scan-facts">
              <div>
                <dt>AI 连接 / 模型</dt>
                <dd>
                  <code>{{ redTeamScan.provider }}</code>
                  <span>{{ redTeamScan.model ?? "—" }}</span>
                </dd>
              </div>
              <div>
                <dt>权限规则</dt>
                <dd>
                  <code>{{ redTeamScan.contractId }}</code>
                  <span>v{{ redTeamScan.contractVersion }}</span>
                </dd>
              </div>
              <div>
                <dt>测试配置</dt>
                <dd><code>{{ redTeamScan.targetProfileId }}</code></dd>
              </div>
              <div>
                <dt>执行轮次 / 耗时</dt>
                <dd>
                  <strong>{{ redTeamScan.attempts.length }}</strong>
                  <span>{{ formatDurationMs(redTeamScan.durationMs) }} ms</span>
                </dd>
              </div>
            </dl>

            <div class="scan-transitions-block">
              <div class="scan-subheading">
                <p>检查过程</p>
                <code>{{ sortedScanTransitions.length }} 个步骤</code>
              </div>
              <ol v-if="sortedScanTransitions.length > 0" class="scan-transitions">
                <li
                  v-for="transition in sortedScanTransitions"
                  :key="transition.sequence"
                  class="scan-transition"
                  :class="`is-${transition.state}`"
                >
                  <span class="scan-transition-sequence">#{{ transition.sequence }}</span>
                  <el-tag :type="scanStateTone(transition.state)" effect="plain" size="small">
                    {{ scanStateLabel(transition.state) }}
                  </el-tag>
                  <code>{{ transition.state }}</code>
                  <span class="scan-transition-summary">{{ transition.summary }}</span>
                </li>
              </ol>
              <p v-else class="scan-evidence-empty">没有状态转换证据。</p>
            </div>

            <div class="scan-attempts-block">
              <div class="scan-subheading">
                <p>ATTEMPTS / TRACE EVIDENCE</p>
                <code>{{ redTeamScan.attempts.length }} attempts</code>
              </div>
              <div v-if="redTeamScan.attempts.length > 0" class="scan-attempt-list">
                <article
                  v-for="attempt in redTeamScan.attempts"
                  :key="attempt.id"
                  class="scan-attempt"
                  :class="{
                    'is-finding': attempt.status === 'finding',
                    'is-passed': attempt.status === 'passed',
                  }"
                  data-testid="scan-attempt"
                >
                  <div class="scan-attempt-header">
                    <div>
                      <p class="scan-attempt-label">ROUND {{ attempt.round }}</p>
                      <p class="scan-attempt-id">
                        <code>{{ attempt.id }}</code>
                        <span>{{ attempt.variant.id }}</span>
                      </p>
                    </div>
                    <el-tag
                      :type="attempt.status === 'finding' ? 'danger' : 'success'"
                      effect="plain"
                      size="small"
                    >
                      {{ attempt.status === "finding" ? "FINDING · 发现" : "PASSED · 通过" }}
                    </el-tag>
                  </div>

                  <dl class="scan-attempt-facts">
                    <div>
                      <dt>Actor / Attacker</dt>
                      <dd>
                        <code>{{ attempt.variant.actorId }}</code>
                        <span>{{ attackerTypeLabel(attempt.variant.attackerType) }}</span>
                      </dd>
                    </div>
                    <div>
                      <dt>Target / Rule</dt>
                      <dd>
                        <code>{{ attempt.variant.targetId }}</code>
                        <span>{{ attempt.variant.basisRuleId }}</span>
                      </dd>
                    </div>
                    <div>
                      <dt>Trace / Findings</dt>
                      <dd>
                        <strong>{{ attemptTraceEvents(attempt).length }}</strong>
                        <span>/ {{ attempt.evaluation.findings.length }}</span>
                      </dd>
                    </div>
                    <div>
                      <dt>Duration</dt>
                      <dd>{{ formatDurationMs(attempt.durationMs) }} ms</dd>
                    </div>
                  </dl>

                  <blockquote class="scan-attempt-message">“{{ attempt.variant.message }}”</blockquote>
                  <div
                    class="scan-mutation-reason scan-strategy-block"
                    :class="{
                      'is-finding': attempt.status === 'finding',
                      'is-passed': attempt.status === 'passed',
                    }"
                    role="note"
                  >
                    <span class="scan-strategy-label">本轮攻击策略</span>
                    <p>{{ attempt.variant.mutationReason }}</p>
                  </div>

                  <div v-if="attemptTraceEvents(attempt).length > 0">
                    <div class="scan-subheading">
                      <p>SOURCE → SINK</p>
                      <code>{{ traceEvidenceSummary(attemptTraceEvents(attempt)).flow }}</code>
                    </div>
                    <div class="scan-finding-evidence">
                      <template
                        v-for="row in traceEvidenceSummaryRows(attemptTraceEvents(attempt))"
                        :key="`${attempt.id}-${row.label}`"
                      >
                        <span>{{ row.label }}</span>
                        <code>{{ row.value }}</code>
                      </template>
                    </div>
                  </div>

                  <details class="scan-attempt-evidence">
                    <summary>展开本轮 Trace / Evaluation 证据</summary>
                    <div class="scan-evidence-grid">
                      <div class="scan-trace-column">
                        <div class="scan-evidence-heading">
                          <p>TRACE</p>
                          <code>{{ attemptTraceEvents(attempt).length }} events</code>
                        </div>
                        <ol v-if="attemptTraceEvents(attempt).length > 0" class="scan-trace-list">
                          <li
                            v-for="event in attemptTraceEvents(attempt)"
                            :key="`${attempt.id}-${event.sequence}-${event.type}-${event.occurredAt}`"
                          >
                            <div class="scan-trace-event-heading">
                              <span>#{{ event.sequence }}</span>
                              <el-tag :type="eventTone(event.type)" effect="plain" size="small">
                                {{ eventTypeLabel(event.type) }}
                              </el-tag>
                              <code>{{ event.type }}</code>
                            </div>
                            <p>{{ event.summary }}</p>
                            <div v-if="traceEvidenceRows(event).length > 0" class="scan-finding-evidence">
                              <template v-for="row in traceEvidenceRows(event)" :key="`${attempt.id}-${event.sequence}-${row.label}`">
                                <span>{{ row.label }}</span>
                                <code>{{ row.value }}</code>
                              </template>
                            </div>
                            <pre v-if="hasDetails(event)">{{ formatDetails(event.details) }}</pre>
                          </li>
                        </ol>
                        <p v-else class="scan-evidence-empty">无 Trace events</p>
                      </div>

                      <div class="scan-evaluation-column">
                        <div class="scan-evidence-heading">
                          <p>EVALUATION</p>
                          <el-tag
                            :type="evaluationStatusType(attempt.evaluation.status)"
                            effect="plain"
                            size="small"
                          >
                            {{ evaluationStatusLabel(attempt.evaluation.status) }}
                          </el-tag>
                        </div>
                        <div v-if="attempt.evaluation.findings.length > 0" class="scan-finding-list">
                          <article
                            v-for="finding in attempt.evaluation.findings"
                            :key="`${attempt.id}-${finding.id}`"
                            class="scan-finding"
                            data-testid="scan-finding"
                          >
                            <div class="scan-finding-topline">
                              <el-tag type="danger" effect="plain" size="small">
                                {{ findingSeverityLabel(finding.severity) }}
                              </el-tag>
                              <code>{{ findingCategoryLabel(finding.category) }}</code>
                            </div>
                            <strong>{{ finding.title }}</strong>
                            <p>{{ finding.summary }}</p>
                            <div class="scan-finding-evidence">
                              <span>ruleId</span>
                              <code>{{ findingRuleLabel(finding) }}</code>
                              <span>sequence</span>
                              <code>{{ finding.evidenceSequences.join(" → ") }}</code>
                            </div>
                          </article>
                        </div>
                        <div v-else class="scan-evaluation-passed">
                          <span>✓</span>
                          <p>本轮未发现确定性 Finding。</p>
                        </div>
                        <div class="scan-answer">
                          <span>Target Agent Response</span>
                          <p>{{ attempt.queryResult.answer }}</p>
                        </div>
                      </div>
                    </div>
                  </details>
                </article>
              </div>
              <p v-else class="scan-evidence-empty">本次 Scan 没有 Attempt。</p>
            </div>
          </template>

          <div v-else class="scan-idle" role="status" aria-live="polite">
            <span class="scan-state-mark">◎</span>
            <div>
              <h3>等待启动一次 Scan</h3>
              <p>从当前 Contract-derived Plan 开始，页面会返回完整状态转换与每轮证据。</p>
            </div>
          </div>
        </el-card>
      </section>

      <section
        v-if="!showUnifiedScanEmpty"
        class="history-section"
        aria-labelledby="history-title"
        data-testid="scan-history"
      >
        <div class="history-heading">
          <div>
            <p class="section-kicker">HISTORY</p>
            <h2 id="history-title">历史记录</h2>
            <p class="scan-subtitle">查看已保存结果，不会重新运行模型。</p>
          </div>
          <el-button
            class="history-refresh-button"
            plain
            :loading="scanHistoryLoading"
            :disabled="scanHistoryLoading"
            @click="loadScanHistory()"
          >
            {{ scanHistoryLoading ? "刷新中" : "刷新历史" }}
          </el-button>
        </div>

        <el-alert
          v-if="scanHistoryError"
          class="scan-alert"
          :title="scanHistoryError"
          type="error"
          :closable="false"
        />

        <el-card class="history-card" shadow="never">
          <div v-if="scanHistoryLoading && scanHistory.length === 0" class="scan-loading">
            <el-skeleton :rows="4" animated />
            <p>正在读取最近持久化 Scan…</p>
          </div>
          <el-empty
            v-else-if="scanHistory.length === 0"
            description="暂无已保存的 Scan；请先在 Audit Setup 发起一次审计"
          />
          <div v-else class="history-list">
            <article
              v-for="summary in scanHistory"
              :key="summary.scanId"
              class="history-item"
              :class="{ 'is-selected': selectedScanId === summary.scanId }"
            >
              <div class="history-item-heading">
                <div>
                  <p class="history-item-id">
                    <code>{{ summary.scanId }}</code>
                    <span>Plan {{ summary.planId }}</span>
                  </p>
                  <p class="history-item-time">{{ formatHistoryDate(summary.completedAt) }}</p>
                </div>
                <el-tag
                  :type="scanStopReasonTone(summary.stopReason)"
                  effect="plain"
                  size="small"
                >
                  {{ scanStopReasonLabel(summary.stopReason) }}
                </el-tag>
              </div>

              <dl class="history-item-facts">
                <div>
                  <dt>Status</dt>
                  <dd><code>{{ summary.status }}</code></dd>
                </div>
                <div>
                  <dt>Contract</dt>
                  <dd><code>{{ summary.contractId }} · v{{ summary.contractVersion }}</code></dd>
                </div>
                <div>
                  <dt>Profile</dt>
                  <dd><code>{{ summary.targetProfileId }}</code></dd>
                </div>
                <div>
                  <dt>Attempts / Findings</dt>
                  <dd><strong>{{ summary.attemptCount }}</strong><span>/ {{ summary.findingCount }}</span></dd>
                </div>
                <div>
                  <dt>Replay</dt>
                  <dd><strong>{{ summary.replayCount }}</strong><span> saved</span></dd>
                </div>
                <div>
                  <dt>Runtime</dt>
                  <dd>
                    <code>{{ summary.runtimeSnapshot.provider }}</code>
                    <span>{{ summary.runtimeSnapshot.model ?? "—" }}</span>
                  </dd>
                </div>
              </dl>

              <div class="history-item-actions">
                <span class="history-item-duration">
                  {{ formatDurationMs(summary.durationMs) }} ms
                </span>
                <el-button
                  type="primary"
                  plain
                  size="small"
                  :loading="scanDetailLoading && selectedScanId === summary.scanId"
                  :disabled="scanDetailLoading"
                  data-testid="restore-scan"
                  @click="selectScanHistory(summary.scanId)"
                >
                  {{ scanDetailLoading && selectedScanId === summary.scanId ? "读取中" : "恢复 Scan 详情" }}
                </el-button>
              </div>
            </article>
          </div>
        </el-card>

        <el-alert
          v-if="scanDetailError"
          class="scan-alert"
          :title="scanDetailError"
          type="error"
          :closable="false"
        />
        <div v-if="scanDetailLoading" class="history-detail-loading scan-loading" role="status" aria-live="polite">
          <el-skeleton :rows="3" animated />
          <p>正在读取所选 Scan 的完整 Attempt / Trace / Finding…</p>
        </div>
        <el-card v-else-if="redTeamScan && selectedScanId" class="history-live-link-card" shadow="never">
          <div class="history-live-link">
            <div>
              <p class="section-kicker">RESTORED SCAN</p>
              <h3>已恢复 {{ redTeamScan.id }}</h3>
              <p>完整状态流和 Attempt / Trace 已加载到上方 Live Audit 证据区。</p>
            </div>
            <el-button type="primary" data-testid="open-findings" @click="showSelectedScanFindings">
              查看 Findings & Replay <span class="button-arrow" aria-hidden="true">↗</span>
            </el-button>
          </div>
        </el-card>
      </section>

      </div>

      <div
        v-else-if="activeWorkspace === 'findings'"
        class="workspace-pane findings-workspace"
        data-testid="workspace-findings"
      >

      <nav class="workspace-section-nav" aria-label="证据页目录" data-testid="evidence-section-nav">
        <a href="#acceptance-runs-title">完整验收</a>
        <a href="#history-findings-title">历史风险与复测</a>
        <a href="#retrieval-evaluation-title">检索质量</a>
        <a href="#benchmark-title">质量基准</a>
        <a href="#trace-title">执行证据</a>
      </nav>
      <AcceptanceRunsView />

      <section class="history-findings-section" aria-labelledby="history-findings-title">
        <div class="history-heading">
          <div>
            <p class="section-kicker">FINDINGS / REPLAY / PERSISTED</p>
            <h2 id="history-findings-title">历史风险与复测</h2>
            <p class="scan-subtitle">
              恢复一次扫描，即可核对当时的权限规则、风险发现（Finding）与复测（Replay），所有内容来自保存的执行快照。
            </p>
          </div>
          <el-button
            class="history-replay-button"
            data-testid="start-persisted-replay"
            type="primary"
            :loading="persistedReplayLoading"
            :disabled="persistedReplayLoading || !selectedScanDetail"
            @click="replayPersistedScan"
          >
            {{ persistedReplayLoading ? "Replay 执行中" : "Replay 当前历史 Scan" }}
          </el-button>
        </div>

        <el-alert
          v-if="persistedReplayError"
          class="scan-alert"
          :title="persistedReplayError"
          type="error"
          :closable="false"
        />

        <el-card
          v-if="selectedScanDetail"
          class="history-detail-card"
          data-testid="history-detail"
          shadow="never"
        >
          <div class="scan-overview">
            <div>
              <p class="scan-id">
                Scan <code>{{ selectedScanDetail.scan.id }}</code>
                <span>Plan {{ selectedScanDetail.planSnapshot.id }}</span>
              </p>
              <p class="scan-caption">
                {{ formatHistoryDate(selectedScanDetail.scan.completedAt) }} ·
                {{ scanStopReasonLabel(selectedScanDetail.scan.stopReason) }}
              </p>
            </div>
            <el-tag :type="scanStopReasonTone(selectedScanDetail.scan.stopReason)" effect="plain">
              {{ selectedScanDetail.scan.status }} · {{ scanStopReasonLabel(selectedScanDetail.scan.stopReason) }}
            </el-tag>
          </div>

          <dl class="scan-facts">
            <div>
              <dt>Attempts / Duration</dt>
              <dd>
                <strong>{{ selectedScanDetail.scan.attempts.length }}</strong>
                <span>{{ formatDurationMs(selectedScanDetail.scan.durationMs) }} ms</span>
              </dd>
            </div>
            <div>
              <dt>Contract at execution</dt>
              <dd>
                <code>{{ selectedScanDetail.contractSnapshot.id }}</code>
                <span>v{{ selectedScanDetail.contractSnapshot.version }}</span>
              </dd>
            </div>
            <div>
              <dt>Target Profile</dt>
              <dd><code>{{ selectedScanDetail.targetProfileSnapshot.id }}</code></dd>
            </div>
            <div>
              <dt>Runtime Provider</dt>
              <dd>
                <code>{{ selectedScanDetail.runtimeSnapshot.provider }}</code>
                <span>{{ selectedScanDetail.runtimeSnapshot.model ?? "—" }}</span>
              </dd>
            </div>
          </dl>

          <div class="history-snapshot-grid">
            <article class="history-snapshot">
              <div class="scan-evidence-heading">
                <p>CONTRACT SNAPSHOT</p>
                <code>immutable</code>
              </div>
              <div class="history-snapshot-meta">
                <strong>{{ selectedScanDetail.contractSnapshot.name }}</strong>
                <span>
                  <code>{{ selectedScanDetail.contractSnapshot.id }}</code>
                  · v{{ selectedScanDetail.contractSnapshot.version }}
                </span>
              </div>
              <details class="history-snapshot-details">
                <summary>展开保存时 Contract JSON</summary>
                <pre>{{ formatJson(selectedScanDetail.contractSnapshot) }}</pre>
              </details>
            </article>

            <article class="history-snapshot">
              <div class="scan-evidence-heading">
                <p>PLAN SNAPSHOT</p>
                <code>immutable</code>
              </div>
              <dl class="history-snapshot-facts">
                <div>
                  <dt>Name / Basis</dt>
                  <dd>
                    <span>{{ selectedScanDetail.planSnapshot.name }}</span>
                    <code>{{ selectedScanDetail.planSnapshot.basisType }}</code>
                  </dd>
                </div>
                <div>
                  <dt>Actor / Attacker</dt>
                  <dd>
                    <code>{{ selectedScanDetail.planSnapshot.actorId }}</code>
                    <span>{{ attackerTypeLabel(selectedScanDetail.planSnapshot.attackerType) }}</span>
                  </dd>
                </div>
                <div>
                  <dt>Target / Profile</dt>
                  <dd>
                    <code>{{ selectedScanDetail.planSnapshot.targetId }}</code>
                    <span>{{ selectedScanDetail.planSnapshot.targetProfileId }}</span>
                  </dd>
                </div>
              </dl>
              <blockquote class="plan-message">“{{ selectedScanDetail.planSnapshot.message }}”</blockquote>
            </article>

            <article class="history-snapshot">
              <div class="scan-evidence-heading">
                <p>PROFILE SNAPSHOT</p>
                <code>immutable</code>
              </div>
              <div class="history-snapshot-meta">
                <strong>{{ selectedScanDetail.targetProfileSnapshot.name }}</strong>
                <code>{{ selectedScanDetail.targetProfileSnapshot.id }}</code>
              </div>
              <dl class="history-snapshot-facts">
                <div>
                  <dt>Resource authorization</dt>
                  <dd>{{ booleanLabel(selectedScanDetail.targetProfileSnapshot.enforceResourceAuthorization) }}</dd>
                </div>
                <div>
                  <dt>Tool authorization</dt>
                  <dd>{{ booleanLabel(selectedScanDetail.targetProfileSnapshot.enforceToolAuthorization) }}</dd>
                </div>
                <div>
                  <dt>Sink authorization</dt>
                  <dd>{{ booleanLabel(selectedScanDetail.targetProfileSnapshot.enforceSinkAuthorization) }}</dd>
                </div>
              </dl>
            </article>

            <article class="history-snapshot">
              <div class="scan-evidence-heading">
                <p>RUNTIME SNAPSHOT</p>
                <code>immutable</code>
              </div>
              <dl class="history-snapshot-facts">
                <div>
                  <dt>Provider / Model</dt>
                  <dd>
                    <code>{{ selectedScanDetail.runtimeSnapshot.provider }}</code>
                    <span>{{ selectedScanDetail.runtimeSnapshot.model ?? "—" }}</span>
                  </dd>
                </div>
                <div>
                  <dt>Retriever</dt>
                  <dd>
                    <code>{{ selectedScanDetail.runtimeSnapshot.retrieverEngine }}</code>
                    <span>{{ selectedScanDetail.runtimeSnapshot.retrieverModel ?? "—" }}</span>
                  </dd>
                </div>
                <div>
                  <dt>Dimensions / Documents</dt>
                  <dd>
                    <span>{{ selectedScanDetail.runtimeSnapshot.retrieverDimensions ?? "—" }}</span>
                    <span>/ {{ selectedScanDetail.runtimeSnapshot.indexedDocumentCount }}</span>
                  </dd>
                </div>
              </dl>
            </article>
          </div>

          <div class="history-evidence-block">
            <div class="scan-subheading">
              <p>FINDINGS / RULE / TRACE</p>
              <code>{{ selectedScanDetail.scan.attempts.length }} attempts</code>
            </div>
            <div v-if="selectedScanDetail.scan.attempts.length > 0" class="scan-attempt-list">
              <article
                v-for="attempt in selectedScanDetail.scan.attempts"
                :key="attempt.id"
                class="scan-attempt"
                :class="{
                  'is-finding': attempt.status === 'finding',
                  'is-passed': attempt.status === 'passed',
                }"
                data-testid="scan-attempt"
              >
                <div class="scan-attempt-header">
                  <div>
                    <p class="scan-attempt-label">ROUND {{ attempt.round }}</p>
                    <p class="scan-attempt-id">
                      <code>{{ attempt.id }}</code>
                      <span>{{ attempt.variant.id }}</span>
                    </p>
                  </div>
                  <el-tag
                    :type="attempt.status === 'finding' ? 'danger' : 'success'"
                    effect="plain"
                    size="small"
                  >
                    {{ attempt.status === "finding" ? "FINDING · 发现" : "PASSED · 通过" }}
                  </el-tag>
                </div>

                <div class="history-attempt-summary">
                  <span>Actor <code>{{ attempt.variant.actorId }}</code></span>
                  <span>Rule <code>{{ attempt.variant.basisRuleId }}</code></span>
                  <span>Trace {{ attemptTraceEvents(attempt).length }}</span>
                  <span>Finding {{ attempt.evaluation.findings.length }}</span>
                  <span>{{ formatDurationMs(attempt.durationMs) }} ms</span>
                </div>

                <blockquote class="scan-attempt-message">“{{ attempt.variant.message }}”</blockquote>
                <div
                  class="scan-mutation-reason scan-strategy-block"
                  :class="{
                    'is-finding': attempt.status === 'finding',
                    'is-passed': attempt.status === 'passed',
                  }"
                  role="note"
                >
                  <span class="scan-strategy-label">本轮攻击策略</span>
                  <p>{{ attempt.variant.mutationReason }}</p>
                </div>

                <div v-if="attempt.evaluation.findings.length > 0" class="scan-finding-list">
                  <article
                    v-for="finding in attempt.evaluation.findings"
                    :key="finding.id"
                    class="scan-finding"
                    data-testid="scan-finding"
                  >
                    <div class="scan-finding-topline">
                      <el-tag type="danger" effect="plain" size="small">
                        {{ findingSeverityLabel(finding.severity) }}
                      </el-tag>
                      <code>{{ findingCategoryLabel(finding.category) }}</code>
                    </div>
                    <strong>{{ finding.title }}</strong>
                    <p>{{ finding.summary }}</p>
                    <div class="scan-finding-evidence">
                      <span>ruleId</span>
                      <code>{{ findingRuleLabel(finding) }}</code>
                      <span>evidence sequence</span>
                      <code>{{ finding.evidenceSequences.join(" → ") }}</code>
                    </div>
                  </article>
                </div>
                <div v-else class="scan-evaluation-passed">
                  <span>✓</span>
                  <p>本轮未发现确定性 Finding。</p>
                </div>

                <details class="scan-attempt-evidence">
                  <summary>展开保存的 Trace（{{ attemptTraceEvents(attempt).length }} events）</summary>
                  <ol v-if="attemptTraceEvents(attempt).length > 0" class="scan-trace-list">
                    <li v-for="event in attemptTraceEvents(attempt)" :key="event.sequence">
                      <div class="scan-trace-event-heading">
                        <span>#{{ event.sequence }}</span>
                        <el-tag :type="eventTone(event.type)" effect="plain" size="small">
                          {{ eventTypeLabel(event.type) }}
                        </el-tag>
                        <code>{{ event.type }}</code>
                      </div>
                      <p>{{ event.summary }}</p>
                      <div v-if="traceEvidenceRows(event).length > 0" class="scan-finding-evidence">
                        <template v-for="row in traceEvidenceRows(event)" :key="row.label">
                          <span>{{ row.label }}</span>
                          <code>{{ row.value }}</code>
                        </template>
                      </div>
                      <pre v-if="hasDetails(event)">{{ formatDetails(event.details) }}</pre>
                    </li>
                  </ol>
                  <p v-else class="scan-evidence-empty">无 Trace events</p>
                </details>
              </article>
            </div>
            <p v-else class="scan-evidence-empty">历史 Scan 没有保存 Attempt。</p>
          </div>

          <div class="history-replays-block">
            <div class="scan-subheading">
              <p>PERSISTED REPLAYS / BEFORE → AFTER</p>
              <code>{{ selectedScanDetail.replays.length }} saved</code>
            </div>
            <div v-if="selectedScanDetail.replays.length > 0" class="history-replay-list">
              <article
                v-for="persistedReplay in selectedScanDetail.replays"
                :key="persistedReplay.id"
                class="history-replay-card"
                data-testid="persisted-replay"
              >
                <div class="history-replay-heading">
                  <div>
                    <p class="replay-id">
                      Replay <code>{{ persistedReplay.id }}</code>
                      <span>result {{ persistedReplay.replay.id }}</span>
                    </p>
                    <p class="replay-caption">{{ formatHistoryDate(persistedReplay.createdAt) }}</p>
                  </div>
                  <el-tag
                    :type="persistedReplay.replay.status === 'passed' ? 'success' : 'danger'"
                    effect="plain"
                  >
                    {{ evaluationStatusLabel(persistedReplay.replay.status) }}
                  </el-tag>
                </div>

                <div class="remediation-block">
                  <div>
                    <p class="remediation-title">{{ persistedReplay.replay.remediation.title }}</p>
                    <p class="remediation-summary">{{ persistedReplay.replay.remediation.summary }}</p>
                    <p class="remediation-advisory">
                      <strong>仅供参考：</strong>该控制项根据当前 Security Contract 与 Trace 生成，并只在内置 secure Profile 中模拟复测；不会修改企业系统，也不能替代根因分析与变更审批。
                    </p>
                  </div>
                  <div class="configuration-change">
                    <code>{{ persistedReplay.replay.remediation.configurationPath }}</code>
                    <span>
                      before {{ booleanLabel(persistedReplay.replay.remediation.beforeValue) }}
                      → after {{ booleanLabel(persistedReplay.replay.remediation.afterValue) }}
                    </span>
                  </div>
                </div>

                <div class="history-replay-attempts">
                  <article
                    v-for="entry in persistedReplayAttempts(persistedReplay.replay)"
                    :key="entry.key"
                    class="history-replay-attempt"
                    :data-testid="entry.key === 'before' ? 'replay-before' : 'replay-after'"
                  >
                    <div class="history-replay-attempt-heading">
                      <strong>{{ entry.label }}</strong>
                      <el-tag
                        :type="replayExecutionStatusType(entry.attempt.executionStatus)"
                        effect="plain"
                        size="small"
                      >
                        {{ replayExecutionStatusLabel(entry.attempt.executionStatus) }}
                      </el-tag>
                    </div>
                    <div class="history-attempt-summary">
                      <span>Evaluation <code>{{ entry.attempt.evaluation.status }}</code></span>
                      <span>Finding {{ entry.attempt.evaluation.findings.length }}</span>
                      <span>Trace {{ entry.attempt.traceEvents.length }}</span>
                    </div>
                    <p v-if="entry.attempt.blockedReason" class="history-blocked-reason">
                      {{ entry.attempt.blockedReason }}
                    </p>
                    <details v-if="entry.attempt.traceEvents.length > 0" class="scan-attempt-evidence">
                      <summary>展开 {{ entry.attempt.traceEvents.length }} 个 Trace events</summary>
                      <ol class="scan-trace-list">
                        <li v-for="event in entry.attempt.traceEvents" :key="event.sequence">
                          <div class="scan-trace-event-heading">
                            <span>#{{ event.sequence }}</span>
                            <el-tag :type="eventTone(event.type)" effect="plain" size="small">
                              {{ eventTypeLabel(event.type) }}
                            </el-tag>
                            <code>{{ event.type }}</code>
                          </div>
                          <p>{{ event.summary }}</p>
                          <pre v-if="hasDetails(event)">{{ formatDetails(event.details) }}</pre>
                        </li>
                      </ol>
                    </details>
                  </article>
                </div>
              </article>
            </div>
            <p v-else class="scan-evidence-empty">当前 Scan 尚未保存 Replay。</p>
          </div>
        </el-card>
        <el-card v-else class="history-detail-empty" shadow="never">
          <div class="scan-idle">
            <span class="scan-state-mark">◎</span>
            <div>
              <h3>选择一条历史 Scan</h3>
              <p>请到「扫描记录」打开一条历史扫描，再回来查看风险、规则快照与复测结果。</p>
            </div>
          </div>
        </el-card>
      </section>

      <DifferentialAuditWorkspace
        :tasks="differentialTasks"
        :task-id="differentialTaskId"
        :profile-id="differentialProfileId"
        :tasks-loading="differentialTasksLoading"
        :tasks-error="differentialTasksError"
        :audit-result="differentialAuditResult"
        :audit-loading="differentialAuditLoading"
        :audit-error="differentialAuditError"
        @update:task-id="updateDifferentialTask"
        @update:profile-id="updateDifferentialProfile"
        @run="runDifferentialAudit"
      />

      <section class="scan-section" aria-labelledby="retrieval-evaluation-title">
        <div class="scan-heading">
          <div>
            <p class="section-kicker">QUALITY / RETRIEVAL</p>
            <h2 id="retrieval-evaluation-title">检索质量</h2>
            <p class="scan-subtitle">用固定 Query 对照 TF-IDF 与 Embedding 排序。</p>
          </div>
          <div class="replay-overview-actions">
            <el-tag
              class="scan-status"
              :type="
                retrievalEvaluationUiStatus === 'success'
                  ? 'success'
                  : retrievalEvaluationUiStatus === 'error'
                    ? 'danger'
                    : retrievalEvaluationUiStatus === 'loading'
                      ? 'warning'
                      : 'info'
              "
              effect="dark"
            >
              {{ retrievalEvaluationUiStatusLabels[retrievalEvaluationUiStatus] }}
            </el-tag>
            <el-button
              class="benchmark-run-button"
              type="primary"
              :loading="retrievalEvaluationLoading"
              :disabled="retrievalEvaluationLoading"
              @click="runRetrievalEvaluation"
            >
              {{ retrievalEvaluationLoading ? "对比执行中" : "运行 Retrieval Evaluation" }}
            </el-button>
          </div>
        </div>

        <el-card class="scan-card" shadow="never">
          <div
            v-if="retrievalEvaluationLoading"
            class="scan-loading"
            role="status"
            aria-live="polite"
          >
            <el-skeleton :rows="5" animated />
            <p>正在执行固定 Query 的 TF-IDF / Embedding 对比…</p>
          </div>

          <el-alert
            v-else-if="retrievalEvaluationError"
            class="scan-alert"
            :title="retrievalEvaluationError"
            type="error"
            :closable="false"
          />

          <template v-else-if="retrievalEvaluationResult">
            <div class="scan-overview">
              <div>
                <p class="scan-id">
                  Retrieval Evaluation <code>{{ retrievalEvaluationResult.id }}</code>
                  <span>{{ retrievalEngineLabel(retrievalEvaluationResult.selectedEngine) }}</span>
                </p>
                <p class="scan-caption">
                  这是小型固定合成集的离线对比证据，不外推为生产检索准确率。
                </p>
              </div>
              <el-tag type="success" effect="plain">
                {{ retrievalEvaluationResult.selectedEngine }} selected
              </el-tag>
            </div>

            <dl class="scan-facts">
              <div>
                <dt>Selected engine</dt>
                <dd><code>{{ retrievalEvaluationResult.selectedEngine }}</code></dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd><code>{{ retrievalEvaluationResult.modelName }}</code></dd>
              </div>
              <div>
                <dt>Dimensions</dt>
                <dd><strong>{{ retrievalEvaluationResult.dimensions }}</strong></dd>
              </div>
              <div>
                <dt>Indexed documents</dt>
                <dd><strong>{{ retrievalEvaluationResult.indexedDocumentCount }}</strong></dd>
              </div>
            </dl>

            <div class="benchmark-metrics retrieval-metrics" aria-label="检索对比指标">
              <div class="benchmark-metric">
                <span>TF-IDF Top-1 hits</span>
                <strong>
                  {{ retrievalEvaluationResult.metrics.tfidfTop1Hits }} /
                  {{ retrievalEvaluationResult.metrics.caseCount }}
                </strong>
              </div>
              <div class="benchmark-metric">
                <span>Embedding Top-1 hits</span>
                <strong>
                  {{ retrievalEvaluationResult.metrics.embeddingTop1Hits }} /
                  {{ retrievalEvaluationResult.metrics.caseCount }}
                </strong>
              </div>
              <div class="benchmark-metric">
                <span>TF-IDF MRR</span>
                <strong>{{ retrievalMetricLabel(retrievalEvaluationResult.metrics.tfidfMrr) }}</strong>
              </div>
              <div class="benchmark-metric">
                <span>Embedding MRR</span>
                <strong>{{ retrievalMetricLabel(retrievalEvaluationResult.metrics.embeddingMrr) }}</strong>
              </div>
            </div>

            <div class="scan-attempts-block">
              <div class="scan-subheading">
                <p>FIXED QUERY CASES / TOP-3 EVIDENCE</p>
                <code>{{ retrievalEvaluationResult.cases.length }} cases</code>
              </div>
              <div v-if="retrievalEvaluationResult.cases.length > 0" class="scan-attempt-list">
                <article
                  v-for="evaluationCase in retrievalEvaluationResult.cases"
                  :key="evaluationCase.caseId"
                  class="scan-attempt"
                >
                  <div class="scan-attempt-header">
                    <div>
                      <p class="scan-attempt-label">FIXED QUERY CASE</p>
                      <p class="scan-attempt-id"><code>{{ evaluationCase.caseId }}</code></p>
                    </div>
                    <el-tag type="info" effect="plain" size="small">
                      expected document
                    </el-tag>
                  </div>

                  <blockquote class="scan-attempt-message">“{{ evaluationCase.query }}”</blockquote>

                  <dl class="scan-attempt-facts">
                    <div>
                      <dt>Expected document</dt>
                      <dd><code>{{ evaluationCase.expectedDocumentId }}</code></dd>
                    </div>
                    <div>
                      <dt>TF-IDF expected rank</dt>
                      <dd><strong>{{ retrievalRankLabel(evaluationCase.tfidfExpectedRank) }}</strong></dd>
                    </div>
                    <div>
                      <dt>Embedding expected rank</dt>
                      <dd><strong>{{ retrievalRankLabel(evaluationCase.embeddingExpectedRank) }}</strong></dd>
                    </div>
                    <div>
                      <dt>Returned candidates</dt>
                      <dd>
                        <span>{{ evaluationCase.tfidfResults.length }} TF-IDF</span>
                        <span>/ {{ evaluationCase.embeddingResults.length }} Embedding</span>
                      </dd>
                    </div>
                  </dl>

                  <div class="scan-evidence-grid">
                    <div class="scan-trace-column">
                      <div class="scan-evidence-heading">
                        <p>TF-IDF TOP-3</p>
                        <code>expected {{ retrievalRankLabel(evaluationCase.tfidfExpectedRank) }}</code>
                      </div>
                      <ol v-if="evaluationCase.tfidfResults.length > 0" class="scan-trace-list">
                        <li
                          v-for="document in evaluationCase.tfidfResults"
                          :key="`${evaluationCase.caseId}-tfidf-${document.rank}-${document.documentId}`"
                        >
                          <div class="scan-trace-event-heading">
                            <span>#{{ document.rank }}</span>
                            <code>{{ document.documentId }}</code>
                          </div>
                          <p>{{ document.title }}</p>
                          <div class="scan-finding-evidence">
                            <span>score</span>
                            <code>{{ retrievalScoreLabel(document.score) }}</code>
                          </div>
                        </li>
                      </ol>
                      <p v-else class="scan-evidence-empty">无 TF-IDF candidates</p>
                    </div>

                    <div class="scan-trace-column">
                      <div class="scan-evidence-heading">
                        <p>EMBEDDING TOP-3</p>
                        <code>expected {{ retrievalRankLabel(evaluationCase.embeddingExpectedRank) }}</code>
                      </div>
                      <ol v-if="evaluationCase.embeddingResults.length > 0" class="scan-trace-list">
                        <li
                          v-for="document in evaluationCase.embeddingResults"
                          :key="`${evaluationCase.caseId}-embedding-${document.rank}-${document.documentId}`"
                        >
                          <div class="scan-trace-event-heading">
                            <span>#{{ document.rank }}</span>
                            <code>{{ document.documentId }}</code>
                          </div>
                          <p>{{ document.title }}</p>
                          <div class="scan-finding-evidence">
                            <span>score</span>
                            <code>{{ retrievalScoreLabel(document.score) }}</code>
                          </div>
                        </li>
                      </ol>
                      <p v-else class="scan-evidence-empty">无 Embedding candidates</p>
                    </div>
                  </div>
                </article>
              </div>
              <p v-else class="scan-evidence-empty">本次评估没有返回固定 Query Case。</p>
            </div>
          </template>

          <div v-else class="scan-idle" role="status" aria-live="polite">
            <span class="scan-state-mark">◎</span>
            <div>
              <h3>等待运行 Retrieval Evaluation</h3>
              <p>点击运行后，服务端会返回固定合成 Query 的双检索排名和指标；不调用 Target Agent。</p>
            </div>
          </div>
        </el-card>
      </section>

      <section class="replay-section" aria-labelledby="replay-title">
        <div class="replay-heading">
          <div>
            <p class="section-kicker">REMEDIATION / REPLAY</p>
            <h2 id="replay-title">修复参考与模拟 Replay</h2>
          </div>
          <el-tag
            v-if="replayResult"
            class="replay-status"
            :type="evaluationStatusType(replayResult.status)"
            effect="dark"
          >
            {{ evaluationStatusLabel(replayResult.status) }}
          </el-tag>
        </div>

        <el-alert
          v-if="replayError"
          class="replay-alert"
          :title="replayError"
          type="error"
          :closable="false"
        />
        <el-alert
          v-if="attackChainReportError"
          class="report-alert"
          :title="attackChainReportError"
          type="error"
          :closable="false"
        />

        <el-card class="replay-card" shadow="never">
          <div v-if="replayLoading" class="replay-loading">
            <el-skeleton :rows="6" animated />
            <p>正在用同一计划比较漏洞 Profile 与内置 secure Profile…</p>
          </div>
          <template v-else-if="replayResult">
            <div class="replay-overview">
              <div>
                <p class="replay-id">
                  Replay <code>{{ replayResult.id }}</code>
                  <span>Plan {{ replayResult.plan.id }}</span>
                </p>
                <p class="replay-caption">
                  before failed → after passed 才会判定 Replay 通过
                </p>
              </div>
              <div class="replay-overview-actions">
                <el-tag :type="evaluationStatusType(replayResult.status)" effect="plain">
                  {{ evaluationStatusLabel(replayResult.status) }}
                </el-tag>
                <el-button
                  class="report-generate-button"
                  type="primary"
                  plain
                  :loading="attackChainReportLoading"
                  :disabled="attackChainReportLoading"
                  @click="generateAttackChainReport"
                >
                  {{ attackChainReportLoading ? "生成中" : "生成攻击链报告" }}
                </el-button>
              </div>
            </div>

            <div class="remediation-block">
              <div>
                <p class="remediation-title">{{ replayResult.remediation.title }}</p>
                <p class="remediation-summary">{{ replayResult.remediation.summary }}</p>
                <p class="remediation-advisory" data-testid="advanced-remediation-advisory">
                  <strong>仅供参考：</strong>该控制项根据当前 Security Contract 与 Trace 生成，并只在内置 secure Profile 中模拟复测；不会修改企业系统，也不能替代根因分析与变更审批。
                </p>
              </div>
              <div class="configuration-change">
                <code>{{ replayResult.remediation.configurationPath }}</code>
                <span>
                  before {{ booleanLabel(replayResult.remediation.beforeValue) }}
                  →
                  after {{ booleanLabel(replayResult.remediation.afterValue) }}
                </span>
              </div>
            </div>

            <div class="replay-attempt-grid">
              <article
                v-for="replayAttempt in replayAttempts"
                :key="replayAttempt.key"
                class="replay-attempt"
              >
                <div class="replay-attempt-heading">
                  <div>
                    <p class="replay-attempt-label">{{ replayAttempt.label }}</p>
                    <p class="replay-profile">
                      profileId <code>{{ replayAttempt.attempt.profileId }}</code>
                    </p>
                  </div>
                  <el-tag
                    :type="replayExecutionStatusType(replayAttempt.attempt.executionStatus)"
                    effect="plain"
                    size="small"
                  >
                    {{ replayExecutionStatusLabel(replayAttempt.attempt.executionStatus) }}
                  </el-tag>
                </div>

                <div class="replay-metrics">
                  <div>
                    <span>Evaluation</span>
                    <el-tag
                      :type="evaluationStatusType(replayAttempt.attempt.evaluation.status)"
                      effect="plain"
                      size="small"
                    >
                      {{ evaluationStatusLabel(replayAttempt.attempt.evaluation.status) }}
                    </el-tag>
                  </div>
                  <div>
                    <span>Finding 数</span>
                    <strong>{{ replayAttempt.attempt.evaluation.findings.length }}</strong>
                  </div>
                  <div class="replay-blocked-reason">
                    <span>blockedReason</span>
                    <code v-if="replayAttempt.attempt.blockedReason">
                      {{ replayAttempt.attempt.blockedReason }}
                    </code>
                    <em v-else>—</em>
                  </div>
                </div>

                <div v-if="replayAttempt.attempt.queryResult" class="replay-answer">
                  <span>QueryResult answer</span>
                  <p>{{ replayAttempt.attempt.queryResult.answer }}</p>
                </div>
                <div v-else class="replay-blocked-answer">
                  <code>queryResult = null</code>
                  <p>执行在授权边界被阻断，未生成回答。</p>
                </div>

                <div v-if="replayAttempt.attempt.traceEvents.length > 0" class="replay-trace">
                  <div class="replay-trace-heading">
                    <span>Source → Sink</span>
                    <code>{{ traceEvidenceSummary(replayAttempt.attempt.traceEvents).flow }}</code>
                  </div>
                  <div class="scan-finding-evidence">
                    <template
                      v-for="row in traceEvidenceSummaryRows(replayAttempt.attempt.traceEvents)"
                      :key="`${replayAttempt.key}-${row.label}`"
                    >
                      <span>{{ row.label }}</span>
                      <code>{{ row.value }}</code>
                    </template>
                  </div>
                </div>

                <div class="replay-trace">
                  <div class="replay-trace-heading">
                    <span>Trace events</span>
                    <code>{{ replayAttempt.attempt.traceEvents.length }}</code>
                  </div>
                  <ul v-if="replayAttempt.attempt.traceEvents.length > 0">
                    <li
                      v-for="event in replayAttempt.attempt.traceEvents"
                      :key="`${replayAttempt.key}-${event.sequence}-${event.type}-${event.occurredAt}`"
                    >
                      <span class="replay-trace-sequence">#{{ event.sequence }}</span>
                      <el-tag :type="eventTone(event.type)" effect="plain" size="small">
                        {{ eventTypeLabel(event.type) }}
                      </el-tag>
                      <code>{{ event.type }}</code>
                      <span class="replay-trace-summary">{{ event.summary }}</span>
                    </li>
                  </ul>
                  <p v-else class="replay-trace-empty">无 Trace events</p>
                </div>
              </article>
            </div>
          </template>
          <div v-else class="replay-empty">
            <span class="replay-empty-mark">↻</span>
            <div>
              <h3>等待一次 Replay</h3>
              <p>在上方选择一个 Contract-driven Plan，执行“参考配置模拟 Replay”查看前后证据。</p>
            </div>
          </div>
        </el-card>
        <div v-if="attackChainReportLoading" class="report-loading">
          <el-skeleton :rows="5" animated />
          <p>正在整理当前 Replay 的攻击链报告…</p>
        </div>
        <AttackChainReportView v-if="attackChainReport" :report="attackChainReport" />
      </section>

      <section class="benchmark-section" aria-labelledby="benchmark-title">
        <div class="benchmark-heading">
          <div>
            <p class="section-kicker">QUALITY / GROUND TRUTH</p>
            <h2 id="benchmark-title">固定质量基准</h2>
          </div>
          <el-button
            class="benchmark-run-button"
            type="primary"
            :loading="benchmarkLoading"
            :disabled="benchmarkLoading || groundTruthCasesLoading"
            @click="runBenchmark"
          >
            {{ benchmarkLoading ? "运行中" : "运行质量基准" }}
          </el-button>
        </div>

        <el-alert
          v-if="groundTruthCasesError"
          class="benchmark-alert"
          :title="groundTruthCasesError"
          type="error"
          :closable="false"
        />
        <el-alert
          v-if="benchmarkError"
          class="benchmark-alert"
          :title="benchmarkError"
          type="error"
          :closable="false"
        />

        <el-card class="benchmark-card" shadow="never">
          <div v-if="groundTruthCasesLoading" class="benchmark-loading">
            <el-skeleton :rows="4" animated />
            <p>正在加载固定 Ground Truth Cases…</p>
          </div>
          <template v-else>
            <div class="benchmark-overview">
              <div class="benchmark-count">
                <span>固定 Ground Truth Cases</span>
                <strong>{{ benchmarkResult?.metrics.caseCount ?? groundTruthCases.length }}</strong>
              </div>
              <div class="benchmark-type-overview">
                <span class="benchmark-label">四类覆盖</span>
                <div class="benchmark-type-list">
                  <span
                    v-for="summary in benchmarkCategorySummary"
                    :key="summary.category"
                    class="benchmark-type-chip"
                  >
                    {{ groundTruthCategoryLabel(summary.category) }}
                    <strong>{{ summary.count }}</strong>
                  </span>
                </div>
              </div>
              <div v-if="groundTruthTypeSummary.length > 0" class="benchmark-type-overview">
                <span class="benchmark-label">执行类型</span>
                <div class="benchmark-type-list">
                  <span
                    v-for="summary in groundTruthTypeSummary"
                    :key="summary.type"
                    class="benchmark-type-chip"
                  >
                    {{ executionTypeLabel(summary.type) }}
                    <strong>{{ summary.count }}</strong>
                  </span>
                </div>
              </div>
              <p v-if="groundTruthCases.length === 0" class="benchmark-overview-note">
                当前没有可运行的 Ground Truth Case。
              </p>
              <p v-else-if="!benchmarkResult && !benchmarkLoading" class="benchmark-overview-note">
                尚未运行基准；点击右上角按钮开始一次真实验收。
              </p>
            </div>

            <div v-if="benchmarkLoading" class="benchmark-run-loading">
              <span class="benchmark-loading-mark" aria-hidden="true">◎</span>
              <div>
                <h3>正在运行质量基准</h3>
                <p>服务端将按固定 Cases 执行并返回逐 Case 结果。</p>
              </div>
            </div>
            <template v-else-if="benchmarkResult">
              <div class="benchmark-metrics" aria-label="质量基准指标">
                <div class="benchmark-metric">
                  <span>Attack Success Rate</span>
                  <strong>{{ benchmarkPercentageLabel(benchmarkResult.metrics.attackSuccessRate) }}</strong>
                </div>
                <div class="benchmark-metric">
                  <span>Detection Recall</span>
                  <strong>{{ benchmarkPercentageLabel(benchmarkResult.metrics.detectionRecall) }}</strong>
                </div>
                <div class="benchmark-metric">
                  <span>False Positive Rate</span>
                  <strong>{{ benchmarkPercentageLabel(benchmarkResult.metrics.falsePositiveRate) }}</strong>
                </div>
                <div class="benchmark-metric">
                  <span>Policy Violation Accuracy</span>
                  <strong>{{ benchmarkPercentageLabel(benchmarkResult.metrics.policyViolationAccuracy) }}</strong>
                </div>
                <div class="benchmark-metric">
                  <span>Mean Attempts</span>
                  <strong>{{ benchmarkNullableNumberLabel(benchmarkResult.metrics.meanAttempts) }}</strong>
                </div>
                <div class="benchmark-metric">
                  <span>Mean Scan Time</span>
                  <strong>{{ benchmarkNullableDurationLabel(benchmarkResult.metrics.meanScanTimeMs) }}</strong>
                </div>
                <div class="benchmark-metric">
                  <span>Replay Pass Rate</span>
                  <strong>{{ benchmarkPercentageLabel(benchmarkResult.metrics.replayPassRate) }}</strong>
                </div>
                <div class="benchmark-metric benchmark-metric-time">
                  <span>Total Scan Time</span>
                  <strong>{{ formatDurationMs(benchmarkResult.metrics.scanTimeMs) }} <small>ms</small></strong>
                </div>
              </div>

              <div class="benchmark-result-meta">
                <span>Run <code>{{ benchmarkResult.id }}</code></span>
                <span>
                  {{ benchmarkResult.metrics.matchedCaseCount }} /
                  {{ benchmarkResult.metrics.caseCount }} cases matched
                </span>
                <span>
                  normal {{ benchmarkResult.metrics.normalCaseCount }} ·
                  violation {{ benchmarkResult.metrics.violationCaseCount }} ·
                  replay {{ benchmarkResult.metrics.replayCaseCount }}
                </span>
              </div>

              <div class="benchmark-type-overview">
                <span class="benchmark-label">Provider usage</span>
                <div class="benchmark-type-list">
                  <span class="benchmark-type-chip">
                    Calls <strong>{{ benchmarkResult.metrics.providerUsage.callCount }}</strong>
                  </span>
                  <span class="benchmark-type-chip">
                    Input tokens
                    <strong>{{ providerUsageLabel(benchmarkResult.metrics.providerUsage.inputTokens) }}</strong>
                  </span>
                  <span class="benchmark-type-chip">
                    Output tokens
                    <strong>{{ providerUsageLabel(benchmarkResult.metrics.providerUsage.outputTokens) }}</strong>
                  </span>
                  <span class="benchmark-type-chip">
                    Total tokens
                    <strong>{{ providerUsageLabel(benchmarkResult.metrics.providerUsage.totalTokens) }}</strong>
                  </span>
                  <span class="benchmark-type-chip">
                    Estimated cost
                    <strong>{{ estimatedCostLabel(benchmarkResult.metrics.providerUsage.estimatedCostUsd) }}</strong>
                  </span>
                </div>
                <p class="benchmark-overview-note">
                  Token usage 只有在所有相关调用提供 usage 时才聚合；null 表示 unavailable，成本不估算。
                </p>
              </div>

              <div class="benchmark-table-wrap">
                <table class="benchmark-table benchmark-quality-table">
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Category</th>
                      <th>Execution Type</th>
                      <th>Execution Status</th>
                      <th>Attempts / Provider Calls</th>
                      <th>Expected → Actual</th>
                      <th>Expected Finding categories</th>
                      <th>Actual Finding categories</th>
                      <th>Matched</th>
                      <th>Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="caseResult in benchmarkResult.cases" :key="caseResult.caseId">
                      <td>
                        <code>{{ caseResult.caseId }}</code>
                        <span class="benchmark-case-name">{{ caseResult.name }}</span>
                      </td>
                      <td>
                        <span class="benchmark-execution-label">
                          {{ groundTruthCategoryLabel(caseResult.category) }}
                        </span>
                        <code>{{ caseResult.category }}</code>
                      </td>
                      <td>
                        <span class="benchmark-execution-label">
                          {{ executionTypeLabel(caseResult.executionType) }}
                        </span>
                        <code>{{ caseResult.executionType }}</code>
                      </td>
                      <td>
                        <span class="benchmark-outcome-label">
                          {{ groundTruthExecutionStatusLabel(caseResult.expectedExecutionStatus) }}
                          →
                          {{ groundTruthExecutionStatusLabel(caseResult.actualExecutionStatus) }}
                        </span>
                        <code>
                          {{ caseResult.expectedExecutionStatus }} → {{ caseResult.actualExecutionStatus }}
                        </code>
                      </td>
                      <td>
                        <span class="benchmark-outcome-label">{{ caseResult.attemptCount }} attempts</span>
                        <code>{{ caseResult.providerCallCount }} provider calls</code>
                      </td>
                      <td>
                        <span class="benchmark-outcome-label">
                          {{ groundTruthOutcomeLabel(caseResult.expectedOutcome) }}
                          →
                          {{ groundTruthOutcomeLabel(caseResult.actualOutcome) }}
                        </span>
                        <code>
                          {{ caseResult.expectedOutcome }} → {{ caseResult.actualOutcome }}
                        </code>
                      </td>
                      <td>{{ findingCategoriesLabel(caseResult.expectedFindingCategories) }}</td>
                      <td>{{ findingCategoriesLabel(caseResult.actualFindingCategories) }}</td>
                      <td>
                        <el-tag
                          :type="caseResult.matched ? 'success' : 'danger'"
                          effect="plain"
                          size="small"
                        >
                          {{ caseResult.matched ? "matched" : "mismatch" }}
                        </el-tag>
                        <code>{{ booleanLabel(caseResult.matched) }}</code>
                      </td>
                      <td><code>{{ formatDurationMs(caseResult.durationMs) }} ms</code></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
            <div v-else-if="groundTruthCases.length > 0" class="benchmark-not-run">
              <span class="benchmark-empty-mark" aria-hidden="true">∿</span>
              <div>
                <h3>等待运行基准</h3>
                <p>结果只在点击“运行质量基准”后从服务端加载，不使用静态数据。</p>
              </div>
            </div>
            <div v-else class="benchmark-empty">
              <span class="benchmark-empty-mark" aria-hidden="true">—</span>
              <div>
                <h3>暂无验收样本</h3>
                <p>Ground Truth Case 列表为空，暂时无法展示逐 Case 结果。</p>
              </div>
            </div>
          </template>
        </el-card>
      </section>

      </div>

      <div v-if="activeWorkspace === 'setup'" class="workspace-pane setup-workspace">
      <section class="workspace-grid" aria-label="企业知识助手查询工作区">
        <el-card class="panel query-panel" shadow="never">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">01 / ASK</p>
              <h2 id="manual-query-title">手动验证一条查询</h2>
            </div>
            <span class="panel-index">INPUT</span>
          </div>

          <el-alert
            v-if="actorsError"
            class="inline-alert"
            :title="actorsError"
            type="error"
            :closable="false"
          />

          <form class="query-form" @submit.prevent="submitQuery">
            <div class="field-group">
              <label class="field-label" for="actor-select">当前 Actor</label>
              <el-select
                id="actor-select"
                v-model="selectedActorId"
                class="actor-select"
                :loading="actorsLoading"
                :disabled="actorsLoading || actors.length === 0"
                placeholder="等待角色列表"
                value-key="id"
              >
                <el-option
                  v-for="actor in actors"
                  :key="actor.id"
                  :label="`${actor.displayName} · ${roleLabels[actor.role]}`"
                  :value="actor.id"
                >
                  <div class="actor-option">
                    <span class="actor-option-name">{{ actor.displayName }}</span>
                    <span class="actor-option-role">{{ roleLabels[actor.role] }}</span>
                  </div>
                </el-option>
              </el-select>
              <p class="field-hint" v-if="selectedActor">
                Actor ID <code>{{ selectedActor.id }}</code>
              </p>
            </div>

            <div class="field-group">
              <label class="field-label" for="query-message">你的问题</label>
              <el-input
                id="query-message"
                v-model="message"
                type="textarea"
                :rows="4"
                maxlength="500"
                show-word-limit
                resize="none"
                placeholder="例如：总结我的客户合同"
              />
              <p class="field-hint">以当前 Actor 身份提交到受控 Agent。</p>
            </div>

            <el-alert
              v-if="queryError"
              class="inline-alert"
              :title="queryError"
              type="error"
              :closable="false"
            />

            <el-button
              class="submit-button"
              type="primary"
              native-type="submit"
              :loading="queryLoading"
              :disabled="!canSubmit"
            >
              {{ queryLoading ? "Agent 执行中" : "提交问题" }}
              <span v-if="!queryLoading" class="button-arrow" aria-hidden="true">↗</span>
            </el-button>
          </form>
        </el-card>

        <el-card class="panel answer-panel" shadow="never">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">02 / RESPONSE</p>
              <h2>Agent 回答</h2>
            </div>
            <span class="panel-index">OUTPUT</span>
          </div>

          <div v-if="result" class="answer-content">
            <div class="answer-meta">
              <span class="answer-actor">
                <span class="avatar-dot">{{ result.actor.displayName.slice(0, 1) }}</span>
                {{ result.actor.displayName }} · {{ roleLabels[result.actor.role] }}
              </span>
              <code>{{ result.queryId }}</code>
            </div>
            <div class="answer-copy">
              <p>{{ result.answer }}</p>
            </div>
          </div>
          <div v-else class="empty-state">
            <div class="empty-orbit" aria-hidden="true"><span></span></div>
            <h3>还没有回答</h3>
            <p>提交一个问题后，这里会显示 Agent 的真实响应。</p>
          </div>
        </el-card>
      </section>

      <section class="contract-section" aria-label="Security Contract 编辑器">
        <el-card class="panel contract-panel" shadow="never">
          <SecurityContractEditor
            :contract="securityContract"
            :loading="contractLoading"
            :saving="contractSaving"
            :preview="contractPreview"
            :preview-loading="contractPreviewLoading"
            :error="contractError"
            :notice="contractNotice"
            @preview="previewSecurityContract"
            @save="saveSecurityContract"
            @cancel="cancelContractEdit"
          />
        </el-card>
      </section>

      <section class="setup-scan-section" aria-labelledby="setup-scan-title">
        <div class="scan-heading">
          <div>
            <p class="section-kicker">高级运行 / Red-Team Agent</p>
            <h2 id="setup-scan-title">设置轮数并启动扫描</h2>
            <p class="scan-subtitle">
              从权限规则派生测试计划，让 Red-Team Agent 在指定轮数内尝试攻击，并保留每轮证据。
            </p>
          </div>
          <el-tag type="info" effect="dark">SETUP · READY</el-tag>
        </div>

        <el-card
          class="scan-card setup-runtime-card"
          data-testid="runtime-summary"
          shadow="never"
        >
          <div class="setup-runtime-heading">
            <div>
              <p class="section-kicker">RUNTIME / API SNAPSHOT</p>
              <h3>当前连接</h3>
              <p class="setup-runtime-caption">只读查看 Provider 与 Retriever。</p>
            </div>
            <div class="setup-runtime-actions">
              <el-tag
                :type="runtimeSnapshot ? 'success' : runtimeLoading ? 'warning' : 'danger'"
                effect="plain"
                size="small"
              >
                {{ runtimeLoading ? "LOADING" : runtimeSnapshot ? "LIVE CONFIG" : "UNAVAILABLE" }}
              </el-tag>
              <el-button
                class="setup-runtime-refresh"
                plain
                size="small"
                :loading="runtimeLoading"
                :disabled="runtimeLoading"
                @click="loadRuntime"
              >
                {{ runtimeLoading ? "读取中" : "刷新 Runtime" }}
              </el-button>
            </div>
          </div>

          <el-alert
            v-if="runtimeError"
            class="scan-alert"
            :title="runtimeError"
            type="error"
            :closable="false"
          />
          <div v-if="runtimeLoading && !runtimeSnapshot" class="scan-loading" role="status" aria-live="polite">
            <el-skeleton :rows="2" animated />
            <p>正在读取当前连接…</p>
          </div>
          <dl v-else-if="runtimeSnapshot" class="scan-facts setup-runtime-facts">
            <div>
              <dt>Provider</dt>
              <dd><code>{{ runtimeSnapshot.provider }}</code></dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd><code>{{ runtimeSnapshot.model ?? "null" }}</code></dd>
            </div>
            <div>
              <dt>Retriever Engine</dt>
              <dd><code>{{ runtimeSnapshot.retrieverEngine }}</code></dd>
            </div>
            <div>
              <dt>Retriever Model</dt>
              <dd><code>{{ runtimeSnapshot.retrieverModel ?? "null" }}</code></dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd><code>{{ runtimeSnapshot.retrieverDimensions ?? "null" }}</code></dd>
            </div>
            <div>
              <dt>Indexed Documents</dt>
              <dd><strong>{{ runtimeSnapshot.indexedDocumentCount }}</strong></dd>
            </div>
          </dl>
          <el-empty v-else description="当前 Runtime 暂不可读" />
        </el-card>

        <el-alert
          v-if="scanError"
          class="scan-alert"
          :title="scanError"
          type="error"
          :closable="false"
        />

        <el-card class="scan-card" shadow="never">
          <div class="scan-launch-grid">
            <div class="field-group">
              <template v-if="singleAttackPlan">
                <span id="setup-scan-plan-label" class="field-label">当前 Attack Plan</span>
                <div
                  id="setup-scan-plan-static"
                  class="scan-plan-static"
                  data-testid="scan-plan-static"
                  role="status"
                  aria-labelledby="setup-scan-plan-label"
                >
                  <div class="scan-plan-static-heading">
                    <strong>{{ singleAttackPlan.name }}</strong>
                    <code>{{ singleAttackPlan.id }}</code>
                  </div>
                  <p>{{ singleAttackPlan.description }}</p>
                  <div class="scan-plan-static-facts">
                    <span>Actor <code>{{ singleAttackPlan.actorId }}</code></span>
                    <span>Target <code>{{ singleAttackPlan.targetId }}</code></span>
                  </div>
                </div>
              </template>
              <template v-else>
                <label class="field-label" for="setup-scan-plan-select">当前 Attack Plan</label>
                <el-select
                  id="setup-scan-plan-select"
                  data-testid="scan-plan-select"
                  v-model="scanPlanId"
                  class="scan-plan-select"
                  :loading="attackPlansLoading"
                  :disabled="scanLoading || attackPlansLoading || attackPlans.length === 0"
                  placeholder="等待 Contract-derived Plan"
                >
                  <el-option
                    v-for="plan in attackPlans"
                    :key="plan.id"
                    :label="plan.name"
                    :value="plan.id"
                  >
                    <div class="scan-plan-option">
                      <span>{{ plan.name }}</span>
                      <code>{{ plan.id }}</code>
                    </div>
                  </el-option>
                </el-select>
              </template>
              <p class="field-hint" v-if="securityContract">
                Contract <code>{{ securityContract.id }}</code> · v{{ securityContract.version }}
              </p>
            </div>

            <div class="field-group">
              <label class="field-label" for="setup-scan-round-select">最大轮数</label>
              <el-select
                id="setup-scan-round-select"
                v-model="scanMaxRounds"
                class="scan-round-select"
                :disabled="scanLoading"
              >
                <el-option :value="2" label="2 rounds" />
                <el-option :value="3" label="3 rounds" />
              </el-select>
              <p class="field-hint">可选 2 或 3 轮。</p>
            </div>

            <div class="scan-launch-action">
              <el-button
                class="scan-start-button"
                data-testid="start-scan"
                type="primary"
                :loading="scanLoading"
                :disabled="scanLoading || attackPlansLoading || !scanPlanId"
                @click="runRedTeamScan()"
              >
                {{ scanLoading ? "Scan 执行中" : "启动 Scan" }}
                <span v-if="!scanLoading" class="button-arrow" aria-hidden="true">↗</span>
              </el-button>
              <p class="field-hint">
                使用当前 Provider 与 Retriever；完成后保存 Snapshot。
              </p>
            </div>
          </div>

          <div class="setup-runtime-note">
            <span class="setup-runtime-dot" aria-hidden="true"></span>
            <span>
              权限、Finding 和完整 Trace 以服务端结果为准。
            </span>
          </div>
        </el-card>
      </section>

      <WorkspaceOperationsView />
      <LocalDiagnosticsView />
      </div>

      <div v-if="activeWorkspace === 'findings'" class="workspace-pane findings-workspace">

      <section class="trace-section" aria-labelledby="trace-title">
        <div class="trace-heading">
          <div>
            <p class="section-kicker">TRACE</p>
            <h2 id="trace-title">执行证据</h2>
          </div>
          <div v-if="result" class="trace-count">
            {{ sortedTraceEvents.length }} 个事件 · 按 sequence 排序
          </div>
        </div>

        <el-card class="trace-card" shadow="never">
          <div v-if="!result" class="trace-empty">
            <span class="trace-empty-line"></span>
            <p>完成一次查询后，检索、授权和工具执行证据将在这里出现。</p>
          </div>
          <el-timeline v-else-if="sortedTraceEvents.length > 0" class="trace-timeline">
            <el-timeline-item
              v-for="event in sortedTraceEvents"
              :key="`${event.sequence}-${event.type}-${event.occurredAt}`"
              :timestamp="formatOccurredAt(event.occurredAt)"
              :type="eventTone(event.type)"
              placement="top"
            >
              <div class="trace-event">
                <div class="trace-event-topline">
                  <span class="trace-sequence">STEP {{ String(event.sequence).padStart(2, "0") }}</span>
                  <el-tag :type="eventTone(event.type)" effect="plain" size="small">
                    {{ eventTypeLabel(event.type) }}
                  </el-tag>
                </div>
                <h3>{{ event.summary }}</h3>
                <p v-if="flowSummary(event)" class="trace-flow">
                  <span class="trace-flow-label">数据流</span>
                  {{ flowSummary(event) }}
                </p>
                <div v-if="traceEvidenceRows(event).length > 0" class="finding-evidence">
                  <template v-for="row in traceEvidenceRows(event)" :key="`${event.sequence}-${row.label}`">
                    <span>{{ row.label }}</span>
                    <code>{{ row.value }}</code>
                  </template>
                </div>
                <pre v-if="hasDetails(event)" class="trace-details">{{ formatDetails(event.details) }}</pre>
              </div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="本次查询没有返回 Trace 事件" />
        </el-card>
      </section>

      <section v-if="result" class="evaluation-section" aria-labelledby="evaluation-title">
        <div class="evaluation-heading">
          <div>
            <p class="section-kicker">CONTRACT CHECK</p>
            <h2 id="evaluation-title">安全结论</h2>
          </div>
          <el-tag
            v-if="evaluation"
            class="evaluation-status"
            :type="evaluationStatusType(evaluation.status)"
            effect="dark"
          >
            {{ evaluationStatusLabel(evaluation.status) }}
          </el-tag>
        </div>

        <el-card class="evaluation-card" shadow="never">
          <div v-if="evaluationLoading" class="evaluation-loading">
            <el-skeleton :rows="4" animated />
            <p>正在依据当前 Security Contract 检查 Trace…</p>
          </div>
          <el-alert
            v-else-if="evaluationError"
            class="evaluation-alert"
            :title="evaluationError"
            type="error"
            :closable="false"
          />
          <template v-else-if="evaluation">
            <div class="evaluation-overview">
              <div>
                <p class="evaluation-contract">
                  Contract <code>{{ evaluation.contractId }}</code>
                  <span>v{{ evaluation.contractVersion }}</span>
                </p>
                <p class="evaluation-caption">
                  {{ evaluation.findings.length > 0 ? "发现需要关注的确定性 Finding" : "当前 Trace 未发现确定性 Finding" }}
                </p>
              </div>
              <el-tag :type="evaluationStatusType(evaluation.status)" effect="plain">
                {{ evaluationStatusLabel(evaluation.status) }}
              </el-tag>
            </div>

            <div v-if="evaluation.findings.length > 0" class="finding-list">
              <article v-for="finding in evaluation.findings" :key="finding.id" class="finding-card">
                <div class="finding-topline">
                  <el-tag type="danger" effect="plain" size="small">
                    {{ findingSeverityLabel(finding.severity) }}
                  </el-tag>
                  <code>{{ findingCategoryLabel(finding.category) }}</code>
                </div>
                <h3>{{ finding.title }}</h3>
                <p>{{ finding.summary }}</p>
                <div class="finding-evidence">
                  <span>ruleId / basis</span>
                  <code>{{ findingRuleLabel(finding) }}</code>
                  <span>evidence sequence</span>
                  <code>{{ finding.evidenceSequences.join(" → ") }}</code>
                </div>
              </article>
            </div>
            <div v-else class="evaluation-passed">
              <span class="evaluation-passed-mark">✓</span>
              <span>资源与工具授权 Trace 未观察到确定性绕过。</span>
            </div>

            <div v-if="evaluation.findings.length > 0" class="semantic-review-area">
              <div class="semantic-review-action">
                <div>
                  <p class="semantic-review-title">需要更易读的上下文说明？</p>
                  <p class="semantic-review-caption">语义解释只补充已有 Finding，不改变确定性结论。</p>
                </div>
                <el-button
                  type="primary"
                  plain
                  :loading="semanticReviewLoading"
                  @click="requestSemanticReview"
                >
                  请求语义解释
                </el-button>
              </div>
              <el-alert
                v-if="semanticReviewError"
                class="evaluation-alert"
                :title="semanticReviewError"
                type="error"
                :closable="false"
              />
              <div
                v-if="evaluation.semanticReview.performed && evaluation.semanticReview.explanation"
                class="semantic-review"
              >
                <span class="semantic-review-label">SEMANTIC REVIEW</span>
                <p>{{ evaluation.semanticReview.explanation }}</p>
              </div>
            </div>
          </template>
          <el-empty v-else description="等待 Trace 评估结果" />
        </el-card>
      </section>
      </div>
    </main>

    <footer class="page-footer">
      <span>知盾 AgentAudit</span>
      <span>受控合成数据 · 不连接真实企业系统</span>
    </footer>
  </div>
</template>
