<script setup lang="ts">
import { computed, ref } from "vue";
import auditChainDataFlowUrl from "../assets/illustrations/audit-chain-data-flow.webp";
import evidencePulseUrl from "../assets/illustrations/evidence-pulse.webp";
import findingEvidenceFocusUrl from "../assets/illustrations/finding-evidence-focus.webp";
import UserProblemCard, { type UserProblem } from "./UserProblemCard.vue";
import type {
  Actor,
  AttackAttempt,
  AttackPlan,
  AuditRuntimeSnapshot,
  Finding,
  RedTeamScan,
  TraceEvent,
  TraceEventType,
} from "@agent-audit/contracts";

type GuidedErrorSource = "plan" | "scan";

const props = withDefaults(
  defineProps<{
    plan: AttackPlan | null;
    scan: RedTeamScan | null;
    runtime: AuditRuntimeSnapshot | null;
    loading: boolean;
    error: string;
    errorDetails?: string | null;
    errorSource?: GuidedErrorSource | null;
  }>(),
  {
    errorDetails: null,
    errorSource: null,
  },
);

const emit = defineEmits<{
  (event: "start"): void;
  (event: "retry"): void;
}>();

type AuditUiStatus = "idle" | "loading" | "error" | "success";
type ChainNodeStatus = "pending" | "observed" | "denied" | "blocked" | "not-observed";
type ChainNodeKind = "actor" | "source" | "resource" | "authorization" | "tool" | "sink";

interface ChainNode {
  key: ChainNodeKind;
  label: string;
  status: ChainNodeStatus;
  events: TraceEvent[];
  actor: Actor | null;
}

interface EvidenceRow {
  label: string;
  value: string;
}

interface ResultContextItem {
  key: "actor" | "source" | "tool" | "sink";
  label: string;
  value: string;
  detail: string;
  tone: "neutral" | "risk" | "evidence";
}

const nodeLabels: Record<ChainNodeKind, string> = {
  actor: "操作人",
  source: "输入来源",
  resource: "读取资料",
  authorization: "权限判断",
  tool: "工具动作",
  sink: "数据去向",
};

const nodeCaptions: Record<ChainNodeKind, string> = {
  actor: "谁发起了请求",
  source: "内容从哪里进入",
  resource: "系统找到了哪些候选资料",
  authorization: "权限规则如何判断",
  tool: "AI 实际调用了什么",
  sink: "数据最终到了哪里",
};

const detailLabels: Record<string, string> = {
  action: "执行动作",
  actorResponse: "返回对象",
  actorId: "操作人 ID",
  arguments: "工具参数",
  approved: "是否审批",
  authorizationDecision: "权限结论",
  authorizationTarget: "检查对象",
  candidates: "候选结果",
  content: "回复内容",
  destination: "目标地址",
  documentId: "文档 ID",
  documentIds: "命中文档",
  dimensions: "向量维度",
  engine: "检索方式",
  engineId: "检索引擎",
  external: "是否外部",
  finishReason: "结束原因",
  includesToolResult: "是否包含工具结果",
  message: "请求内容",
  model: "模型",
  modelName: "Embedding 模型",
  query: "检索问题",
  recordCount: "记录数量",
  reason: "判断原因",
  resourceIds: "涉及资源",
  resourceLabels: "资源标签",
  resourceLabelsById: "资源标签明细",
  ruleId: "规则 ID",
  scores: "相关度",
  sinkId: "流向记录 ID",
  sinkType: "流向类型",
  sourceId: "来源 ID",
  sourceTrustLevels: "来源可信等级",
  sourceType: "来源类型",
  success: "是否成功",
  summary: "结果摘要",
  toolCallCount: "工具调用次数",
  trustLevel: "可信等级",
  toolName: "工具名称",
};

const detailValueLabels: Record<string, string> = {
  admin: "管理员",
  allowed: "允许",
  blocked_source_trust: "因来源不可信而拒绝",
  confidential: "机密",
  customer_export: "客户数据导出",
  denied: "拒绝",
  employee: "普通员工",
  external_document: "外部文档",
  external_message: "外部消息",
  model_context: "模型上下文",
  finance_manager: "财务经理",
  hr: "人力资源",
  knowledge_base: "企业知识库",
  mock_customer_export: "客户数据导出工具",
  mock_customer_lookup: "客户资料查询工具",
  mock_mail_send: "邮件发送工具",
  sales: "销售",
  trusted: "可信",
  untrusted: "不可信",
  user_input: "用户输入",
  visitor: "访客",
};

const previewNodeKinds: ChainNodeKind[] = [
  "actor",
  "source",
  "resource",
  "authorization",
  "tool",
  "sink",
];

const previewNodeTitles: Record<ChainNodeKind, string> = {
  actor: "发起用户",
  source: "输入资料",
  resource: "知识资源",
  authorization: "权限判断",
  tool: "工具动作",
  sink: "数据去向",
};

const eventTypeLabels: Record<TraceEventType, string> = {
  input: "输入",
  source: "来源",
  retrieval: "检索",
  authorization: "权限判断",
  tool_call: "工具调用",
  tool_result: "工具结果",
  sink: "数据流向",
  model_response: "模型响应",
};

const targetKindLabels: Record<AttackPlan["targetKind"], string> = {
  knowledge_document: "知识文档",
  customer_record: "客户记录",
  external_sink: "外部数据去向",
  customer_export: "客户数据导出",
};

const attackerTypeLabels: Record<AttackPlan["attackerType"], string> = {
  outside_in: "外部不可信内容",
  inside_out: "内部合法身份滥用",
};

const uiStatus = computed<AuditUiStatus>(() => {
  if (props.loading) {
    return "loading";
  }
  if (props.error) {
    return "error";
  }
  if (props.scan) {
    return "success";
  }
  return "idle";
});

const guidedProblem = computed<UserProblem | null>(() => {
  if (!props.error) {
    return null;
  }

  if (props.errorSource === "plan") {
    return {
      stage: "准备检查",
      title: "安全检查计划没有加载",
      reason: "当前权限边界还没有返回可运行的检查计划。",
      impact: "暂时不能开始安全检查；已有连接和资料不会被修改。",
      actionLabel: "重新读取检查",
      technicalDetails: props.errorDetails || props.error,
      tone: "warning",
    };
  }

  return {
    stage: "执行安全检查",
    title: "安全检查没有完成",
    reason: "这次检查没有返回完整结果，可能需要确认连接、权限边界或服务状态。",
    impact: "当前不能据此判断风险；之前已保存的资料和记录仍可查看。",
    actionLabel: "再次运行",
    technicalDetails: props.errorDetails || props.error,
  };
});

function resolveGuidedProblem(): void {
  if (props.errorSource === "plan") {
    emit("retry");
    return;
  }
  emit("start");
}

const sortedAttempts = computed<AttackAttempt[]>(() =>
  [...(props.scan?.attempts ?? [])].sort((left, right) => left.round - right.round),
);

/**
 * The latest attempt is the only source for the primary chain and Finding summary.
 * No expected category or model answer is used for either projection.
 */
const latestAttempt = computed<AttackAttempt | null>(
  () => sortedAttempts.value.at(-1) ?? null,
);

const latestActor = computed<Actor | null>(() => latestAttempt.value?.queryResult?.actor ?? null);

const latestTraceEvents = computed<TraceEvent[]>(() =>
  [...(latestAttempt.value?.queryResult?.traceEvents ?? [])].sort(
    (left, right) => left.sequence - right.sequence,
  ),
);

const latestFindings = computed<Finding[]>(() => latestAttempt.value?.evaluation.findings ?? []);

const latestEvaluationStatus = computed(() => latestAttempt.value?.evaluation.status ?? null);

const selectedChainNodeKey = ref<ChainNodeKind | null>(null);

const chainNodes = computed<ChainNode[]>(() => {
  const events = latestTraceEvents.value;
  const sourceEvents = events.filter((event) => event.type === "source");
  const resourceEvents = events.filter((event) => event.type === "retrieval");
  const authorizationEvents = events.filter((event) => event.type === "authorization");
  const toolEvents = events.filter((event) => event.type === "tool_call");
  const sinkEvents = events.filter((event) => event.type === "sink");
  const untrustedSourceEvents = sourceEvents.filter(
    (event) =>
      detailText(event.details.sourceType) === "external_document" ||
      detailText(event.details.trustLevel) === "untrusted",
  );
  const deniedAuthorizationEvents = authorizationEvents.filter(
    (event) => eventDecision(event) === "denied",
  );
  const businessSinkEvents = sinkEvents.filter((event) => {
    const sinkType = detailText(event.details.sinkType);
    return sinkType === "external_message" || sinkType === "customer_export";
  });

  return [
    makeChainNode("actor", [], latestActor.value),
    makeChainNode(
      "source",
      untrustedSourceEvents.length > 0 ? untrustedSourceEvents : sourceEvents,
      null,
    ),
    makeChainNode("resource", resourceEvents, null),
    makeChainNode(
      "authorization",
      deniedAuthorizationEvents.length > 0 ? deniedAuthorizationEvents : authorizationEvents,
      null,
    ),
    makeChainNode("tool", toolEvents, null, authorizationEvents),
    makeChainNode(
      "sink",
      businessSinkEvents,
      null,
      authorizationEvents,
    ),
  ];
});

const selectedChainNode = computed<ChainNode | null>(() =>
  chainNodes.value.find((node) => node.key === selectedChainNodeKey.value) ?? null,
);

const resultContextItems = computed<ResultContextItem[]>(() => {
  if (!latestAttempt.value) {
    return [];
  }

  const source = chainNodes.value.find((node) => node.key === "source");
  const tool = chainNodes.value.find((node) => node.key === "tool");
  const sink = chainNodes.value.find((node) => node.key === "sink");
  const actor = latestActor.value;
  const sourceTrust = source?.events
    .map((event) => detailText(event.details.trustLevel))
    .find((value): value is string => value !== null);

  return [
    {
      key: "actor",
      label: "操作人",
      value: actor?.displayName ?? props.plan?.actorId ?? "未观测到操作人",
      detail: actor ? detailValueLabels[actor.role] ?? actor.role : "未记录身份",
      tone: "neutral",
    },
    {
      key: "source",
      label: "输入来源",
      value: sourceTitle(source?.events ?? []),
      detail: sourceTrust ? detailValueLabels[sourceTrust] ?? sourceTrust : "来源已留证",
      tone: "neutral",
    },
    {
      key: "tool",
      label: "工具动作",
      value: toolTitle(tool?.events ?? []),
      detail: tool && tool.events.length > 0 ? `${tool.events.length} 条调用记录` : "未发生工具调用",
      tone: latestFindings.value.some(
        (finding) =>
          finding.category === "tool_authorization_bypass" ||
          finding.category === "tool_business_policy_violation",
      )
        ? "risk"
        : "neutral",
    },
    {
      key: "sink",
      label: "数据去向",
      value: sinkTitle(sink?.events ?? []),
      detail: sink && sink.events.length > 0 ? `${sink.events.length} 条流向记录` : "未观察到外部流向",
      tone: latestFindings.value.some(
        (finding) => finding.category === "external_sink_policy_violation",
      )
        ? "risk"
        : "evidence",
    },
  ];
});

function toggleChainEvidence(key: ChainNodeKind): void {
  selectedChainNodeKey.value = selectedChainNodeKey.value === key ? null : key;
}

function makeChainNode(
  key: ChainNodeKind,
  events: TraceEvent[],
  actor: Actor | null,
  authorizationEvents: TraceEvent[] = [],
): ChainNode {
  const hasAttempt = latestAttempt.value !== null;
  let status: ChainNodeStatus;

  if (key === "actor") {
    status = actor ? "observed" : hasAttempt ? "not-observed" : "pending";
  } else if (events.length > 0) {
    status = key === "authorization" && hasDeniedDecision(events) ? "denied" : "observed";
  } else if (
    (key === "tool" && hasDeniedAuthorization(authorizationEvents, "tool")) ||
    (key === "sink" && hasDeniedAuthorization(authorizationEvents, "sink"))
  ) {
    status = "blocked";
  } else {
    status = hasAttempt ? "not-observed" : "pending";
  }

  return {
    key,
    label: nodeLabels[key],
    status,
    events,
    actor,
  };
}

function detailText(value: unknown): string | null {
  if (typeof value === "string") {
    return value.trim() || null;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return null;
}

function detailValue(value: unknown): string | null {
  const text = detailText(value);
  if (text) {
    return text;
  }
  if (value !== null && typeof value === "object") {
    const serialized = JSON.stringify(value);
    return serialized && serialized !== "{}" ? serialized : null;
  }
  return null;
}

function readableDetailValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (Array.isArray(value)) {
    return value.map((item) => readableDetailValue(item)).join("、");
  }
  const text = detailValue(value);
  if (!text) {
    return "—";
  }
  return detailValueLabels[text] ?? text;
}

function detailLabel(key: string): string {
  return detailLabels[key] ?? key;
}

function detailValues(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.flatMap((item) => detailValues(item));
  }
  const text = detailValue(value);
  return text ? [text] : [];
}

function unique(values: string[]): string[] {
  return values.filter((value, index) => values.indexOf(value) === index);
}

function eventDetail(event: TraceEvent, keys: string[]): string[] {
  return unique(keys.flatMap((key) => detailValues(event.details[key])));
}

function eventDecision(event: TraceEvent): string | null {
  return detailText(event.details.decision) ?? detailText(event.details.authorizationDecision);
}

function authorizationTarget(event: TraceEvent): string {
  const explicitTarget = detailText(event.details.authorizationTarget);
  if (explicitTarget) {
    return explicitTarget;
  }
  if (event.details.toolName !== undefined) {
    return "tool";
  }
  if (event.details.documentId !== undefined) {
    return "resource";
  }
  return "authorization";
}

function hasDeniedDecision(events: TraceEvent[]): boolean {
  return events.some((event) => eventDecision(event) === "denied");
}

function hasDeniedAuthorization(events: TraceEvent[], target: "tool" | "sink"): boolean {
  return events.some(
    (event) => authorizationTarget(event) === target && eventDecision(event) === "denied",
  );
}

function statusLabel(status: ChainNodeStatus): string {
  switch (status) {
    case "observed":
      return "已观测";
    case "denied":
      return "拒绝 · 已留证";
    case "blocked":
      return "已阻断";
    case "not-observed":
      return "未发生";
    case "pending":
      return "等待验收";
  }
}

function statusDescription(status: ChainNodeStatus): string {
  switch (status) {
    case "observed":
      return "本次执行中确实发生";
    case "denied":
      return "权限检查拒绝，但需继续核对后续是否仍执行";
    case "blocked":
      return "权限边界生效，后续动作没有发生";
    case "not-observed":
      return "本次执行没有发生此动作";
    case "pending":
      return "开始验收后显示实际结果";
  }
}

function actorTitle(actor: Actor | null): string {
  if (!actor) {
    return latestAttempt.value ? "未观测到 Actor" : "尚未执行";
  }
  return `${actor.displayName}发起请求`;
}

function actorFacts(actor: Actor | null): EvidenceRow[] {
  if (!actor) {
    return [];
  }
  return [
    { label: "操作人 ID", value: actor.id },
    { label: "身份角色", value: detailValueLabels[actor.role] ?? actor.role },
  ];
}

function sourceTitle(events: TraceEvent[]): string {
  if (events.length === 0) {
    return latestAttempt.value ? "未发生" : "尚未执行";
  }
  if (
    events.some(
      (event) =>
        detailText(event.details.sourceType) === "external_document" ||
        detailText(event.details.trustLevel) === "untrusted",
    )
  ) {
    return "外部不可信文档进入助手";
  }
  if (events.some((event) => detailText(event.details.sourceType) === "user_input")) {
    return "用户输入进入助手";
  }
  if (events.some((event) => detailText(event.details.sourceType) === "knowledge_base")) {
    return "企业知识库内容进入助手";
  }
  return "输入内容进入助手";
}

function resourceTitle(events: TraceEvent[]): string {
  if (events.length === 0) {
    return latestAttempt.value ? "未发生" : "尚未执行";
  }
  const resources = unique(
    events.flatMap((event) => eventDetail(event, ["documentIds", "resourceIds", "documentId"])),
  );
  if (resources.length > 0) {
    return `检索到 ${resources.length} 份知识资料`;
  }
  return "读取了知识资料";
}

function authorizationTitle(events: TraceEvent[]): string {
  if (events.length === 0) {
    return latestAttempt.value ? "未发生" : "尚未执行";
  }
  const deniedEvent = events.find((event) => eventDecision(event) === "denied");
  const selected = deniedEvent ?? events[0];
  const target = selected ? authorizationTarget(selected) : "authorization";
  const targetLabels: Record<string, string> = {
    resource: "读取资料",
    tool: "调用工具",
    sink: "向外发送",
    authorization: "本次动作",
  };
  const decision = selected ? eventDecision(selected) : null;
  if (decision === "denied") {
    return `权限检查拒绝${targetLabels[target] ?? "本次动作"}`;
  }
  if (decision === "allowed") {
    return `权限检查允许${targetLabels[target] ?? "本次动作"}`;
  }
  return "权限检查已完成";
}

function toolTitle(events: TraceEvent[]): string {
  if (events.length === 0) {
    return latestAttempt.value ? "未发生" : "尚未执行";
  }
  const tools = unique(events.flatMap((event) => eventDetail(event, ["toolName"])));
  const readableTools = tools
    .map((tool) => detailValueLabels[tool])
    .filter((tool): tool is string => tool !== undefined);
  if (readableTools.length === 1) {
    return `调用了${readableTools[0]}`;
  }
  if (readableTools.length > 1) {
    return `调用了 ${readableTools.length} 个业务工具`;
  }
  return tools.length > 0 ? "调用了业务工具" : "执行了工具动作";
}

function sinkTitle(events: TraceEvent[]): string {
  if (events.length === 0) {
    return latestAttempt.value ? "未发生" : "尚未执行";
  }
  const sinkTypes = unique(events.flatMap((event) => eventDetail(event, ["sinkType"])));
  if (sinkTypes.includes("external_message")) {
    return "邮件已到达外部演示地址";
  }
  if (sinkTypes.includes("customer_export")) {
    return "客户数据已写入导出文件";
  }
  return "数据已到达目标位置";
}

function chainNodeTitle(node: ChainNode): string {
  switch (node.key) {
    case "actor":
      return actorTitle(node.actor);
    case "source":
      return sourceTitle(node.events);
    case "resource":
      return resourceTitle(node.events);
    case "authorization":
      return authorizationTitle(node.events);
    case "tool":
      return toolTitle(node.events);
    case "sink":
      return sinkTitle(node.events);
  }
}

function chainNodeExplanation(node: ChainNode): string {
  if (node.status === "pending" || node.status === "not-observed" || node.status === "blocked") {
    return statusDescription(node.status);
  }
  switch (node.key) {
    case "actor":
      return node.actor ? `身份：${detailValueLabels[node.actor.role] ?? node.actor.role}` : statusDescription(node.status);
    case "source":
      return node.events.some((event) => detailText(event.details.trustLevel) === "untrusted")
        ? "该来源已被标记为不可信"
        : "来源信息已记录";
    case "resource": {
      const labels = unique(node.events.flatMap((event) => eventDetail(event, ["resourceLabels"])));
      return labels.includes("confidential") ? "候选资料中包含机密标签" : "候选资料已记录";
    }
    case "authorization":
      if (hasDeniedDecision(node.events)) {
        return "已确认的权限规则明确拒绝了该动作";
      }
      return node.events.some((event) => eventDecision(event) === "allowed")
        ? "已确认的权限规则允许了该动作"
        : "已确认的权限规则完成了判断";
    case "tool":
      return "工具动作和参数已记录";
    case "sink": {
      return "数据去向已记录";
    }
  }
}

function chainStoryText(): string {
  if (!latestAttempt.value) {
    return "开始验收后，这里会用一句话说明本次攻击实际经过了哪些环节。";
  }
  const actor = latestActor.value?.displayName
    ? `${latestActor.value.displayName}发起请求`
    : "本次请求未记录操作人";
  const source = chainNodes.value.find((node) => node.key === "source");
  const resource = chainNodes.value.find((node) => node.key === "resource");
  const authorization = chainNodes.value.find((node) => node.key === "authorization");
  const tool = chainNodes.value.find((node) => node.key === "tool");
  const sink = chainNodes.value.find((node) => node.key === "sink");
  const sourcePhrase = source?.status === "observed" ? sourceTitle(source.events) : "未记录输入来源";
  const resourcePhrase = resource?.status === "observed" ? resourceTitle(resource.events) : "未检索到知识资料";
  const denied = authorization?.status === "denied";
  const authorizationPhrase =
    authorization?.status === "denied"
      ? authorizationTitle(authorization.events)
      : authorization?.status === "observed"
        ? authorizationTitle(authorization.events)
        : "未记录权限判断";
  const toolRan = tool?.status === "observed";
  const sinkReached = sink?.status === "observed";
  const journey = `${actor}，${sourcePhrase}，${resourcePhrase}`;

  if (denied && toolRan && sinkReached) {
    return `${journey}；${authorizationPhrase}，但${toolTitle(tool?.events ?? [])}，${sinkTitle(sink?.events ?? [])}。`;
  }
  if (denied && !sinkReached) {
    const continuation = toolRan ? `${toolTitle(tool?.events ?? [])}，但未观察到数据去向` : "后续动作未发生";
    return `${journey}；${authorizationPhrase}，${continuation}。`;
  }
  if (toolRan && sinkReached) {
    return `${journey}；${authorizationPhrase}，${toolTitle(tool?.events ?? [])}，${sinkTitle(sink?.events ?? [])}。`;
  }
  return `${journey}；${authorizationPhrase}，后续动作请按六个节点继续核对。`;
}

function chainNodeFacts(node: ChainNode): EvidenceRow[] {
  if (node.key === "actor") {
    return actorFacts(node.actor);
  }

  const keysByNode: Record<Exclude<ChainNodeKind, "actor">, string[]> = {
    source: ["sourceType", "sourceId", "documentId", "trustLevel"],
    resource: ["documentIds", "resourceIds", "documentId", "resourceLabels"],
    authorization: [
      "authorizationTarget",
      "decision",
      "authorizationDecision",
      "ruleId",
      "reason",
      "destination",
    ],
    tool: ["toolName", "action", "arguments"],
    sink: ["sinkType", "sinkId", "destination", "external", "authorizationDecision"],
  };

  const rows: EvidenceRow[] = [];
  for (const event of node.events) {
    for (const key of keysByNode[node.key]) {
      const values = eventDetail(event, [key]);
      if (values.length > 0) {
        rows.push({
          label: `${detailLabel(key)} · Trace #${event.sequence}`,
          value: values.map((value) => detailValueLabels[value] ?? value).join("、"),
        });
      }
    }
  }

  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.label}:${row.value}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function chainNodeTone(status: ChainNodeStatus): string {
  return `is-${status}`;
}

function eventTypeLabel(type: TraceEventType): string {
  return eventTypeLabels[type] ?? type;
}

function formatDetailValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  const serialized = JSON.stringify(value, null, 2);
  return serialized ?? String(value);
}

function formatTraceDetails(details: Record<string, unknown>): string {
  return formatDetailValue(details);
}

function traceEventRows(event: TraceEvent): EvidenceRow[] {
  const preferredKeys: Record<TraceEventType, string[]> = {
    input: ["actorId", "message"],
    source: ["sourceType", "trustLevel", "sourceId", "documentId"],
    retrieval: [
      "engineId",
      "modelName",
      "documentIds",
      "resourceLabels",
    ],
    authorization: [
      "authorizationTarget",
      "decision",
      "ruleId",
      "reason",
      "destination",
      "toolName",
      "approved",
      "recordCount",
      "maxRecords",
    ],
    tool_call: ["toolName"],
    tool_result: ["toolName", "success", "summary"],
    sink: [
      "sinkId",
      "sinkType",
      "toolName",
      "destination",
      "external",
      "recordCount",
      "resourceIds",
      "resourceLabels",
      "sourceTrustLevels",
      "approved",
      "authorizationDecision",
    ],
    model_response: ["toolCallCount"],
  };
  const keys = preferredKeys[event.type];
  return keys.flatMap((key) => {
    const value = event.details[key];
    const text = detailValue(value);
    return text ? [{ label: detailLabel(key), value: readableDetailValue(value) }] : [];
  });
}

function traceEventTitle(event: TraceEvent): string {
  switch (event.type) {
    case "input":
      return "收到用户提交的验收请求";
    case "source":
      if (
        detailText(event.details.sourceType) === "external_document" ||
        detailText(event.details.trustLevel) === "untrusted"
      ) {
        return "记录到一项外部不可信文档来源";
      }
      if (detailText(event.details.sourceType) === "knowledge_base") {
        return "记录到一项企业知识库来源";
      }
      if (detailText(event.details.sourceType) === "user_input") {
        return "记录用户输入来源";
      }
      return "记录到一项内容来源";
    case "retrieval": {
      const documents = eventDetail(event, ["documentIds", "resourceIds", "documentId"]);
      return documents.length > 0 ? `检索返回 ${documents.length} 份知识资料` : "完成知识资料检索";
    }
    case "authorization":
      return authorizationTitle([event]);
    case "tool_call":
      return `AI 请求${toolTitle([event])}`;
    case "tool_result":
      return "业务工具返回执行结果";
    case "sink":
      return sinkTitle([event]);
    case "model_response":
      return "AI 返回最终回复";
  }
}

function findingRule(finding: Finding): string {
  return finding.ruleId ?? "default deny（默认拒绝）";
}

function findingEvidenceEvents(finding: Finding): TraceEvent[] {
  const sequences = new Set(finding.evidenceSequences);
  return latestTraceEvents.value.filter((event) => sequences.has(event.sequence));
}

function severityLabel(severity: Finding["severity"]): string {
  return severity === "critical" ? "严重风险 · Critical" : "高风险 · High";
}

function evaluationLabel(status: "passed" | "failed"): string {
  return status === "failed" ? "发现违规" : "检查通过";
}

function stopReasonLabel(reason: RedTeamScan["stopReason"]): string {
  const labels: Record<RedTeamScan["stopReason"], string> = {
    finding_detected: "发现 Finding",
    no_new_variant: "无新变体",
    max_rounds_reached: "达到轮数上限",
  };
  return labels[reason];
}

function formatDuration(durationMs: number): string {
  if (!Number.isFinite(durationMs)) {
    return String(durationMs);
  }
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(2).replace(/\.?0+$/, "")} s`;
  }
  return `${durationMs} ms`;
}

function planTargetLabel(plan: AttackPlan | null): string {
  if (!plan) {
    return "尚未加载";
  }
  return `${targetKindLabels[plan.targetKind]} · ${plan.targetId}`;
}

function previewNodeValue(kind: ChainNodeKind): string {
  if (kind === "actor") {
    return props.plan ? attackerTypeLabels[props.plan.attackerType] : "等待检查计划";
  }
  if (kind === "authorization") {
    return props.plan ? "按权限规则判断" : "等待检查计划";
  }
  if (kind === "sink") {
    return props.plan ? targetKindLabels[props.plan.targetKind] : "等待检查计划";
  }
  return "检查后由过程记录填充";
}

function previewNodeStatus(kind: ChainNodeKind): string {
  return kind === "actor" || kind === "authorization" || kind === "sink" ? "已知" : "待观察";
}

function runtimeModel(runtime: AuditRuntimeSnapshot): string {
  return runtime.model ?? "未配置模型";
}

function statusHeadline(status: AuditUiStatus): string {
  switch (status) {
    case "idle":
      return "还未开始";
    case "loading":
      return "正在验收";
    case "error":
      return "验收失败";
    case "success":
      return latestAttempt.value ? "验收完成" : "没有 Attempt";
  }
}

function statusHint(status: AuditUiStatus): string {
  switch (status) {
    case "idle":
      return "点击主按钮开始，结果会显示在下方。";
    case "loading":
      return "正在执行 Scan，等待真实 Trace。";
    case "error":
      return "处理上方错误后，可以再次验收。";
    case "success":
      return latestAttempt.value
        ? "下面展示最新 Attempt 的 Trace 与 Evaluation。"
        : "本次 Scan 没有返回 Attempt。";
  }
}

function businessFindingSummary(finding: Finding): string {
  const hasDeniedSink = latestTraceEvents.value.some(
    (event) =>
      event.type === "authorization" &&
      authorizationTarget(event) === "sink" &&
      eventDecision(event) === "denied",
  );
  const hasExternalSink = latestTraceEvents.value.some(
    (event) => event.type === "sink" && event.details.external === true,
  );
  const hasDeniedTool = latestTraceEvents.value.some(
    (event) =>
      event.type === "authorization" &&
      authorizationTarget(event) === "tool" &&
      eventDecision(event) === "denied",
  );
  const hasToolAction = latestTraceEvents.value.some(
    (event) => event.type === "tool_call" || event.type === "tool_result",
  );

  switch (finding.category) {
    case "external_sink_policy_violation":
      if (hasDeniedSink && hasExternalSink) {
        return "权限检查已经拒绝向外发送，但外部发送动作仍被执行。";
      }
      if (hasDeniedSink) {
        return "权限检查已经拒绝向外发送，当前过程没有观察到后续外部发送动作。";
      }
      if (hasExternalSink) {
        return "系统执行了外部发送动作，当前权限边界需要进一步核对。";
      }
      return "发现一项外部数据去向策略违规，需要核对权限边界。";
    case "resource_authorization_bypass":
      return "权限检查未能阻止受限资料继续被读取，已形成可追溯证据。";
    case "tool_authorization_bypass":
      if (hasDeniedTool && hasToolAction) {
        return "权限检查已经拒绝调用业务工具，但工具动作仍被执行。";
      }
      return "权限检查未能阻止受限业务工具动作，需要核对工具授权边界。";
    case "tool_business_policy_violation":
      return "工具动作超出当前业务规则允许的数量或审批边界。";
    default:
      return "发现一项需要依据权限规则核对的业务风险。";
  }
}

function resultHeadline(): string {
  if (latestFindings.value.some((finding) => finding.severity === "critical")) {
    return "发现一条业务权限风险";
  }
  if (latestEvaluationStatus.value === "failed") {
    return "发现一项待核对问题";
  }
  return "本次验收通过";
}

function resultSubheadline(): string {
  const firstFinding = latestFindings.value[0];
  if (firstFinding) {
    return businessFindingSummary(firstFinding);
  }
  if (latestEvaluationStatus.value === "passed") {
    return "本次请求没有触发当前 Security Contract 定义的业务权限违规。";
  }
  return "本次执行没有返回可用于判断的完整 Finding，请继续查看过程证据。";
}

function resultStatusLabel(): string {
  if (latestEvaluationStatus.value === "passed") {
    return "检查通过";
  }
  if (latestEvaluationStatus.value === "failed") {
    return "发现风险";
  }
  return "等待结果";
}
</script>

<template>
  <section
    class="guided-audit-flow"
    :class="{ 'has-result': Boolean(latestAttempt) }"
    aria-labelledby="guided-audit-title"
  >
    <header class="guided-hero" :class="{ 'is-result': Boolean(latestAttempt) }">
      <template v-if="latestAttempt">
        <div class="guided-result-heading">
          <span class="guided-result-mark" aria-hidden="true">!</span>
          <div class="guided-hero-copy">
            <p class="guided-kicker">核心验收结果</p>
            <h1 id="guided-audit-title">{{ resultHeadline() }}</h1>
            <p class="guided-lede">{{ resultSubheadline() }}</p>
            <p class="guided-result-boundary">结果来自本次真实 Trace；数据为本地合成演示，不发送真实邮件。</p>
          </div>
        </div>
        <div class="guided-result-actions">
          <span class="guided-result-outcome" :class="`is-${latestEvaluationStatus ?? 'pending'}`">
            {{ resultStatusLabel() }}
          </span>
          <button
            class="guided-start"
            data-testid="guided-start-scan"
            type="button"
            :disabled="props.loading"
            :aria-busy="props.loading"
            aria-label="再次开始核心验收"
            @click="emit('start')"
          >
            再次验收
          </button>
        </div>
      </template>
      <template v-else>
        <div class="guided-hero-copy">
          <p class="guided-kicker">核心验收 · 从内容到数据去向</p>
          <h1 id="guided-audit-title">AI 是否会把企业机密发送到外部？</h1>
          <p class="guided-lede">
            用一次真实检查说明风险如何发生、权限在哪里生效，以及证据是否完整。
          </p>
          <div class="guided-boundary" aria-label="靶场边界">
            <span>合成靶场</span>
            <span>本地演示</span>
            <span>不发送真实邮件</span>
          </div>
        </div>
        <button
          class="guided-start"
          data-testid="guided-start-scan"
          type="button"
          :disabled="props.loading"
          :aria-busy="props.loading"
          aria-label="开始核心验收"
          @click="emit('start')"
        >
          开始核心验收
        </button>
      </template>
    </header>

    <section class="guided-status" :class="`status-${uiStatus}`" role="status" aria-live="polite">
      <div class="status-mark" aria-hidden="true">
        <span v-if="uiStatus === 'success'">✓</span>
        <span v-else-if="uiStatus === 'error'">!</span>
        <span v-else-if="uiStatus === 'loading'">…</span>
        <span v-else>·</span>
      </div>
      <div class="status-copy">
        <strong>{{ statusHeadline(uiStatus) }}</strong>
        <span>{{ statusHint(uiStatus) }}</span>
      </div>

    </section>

    <UserProblemCard
      v-if="guidedProblem"
      class="guided-error"
      data-testid="guided-problem"
      :problem="guidedProblem"
      action-test-id="guided-problem-action"
      @action="resolveGuidedProblem"
    />

    <section
      v-if="latestAttempt"
      class="guided-result-context"
      data-testid="guided-result-context"
      aria-label="本次验收的业务上下文"
    >
      <div
        v-for="(item, index) in resultContextItems"
        :key="item.key"
        class="guided-result-context-item"
        :class="`is-${item.tone}`"
      >
        <span class="guided-result-context-index" aria-hidden="true">{{ String(index + 1).padStart(2, "0") }}</span>
        <div>
          <span class="guided-result-context-label">{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.detail }}</small>
        </div>
      </div>
    </section>

    <nav v-if="latestAttempt" class="workspace-section-nav" aria-label="本次结果阅读顺序" data-testid="guided-result-nav">
      <a href="#guided-summary-title">1 · 看风险结论</a>
      <a href="#guided-chain-title">2 · 沿 Trace 定位</a>
      <a href="#guided-replay-section">3 · 用同一攻击复测</a>
    </nav>
    <section class="guided-plan" data-testid="guided-plan" aria-labelledby="guided-plan-title">
      <div class="section-heading">
        <div>
          <p class="guided-kicker">01 / 权限契约 · Security Contract</p>
          <h2 id="guided-plan-title">先看这条风险链</h2>
        </div>
        <span class="section-note">来自已确认的权限边界</span>
      </div>

      <p v-if="props.plan" class="plan-name">{{ props.plan.name }}</p>
      <dl class="plan-facts">
        <div>
          <dt>执行身份</dt>
          <dd><span>按计划选择的操作人</span> <code>{{ props.plan?.actorId ?? "尚未加载" }}</code></dd>
        </div>
        <div>
          <dt>保护对象</dt>
          <dd>
            <span>{{ planTargetLabel(props.plan) }}</span>
          </dd>
        </div>
        <div>
          <dt>权限边界</dt>
          <dd><code>{{ props.plan?.basisRuleId ?? "尚未加载" }}</code></dd>
        </div>
        <div>
          <dt>测试视角</dt>
          <dd>
            <span>{{ props.plan ? attackerTypeLabels[props.plan.attackerType] : "尚未加载" }}</span>
          </dd>
        </div>
      </dl>

      <div class="plan-message">
        <span class="fact-label">攻击消息</span>
        <p>{{ props.plan?.message ?? "等待服务端返回攻击计划。" }}</p>
      </div>
    </section>

    <section class="guided-chain-section" aria-labelledby="guided-chain-title">
      <div class="section-heading">
        <div>
          <p class="guided-kicker">02 / 全程追踪 · Trace</p>
          <h2 id="guided-chain-title">攻击链</h2>
          <p class="chain-path">谁发起 → 内容来源 → 读取资料 → 权限判断 → 工具动作 → 数据去向</p>
        </div>
        <span v-if="latestAttempt" class="section-note">
          最新一轮检查结果
        </span>
        <span v-else class="section-note">检查后显示实际过程</span>
      </div>

      <p class="chain-story" data-testid="guided-chain-story">{{ chainStoryText() }}</p>

      <div
        class="chain-frame"
        :class="{ 'has-flow-backdrop': !props.loading }"
        data-testid="guided-attack-chain"
      >
        <figure v-if="!props.loading" class="chain-flow-strip" aria-hidden="true">
          <img
            class="chain-flow-backdrop"
            :src="auditChainDataFlowUrl"
            alt=""
            data-testid="guided-chain-flow-backdrop"
            width="1600"
            height="640"
          />
        </figure>
        <figure
          v-if="props.loading"
          class="chain-illustration is-loading"
          data-testid="running-evidence-pulse"
          aria-hidden="true"
        >
          <img :src="evidencePulseUrl" alt="" width="1600" height="615" />
        </figure>
        <ol
          v-else-if="!latestAttempt"
          class="chain-list chain-preview-list"
          data-testid="guided-chain-preview"
          aria-label="核心验收将观察的六个 Trace 环节"
        >
          <li
            v-for="(kind, index) in previewNodeKinds"
            :key="kind"
            class="chain-preview-node"
          >
            <span class="chain-index">{{ String(index + 1).padStart(2, "0") }}</span>
            <div class="chain-node-heading">
              <span class="chain-node-label">{{ nodeLabels[kind] }}</span>
              <span class="chain-node-status">{{ previewNodeStatus(kind) }}</span>
            </div>
            <strong class="chain-preview-title">{{ previewNodeTitles[kind] }}</strong>
            <p class="chain-preview-caption">{{ nodeCaptions[kind] }}</p>
            <code class="chain-preview-value">{{ previewNodeValue(kind) }}</code>
          </li>
        </ol>
        <ol v-else class="chain-list" aria-label="从操作人到数据去向的真实审计链">
          <li
            v-for="(node, index) in chainNodes"
            :key="node.key"
            class="chain-node"
            :class="chainNodeTone(node.status)"
          >
            <span class="chain-index">{{ String(index + 1).padStart(2, "0") }}</span>
            <div class="chain-node-heading">
              <span class="chain-node-label">{{ node.label }}</span>
              <span class="chain-node-status">{{ statusLabel(node.status) }}</span>
            </div>
            <strong class="chain-node-title">{{ chainNodeTitle(node) }}</strong>
            <p class="chain-node-caption">{{ nodeCaptions[node.key] }}</p>
            <p class="chain-node-description">{{ chainNodeExplanation(node) }}</p>
            <button
              v-if="chainNodeFacts(node).length > 0 || node.events.length > 0"
              class="chain-evidence-toggle"
              type="button"
              :aria-expanded="selectedChainNodeKey === node.key"
              :aria-controls="`chain-evidence-${node.key}`"
              @click="toggleChainEvidence(node.key)"
            >
              {{ selectedChainNodeKey === node.key ? "收起证据" : "查看证据" }}
            <span v-if="node.events.length > 0">· {{ node.events.length }} 条过程记录</span>
            </button>
          </li>
        </ol>
        <section
          v-if="selectedChainNode"
          :id="`chain-evidence-${selectedChainNode.key}`"
          class="chain-evidence-panel"
          data-testid="chain-evidence-panel"
          :aria-label="`${selectedChainNode.label}证据`"
        >
          <header class="chain-evidence-panel-heading">
            <div>
              <span>{{ selectedChainNode.label }}证据</span>
              <strong>{{ chainNodeTitle(selectedChainNode) }}</strong>
            </div>
            <button type="button" @click="selectedChainNodeKey = null">关闭</button>
          </header>
          <div v-if="chainNodeFacts(selectedChainNode).length > 0" class="chain-facts">
            <div
              v-for="fact in chainNodeFacts(selectedChainNode)"
              :key="`${selectedChainNode.key}-${fact.label}-${fact.value}`"
            >
              <span>{{ fact.label }}</span>
              <code>{{ fact.value }}</code>
            </div>
          </div>
          <ul v-if="selectedChainNode.events.length > 0" class="chain-evidence-events">
            <li
              v-for="event in selectedChainNode.events"
              :key="`${selectedChainNode.key}-${event.sequence}-${event.occurredAt}`"
            >
              <span>#{{ event.sequence }} · {{ eventTypeLabel(event.type) }}</span>
              <strong class="chain-event-title">{{ traceEventTitle(event) }}</strong>
              <details class="chain-event-json">
                <summary>查看系统原始事件</summary>
                <p>事件类型：<code>{{ event.type }}</code></p>
                <p>原始摘要：{{ event.summary }}</p>
                <pre>{{ formatTraceDetails(event.details) }}</pre>
              </details>
            </li>
          </ul>
        </section>
      </div>
    </section>

    <section class="guided-summary" data-testid="guided-finding-summary" aria-labelledby="guided-summary-title">
      <div class="section-heading">
        <div>
          <p class="guided-kicker">03 / 结论</p>
          <h2 id="guided-summary-title">验收结果</h2>
        </div>
        <span v-if="latestEvaluationStatus" class="evaluation-status" :class="`evaluation-${latestEvaluationStatus}`">
          {{ evaluationLabel(latestEvaluationStatus) }}
        </span>
      </div>

      <div class="summary-metrics">
        <div>
          <strong>{{ latestFindings.length }}</strong>
          <span>Finding</span>
        </div>
        <div>
          <strong>{{ latestTraceEvents.length }}</strong>
          <span>过程记录</span>
        </div>
        <div>
          <strong>{{ props.scan?.attempts.length ?? 0 }}</strong>
          <span>执行轮次</span>
        </div>
        <div>
          <strong>{{ props.scan ? formatDuration(props.scan.durationMs) : "—" }}</strong>
          <span>耗时</span>
          <code v-if="props.scan">{{ props.scan.durationMs }} ms</code>
        </div>
      </div>
      <p v-if="props.scan" class="scan-result-meta">
        Scan <code>{{ props.scan.id }}</code>
        · {{ stopReasonLabel(props.scan.stopReason) }}
        · status <code>{{ props.scan.status }}</code>
        <span v-if="latestAttempt"> · latest Attempt {{ latestAttempt.durationMs }} ms</span>
      </p>

      <div v-if="latestFindings.length > 0" class="finding-list">
        <article v-for="finding in latestFindings" :key="finding.id" class="finding-card">
          <div
            class="finding-heading"
            :class="{ 'is-critical': finding.severity === 'critical' }"
            :data-testid="finding.severity === 'critical' ? 'critical-finding-visual' : undefined"
          >
            <div class="finding-heading-content">
              <div class="finding-topline">
                <span class="finding-severity">{{ severityLabel(finding.severity) }}</span>
              </div>
              <h3>{{ finding.title }}</h3>
            </div>
            <img
              v-if="finding.severity === 'critical'"
              class="finding-evidence-focus"
              :src="findingEvidenceFocusUrl"
              alt=""
              width="1600"
              height="640"
              aria-hidden="true"
            />
          </div>
          <div class="finding-id-block" data-testid="finding-id-block">
            <span>Finding 编号</span>
            <code>{{ finding.id }}</code>
          </div>
          <p>{{ businessFindingSummary(finding) }}</p>
          <dl class="finding-facts">
            <div>
              <dt>命中规则</dt>
              <dd><code>{{ findingRule(finding) }}</code></dd>
            </div>
            <div>
              <dt>关键证据序号</dt>
              <dd>
                <code>{{ finding.evidenceSequences.length > 0 ? finding.evidenceSequences.join(" → ") : "未提供" }}</code>
              </dd>
            </div>
          </dl>
          <details v-if="findingEvidenceEvents(finding).length > 0" class="finding-evidence-details">
            <summary>查看关键证据事件</summary>
            <ul>
              <li v-for="event in findingEvidenceEvents(finding)" :key="`finding-${finding.id}-${event.sequence}`">
                <span>#{{ event.sequence }} · {{ eventTypeLabel(event.type) }}</span>
                <p>{{ event.summary }}</p>
              </li>
            </ul>
          </details>
          <details class="finding-original-details">
            <summary>查看系统原始结论</summary>
            <p>{{ finding.summary }}</p>
          </details>
        </article>
      </div>
      <p v-else-if="latestEvaluationStatus === 'passed'" class="summary-empty success-copy">
        本次通过，未发现 Finding。
      </p>
      <p v-else-if="latestEvaluationStatus === 'failed'" class="summary-empty">
        结论失败，但没有 Finding；展开 Trace 查看证据。
      </p>
      <p v-else class="summary-empty">开始一次验收，结果会显示在这里。</p>
    </section>

    <details class="guided-runtime-details">
      <summary>技术详情 · Runtime</summary>
      <section class="guided-runtime" aria-label="Runtime snapshot">
        <div>
          <p class="guided-kicker">RUNTIME</p>
          <h2>本次执行环境</h2>
        </div>
        <div v-if="props.runtime" class="runtime-facts">
          <span><small>Provider</small><code>{{ props.runtime.provider }}</code></span>
          <span><small>Model</small><code>{{ runtimeModel(props.runtime) }}</code></span>
          <span><small>Retriever</small><code>{{ props.runtime.retrieverEngine }}</code></span>
          <span><small>Indexed docs</small><strong>{{ props.runtime.indexedDocumentCount }}</strong></span>
        </div>
        <p v-else class="runtime-empty">Runtime 尚未读取。</p>
      </section>
    </details>

    <details class="guided-trace-details">
      <summary>技术详情 · 完整 Trace（{{ latestTraceEvents.length }} 个事件）</summary>
      <div v-if="latestTraceEvents.length > 0" class="trace-list">
        <article v-for="event in latestTraceEvents" :key="`${event.sequence}-${event.type}-${event.occurredAt}`" class="trace-event">
          <div class="trace-event-heading">
            <span>#{{ event.sequence }}</span>
            <span>{{ eventTypeLabel(event.type) }}</span>
            <time>{{ event.occurredAt }}</time>
          </div>
          <h3 class="trace-event-title">{{ traceEventTitle(event) }}</h3>
          <div v-if="traceEventRows(event).length > 0" class="trace-facts">
            <div v-for="row in traceEventRows(event)" :key="`${event.sequence}-${row.label}`">
              <span>{{ row.label }}</span>
              <code>{{ row.value }}</code>
            </div>
          </div>
          <details class="trace-event-json">
            <summary>查看系统原始事件</summary>
            <p class="trace-event-original-summary">事件类型：<code>{{ event.type }}</code></p>
            <p class="trace-event-original-summary">原始摘要：{{ event.summary }}</p>
            <pre>{{ formatTraceDetails(event.details) }}</pre>
          </details>
        </article>
      </div>
      <p v-else class="trace-empty">开始验收后，原始 Trace 会保留在这里。</p>
    </details>
  </section>
</template>

<style scoped>
.guided-audit-flow {
  --guided-ink-strong: var(--ink-strong, #f5f8fc);
  --guided-ink: var(--ink, #dbe7f6);
  --guided-muted: var(--ink-muted, #8292a9);
  --guided-faint: var(--ink-faint, #5e6d83);
  --guided-line: var(--line, rgba(160, 181, 207, 0.16));
  --guided-surface: var(--surface, rgba(16, 29, 48, 0.88));
  --guided-accent: var(--accent, #6ee7c5);
  --guided-danger: #fb7185;
  --guided-warning: #fbbf24;
  --guided-success: #6ee7c5;
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  color: var(--guided-ink);
}

.guided-hero,
.guided-status,
.guided-plan,
.guided-chain-section,
.guided-summary,
.guided-runtime,
.guided-trace-details {
  min-width: 0;
  border: 1px solid var(--guided-line);
  background: var(--guided-surface);
  border-radius: 14px;
}

.guided-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  padding: clamp(22px, 4vw, 38px);
  background:
    linear-gradient(135deg, rgba(110, 231, 197, 0.1), transparent 48%),
    var(--guided-surface);
}

.guided-hero-copy {
  min-width: 0;
}

.guided-kicker,
.section-note,
.fact-label,
.plan-facts dt,
.finding-facts dt,
.runtime-facts small,
.status-code,
.chain-index,
.chain-node-label,
.chain-event-ref,
.trace-event-heading,
.summary-metrics span,
.summary-metrics code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

.guided-kicker {
  margin: 0;
  color: var(--guided-accent);
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.guided-hero h1 {
  max-width: 760px;
  margin: 9px 0 0;
  color: var(--guided-ink-strong);
  font-size: clamp(26px, 4vw, 43px);
  font-weight: 700;
  letter-spacing: -0.035em;
  line-height: 1.13;
}

.guided-lede {
  max-width: 700px;
  margin: 13px 0 0;
  color: var(--guided-muted);
  font-size: 13px;
  line-height: 1.7;
}

.guided-boundary {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 17px;
}

.guided-boundary span {
  padding: 5px 8px;
  color: var(--guided-accent);
  background: rgba(110, 231, 197, 0.09);
  border: 1px solid rgba(110, 231, 197, 0.22);
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  line-height: 1.2;
}

.guided-start {
  flex: 0 0 auto;
  min-height: 46px;
  padding: 0 19px;
  color: #071820;
  background: var(--guided-accent);
  border: 0;
  border-radius: 8px;
  box-shadow: 0 10px 24px rgba(70, 220, 180, 0.13);
  cursor: pointer;
  font-size: 13px;
  font-weight: 750;
  white-space: nowrap;
}

.guided-start:hover:not(:disabled) {
  background: #93f2d6;
}

.guided-start:focus-visible,
.guided-trace-details summary:focus-visible,
.chain-evidence-toggle:focus-visible,
.chain-evidence-panel-heading button:focus-visible,
.chain-event-details summary:focus-visible,
.finding-evidence-details summary:focus-visible,
.trace-event-json summary:focus-visible {
  outline: 2px solid var(--guided-accent);
  outline-offset: 3px;
}

.guided-start:disabled {
  cursor: wait;
  opacity: 0.65;
}

.guided-status {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  padding: 12px 15px;
}

.status-mark {
  display: grid;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--guided-accent);
  background: rgba(110, 231, 197, 0.1);
  border: 1px solid rgba(110, 231, 197, 0.25);
  border-radius: 50%;
  font-size: 15px;
  font-weight: 700;
}

.status-copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.status-copy strong {
  color: var(--guided-ink-strong);
  font-size: 12px;
}

.status-copy span {
  color: var(--guided-muted);
  font-size: 11px;
  line-height: 1.45;
}

.status-code {
  margin-left: auto;
  color: var(--guided-faint);
  font-size: 9px;
  letter-spacing: 0.08em;
}

.status-loading {
  border-color: rgba(251, 191, 36, 0.28);
}

.status-loading .status-mark {
  color: var(--guided-warning);
  background: rgba(251, 191, 36, 0.1);
  border-color: rgba(251, 191, 36, 0.25);
}

.status-error {
  border-color: rgba(251, 113, 133, 0.34);
}

.status-error .status-mark {
  color: var(--guided-danger);
  background: rgba(251, 113, 133, 0.1);
  border-color: rgba(251, 113, 133, 0.26);
}

.guided-error {
  margin: 12px 0 0;
  padding: 11px 14px;
  color: #fecdd3;
  background: rgba(127, 29, 29, 0.2);
  border: 1px solid rgba(251, 113, 133, 0.34);
  border-radius: 9px;
  font-size: 11px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.guided-plan,
.guided-chain-section,
.guided-summary,
.guided-runtime,
.guided-trace-details {
  margin-top: 12px;
  padding: clamp(17px, 3vw, 25px);
}

.section-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.section-heading h2,
.guided-runtime h2 {
  margin: 6px 0 0;
  color: var(--guided-ink-strong);
  font-size: 17px;
  font-weight: 650;
  line-height: 1.3;
}

.chain-path {
  margin: 7px 0 0;
  color: var(--guided-faint);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 9px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.chain-story {
  margin: 15px 0 0;
  padding: 12px 14px;
  color: var(--guided-ink-strong);
  background: #f1f8ff;
  border-left: 3px solid var(--guided-action, #4f7cff);
  border-radius: 6px 9px 9px 6px;
  font-size: 13px;
  font-weight: 560;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.section-note {
  flex: 0 1 auto;
  color: var(--guided-faint);
  font-size: 9px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  text-align: right;
}

.plan-name {
  margin: 18px 0 0;
  color: var(--guided-ink-strong);
  font-size: 13px;
  font-weight: 650;
  line-height: 1.5;
}

.plan-facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
  margin: 13px 0 0;
}

.plan-facts > div,
.finding-facts > div {
  min-width: 0;
  padding: 11px 12px;
  background: rgba(5, 13, 24, 0.34);
  border: 1px solid var(--guided-line);
  border-radius: 8px;
}

.plan-facts dt,
.finding-facts dt {
  color: var(--guided-faint);
  font-size: 9px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.plan-facts dd,
.finding-facts dd {
  margin: 7px 0 0;
  color: var(--guided-ink);
  font-size: 11px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

code {
  color: var(--guided-accent);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 10px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.plan-message {
  margin-top: 10px;
  padding: 12px 13px;
  background: rgba(110, 231, 197, 0.055);
  border-left: 2px solid rgba(110, 231, 197, 0.48);
  border-radius: 5px 8px 8px 5px;
}

.fact-label {
  display: block;
  color: var(--guided-faint);
  font-size: 9px;
  letter-spacing: 0.04em;
}

.plan-message p {
  margin: 7px 0 0;
  color: var(--guided-ink);
  font-size: 11px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.chain-frame {
  position: relative;
  margin-top: 17px;
  padding: 13px;
  background: rgba(5, 13, 24, 0.34);
  border: 1px solid var(--guided-line);
  border-radius: 10px;
  overflow: hidden;
}

.chain-flow-backdrop {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.58;
  filter: saturate(0.94) blur(0.2px);
  pointer-events: none;
  transition: opacity 260ms ease;
}

.chain-frame.has-flow-backdrop::after {
  position: absolute;
  z-index: 1;
  inset: 0;
  background: radial-gradient(ellipse at center, rgba(11, 35, 64, 0.08), transparent 80%);
  content: "";
  pointer-events: none;
}

.chain-frame.has-flow-backdrop:hover .chain-flow-backdrop {
  opacity: 0.68;
}

.chain-list {
  position: relative;
  z-index: 2;
  display: grid;
  align-items: stretch;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  grid-auto-rows: 1fr;
  gap: 9px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.chain-preview-node {
  position: relative;
  display: flex;
  min-width: 0;
  min-height: 142px;
  flex-direction: column;
  padding: 13px 11px 12px;
  background:
    radial-gradient(circle at 82% 12%, rgba(77, 132, 255, 0.18), transparent 38%),
    linear-gradient(155deg, rgba(18, 35, 58, 0.72), rgba(7, 20, 38, 0.62));
  border: 1px solid rgba(82, 135, 214, 0.36);
  border-radius: 9px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 8px 20px rgba(2, 12, 28, 0.16);
  backdrop-filter: blur(2px);
}

@media (prefers-reduced-motion: reduce) {
  .chain-flow-backdrop {
    transition: none;
  }

  .chain-frame.has-flow-backdrop:hover .chain-flow-backdrop {
    opacity: 0.58;
  }
}

.chain-preview-node::before {
  position: absolute;
  top: 0;
  right: 12px;
  left: 12px;
  height: 2px;
  background: linear-gradient(90deg, transparent, #4c8dff, transparent);
  content: "";
}

.chain-preview-node:not(:last-child)::after {
  position: absolute;
  top: 44px;
  right: -9px;
  z-index: 2;
  color: #78a7ef;
  content: "→";
  font-size: 14px;
}

.chain-preview-title {
  display: block;
  margin-top: 13px;
  color: #f4f8ff;
  font-size: 13px;
}

.chain-preview-caption {
  margin: 5px 0 0;
  color: #9fb2cc;
  font-size: 9px;
}

.chain-preview-value {
  display: -webkit-box;
  margin-top: auto;
  padding-top: 12px;
  overflow: hidden;
  color: #c9dbf4;
  font-size: 8px;
  line-height: 1.45;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.chain-illustration {
  position: relative;
  margin: 0;
  overflow: hidden;
  aspect-ratio: 13 / 5;
  background: #f7f3ea;
  border: 1px solid rgba(203, 218, 235, 0.82);
  border-radius: 9px;
}

.chain-illustration img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.chain-illustration.is-loading::after {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0 42%,
    rgba(63, 151, 255, 0.08) 46%,
    rgba(255, 184, 77, 0.3) 49.2%,
    rgba(255, 207, 124, 0.42) 50%,
    rgba(255, 184, 77, 0.12) 51.4%,
    transparent 56% 100%
  );
  content: "";
  mix-blend-mode: screen;
  pointer-events: none;
  transform: translateX(-100%);
  animation: evidence-sweep 3.8s ease-in-out infinite;
}

@keyframes evidence-sweep {
  to {
    transform: translateX(100%);
  }
}

.chain-node {
  position: relative;
  display: flex;
  align-self: stretch;
  min-width: 0;
  flex-direction: column;
  min-height: 204px;
  padding: 13px 11px 12px;
  background: rgba(16, 29, 48, 0.7);
  border: 1px solid var(--guided-line);
  border-radius: 9px;
}

.chain-node:not(:last-child)::after {
  position: absolute;
  top: 44px;
  right: -9px;
  z-index: 1;
  color: var(--guided-faint);
  content: "→";
  font-size: 14px;
}

.chain-index {
  color: var(--guided-faint);
  font-size: 10px;
}

.chain-node-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 5px;
  margin-top: 8px;
}

.chain-node-label {
  color: var(--guided-accent);
  font-size: 12px;
  letter-spacing: 0.04em;
}

.chain-node-status {
  flex-shrink: 0;
  color: var(--guided-muted);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
  line-height: 1.3;
  text-align: right;
}

.chain-node-title {
  display: block;
  margin-top: 11px;
  color: var(--guided-ink-strong);
  font-size: 14px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.chain-node-caption,
.chain-node-description {
  margin: 5px 0 0;
  color: var(--guided-muted);
  font-size: 11px;
  line-height: 1.5;
}

.chain-node-description {
  color: var(--guided-faint);
}

.chain-facts {
  display: grid;
  gap: 5px;
  margin-top: 11px;
}

.chain-facts > div {
  display: grid;
  grid-template-columns: minmax(0, auto) minmax(0, 1fr);
  gap: 5px;
  align-items: baseline;
  min-width: 0;
}

.chain-facts span {
  color: var(--guided-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.chain-facts code {
  color: var(--guided-ink);
  font-size: 10px;
  line-height: 1.5;
  text-align: right;
}

.chain-event-ref {
  margin: auto 0 0;
  padding-top: 10px;
  color: var(--guided-faint);
  font-size: 8px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.chain-evidence-toggle {
  margin-top: auto;
  padding: 10px 0 0;
  color: var(--guided-accent);
  background: transparent;
  border: 0;
  font: inherit;
  font-size: 11px;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
}

.chain-evidence-toggle span {
  color: var(--guided-faint);
}

.chain-evidence-panel {
  position: relative;
  z-index: 2;
  margin-top: 14px;
  padding: 18px;
  color: var(--guided-ink);
  background: #ffffff;
  border: 1px solid #9ebcff;
  border-radius: 10px;
  box-shadow: 0 10px 24px rgba(3, 17, 36, 0.2);
}

.chain-evidence-panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 13px;
  border-bottom: 1px solid var(--guided-line);
}

.chain-evidence-panel-heading div {
  display: grid;
  gap: 4px;
}

.chain-evidence-panel-heading span {
  color: #4169d8;
  font-size: 12px;
}

.chain-evidence-panel-heading strong {
  color: var(--guided-ink-strong);
  font-size: 17px;
  line-height: 1.45;
}

.chain-evidence-panel-heading button {
  flex: 0 0 auto;
  padding: 7px 13px;
  color: #4169d8;
  background: #f1f5ff;
  border: 1px solid #cbd7ff;
  border-radius: 7px;
  cursor: pointer;
}

.chain-evidence-panel .chain-facts {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 18px;
}

.chain-evidence-panel .chain-facts > div {
  padding: 10px 12px;
  background: #f8fafc;
  border: 1px solid var(--guided-line);
  border-radius: 7px;
}

.chain-evidence-events {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 0;
  padding: 0;
  list-style: none;
}

.chain-evidence-events > li {
  min-width: 0;
  padding: 12px;
  background: #f8fafc;
  border: 1px solid var(--guided-line);
  border-radius: 7px;
}

.chain-evidence-events > li > span {
  color: var(--guided-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}

.chain-event-details,
.finding-evidence-details,
.trace-event-json,
.chain-event-json {
  min-width: 0;
  margin-top: 8px;
  color: var(--guided-muted);
  font-size: 11px;
}

.chain-event-details summary,
.finding-evidence-details summary,
.trace-event-json summary,
.chain-event-json summary,
.guided-trace-details > summary {
  cursor: pointer;
  color: var(--guided-accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}

.chain-event-details ul,
.finding-evidence-details ul {
  display: grid;
  gap: 8px;
  margin: 8px 0 0;
  padding-left: 14px;
}

.chain-event-details li,
.finding-evidence-details li {
  min-width: 0;
}

.chain-event-details li > span,
.finding-evidence-details li > span {
  color: var(--guided-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
  line-height: 1.4;
}

.chain-event-details p,
.finding-evidence-details p {
  margin: 3px 0 0;
  color: var(--guided-ink);
  font-size: 10px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.chain-event-title {
  display: block;
  margin-top: 7px;
  color: var(--guided-ink-strong);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.chain-event-details pre,
.trace-event-json pre,
.chain-event-json pre {
  max-width: 100%;
  margin: 5px 0 0;
  padding: 7px;
  overflow-x: auto;
  color: var(--guided-ink);
  background: rgba(5, 13, 24, 0.65);
  border: 1px solid var(--guided-line);
  border-radius: 5px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

.chain-node.is-observed {
  border-color: rgba(110, 231, 197, 0.28);
}

.chain-node.is-denied {
  background: rgba(120, 53, 15, 0.17);
  border-color: rgba(251, 191, 36, 0.44);
}

.chain-node.is-denied .chain-node-status {
  color: var(--guided-warning);
}

.chain-node.is-blocked {
  background: rgba(120, 53, 15, 0.11);
  border-color: rgba(251, 191, 36, 0.3);
}

.chain-node.is-blocked .chain-node-status {
  color: var(--guided-warning);
}

.chain-node.is-not-observed .chain-node-status,
.chain-node.is-pending .chain-node-status {
  color: var(--guided-faint);
}

.guided-summary {
  position: relative;
}

.evaluation-status {
  flex: 0 0 auto;
  padding: 5px 8px;
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  line-height: 1.2;
}

.evaluation-failed {
  color: #fecdd3;
  background: rgba(127, 29, 29, 0.32);
  border: 1px solid rgba(251, 113, 133, 0.38);
}

.evaluation-passed {
  color: var(--guided-success);
  background: rgba(110, 231, 197, 0.09);
  border: 1px solid rgba(110, 231, 197, 0.26);
}

.summary-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
  margin-top: 17px;
}

.summary-metrics > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: rgba(5, 13, 24, 0.34);
  border: 1px solid var(--guided-line);
  border-radius: 8px;
}

.summary-metrics strong {
  color: var(--guided-ink-strong);
  font-size: 18px;
  font-weight: 680;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.summary-metrics span {
  color: var(--guided-faint);
  font-size: 9px;
}

.summary-metrics code {
  color: var(--guided-faint);
  font-size: 8px;
}

.finding-list {
  display: grid;
  gap: 9px;
  margin-top: 13px;
}

.scan-result-meta {
  margin: 11px 0 0;
  color: var(--guided-faint);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 9px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.finding-card {
  min-width: 0;
  padding: 14px;
  background: rgba(127, 29, 29, 0.14);
  border: 1px solid rgba(251, 113, 133, 0.28);
  border-left: 3px solid var(--guided-danger);
  border-radius: 8px;
}

.finding-heading {
  min-width: 0;
}

.finding-heading.is-critical {
  position: relative;
  min-height: 148px;
  overflow: hidden;
  margin: -14px -14px 0;
  padding: 18px;
  background: #071a2c;
  border-radius: 7px 7px 0 0;
}

.finding-heading.is-critical::after {
  position: absolute;
  z-index: 1;
  inset: 0;
  background: linear-gradient(90deg, rgba(5, 18, 32, 0.94) 0%, rgba(5, 18, 32, 0.76) 38%, rgba(5, 18, 32, 0.12) 72%);
  content: "";
  pointer-events: none;
}

.finding-evidence-focus {
  position: absolute;
  z-index: 0;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
}

.finding-heading-content {
  position: relative;
  z-index: 2;
  min-width: 0;
}

.finding-heading.is-critical .finding-heading-content {
  display: flex;
  min-height: 112px;
  max-width: 72%;
  flex-direction: column;
  justify-content: space-between;
}

.finding-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 9px;
}

.finding-topline code {
  overflow-wrap: anywhere;
}

.finding-id-block {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  margin-top: 10px;
  padding: 10px 12px;
  color: var(--guided-ink-strong);
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(251, 113, 133, 0.4);
  border-radius: 7px;
}

.finding-id-block span {
  color: var(--guided-muted);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.04em;
}

.finding-id-block code {
  color: var(--guided-ink-strong);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
  text-align: right;
}

.finding-severity {
  padding: 4px 7px;
  color: #fecdd3;
  background: rgba(251, 113, 133, 0.14);
  border: 1px solid rgba(251, 113, 133, 0.3);
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.finding-card h3 {
  margin: 10px 0 0;
  color: var(--guided-ink-strong);
  font-size: 13px;
  line-height: 1.45;
}

.finding-heading.is-critical h3 {
  color: #f5f9ff;
  font-size: 15px;
  text-shadow: 0 1px 12px rgba(0, 0, 0, 0.36);
}

.finding-heading.is-critical + p {
  margin-top: 12px;
}

.finding-card > p {
  margin: 6px 0 0;
  color: var(--guided-muted);
  font-size: 11px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.finding-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 12px 0 0;
}

.finding-facts > div {
  padding: 9px 10px;
}

.finding-facts dd {
  font-size: 10px;
}

.summary-empty,
.runtime-empty,
.trace-empty {
  margin: 14px 0 0;
  color: var(--guided-muted);
  font-size: 11px;
  line-height: 1.6;
}

.success-copy {
  color: var(--guided-success);
}

.guided-runtime {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
}

.guided-runtime h2 {
  margin-top: 5px;
  font-size: 13px;
}

.runtime-facts {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
}

.runtime-facts span {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.runtime-facts small {
  color: var(--guided-faint);
  font-size: 8px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.runtime-facts code,
.runtime-facts strong {
  color: var(--guided-ink);
  font-size: 9px;
  overflow-wrap: anywhere;
}

.guided-trace-details > summary {
  list-style-position: inside;
  color: var(--guided-ink-strong);
  font-size: 13px;
  font-weight: 650;
  line-height: 1.45;
}

.trace-list {
  display: grid;
  gap: 11px;
  margin-top: 16px;
}

.trace-event {
  min-width: 0;
  padding: 15px 16px;
  background: rgba(5, 13, 24, 0.34);
  border: 1px solid var(--guided-line);
  border-radius: 7px;
}

.trace-event-heading {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 9px;
  color: var(--guided-accent);
  font-size: 11px;
  line-height: 1.45;
}

.trace-event-heading time {
  color: var(--guided-faint);
  overflow-wrap: anywhere;
}

.trace-event > p {
  margin: 7px 0 0;
  color: var(--guided-ink);
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.trace-event-title {
  margin: 11px 0 0;
  color: var(--guided-ink-strong);
  font-size: 16px;
  font-weight: 680;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.trace-event-original-summary {
  color: var(--guided-muted) !important;
  font-size: 12px !important;
}

.trace-event-original-summary::first-letter {
  color: var(--guided-faint);
}

.trace-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 9px;
  align-items: stretch;
  margin-top: 13px;
  padding-top: 12px;
  border-top: 1px solid var(--guided-line);
}

.trace-facts > div {
  display: block;
  min-width: 0;
  padding: 10px 11px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--guided-line);
  border-radius: 7px;
}

.trace-facts span {
  color: var(--guided-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
  line-height: 1.4;
}

.trace-facts code {
  display: block;
  margin-top: 5px;
  color: var(--guided-ink);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

@media (max-width: 900px) {
  .chain-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .chain-node:nth-child(3)::after,
  .chain-node:nth-child(6)::after,
  .chain-preview-node:nth-child(3)::after,
  .chain-preview-node:nth-child(6)::after {
    display: none;
  }

  .chain-node:nth-child(2)::after,
  .chain-node:nth-child(5)::after {
    content: "↓";
    top: auto;
    right: 50%;
    bottom: -13px;
  }
}

@media (max-width: 680px) {
  .guided-hero {
    align-items: stretch;
    flex-direction: column;
    gap: 20px;
  }

  .guided-start {
    width: 100%;
  }

  .plan-facts,
  .summary-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .guided-runtime {
    align-items: flex-start;
    flex-direction: column;
  }

  .runtime-facts {
    width: 100%;
    justify-content: flex-start;
  }

  .chain-evidence-panel .chain-facts,
  .chain-evidence-events {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .guided-audit-flow {
    min-width: 0;
  }

  .guided-hero,
  .guided-plan,
  .guided-chain-section,
  .guided-summary,
  .guided-runtime,
  .guided-trace-details {
    border-radius: 10px;
  }

  .guided-hero h1 {
    font-size: 26px;
  }

  .guided-lede {
    font-size: 12px;
  }

  .section-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 7px;
  }

  .section-note {
    text-align: left;
  }

  .plan-facts,
  .summary-metrics,
  .finding-facts {
    grid-template-columns: 1fr;
  }

  .chain-frame {
    padding: 9px;
  }

  .chain-evidence-panel {
    padding: 14px;
  }

  .chain-evidence-panel-heading strong {
    font-size: 15px;
  }

  .chain-list {
    align-items: start;
    grid-template-columns: 1fr;
    grid-auto-rows: auto;
    gap: 10px;
  }

  .chain-node {
    align-self: start;
    width: 100%;
    min-height: 0;
  }

  .chain-preview-node {
    align-self: start;
    width: 100%;
  }

  .chain-node:not(:last-child)::after,
  .chain-node:nth-child(2)::after,
  .chain-node:nth-child(5)::after,
  .chain-preview-node:not(:last-child)::after,
  .chain-preview-node:nth-child(2)::after,
  .chain-preview-node:nth-child(5)::after {
    top: auto;
    right: 50%;
    bottom: -15px;
    display: block;
    content: "↓";
  }

  .chain-node:last-child::after {
    display: none;
  }

  .chain-preview-node {
    min-height: 112px;
  }

  .chain-preview-node:last-child::after {
    display: none;
  }

  .status-code {
    display: none;
  }
}

/* F-032 visual hierarchy: light workbench, with the chain as the dark evidence anchor. */
.guided-audit-flow {
  --guided-ink-strong: #132238;
  --guided-ink: #28384d;
  --guided-muted: #64748b;
  --guided-faint: #8a99ad;
  --guided-line: #dbe4ef;
  --guided-surface: #ffffff;
  --guided-canvas: #f4f7fb;
  --guided-brand: #0b2340;
  --guided-action: #4f7cff;
  --guided-danger: #ff5d5d;
  --guided-warning: #e6a23c;
  --guided-success: #25bfae;
  color: var(--guided-ink);
}

.guided-hero,
.guided-status,
.guided-plan,
.guided-chain-section,
.guided-summary,
.guided-runtime,
.guided-trace-details {
  border-color: var(--guided-line);
  background: var(--guided-surface);
  box-shadow: 0 10px 30px rgba(24, 50, 83, 0.06);
}

.guided-hero {
  background: linear-gradient(112deg, #0b2340 0%, #163a63 100%);
  border-color: #0b2340;
  box-shadow: 0 18px 36px rgba(11, 35, 64, 0.18);
}

.guided-hero .guided-kicker,
.guided-hero h1 {
  color: #ffffff;
}

.guided-hero .guided-lede {
  color: #d8e5f5;
}

.guided-hero .guided-boundary span {
  color: #d7fff4;
  background: rgba(37, 191, 174, 0.14);
  border-color: rgba(130, 239, 220, 0.32);
}

.guided-start {
  color: #ffffff;
  background: var(--guided-action);
  box-shadow: 0 10px 24px rgba(79, 124, 255, 0.3);
}

.guided-start:hover:not(:disabled) {
  background: #6d93ff;
}

.guided-start:focus-visible,
.guided-trace-details summary:focus-visible,
.guided-runtime-details summary:focus-visible,
.chain-evidence-toggle:focus-visible,
.chain-evidence-panel-heading button:focus-visible,
.chain-event-details summary:focus-visible,
.chain-event-json summary:focus-visible,
.finding-evidence-details summary:focus-visible,
.trace-event-json summary:focus-visible {
  outline-color: var(--guided-action);
}

.guided-status {
  background: #ffffff;
}

.status-mark {
  color: var(--guided-action);
  background: #eef2ff;
  border-color: #cbd7ff;
}

.status-copy strong,
.section-heading h2,
.guided-runtime h2,
.plan-name,
.summary-metrics strong,
.finding-card h3,
.chain-node-title {
  color: var(--guided-ink-strong);
}

.status-copy span,
.guided-lede,
.chain-node-caption,
.chain-node-description,
.summary-empty,
.runtime-empty,
.finding-card > p {
  color: var(--guided-muted);
}

.status-loading {
  border-color: #f1d39a;
  background: #fffaf0;
}

.status-loading .status-mark {
  color: #9a650f;
  background: #fff4d9;
  border-color: #f1d39a;
}

.status-error,
.guided-error {
  border-color: #ffcaca;
}

.status-error {
  background: #fff7f7;
}

.status-error .status-mark {
  color: #c53b3b;
  background: #fff0f0;
  border-color: #ffcaca;
}

.guided-error {
  color: #9f3030;
  background: #fff1f1;
}

.guided-plan,
.guided-chain-section,
.guided-summary,
.guided-runtime,
.guided-trace-details {
  background: #ffffff;
}

.guided-kicker,
.guided-runtime-details > summary,
.guided-trace-details > summary {
  color: var(--guided-action);
}

.section-note,
.chain-path,
.plan-facts dt,
.finding-facts dt,
.fact-label,
.runtime-facts small,
.status-code,
.chain-index,
.chain-node-status,
.scan-result-meta,
.summary-metrics span,
.summary-metrics code {
  color: var(--guided-faint);
}

.plan-facts > div,
.finding-facts > div,
.summary-metrics > div,
.trace-event {
  background: #f8fafc;
  border-color: var(--guided-line);
}

.plan-message {
  background: #f1f8ff;
  border-left-color: var(--guided-action);
}

.plan-message p,
.plan-facts dd,
.finding-facts dd,
.trace-event > p,
.runtime-facts code,
.runtime-facts strong,
.finding-card > p {
  color: var(--guided-ink);
}

.guided-chain-section {
  overflow: hidden;
}

.chain-frame {
  background: var(--guided-brand);
  border-color: #0b2340;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.09);
}

.chain-node {
  background: #ffffff;
  border-color: #cdd9e7;
  box-shadow: 0 5px 14px rgba(3, 17, 36, 0.13);
}

.chain-node:not(:last-child)::after {
  color: #9ebcff;
}

.chain-node-label {
  color: #4169d8;
}

.chain-node-status {
  color: var(--guided-muted);
}

.chain-node.is-observed {
  border-color: #8edfd3;
}

.chain-node.is-observed .chain-node-status {
  color: #118f81;
}

.chain-node.is-denied {
  background: #fff7f7;
  border-color: #ff9d9d;
  box-shadow: 0 5px 16px rgba(255, 93, 93, 0.12);
}

.chain-node.is-denied .chain-node-status,
.chain-node.is-blocked .chain-node-status {
  color: #c84242;
}

.chain-node.is-blocked {
  background: #f0fbf9;
  border-color: #86d9ce;
}

.chain-node.is-blocked .chain-node-status {
  color: #118f81;
}

.chain-node.is-not-observed .chain-node-status,
.chain-node.is-pending .chain-node-status {
  color: #98a6b7;
}

.chain-facts span,
.chain-evidence-toggle,
.chain-event-details,
.chain-event-json,
.finding-evidence-details,
.trace-event-json {
  color: var(--guided-muted);
}

.chain-facts code,
code {
  color: #4169d8;
}

.chain-event-details summary,
.chain-evidence-toggle,
.finding-evidence-details summary,
.trace-event-json summary,
.chain-event-json summary {
  color: #4169d8;
}

.chain-event-details pre,
.trace-event-json pre,
.chain-event-json pre {
  color: #dce8f8;
  background: #102c4f;
  border-color: #254a73;
}

.evaluation-failed {
  color: #b52e2e;
  background: #fff0f0;
  border-color: #ffb1b1;
}

.evaluation-passed,
.success-copy {
  color: #118f81;
}

.evaluation-passed {
  background: #eafaf7;
  border-color: #9be0d7;
}

.finding-card {
  background: #fff5f5;
  border-color: #ffcaca;
  border-left-color: var(--guided-danger);
}

.finding-id-block {
  color: var(--guided-ink-strong);
  background: #ffffff;
  border-color: #ffb1b1;
}

.finding-id-block span {
  color: #9f3030;
}

.finding-id-block code {
  color: #173f78;
}

.finding-severity {
  color: #b52e2e;
  background: #ffe7e7;
  border-color: #ffb1b1;
}

.guided-runtime-details {
  margin-top: 12px;
  padding: 13px 17px;
  border: 1px solid var(--guided-line);
  border-radius: 14px;
  background: #f8fafc;
}

.guided-runtime-details > summary {
  cursor: pointer;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.guided-runtime-details .guided-runtime {
  margin-top: 12px;
  box-shadow: none;
}

.guided-trace-details {
  background: #f8fafc;
}

@media (max-width: 480px) {
  .guided-runtime-details {
    padding: 12px 14px;
  }

  .chain-frame {
    padding: 9px;
  }

  .chain-illustration {
    aspect-ratio: 3 / 2;
  }

  .finding-heading.is-critical {
    min-height: 118px;
    padding: 14px;
  }

  .finding-heading.is-critical .finding-heading-content {
    min-height: 90px;
    max-width: 72%;
  }

  .finding-heading.is-critical h3 {
    font-size: 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .chain-illustration.is-loading::after {
    animation: none;
  }
}

/* F-060: the default reading layer is business-first; technical values stay
 * available in the existing folded evidence sections. */
.guided-kicker,
.section-note,
.fact-label,
.plan-facts dt,
.finding-facts dt,
.runtime-facts small,
.status-code,
.chain-index,
.chain-node-label,
.summary-metrics span {
  color: var(--guided-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.guided-hero .guided-kicker,
.guided-hero .section-note {
  color: #d7fff4;
}

.guided-lede {
  color: #d8e5f5;
  font-size: var(--type-body-size, 15px);
  line-height: var(--type-body-leading, 1.62);
}

.guided-boundary span {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.status-copy strong {
  font-size: var(--type-card-title-size, 18px);
}

.status-copy span {
  color: var(--guided-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.status-code {
  color: var(--guided-muted);
}

.guided-error.user-problem-card {
  margin-top: 12px;
  font-family: var(--font-ui);
}

.section-heading h2,
.guided-runtime h2 {
  font-size: var(--type-section-title-size, 23px);
  line-height: var(--type-heading-leading, 1.22);
}

.section-note {
  text-align: right;
}

.chain-path,
.chain-story,
.plan-message p {
  font-family: var(--font-ui);
}

.chain-path {
  color: var(--guided-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.chain-story {
  font-size: var(--type-body-size, 15px);
  line-height: var(--type-body-leading, 1.62);
}

.plan-name {
  font-size: var(--type-card-title-size, 18px);
}

.plan-facts dt,
.finding-facts dt,
.fact-label {
  color: var(--guided-muted);
}

.plan-facts dd,
.finding-facts dd,
.plan-message p {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.chain-preview-title,
.chain-node-title,
.finding-card h3 {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.chain-preview-caption,
.chain-node-caption,
.chain-node-description,
.chain-evidence-toggle,
.summary-empty,
.runtime-empty,
.trace-empty,
.finding-card > p {
  color: var(--guided-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.chain-preview-value {
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
}

.chain-node-status,
.chain-facts span,
.chain-event-details summary,
.chain-event-json summary,
.finding-evidence-details summary,
.trace-event-json summary {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.chain-node-status,
.chain-facts span {
  color: var(--guided-muted);
}

.chain-evidence-toggle {
  min-height: 40px;
  padding-top: 10px;
}

.summary-metrics span,
.summary-metrics code,
.scan-result-meta {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.finding-severity,
.evaluation-status {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.finding-heading.is-critical h3 {
  font-size: var(--type-card-title-size, 18px);
}

.finding-id-block span,
.finding-facts dd {
  font-size: var(--type-body-small-size, 13px);
}

.runtime-facts small,
.runtime-facts code,
.runtime-facts strong,
.trace-event-heading,
.trace-event-original-summary {
  font-size: var(--type-body-small-size, 13px);
}

.guided-runtime-details > summary,
.guided-trace-details > summary {
  font-family: var(--font-ui);
  font-size: var(--type-card-title-size, 18px);
}

/* F-061: evidence text remains readable while IDs and raw payloads stay technical. */
.chain-event-title {
  font-family: var(--font-ui);
  font-size: var(--type-body-size, 15px);
  line-height: var(--type-body-leading, 1.62);
}

.chain-evidence-events > li > span,
.chain-event-details li > span,
.finding-evidence-details li > span,
.trace-facts span {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.chain-event-details p,
.finding-evidence-details p {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

/* F-063: result state uses shared semantic tokens.  The existing assets remain
 * state-driven, and readable business copy stays outside each illustration. */
.guided-audit-flow {
  max-width: 1440px;
  color: var(--ink);
}

.guided-audit-flow code {
  font-family: var(--font-code, "SFMono-Regular", Consolas, monospace);
}

.guided-audit-flow .guided-hero.is-result {
  align-items: center;
  min-height: 136px;
  padding: 22px 24px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 5px solid var(--risk-coral);
  border-radius: var(--radius-card) var(--radius-card) 0 0;
  box-shadow: var(--shadow-card);
}

.guided-result-heading {
  display: flex;
  align-items: flex-start;
  min-width: 0;
  gap: 16px;
}

.guided-result-mark {
  display: grid;
  width: 52px;
  height: 52px;
  flex: 0 0 52px;
  place-items: center;
  color: var(--risk-coral);
  background: #fff1f1;
  border: 1px solid #ffd0d0;
  border-radius: 10px;
  font-size: 30px;
  font-weight: 800;
  line-height: 1;
}

.guided-hero.is-result .guided-hero-copy {
  min-width: 0;
}

.guided-hero.is-result .guided-kicker {
  color: var(--risk-coral);
}

.guided-hero.is-result h1 {
  margin-top: 6px;
  color: var(--ink-strong);
  font-size: clamp(25px, 3vw, 32px);
  letter-spacing: -0.025em;
}

.guided-hero.is-result .guided-lede {
  max-width: 900px;
  margin-top: 7px;
  color: var(--ink-muted);
  font-size: var(--type-body-size, 15px);
  line-height: var(--type-body-leading, 1.62);
}

.guided-result-boundary {
  margin: 8px 0 0;
  color: var(--ink-faint);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.guided-result-actions {
  display: flex;
  align-items: flex-end;
  flex: 0 0 auto;
  flex-direction: column;
  gap: 11px;
}

.guided-result-outcome {
  color: var(--risk-coral);
  font-size: var(--type-label-size, 12px);
  font-weight: 700;
  line-height: var(--type-label-leading, 1.35);
}

.guided-result-outcome.is-passed {
  color: var(--evidence-teal);
}

.guided-result-outcome.is-failed {
  color: var(--risk-coral);
}

.guided-audit-flow.has-result > .guided-status,
.guided-audit-flow.has-result > .guided-plan {
  display: none;
}

.guided-result-context {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  min-width: 0;
  margin-top: -1px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-top: 0;
  border-radius: 0 0 var(--radius-card) var(--radius-card);
  box-shadow: var(--shadow-card);
}

.guided-result-context-item {
  position: relative;
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 11px;
  padding: 17px 18px 18px;
}

.guided-result-context-item:not(:last-child)::after {
  position: absolute;
  top: 18px;
  right: 0;
  bottom: 18px;
  width: 1px;
  background: var(--line);
  content: "";
}

.guided-result-context-index {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  place-items: center;
  color: var(--action-blue-strong);
  background: #eef2ff;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 750;
}

.guided-result-context-item > div {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.guided-result-context-label {
  color: var(--ink-muted);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.guided-result-context-item strong {
  color: var(--ink-strong);
  font-size: var(--type-body-size, 15px);
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.guided-result-context-item small {
  color: var(--ink-muted);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
  overflow-wrap: anywhere;
}

.guided-result-context-item.is-risk .guided-result-context-index {
  color: var(--risk-coral);
  background: #fff1f1;
}

.guided-result-context-item.is-risk strong {
  color: #b52e2e;
}

.guided-result-context-item.is-evidence .guided-result-context-index {
  color: var(--evidence-teal);
  background: #eafaf7;
}

.guided-audit-flow.has-result .guided-chain-section,
.guided-audit-flow.has-result .guided-summary {
  margin-top: 26px;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.guided-audit-flow.has-result .guided-chain-section > .section-heading {
  padding: 0 0 2px;
}

.guided-audit-flow.has-result .section-heading h2 {
  color: var(--ink-strong);
  font-size: var(--type-section-title-size, 23px);
}

.guided-audit-flow.has-result .chain-path {
  color: var(--ink-muted);
}

.guided-audit-flow.has-result .chain-story {
  margin-top: 12px;
  padding: 11px 13px;
  color: var(--ink);
  background: var(--surface-raised);
  border-left: 3px solid var(--action-blue-strong);
  border-radius: 0 6px 6px 0;
  font-size: var(--type-body-small-size, 13px);
  font-weight: 560;
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-audit-flow .chain-frame,
.guided-audit-flow.has-result .chain-frame {
  position: relative;
  margin-top: 14px;
  padding: var(--space-4);
  overflow: hidden;
  isolation: isolate;
  background: var(--surface-evidence);
  border: 1px solid var(--brand-navy);
  border-radius: var(--radius-stage);
  box-shadow: var(--shadow-overlay);
}

.guided-audit-flow .chain-frame.has-flow-backdrop::after {
  z-index: 1;
  display: block;
  background: linear-gradient(180deg, rgba(11, 35, 64, 0.14), rgba(11, 35, 64, 0.42));
}

.chain-flow-strip {
  position: absolute;
  z-index: 0;
  inset: 0;
  height: auto;
  margin: 0;
  overflow: hidden;
  background: var(--surface-evidence);
  border: 0;
  border-radius: inherit;
  pointer-events: none;
}

.guided-audit-flow .chain-flow-backdrop {
  position: absolute;
  z-index: 0;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 54%;
  opacity: 0.72;
  filter: saturate(1.02);
  transition: opacity 180ms ease;
}

.guided-audit-flow .chain-flow-strip:hover .chain-flow-backdrop {
  opacity: 0.8;
}

.guided-audit-flow .chain-illustration {
  z-index: 2;
  background: var(--surface-evidence);
  border-color: var(--line-on-dark);
  border-radius: var(--radius-card);
  box-shadow: none;
}

.guided-audit-flow .chain-preview-value {
  color: var(--ink-muted);
}

.guided-audit-flow.has-result .chain-list {
  position: relative;
  z-index: 2;
  grid-template-rows: minmax(214px, 1fr);
  gap: 12px;
  padding: 0;
}

.guided-audit-flow .chain-node,
.guided-audit-flow .chain-preview-node,
.guided-audit-flow.has-result .chain-node,
.guided-audit-flow.has-result .chain-preview-node {
  min-height: 214px;
  padding: 15px 14px 14px;
  background: var(--surface);
  border: 1px solid var(--line-bright);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  backdrop-filter: none;
}

.guided-audit-flow .chain-node:not(:last-child)::after,
.guided-audit-flow .chain-preview-node:not(:last-child)::after {
  color: rgba(255, 255, 255, 0.86);
  font-size: 20px;
}

.guided-audit-flow .chain-node-label {
  color: var(--action-blue-strong);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow .chain-node-status {
  color: var(--ink-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow .chain-node-title,
.guided-audit-flow .chain-preview-title {
  color: var(--ink-strong);
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.guided-audit-flow .chain-node-caption,
.guided-audit-flow .chain-node-description,
.guided-audit-flow .chain-preview-caption {
  color: var(--ink-muted);
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-audit-flow .chain-node.is-denied {
  background: #fff7f7;
  border-color: #ff9d9d;
  box-shadow: 0 8px 20px rgba(255, 93, 93, 0.1);
}

.guided-audit-flow .chain-node.is-denied .chain-node-label,
.guided-audit-flow .chain-node.is-denied .chain-node-status {
  color: var(--risk-coral);
}

.guided-audit-flow .chain-node.is-blocked {
  background: #f0fbf9;
  border-color: #86d9ce;
  box-shadow: 0 8px 20px rgba(37, 191, 174, 0.1);
}

.guided-audit-flow .chain-node.is-blocked .chain-node-status {
  color: var(--evidence-teal);
}

.guided-audit-flow .chain-index {
  color: var(--ink-faint);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow .chain-evidence-toggle {
  min-height: 44px;
  color: var(--action-blue-strong);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow .chain-evidence-panel,
.guided-audit-flow.has-result .chain-evidence-panel {
  position: relative;
  z-index: 3;
  margin: var(--space-4) 0 0;
  padding: var(--space-6);
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--line-bright);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.guided-audit-flow.has-result .chain-evidence-panel-heading {
  padding-bottom: 12px;
  border-color: var(--line);
}

.guided-audit-flow.has-result .chain-evidence-panel-heading span,
.guided-audit-flow.has-result .chain-evidence-panel-heading button {
  color: var(--action-blue-strong);
}

.guided-audit-flow.has-result .chain-evidence-panel-heading strong {
  color: var(--ink-strong);
  font-size: var(--type-card-title-size, 18px);
}

.guided-audit-flow .chain-evidence-panel-heading button {
  min-height: 44px;
  background: #eef2ff;
  border-color: #cbd7ff;
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow.has-result .chain-evidence-panel .chain-facts > div,
.guided-audit-flow.has-result .chain-evidence-events > li {
  background: #ffffff;
  border-color: var(--line);
}

.guided-audit-flow.has-result .chain-evidence-events > li > span,
.guided-audit-flow.has-result .chain-facts span {
  color: var(--ink-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow.has-result .chain-event-title {
  color: var(--ink-strong);
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 13px);
}

.guided-audit-flow.has-result .guided-summary .section-heading {
  margin-bottom: 12px;
}

.guided-audit-flow.has-result .summary-metrics {
  gap: 0;
  margin-top: 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.guided-audit-flow.has-result .summary-metrics > div {
  padding: 13px 14px;
  background: transparent;
  border: 0;
  border-right: 1px solid var(--line);
  border-radius: 0;
}

.guided-audit-flow.has-result .summary-metrics > div:last-child {
  border-right: 0;
}

.guided-audit-flow.has-result .summary-metrics strong {
  color: var(--ink-strong);
  font-size: 22px;
}

.guided-audit-flow.has-result .summary-metrics span,
.guided-audit-flow.has-result .summary-metrics code,
.guided-audit-flow.has-result .scan-result-meta {
  color: var(--ink-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow.has-result .finding-list {
  margin-top: 14px;
}

.guided-audit-flow.has-result .finding-card {
  padding: 0;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid #ffcaca;
  border-left: 4px solid var(--risk-coral);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
}

.guided-audit-flow.has-result .finding-heading.is-critical {
  display: block;
  min-height: 0;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: var(--surface);
  border-radius: 0;
}

.guided-audit-flow.has-result .finding-heading.is-critical::after {
  display: none;
}

.guided-audit-flow.has-result .finding-heading-content {
  display: flex;
  min-width: 0;
  min-height: 0;
  max-width: none;
  flex-direction: column;
  justify-content: center;
  padding: var(--space-6);
}

.guided-audit-flow.has-result .finding-evidence-focus {
  position: static;
  display: block;
  width: 100%;
  height: 200px;
  min-height: 200px;
  max-height: 240px;
  object-fit: cover;
  object-position: 68% 50%;
  border-top: 1px solid #f1d3d3;
  border-left: 0;
}

.guided-audit-flow.has-result .finding-severity {
  color: #b52e2e;
  background: #ffe7e7;
  border-color: #ffb1b1;
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow.has-result .finding-card h3,
.guided-audit-flow.has-result .finding-heading.is-critical h3 {
  margin-top: 10px;
  color: var(--ink-strong);
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
  text-shadow: none;
}

.guided-audit-flow.has-result .finding-id-block {
  margin: 0;
  padding: 11px 16px;
  border: 0;
  border-top: 1px solid #f1d3d3;
  border-bottom: 1px solid #f1d3d3;
  border-radius: 0;
  background: #fffafa;
}

.guided-audit-flow.has-result .finding-id-block span {
  color: #9f3030;
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow.has-result .finding-id-block code {
  color: #173f78;
  font-size: var(--type-code-size, 13px);
}

.guided-audit-flow.has-result .finding-card > p {
  margin: 0;
  padding: 14px 16px 0;
  color: var(--ink-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-audit-flow.has-result .finding-facts {
  margin: 13px 16px 0;
  gap: 8px;
}

.guided-audit-flow.has-result .finding-facts > div {
  padding: 10px 11px;
  background: #fbfcfe;
  border-color: var(--line);
  border-radius: 6px;
}

.guided-audit-flow.has-result .finding-facts dt {
  color: var(--ink-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.guided-audit-flow.has-result .finding-facts dd {
  color: var(--ink);
  font-size: var(--type-body-small-size, 13px);
}

.guided-audit-flow.has-result .finding-evidence-details {
  margin: 14px 16px 16px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.guided-audit-flow.has-result .finding-evidence-details summary {
  color: var(--action-blue-strong);
  font-family: var(--font-ui);
  font-size: max(14px, var(--type-body-small-size, 14px));
  font-weight: 600;
}

.guided-audit-flow.has-result .finding-original-details {
  margin: 0 16px 16px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.guided-audit-flow.has-result .finding-original-details summary {
  color: var(--ink-muted);
  cursor: pointer;
  font-family: var(--font-ui);
  font-size: max(14px, var(--type-body-small-size, 14px));
  font-weight: 600;
}

.guided-audit-flow.has-result .finding-original-details p {
  margin-top: 9px;
  padding: 10px 11px;
  color: var(--ink-muted);
  background: #f8fafc;
  border: 1px solid var(--line);
  border-radius: 6px;
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
  overflow-wrap: anywhere;
}

.guided-audit-flow.has-result .guided-runtime-details,
.guided-audit-flow.has-result .guided-trace-details {
  border-color: var(--line);
  border-radius: 7px;
  background: #fbfcfe;
  box-shadow: none;
}

.guided-audit-flow.has-result .guided-runtime-details > summary,
.guided-audit-flow.has-result .guided-trace-details > summary {
  color: var(--action-blue-strong);
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 13px);
}

@media (max-width: 900px) {
  .guided-result-context {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .guided-result-context-item:nth-child(2)::after {
    display: none;
  }

  .guided-result-context-item:nth-child(-n + 2) {
    border-bottom: 1px solid var(--line);
  }

  .guided-audit-flow.has-result .chain-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .guided-audit-flow .guided-hero.is-result {
    align-items: stretch;
    flex-direction: column;
    gap: 18px;
    padding: 18px;
  }

  .guided-result-actions {
    align-items: stretch;
    flex-direction: row;
    justify-content: space-between;
  }

  .guided-result-actions .guided-start {
    width: auto;
  }

  .guided-audit-flow.has-result .chain-list {
    grid-template-columns: 1fr;
    grid-template-rows: none;
    gap: var(--space-6);
  }

  .guided-audit-flow .chain-node:not(:last-child)::after,
  .guided-audit-flow .chain-preview-node:not(:last-child)::after {
    top: auto;
    right: auto;
    bottom: -20px;
    left: 50%;
    content: "↓";
    transform: translateX(-50%);
  }

  .guided-audit-flow.has-result .chain-node {
    min-height: 178px;
  }

  .guided-audit-flow.has-result .finding-heading.is-critical {
    grid-template-columns: 1fr;
  }

  .guided-audit-flow.has-result .finding-evidence-focus {
    height: 180px;
    min-height: 180px;
    max-height: 180px;
    border-top: 1px solid #f1d3d3;
    border-left: 0;
  }
}

@media (max-width: 480px) {
  .guided-result-context {
    grid-template-columns: 1fr;
  }

  .guided-result-context-item,
  .guided-result-context-item:nth-child(-n + 2) {
    border-bottom: 1px solid var(--line);
  }

  .guided-result-context-item:last-child {
    border-bottom: 0;
  }

  .guided-result-context-item:not(:last-child)::after,
  .guided-result-context-item:nth-child(2)::after {
    display: none;
  }

  .guided-result-actions {
    align-items: center;
  }

  .guided-result-actions .guided-start {
    flex: 1;
  }

  .guided-audit-flow.has-result .chain-flow-strip {
    height: auto;
  }

  .guided-audit-flow.has-result .chain-list {
    padding: 0;
  }

  .guided-audit-flow.has-result .chain-evidence-panel {
    margin: var(--space-4) 0 0;
    padding: var(--space-4);
  }

  .guided-audit-flow.has-result .finding-heading-content {
    min-height: 0;
    padding: var(--space-4);
  }

  .guided-audit-flow.has-result .finding-card h3,
  .guided-audit-flow.has-result .finding-heading.is-critical h3 {
    font-size: var(--type-card-title-size, 18px);
  }

  .guided-audit-flow.has-result .finding-id-block {
    align-items: flex-start;
    flex-direction: column;
    gap: 5px;
  }

  .guided-audit-flow.has-result .finding-id-block code {
    text-align: left;
  }
}

@media (prefers-reduced-motion: reduce) {
  .guided-audit-flow .chain-flow-backdrop {
    transition: none;
  }
}

/* F-063 visual pass 2: keep business copy readable at the narrowest viewport;
 * technical values remain secondary but large enough to wrap and copy. */
.guided-audit-flow.has-result .guided-result-boundary,
.guided-audit-flow.has-result .guided-result-context-item small {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-audit-flow.has-result .chain-story,
.guided-audit-flow.has-result .finding-card > p {
  font-size: max(16px, var(--type-body-size, 16px));
  line-height: var(--type-body-leading, 1.62);
}

.guided-audit-flow.has-result .chain-node-caption,
.guided-audit-flow.has-result .chain-node-description,
.guided-audit-flow.has-result .chain-preview-caption,
.guided-audit-flow.has-result .chain-event-details p,
.guided-audit-flow.has-result .finding-evidence-details p,
.guided-audit-flow.has-result .finding-original-details p {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.guided-audit-flow.has-result .chain-event-title {
  font-size: max(16px, var(--type-body-size, 16px));
  line-height: var(--type-body-leading, 1.62);
}

.guided-audit-flow.has-result .chain-facts code,
.guided-audit-flow.has-result .chain-evidence-panel code,
.guided-audit-flow.has-result .finding-facts code,
.guided-audit-flow.has-result .finding-id-block code {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}

/* F-063 visual pass 3: disclosures are controls, not incidental inline text.
 * Keep the business layer quiet while making every technical layer easy to
 * discover, focus, and operate with a keyboard or touch input. */
.guided-audit-flow .guided-runtime-details > summary,
.guided-audit-flow .guided-trace-details > summary,
.guided-audit-flow .chain-event-details > summary,
.guided-audit-flow .chain-event-json > summary,
.guided-audit-flow .finding-evidence-details > summary,
.guided-audit-flow .finding-original-details > summary,
.guided-audit-flow .trace-event-json > summary {
  box-sizing: border-box;
  min-height: 44px;
  margin: 0;
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

.guided-audit-flow .guided-runtime-details > summary::-webkit-details-marker,
.guided-audit-flow .guided-trace-details > summary::-webkit-details-marker,
.guided-audit-flow .chain-event-details > summary::-webkit-details-marker,
.guided-audit-flow .chain-event-json > summary::-webkit-details-marker,
.guided-audit-flow .finding-evidence-details > summary::-webkit-details-marker,
.guided-audit-flow .finding-original-details > summary::-webkit-details-marker,
.guided-audit-flow .trace-event-json > summary::-webkit-details-marker {
  display: none;
}

.guided-audit-flow .guided-runtime-details > summary::before,
.guided-audit-flow .guided-trace-details > summary::before,
.guided-audit-flow .chain-event-details > summary::before,
.guided-audit-flow .chain-event-json > summary::before,
.guided-audit-flow .finding-evidence-details > summary::before,
.guided-audit-flow .finding-original-details > summary::before,
.guided-audit-flow .trace-event-json > summary::before {
  position: absolute;
  left: 12px;
  width: 14px;
  height: 14px;
  background: var(--disclosure-chevron) center / 14px 14px no-repeat;
  content: "";
  transition: transform 160ms ease;
}

.guided-audit-flow .guided-runtime-details > summary,
.guided-audit-flow .guided-trace-details > summary,
.guided-audit-flow .chain-event-details > summary,
.guided-audit-flow .chain-event-json > summary,
.guided-audit-flow .finding-evidence-details > summary,
.guided-audit-flow .finding-original-details > summary,
.guided-audit-flow .trace-event-json > summary {
  position: relative;
}

.guided-audit-flow .guided-runtime-details[open] > summary::before,
.guided-audit-flow .guided-trace-details[open] > summary::before,
.guided-audit-flow .chain-event-details[open] > summary::before,
.guided-audit-flow .chain-event-json[open] > summary::before,
.guided-audit-flow .finding-evidence-details[open] > summary::before,
.guided-audit-flow .finding-original-details[open] > summary::before,
.guided-audit-flow .trace-event-json[open] > summary::before {
  transform: rotate(90deg);
}

.guided-audit-flow .guided-runtime-details > summary:hover,
.guided-audit-flow .guided-trace-details > summary:hover,
.guided-audit-flow .chain-event-details > summary:hover,
.guided-audit-flow .chain-event-json > summary:hover,
.guided-audit-flow .finding-evidence-details > summary:hover,
.guided-audit-flow .finding-original-details > summary:hover,
.guided-audit-flow .trace-event-json > summary:hover {
  background: var(--surface-raised);
}

.guided-audit-flow .guided-runtime-details > summary:focus-visible,
.guided-audit-flow .guided-trace-details > summary:focus-visible,
.guided-audit-flow .chain-event-details > summary:focus-visible,
.guided-audit-flow .chain-event-json > summary:focus-visible,
.guided-audit-flow .finding-evidence-details > summary:focus-visible,
.guided-audit-flow .finding-original-details > summary:focus-visible,
.guided-audit-flow .trace-event-json > summary:focus-visible,
.guided-audit-flow .chain-evidence-toggle:focus-visible,
.guided-audit-flow .chain-evidence-panel-heading button:focus-visible {
  outline: 2px solid var(--action-blue-strong);
  outline-offset: 2px;
}

.guided-audit-flow .chain-evidence-toggle {
  width: 100%;
  min-height: 44px;
  padding: 10px 8px 0;
  border-top: 1px solid var(--line);
  font-size: max(14px, var(--type-body-small-size, 14px));
}

.guided-audit-flow .plan-facts dd,
.guided-audit-flow .plan-facts code,
.guided-audit-flow .chain-facts code,
.guided-audit-flow .chain-evidence-panel code,
.guided-audit-flow .finding-facts dd,
.guided-audit-flow .finding-facts code,
.guided-audit-flow .finding-id-block code,
.guided-audit-flow .runtime-facts code,
.guided-audit-flow .trace-facts code {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.guided-audit-flow .chain-event-details pre,
.guided-audit-flow .chain-event-json pre,
.guided-audit-flow .trace-event-json pre {
  max-width: 100%;
  overflow-x: auto;
  overflow-wrap: anywhere;
  font-family: var(--font-code, "Cascadia Mono", Consolas, monospace);
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
  white-space: pre-wrap;
}
</style>
