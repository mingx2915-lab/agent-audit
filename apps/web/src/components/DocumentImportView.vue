<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { apiFetch } from "../api";
import { nativeErrorMessage, selectDocumentFiles, selectDocumentFolder } from "../native";
import UserProblemCard, { type UserProblem } from "./UserProblemCard.vue";
import type {
  Actor,
  DocumentAuthorizationPreview,
  DocumentBusinessScope,
  DocumentCatalog,
  DocumentImportDraft,
  DocumentImportDiagnosticCode,
  DocumentImportMetadata,
  DocumentImportPreview,
  DocumentImportPreviewItem,
  DocumentImportResult,
  DocumentImportSource,
  DocumentSensitivity,
  DocumentTrustLevel,
} from "@agent-audit/contracts";

const props = withDefaults(
  defineProps<{
    actors?: Actor[];
  }>(),
  {
    actors: () => [],
  },
);

const emit = defineEmits<{
  (event: "catalog", catalog: DocumentCatalog): void;
  (event: "imported", result: DocumentImportResult): void;
  (event: "start-guided-audit", planId: string): void;
  (event: "open-contract"): void;
}>();

const catalog = ref<DocumentCatalog | null>(null);
const catalogLoading = ref(false);
const catalogError = ref("");
const documentErrorSource = ref<DocumentErrorSource | null>(null);
const expanded = ref(false);
const selectedDocuments = ref<DocumentImportDraft[]>([]);
const selectionLoading = ref<"files" | "folder" | "">("");
const lastSelectionMode = ref<"files" | "folder">("files");
const selectionNotice = ref("");
const metadataConfirmed = ref(false);
const preview = ref<DocumentImportPreview | null>(null);
const previewLoading = ref(false);
const previewError = ref("");
const previewFingerprint = ref("");
const commitLoading = ref(false);
const commitError = ref("");
const importResult = ref<DocumentImportResult | null>(null);
const batchBusinessScope = ref<DocumentBusinessScope | "">("");
const batchSensitivity = ref<DocumentSensitivity | "">("");
const batchOwnerId = ref<string | "">("");

type DocumentProblemAction = "catalog" | "pick" | "preview" | "commit";
type DocumentProblem = UserProblem & { action: DocumentProblemAction };
type DocumentErrorSource = "catalog" | "selection" | "preview" | "commit";

class DocumentResponseError extends Error {
  readonly status: number;
  readonly operationId: string | null;

  constructor(status: number, detail: string, operationId: string | null) {
    super(detail || `请求失败（${status}）`);
    this.name = "DocumentResponseError";
    this.status = status;
    this.operationId = operationId;
  }
}

const sensitivityLabels: Record<DocumentSensitivity, string> = {
  public: "公开 Public",
  confidential: "机密 Confidential",
};

const businessScopeLabels: Record<DocumentBusinessScope, string> = {
  general: "通用 General",
  customer: "客户 Customer",
  finance: "财务 Finance",
  hr: "人力 HR",
};

const trustLevelLabels: Record<DocumentTrustLevel, string> = {
  trusted: "内部可信 Trusted",
  untrusted: "外部不可信 Untrusted",
};

const selectedDocumentCount = computed(() => selectedDocuments.value.length);
const readyPreviewItems = computed(() =>
  preview.value?.items.filter((item) => item.status === "ready") ?? [],
);
const previewIsStale = computed(
  () => Boolean(preview.value) && previewFingerprint.value !== currentFingerprint(),
);
const canPreview = computed(
  () =>
    selectedDocuments.value.length > 0 &&
    metadataConfirmed.value &&
    !previewLoading.value &&
    !commitLoading.value,
);
const canCommit = computed(
  () =>
    Boolean(preview.value) &&
    !previewIsStale.value &&
    readyPreviewItems.value.length > 0 &&
    !commitLoading.value,
);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isDocumentCatalog(value: unknown): value is DocumentCatalog {
  if (!isRecord(value) || !Array.isArray(value.documents) || !isRecord(value.retriever)) {
    return false;
  }

  return (
    (value.workspaceName === null || typeof value.workspaceName === "string") &&
    typeof value.retriever.indexedDocumentCount === "number" &&
    Number.isInteger(value.retriever.indexedDocumentCount) &&
    value.retriever.indexedDocumentCount >= 0
  );
}

function isDocumentImportPreview(value: unknown): value is DocumentImportPreview {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    return false;
  }

  return (
    typeof value.contractId === "string" &&
    typeof value.contractVersion === "number" &&
    typeof value.readyCount === "number" &&
    typeof value.skippedCount === "number" &&
    Array.isArray(value.executablePlans) &&
    (value.planDiagnostic === null || typeof value.planDiagnostic === "string")
  );
}

function isDocumentImportResult(value: unknown): value is DocumentImportResult {
  if (!isRecord(value) || !Array.isArray(value.imported) || !Array.isArray(value.skipped)) {
    return false;
  }

  return (
    isRecord(value.retriever) &&
    typeof value.retriever.indexedDocumentCount === "number" &&
    Array.isArray(value.executablePlans) &&
    (value.planDiagnostic === null || typeof value.planDiagnostic === "string")
  );
}

function titleSuggestion(source: DocumentImportSource): string {
  const name = source.displayName.trim();
  const extension = source.extension.trim().replace(/^\./, "");
  if (extension && name.toLowerCase().endsWith(`.${extension.toLowerCase()}`)) {
    return name.slice(0, -(extension.length + 1)) || name;
  }
  return name || "未命名资料";
}

function defaultMetadata(source: DocumentImportSource): DocumentImportMetadata {
  return {
    title: titleSuggestion(source),
    sensitivity: "public",
    businessScope: "general",
    ownerId: null,
    trustLevel: "trusted",
  };
}

function currentFingerprint(): string {
  return JSON.stringify(
    selectedDocuments.value.map(({ source, metadata }) => ({
      sourceId: source.sourceId,
      metadata,
    })),
  );
}

function actorLabel(actorId: string): string {
  const actor = props.actors.find((candidate) => candidate.id === actorId);
  return actor ? `${actor.displayName} · ${actor.role}` : actorId;
}

function authorizationLabel(authorization: DocumentAuthorizationPreview): string {
  return authorization.allowed ? "允许 · allowed" : "拒绝 · denied";
}

function authorizationTone(authorization: DocumentAuthorizationPreview): "success" | "danger" {
  return authorization.allowed ? "success" : "danger";
}

function statusLabel(item: DocumentImportPreviewItem): string {
  if (item.status === "ready") {
    return "READY · 可导入";
  }
  if (item.status === "unsupported") {
    return "UNSUPPORTED · 不支持";
  }
  return "INVALID · 无法读取";
}

function statusTone(item: DocumentImportPreviewItem): "success" | "warning" | "danger" {
  if (item.status === "ready") {
    return "success";
  }
  return item.status === "unsupported" ? "warning" : "danger";
}

function sourceStatusLabel(source: DocumentImportSource): string {
  if (source.status === "ready") {
    return "READY · 可导入";
  }
  if (source.status === "unsupported") {
    return "UNSUPPORTED · 跳过";
  }
  if (source.status === "invalid") {
    return "INVALID · 需处理";
  }
  if (source.diagnostic) {
    return "INVALID · 需处理";
  }
  if ([".txt", ".md", ".pdf", ".docx"].includes(source.extension)) {
    return "待预览";
  }
  return "待预览 · 格式待判定";
}

function sourceStatusTone(source: DocumentImportSource): "success" | "warning" | "danger" | "info" {
  if (source.status === "ready") {
    return "success";
  }
  if (source.status === "unsupported") {
    return "warning";
  }
  return source.diagnostic || source.status === "invalid" ? "danger" : "info";
}

const diagnosticCodeLabels: Record<DocumentImportDiagnosticCode, string> = {
  unsupported_format: "格式不支持",
  invalid_utf8: "不是有效 UTF-8",
  parse_failed: "解析失败",
  encrypted: "文档已加密",
  no_text: "没有可提取文字",
  too_large: "超过大小限制",
  read_failed: "读取失败",
};

function diagnosticLabel(code: string | null | undefined): string {
  if (!code) {
    return "";
  }
  return diagnosticCodeLabels[code as DocumentImportDiagnosticCode] ?? code;
}

async function responseError(response: Response): Promise<DocumentResponseError> {
  let detail = "";
  try {
    const payload: unknown = await response.json();
    if (isRecord(payload) && typeof payload.detail === "string") {
      detail = payload.detail;
    }
  } catch {
    // Status code remains the useful boundary when the body is not JSON.
  }
  return new DocumentResponseError(
    response.status,
    detail,
    response.headers.get("X-AgentAudit-Operation-Id"),
  );
}

function documentTechnicalDetails(error: unknown, fallback: string): string {
  if (error instanceof DocumentResponseError) {
    const operation = error.operationId ? `\noperation ID: ${error.operationId}` : "";
    return `HTTP ${error.status}${operation}\n${error.message}`;
  }
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

async function loadCatalog(): Promise<void> {
  if (catalogLoading.value) {
    return;
  }

  catalogLoading.value = true;
  catalogError.value = "";
  if (documentErrorSource.value === "catalog") {
    documentErrorSource.value = null;
  }
  try {
    const response = await apiFetch("/api/workspace/documents");
    if (!response.ok) {
      throw await responseError(response);
    }
    const payload: unknown = await response.json();
    if (!isDocumentCatalog(payload)) {
      throw new Error("Workspace 文档目录响应格式无效");
    }
    catalog.value = payload;
    emit("catalog", payload);
  } catch (error) {
    catalogError.value = nativeErrorMessage(error, "Workspace 文档目录加载失败");
    documentErrorSource.value = "catalog";
  } finally {
    catalogLoading.value = false;
  }
}

const documentProblem = computed<DocumentProblem | null>(() => {
  switch (documentErrorSource.value) {
    case "catalog":
      return catalogError.value
        ? {
            stage: "读取资料目录",
            title: "当前资料目录没有读完",
            reason: "本地 Workspace 的资料目录暂时无法读取。",
            impact: "还不能确认哪些资料已经进入索引；不会自动扫描其他文件。",
            actionLabel: "重新读取目录",
            action: "catalog",
            technicalDetails: documentTechnicalDetails(catalogError.value, "资料目录读取失败"),
            tone: "warning",
          }
        : null;
    case "selection":
      return previewError.value
        ? {
            stage: "选择业务资料",
            title: "这次资料选择没有完成",
            reason: `系统没有读完你刚选择的资料：${previewError.value}`,
            impact: "本次没有资料进入待预览列表，也不会写入 Workspace。",
            actionLabel: "重新选择资料",
            action: "pick",
            technicalDetails: documentTechnicalDetails(previewError.value, "资料选择失败"),
          }
        : null;
    case "preview":
      return previewError.value
        ? {
            stage: "生成授权预览",
            title: "资料预览没有生成",
            reason: "当前选择的资料还没有完成格式与权限预览。",
            impact: "资料不会被导入，需先完成预览后才能确认。",
            actionLabel: "重新生成预览",
            action: "preview",
            technicalDetails: documentTechnicalDetails(previewError.value, "资料预览失败"),
          }
        : null;
    case "commit":
      return commitError.value
        ? {
            stage: "确认导入",
            title: "资料还没有导入",
            reason: "这次导入没有完成，当前 Workspace 不会新增这批资料。",
            impact: "权限规则和检查计划不会基于这批资料更新。",
            actionLabel: "重新确认导入",
            action: "commit",
            technicalDetails: documentTechnicalDetails(commitError.value, "资料导入失败"),
          }
        : null;
    default:
      return null;
  }
});

async function resolveDocumentProblem(): Promise<void> {
  const problem = documentProblem.value;
  if (!problem) {
    return;
  }

  switch (problem.action) {
    case "catalog":
      await loadCatalog();
      return;
    case "pick":
      await pickDocuments(lastSelectionMode.value);
      return;
    case "preview":
      await requestPreview();
      return;
    case "commit":
      await commitImport();
      return;
  }
}

async function pickDocuments(mode: "files" | "folder"): Promise<void> {
  if (selectionLoading.value || previewLoading.value || commitLoading.value) {
    return;
  }

  selectionLoading.value = mode;
  lastSelectionMode.value = mode;
  selectionNotice.value = "";
  previewError.value = "";
  commitError.value = "";
  documentErrorSource.value = null;
  try {
    const sources = mode === "files" ? await selectDocumentFiles() : await selectDocumentFolder();
    if (sources.length === 0) {
      selectionNotice.value = "没有加入新的资料；如果刚选择的是文件夹，请确认其中包含 PDF、DOCX、TXT 或 MD。";
      return;
    }

    selectedDocuments.value = sources.map((source) => ({
      source,
      metadata: defaultMetadata(source),
    }));
    metadataConfirmed.value = false;
    preview.value = null;
    previewFingerprint.value = "";
    importResult.value = null;
    selectionNotice.value = `已选择 ${sources.length} 项；请核对每项元数据后生成 Preview。`;
  } catch (error) {
    selectionNotice.value = "";
    previewError.value = nativeErrorMessage(error, "无法读取所选资料");
    documentErrorSource.value = "selection";
  } finally {
    selectionLoading.value = "";
  }
}

function invalidatePreview(): void {
  preview.value = null;
  previewFingerprint.value = "";
  importResult.value = null;
  previewError.value = "";
  commitError.value = "";
  documentErrorSource.value = null;
}

function applyBatchMetadata(
  field: "businessScope" | "sensitivity" | "ownerId",
  value: string,
): void {
  if (!value || selectedDocuments.value.length === 0) {
    return;
  }
  const nextValue = field === "ownerId" && value === "__none__" ? null : value;
  selectedDocuments.value = selectedDocuments.value.map((draft) => ({
    ...draft,
    metadata: {
      ...draft.metadata,
      [field]: nextValue,
    },
  }));
  if (field === "businessScope") {
    batchBusinessScope.value = "";
  } else if (field === "sensitivity") {
    batchSensitivity.value = "";
  } else {
    batchOwnerId.value = "";
  }
  invalidatePreview();
  selectionNotice.value = `已将${field === "businessScope" ? "资料类别" : field === "sensitivity" ? "敏感等级" : "Owner"}应用到 ${selectedDocuments.value.length} 项；仍可在下方修改例外项。`;
}

function removeDocument(sourceId: string): void {
  if (selectionLoading.value || previewLoading.value || commitLoading.value) {
    return;
  }
  selectedDocuments.value = selectedDocuments.value.filter(
    (draft) => draft.source.sourceId !== sourceId,
  );
  invalidatePreview();
  selectionNotice.value = "已移除一项；没有写入 Workspace。请重新生成 Preview。";
}

function cancelSelection(): void {
  if (selectionLoading.value || previewLoading.value || commitLoading.value) {
    return;
  }
  selectedDocuments.value = [];
  metadataConfirmed.value = false;
  preview.value = null;
  previewFingerprint.value = "";
  importResult.value = null;
  selectionNotice.value = "已清空本次导入选择；没有写入 Workspace。";
  previewError.value = "";
  commitError.value = "";
  documentErrorSource.value = null;
}

async function requestPreview(): Promise<void> {
  if (!canPreview.value) {
    return;
  }

  previewLoading.value = true;
  previewError.value = "";
  commitError.value = "";
  documentErrorSource.value = null;
  try {
    const response = await apiFetch("/api/document-imports/previews", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ documents: selectedDocuments.value }),
    });
    if (!response.ok) {
      throw await responseError(response);
    }
    const payload: unknown = await response.json();
    if (!isDocumentImportPreview(payload)) {
      throw new Error("Document Import Preview 响应格式无效");
    }
    preview.value = payload;
    previewFingerprint.value = currentFingerprint();
  } catch (error) {
    preview.value = null;
    previewFingerprint.value = "";
    previewError.value = nativeErrorMessage(error, "资料解析 Preview 失败");
    documentErrorSource.value = "preview";
  } finally {
    previewLoading.value = false;
  }
}

async function commitImport(): Promise<void> {
  if (!canCommit.value || !preview.value) {
    return;
  }

  commitLoading.value = true;
  commitError.value = "";
  documentErrorSource.value = null;
  try {
    // Send the complete reviewed selection. The backend recomputes each
    // source boundary and returns imported + skipped items for the result;
    // filtering here would hide unsupported or unreadable files.
    const documents = [...selectedDocuments.value];
    const response = await apiFetch("/api/document-imports", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ documents }),
    });
    if (!response.ok) {
      throw await responseError(response);
    }
    const payload: unknown = await response.json();
    if (!isDocumentImportResult(payload)) {
      throw new Error("Document Import 响应格式无效");
    }

    importResult.value = payload;
    selectedDocuments.value = [];
    metadataConfirmed.value = false;
    preview.value = null;
    previewFingerprint.value = "";
    expanded.value = false;
    selectionNotice.value = `已导入 ${payload.imported.length} 项；Retriever 已更新，无需重启。`;
    emit("imported", payload);
    await loadCatalog();
  } catch (error) {
    commitError.value = nativeErrorMessage(error, "资料导入失败");
    documentErrorSource.value = "commit";
  } finally {
    commitLoading.value = false;
  }
}

onMounted(() => {
  void loadCatalog();
});

watch(
  selectedDocuments,
  () => {
    metadataConfirmed.value = false;
  },
  { deep: true },
);
</script>

<template>
  <section
    class="document-import"
    :class="{ 'document-import--expanded': expanded }"
    aria-labelledby="document-import-title"
    data-testid="document-import"
  >
    <div class="document-import-heading">
      <div>
        <p class="section-kicker">准备步骤 · 资料</p>
        <h2 id="document-import-title">添加业务资料</h2>
        <p class="document-import-subtitle">
          选择文档 → 核对角色与访问范围 → 确认导入。RAG 检索只使用进入本地资料库的内容。
        </p>
      </div>
      <div v-if="expanded" class="document-import-heading-meta">
        <el-tag type="info" effect="plain">本地快照</el-tag>
        <span>{{ catalog?.retriever.indexedDocumentCount ?? "—" }} 份已索引</span>
      </div>
    </div>

    <el-card class="document-import-card" shadow="never">
      <UserProblemCard
        v-if="documentProblem?.action === 'catalog'"
        class="document-import-alert"
        data-testid="document-catalog-error"
        :problem="documentProblem"
        action-test-id="document-problem-action"
        @action="resolveDocumentProblem"
      />

      <div v-if="!expanded" class="document-import-summary" data-testid="document-import-summary">
        <div class="document-import-summary-copy">
          <span class="document-import-label">当前资料库</span>
          <div class="document-import-summary-primary">
            <strong>{{ catalog?.workspaceName ?? "默认资料库" }}</strong>
            <p class="document-import-summary-facts">
              {{ catalog?.documents.length ?? 0 }} 份资料 ·
              已索引 {{ catalog?.retriever.indexedDocumentCount ?? "—" }} 份
            </p>
          </div>
        </div>
        <el-button
          class="document-import-summary-action"
          data-testid="document-import-open"
          :aria-expanded="expanded"
          @click="expanded = true"
        >
          添加 / 管理资料
        </el-button>
      </div>
      <p v-if="!expanded && catalogLoading" class="document-import-summary-loading" data-testid="document-catalog-loading">
        正在读取当前 Workspace 文档目录…
      </p>

      <template v-if="expanded">
        <div class="document-import-actions">
          <div>
            <strong>添加 AI 会检索的业务文档</strong>
            <p>支持 PDF、DOCX、UTF-8 TXT、MD；只在本机提取文字，导入为可移动快照。</p>
            <p>每批最多 50 项；单文件原始大小 ≤ 20 MiB、提取后文字 ≤ 2 MiB，超限会逐项说明。</p>
          </div>
          <div class="document-import-action-buttons">
            <el-button
              type="primary"
              data-testid="document-import-files"
              :loading="selectionLoading === 'files'"
              :disabled="Boolean(selectionLoading || previewLoading || commitLoading)"
              @click="pickDocuments('files')"
            >
              选择文件（推荐）
            </el-button>
            <el-button
              plain
              data-testid="document-import-folder"
              :loading="selectionLoading === 'folder'"
              :disabled="Boolean(selectionLoading || previewLoading || commitLoading)"
              @click="pickDocuments('folder')"
            >
              选择文件夹（批量）
            </el-button>
            <el-button
              class="document-import-collapse"
              data-testid="document-import-collapse"
              text
              :disabled="Boolean(selectionLoading || previewLoading || commitLoading)"
              @click="expanded = false"
            >
              收起
            </el-button>
          </div>
        </div>

        <details class="document-import-boundary">
          <summary><span class="document-import-dot" aria-hidden="true"></span>应该 / 不应该导入什么？</summary>
          <div class="document-import-boundary-copy">
            <p><strong>应该：</strong>产品说明、公开 FAQ、员工手册、操作流程、客户合同、服务记录、预算和审批文件。</p>
            <p><strong>不应该：</strong>模型文件或安装目录、项目源码、API Key、数据库文件、软件自己的 Workspace。</p>
            <p>桌面端使用原生选择器，只读取你本次选中的文件；不会静默扫描电脑或局域网。文件夹中的其他格式会逐项跳过。</p>
          </div>
        </details>

        <UserProblemCard
          v-if="documentProblem && documentProblem.action !== 'catalog'"
          class="document-import-alert"
          data-testid="document-import-error"
          :problem="documentProblem"
          action-test-id="document-problem-action"
          @action="resolveDocumentProblem"
        />
        <p v-if="selectionNotice" class="document-import-notice" data-testid="document-import-notice">
          {{ selectionNotice }}
        </p>

        <div v-if="catalogLoading" class="document-import-loading" data-testid="document-catalog-loading">
          <el-skeleton :rows="2" animated />
          <p>正在读取当前 Workspace 文档目录…</p>
        </div>
        <div v-else class="document-catalog" data-testid="document-catalog">
          <div class="document-catalog-heading">
            <div>
              <span class="document-import-label">当前 Workspace</span>
              <strong>{{ catalog?.workspaceName ?? "默认 Workspace" }}</strong>
            </div>
            <span>{{ catalog?.documents.length ?? 0 }} documents · {{ catalog?.retriever.engineId ?? "—" }}</span>
          </div>
          <ul v-if="catalog && catalog.documents.length > 0" class="document-catalog-list">
            <li v-for="document in catalog.documents" :key="document.id">
              <div>
                <strong>{{ document.title }}</strong>
                <code>{{ document.id }}</code>
              </div>
              <span>{{ document.labels.join(" · ") || "无标签" }}</span>
            </li>
          </ul>
          <p v-else class="document-catalog-empty">当前 Workspace 还没有文档。</p>
        </div>

      <div v-if="selectedDocuments.length > 0" class="document-selection" data-testid="document-import-selection">
        <div class="document-selection-heading">
          <div>
            <span class="document-import-label">待导入资料</span>
            <h3>核对 {{ selectedDocumentCount }} 项资料</h3>
            <p>先批量确认资料类别、角色 / 部门范围、敏感等级和 Owner，再修改例外项。</p>
          </div>
          <el-button
            data-testid="document-import-cancel"
            text
            :disabled="Boolean(selectionLoading || previewLoading || commitLoading)"
            @click="cancelSelection"
          >
            取消本次选择
          </el-button>
        </div>

        <div class="document-batch-controls" data-testid="document-import-batch-controls">
          <label>
            <span>批量资料类别 / 角色部门</span>
            <el-select v-model="batchBusinessScope" aria-label="批量资料类别">
              <el-option label="选择类别" value="" />
              <el-option
                v-for="(label, value) in businessScopeLabels"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
          </label>
          <el-button
            plain
            :disabled="!batchBusinessScope"
            @click="applyBatchMetadata('businessScope', batchBusinessScope)"
          >
            应用类别
          </el-button>
          <label>
            <span>批量敏感等级</span>
            <el-select v-model="batchSensitivity" aria-label="批量敏感等级">
              <el-option label="选择等级" value="" />
              <el-option
                v-for="(label, value) in sensitivityLabels"
                :key="value"
                :label="label"
                :value="value"
              />
            </el-select>
          </label>
          <el-button
            plain
            :disabled="!batchSensitivity"
            @click="applyBatchMetadata('sensitivity', batchSensitivity)"
          >
            应用等级
          </el-button>
          <label>
            <span>批量 Owner（角色 / 部门）</span>
            <el-select v-model="batchOwnerId" clearable aria-label="批量 Owner">
              <el-option label="选择 Owner" value="" />
              <el-option label="无特定 Owner" value="__none__" />
              <el-option
                v-for="actor in actors"
                :key="actor.id"
                :label="actorLabel(actor.id)"
                :value="actor.id"
              />
            </el-select>
          </label>
          <el-button
            plain
            :disabled="!batchOwnerId"
            @click="applyBatchMetadata('ownerId', batchOwnerId)"
          >
            应用 Owner
          </el-button>
        </div>

        <div class="document-selection-list">
          <article
            v-for="draft in selectedDocuments"
            :key="draft.source.sourceId"
            class="document-selection-item"
            data-testid="document-import-item"
          >
            <div class="document-selection-source">
              <div>
                <strong>{{ draft.source.displayName }}</strong>
                <code>{{ draft.source.relativePath }}</code>
              </div>
              <div class="document-selection-source-actions">
                <el-tag :type="sourceStatusTone(draft.source)" effect="plain" size="small">
                  {{ sourceStatusLabel(draft.source) }}
                </el-tag>
                <el-button
                  text
                  size="small"
                  :disabled="Boolean(selectionLoading || previewLoading || commitLoading)"
                  @click="removeDocument(draft.source.sourceId)"
                >
                  移除
                </el-button>
              </div>
            </div>
            <div class="document-metadata-grid">
              <label>
                <span>标题 Title</span>
                <el-input v-model="draft.metadata.title" aria-label="资料标题" />
              </label>
              <label>
                <span>敏感等级</span>
                <el-select v-model="draft.metadata.sensitivity" aria-label="资料敏感等级">
                  <el-option
                    v-for="(label, value) in sensitivityLabels"
                    :key="value"
                    :label="label"
                    :value="value"
                  />
                </el-select>
              </label>
              <label>
                <span>资料类别 / 角色或部门范围</span>
                <el-select v-model="draft.metadata.businessScope" aria-label="资料业务范围">
                  <el-option
                    v-for="(label, value) in businessScopeLabels"
                    :key="value"
                    :label="label"
                    :value="value"
                  />
                </el-select>
              </label>
              <label>
                <span>Owner（角色 / 部门）</span>
                <el-select v-model="draft.metadata.ownerId" clearable aria-label="资料 Owner">
                  <el-option label="无特定 Owner" :value="null" />
                  <el-option
                    v-for="actor in actors"
                    :key="actor.id"
                    :label="actorLabel(actor.id)"
                    :value="actor.id"
                  />
                </el-select>
              </label>
              <label>
                <span>来源可信度</span>
                <details class="document-advanced-field">
                  <summary>技术选项</summary>
                  <el-select v-model="draft.metadata.trustLevel" aria-label="资料来源可信度">
                    <el-option
                      v-for="(label, value) in trustLevelLabels"
                      :key="value"
                      :label="label"
                      :value="value"
                    />
                  </el-select>
                </details>
              </label>
            </div>
            <p v-if="draft.source.diagnostic" class="document-selection-diagnostic" role="alert">
              <strong v-if="draft.source.diagnosticCode">{{ diagnosticLabel(draft.source.diagnosticCode) }}：</strong>
              {{ draft.source.diagnostic }}
            </p>
          </article>
        </div>

        <div class="document-selection-footer">
          <div class="document-selection-confirmation">
            <el-checkbox v-model="metadataConfirmed" data-testid="document-import-metadata-confirmed">
              我已核对本批资料的类别、角色 / 部门范围、敏感等级和 Owner
            </el-checkbox>
            <details class="document-import-technical-details">
              <summary>核对哪些字段？</summary>
              <span>普通层确认标题、资料类别/角色或部门范围、敏感等级和 Owner；Advanced 可调整来源可信度。Preview 只读取 active Contract，不调用模型，也不会修改 Workspace。</span>
            </details>
          </div>
          <el-button
            data-testid="document-import-preview-submit"
            type="primary"
            :loading="previewLoading"
            :disabled="!canPreview"
            @click="requestPreview"
          >
            {{ previewLoading ? "Preview 中" : "生成授权 Preview" }}
          </el-button>
        </div>
      </div>

      <div v-if="preview" class="document-preview" data-testid="document-import-preview">
        <div class="document-preview-heading">
          <div>
            <span class="document-import-label">授权预览</span>
            <h3>导入前影响</h3>
          </div>
          <div class="document-preview-counts">
            <el-tag type="success" effect="plain">{{ preview.readyCount }} ready</el-tag>
            <el-tag v-if="preview.skippedCount > 0" type="warning" effect="plain">
              {{ preview.skippedCount }} skipped
            </el-tag>
          </div>
        </div>

        <el-alert
          v-if="previewIsStale"
          class="document-import-alert"
          data-testid="document-import-preview-stale"
          title="元数据已变化，请重新生成 Preview 后才能确认导入。"
          type="warning"
          :closable="false"
        />

        <div class="document-preview-list">
          <article
            v-for="item in preview.items"
            :key="item.sourceId"
            class="document-preview-item"
            :class="`is-${item.status}`"
            data-testid="document-import-preview-item"
          >
            <div class="document-preview-item-heading">
              <div>
                <strong>{{ item.titleSuggestion }}</strong>
                <code>{{ item.relativePath }}</code>
              </div>
              <el-tag :type="statusTone(item)" effect="plain" size="small">
                {{ statusLabel(item) }}
              </el-tag>
            </div>
            <p v-if="item.diagnostic" class="document-selection-diagnostic">{{ item.diagnostic }}</p>
            <p v-else-if="item.contentPreview" class="document-content-preview">{{ item.contentPreview }}</p>
            <div v-if="item.status === 'ready'" class="document-authorization">
              <div class="document-authorization-heading">
                <span>按 Contract 计算授权</span>
                <code>v{{ preview.contractVersion }}</code>
              </div>
              <ul>
                <li v-for="authorization in item.authorization" :key="authorization.actorId">
                  <span>{{ actorLabel(authorization.actorId) }}</span>
                  <el-tag :type="authorizationTone(authorization)" effect="plain" size="small">
                    {{ authorizationLabel(authorization) }}
                  </el-tag>
                  <code>{{ authorization.ruleId ?? "default deny" }}</code>
                </li>
              </ul>
            </div>
          </article>
        </div>

        <div class="document-preview-footer">
          <p>Contract <code>{{ preview.contractId }} · v{{ preview.contractVersion }}</code></p>
          <el-button
            data-testid="document-import-confirm"
            type="primary"
            :loading="commitLoading"
            :disabled="!canCommit"
            @click="commitImport"
          >
            {{ commitLoading ? "导入中" : "确认导入到 Workspace" }}
          </el-button>
        </div>
      </div>

      </template>

      <div v-if="importResult" class="document-import-result" data-testid="document-import-result">
        <div>
          <span class="document-import-label">导入结果</span>
          <h3>资料已进入本地快照</h3>
          <p>
            成功 {{ importResult.imported.length }} 项；跳过 {{ importResult.skipped.length }} 项；Retriever 当前索引
            {{ importResult.retriever.indexedDocumentCount }} 项。
          </p>
          <ul v-if="importResult.skipped.length > 0" class="document-import-skipped-list">
            <li v-for="item in importResult.skipped" :key="item.sourceId">
              <strong>{{ item.displayName }}</strong>
              <span>{{ item.diagnostic }}</span>
            </li>
          </ul>
        </div>
        <el-tag type="success" effect="plain">无需重启</el-tag>
        <div class="document-import-next-step" data-testid="document-import-next-step">
          <div>
            <span class="document-import-label">下一步</span>
            <strong v-if="importResult.executablePlans.length">
              已根据当前 Contract 派生 {{ importResult.executablePlans.length }} 条真实检查计划
            </strong>
            <strong v-else>暂时没有可执行的 Contract-derived Plan</strong>
            <p v-if="importResult.planDiagnostic">{{ importResult.planDiagnostic }}</p>
            <p v-else>选择一条计划，运行 Guided Audit；结果会产生真实 Trace、Finding 与 Replay。</p>
          </div>
          <div v-if="importResult.executablePlans.length" class="document-import-plan-actions">
            <div v-for="plan in importResult.executablePlans" :key="plan.id" class="document-import-plan">
              <div>
                <strong>{{ plan.name }}</strong>
                <p>{{ plan.description }}</p>
                <code>{{ plan.id }} · {{ plan.basisRuleId }}</code>
              </div>
              <el-button
                type="primary"
                size="small"
                data-testid="document-import-run-plan"
                @click="emit('start-guided-audit', plan.id)"
              >
                运行此 Guided Audit
              </el-button>
            </div>
          </div>
          <el-button
            v-else
            plain
            data-testid="document-import-open-contract"
            @click="emit('open-contract')"
          >
            返回 Contract Preview
          </el-button>
        </div>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.document-import {
  width: min(1080px, 100%);
  margin: 30px auto 42px;
}

.document-import--expanded {
  width: 100%;
  max-width: var(--layout-reading-max, 1440px);
}

.document-import-heading,
.document-import-actions,
.document-selection-heading,
.document-preview-heading,
.document-preview-footer,
.document-import-result {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.document-import-heading {
  align-items: flex-end;
  margin-bottom: 12px;
}

.document-import-heading h2,
.document-selection-heading h3,
.document-preview-heading h3,
.document-import-result h3 {
  margin: 7px 0 0;
  color: var(--ink-strong);
  font-size: var(--type-section-title-size, 23px);
  font-weight: 600;
  letter-spacing: -0.02em;
}

.document-import-subtitle {
  margin: 8px 0 0;
  color: var(--type-body-small-color, var(--ink-muted));
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.6);
}

.document-import-heading-meta,
.document-preview-counts {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
  white-space: nowrap;
}

.document-import-card.el-card {
  overflow: hidden;
  color: var(--ink);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  box-shadow: 0 8px 24px rgba(21, 50, 80, 0.07);
}

.document-import-card :deep(.el-card__body) {
  padding: 16px 20px;
}

.document-import--expanded .document-import-card :deep(.el-card__body) {
  padding: 24px 26px;
}

.document-import-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  min-height: 54px;
  padding-left: 16px;
  border-left: 3px solid rgba(73, 122, 255, 0.34);
}

.document-import-summary-copy {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.document-import-summary-primary {
  display: flex;
  align-items: baseline;
  min-width: 0;
  flex-wrap: wrap;
  gap: 5px 14px;
}

.document-import-summary-primary > strong {
  overflow: hidden;
  color: var(--ink-strong);
  font-size: var(--type-card-title-size, 18px);
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-import-summary-facts,
.document-import-summary-loading {
  margin: 0;
  color: var(--ink-muted);
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.document-import-summary-loading {
  margin-top: 12px;
  color: var(--ink-faint);
}

.document-import-summary-action.el-button {
  flex-shrink: 0;
  min-height: 40px;
  margin: 0;
  color: var(--action-blue, #497aff);
  background: transparent;
  border-color: rgba(73, 122, 255, 0.34);
  font-size: var(--type-body-small-size, 14px);
  font-weight: 650;
}

.document-import-summary-action.el-button:hover:not(.is-disabled),
.document-import-summary-action.el-button:focus-visible {
  color: #315ddc;
  background: rgba(73, 122, 255, 0.07);
  border-color: rgba(73, 122, 255, 0.56);
}

.document-import-actions {
  align-items: center;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--line);
}

.document-import-actions strong {
  color: var(--ink-strong);
  font-size: 14px;
}

.document-import-actions p,
.document-selection-footer p,
.document-preview-footer p,
.document-import-result p {
  margin: 7px 0 0;
  color: var(--ink-muted);
  font-size: 11px;
  line-height: 1.6;
}

.document-import-action-buttons {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
}

.document-import-action-buttons .el-button,
.document-selection-footer .el-button,
.document-preview-footer .el-button {
  margin: 0;
}

.document-import-boundary {
  margin: 16px 0 0;
  color: var(--ink-muted);
  font-size: 11px;
  line-height: 1.5;
}

.document-import-boundary summary {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  color: var(--action-blue, #4f7cff);
  cursor: pointer;
}

.document-import-boundary > span {
  display: block;
  margin-top: 6px;
  color: var(--ink-muted);
}

.document-import-boundary-copy {
  margin-top: 7px;
  color: var(--ink-muted);
}

.document-import-boundary-copy p {
  margin: 5px 0 0;
}

.document-import-boundary-copy strong {
  color: var(--ink);
  font-weight: 600;
}

.document-import-dot {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
  background: var(--accent);
  border-radius: 50%;
}

.document-import-alert.el-alert {
  min-height: 36px;
  margin-top: 16px;
  border: 1px solid var(--line);
}

.document-import-alert :deep(.el-alert__title) {
  font-size: 12px;
  line-height: 1.4;
}

.document-import-notice {
  margin: 15px 0 0;
  padding: 11px 13px;
  color: #087f73;
  background: #e9fbf7;
  border: 1px solid rgba(37, 191, 174, 0.28);
  border-radius: 7px;
  font-size: 11px;
  line-height: 1.5;
}

.document-import-loading {
  margin-top: 20px;
  color: var(--ink-muted);
}

.document-import-loading p {
  margin: 10px 0 0;
  font-size: 11px;
}

.document-catalog {
  margin-top: 20px;
  padding: 15px 16px;
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line);
  border-radius: 9px;
}

.document-catalog-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.document-catalog-heading > div {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.document-catalog-heading strong {
  color: var(--ink-strong);
  font-family: inherit;
  font-size: 11px;
}

.document-import-label {
  color: var(--evidence-teal, #25bfae);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  letter-spacing: 0.1em;
}

.document-catalog-list,
.document-authorization ul {
  display: grid;
  gap: 7px;
  margin: 13px 0 0;
  padding: 0;
  list-style: none;
}

.document-catalog-list li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-top: 9px;
  border-top: 1px solid var(--line);
  color: var(--ink-faint);
  font-size: 10px;
}

.document-catalog-list li > div {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 9px;
}

.document-catalog-list strong {
  overflow: hidden;
  color: var(--ink);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-catalog-list code,
.document-selection-source code,
.document-preview-item-heading code,
.document-preview-footer code {
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
}

.document-catalog-empty {
  margin: 14px 0 0;
  color: var(--ink-faint);
  font-size: 11px;
}

.document-selection,
.document-preview {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
}

.document-selection-heading,
.document-preview-heading {
  align-items: center;
}

.document-selection-heading h3,
.document-preview-heading h3,
.document-import-result h3 {
  font-size: 16px;
}

.document-selection-heading p {
  margin: 6px 0 0;
  color: var(--ink-muted);
  font-size: 11px;
  line-height: 1.5;
}

.document-batch-controls {
  display: grid;
  grid-template-columns: minmax(130px, 1fr) auto minmax(130px, 1fr) auto minmax(130px, 1fr) auto;
  gap: 8px;
  align-items: end;
  margin-top: 15px;
  padding: 12px;
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line);
  border-radius: 9px;
}

.document-batch-controls label {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.document-batch-controls label > span {
  color: var(--ink-faint);
  font-size: 10px;
}

.document-batch-controls :deep(.el-select__wrapper) {
  min-height: 34px;
  color: var(--ink-strong);
  background: var(--surface, #ffffff);
  border: 1px solid var(--line);
  box-shadow: none;
}

.document-batch-controls :deep(.el-select__selected-item) {
  color: var(--ink-strong);
  font-size: 11px;
}

.document-batch-controls .el-button {
  margin: 0;
}

.document-selection-list,
.document-preview-list {
  display: grid;
  gap: 10px;
  margin-top: 15px;
}

.document-selection-item,
.document-preview-item {
  padding: 14px 15px;
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line);
  border-radius: 9px;
}

.document-selection-source,
.document-preview-item-heading,
.document-authorization-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.document-selection-source > div,
.document-preview-item-heading > div {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.document-selection-source-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 5px;
}

.document-selection-source-actions .el-button {
  margin: 0;
  color: var(--risk-coral, #b43f3f);
  font-size: 10px;
}

.document-selection-source strong,
.document-preview-item-heading strong {
  color: var(--ink-strong);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.document-metadata-grid {
  display: grid;
  grid-template-columns: minmax(150px, 1.3fr) repeat(4, minmax(110px, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.document-metadata-grid label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.document-metadata-grid label > span {
  color: var(--ink-faint);
  font-size: 10px;
}

.document-metadata-grid :deep(.el-input__wrapper),
.document-metadata-grid :deep(.el-select__wrapper) {
  min-height: 34px;
  color: var(--ink-strong);
  background: var(--surface, #ffffff);
  border: 1px solid var(--line);
  box-shadow: none;
}

.document-metadata-grid :deep(.el-input__inner),
.document-metadata-grid :deep(.el-select__selected-item) {
  color: var(--ink-strong);
  font-size: 11px;
}

.document-selection-diagnostic {
  margin: 12px 0 0;
  color: var(--risk-coral, #b43f3f);
  font-size: 11px;
  line-height: 1.5;
}

.document-selection-diagnostic strong {
  font-weight: 600;
}

.document-advanced-field {
  display: grid;
  gap: 7px;
}

.document-advanced-field summary {
  width: fit-content;
  color: var(--action-blue, #4f7cff);
  cursor: pointer;
  font-size: 10px;
}

.document-selection-footer,
.document-preview-footer {
  align-items: center;
  margin-top: 15px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.document-selection-confirmation {
  min-width: 0;
}

.document-selection-confirmation :deep(.el-checkbox) {
  height: auto;
  margin: 0;
  color: var(--ink);
  white-space: normal;
}

.document-selection-confirmation :deep(.el-checkbox__label) {
  color: var(--ink);
  font-size: 11px;
  line-height: 1.5;
  white-space: normal;
}

.document-selection-confirmation p {
  margin-top: 6px;
}

.document-import-technical-details {
  margin-top: 6px;
  color: var(--ink-muted);
  font-size: 10px;
  line-height: 1.5;
}

.document-import-technical-details summary {
  width: fit-content;
  color: var(--action-blue, #4f7cff);
  cursor: pointer;
}

.document-import-technical-details > span {
  display: block;
  margin-top: 5px;
}

.document-selection-footer p,
.document-preview-footer p {
  margin: 0;
}

.document-preview-item.is-unsupported {
  border-color: rgba(251, 191, 36, 0.2);
}

.document-preview-item.is-invalid {
  border-color: rgba(248, 113, 113, 0.24);
}

.document-content-preview {
  max-height: 80px;
  margin: 12px 0 0;
  padding: 10px 12px;
  overflow: hidden;
  color: var(--ink-muted);
  background: var(--surface, #ffffff);
  border-radius: 6px;
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.document-authorization {
  margin-top: 13px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.document-authorization-heading {
  align-items: center;
  color: var(--ink-muted);
  font-size: 10px;
}

.document-authorization-heading code {
  color: var(--accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.document-authorization ul {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.document-authorization li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 6px 8px;
  align-items: center;
  padding: 8px 9px;
  border: 1px solid var(--line);
  border-radius: 6px;
}

.document-authorization li > span {
  min-width: 0;
  overflow: hidden;
  color: var(--ink);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-authorization li > code {
  grid-column: 1 / -1;
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
}

.document-import-result {
  align-items: center;
  margin-top: 20px;
  padding: 15px 16px;
  background: #e9fbf7;
  border: 1px solid rgba(37, 191, 174, 0.28);
  border-radius: 9px;
}

.document-import-result h3 {
  margin-top: 5px;
}

.document-import-result p {
  margin-top: 6px;
}

.document-import-skipped-list {
  display: grid;
  gap: 5px;
  margin: 11px 0 0;
  padding: 0;
  color: var(--risk-coral, #b43f3f);
  font-size: 10px;
  list-style: none;
}

.document-import-skipped-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.document-import-skipped-list strong {
  color: var(--ink);
  font-weight: 600;
}

.document-import-next-step {
  display: grid;
  flex: 1 1 100%;
  gap: 12px;
  width: 100%;
  margin-top: 15px;
  padding-top: 14px;
  border-top: 1px solid rgba(37, 191, 174, 0.28);
}

.document-import-next-step > div:first-child {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.document-import-next-step > div:first-child > strong {
  color: var(--ink-strong);
  font-size: 13px;
}

.document-import-next-step .document-import-label {
  display: block;
}

.document-import-plan-actions {
  display: grid;
  gap: 8px;
}

.document-import-plan {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 11px;
  background: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(37, 191, 174, 0.24);
  border-radius: 7px;
}

.document-import-plan > div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.document-import-plan strong {
  color: var(--ink-strong);
  font-size: 11px;
}

.document-import-plan p {
  margin: 0;
  overflow-wrap: anywhere;
}

.document-import-plan code {
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
}

.document-import-plan .el-button {
  flex-shrink: 0;
  margin: 0;
}

@media (max-width: 760px) {
  .document-import,
  .document-import--expanded {
    width: 100%;
    margin: 22px auto 32px;
  }

  .document-import-heading,
  .document-import-actions,
  .document-selection-heading,
  .document-preview-heading,
  .document-selection-footer,
  .document-preview-footer,
  .document-import-result {
    align-items: stretch;
    flex-direction: column;
  }

  .document-import-heading-meta,
  .document-preview-counts {
    justify-content: space-between;
  }

  .document-import-summary {
    align-items: stretch;
    flex-direction: column;
    min-height: 0;
    padding-left: 12px;
  }

  .document-import-summary .el-button {
    width: 100%;
    margin: 0;
  }

  .document-import-action-buttons {
    display: grid;
    grid-template-columns: 1fr 1fr;
    width: 100%;
  }

  .document-import-action-buttons .el-button,
  .document-selection-footer .el-button,
  .document-preview-footer .el-button {
    width: 100%;
  }

  .document-import-action-buttons .document-import-collapse {
    grid-column: 1 / -1;
  }

  .document-catalog-heading,
  .document-catalog-list li {
    align-items: flex-start;
    flex-direction: column;
  }

  .document-metadata-grid {
    grid-template-columns: 1fr 1fr;
  }

  .document-batch-controls {
    grid-template-columns: 1fr auto;
  }

  .document-batch-controls label {
    grid-column: 1 / -1;
  }

  .document-batch-controls .el-button {
    width: 100%;
  }

  .document-metadata-grid label:first-child {
    grid-column: 1 / -1;
  }

  .document-authorization ul {
    grid-template-columns: 1fr;
  }

  .document-import-plan {
    align-items: stretch;
    flex-direction: column;
  }

  .document-import-plan .el-button {
    width: 100%;
  }
}

/* F-060: keep the default import path readable while leaving IDs and raw
 * payloads in their existing technical/evidence presentation. */
.document-import-heading-meta,
.document-preview-counts,
.document-import-label,
.document-catalog-heading,
.document-batch-controls label > span,
.document-metadata-grid label > span,
.document-advanced-field summary,
.document-import-technical-details,
.document-authorization-heading,
.document-import-next-step .document-import-label {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
  letter-spacing: normal;
}

.document-import-actions p,
.document-import-boundary,
.document-import-boundary-copy,
.document-selection-heading p,
.document-selection-footer p,
.document-preview-footer p,
.document-import-result p,
.document-selection-diagnostic,
.document-content-preview,
.document-import-notice {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.document-catalog-heading strong,
.document-catalog-list li,
.document-catalog-list strong,
.document-catalog-empty,
.document-selection-source strong,
.document-preview-item-heading strong,
.document-selection-source-actions .el-button,
.document-authorization li > span,
.document-import-skipped-list,
.document-import-plan strong {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.document-import-label {
  color: var(--evidence-teal-strong, #08786e);
}

.document-import-card .document-import-alert.user-problem-card {
  margin-top: 12px;
}

.document-selection-confirmation :deep(.el-checkbox__label),
.document-batch-controls :deep(.el-select__selected-item),
.document-metadata-grid :deep(.el-input__inner),
.document-metadata-grid :deep(.el-select__selected-item) {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

/* F-062: document management stays an open work surface. The catalog and
   item rows remain distinct through dividers, without stacking card shells. */
.document-import .section-kicker {
  color: var(--ink-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.document-import-card.el-card {
  border-radius: 10px;
  box-shadow: none;
}

.document-import-card :deep(.el-card__body) {
  padding: 18px 22px;
}

.document-import--expanded .document-import-card :deep(.el-card__body) {
  padding: 22px 26px;
}

.document-catalog {
  padding-right: 0;
  padding-left: 0;
  background: transparent;
  border-right: 0;
  border-left: 0;
  border-radius: 0;
}

.document-selection-item,
.document-preview-item {
  background: transparent;
  border-right: 0;
  border-left: 0;
  border-radius: 0;
}

.document-batch-controls {
  border-radius: 8px;
  box-shadow: none;
}

.document-import-action-buttons .el-button,
.document-selection-footer .el-button,
.document-preview-footer .el-button,
.document-import-plan .el-button {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.document-import-actions strong,
.document-import-summary-primary > strong,
.document-selection-source strong,
.document-preview-item-heading strong,
.document-import-result h3 {
  line-height: var(--type-heading-leading, 1.22);
}

.document-import-heading-meta {
  flex-wrap: wrap;
  white-space: normal;
}

.document-import-boundary-copy,
.document-selection-diagnostic,
.document-content-preview,
.document-import-notice,
.document-import-result,
.document-import-plan {
  overflow-wrap: anywhere;
}

@media (max-width: 480px) {
  .document-import-card :deep(.el-card__body),
  .document-import--expanded .document-import-card :deep(.el-card__body) {
    padding: 16px;
  }

  .document-metadata-grid {
    grid-template-columns: 1fr;
  }

  .document-import-action-buttons {
    grid-template-columns: 1fr;
  }

  .document-import-action-buttons .document-import-collapse {
    grid-column: auto;
  }
}

/* F-063: document import remains a staged, code-native workflow. Keep the
 * outer work surface, use dividers for its stages, and let shared type/control
 * tokens carry the business copy. No decorative artwork belongs here. */
.document-import {
  font-family: var(--font-ui);
  font-size: var(--type-body-size, 16px);
  line-height: var(--type-body-leading, 1.62);
}

.document-import-card.el-card {
  border-radius: var(--radius-card, 12px);
  border-color: var(--line, #dce5ef);
  box-shadow: var(--shadow-card, 0 12px 30px rgba(35, 68, 120, 0.08));
}

.document-import-heading h2,
.document-selection-heading h3,
.document-preview-heading h3,
.document-import-result h3 {
  font-size: var(--type-section-title-size, 24px);
  line-height: var(--type-heading-leading, 1.22);
}

.document-import-subtitle,
.document-import-actions p,
.document-import-boundary,
.document-import-boundary-copy,
.document-selection-heading p,
.document-selection-footer p,
.document-preview-footer p,
.document-import-result p,
.document-selection-diagnostic,
.document-content-preview,
.document-import-notice,
.document-import-next-step p,
.document-import-plan p {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.document-import-actions strong,
.document-selection-source strong,
.document-preview-item-heading strong,
.document-import-next-step > div:first-child > strong,
.document-import-plan strong {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.document-import-label,
.document-catalog-heading,
.document-batch-controls label > span,
.document-metadata-grid label > span,
.document-advanced-field summary,
.document-import-technical-details,
.document-authorization-heading,
.document-import-next-step .document-import-label {
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.document-import-card :deep(.el-button),
.document-import-card :deep(.el-checkbox) {
  min-height: 44px;
}

.document-import-card :deep(.el-input__wrapper),
.document-import-card :deep(.el-select__wrapper) {
  min-height: 44px;
}

.document-import-card :deep(.el-button) {
  border-radius: var(--radius-control, 9px);
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.document-import-card :deep(.el-alert__title) {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.document-catalog-list code,
.document-selection-source code,
.document-preview-item-heading code,
.document-preview-footer code,
.document-import-plan code {
  font-family: var(--font-code);
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
}

/* The catalog, selection, preview and next-step blocks are already one
 * workflow. Remove competing card fills so nested rows read as stages. */
.document-batch-controls,
.document-selection-item,
.document-preview-item,
.document-import-next-step,
.document-import-plan {
  border-radius: 0;
  box-shadow: none;
}

.document-batch-controls {
  background: transparent;
  border-right: 0;
  border-left: 0;
  border-color: var(--line, #dce5ef);
}

.document-selection-item,
.document-preview-item,
.document-import-plan {
  background: transparent;
  border-right: 0;
  border-left: 0;
}

.document-selection-item + .document-selection-item,
.document-preview-item + .document-preview-item,
.document-import-plan + .document-import-plan {
  border-top-color: var(--line, #dce5ef);
}

.document-import-next-step {
  border-color: var(--line, #dce5ef);
}

.document-import-card :is(button, a, input, select, textarea):focus-visible {
  outline: 2px solid var(--action-blue, #4f7cff);
  outline-offset: 2px;
}

/* F-063 second visual pass: mobile uses a smaller shared token, but import
 * guidance is business copy and must stay at a comfortable reading size. */
.document-import-subtitle,
.document-import-actions p,
.document-import-boundary,
.document-import-boundary-copy,
.document-selection-heading p,
.document-selection-footer p,
.document-preview-footer p,
.document-import-result p,
.document-selection-diagnostic,
.document-content-preview,
.document-import-notice,
.document-import-next-step p,
.document-import-plan p {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.document-import-card :deep(.el-button) {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.document-import details > summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 10px 0;
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.document-catalog-list code,
.document-selection-source code,
.document-preview-item-heading code,
.document-preview-footer code,
.document-import-plan code {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}
</style>
