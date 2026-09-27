<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import ProviderReadinessView from "./ProviderReadinessView.vue";
import UserProblemCard, { type UserProblem } from "./UserProblemCard.vue";
import { apiFetch } from "../api";
import readinessBlockedUrl from "../assets/illustrations/provider-readiness-blocked.webp";
import readinessConnectedUrl from "../assets/illustrations/provider-readiness-connected.webp";
import {
  deleteProviderSecret,
  isDesktopRuntime,
  storeProviderSecret,
} from "../native";
import type {
  AuditRuntimeSnapshot,
  AgentAuditAdapterManifest,
  OllamaDiscoveryResult,
  OllamaModelCandidate,
  ProviderCapabilityManifest,
  ProviderAuthMode,
  ProviderCandidateReadinessRequest,
  ProviderConnectionSettings,
  ProviderConnectionKind,
  ProviderInspectionRequest,
  ProviderModelCandidate,
  ProviderReadinessResult,
  ProtocolInspectionResult,
  ProviderSetupState,
  SaveProviderSettingsRequest,
} from "@agent-audit/contracts";

type ConnectionMode = "discover" | "manual";
type ProviderProblemAction = "reload" | "discover" | "inspect" | "readiness" | "save" | "edit";
type ProviderProblem = UserProblem & { action: ProviderProblemAction };

class ProviderResponseError extends Error {
  readonly status: number;
  readonly operationId: string | null;

  constructor(status: number, detail: string, operationId: string | null) {
    super(detail || `请求失败（${status}）`);
    this.name = "ProviderResponseError";
    this.status = status;
    this.operationId = operationId;
  }
}

const LOCAL_OLLAMA_ENDPOINT = "http://127.0.0.1:11434";
const AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION = "agent_audit_adapter.v1";

const ENTERPRISE_PROTOCOLS: Exclude<ProviderConnectionKind, "ollama">[] = [
  "openai_compatible",
  "anthropic_compatible",
  "agent_audit_adapter",
];

const AUTH_MODES_BY_PROTOCOL: Record<
  Exclude<ProviderConnectionKind, "ollama">,
  ProviderAuthMode[]
> = {
  openai_compatible: ["none", "bearer"],
  anthropic_compatible: ["none", "x_api_key", "bearer"],
  agent_audit_adapter: ["none", "bearer", "x_api_key"],
};

const emit = defineEmits<{
  (event: "saved", state: ProviderSetupState): void;
}>();

const setupState = ref<ProviderSetupState | null>(null);
const setupLoading = ref(false);
const setupError = ref("");
const editing = ref(true);

const connectionMode = ref<ConnectionMode>("discover");
const manualBaseUrl = ref("");
const manualModel = ref("");
const selectedModel = ref("");
const manualProtocol = ref<Exclude<ProviderConnectionKind, "ollama">>(
  "openai_compatible",
);
const manualAuthMode = ref<ProviderAuthMode>("none");
const manualSecret = ref("");

const discoveryResult = ref<OllamaDiscoveryResult | null>(null);
const discoveryLoading = ref(false);
const discoveryError = ref("");

const inspectionResult = ref<ProtocolInspectionResult | null>(null);
const inspectionLoading = ref(false);
const inspectionError = ref("");
const inspectionAttempted = ref(false);
const inspectionWriteback = ref(false);

const readinessResult = ref<ProviderReadinessResult | null>(null);
const readinessLoading = ref(false);
const readinessError = ref("");
const readinessStale = ref(false);

const saving = ref(false);
const saveError = ref("");

const configured = computed(() => setupState.value?.configured === true);
const configuredCredentialMissing = computed(
  () =>
    configured.value &&
    setupState.value?.settings?.authMode !== undefined &&
    setupState.value?.settings?.authMode !== "none" &&
    setupState.value.credentialConfigured !== true,
);
const draftBaseUrl = computed(() =>
  connectionMode.value === "discover"
    ? LOCAL_OLLAMA_ENDPOINT
    : manualBaseUrl.value.trim(),
);
const draftModel = computed(() =>
  connectionMode.value === "discover" ? selectedModel.value.trim() : manualModel.value.trim(),
);
const draftSettings = computed<ProviderConnectionSettings>(() => ({
  kind: connectionMode.value === "discover" ? "ollama" : manualProtocol.value,
  baseUrl: draftBaseUrl.value,
  model: draftModel.value,
  authMode: connectionMode.value === "discover" ? "none" : manualAuthMode.value,
}));
const enterpriseAuthModes = computed(() => AUTH_MODES_BY_PROTOCOL[manualProtocol.value]);
const credentialRequired = computed(() => draftSettings.value.authMode !== "none");
const credentialLabel = computed(() =>
  draftSettings.value.authMode === "x_api_key" ? "x-api-key" : "Bearer API Key",
);
const credentialPlaceholder = "输入后仅用于本次检查和桌面端系统凭据存储";
const settingsComplete = computed(
  () => Boolean(draftSettings.value.baseUrl) && Boolean(draftSettings.value.model),
);
const readinessReady = computed(() => readinessResult.value?.status === "ready");
const readinessVisualState = computed<"blocked" | "connected">(() =>
  readinessReady.value && !readinessStale.value ? "connected" : "blocked",
);
const readinessVisualUrl = computed(() =>
  readinessVisualState.value === "connected" ? readinessConnectedUrl : readinessBlockedUrl,
);
const readinessVisualLabel = computed(() => {
  if (readinessLoading.value) {
    return "正在检查候选模型链路";
  }
  if (readinessVisualState.value === "connected") {
    return "候选模型链路已通过四项 Readiness";
  }
  if (readinessStale.value) {
    return "连接信息已变化，等待重新检查";
  }
  if (readinessError.value || readinessResult.value) {
    return "候选模型链路尚未通过 Readiness";
  }
  return "候选模型链路尚未验证";
});
const readinessVisualCaption = computed(() => {
  if (readinessLoading.value) {
    return "正在运行四项能力检查…";
  }
  if (readinessVisualState.value === "connected") {
    return "目标连接、工具调用、攻击连接和严格 JSON 均已通过。";
  }
  if (readinessStale.value) {
    return "草稿已变化，请以新地址和模型重新检查。";
  }
  if (readinessError.value || readinessResult.value) {
    return "链路尚未就绪，具体原因以下方探针与错误为准。";
  }
  return "尚未检查，不代表 Provider 已发生故障。";
});
const enterpriseInspectionComplete = computed(
  () => connectionMode.value === "discover" || inspectionAttempted.value,
);
const sameSavedConnection = computed(() => {
  const saved = setupState.value?.settings;
  if (!saved) {
    return false;
  }
  return (
    saved.kind === draftSettings.value.kind &&
    saved.baseUrl === draftSettings.value.baseUrl &&
    (saved.authMode || "none") === draftSettings.value.authMode
  );
});
const secretAvailableForSave = computed(
  () =>
    Boolean(manualSecret.value.trim()) ||
    (sameSavedConnection.value && setupState.value?.credentialConfigured === true),
);

const protocolLabel = (protocol: ProtocolInspectionResult["protocol"]): string => {
  if (protocol === "ollama") {
    return "Ollama";
  }
  if (protocol === "openai_compatible") {
    return "OpenAI-compatible";
  }
  if (protocol === "anthropic_compatible") {
    return "Anthropic / Claude Gateway";
  }
  if (protocol === "agent_audit_adapter") {
    return "企业适配器（agent_audit_adapter v1）";
  }
  return "未确认";
};

const authModeLabel = (authMode: ProviderAuthMode): string => {
  if (authMode === "x_api_key") {
    return "x-api-key";
  }
  if (authMode === "bearer") {
    return "Bearer API Key";
  }
  return "无认证";
};

const enterpriseProtocolHint = computed(() => {
  if (manualProtocol.value === "anthropic_compatible") {
    return "Anthropic Messages API；适用于 Claude Gateway。模型可手填。";
  }
  if (manualProtocol.value === "agent_audit_adapter") {
    return "企业受控桥接协议；仅接受版本化 manifest，不执行自定义转换代码。";
  }
  return "适用于 OpenAI-compatible Chat Completions 企业服务。";
});
const enterpriseInspectionHint = computed(() => {
  if (manualProtocol.value === "anthropic_compatible") {
    return "只访问你填写的一个地址，按 Anthropic Messages API 检查，不探测其他地址。";
  }
  if (manualProtocol.value === "agent_audit_adapter") {
    return "只访问你填写的一个地址，检查 /v1/manifest 与模型能力，不探测其他地址。";
  }
  return "只访问你填写的一个地址，按 OpenAI-compatible /v1/models 检查，不探测其他地址。";
});
const inspectionCapabilities = computed<ProviderCapabilityManifest | null>(() => {
  const result = inspectionResult.value;
  return result?.capabilities ?? result?.manifest?.capabilities ?? null;
});
const inspectionProtocolVersion = computed(
  () => inspectionResult.value?.protocolVersion ?? inspectionResult.value?.manifest?.protocolVersion ?? null,
);

const settingsProtocolLabel = (settings: ProviderConnectionSettings | null): string =>
  settings ? protocolLabel(settings.kind) : "未确认";

const compactCredentialLabel = computed(() => {
  const settings = setupState.value?.settings;
  if (!settings || settings.authMode === "none") {
    return "无需凭据";
  }
  return setupState.value?.credentialConfigured === true
    ? `${settings.authMode === "x_api_key" ? "x-api-key" : "Bearer API Key"}（已配置）`
    : `需要补充 ${settings.authMode === "x_api_key" ? "x-api-key" : "API Key"} · 连接未就绪`;
});

const readinessStatusError = computed(() => {
  if (!readinessResult.value) {
    return "";
  }

  if (readinessResult.value.status === "partial") {
    return "Readiness 结果为 PARTIAL（部分兼容），当前设置不会保存。请调整地址或模型后重新检查。";
  }

  if (readinessResult.value.status === "unavailable") {
    return "Readiness 结果为 UNAVAILABLE（不可用），当前设置不会保存。请确认地址、模型和认证信息后重新检查。";
  }

  return "";
});

const discoveryStatusError = computed(() => {
  if (!discoveryResult.value || discoveryResult.value.status !== "unavailable") {
    return "";
  }

  return (
    discoveryResult.value.diagnostic?.trim() ||
    "本机 Ollama 当前不可用，请确认固定地址 127.0.0.1:11434 上的服务已启动。"
  );
});

const discoveryNoModels = computed(
  () =>
    discoveryResult.value?.status === "available" &&
    discoveryResult.value.models.length === 0,
);

const inspectionStatusError = computed(() => {
  if (!inspectionResult.value || inspectionResult.value.status !== "unavailable") {
    return "";
  }

  return (
    inspectionResult.value.diagnostic?.trim() ||
    "企业地址当前不可用，请确认你填写的地址和认证信息。"
  );
});

function providerTechnicalDetails(error: unknown, fallback: string): string {
  if (error instanceof ProviderResponseError) {
    const operation = error.operationId ? `\noperation ID: ${error.operationId}` : "";
    return `HTTP ${error.status}${operation}\n${error.message}`;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function providerRequestProblem(
  stage: string,
  title: string,
  reason: string,
  impact: string,
  actionLabel: string,
  action: ProviderProblemAction,
  error: unknown,
  tone: UserProblem["tone"] = "danger",
): ProviderProblem {
  return {
    stage,
    title,
    reason,
    impact,
    actionLabel,
    action,
    tone,
    technicalDetails: providerTechnicalDetails(error, reason),
  };
}

const providerProblem = computed<ProviderProblem | null>(() => {
  if (setupError.value) {
    return providerRequestProblem(
      "读取连接状态",
      "暂时无法读取连接状态",
      setupError.value,
      "当前不能确认 AI 是否可以使用；已有资料和验收记录不受影响。",
      "重新读取",
      "reload",
      setupError.value,
    );
  }

  if (configuredCredentialMissing.value) {
    return providerRequestProblem(
      "连接状态",
      "需要补充连接凭据",
      "已保存的企业连接需要 API Key 才能继续检查。",
      "模型能力检查和后续安全验收暂时不能开始。",
      "补充凭据",
      "edit",
      "saved connection requires a credential",
      "warning",
    );
  }

  if (discoveryError.value) {
    return providerRequestProblem(
      "查找本机模型",
      "本机模型查找没有完成",
      discoveryError.value,
      "还不能选择模型或开始安全验收。",
      "重新检测",
      "discover",
      discoveryError.value,
    );
  }

  if (discoveryStatusError.value) {
    return providerRequestProblem(
      "查找本机模型",
      "本机模型服务没有响应",
      discoveryStatusError.value,
      "还不能选择模型或开始安全验收。",
      "重新检测",
      "discover",
      discoveryStatusError.value,
    );
  }

  if (discoveryNoModels.value) {
    return providerRequestProblem(
      "查找本机模型",
      "本机服务已响应，但没有可选择的模型",
      "本机服务返回了 0 个已安装模型。",
      "还不能进行模型能力检查或安全验收。",
      "重新检测",
      "discover",
      "endpoint: http://127.0.0.1:11434\nmodels: 0",
      "warning",
    );
  }

  if (inspectionError.value) {
    return providerRequestProblem(
      "检查企业地址",
      "企业 AI 地址检查没有完成",
      inspectionError.value,
      "还不能确认地址和模型是否适合本次安全验收。",
      "重新检查",
      "inspect",
      inspectionError.value,
    );
  }

  if (inspectionStatusError.value) {
    return providerRequestProblem(
      "检查企业地址",
      "企业 AI 地址暂时不可用",
      inspectionStatusError.value,
      "还不能选择模型或检查模型能力。",
      "重新检查",
      "inspect",
      inspectionStatusError.value,
    );
  }

  if (readinessError.value) {
    return providerRequestProblem(
      "检查模型能力",
      "模型能力检查没有完成",
      readinessError.value,
      "连接不会被确认，安全验收暂时不能开始。",
      "重新检查",
      "readiness",
      readinessError.value,
    );
  }

  if (readinessStatusError.value) {
    return providerRequestProblem(
      "检查模型能力",
      readinessResult.value?.status === "partial" ? "模型能力仍有缺口" : "模型暂时不可用",
      readinessStatusError.value,
      "连接不会被保存，安全验收暂时不能开始。",
      "重新检查",
      "readiness",
      readinessStatusError.value,
      readinessResult.value?.status === "partial" ? "warning" : "danger",
    );
  }

  if (saveError.value) {
    return providerRequestProblem(
      "确认连接",
      "连接还没有保存",
      saveError.value,
      "本次连接不会成为后续安全验收使用的连接。",
      "重新确认",
      "save",
      saveError.value,
    );
  }

  return null;
});

const statusCaption = computed(() => {
  if (setupLoading.value) {
    return "正在读取连接状态…";
  }
  if (configured.value && setupState.value?.settings) {
    const credentialCaption = configuredCredentialMissing.value
      ? " · 需要重新输入 API Key"
      : "";
    return `${settingsProtocolLabel(setupState.value.settings)} · ${setupState.value.settings.model}${credentialCaption}`;
  }
  return "自动只查本机 Ollama；企业连接只访问你明确填写的地址。";
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isRuntimeSnapshot(value: unknown): value is AuditRuntimeSnapshot {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.provider === "string" &&
    (value.model === null || typeof value.model === "string") &&
    (value.retrieverEngine === "embedding" || value.retrieverEngine === "tfidf") &&
    (value.retrieverModel === null || typeof value.retrieverModel === "string") &&
    (value.retrieverDimensions === null || typeof value.retrieverDimensions === "number") &&
    typeof value.indexedDocumentCount === "number" &&
    Number.isInteger(value.indexedDocumentCount) &&
    value.indexedDocumentCount >= 0
  );
}

function parseSettings(value: unknown): ProviderConnectionSettings {
  if (
    !isRecord(value) ||
    (value.kind !== "ollama" &&
      value.kind !== "openai_compatible" &&
      value.kind !== "anthropic_compatible" &&
      value.kind !== "agent_audit_adapter") ||
    typeof value.baseUrl !== "string" ||
    typeof value.model !== "string"
  ) {
    throw new Error("Provider 设置响应格式无效");
  }

  const authMode = value.authMode === undefined ? "none" : value.authMode;
  if (authMode !== "none" && authMode !== "bearer" && authMode !== "x_api_key") {
    throw new Error("Provider 设置认证模式无效");
  }

  return {
    kind: value.kind,
    baseUrl: value.baseUrl,
    model: value.model,
    authMode,
  };
}

function parseSetupState(value: unknown): ProviderSetupState {
  if (
    !isRecord(value) ||
    typeof value.configured !== "boolean" ||
    !(value.credentialConfigured === undefined || typeof value.credentialConfigured === "boolean")
  ) {
    throw new Error("Provider Setup 响应格式无效");
  }

  const settings = value.settings === null ? null : parseSettings(value.settings);
  if (!isRuntimeSnapshot(value.runtimeSnapshot)) {
    throw new Error("Provider Setup 响应缺少 Runtime 摘要");
  }

  return {
    configured: value.configured,
    settings,
    credentialConfigured: value.credentialConfigured === true,
    runtimeSnapshot: value.runtimeSnapshot,
  };
}

function parseDiscoveryResult(value: unknown): OllamaDiscoveryResult {
  if (
    !isRecord(value) ||
    typeof value.endpoint !== "string" ||
    (value.status !== "available" && value.status !== "unavailable") ||
    !Array.isArray(value.models)
  ) {
    throw new Error("Ollama 发现响应格式无效");
  }
  if (value.endpoint.replace(/\/+$/, "") !== LOCAL_OLLAMA_ENDPOINT) {
    throw new Error("本机 Ollama 发现响应不是固定 loopback 地址");
  }

  const models: OllamaModelCandidate[] = value.models.map((model) => {
    if (!isRecord(model) || typeof model.name !== "string") {
      throw new Error("Ollama 模型列表响应格式无效");
    }

    if (
      !(model.sizeBytes === null || typeof model.sizeBytes === "number") ||
      !(model.modifiedAt === null || typeof model.modifiedAt === "string")
    ) {
      throw new Error("Ollama 模型信息响应格式无效");
    }

    return {
      name: model.name,
      sizeBytes: model.sizeBytes,
      modifiedAt: model.modifiedAt,
    };
  });

  if (!(value.diagnostic === null || typeof value.diagnostic === "string")) {
    throw new Error("Ollama 诊断信息响应格式无效");
  }

  return {
    endpoint: value.endpoint,
    status: value.status,
    models,
    diagnostic: value.diagnostic,
  };
}

function parseInspectionResult(value: unknown): ProtocolInspectionResult {
  if (
    !isRecord(value) ||
    (value.status !== "available" && value.status !== "unavailable") ||
    !(
      value.protocol === null ||
      value.protocol === "ollama" ||
      value.protocol === "openai_compatible" ||
      value.protocol === "anthropic_compatible" ||
      value.protocol === "agent_audit_adapter"
    ) ||
    typeof value.baseUrl !== "string" ||
    !Array.isArray(value.models) ||
    !(value.diagnostic === null || typeof value.diagnostic === "string") ||
    typeof value.modelsEnumerated !== "boolean" ||
    !isOptionalAdapterProtocolVersion(value.protocolVersion) ||
    !isOptionalCapabilityPayload(value.capabilities) ||
    !isOptionalAdapterManifestPayload(value.manifest)
  ) {
    throw new Error("企业地址检查响应格式无效");
  }

  const models: ProviderModelCandidate[] = value.models.map((model) => {
    if (
      !isRecord(model) ||
      typeof model.id !== "string" ||
      !(model.object === null || model.object === "model") ||
      !(model.created === null || (typeof model.created === "number" && Number.isInteger(model.created))) ||
      !(model.ownedBy === null || typeof model.ownedBy === "string")
    ) {
      throw new Error("企业模型列表响应格式无效");
    }

    return {
      id: model.id,
      object: model.object,
      created: model.created,
      ownedBy: model.ownedBy,
    };
  });

  const protocolVersion = value.protocolVersion === undefined ? null : value.protocolVersion;
  const manifest = normalizeAdapterManifest(value.manifest);
  const capabilities = normalizeCapabilityManifest(value.capabilities);

  if (value.protocol === "agent_audit_adapter" && value.status === "available") {
    if (
      protocolVersion !== AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION ||
      manifest === null ||
      capabilities === null ||
      !capabilityFlagsEqual(capabilities, manifest.capabilities)
    ) {
      throw new Error("企业适配器可用检查响应缺少一致的 v1 manifest");
    }
  } else if (
    value.protocol !== "agent_audit_adapter" &&
    (protocolVersion !== null || capabilities !== null || manifest !== null)
  ) {
    throw new Error("非适配器检查响应不得携带适配器 manifest");
  }

  return {
    status: value.status,
    protocol: value.protocol,
    baseUrl: value.baseUrl,
    models,
    diagnostic: value.diagnostic,
    modelsEnumerated: value.modelsEnumerated,
    protocolVersion,
    capabilities,
    manifest,
  };
}

function isOptionalAdapterProtocolVersion(
  value: unknown,
): value is "agent_audit_adapter.v1" | null | undefined {
  return value === undefined || value === null || value === AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION;
}

function isCapabilityFlags(
  value: unknown,
): value is ProviderCapabilityManifest {
  return (
    isRecord(value) &&
    typeof value.text === "boolean" &&
    typeof value.toolCalling === "boolean" &&
    typeof value.structuredOutput === "boolean" &&
    typeof value.usage === "boolean"
  );
}

function isOptionalCapabilityPayload(
  value: unknown,
): boolean {
  return (
    value === undefined ||
    value === null ||
    isCapabilityFlags(value)
  );
}

function isOptionalAdapterManifestPayload(
  value: unknown,
): boolean {
  return (
    value === undefined ||
    value === null ||
    (isRecord(value) &&
      value.protocol === "agent_audit_adapter" &&
      value.protocolVersion === AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION &&
      isCapabilityFlags(value.capabilities))
  );
}

function normalizeCapabilityManifest(
  value: unknown,
): ProviderCapabilityManifest | null {
  return isCapabilityFlags(value) ? value : null;
}

function capabilityFlagsEqual(
  left: ProviderCapabilityManifest,
  right: ProviderCapabilityManifest,
): boolean {
  return (
    left.text === right.text &&
    left.toolCalling === right.toolCalling &&
    left.structuredOutput === right.structuredOutput &&
    left.usage === right.usage
  );
}

function normalizeAdapterManifest(value: unknown): AgentAuditAdapterManifest | null {
  if (!isRecord(value) || value.protocol !== "agent_audit_adapter") {
    return null;
  }
  if (value.protocolVersion !== AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION) {
    return null;
  }
  if (!isCapabilityFlags(value.capabilities)) {
    return null;
  }
  return {
    protocol: "agent_audit_adapter",
    protocolVersion: AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION,
    capabilities: value.capabilities,
  };
}

function parseReadinessResult(value: unknown): ProviderReadinessResult {
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    typeof value.checkedAt !== "string" ||
    (value.status !== "ready" && value.status !== "partial" && value.status !== "unavailable") ||
    !isRecord(value.targetProvider) ||
    !isRecord(value.attackProvider) ||
    !Array.isArray(value.planCompatibility)
  ) {
    throw new Error("Provider Readiness 响应格式无效");
  }

  return value as unknown as ProviderReadinessResult;
}

async function responseError(response: Response): Promise<ProviderResponseError> {
  let detail = "";
  try {
    const payload: unknown = await response.json();
    if (isRecord(payload) && typeof payload.detail === "string") {
      detail = payload.detail;
    } else if (isRecord(payload) && payload.detail !== undefined) {
      detail = JSON.stringify(payload.detail);
    }
  } catch {
    // The status remains the useful boundary error when the body is not JSON.
  }

  return new ProviderResponseError(
    response.status,
    detail,
    response.headers.get("X-AgentAudit-Operation-Id"),
  );
}

function markReadinessStale(): void {
  if (readinessResult.value) {
    readinessResult.value = null;
    readinessStale.value = true;
    readinessError.value = "";
  }
}

function clearTransientSecret(): void {
  manualSecret.value = "";
}

function resetDraftToSavedSettings(): void {
  discoveryResult.value = null;
  discoveryError.value = "";
  selectedModel.value = "";
  inspectionResult.value = null;
  inspectionError.value = "";
  inspectionAttempted.value = false;
  readinessResult.value = null;
  readinessError.value = "";
  readinessStale.value = false;
  saveError.value = "";
  clearTransientSecret();

  const settings = setupState.value?.settings;
  if (settings) {
    manualBaseUrl.value = settings.baseUrl;
    manualModel.value = settings.model;
    manualAuthMode.value = settings.authMode || "none";
    connectionMode.value = settings.kind === "ollama" ? "discover" : "manual";
    if (settings.kind !== "ollama") {
      manualProtocol.value = settings.kind;
      ensureAuthModeForProtocol(settings.kind);
    }
    return;
  }

  manualBaseUrl.value = "";
  manualModel.value = "";
  manualProtocol.value = "openai_compatible";
  manualAuthMode.value = "none";
  connectionMode.value = "discover";
}

function beginEditing(): void {
  if (editing.value) {
    return;
  }

  resetDraftToSavedSettings();
  editing.value = true;
}

function cancelEditing(): void {
  if (
    !configured.value ||
    saving.value ||
    discoveryLoading.value ||
    inspectionLoading.value ||
    readinessLoading.value
  ) {
    return;
  }

  resetDraftToSavedSettings();
  editing.value = false;
}

function selectMode(mode: ConnectionMode): void {
  if (connectionMode.value === mode) {
    return;
  }

  connectionMode.value = mode;
  discoveryResult.value = null;
  discoveryError.value = "";
  selectedModel.value = "";
  inspectionResult.value = null;
  inspectionError.value = "";
  inspectionAttempted.value = false;
  if (mode === "discover") {
    clearTransientSecret();
  }
  markReadinessStale();
}

function defaultAuthModeForProtocol(
  protocol: Exclude<ProviderConnectionKind, "ollama">,
): ProviderAuthMode {
  return protocol === "anthropic_compatible" ? "x_api_key" : "none";
}

function ensureAuthModeForProtocol(
  protocol: Exclude<ProviderConnectionKind, "ollama">,
): void {
  const allowed = AUTH_MODES_BY_PROTOCOL[protocol];
  if (!allowed.includes(manualAuthMode.value)) {
    manualAuthMode.value = defaultAuthModeForProtocol(protocol);
  }
}

function selectProtocol(
  protocol: Exclude<ProviderConnectionKind, "ollama">,
): void {
  manualProtocol.value = protocol;
  manualAuthMode.value = defaultAuthModeForProtocol(protocol);
  manualModel.value = "";
  inspectionResult.value = null;
  inspectionError.value = "";
  inspectionAttempted.value = false;
  clearTransientSecret();
  markReadinessStale();
}

async function loadSetup(): Promise<void> {
  setupLoading.value = true;
  setupError.value = "";

  try {
    const response = await apiFetch("/api/provider-setup");
    if (!response.ok) {
      throw await responseError(response);
    }

    const state = parseSetupState(await response.json());
    setupState.value = state;
    if (state.settings) {
      manualBaseUrl.value = state.settings.baseUrl;
      manualModel.value = state.settings.model;
      manualAuthMode.value = state.settings.authMode || "none";
      connectionMode.value = state.settings.kind === "ollama" ? "discover" : "manual";
      if (state.settings.kind !== "ollama") {
        manualProtocol.value = state.settings.kind;
        ensureAuthModeForProtocol(state.settings.kind);
      }
    }
    clearTransientSecret();
    editing.value = !state.configured;
  } catch (error) {
    setupError.value = error instanceof Error ? error.message : "Provider 设置加载失败";
  } finally {
    setupLoading.value = false;
  }
}

async function discoverOllama(): Promise<void> {
  if (discoveryLoading.value || inspectionLoading.value || readinessLoading.value || saving.value) {
    return;
  }

  discoveryLoading.value = true;
  discoveryError.value = "";
  discoveryResult.value = null;
  selectedModel.value = "";
  markReadinessStale();

  try {
    const response = await apiFetch("/api/provider-discoveries/ollama", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw await responseError(response);
    }

    discoveryResult.value = parseDiscoveryResult(await response.json());
  } catch (error) {
    discoveryError.value = error instanceof Error ? error.message : "本机 Ollama 发现失败";
  } finally {
    discoveryLoading.value = false;
  }
}

async function inspectEnterprise(): Promise<void> {
  if (inspectionLoading.value || discoveryLoading.value || readinessLoading.value || saving.value) {
    return;
  }

  const baseUrl = manualBaseUrl.value.trim();
  if (!baseUrl) {
    inspectionError.value = "请先填写企业地址，再检查地址。";
    inspectionAttempted.value = true;
    return;
  }

  inspectionLoading.value = true;
  inspectionError.value = "";
  inspectionResult.value = null;
  inspectionAttempted.value = true;
  selectedModel.value = "";
  manualModel.value = "";
  markReadinessStale();

  const request: ProviderInspectionRequest = {
    kind: manualProtocol.value,
    baseUrl,
    authMode: manualAuthMode.value,
  };
  const credential = manualSecret.value;
  if (manualAuthMode.value !== "none" && credential.trim()) {
    request.credential = credential;
  }

  try {
    const response = await apiFetch("/api/provider-inspections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      throw await responseError(response);
    }

    const result = parseInspectionResult(await response.json());
    inspectionResult.value = result;
    // The service may canonicalize the explicit path (for example by adding
    // `/v1`). Keep that exact non-secret address in the draft. The sync guard
    // prevents this internal writeback from looking like a user edit and
    // invalidating the inspection we just received.
    inspectionWriteback.value = true;
    manualBaseUrl.value = result.baseUrl;
    inspectionWriteback.value = false;
  } catch (error) {
    inspectionError.value = error instanceof Error ? error.message : "企业地址检查失败";
  } finally {
    inspectionLoading.value = false;
  }
}

async function checkReadiness(): Promise<void> {
  if (readinessLoading.value || saving.value) {
    return;
  }

  if (!enterpriseInspectionComplete.value) {
    readinessError.value = "请先检查企业地址；即使模型未枚举，也要在检查后手填模型 ID。";
    return;
  }
  if (!settingsComplete.value) {
    readinessError.value = "请先选择或填写地址和模型，再检查 Readiness。";
    return;
  }

  const credential = manualSecret.value;
  if (
    credentialRequired.value &&
    !credential.trim() &&
    !secretAvailableForSave.value
  ) {
    readinessError.value = `当前连接需要 ${credentialLabel.value}；换了企业地址后请重新输入密钥再检查；协议变化也需要重新输入。`;
    return;
  }

  readinessLoading.value = true;
  readinessError.value = "";
  saveError.value = "";
  readinessResult.value = null;
  readinessStale.value = false;

  const request: ProviderCandidateReadinessRequest = {
    settings: draftSettings.value,
  };
  if (draftSettings.value.authMode === "bearer" && credential.trim()) {
    request.credential = credential;
  } else if (draftSettings.value.authMode === "x_api_key" && credential.trim()) {
    request.credential = credential;
  }

  try {
    const response = await apiFetch("/api/provider-candidates/readiness", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      throw await responseError(response);
    }

    readinessResult.value = parseReadinessResult(await response.json());
  } catch (error) {
    readinessError.value = error instanceof Error ? error.message : "Readiness 检查失败";
  } finally {
    readinessLoading.value = false;
  }
}

async function confirmProvider(): Promise<void> {
  saveError.value = "";
  if (!settingsComplete.value) {
    saveError.value = "请先选择或填写地址和模型。";
    return;
  }
  if (!enterpriseInspectionComplete.value) {
    saveError.value = "请先检查企业地址，再确认使用。";
    return;
  }
  if (!readinessResult.value || !readinessReady.value || readinessStale.value) {
    saveError.value = "请先完成一次 READY 的 Readiness 检查，再确认使用。";
    return;
  }
  if (saving.value) {
    return;
  }

  const settings = draftSettings.value;
  const credential = manualSecret.value;
  if (settings.authMode !== "none") {
    if (!isDesktopRuntime()) {
      saveError.value = `${settings.authMode === "x_api_key" ? "x-api-key" : "Bearer API Key"} 只能在桌面端保存；浏览器模式不会明文保存。`;
      return;
    }
    if (!credential.trim() && !secretAvailableForSave.value) {
      saveError.value = `请输入 ${settings.authMode === "x_api_key" ? "x-api-key" : "Bearer API Key"}；它只会保存到桌面端系统凭据存储。`;
      return;
    }
  }

  saving.value = true;
  try {
    // Store first, then send only a one-time transient value to the Sidecar so
    // its current in-memory Provider can use a newly entered key.  The API
    // persists settings only; it never returns or writes this value.
    if (settings.authMode !== "none" && credential.trim()) {
      await storeProviderSecret(credential);
    } else if (
      settings.authMode === "none" &&
      setupState.value?.settings?.authMode !== undefined &&
      setupState.value?.settings?.authMode !== "none" &&
      isDesktopRuntime()
    ) {
      await deleteProviderSecret();
    }

    const request: SaveProviderSettingsRequest = { settings };
    if (settings.authMode !== "none" && credential.trim()) {
      request.credential = credential;
    }
    const response = await apiFetch("/api/provider-setup", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      throw await responseError(response);
    }

    const state = parseSetupState(await response.json());
    setupState.value = state;
    readinessStale.value = false;
    editing.value = false;
    clearTransientSecret();
    emit("saved", state);
  } catch (error) {
    saveError.value = error instanceof Error ? error.message : "Provider 设置保存失败";
  } finally {
    saving.value = false;
  }
}

async function resolveProviderProblem(): Promise<void> {
  const problem = providerProblem.value;
  if (!problem) {
    return;
  }

  switch (problem.action) {
    case "reload":
      await loadSetup();
      return;
    case "discover":
      await discoverOllama();
      return;
    case "inspect":
      await inspectEnterprise();
      return;
    case "readiness":
      await checkReadiness();
      return;
    case "save":
      await confirmProvider();
      return;
    case "edit":
      beginEditing();
      return;
  }
}

watch(
  [
    connectionMode,
    manualProtocol,
    manualBaseUrl,
    manualModel,
    selectedModel,
    manualAuthMode,
    manualSecret,
    () => discoveryResult.value?.endpoint ?? "",
    () => inspectionResult.value?.baseUrl ?? "",
  ],
  markReadinessStale,
);

watch(
  [manualProtocol, manualBaseUrl, manualAuthMode, manualSecret],
  () => {
    if (inspectionWriteback.value) {
      return;
    }
    inspectionResult.value = null;
    inspectionError.value = "";
    inspectionAttempted.value = false;
  },
  { flush: "sync" },
);

watch(manualAuthMode, (next, previous) => {
  if (next !== previous) {
    clearTransientSecret();
  }
});

onMounted(() => {
  // Initial load intentionally performs only the non-mutating setup GET.
  void loadSetup();
});
</script>

<template>
  <section class="provider-setup" data-testid="provider-setup" aria-labelledby="provider-setup-title">
    <header class="provider-setup-header">
      <div class="provider-setup-heading">
        <p class="provider-setup-kicker">连接设置</p>
        <h2 id="provider-setup-title">连接 AI</h2>
        <p class="provider-setup-lede">
          选择连接方式 → 检查四项能力 → 确认使用。完成后继续安全验收。
        </p>
      </div>

      <div
        v-if="!configured || editing"
        class="provider-setup-status"
        data-testid="provider-setup-status"
        :class="configuredCredentialMissing ? 'is-needs-credential' : configured ? 'is-configured' : 'is-unconfigured'"
        role="status"
        aria-live="polite"
      >
        <span class="provider-setup-status-dot" aria-hidden="true"></span>
        <div>
          <strong>
            {{ configuredCredentialMissing ? "需要补充 API Key" : configured ? "AI 已连接" : "尚未连接 AI" }}
          </strong>
          <p>{{ statusCaption }}</p>
        </div>
      </div>
    </header>

    <div v-if="setupLoading" class="provider-setup-loading" role="status" aria-live="polite">
      正在读取连接状态…
    </div>

    <UserProblemCard
      v-if="providerProblem"
      class="provider-setup-error"
      data-testid="provider-setup-error"
      :problem="providerProblem"
      action-test-id="provider-problem-action"
      @action="resolveProviderProblem"
    />

    <div class="provider-setup-body">
      <template v-if="!configured || editing">
        <div class="provider-setup-mode" role="tablist" aria-label="连接方式">
          <button
            type="button"
            class="provider-setup-mode-button"
            data-testid="provider-setup-auto"
            :class="{ 'is-active': connectionMode === 'discover' }"
            :aria-selected="connectionMode === 'discover'"
            role="tab"
            @click="selectMode('discover')"
          >
            <strong>自动查找本机</strong>
            <span>本机 Ollama</span>
          </button>
          <button
            type="button"
            class="provider-setup-mode-button"
            data-testid="provider-setup-manual"
            :class="{ 'is-active': connectionMode === 'manual' }"
            :aria-selected="connectionMode === 'manual'"
            role="tab"
            @click="selectMode('manual')"
          >
            <strong>连接企业地址</strong>
            <span>选择协议，连接一个企业地址</span>
          </button>
        </div>

        <section v-if="connectionMode === 'discover'" class="provider-setup-method provider-setup-method-local" aria-labelledby="provider-setup-discover-title">
          <div class="provider-setup-local-grid">
            <div class="provider-setup-local-method">
              <p class="provider-setup-grid-label">01 / 选择连接</p>

              <h3 id="provider-setup-discover-title">查找本机 Ollama</h3>
              <p>先启动 Ollama，再点击「查找本机模型」。</p>
              <details class="provider-setup-technical-details">
                <summary>查看检查范围</summary>
                <span>只请求 <code>http://127.0.0.1:11434/api/tags</code>，不扫描局域网或模型文件夹。</span>
              </details>
            </div>

            <div class="provider-setup-local-target">
              <p class="provider-setup-grid-label">地址与模型</p>
              <div class="provider-setup-readonly">127.0.0.1:11434</div>
              <div v-if="discoveryResult" class="provider-setup-discovery-result" aria-live="polite">
                <div class="provider-setup-discovery-meta">
                  <span
                    class="provider-setup-result-badge"
                    :class="discoveryResult.status === 'available' ? 'is-available' : 'is-unavailable'"
                  >
                    {{ discoveryResult.status === "available" ? "可用" : "不可用" }}
                  </span>
                  <span>{{ discoveryResult.models.length }} 个模型</span>
                </div>

                <p v-if="discoveryResult.status === 'unavailable'" class="provider-setup-method-error">
                  {{ discoveryResult.diagnostic || "本机 Ollama 当前不可用，请确认它已启动后再次尝试。" }}
                </p>

                <div v-if="discoveryResult.status === 'available'" class="provider-setup-inspection-summary">
                  <span>协议</span>
                  <strong>Ollama</strong>
                  <span>地址</span>
                  <code>{{ discoveryResult.endpoint }}</code>
                </div>

                <div v-if="discoveryResult.status === 'available' && discoveryResult.models.length > 0" class="provider-setup-field">
                  <label for="provider-setup-model">选择一个已安装模型</label>
                  <select id="provider-setup-model" v-model="selectedModel" data-testid="provider-setup-model">
                    <option value="" disabled>请选择一个已安装模型</option>
                    <option v-for="model in discoveryResult.models" :key="model.name" :value="model.name">
                      {{ model.name }}
                    </option>
                  </select>
                  <p class="provider-setup-method-note">
                    本项目不限定模型名称；是否适合当前验收，以后续四项 Readiness 实测为准。
                  </p>
                </div>
                <p v-else-if="discoveryResult.status === 'available'" class="provider-setup-method-error">
                  本机 Ollama 没有返回已安装模型。请先安装一个模型后再次查找；本项目不限定模型名称，最终以 Readiness 实测为准。
                </p>
              </div>
              <p v-else class="provider-setup-method-note">
                查找后可选择任一已安装模型；是否适合本项目，以后续四项 Readiness 实测为准。
              </p>
            </div>

            <div class="provider-setup-local-action">
              <p class="provider-setup-grid-label">操作</p>
              <button
                type="button"
                class="provider-setup-primary"
                data-testid="provider-setup-discover"
                :disabled="discoveryLoading || inspectionLoading || readinessLoading || saving"
                @click="discoverOllama"
              >
                {{ discoveryLoading ? "查找中…" : "查找本机模型" }}
              </button>
            </div>
          </div>
        </section>

        <section v-else class="provider-setup-method" aria-labelledby="provider-setup-manual-title">
          <div class="provider-setup-method-heading">
            <div>
              <p class="provider-setup-section-kicker">企业连接</p>
              <h3 id="provider-setup-manual-title">连接企业地址</h3>
              <p>选择明确协议，再填写一个企业模型地址。</p>
              <details class="provider-setup-technical-details">
                <summary>查看连接范围</summary>
                <span>{{ enterpriseInspectionHint }}</span>
              </details>
            </div>
          </div>

          <div class="provider-setup-form">
            <div class="provider-setup-field">
              <label for="provider-setup-protocol">协议</label>
              <select
                id="provider-setup-protocol"
                v-model="manualProtocol"
                data-testid="provider-setup-protocol"
                @change="selectProtocol(manualProtocol)"
              >
                <option v-for="protocol in ENTERPRISE_PROTOCOLS" :key="protocol" :value="protocol">
                  {{ protocolLabel(protocol) }}
                </option>
              </select>
              <p class="provider-setup-method-note provider-setup-protocol-hint">
                {{ enterpriseProtocolHint }}
              </p>
            </div>
            <div class="provider-setup-field">
              <label for="provider-setup-base-url">企业地址</label>
              <input
                id="provider-setup-base-url"
                v-model="manualBaseUrl"
                data-testid="provider-setup-base-url"
                type="url"
                autocomplete="off"
                placeholder="例如 https://ai.intra.example/v1"
              />
            </div>
            <div class="provider-setup-field">
              <label for="provider-setup-auth-mode">认证</label>
              <select
                id="provider-setup-auth-mode"
                v-model="manualAuthMode"
                data-testid="provider-setup-auth-mode"
              >
                <option v-for="authMode in enterpriseAuthModes" :key="authMode" :value="authMode">
                  {{ authModeLabel(authMode) }}
                </option>
              </select>
            </div>
          </div>

          <div v-if="credentialRequired" class="provider-setup-secret-field">
            <label for="provider-setup-secret">{{ credentialLabel }}</label>
            <input
              id="provider-setup-secret"
              v-model="manualSecret"
              data-testid="provider-setup-secret"
              type="password"
              autocomplete="new-password"
              :placeholder="credentialPlaceholder"
            />
            <p>
              {{ isDesktopRuntime() ? "桌面端使用系统凭据存储。" : "浏览器仅临时使用，不保存密钥。" }}
            </p>
          </div>

          <div class="provider-setup-inspect-row">
            <button
              type="button"
              class="provider-setup-primary"
              data-testid="provider-setup-inspect"
              :disabled="inspectionLoading || discoveryLoading || readinessLoading || saving || !manualBaseUrl.trim()"
              @click="inspectEnterprise"
            >
              {{ inspectionLoading ? "检查中…" : "检查企业地址" }}
            </button>
            <details class="provider-setup-technical-details">
              <summary>检查说明</summary>
              <span>仅在点击后访问，不会在首载或刷新时访问企业地址。</span>
            </details>
          </div>

          <div v-if="inspectionResult" class="provider-setup-inspection" data-testid="provider-setup-inspection-result" aria-live="polite">
            <div class="provider-setup-inspection-summary">
              <span>状态</span>
              <strong :class="inspectionResult.status === 'available' ? 'is-positive' : 'is-negative'">
                {{ inspectionResult.status === "available" ? "可用" : "不可用" }}
              </strong>
              <span>协议</span>
              <strong>{{ protocolLabel(inspectionResult.protocol) }}</strong>
              <span>地址</span>
              <code>{{ inspectionResult.baseUrl }}</code>
            </div>
            <p v-if="inspectionResult.status === 'unavailable'" class="provider-setup-method-error">
              {{ inspectionStatusError }}
            </p>
            <div
              v-if="inspectionResult.status === 'available' && inspectionCapabilities"
              class="provider-setup-capabilities"
              data-testid="provider-setup-capabilities"
            >
              <div class="provider-setup-capabilities-heading">
                <span>{{ inspectionResult.protocol === "agent_audit_adapter" ? "适配器版本" : "协议能力" }}</span>
                <strong>{{ inspectionProtocolVersion || "已返回" }}</strong>
              </div>
              <div class="provider-setup-capabilities-list">
                <span :class="{ 'is-supported': inspectionCapabilities.text }">文本</span>
                <span :class="{ 'is-supported': inspectionCapabilities.toolCalling }">Tool Calling</span>
                <span :class="{ 'is-supported': inspectionCapabilities.structuredOutput }">Structured Output</span>
                <span :class="{ 'is-supported': inspectionCapabilities.usage }">Usage</span>
              </div>
            </div>
            <p v-if="inspectionResult.status === 'available' && (!inspectionResult.modelsEnumerated || inspectionResult.models.length === 0)" class="provider-setup-method-note">
              {{ manualProtocol === "anthropic_compatible" ? "Anthropic Messages API 不保证模型枚举，" : "模型未从服务枚举，" }}最终以四项 Readiness 为准。请手填模型 ID。
            </p>
            <div v-if="inspectionResult.status === 'available' && inspectionResult.modelsEnumerated && inspectionResult.models.length > 0" class="provider-setup-field provider-setup-model-field">
              <label for="provider-setup-enterprise-model">服务返回的模型</label>
              <select
                id="provider-setup-enterprise-model"
                v-model="manualModel"
                data-testid="provider-setup-model"
              >
                <option value="" disabled>请选择服务返回的模型</option>
                <option v-for="model in inspectionResult.models" :key="model.id" :value="model.id">
                  {{ model.id }}
                </option>
              </select>
            </div>
          </div>

          <div
            v-if="inspectionAttempted && (!inspectionResult || !inspectionResult.modelsEnumerated || inspectionResult.models.length === 0)"
            class="provider-setup-field provider-setup-manual-model"
          >
            <label for="provider-setup-manual-model">模型 ID</label>
            <input
              id="provider-setup-manual-model"
              v-model="manualModel"
              data-testid="provider-setup-model"
              type="text"
              autocomplete="off"
              placeholder="例如 enterprise-model"
            />
            <p class="provider-setup-method-note">模型未从服务枚举，最终以四项 Readiness 为准。</p>
          </div>
        </section>

        <div class="provider-setup-readiness-area">
          <figure
            class="provider-setup-flow-visual"
            :class="`is-${readinessVisualState}`"
            data-testid="provider-readiness-visual"
            :data-state="readinessVisualState"
            role="img"
            aria-live="polite"
            :aria-label="readinessVisualLabel"
          >
            <Transition name="provider-flow-state">
              <img
                :key="readinessVisualState"
                :src="readinessVisualUrl"
                alt=""
                width="1600"
                height="640"
              />
            </Transition>
            <span
              v-if="readinessVisualState === 'connected'"
              :key="`sweep-${readinessVisualState}`"
              class="provider-setup-flow-success-sweep"
              aria-hidden="true"
            ></span>
            <span
              v-if="readinessLoading"
              class="provider-setup-flow-loading-sweep"
              aria-hidden="true"
            ></span>
            <figcaption class="provider-setup-flow-copy">
              <strong>{{ readinessVisualLabel }}</strong>
              <span>{{ readinessVisualCaption }}</span>
            </figcaption>
          </figure>

          <div v-if="readinessStale" class="provider-setup-stale" role="note">
            草稿已变化，之前的兼容性结果已过期。请重新检查兼容性。
          </div>

          <ProviderReadinessView
            :result="readinessResult"
            :loading="readinessLoading"
            :error="providerProblem?.action === 'readiness' ? '' : readinessError"
            title="模型能力检查 · Readiness"
            title-id="provider-setup-readiness-title"
            lede="确认 AI 能连接、能调用工具，攻击模型能按要求生成结构化输出；通过后才能确认使用。"
            run-label="开始检查"
            run-test-id="provider-setup-check"
            presentation="candidate"
            :run-disabled="!settingsComplete || !enterpriseInspectionComplete || saving"
            @run="checkReadiness"
          />
        </div>

        <footer class="provider-setup-confirm-row">
          <div class="provider-setup-confirm-summary">
            <span class="provider-setup-confirm-kicker">03 / 完成连接</span>
            <strong>确认后即可使用</strong>
            <p>四项检查通过后点击「确认使用」，再继续当前验收流程。API Key 仅存桌面系统凭据。</p>
          </div>
          <div class="provider-setup-confirm-actions">
            <button
              v-if="configured"
              type="button"
              class="provider-setup-cancel"
              data-testid="provider-setup-cancel"
              :disabled="saving || readinessLoading || discoveryLoading"
              @click="cancelEditing"
            >
              取消更改
            </button>
            <button
              type="button"
              class="provider-setup-confirm"
              data-testid="provider-setup-confirm"
              :disabled="saving || readinessLoading || inspectionLoading || !settingsComplete || !enterpriseInspectionComplete || !readinessReady || readinessStale"
              @click="confirmProvider"
            >
              {{ saving ? "保存中…" : "确认使用" }}
            </button>
          </div>
        </footer>
      </template>

      <section v-else class="provider-setup-compact" data-testid="provider-setup-compact" aria-label="当前 AI 连接">
        <div
          class="provider-setup-compact-state"
          data-testid="provider-setup-status"
          role="status"
          aria-live="polite"
        >
          <span
            class="provider-setup-compact-dot"
            :class="{ 'is-warning': configuredCredentialMissing }"
            aria-hidden="true"
          ></span>
          <div>
            <p class="provider-setup-section-kicker">当前连接</p>
            <strong>{{ configuredCredentialMissing ? "连接未就绪" : "已连接" }}</strong>
            <div class="provider-setup-compact-details">
              <span>协议：{{ settingsProtocolLabel(setupState?.settings || null) }}</span>
              <span>模型：<code>{{ setupState?.settings?.model || "未配置模型" }}</code></span>
              <span>认证：{{ compactCredentialLabel }}</span>
            </div>
          </div>
        </div>
        <button
          type="button"
          class="provider-setup-edit"
          data-testid="provider-setup-edit"
          @click="beginEditing"
        >
          更改连接
        </button>
      </section>
    </div>
  </section>
</template>

<style scoped>
.provider-setup {
  --setup-ink-strong: var(--ink-strong, #132238);
  --setup-ink: var(--ink, #26364c);
  --setup-muted: var(--ink-muted, #64748b);
  --setup-faint: var(--ink-faint, #94a3b8);
  --setup-line: var(--line, #dbe4ef);
  --setup-surface: var(--surface, #ffffff);
  --setup-raised: var(--surface-raised, #f8fafc);
  --setup-action: var(--action-blue, #4f7cff);
  --setup-accent: var(--evidence-teal, #25bfae);
  --setup-warning: var(--warning-amber, #e6a23c);
  --setup-danger: var(--risk-coral, #ff5d5d);
  width: 100%;
  max-width: 1180px;
  min-width: 0;
  margin: 0 auto 18px;
  color: var(--setup-ink);
}

.provider-setup,
.provider-setup * {
  min-width: 0;
}

.provider-setup-header,
.provider-setup-method,
.provider-setup-error,
.provider-setup-loading,
.provider-setup-stale,
.provider-setup-confirm-row,
.provider-setup-compact {
  border: 1px solid var(--setup-line);
  border-radius: 14px;
  background: var(--setup-surface);
}

.provider-setup-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: clamp(17px, 3vw, 23px) clamp(18px, 3vw, 26px);
  background:
    linear-gradient(135deg, rgba(79, 124, 255, 0.08), transparent 48%),
    var(--setup-surface);
}

.provider-setup-heading {
  min-width: 0;
}

.provider-setup-kicker,
.provider-setup-section-kicker {
  margin: 0;
  color: var(--setup-accent);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.provider-setup-heading h2 {
  margin: 6px 0 0;
  color: var(--setup-ink-strong);
  font-size: clamp(22px, 3vw, 29px);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.2;
}

.provider-setup-lede {
  max-width: 650px;
  margin: 7px 0 0;
  color: var(--setup-muted);
  font-size: 12px;
  line-height: 1.65;
}

.provider-setup-status {
  display: flex;
  align-items: flex-start;
  flex: 0 1 235px;
  gap: 8px;
  min-width: 0;
  padding: 9px 11px;
  border: 1px solid var(--setup-line);
  border-radius: 10px;
  background: var(--setup-raised);
}

.provider-setup-status.is-configured {
  border-color: rgba(37, 191, 174, 0.38);
}

.provider-setup-status.is-needs-credential {
  border-color: rgba(230, 162, 60, 0.42);
}

.provider-setup-status-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  margin-top: 4px;
  background: var(--setup-warning);
  border-radius: 50%;
  box-shadow: 0 0 0 4px rgba(230, 162, 60, 0.14);
}

.provider-setup-status.is-configured .provider-setup-status-dot {
  background: var(--setup-accent);
  box-shadow: 0 0 0 4px rgba(37, 191, 174, 0.14);
}

.provider-setup-status.is-needs-credential .provider-setup-status-dot {
  background: var(--setup-warning);
  box-shadow: 0 0 0 4px rgba(230, 162, 60, 0.14);
}

.provider-setup-status strong {
  color: var(--setup-ink-strong);
  font-size: 11px;
}

.provider-setup-status p {
  margin: 3px 0 0;
  color: var(--setup-muted);
  font-size: 10px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.provider-setup-loading,
.provider-setup-error,
.provider-setup-stale {
  margin-top: 10px;
  padding: 11px 14px;
  font-size: 11px;
  line-height: 1.55;
}

.provider-setup-loading {
  color: var(--setup-muted);
}

.provider-setup-error {
  color: #8f2d2d;
  border-color: rgba(255, 93, 93, 0.35);
  background: #fff3f2;
}

.provider-setup-error strong {
  color: var(--setup-danger);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  letter-spacing: 0.06em;
}

.provider-setup-error p,
.provider-setup-stale {
  margin-bottom: 0;
}

.provider-setup-error p {
  margin: 5px 0 0;
  overflow-wrap: anywhere;
}

.provider-setup-stale {
  color: #8a5b11;
  border-color: rgba(230, 162, 60, 0.4);
  background: #fff8e8;
}

.provider-setup-body {
  min-width: 0;
  margin-top: 10px;
}

.provider-setup-mode {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.provider-setup-mode-button {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 10px 13px;
  color: var(--setup-muted);
  text-align: left;
  background: var(--setup-surface);
  border: 1px solid var(--setup-line);
  border-radius: 9px;
  cursor: pointer;
}

.provider-setup-mode-button:hover,
.provider-setup-mode-button.is-active {
  color: var(--setup-ink-strong);
  border-color: rgba(79, 124, 255, 0.58);
  background: #f1f5ff;
}

.provider-setup-mode-button strong {
  font-size: 12px;
}

.provider-setup-mode-button span {
  color: var(--setup-faint);
  font-size: 10px;
  line-height: 1.45;
}

.provider-setup-method {
  margin-top: 10px;
  padding: 16px;
}

.provider-setup-method-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.provider-setup-local-grid {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 6fr) minmax(122px, 3fr);
  gap: 14px;
  align-items: start;
}

.provider-setup-local-method,
.provider-setup-local-target,
.provider-setup-local-action {
  min-width: 0;
}

.provider-setup-grid-label,
.provider-setup-confirm-kicker {
  margin: 0 0 7px;
  color: var(--setup-faint);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 9px;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.provider-setup-local-method .provider-setup-section-kicker {
  margin-top: 1px;
}

.provider-setup-local-method h3 {
  margin-top: 5px;
}

.provider-setup-local-method > p:not(.provider-setup-grid-label):not(.provider-setup-section-kicker) {
  margin: 5px 0 0;
  color: var(--setup-muted);
  font-size: 10px;
  line-height: 1.5;
}

.provider-setup-local-target .provider-setup-readonly {
  margin-top: 0;
}

.provider-setup-local-target > .provider-setup-method-note {
  margin-top: 8px;
}

.provider-setup-local-action .provider-setup-primary {
  width: 100%;
}

.provider-setup-method h3 {
  margin: 6px 0 0;
  color: var(--setup-ink-strong);
  font-size: 16px;
  font-weight: 650;
}

.provider-setup-method-heading p:last-child {
  max-width: 620px;
  margin: 6px 0 0;
  color: var(--setup-muted);
  font-size: 11px;
  line-height: 1.55;
}

.provider-setup-method-heading code,
.provider-setup-method code {
  color: var(--setup-ink);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 10px;
}

.provider-setup-primary,
.provider-setup-confirm {
  flex: 0 0 auto;
  min-height: 40px;
  padding: 0 15px;
  color: #ffffff;
  background: var(--setup-action);
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 750;
  white-space: nowrap;
}

.provider-setup-primary:hover:not(:disabled),
.provider-setup-confirm:hover:not(:disabled) {
  background: #3f68df;
}

.provider-setup-confirm {
  background: var(--setup-accent);
  border-color: var(--setup-accent);
}

.provider-setup-confirm:hover:not(:disabled) {
  background: #1fa895;
}

.provider-setup-primary:disabled,
.provider-setup-confirm:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.provider-setup-discovery-result {
  margin-top: 8px;
}

.provider-setup-inspection-summary {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 6px 12px;
  margin-top: 14px;
  color: var(--setup-muted);
  font-size: 10px;
  line-height: 1.5;
}

.provider-setup-inspection-summary strong {
  color: var(--setup-ink-strong);
  font-size: 11px;
  font-weight: 650;
}

.provider-setup-inspection-summary strong.is-positive {
  color: var(--setup-accent);
}

.provider-setup-inspection-summary strong.is-negative {
  color: var(--setup-danger);
}

.provider-setup-inspection-summary code {
  color: var(--setup-ink);
  overflow-wrap: anywhere;
}

.provider-setup-discovery-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--setup-muted);
  font-size: 10px;
}

.provider-setup-result-badge {
  display: inline-flex;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.provider-setup-result-badge.is-available {
  color: #087f73;
  border-color: rgba(37, 191, 174, 0.34);
  background: #e9fbf7;
}

.provider-setup-result-badge.is-unavailable {
  color: #a33a3a;
  border-color: rgba(255, 93, 93, 0.32);
  background: #fff3f2;
}

.provider-setup-field {
  display: grid;
  gap: 7px;
  min-width: 0;
}

.provider-setup-discovery-result .provider-setup-field {
  max-width: none;
  margin-top: 9px;
}

.provider-setup-field label,
.provider-setup-field-label {
  color: var(--setup-ink);
  font-size: 11px;
  font-weight: 650;
}

.provider-setup-field input,
.provider-setup-field select {
  width: 100%;
  min-height: 42px;
  min-width: 0;
  padding: 0 12px;
  color: var(--setup-ink-strong);
  background: var(--setup-surface);
  border: 1px solid var(--setup-line);
  border-radius: 8px;
  outline: none;
  font-size: 12px;
}

.provider-setup-field input::placeholder {
  color: var(--setup-faint);
}

.provider-setup-field input:focus,
.provider-setup-field select:focus {
  border-color: rgba(79, 124, 255, 0.72);
  box-shadow: 0 0 0 3px rgba(79, 124, 255, 0.12);
}

.provider-setup-field select option {
  color: var(--setup-ink-strong);
  background: var(--setup-surface);
}

.provider-setup-method-error {
  margin: 12px 0 0;
  color: #a33a3a;
  font-size: 11px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.provider-setup-protocol-hint {
  margin-top: 6px;
  font-size: 10px;
}

.provider-setup-method-note {
  margin: 12px 0 0;
  color: var(--setup-muted);
  font-size: 11px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.provider-setup-form {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 6fr) minmax(0, 3fr);
  gap: 12px;
  margin-top: 14px;
}

.provider-setup-secret-field {
  display: grid;
  gap: 7px;
  max-width: none;
  margin-top: 12px;
}

.provider-setup-secret-field label {
  color: var(--setup-ink);
  font-size: 11px;
  font-weight: 650;
}

.provider-setup-secret-field input {
  width: 100%;
  min-height: 42px;
  padding: 0 12px;
  color: var(--setup-ink-strong);
  background: var(--setup-surface);
  border: 1px solid var(--setup-line);
  border-radius: 8px;
  outline: none;
  font-size: 12px;
}

.provider-setup-secret-field input:focus {
  border-color: rgba(79, 124, 255, 0.72);
  box-shadow: 0 0 0 3px rgba(79, 124, 255, 0.12);
}

.provider-setup-secret-field input::placeholder {
  color: var(--setup-faint);
}

.provider-setup-secret-field p,
.provider-setup-inspect-row p {
  margin: 0;
  color: var(--setup-muted);
  font-size: 10px;
  line-height: 1.5;
}

.provider-setup-inspect-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 13px;
}

.provider-setup-technical-details {
  margin-top: 8px;
  color: var(--setup-muted);
  font-size: 10px;
  line-height: 1.5;
}

.provider-setup-technical-details summary {
  width: fit-content;
  color: var(--setup-action);
  cursor: pointer;
  font-size: 10px;
}

.provider-setup-technical-details span {
  display: block;
  max-width: 620px;
  margin-top: 5px;
  color: var(--setup-muted);
}

.provider-setup-inspect-row .provider-setup-technical-details {
  margin-top: 0;
}

.provider-setup-inspect-row .provider-setup-primary {
  min-height: 36px;
}

.provider-setup-inspection {
  margin-top: 13px;
  padding: 12px 0 0;
  border-top: 1px solid var(--setup-line);
}

.provider-setup-capabilities {
  display: grid;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 11px;
  color: var(--setup-muted);
  background: var(--setup-raised);
  border: 1px solid var(--setup-line);
  border-radius: 8px;
  font-size: 10px;
}

.provider-setup-capabilities-heading,
.provider-setup-capabilities-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px 12px;
}

.provider-setup-capabilities-heading {
  justify-content: space-between;
}

.provider-setup-capabilities-heading strong {
  color: var(--setup-ink-strong);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 10px;
}

.provider-setup-capabilities-list span {
  color: var(--setup-faint);
}

.provider-setup-capabilities-list span.is-supported {
  color: var(--setup-accent);
}

.provider-setup-model-field,
.provider-setup-manual-model {
  max-width: none;
  margin-top: 11px;
}

.provider-setup-readonly {
  display: flex;
  align-items: center;
  min-height: 42px;
  padding: 0 12px;
  color: var(--setup-muted);
  background: var(--setup-raised);
  border: 1px solid var(--setup-line);
  border-radius: 8px;
  font-size: 12px;
}

.provider-setup-confirm-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 10px;
  padding: 11px 14px;
}

.provider-setup-confirm-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 9px;
  flex: 0 0 auto;
}

.provider-setup-readiness-area {
  margin-top: 10px;
}

.provider-setup-flow-visual {
  position: relative;
  height: clamp(160px, 24vw, 280px);
  margin: 0 0 10px;
  overflow: hidden;
  isolation: isolate;
  background: #061326;
  border-radius: 14px;
  box-shadow: 0 14px 32px rgba(7, 19, 34, 0.18);
}

.provider-setup-flow-visual::after {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  content: "";
  background:
    linear-gradient(90deg, rgba(3, 12, 26, 0.54), transparent 34%),
    linear-gradient(0deg, rgba(3, 12, 26, 0.62), transparent 48%);
}

.provider-setup-flow-visual img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.provider-setup-flow-copy {
  position: absolute;
  right: 16px;
  bottom: 14px;
  left: 16px;
  z-index: 4;
  display: grid;
  gap: 4px;
  max-width: 600px;
  color: rgba(232, 242, 255, 0.78);
  font-size: 10px;
  line-height: 1.5;
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.72);
}

.provider-setup-flow-copy strong {
  color: #ffffff;
  font-size: 13px;
  letter-spacing: 0.01em;
}

.provider-setup-flow-visual.is-connected .provider-setup-flow-copy strong {
  color: #8ff7dc;
}

.provider-setup-flow-success-sweep,
.provider-setup-flow-loading-sweep {
  position: absolute;
  inset: 0;
  z-index: 3;
  pointer-events: none;
}

.provider-setup-flow-success-sweep {
  background: linear-gradient(
    100deg,
    transparent 30%,
    rgba(75, 244, 197, 0.04) 43%,
    rgba(75, 244, 197, 0.42) 50%,
    rgba(75, 244, 197, 0.04) 57%,
    transparent 70%
  );
  transform: translateX(85%);
  animation: provider-flow-success 720ms cubic-bezier(0.22, 0.72, 0.22, 1) both;
}

.provider-setup-flow-loading-sweep {
  background: linear-gradient(
    100deg,
    transparent 34%,
    rgba(99, 167, 255, 0.28) 50%,
    transparent 66%
  );
  animation: provider-flow-loading 1.15s ease-in-out infinite;
}

.provider-flow-state-enter-active,
.provider-flow-state-leave-active {
  transition:
    opacity 420ms ease,
    filter 520ms ease,
    transform 560ms cubic-bezier(0.22, 0.72, 0.22, 1);
}

.provider-flow-state-enter-from {
  opacity: 0;
  filter: saturate(0.72) blur(5px);
  transform: scale(1.018);
}

.provider-flow-state-leave-to {
  opacity: 0;
  filter: saturate(0.84) blur(3px);
  transform: scale(0.994);
}

@keyframes provider-flow-success {
  from {
    transform: translateX(-90%);
  }
  to {
    transform: translateX(85%);
  }
}

@keyframes provider-flow-loading {
  from {
    transform: translateX(-80%);
  }
  to {
    transform: translateX(80%);
  }
}

.provider-setup-readiness-area .provider-setup-stale {
  margin: 0 0 8px;
  padding: 8px 11px;
  font-size: 10px;
}

.provider-setup-confirm-summary {
  min-width: 0;
}

.provider-setup-confirm-kicker {
  margin-bottom: 4px;
}

.provider-setup-cancel,
.provider-setup-edit {
  min-height: 40px;
  padding: 0 15px;
  color: var(--setup-action);
  background: transparent;
  border: 1px solid rgba(79, 124, 255, 0.44);
  border-radius: 8px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.provider-setup-cancel:hover:not(:disabled),
.provider-setup-edit:hover:not(:disabled) {
  color: #ffffff;
  background: var(--setup-action);
  border-color: var(--setup-action);
}

.provider-setup-cancel:disabled,
.provider-setup-edit:disabled {
  cursor: not-allowed;
  opacity: 0.52;
}

.provider-setup-compact {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 18px;
}

.provider-setup-compact-state {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.provider-setup-compact-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 auto;
  margin-top: 4px;
  background: var(--setup-accent);
  border-radius: 50%;
  box-shadow: 0 0 0 4px rgba(37, 191, 174, 0.14);
}

.provider-setup-compact-dot.is-warning {
  background: var(--setup-warning);
  box-shadow: 0 0 0 4px rgba(230, 162, 60, 0.14);
}

.provider-setup-compact-state strong {
  display: block;
  margin-top: 5px;
  color: var(--setup-ink-strong);
  font-size: 13px;
}

.provider-setup-compact-state p:last-child {
  margin: 5px 0 0;
  color: var(--setup-muted);
  font-size: 10px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.provider-setup-compact-state code {
  color: var(--setup-accent);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 10px;
}

.provider-setup-compact-details {
  display: grid;
  gap: 3px;
  margin-top: 5px;
  color: var(--setup-muted);
  font-size: 10px;
  line-height: 1.45;
}

.provider-setup-confirm-row strong {
  color: var(--setup-ink-strong);
  font-size: 12px;
}

.provider-setup-confirm-row p {
  margin: 5px 0 0;
  color: var(--setup-muted);
  font-size: 10px;
  line-height: 1.5;
}

@media (max-width: 760px) {
  .provider-setup-header,
  .provider-setup-method-heading,
  .provider-setup-confirm-row,
  .provider-setup-compact {
    align-items: stretch;
    flex-direction: column;
  }

  .provider-setup-status {
    flex-basis: auto;
  }

  .provider-setup-local-grid {
    grid-template-columns: 1fr;
    gap: 15px;
  }

  .provider-setup-local-action {
    padding-top: 1px;
  }

  .provider-setup-primary,
  .provider-setup-confirm,
  .provider-setup-cancel,
  .provider-setup-edit {
    width: 100%;
  }

  .provider-setup-inspect-row {
    align-items: stretch;
    flex-direction: column;
  }

  .provider-setup-confirm-actions {
    width: 100%;
    flex-direction: column;
  }

  .provider-setup-form {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .provider-setup-header,
  .provider-setup-method,
  .provider-setup-error,
  .provider-setup-loading,
  .provider-setup-stale,
  .provider-setup-confirm-row,
  .provider-setup-compact {
    border-radius: 10px;
  }

  .provider-setup-flow-visual {
    height: 156px;
    border-radius: 10px;
  }

  .provider-setup-flow-copy {
    right: 11px;
    bottom: 10px;
    left: 11px;
  }

  .provider-setup-flow-copy strong {
    font-size: 11px;
  }

  .provider-setup-header,
  .provider-setup-method {
    padding: 16px;
  }

  .provider-setup-mode {
    grid-template-columns: 1fr;
  }

  .provider-setup-discovery-meta {
    align-items: flex-start;
    flex-direction: column;
  }
}

/* F-060: user-facing connection guidance uses the shared type scale. IDs,
 * endpoint values and raw diagnostics remain the only monospace layer. */
.provider-setup-kicker,
.provider-setup-section-kicker,
.provider-setup-grid-label,
.provider-setup-confirm-kicker {
  color: var(--setup-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.provider-setup-lede,
.provider-setup-status p,
.provider-setup-method-heading p:last-child,
.provider-setup-local-method > p:not(.provider-setup-grid-label):not(.provider-setup-section-kicker),
.provider-setup-method-note,
.provider-setup-method-error,
.provider-setup-secret-field p,
.provider-setup-inspect-row p,
.provider-setup-technical-details,
.provider-setup-technical-details span,
.provider-setup-confirm-row p,
.provider-setup-compact-state p:last-child,
.provider-setup-compact-details {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-status strong,
.provider-setup-mode-button strong,
.provider-setup-field label,
.provider-setup-secret-field label,
.provider-setup-confirm-row strong,
.provider-setup-compact-state strong {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-mode-button span,
.provider-setup-primary,
.provider-setup-confirm,
.provider-setup-cancel,
.provider-setup-edit,
.provider-setup-technical-details summary,
.provider-setup-result-badge,
.provider-setup-discovery-meta,
.provider-setup-inspection-summary,
.provider-setup-inspection-summary strong,
.provider-setup-capabilities,
.provider-setup-capabilities-heading strong,
.provider-setup-capabilities-list span {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.provider-setup-method h3 {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.provider-setup-error.user-problem-card {
  margin-top: 12px;
  padding: 16px 18px;
  color: var(--setup-ink);
  background: #fff1f1;
  border-color: #ffcaca;
  font-family: var(--font-ui);
}

.provider-setup-flow-copy {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-flow-copy strong {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.provider-setup-readiness-area .provider-setup-stale {
  font-size: var(--type-body-small-size, 13px);
}

@media (prefers-reduced-motion: reduce) {
  .provider-flow-state-enter-active,
  .provider-flow-state-leave-active {
    transition: none;
  }

  .provider-setup-flow-success-sweep,
  .provider-setup-flow-loading-sweep {
    animation: none;
  }
}

/* F-062: keep the readiness artwork as a bounded status band. It is tied to
   the real readiness state and remains subordinate to the connection form. */
.provider-setup-header,
.provider-setup-method,
.provider-setup-confirm-row,
.provider-setup-compact {
  border-radius: 10px;
  box-shadow: none;
}

.provider-setup-mode {
  gap: 0;
  overflow: hidden;
  background: var(--setup-surface);
  border: 1px solid var(--setup-line);
  border-radius: 10px;
}

.provider-setup-mode-button {
  border: 0;
  border-radius: 0;
  background: transparent;
}

.provider-setup-mode-button + .provider-setup-mode-button {
  border-left: 1px solid var(--setup-line);
}

.provider-setup-flow-visual {
  height: clamp(128px, 12vw, 164px);
  border-radius: 10px;
  box-shadow: none;
}

.provider-setup-flow-copy {
  right: 14px;
  bottom: 12px;
  left: 14px;
  max-width: 720px;
}

.provider-setup-flow-copy strong {
  font-size: 16px;
  line-height: var(--type-heading-leading, 1.22);
}

.provider-setup-flow-copy span {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

@media (max-width: 760px) {
  .provider-setup-mode-button + .provider-setup-mode-button {
    border-top: 1px solid var(--setup-line);
    border-left: 0;
  }

  .provider-setup-flow-visual {
    height: 132px;
  }
}

/* F-063: connection setup is a business work surface. The readiness image
 * remains a bounded, state-driven band; the rest of the page uses the shared
 * tokens and keeps raw endpoint/diagnostic values in the technical layer. */
.provider-setup {
  --setup-faint: var(--ink-muted, #64748b);
  --setup-line: var(--line, #dce5ef);
  --setup-surface: var(--surface, #ffffff);
  --setup-raised: var(--surface-raised, #f8fafc);
  font-family: var(--font-ui);
  font-size: var(--type-body-size, 16px);
  line-height: var(--type-body-leading, 1.62);
}

.provider-setup-header,
.provider-setup-method,
.provider-setup-error,
.provider-setup-loading,
.provider-setup-stale,
.provider-setup-confirm-row,
.provider-setup-compact {
  border-radius: var(--radius-card, 12px);
  box-shadow: var(--shadow-card, 0 12px 30px rgba(35, 68, 120, 0.08));
}

.provider-setup-header {
  background: var(--surface, #ffffff);
}

.provider-setup-kicker,
.provider-setup-section-kicker,
.provider-setup-grid-label,
.provider-setup-confirm-kicker {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
  letter-spacing: normal;
  text-transform: none;
}

.provider-setup-heading h2 {
  font-size: var(--type-section-title-size, 24px);
  line-height: var(--type-heading-leading, 1.22);
}

.provider-setup-lede,
.provider-setup-status p,
.provider-setup-method-heading p:last-child,
.provider-setup-local-method > p:not(.provider-setup-grid-label):not(.provider-setup-section-kicker),
.provider-setup-method-note,
.provider-setup-method-error,
.provider-setup-secret-field p,
.provider-setup-inspect-row p,
.provider-setup-technical-details,
.provider-setup-technical-details span,
.provider-setup-confirm-row p,
.provider-setup-compact-details {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-status strong,
.provider-setup-confirm-row strong,
.provider-setup-compact-state strong {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.provider-setup-mode-button,
.provider-setup-primary,
.provider-setup-confirm,
.provider-setup-cancel,
.provider-setup-edit,
.provider-setup-inspect-row .provider-setup-primary {
  min-height: 44px;
  border-radius: var(--radius-control, 9px);
}

.provider-setup-mode-button {
  font-size: var(--type-body-small-size, 14px);
}

.provider-setup-mode-button strong,
.provider-setup-field label,
.provider-setup-secret-field label {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-mode-button span,
.provider-setup-primary,
.provider-setup-confirm,
.provider-setup-cancel,
.provider-setup-edit,
.provider-setup-result-badge,
.provider-setup-discovery-meta,
.provider-setup-inspection-summary,
.provider-setup-inspection-summary strong,
.provider-setup-capabilities,
.provider-setup-capabilities-heading strong,
.provider-setup-capabilities-list span,
.provider-setup-technical-details summary {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.provider-setup-method h3 {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.provider-setup-loading,
.provider-setup-error,
.provider-setup-stale {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-error,
.provider-setup-method-error {
  color: var(--risk-coral-strong, #c63d46);
}

.provider-setup-stale {
  color: var(--warning-amber, #e6a23c);
  background: var(--warning-amber-wash, rgba(230, 162, 60, 0.14));
}

.provider-setup-field input,
.provider-setup-field select,
.provider-setup-secret-field input,
.provider-setup-readonly {
  min-height: 44px;
  border-radius: var(--radius-control, 9px);
  font-size: var(--type-body-small-size, 14px);
}

.provider-setup-field input:focus,
.provider-setup-field select:focus,
.provider-setup-secret-field input:focus,
.provider-setup button:focus-visible {
  outline: 2px solid var(--action-blue, #4f7cff);
  outline-offset: 2px;
}

.provider-setup-method code,
.provider-setup-compact-details code {
  font-family: var(--font-code);
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
}

.provider-setup-result-badge.is-available,
.provider-setup-inspection-summary strong.is-positive,
.provider-setup-capabilities-list span.is-supported {
  color: var(--evidence-teal-strong, #08786e);
  background: var(--evidence-teal-wash, rgba(22, 143, 130, 0.1));
}

.provider-setup-result-badge.is-unavailable,
.provider-setup-inspection-summary strong.is-negative {
  color: var(--risk-coral-strong, #c63d46);
  background: var(--risk-coral-wash, rgba(255, 93, 93, 0.1));
}

.provider-setup-primary,
.provider-setup-confirm {
  font-size: var(--type-body-small-size, 14px);
}

.provider-setup-primary:hover:not(:disabled),
.provider-setup-confirm:hover:not(:disabled) {
  background: var(--action-blue-strong, #345fe7);
}

.provider-setup-confirm:hover:not(:disabled) {
  background: var(--evidence-teal-strong, #08786e);
}

.provider-setup-flow-visual {
  height: clamp(208px, 17vw, 240px);
  border-radius: var(--radius-stage, 16px);
  background: var(--surface-evidence, #0b2340);
  box-shadow: var(--shadow-card, 0 12px 30px rgba(35, 68, 120, 0.08));
}

.provider-setup-flow-copy {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-flow-copy strong {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.provider-setup-flow-copy span {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-flow-visual.is-connected .provider-setup-flow-copy strong {
  color: var(--evidence-teal, #25bfae);
}

/* F-063 second visual pass: connection guidance stays readable at the mobile
 * viewport, and all technical disclosures remain easy to open. */
.provider-setup-lede,
.provider-setup-status p,
.provider-setup-method-heading p:last-child,
.provider-setup-local-method > p:not(.provider-setup-grid-label):not(.provider-setup-section-kicker),
.provider-setup-method-note,
.provider-setup-method-error,
.provider-setup-secret-field p,
.provider-setup-inspect-row p,
.provider-setup-technical-details,
.provider-setup-technical-details span,
.provider-setup-confirm-row p,
.provider-setup-compact-details {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup details > summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 10px 0;
  cursor: pointer;
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup details > summary:focus-visible {
  outline: 2px solid var(--action-blue, #4f7cff);
  outline-offset: 4px;
  border-radius: var(--radius-control, 9px);
}

.provider-setup-mode-button,
.provider-setup-primary,
.provider-setup-confirm,
.provider-setup-cancel,
.provider-setup-edit {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.provider-setup-mode-button span {
  font-size: max(13px, var(--type-label-size, 13px));
  line-height: 1.45;
}

.provider-setup-method code,
.provider-setup-compact-details code {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}

@media (max-width: 760px) {
  .provider-setup-flow-visual {
    height: 180px;
  }
}
</style>
