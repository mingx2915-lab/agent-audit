<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { DiagnosticCategory, DiagnosticPreview } from "@agent-audit/contracts";
import { apiFetch } from "../api";
import { isDesktopRuntime, nativeErrorMessage, saveDiagnosticsArchive } from "../native";

const preview = ref<DiagnosticPreview | null>(null);
const loading = ref(false);
const exporting = ref(false);
const error = ref("");
const notice = ref("");

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function diagnosticCategoryId(value: unknown): value is DiagnosticCategory["id"] {
  return value === "logs" || value === "runtime" || value === "sidecar" || value === "workspace";
}

function parsePreview(value: unknown): DiagnosticPreview {
  if (!record(value) || !Array.isArray(value.included) || !Array.isArray(value.excluded)) {
    throw new Error("诊断 Preview 响应格式无效");
  }
  const included = value.included.map((item) => {
    if (!record(item) || !diagnosticCategoryId(item.id) || typeof item.label !== "string" ||
      typeof item.available !== "boolean" || typeof item.count !== "number") {
      throw new Error("诊断 Preview 包含项格式无效");
    }
    return { id: item.id, label: item.label, available: item.available, count: item.count };
  });
  if (!value.excluded.every((item) => typeof item === "string") ||
    value.localOnly !== true || typeof value.suggestedFilename !== "string" ||
    typeof value.disclaimer !== "string") {
    throw new Error("诊断 Preview 边界字段无效");
  }
  return {
    included,
    excluded: value.excluded as string[],
    localOnly: value.localOnly,
    suggestedFilename: value.suggestedFilename,
    disclaimer: value.disclaimer,
  };
}

async function responseError(response: Response): Promise<Error> {
  try {
    const payload: unknown = await response.json();
    if (record(payload) && typeof payload.detail === "string") return new Error(payload.detail);
  } catch { /* status remains useful */ }
  return new Error(`请求失败（${response.status}）`);
}

async function loadPreview(): Promise<void> {
  if (loading.value) return;
  loading.value = true;
  error.value = "";
  try {
    const response = await apiFetch("/api/diagnostics/preview");
    if (!response.ok) throw await responseError(response);
    preview.value = parsePreview(await response.json());
  } catch (cause) {
    error.value = nativeErrorMessage(cause, "诊断 Preview 加载失败");
  } finally { loading.value = false; }
}

function downloadBlob(bytes: Uint8Array, filename: string): void {
  const copy = new Uint8Array(bytes.byteLength); copy.set(bytes);
  const url = URL.createObjectURL(new Blob([copy.buffer as ArrayBuffer], { type: "application/zip" }));
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click();
  URL.revokeObjectURL(url);
}

async function exportDiagnostics(): Promise<void> {
  if (!preview.value || exporting.value) return;
  exporting.value = true; error.value = ""; notice.value = "";
  try {
    const response = await apiFetch("/api/diagnostics/export", { method: "POST" });
    if (!response.ok) throw await responseError(response);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (isDesktopRuntime()) {
      const saved = await saveDiagnosticsArchive(bytes, preview.value.suggestedFilename);
      notice.value = saved === false ? "已取消保存；没有写入诊断包。" : "诊断包已保存到你选择的本地位置。";
    } else {
      downloadBlob(bytes, preview.value.suggestedFilename);
      notice.value = "诊断包已由浏览器下载。";
    }
  } catch (cause) {
    error.value = nativeErrorMessage(cause, "诊断包导出失败");
  } finally { exporting.value = false; }
}

onMounted(() => { void loadPreview(); });
</script>

<template>
  <section class="diagnostics" data-testid="local-diagnostics" aria-labelledby="diagnostics-title">
    <div class="diagnostics-heading">
      <div><p class="section-kicker">LOCAL SUPPORT</p><h2 id="diagnostics-title">导出本地诊断</h2>
        <p>只收集允许的运行元数据和脱敏日志，不上传网络。</p></div>
      <el-button type="primary" plain :loading="exporting" :disabled="!preview || loading" data-testid="diagnostics-export" @click="exportDiagnostics">
        {{ exporting ? "生成中" : "生成并保存 ZIP" }}
      </el-button>
    </div>
    <p v-if="loading" class="diagnostics-state">正在读取诊断范围…</p>
    <el-alert v-else-if="error" :title="error" type="error" :closable="false" data-testid="diagnostics-error" />
    <template v-else-if="preview">
      <div class="diagnostics-lists">
        <div><h3>将包含</h3><ul><li v-for="item in preview.included" :key="item.id">
          <span>{{ item.label }}</span><small>{{ item.available ? `${item.count} 项` : "当前无可用记录" }}</small>
        </li></ul></div>
        <div><h3>明确排除</h3><ul><li v-for="item in preview.excluded" :key="item"><span>{{ item }}</span></li></ul></div>
      </div>
      <p class="diagnostics-boundary" data-testid="diagnostics-boundary">
        <strong>{{ preview.localOnly ? "全程本地处理·不上传" : "请核对处理边界" }}</strong>
        <span>{{ preview.disclaimer }}</span>
      </p>
      <p v-if="notice" class="diagnostics-notice" data-testid="diagnostics-notice">{{ notice }}</p>
    </template>
  </section>
</template>

<style scoped>
.diagnostics{margin:24px 0;padding:28px 32px;border:1px solid var(--line);border-radius:var(--radius-card);background:var(--surface)}
.diagnostics-heading{display:flex;justify-content:space-between;align-items:end;gap:28px}.diagnostics-heading h2{margin:5px 0 7px;color:var(--ink-strong)}.diagnostics-heading p{margin:0;color:var(--ink-muted)}
.diagnostics-lists{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:24px}.diagnostics-lists>div{padding:18px;border:1px solid var(--line);border-radius:var(--radius-control);background:var(--surface-raised)}
.diagnostics-lists h3{margin:0 0 12px}.diagnostics-lists ul{display:grid;gap:9px;margin:0;padding:0;list-style:none}.diagnostics-lists li{display:flex;justify-content:space-between;gap:16px;color:var(--ink)}.diagnostics-lists small{color:var(--ink-muted)}
.diagnostics-boundary{display:flex;gap:18px;margin:18px 0 0;padding:14px 16px;border-left:3px solid var(--warning-amber);background:rgba(246,181,56,.09);color:var(--ink-muted)}.diagnostics-boundary strong{white-space:nowrap;color:var(--ink)}
.diagnostics-notice,.diagnostics-state{color:var(--evidence-teal);margin:14px 0 0}
@media(max-width:700px){.diagnostics{padding:22px 18px}.diagnostics-heading{align-items:stretch;flex-direction:column}.diagnostics-heading .el-button{width:100%}.diagnostics-lists{grid-template-columns:1fr}.diagnostics-boundary{flex-direction:column;gap:5px}.diagnostics-boundary strong{white-space:normal}}
</style>
