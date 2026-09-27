<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { apiFetch } from "../api";
import {
  activateWorkspace,
  isDesktopRuntime,
  saveWorkspaceBackup,
  selectWorkspaceBackup,
} from "../native";
import type {
  WorkspaceActivationPreparation,
  WorkspaceBackupPreview,
  WorkspaceRestoreResult,
  WorkspaceSummary,
} from "@agent-audit/contracts";

const expanded = ref(false);
const currentWorkspace = ref<WorkspaceSummary | null>(null);
const currentLoading = ref(false);
const currentError = ref("");
const operationError = ref("");
const notice = ref("");
const backupLoading = ref(false);
const restoreLoading = ref(false);
const previewLoading = ref(false);
const activateLoading = ref(false);
const backupPreview = ref<WorkspaceBackupPreview | null>(null);
const restoredWorkspace = ref<WorkspaceRestoreResult | null>(null);
const archiveBytes = ref<Uint8Array | null>(null);

const hasArchive = computed(() => Boolean(archiveBytes.value));
const canRestore = computed(
  () => Boolean(backupPreview.value && archiveBytes.value) && !restoreLoading.value,
);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isWorkspaceSummary(value: unknown): value is WorkspaceSummary {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.name === "string" &&
    typeof value.relativeDirectory === "string" &&
    typeof value.contractId === "string" &&
    typeof value.contractVersion === "number" &&
    typeof value.documentCount === "number" &&
    typeof value.historyIncluded === "boolean" &&
    typeof value.active === "boolean"
  );
}

function isBackupPreview(value: unknown): value is WorkspaceBackupPreview {
  if (!isRecord(value) || value.formatVersion !== 1) {
    return false;
  }
  return (
    isWorkspaceSummary(value.workspace) &&
    typeof value.archiveSizeBytes === "number" &&
    typeof value.createdAt === "string"
  );
}

function isRestoreResult(value: unknown): value is WorkspaceRestoreResult {
  if (!isRecord(value) || value.restored !== true || value.restartRequired !== true) {
    return false;
  }
  return isWorkspaceSummary(value.workspace);
}

function isActivationPreparation(value: unknown): value is WorkspaceActivationPreparation {
  return (
    isRecord(value) &&
    value.prepared === true &&
    typeof value.relativeDirectory === "string" &&
    typeof value.workspaceSchemaVersion === "number" &&
    typeof value.sqliteSchemaVersion === "number"
  );
}

async function responseError(response: Response): Promise<Error> {
  let detail = "";
  try {
    const payload: unknown = await response.json();
    if (isRecord(payload) && typeof payload.detail === "string") {
      detail = payload.detail;
    }
  } catch {
    // The status remains useful when a failed response is not JSON.
  }
  return new Error(detail || `请求失败（${response.status}）`);
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KiB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

function archiveBody(bytes: Uint8Array): Blob {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return new Blob([copy.buffer as ArrayBuffer], { type: "application/zip" });
}

function clearArchive(): void {
  if (backupLoading.value || previewLoading.value || restoreLoading.value) {
    return;
  }
  archiveBytes.value = null;
  backupPreview.value = null;
  restoredWorkspace.value = null;
  operationError.value = "";
  notice.value = "已取消本次恢复选择；没有写入 Workspace。";
}

async function loadCurrentWorkspace(): Promise<void> {
  if (currentLoading.value) {
    return;
  }
  currentLoading.value = true;
  currentError.value = "";
  try {
    const response = await apiFetch("/api/workspace");
    if (!response.ok) {
      throw await responseError(response);
    }
    const payload: unknown = await response.json();
    if (!isWorkspaceSummary(payload)) {
      throw new Error("Workspace 状态响应格式无效");
    }
    currentWorkspace.value = payload;
  } catch (error) {
    currentError.value = error instanceof Error ? error.message : "Workspace 状态加载失败";
  } finally {
    currentLoading.value = false;
  }
}

async function createBackup(): Promise<void> {
  if (backupLoading.value || restoreLoading.value) {
    return;
  }
  backupLoading.value = true;
  operationError.value = "";
  notice.value = "";
  try {
    const response = await apiFetch("/api/workspace/backups/current");
    if (!response.ok) {
      throw await responseError(response);
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    const date = new Date().toISOString().slice(0, 10);
    const saved = await saveWorkspaceBackup(bytes, `agent-audit-workspace-${date}.zip`);
    notice.value = saved === false ? "已取消保存；没有写入备份文件。" : "Workspace 备份已保存到你选择的位置。";
  } catch (error) {
    operationError.value = error instanceof Error ? error.message : "Workspace 备份失败";
  } finally {
    backupLoading.value = false;
  }
}

async function selectBackup(): Promise<void> {
  if (backupLoading.value || previewLoading.value || restoreLoading.value) {
    return;
  }
  previewLoading.value = true;
  operationError.value = "";
  notice.value = "";
  try {
    const bytes = await selectWorkspaceBackup();
    if (!bytes || bytes.byteLength === 0) {
      notice.value = "已取消选择；没有读取备份文件。";
      return;
    }
    archiveBytes.value = bytes;
    const response = await apiFetch("/api/workspace/backups/previews", {
      method: "POST",
      headers: { "Content-Type": "application/zip" },
      body: archiveBody(bytes),
    });
    if (!response.ok) {
      throw await responseError(response);
    }
    const payload: unknown = await response.json();
    if (!isBackupPreview(payload)) {
      throw new Error("Workspace 备份 Preview 响应格式无效");
    }
    backupPreview.value = payload;
    restoredWorkspace.value = null;
    notice.value = "已生成只读 Preview；确认后才会创建新的 Workspace。";
  } catch (error) {
    archiveBytes.value = null;
    backupPreview.value = null;
    operationError.value = error instanceof Error ? error.message : "Workspace 备份 Preview 失败";
  } finally {
    previewLoading.value = false;
  }
}

async function restoreBackup(): Promise<void> {
  if (!canRestore.value || !archiveBytes.value) {
    return;
  }
  restoreLoading.value = true;
  operationError.value = "";
  notice.value = "";
  try {
    const response = await apiFetch("/api/workspace/restores", {
      method: "POST",
      headers: { "Content-Type": "application/zip" },
      body: archiveBody(archiveBytes.value),
    });
    if (!response.ok) {
      throw await responseError(response);
    }
    const payload: unknown = await response.json();
    if (!isRestoreResult(payload)) {
      throw new Error("Workspace 恢复响应格式无效");
    }
    restoredWorkspace.value = payload;
    notice.value = `已恢复为新 Workspace「${payload.workspace.name}」；当前 Workspace 未被覆盖。`;
  } catch (error) {
    operationError.value = error instanceof Error ? error.message : "Workspace 恢复失败";
  } finally {
    restoreLoading.value = false;
  }
}

async function switchWorkspace(): Promise<void> {
  const workspace = restoredWorkspace.value?.workspace;
  if (!workspace || activateLoading.value) {
    return;
  }
  activateLoading.value = true;
  operationError.value = "";
  try {
    const preparation = await apiFetch("/api/workspace/activation-preparations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ relativeDirectory: workspace.relativeDirectory }),
    });
    if (!preparation.ok) {
      throw await responseError(preparation);
    }
    const prepared: unknown = await preparation.json();
    if (!isActivationPreparation(prepared) || prepared.relativeDirectory !== workspace.relativeDirectory) {
      throw new Error("Workspace 激活准备响应格式无效");
    }
    await activateWorkspace(workspace.relativeDirectory);
    if (isDesktopRuntime()) {
      notice.value = "新 Workspace 已激活，正在重新连接本机后台…";
      window.location.reload();
    } else {
      notice.value = "新 Workspace 已准备好；请在桌面窗口中重新加载以切换。";
    }
  } catch (error) {
    operationError.value = error instanceof Error ? error.message : "Workspace 切换失败";
  } finally {
    activateLoading.value = false;
  }
}

onMounted(() => {
  void loadCurrentWorkspace();
});
</script>

<template>
  <section class="workspace-operations" aria-labelledby="workspace-operations-title" data-testid="workspace-operations">
    <el-card class="workspace-operations-card" shadow="never">
      <div class="workspace-operations-summary" data-testid="workspace-operations-summary">
        <div>
          <p class="section-kicker">Workspace</p>
          <h2 id="workspace-operations-title">Workspace 备份与恢复</h2>
          <p class="workspace-operations-caption">
            备份、恢复或切换当前 Workspace。
          </p>
          <p v-if="currentLoading" class="workspace-operations-status">正在读取当前 Workspace…</p>
          <p v-else-if="currentWorkspace" class="workspace-operations-status">
            当前：<strong>{{ currentWorkspace.name }}</strong> · {{ currentWorkspace.documentCount }} documents ·
            Contract v{{ currentWorkspace.contractVersion }}
          </p>
          <p v-else-if="currentError" class="workspace-operations-error">{{ currentError }}</p>
        </div>
        <el-button
          data-testid="workspace-operations-open"
          type="primary"
          plain
          :aria-expanded="expanded"
          @click="expanded = !expanded"
        >
          {{ expanded ? "收起" : "备份 / 恢复" }}
        </el-button>
      </div>

      <template v-if="expanded">
        <details class="workspace-operations-boundary">
          <summary><span class="workspace-operations-dot" aria-hidden="true"></span>备份范围</summary>
          <span>备份是本地 ZIP；原生保存/选择只在桌面窗口执行，来源绝对路径不会进入 API 工件。</span>
        </details>

        <el-alert
          v-if="operationError"
          class="workspace-operations-alert"
          data-testid="workspace-operations-error"
          :title="operationError"
          type="error"
          :closable="false"
        />
        <p v-if="notice" class="workspace-operations-notice" data-testid="workspace-operations-notice">
          {{ notice }}
        </p>

        <div class="workspace-operations-actions">
          <div>
            <span class="workspace-operations-label">当前 Workspace</span>
            <strong>{{ currentWorkspace?.name ?? "当前 Workspace" }}</strong>
            <small>完整快照 · 不覆盖当前数据</small>
          </div>
          <el-button
            data-testid="workspace-backup-save"
            type="primary"
            :loading="backupLoading"
            :disabled="backupLoading || restoreLoading"
            @click="createBackup"
          >
            {{ backupLoading ? "生成中" : "备份当前 Workspace" }}
          </el-button>
        </div>

        <div class="workspace-restore-block" data-testid="workspace-restore">
          <div class="workspace-restore-heading">
            <div>
              <span class="workspace-operations-label">恢复为新 Workspace</span>
              <h3>从备份恢复</h3>
              <p>先预览 ZIP，再创建新的 Workspace。</p>
            </div>
            <div class="workspace-restore-buttons">
              <el-button
                data-testid="workspace-backup-select"
                :loading="previewLoading"
                :disabled="backupLoading || previewLoading || restoreLoading"
                @click="selectBackup"
              >
                {{ previewLoading ? "读取中" : "选择备份 ZIP" }}
              </el-button>
              <el-button
                data-testid="workspace-backup-cancel"
                text
                :disabled="backupLoading || previewLoading || restoreLoading"
                @click="clearArchive"
              >
                取消
              </el-button>
            </div>
          </div>

          <div v-if="backupPreview" class="workspace-backup-preview" data-testid="workspace-backup-preview">
            <div class="workspace-backup-preview-heading">
              <div>
                <span class="workspace-operations-label">备份预览 · 只读</span>
                <h3>{{ backupPreview.workspace.name }}</h3>
              </div>
              <el-tag type="info" effect="plain">{{ formatBytes(backupPreview.archiveSizeBytes) }}</el-tag>
            </div>
            <dl class="workspace-backup-facts">
              <div><dt>Workspace ID</dt><dd><code>{{ backupPreview.workspace.id }}</code></dd></div>
              <div><dt>Contract</dt><dd><code>{{ backupPreview.workspace.contractId }} · v{{ backupPreview.workspace.contractVersion }}</code></dd></div>
              <div><dt>Documents</dt><dd>{{ backupPreview.workspace.documentCount }}</dd></div>
              <div><dt>History</dt><dd>{{ backupPreview.workspace.historyIncluded ? "included" : "none" }}</dd></div>
            </dl>
            <div class="workspace-backup-preview-footer">
              <details class="workspace-operations-technical-details">
                <summary>预览说明</summary>
                <span>Preview 不写磁盘、不切换当前 Workspace、不调用 Provider。</span>
              </details>
              <el-button
                data-testid="workspace-backup-restore"
                type="primary"
                :loading="restoreLoading"
                :disabled="!canRestore"
                @click="restoreBackup"
              >
                {{ restoreLoading ? "恢复中" : "确认恢复为新 Workspace" }}
              </el-button>
            </div>
          </div>

          <div v-if="restoredWorkspace" class="workspace-restore-result" data-testid="workspace-restore-result">
            <div>
              <span class="workspace-operations-label">新 Workspace</span>
              <h3>{{ restoredWorkspace.workspace.name }}</h3>
              <p>
                已创建新目录 <code>{{ restoredWorkspace.workspace.relativeDirectory }}</code>；原 Workspace 保持不变。
              </p>
            </div>
            <el-button
              data-testid="workspace-activate"
              type="primary"
              :loading="activateLoading"
              @click="switchWorkspace"
            >
              {{ activateLoading ? "切换中" : "切换到此 Workspace" }}
            </el-button>
          </div>
        </div>
      </template>
    </el-card>
  </section>
</template>

<style scoped>
.workspace-operations {
  margin-top: 24px;
}

.workspace-operations-card {
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 18px;
  background: rgba(248, 250, 252, 0.72);
}

.workspace-operations-summary,
.workspace-operations-actions,
.workspace-restore-heading,
.workspace-backup-preview-heading,
.workspace-backup-preview-footer,
.workspace-restore-result {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.workspace-operations-summary {
  align-items: center;
}

.workspace-operations-summary h2,
.workspace-restore-heading h3,
.workspace-backup-preview-heading h3,
.workspace-restore-result h3 {
  margin: 6px 0 0;
  color: #10233f;
}

.workspace-operations-caption,
.workspace-restore-heading p,
.workspace-restore-result p {
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.6;
}

.workspace-operations-status,
.workspace-operations-error,
.workspace-operations-notice {
  margin: 8px 0 0;
  color: #475569;
  font-size: 13px;
}

.workspace-operations-error,
.workspace-operations-alert :deep(.el-alert__title) {
  color: #b42318;
}

.workspace-operations-boundary {
  margin: 18px 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(224, 242, 254, 0.58);
  color: #36526e;
  font-size: 13px;
}

.workspace-operations-boundary summary {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  color: var(--action-blue, #4f7cff);
  cursor: pointer;
}

.workspace-operations-boundary > span {
  display: block;
  margin-top: 6px;
}

.workspace-operations-technical-details {
  margin: 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.workspace-operations-technical-details summary {
  width: fit-content;
  color: var(--action-blue, #4f7cff);
  cursor: pointer;
}

.workspace-operations-technical-details > span {
  display: block;
  margin-top: 5px;
}

.workspace-operations-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: #0ea5e9;
}

.workspace-operations-actions {
  align-items: center;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  background: #fff;
}

.workspace-operations-actions strong,
.workspace-operations-actions small {
  display: block;
}

.workspace-operations-actions strong {
  margin-top: 4px;
  color: #1e293b;
}

.workspace-operations-actions small {
  margin-top: 5px;
  color: #64748b;
}

.workspace-operations-label {
  display: block;
  color: #64748b;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.workspace-restore-block {
  margin-top: 14px;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  background: #fff;
}

.workspace-restore-buttons {
  display: flex;
  align-items: center;
  gap: 8px;
}

.workspace-backup-preview,
.workspace-restore-result {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.22);
}

.workspace-backup-facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0;
}

.workspace-backup-facts div {
  padding: 10px;
  border-radius: 10px;
  background: #f8fafc;
}

.workspace-backup-facts dt {
  color: #64748b;
  font-size: 11px;
}

.workspace-backup-facts dd {
  margin: 5px 0 0;
  color: #1e293b;
  font-size: 13px;
}

.workspace-backup-preview-footer {
  align-items: center;
}

.workspace-backup-preview-footer p {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

.workspace-restore-result {
  align-items: center;
}

.workspace-restore-result code,
.workspace-backup-facts code {
  overflow-wrap: anywhere;
}

@media (max-width: 720px) {
  .workspace-operations-summary,
  .workspace-operations-actions,
  .workspace-restore-heading,
  .workspace-backup-preview-heading,
  .workspace-backup-preview-footer,
  .workspace-restore-result {
    flex-direction: column;
    align-items: stretch;
  }

  .workspace-backup-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workspace-restore-buttons {
    justify-content: flex-start;
  }
}

@media (max-width: 390px) {
  .workspace-backup-facts {
    grid-template-columns: 1fr;
  }
}

/* F-063: backup/restore is one local workspace surface. Keep each operation
 * in the existing flow, but replace card-in-card fills with shared dividers
 * and readable controls. */
.workspace-operations {
  font-family: var(--font-ui);
  font-size: var(--type-body-size, 16px);
  line-height: var(--type-body-leading, 1.62);
}

.workspace-operations-card {
  border: 1px solid var(--line, #dce5ef);
  border-radius: var(--radius-card, 12px);
  background: var(--surface, #ffffff);
  box-shadow: var(--shadow-card, 0 12px 30px rgba(35, 68, 120, 0.08));
}

.workspace-operations-card :deep(.el-card__body) {
  padding: var(--space-6, 24px);
}

.workspace-operations-summary h2 {
  font-size: var(--type-section-title-size, 24px);
  line-height: var(--type-heading-leading, 1.22);
}

.workspace-operations-caption,
.workspace-operations-status,
.workspace-operations-boundary,
.workspace-operations-technical-details,
.workspace-operations-error,
.workspace-operations-notice,
.workspace-operations-actions small,
.workspace-restore-heading p,
.workspace-backup-preview-footer,
.workspace-restore-result p {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.workspace-operations-label {
  color: var(--ink-muted, #64748b);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
  letter-spacing: normal;
}

.workspace-operations-actions strong,
.workspace-restore-heading h3,
.workspace-backup-preview-heading h3,
.workspace-restore-result h3 {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.workspace-operations-card :deep(.el-button) {
  min-height: 44px;
  border-radius: var(--radius-control, 9px);
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.workspace-backup-facts dt {
  color: var(--ink-muted, #64748b);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.workspace-backup-facts dd {
  color: var(--ink, #24364d);
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.workspace-backup-facts code,
.workspace-restore-result code {
  font-family: var(--font-code);
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
}

/* One surface, several operation stages. */
.workspace-operations-actions,
.workspace-restore-block,
.workspace-backup-preview,
.workspace-restore-result,
.workspace-backup-facts div {
  border-radius: 0;
  box-shadow: none;
}

.workspace-operations-actions,
.workspace-restore-block {
  background: transparent;
  border-right: 0;
  border-bottom: 0;
  border-left: 0;
  border-color: var(--line, #dce5ef);
}

.workspace-backup-facts div {
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line, #dce5ef);
}

.workspace-operations-card :is(button, a):focus-visible {
  outline: 2px solid var(--action-blue, #4f7cff);
  outline-offset: 2px;
}

/* F-063 second visual pass: explanatory Workspace copy follows the readable
 * body scale, while both disclosure rows retain a full touch target. */
.workspace-operations-caption,
.workspace-operations-status,
.workspace-operations-boundary,
.workspace-operations-technical-details,
.workspace-operations-error,
.workspace-operations-notice,
.workspace-operations-actions small,
.workspace-restore-heading p,
.workspace-backup-preview-footer,
.workspace-restore-result p {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.workspace-operations-boundary summary,
.workspace-operations-technical-details summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 10px 0;
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.workspace-operations-card :deep(.el-button) {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}
</style>
