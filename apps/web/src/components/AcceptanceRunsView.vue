<script setup lang="ts">
import { onMounted, ref } from "vue";
import type {
  AcceptanceMetricDelta,
  AcceptanceRun,
  AcceptanceRunComparison,
  AcceptanceRunSummary,
  CIGateCheck,
  FindingCategory,
  ProviderReadinessStatus,
} from "@agent-audit/contracts";
import { apiFetch, apiUrl } from "../api";

const summaries = ref<AcceptanceRunSummary[]>([]);
const selectedRunId = ref("");
const selectedRun = ref<AcceptanceRun | null>(null);
const comparison = ref<AcceptanceRunComparison | null>(null);

const historyLoading = ref(false);
const historyError = ref("");
const runLoading = ref(false);
const runError = ref("");
const detailLoading = ref(false);
const detailError = ref("");

let historyRequestToken = 0;
let detailRequestToken = 0;

const findingCategoryLabels: Record<FindingCategory, string> = {
  resource_authorization_bypass: "资源授权绕过",
  tool_authorization_bypass: "工具授权绕过",
  external_sink_policy_violation: "外部数据流向策略违规",
  tool_business_policy_violation: "工具业务约束违规",
};

const readinessLabels: Record<ProviderReadinessStatus, string> = {
  ready: "已就绪 · READY",
  partial: "部分兼容 · PARTIAL",
  unavailable: "不可用 · UNAVAILABLE",
};

const gateCheckLabels: Record<string, string> = {
  all_cases_matched: "24 项 Case 全部匹配",
  detection_recall: "发现召回率",
  false_positive_rate: "误报率",
  policy_violation_accuracy: "策略违规准确率",
  replay_pass_rate: "Replay 通过率",
};

const metricLabels: Record<string, string> = {
  all_cases_matched: "Case 匹配情况",
  detection_recall: "发现召回率 Detection Recall",
  false_positive_rate: "误报率 False Positive Rate",
  policy_violation_accuracy: "策略违规准确率 Policy Accuracy",
  replay_pass_rate: "Replay 通过率 Replay Pass Rate",
};

function formatDate(value: string): string {
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

function formatDuration(value: number): string {
  if (!Number.isFinite(value)) {
    return String(value);
  }

  return `${Number.isInteger(value) ? value : value.toFixed(2)} ms`;
}

function formatPercentage(value: number | null): string {
  return value === null ? "暂无数据" : `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value: number | null): string {
  return value === null ? "暂无数据" : Number.isInteger(value) ? String(value) : value.toFixed(3);
}

function formatBoolean(value: boolean | null): string {
  if (value === null) {
    return "暂无数据";
  }

  return value ? "是 · true" : "否 · false";
}

function formatMetricValue(id: string, value: boolean | number | null): string {
  if (id === "all_cases_matched") {
    return formatBoolean(typeof value === "boolean" ? value : null);
  }

  return formatPercentage(typeof value === "number" ? value : null);
}

function formatMetricDelta(metric: AcceptanceMetricDelta): string {
  if (metric.delta === null) {
    return "—";
  }

  if (metric.id === "all_cases_matched") {
    return metric.delta > 0 ? "+1 · 改善" : metric.delta < 0 ? "−1 · 变差" : "0 · 无变化";
  }

  const percentagePoints = metric.delta * 100;
  const sign = percentagePoints > 0 ? "+" : "";
  return `${sign}${percentagePoints.toFixed(1)} pp`;
}

function metricDeltaClass(metric: AcceptanceMetricDelta): string {
  if (metric.delta === null || metric.delta === 0) {
    return "is-neutral";
  }

  const improved = metric.id === "false_positive_rate" ? metric.delta < 0 : metric.delta > 0;
  return improved ? "is-positive" : "is-negative";
}

function readinessClass(status: ProviderReadinessStatus): string {
  return `is-${status}`;
}

function gateClass(status: "passed" | "failed"): string {
  return `is-${status}`;
}

function verdictLabel(verdict: "passed" | "failed"): string {
  return verdict === "passed" ? "通过 · PASSED" : "未通过 · FAILED";
}

function findingCategoryLabel(category: FindingCategory): string {
  return findingCategoryLabels[category] ?? category;
}

function findingCategoriesLabel(categories: FindingCategory[]): string {
  return categories.length > 0 ? categories.map(findingCategoryLabel).join(" · ") : "无实际风险类别";
}

function providerModel(provider: { provider: string; model: string | null }): string {
  return `${provider.provider} / ${provider.model ?? "未配置模型"}`;
}

function checkLabel(check: CIGateCheck): string {
  return gateCheckLabels[check.id] ?? check.id;
}

function checkValue(value: boolean | number | null): string {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }

  return value === null ? "null" : String(value);
}

function scanStatusLabel(status: string): string {
  switch (status) {
    case "completed":
      return "已完成 · COMPLETED";
    case "blocked":
      return "已阻断 · BLOCKED";
    case "failed":
      return "失败 · FAILED";
    case "running":
      return "执行中 · RUNNING";
    default:
      return status;
  }
}

function stopReasonLabel(reason: string): string {
  switch (reason) {
    case "finding_detected":
      return "发现风险 · FINDING DETECTED";
    case "no_new_variant":
      return "没有新的攻击变体 · NO NEW VARIANT";
    case "max_rounds_reached":
      return "达到轮数上限 · MAX ROUNDS";
    default:
      return reason;
  }
}

function evaluationStatusLabel(status: string): string {
  switch (status) {
    case "passed":
      return "通过 · PASSED";
    case "failed":
      return "未通过 · FAILED";
    default:
      return status;
  }
}

function runStatusLabel(status: string): string {
  switch (status) {
    case "completed":
      return "已完成 · COMPLETED";
    case "failed":
      return "失败 · FAILED";
    case "running":
      return "执行中 · RUNNING";
    default:
      return status;
  }
}

function changedLabel(changed: boolean): string {
  return changed ? "已变化 · CHANGED" : "未变化 · UNCHANGED";
}

function responseError(response: Response): Promise<Error> {
  return response
    .json()
    .then((payload: unknown) => {
      if (payload !== null && typeof payload === "object" && "detail" in payload) {
        const detail = payload.detail;
        if (typeof detail === "string" && detail.trim()) {
          return new Error(detail);
        }
        if (detail !== undefined && detail !== null) {
          return new Error(JSON.stringify(detail));
        }
      }
      return new Error(`请求失败（${response.status}）`);
    })
    .catch(() => new Error(`请求失败（${response.status}）`));
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(url, init);
  if (!response.ok) {
    throw await responseError(response);
  }

  return (await response.json()) as T;
}

async function loadRunDetail(runId: string): Promise<void> {
  const requestToken = ++detailRequestToken;
  selectedRunId.value = runId;
  detailLoading.value = true;
  detailError.value = "";
  selectedRun.value = null;
  comparison.value = null;

  try {
    const [run, runComparison] = await Promise.all([
      fetchJson<AcceptanceRun>(`/api/acceptance-runs/${encodeURIComponent(runId)}`),
      fetchJson<AcceptanceRunComparison>(
        `/api/acceptance-runs/${encodeURIComponent(runId)}/comparison`,
      ),
    ]);
    if (requestToken !== detailRequestToken || selectedRunId.value !== runId) {
      return;
    }

    selectedRun.value = run;
    comparison.value = runComparison;
  } catch (error) {
    if (requestToken === detailRequestToken) {
      detailError.value = error instanceof Error ? error.message : "Acceptance Run 详情加载失败";
    }
  } finally {
    if (requestToken === detailRequestToken) {
      detailLoading.value = false;
    }
  }
}

async function loadHistory(preferredRunId?: string): Promise<void> {
  const requestToken = ++historyRequestToken;
  historyLoading.value = true;
  historyError.value = "";

  try {
    const payload = await fetchJson<AcceptanceRunSummary[]>("/api/acceptance-runs?limit=20");
    if (requestToken !== historyRequestToken) {
      return;
    }

    summaries.value = Array.isArray(payload) ? payload : [];
    const nextId =
      preferredRunId ??
      (selectedRunId.value && summaries.value.some((summary) => summary.id === selectedRunId.value)
        ? selectedRunId.value
        : summaries.value[0]?.id ?? "");
    if (!nextId) {
      selectedRunId.value = "";
      selectedRun.value = null;
      comparison.value = null;
      detailError.value = "";
      return;
    }

    await loadRunDetail(nextId);
  } catch (error) {
    if (requestToken === historyRequestToken) {
      historyError.value = error instanceof Error ? error.message : "Acceptance Run 历史加载失败";
      selectedRun.value = null;
      comparison.value = null;
    }
  } finally {
    if (requestToken === historyRequestToken) {
      historyLoading.value = false;
    }
  }
}

async function runAcceptance(): Promise<void> {
  if (runLoading.value) {
    return;
  }

  runLoading.value = true;
  runError.value = "";
  detailError.value = "";

  try {
    const run = await fetchJson<AcceptanceRun>("/api/acceptance-runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    await loadHistory(run.id);
  } catch (error) {
    runError.value = error instanceof Error ? error.message : "完整 Acceptance Run 执行失败";
  } finally {
    runLoading.value = false;
  }
}

function emptyListLabel(values: string[], empty = "无"): string {
  return values.length > 0 ? values.join(" · ") : empty;
}

onMounted(() => {
  void loadHistory();
});
</script>

<template>
  <section class="acceptance-runs" data-testid="acceptance-runs" aria-labelledby="acceptance-runs-title">
    <header class="acceptance-header">
      <div class="acceptance-header-copy">
        <p class="acceptance-kicker">验收证据</p>
        <h2 id="acceptance-runs-title">一次完成全链路验收</h2>
        <p class="acceptance-lede">
          集中运行固定测试、身份差分和同计划复测，检查权限是否符合预期，保存可复核的结论与证据。
        </p>
        <div class="acceptance-header-actions">
          <button
            class="acceptance-run-button"
            data-testid="acceptance-run-start"
            type="button"
            :disabled="runLoading || historyLoading"
            :aria-busy="runLoading"
            @click="runAcceptance"
          >
            {{ runLoading ? "完整验收执行中…" : "开始完整验收" }}
            <span v-if="!runLoading" aria-hidden="true">↗</span>
          </button>
          <button
            class="acceptance-refresh"
            data-testid="acceptance-run-refresh"
            type="button"
            :disabled="historyLoading || runLoading"
            @click="loadHistory()"
          >
            {{ historyLoading ? "读取中…" : "刷新历史" }}
          </button>
        </div>
      </div>

      <aside class="acceptance-scope" data-testid="acceptance-run-scope" aria-label="固定验收范围">
        <div class="acceptance-scope-heading">
          <span>本次运行范围</span>
          <small>固定本地证据链</small>
        </div>
        <div class="acceptance-scope-metrics">
          <span><strong>24</strong><small>固定测试<br />项</small></span>
          <span><strong>5</strong><small>质量门<br />检查</small></span>
          <span><strong>2</strong><small>身份差分<br />任务</small></span>
          <span><strong>1</strong><small>同一计划<br />复测</small></span>
        </div>
        <p class="acceptance-scope-route">Readiness <i>→</i> Evidence <i>→</i> Gate <i>→</i> Replay</p>
      </aside>
    </header>

    <details class="acceptance-boundary">
      <summary>运行说明</summary>
      <span>首载、刷新和选择历史只读取 GET；只有点击“运行完整验收”才会 POST 并调用既有验收链路。</span>
    </details>

    <p v-if="runLoading" class="acceptance-loading" data-testid="acceptance-run-loading" role="status" aria-live="polite">
      <span class="loading-mark" aria-hidden="true">◎</span>
      <span>
        <strong>正在运行固定验收</strong>
        <small>Readiness → Retrieval → Differential → Gate → Scan → Replay</small>
      </span>
    </p>
    <p v-if="historyError || runError || detailError" class="acceptance-error" data-testid="acceptance-run-error" role="alert">
      <span>验收错误</span>
      {{ historyError || runError || detailError }}
    </p>

    <section
      class="acceptance-history"
      :class="{ 'is-empty': !historyLoading && summaries.length === 0 }"
      data-testid="acceptance-run-history"
      aria-labelledby="acceptance-history-title"
    >
      <div class="section-heading">
        <div>
          <p class="acceptance-kicker">历史记录</p>
          <h3 id="acceptance-history-title">历史验收记录</h3>
        </div>
        <span class="section-count">{{ summaries.length }} 条</span>
      </div>

      <div v-if="historyLoading && summaries.length === 0" class="history-placeholder" role="status" aria-live="polite">
        <span class="loading-mark" aria-hidden="true">…</span>
        <span>正在读取已保存 Acceptance Run…</span>
      </div>
      <div v-else-if="summaries.length === 0" class="history-placeholder history-empty" data-testid="acceptance-run-empty">
        <span class="empty-mark" aria-hidden="true">01</span>
        <span class="history-empty-copy">
          <strong>还没有验收记录</strong>
          <small>首次运行后，这里会保存可回看的结论与完整本地证据。</small>
        </span>
        <span class="history-empty-outputs" aria-label="运行后保存的内容">
          <span>验收结论</span>
          <span>风险发现 Finding</span>
          <span>修复复测 Replay</span>
          <span>JSON / Markdown</span>
        </span>
      </div>
      <div v-else class="history-list">
        <button
          v-for="(summary, index) in summaries"
          :key="summary.id"
          class="history-item"
          :class="{ 'is-selected': selectedRunId === summary.id }"
          data-testid="acceptance-run-history-item"
          :data-run-id="summary.id"
          type="button"
          :aria-pressed="selectedRunId === summary.id"
          @click="loadRunDetail(summary.id)"
        >
          <span class="history-item-heading">
            <span>
              <strong>{{ summary.id }}</strong>
              <small>{{ formatDate(summary.completedAt) }}</small>
            </span>
            <span class="history-item-badges">
              <span v-if="index === 0" class="latest-badge">最新</span>
              <span class="status-pill" :class="gateClass(summary.verdict)">{{ verdictLabel(summary.verdict) }}</span>
            </span>
          </span>
          <span class="history-item-facts">
            <span>权限契约 Contract <code>{{ summary.contractId }} · v{{ summary.contractVersion }}</code></span>
            <span>质量门 Gate <code>{{ summary.benchmarkMatchedCaseCount }}/{{ summary.benchmarkCaseCount }}</code></span>
            <span>风险发现 Finding <code>{{ summary.findingCount }}</code></span>
            <span>修复复测 Replay <code>{{ summary.guidedReplayStatus }}</code></span>
          </span>
        </button>
      </div>
    </section>

    <div v-if="detailLoading" class="detail-loading" data-testid="acceptance-run-detail-loading" role="status" aria-live="polite">
      <span class="loading-mark" aria-hidden="true">…</span>
      <span>正在读取所选 Run 的完整快照与对比…</span>
    </div>

    <template v-if="selectedRun">
      <section class="run-summary" data-testid="acceptance-run-summary" aria-labelledby="run-summary-title">
        <header class="section-heading">
          <div>
            <p class="acceptance-kicker">选中记录</p>
            <h3 id="run-summary-title">本次验收摘要</h3>
            <p class="section-caption">
              <code>{{ selectedRun.id }}</code> · {{ formatDate(selectedRun.completedAt) }} ·
              {{ formatDuration(selectedRun.durationMs) }}
            </p>
          </div>
          <div class="summary-statuses">
            <span class="status-pill" data-testid="acceptance-run-status" :class="gateClass(selectedRun.verdict)">
              {{ verdictLabel(selectedRun.verdict) }}
            </span>
            <span class="status-pill is-neutral">{{ runStatusLabel(selectedRun.status) }}</span>
          </div>
        </header>

        <div class="download-row" data-testid="acceptance-run-downloads">
          <span>固定证据导出</span>
          <a
            data-testid="acceptance-run-json-download"
            :href="apiUrl(`/api/acceptance-runs/${encodeURIComponent(selectedRun.id)}/evidence.json`)"
            download
          >下载 JSON</a>
          <a
            data-testid="acceptance-run-markdown-download"
            :href="apiUrl(`/api/acceptance-runs/${encodeURIComponent(selectedRun.id)}/evidence.md`)"
            download
          >下载 Markdown</a>
        </div>

        <div class="summary-grid">
          <article class="summary-card">
            <p class="card-kicker">权限契约快照 <span class="technical-label">CONTRACT SNAPSHOT</span></p>
            <h4>{{ selectedRun.contractSnapshot.name }}</h4>
            <dl class="fact-list">
              <div><dt>Contract</dt><dd><code>{{ selectedRun.contractSnapshot.id }}</code> · v{{ selectedRun.contractSnapshot.version }}</dd></div>
              <div><dt>检查计划</dt><dd>{{ selectedRun.planSnapshots.length }} 个由 Contract 派生的计划</dd></div>
              <div><dt>目标配置</dt><dd>{{ selectedRun.profileSnapshots.length }} 个目标配置 Profile</dd></div>
            </dl>
            <details class="snapshot-details">
              <summary>查看快照 ID</summary>
              <div class="chip-list">
                <code v-for="plan in selectedRun.planSnapshots" :key="plan.id">{{ plan.id }}</code>
              </div>
            </details>
          </article>

          <article class="summary-card">
            <p class="card-kicker">运行环境快照 <span class="technical-label">RUNTIME SNAPSHOT</span></p>
            <h4>{{ providerModel(selectedRun.runtimeSnapshot) }}</h4>
            <dl class="fact-list">
              <div><dt>检索引擎</dt><dd><code>{{ selectedRun.runtimeSnapshot.retrieverEngine }}</code> · {{ selectedRun.runtimeSnapshot.retrieverModel ?? "—" }}</dd></div>
              <div><dt>向量维度</dt><dd>{{ selectedRun.runtimeSnapshot.retrieverDimensions ?? "—" }}</dd></div>
              <div><dt>已索引资料</dt><dd>{{ selectedRun.runtimeSnapshot.indexedDocumentCount }}</dd></div>
            </dl>
          </article>

          <article class="summary-card" data-testid="acceptance-run-readiness">
            <p class="card-kicker">Provider 就绪状态 · 仅作证据 <span class="technical-label">PROVIDER READINESS</span></p>
            <h4 :class="readinessClass(selectedRun.providerReadiness.status)">
              {{ readinessLabels[selectedRun.providerReadiness.status] }}
            </h4>
            <p class="card-caption">Readiness 不直接决定 Finding 或 Gate verdict。</p>
            <dl class="fact-list">
              <div><dt>目标侧</dt><dd><code>{{ providerModel(selectedRun.providerReadiness.targetProvider) }}</code><span :class="readinessClass(selectedRun.providerReadiness.targetProvider.status)">{{ readinessLabels[selectedRun.providerReadiness.targetProvider.status] }}</span></dd></div>
              <div><dt>攻击侧</dt><dd><code>{{ providerModel(selectedRun.providerReadiness.attackProvider) }}</code><span :class="readinessClass(selectedRun.providerReadiness.attackProvider.status)">{{ readinessLabels[selectedRun.providerReadiness.attackProvider.status] }}</span></dd></div>
              <div><dt>探针数量</dt><dd>{{ selectedRun.providerReadiness.targetProvider.probes.length + selectedRun.providerReadiness.attackProvider.probes.length }} 个固定探针</dd></div>
            </dl>
          </article>

          <article class="summary-card" data-testid="acceptance-run-gate">
            <p class="card-kicker">24 项固定质量门 <span class="technical-label">24 CASE CI GATE</span></p>
            <h4 :class="gateClass(selectedRun.ciGate.status)">{{ verdictLabel(selectedRun.ciGate.status) }} · {{ selectedRun.ciGate.failedCheckIds.length }} 项未通过检查</h4>
            <dl class="fact-list">
              <div><dt>匹配 Case</dt><dd><strong>{{ selectedRun.ciGate.benchmark.metrics.matchedCaseCount }}</strong> / {{ selectedRun.ciGate.benchmark.metrics.caseCount }} 个</dd></div>
              <div><dt>发现召回率</dt><dd>{{ formatPercentage(selectedRun.ciGate.benchmark.metrics.detectionRecall) }}</dd></div>
              <div><dt>误报率</dt><dd>{{ formatPercentage(selectedRun.ciGate.benchmark.metrics.falsePositiveRate) }}</dd></div>
              <div><dt>策略准确率</dt><dd>{{ formatPercentage(selectedRun.ciGate.benchmark.metrics.policyViolationAccuracy) }}</dd></div>
              <div><dt>Replay 通过率</dt><dd>{{ formatPercentage(selectedRun.ciGate.benchmark.metrics.replayPassRate) }}</dd></div>
            </dl>
            <div class="check-list">
              <span v-for="check in selectedRun.ciGate.checks" :key="check.id" class="check-row" :class="check.passed ? 'is-passed' : 'is-failed'">
                <span>{{ check.passed ? "✓" : "!" }}</span>
                <strong>{{ checkLabel(check) }}</strong>
                <code>{{ checkValue(check.actual) }} → {{ checkValue(check.expected) }}</code>
              </span>
            </div>
          </article>

          <article class="summary-card" data-testid="acceptance-run-retrieval">
            <p class="card-kicker">检索质量评估 <span class="technical-label">RETRIEVAL EVALUATION</span></p>
            <h4>固定 {{ selectedRun.retrievalEvaluation.metrics.caseCount }} 个检索问题 Query</h4>
            <dl class="fact-list">
              <div><dt>当前引擎</dt><dd><code>{{ selectedRun.retrievalEvaluation.selectedEngine }}</code></dd></div>
              <div><dt>Embedding Top-1 命中</dt><dd>{{ selectedRun.retrievalEvaluation.metrics.embeddingTop1Hits }} / {{ selectedRun.retrievalEvaluation.metrics.caseCount }}</dd></div>
              <div><dt>Embedding MRR</dt><dd>{{ formatNumber(selectedRun.retrievalEvaluation.metrics.embeddingMrr) }}</dd></div>
              <div><dt>维度 / 资料数</dt><dd>{{ selectedRun.retrievalEvaluation.dimensions }} · {{ selectedRun.retrievalEvaluation.indexedDocumentCount }}</dd></div>
              <div><dt>Embedding 模型</dt><dd><code>{{ selectedRun.retrievalEvaluation.modelName }}</code></dd></div>
            </dl>
          </article>

          <article class="summary-card" data-testid="acceptance-run-differential">
            <p class="card-kicker">多身份差分 <span class="technical-label">MULTI-IDENTITY DIFFERENTIAL</span></p>
            <h4>{{ selectedRun.differentialAudits.length }} 项固定任务</h4>
            <div class="audit-list">
              <div v-for="audit in selectedRun.differentialAudits" :key="audit.id" class="audit-row">
                <span>
                  <strong>{{ audit.task.name }}</strong>
                  <small><code>{{ audit.targetProfileId }}</code> · {{ audit.rows.length }} 个操作人</small>
                </span>
                <span class="audit-status" :class="gateClass(audit.status)">{{ verdictLabel(audit.status) }} · {{ audit.mismatchCount }} 个差异</span>
              </div>
            </div>
          </article>

          <article class="summary-card" data-testid="acceptance-run-scan">
            <p class="card-kicker">引导式来源 → 数据去向 <span class="technical-label">GUIDED SOURCE → SINK</span></p>
            <h4>来源到数据去向检查 <code>{{ selectedRun.guidedScan.planId }}</code></h4>
            <dl class="fact-list">
              <div><dt>扫描</dt><dd>{{ scanStatusLabel(selectedRun.guidedScan.status) }} · {{ selectedRun.guidedScan.attempts.length }} 轮</dd></div>
              <div><dt>停止原因</dt><dd>{{ stopReasonLabel(selectedRun.guidedScan.stopReason) }}</dd></div>
              <div><dt>过程记录</dt><dd>{{ selectedRun.guidedScan.attempts.reduce((count, attempt) => count + attempt.queryResult.traceEvents.length, 0) }} 个事件，跨 {{ selectedRun.guidedScan.attempts.length }} 轮</dd></div>
            </dl>
          </article>

          <article class="summary-card" data-testid="acceptance-run-replay">
            <p class="card-kicker">同一计划修复复测 <span class="technical-label">SAME PLAN REPLAY</span></p>
            <h4 :class="gateClass(selectedRun.guidedReplay.status)">{{ verdictLabel(selectedRun.guidedReplay.status) }} · <code>{{ selectedRun.guidedReplay.plan.id }}</code></h4>
            <dl class="fact-list">
              <div><dt>修复前</dt><dd><span>{{ scanStatusLabel(selectedRun.guidedReplay.before.executionStatus) }}</span> · {{ evaluationStatusLabel(selectedRun.guidedReplay.before.evaluation.status) }} · {{ selectedRun.guidedReplay.before.evaluation.findings.length }} 个 Finding</dd></div>
              <div><dt>修复后</dt><dd><span>{{ scanStatusLabel(selectedRun.guidedReplay.after.executionStatus) }}</span> · {{ evaluationStatusLabel(selectedRun.guidedReplay.after.evaluation.status) }} · {{ selectedRun.guidedReplay.after.evaluation.findings.length }} 个 Finding</dd></div>
              <div><dt>规则路径</dt><dd><code>{{ selectedRun.guidedReplay.remediation.configurationPath }}</code></dd></div>
            </dl>
            <p class="card-caption" data-testid="acceptance-remediation-advisory">
              仅供参考：After 是内置 secure Profile 的模拟复测，不代表已定位企业系统根因或已修改生产配置。
            </p>
          </article>

          <article class="summary-card finding-card" data-testid="acceptance-run-findings">
            <p class="card-kicker">实际风险类别 <span class="technical-label">ACTUAL FINDING CATEGORIES</span></p>
            <h4>{{ selectedRun.findingCount }} 个风险发现 Findings</h4>
            <p class="category-copy">{{ findingCategoriesLabel(selectedRun.findingCategories) }}</p>
            <p class="card-caption">类别从 Differential、Benchmark、Scan 与 Replay 的实际结构化结果去重汇总；expected 不参与改写。</p>
          </article>
        </div>
      </section>
    </template>

    <section v-else-if="!historyLoading && summaries.length > 0" class="run-empty" data-testid="acceptance-run-empty">
      <span class="empty-mark" aria-hidden="true">◎</span>
      <p>选择一条历史运行记录查看完整权限契约、运行环境、就绪状态、质量门、风险发现和 Replay。</p>
    </section>

    <section v-if="comparison" class="comparison-section" data-testid="acceptance-run-comparison" aria-labelledby="comparison-title">
      <header class="section-heading">
        <div>
          <p class="acceptance-kicker">与上次运行对比</p>
          <h3 id="comparison-title">与上一次验收对比</h3>
          <p class="section-caption">只比较已保存快照，不读取 active Contract，不调用 Provider。</p>
        </div>
        <span v-if="comparison.previous" class="comparison-baseline">对照记录 Baseline {{ comparison.previous.id }}</span>
      </header>

      <div v-if="!comparison.previous" class="baseline-empty">
        <span class="empty-mark" aria-hidden="true">—</span>
        <div>
          <strong>首个 Run · 无 baseline</strong>
          <p>这是第一条历史验收记录，未伪造上一次结果；变化集保持为空。</p>
        </div>
      </div>
      <template v-else>
        <div class="comparison-summary-grid">
          <article data-testid="acceptance-comparison-current">
            <p class="comparison-subheading">当前运行记录 <span class="technical-label">CURRENT / RUN</span></p>
            <strong>{{ comparison.current.id }}</strong>
            <span>权限契约 {{ comparison.current.contractId }} · v{{ comparison.current.contractVersion }}</span>
            <span>质量门 {{ verdictLabel(comparison.current.gateStatus) }} · {{ comparison.current.benchmarkMatchedCaseCount }}/{{ comparison.current.benchmarkCaseCount }} 匹配 · 风险发现 {{ comparison.current.findingCount }}</span>
          </article>
          <article data-testid="acceptance-comparison-previous">
            <p class="comparison-subheading">上一次运行记录 <span class="technical-label">PREVIOUS / RUN</span></p>
            <strong>{{ comparison.previous.id }}</strong>
            <span>权限契约 {{ comparison.previous.contractId }} · v{{ comparison.previous.contractVersion }}</span>
            <span>质量门 {{ verdictLabel(comparison.previous.gateStatus) }} · {{ comparison.previous.benchmarkMatchedCaseCount }}/{{ comparison.previous.benchmarkCaseCount }} 匹配 · 风险发现 {{ comparison.previous.findingCount }}</span>
          </article>
        </div>

        <div class="comparison-state-grid">
          <div><span>权限契约 Contract</span><strong :class="comparison.contractChanged ? 'is-changed' : 'is-neutral'">{{ changedLabel(comparison.contractChanged) }}</strong></div>
          <div><span>运行环境 Runtime</span><strong :class="comparison.runtimeChanged ? 'is-changed' : 'is-neutral'">{{ changedLabel(comparison.runtimeChanged) }}</strong></div>
          <div><span>就绪状态 Readiness</span><strong :class="comparison.readinessChanged ? 'is-changed' : 'is-neutral'">{{ changedLabel(comparison.readinessChanged) }}</strong></div>
          <div><span>质量门 Gate</span><strong :class="comparison.gateStatusChanged ? 'is-changed' : 'is-neutral'">{{ changedLabel(comparison.gateStatusChanged) }}</strong></div>
        </div>

        <div class="metric-delta-list">
          <div class="comparison-subheading"><span>五项固定质量门指标</span><code>previous → current · delta</code></div>
          <div v-for="metric in comparison.gateMetricDeltas" :key="metric.id" class="metric-delta-row" :class="metricDeltaClass(metric)">
            <strong>{{ metricLabels[metric.id] ?? metric.id }}</strong>
            <code>{{ formatMetricValue(metric.id, metric.previous) }} → {{ formatMetricValue(metric.id, metric.current) }}</code>
            <span>{{ formatMetricDelta(metric) }}</span>
          </div>
        </div>

        <div class="change-grid">
          <article>
            <p class="comparison-subheading">未通过的检查 ID</p>
            <dl class="change-list">
              <div><dt>新增 <span class="technical-label">ADDED</span></dt><dd>{{ emptyListLabel(comparison.addedFailedCheckIds) }}</dd></div>
              <div><dt>已解决 <span class="technical-label">RESOLVED</span></dt><dd>{{ emptyListLabel(comparison.resolvedFailedCheckIds) }}</dd></div>
            </dl>
          </article>
          <article>
            <p class="comparison-subheading">不匹配的 Case ID</p>
            <dl class="change-list">
              <div><dt>新增 <span class="technical-label">ADDED</span></dt><dd>{{ emptyListLabel(comparison.addedMismatchedCaseIds) }}</dd></div>
              <div><dt>已解决 <span class="technical-label">RESOLVED</span></dt><dd>{{ emptyListLabel(comparison.resolvedMismatchedCaseIds) }}</dd></div>
            </dl>
          </article>
          <article>
            <p class="comparison-subheading">风险发现类别 Finding</p>
            <dl class="change-list">
              <div><dt>新增 <span class="technical-label">ADDED</span></dt><dd>{{ findingCategoriesLabel(comparison.addedFindingCategories) }}</dd></div>
              <div><dt>已解决 <span class="technical-label">RESOLVED</span></dt><dd>{{ findingCategoriesLabel(comparison.resolvedFindingCategories) }}</dd></div>
            </dl>
          </article>
        </div>
      </template>
    </section>
  </section>
</template>

<style scoped>
.acceptance-runs {
  --acceptance-ink-strong: var(--ink-strong, #132238);
  --acceptance-ink: var(--ink, #26364c);
  --acceptance-muted: var(--ink-muted, #64748b);
  --acceptance-faint: var(--ink-faint, #94a3b8);
  --acceptance-line: var(--line, #dbe4ef);
  --acceptance-surface: var(--surface, #ffffff);
  --acceptance-surface-raised: var(--surface-raised, #f8fafc);
  --acceptance-action: var(--action-blue, #4f7cff);
  --acceptance-accent: var(--evidence-teal, #25bfae);
  --acceptance-warning: var(--warning-amber, #e6a23c);
  --acceptance-danger: var(--risk-coral, #ff5d5d);
  width: 100%;
  max-width: 1180px;
  margin: 0 auto 42px;
  color: var(--acceptance-ink);
}

.acceptance-runs,
.acceptance-runs * {
  min-width: 0;
}

.acceptance-header,
.acceptance-boundary,
.acceptance-history,
.run-summary,
.comparison-section,
.acceptance-loading,
.acceptance-error {
  border: 1px solid var(--acceptance-line);
  border-radius: 14px;
  background: var(--acceptance-surface);
}

.acceptance-header {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(410px, 1.1fr);
  align-items: stretch;
  gap: clamp(20px, 2vw, 28px);
  min-height: 260px;
  padding: clamp(28px, 4vw, 48px);
  background:
    linear-gradient(135deg, rgba(79, 124, 255, 0.1), transparent 46%),
    var(--acceptance-surface);
  overflow: hidden;
}

.acceptance-header::before {
  position: absolute;
  z-index: 0;
  inset: 0;
  background: url("../assets/illustrations/acceptance-evidence-convergence.webp") center / cover no-repeat;
  content: "";
  opacity: 0.76;
  pointer-events: none;
}

.acceptance-header::after {
  position: absolute;
  z-index: 0;
  inset: 0;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.92) 0%, rgba(255, 255, 255, 0.76) 34%, rgba(255, 255, 255, 0.3) 64%, rgba(255, 255, 255, 0.16) 100%);
  content: "";
  pointer-events: none;
}

.acceptance-header-copy {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
}

.acceptance-kicker,
.card-kicker,
.comparison-subheading,
.section-count,
.section-caption,
.acceptance-error > span,
.fact-list dt,
.history-item-facts,
.history-item-heading small,
.download-row,
.acceptance-boundary,
.loading-mark {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

.acceptance-kicker {
  margin: 0;
  color: var(--acceptance-accent);
  font-size: var(--type-label-size, 12px);
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.acceptance-header h2 {
  margin: 10px 0 0;
  color: var(--acceptance-ink-strong);
  font-size: var(--type-page-title-size, 36px);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.2;
}

.acceptance-lede {
  max-width: 620px;
  margin: 14px 0 0;
  color: var(--acceptance-muted);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.acceptance-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 24px;
}

.acceptance-header-actions button,
.download-row a {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 39px;
  padding: 0 14px;
  border-radius: 8px;
  cursor: pointer;
  font-size: var(--type-body-small-size, 13px);
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
}

.acceptance-refresh {
  color: var(--acceptance-action);
  background: transparent;
  border: 1px solid rgba(79, 124, 255, 0.4);
}

.acceptance-run-button {
  min-width: 156px;
  color: #ffffff;
  background: var(--acceptance-action);
  border: 1px solid var(--acceptance-action);
  box-shadow: 0 12px 26px rgba(79, 124, 255, 0.22);
}

.acceptance-scope {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: center;
  flex-direction: column;
  padding: clamp(18px, 2.2vw, 26px);
  background: linear-gradient(90deg, rgba(247, 251, 255, 0.72), rgba(247, 251, 255, 0.38));
  border: 1px solid rgba(110, 148, 212, 0.25);
  border-radius: 13px;
  box-shadow: 0 18px 42px rgba(57, 91, 143, 0.1);
  overflow: hidden;
}

.acceptance-scope-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(110, 148, 212, 0.24);
}

.acceptance-scope-heading > span {
  color: var(--acceptance-ink-strong);
  font-size: var(--type-card-title-size, 18px);
  font-weight: 720;
}

.acceptance-scope-heading small,
.acceptance-scope-route {
  color: var(--acceptance-faint);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: var(--type-label-size, 12px);
}

.acceptance-scope-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 20px;
}

.acceptance-scope-metrics > span {
  display: grid;
  align-content: start;
  grid-template-columns: auto 1fr;
  gap: 8px;
  padding: 0 12px;
  border-left: 1px solid rgba(110, 148, 212, 0.24);
}

.acceptance-scope-metrics > span:first-child {
  padding-left: 0;
  border-left: 0;
}

.acceptance-scope-metrics strong {
  color: var(--acceptance-action);
  font-size: clamp(25px, 2.2vw, 34px);
  font-weight: 760;
  line-height: 1;
}

.acceptance-scope-metrics small {
  color: var(--acceptance-ink);
  font-size: var(--type-label-size, 12px);
  line-height: 1.35;
}

.acceptance-scope-route {
  margin: 20px 0 0;
  color: #496487;
  letter-spacing: 0.02em;
}

.acceptance-scope-route i {
  margin: 0 5px;
  color: var(--acceptance-accent);
  font-style: normal;
}

.acceptance-header-actions button:hover:not(:disabled),
.download-row a:hover {
  transform: translateY(-1px);
}

.acceptance-refresh:hover:not(:disabled) {
  background: #f1f5ff;
}

.acceptance-run-button:hover:not(:disabled) {
  background: #3f68df;
}

.acceptance-header-actions button:focus-visible,
.history-item:focus-visible,
.download-row a:focus-visible {
  outline: 2px solid var(--acceptance-action);
  outline-offset: 3px;
}

.acceptance-header-actions button:disabled {
  cursor: wait;
  opacity: 0.56;
}

.acceptance-boundary {
  margin-top: 11px;
  padding: 11px 14px;
  color: var(--acceptance-muted);
  font-size: 10px;
  line-height: 1.55;
}

.acceptance-boundary summary {
  width: fit-content;
  color: var(--acceptance-action);
  cursor: pointer;
  font-size: 9px;
  letter-spacing: 0.04em;
}

.acceptance-boundary > span {
  display: block;
  margin-top: 6px;
}

.acceptance-loading,
.acceptance-error,
.detail-loading {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-top: 11px;
  padding: 13px 15px;
  font-size: 11px;
  line-height: 1.55;
}

.acceptance-loading {
  border-color: rgba(230, 162, 60, 0.4);
}

.acceptance-loading strong,
.acceptance-loading small {
  display: block;
}

.acceptance-loading strong {
  color: var(--acceptance-ink-strong);
  font-size: 12px;
}

.acceptance-loading small {
  margin-top: 3px;
  color: var(--acceptance-muted);
  font-size: 10px;
}

.loading-mark,
.empty-mark {
  display: grid;
  width: 29px;
  height: 29px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--acceptance-warning);
  border: 1px solid rgba(230, 162, 60, 0.42);
  border-radius: 50%;
  font-size: 15px;
}

.empty-mark {
  color: var(--acceptance-faint);
  border-color: var(--acceptance-line);
}

.acceptance-error {
  color: #8f2d2d;
  background: #fff3f2;
  border-color: rgba(255, 93, 93, 0.35);
  overflow-wrap: anywhere;
}

.acceptance-error > span {
  flex: 0 0 auto;
  color: var(--acceptance-danger);
  font-size: 9px;
  letter-spacing: 0.07em;
}

.acceptance-history,
.run-summary,
.comparison-section {
  margin-top: 19px;
  padding: clamp(16px, 3vw, 25px);
}

.acceptance-history.is-empty {
  padding-bottom: clamp(16px, 2vw, 22px);
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 15px;
}

.section-heading h3 {
  margin: 6px 0 0;
  color: var(--acceptance-ink-strong);
  font-size: 18px;
  font-weight: 680;
  line-height: 1.3;
}

.section-caption {
  margin: 6px 0 0;
  color: var(--acceptance-muted);
  font-size: 10px;
  line-height: 1.45;
}

.section-count,
.comparison-baseline {
  color: var(--acceptance-faint);
  font-size: 9px;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.history-placeholder,
.run-empty {
  display: flex;
  align-items: center;
  gap: 11px;
  min-height: 85px;
  margin-top: 14px;
  color: var(--acceptance-muted);
  font-size: 11px;
  line-height: 1.55;
}

.acceptance-history.is-empty .history-placeholder {
  min-height: 0;
}

.history-empty {
  display: grid;
  align-items: center;
  grid-template-columns: auto minmax(220px, 1fr) auto;
  gap: 14px;
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--acceptance-line);
}

.history-empty .empty-mark {
  color: var(--acceptance-action);
  border-color: rgba(79, 124, 255, 0.35);
  font-size: 10px;
}

.history-empty-copy {
  display: grid;
  gap: 3px;
}

.history-empty-copy strong {
  color: var(--acceptance-ink-strong);
  font-size: var(--type-body-size, 15px);
}

.history-empty-copy small {
  color: var(--acceptance-muted);
  font-size: var(--type-body-small-size, 13px);
}

.history-empty-outputs {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
}

.history-empty-outputs > span {
  padding: 6px 9px;
  color: #496487;
  background: #f4f7fc;
  border: 1px solid rgba(110, 148, 212, 0.2);
  border-radius: 999px;
  font-size: var(--type-label-size, 12px);
}

.history-list {
  display: grid;
  gap: 7px;
  margin-top: 14px;
}

.history-item {
  display: block;
  width: 100%;
  padding: 13px 14px;
  color: var(--acceptance-ink);
  text-align: left;
  background: var(--acceptance-surface-raised);
  border: 1px solid var(--acceptance-line);
  border-radius: 9px;
  cursor: pointer;
}

.history-item:hover,
.history-item.is-selected {
  background: #f1f5ff;
  border-color: rgba(79, 124, 255, 0.5);
}

.history-item-heading,
.history-item-heading > span,
.summary-statuses,
.download-row,
.comparison-subheading,
.metric-delta-row,
.audit-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.history-item-heading > span:first-child {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.history-item-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 5px;
}

.latest-badge {
  color: var(--acceptance-accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  letter-spacing: 0.04em;
}

.history-item-heading strong {
  overflow-wrap: anywhere;
  color: var(--acceptance-ink-strong);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
}

.history-item-heading small {
  color: var(--acceptance-faint);
  font-size: 9px;
}

.status-pill,
.audit-status,
.summary-card h4.is-ready,
.summary-card h4.is-partial,
.summary-card h4.is-unavailable,
.summary-card h4.is-passed,
.summary-card h4.is-failed {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 5px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  line-height: 1.2;
  white-space: nowrap;
}

.status-pill.is-passed,
.status-pill.is-ready,
.summary-card h4.is-ready,
.summary-card h4.is-passed,
.audit-status.is-passed {
  color: #087f73;
  background: #e9fbf7;
  border-color: rgba(37, 191, 174, 0.34);
}

.status-pill.is-failed,
.status-pill.is-unavailable,
.summary-card h4.is-unavailable,
.summary-card h4.is-failed,
.audit-status.is-failed {
  color: #a33a3a;
  background: #fff3f2;
  border-color: rgba(255, 93, 93, 0.32);
}

.status-pill.is-neutral,
.status-pill.is-partial,
.summary-card h4.is-partial {
  color: #8a5b11;
  background: #fff8e8;
  border-color: rgba(230, 162, 60, 0.4);
}

.history-item-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 15px;
  margin-top: 11px;
  color: var(--acceptance-faint);
  font-size: 9px;
}

code {
  color: var(--acceptance-accent);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.detail-loading {
  color: var(--acceptance-muted);
  border: 1px solid var(--acceptance-line);
  border-radius: 10px;
  background: var(--acceptance-surface-raised);
}

.summary-statuses {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.download-row {
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 15px;
  padding: 10px 0 0;
  color: var(--acceptance-muted);
  border-top: 1px solid var(--acceptance-line);
  font-size: 9px;
}

.download-row a {
  min-height: 30px;
  color: var(--acceptance-action);
  background: #f1f5ff;
  border: 1px solid rgba(79, 124, 255, 0.3);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 15px;
}

.summary-card {
  min-width: 0;
  padding: 14px;
  background: var(--acceptance-surface-raised);
  border: 1px solid var(--acceptance-line);
  border-radius: 9px;
}

.summary-card.finding-card {
  background: #fff3f2;
  border-color: rgba(255, 93, 93, 0.28);
}

.card-kicker {
  margin: 0;
  color: var(--acceptance-accent);
  font-size: 9px;
  letter-spacing: 0.06em;
}

.summary-card h4 {
  max-width: 100%;
  margin: 7px 0 0;
  color: var(--acceptance-ink-strong);
  font-size: 14px;
  font-weight: 680;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.summary-card h4.is-ready,
.summary-card h4.is-partial,
.summary-card h4.is-unavailable,
.summary-card h4.is-passed,
.summary-card h4.is-failed {
  display: inline-flex;
}

.card-caption,
.category-copy {
  margin: 8px 0 0;
  color: var(--acceptance-muted);
  font-size: 10px;
  line-height: 1.55;
}

.category-copy {
  color: var(--acceptance-ink);
  overflow-wrap: anywhere;
}

.fact-list {
  display: grid;
  gap: 6px;
  margin: 13px 0 0;
}

.fact-list > div {
  display: grid;
  grid-template-columns: minmax(72px, 0.43fr) minmax(0, 1fr);
  gap: 8px;
  padding: 7px 8px;
  background: var(--acceptance-surface);
  border: 1px solid var(--acceptance-line);
  border-radius: 6px;
}

.fact-list dt {
  color: var(--acceptance-faint);
  font-size: 8px;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.fact-list dd {
  display: grid;
  gap: 4px;
  margin: 0;
  color: var(--acceptance-ink);
  font-size: 10px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.fact-list dd span {
  width: fit-content;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
}

.fact-list dd span.is-ready {
  color: var(--acceptance-accent);
}

.fact-list dd span.is-partial {
  color: var(--acceptance-warning);
}

.fact-list dd span.is-unavailable {
  color: var(--acceptance-danger);
}

.snapshot-details {
  margin-top: 10px;
  color: var(--acceptance-muted);
  font-size: 10px;
}

.snapshot-details summary {
  cursor: pointer;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}

.chip-list code {
  padding: 3px 5px;
  background: var(--acceptance-surface);
  border: 1px solid var(--acceptance-line);
  border-radius: 4px;
}

.check-list,
.audit-list {
  display: grid;
  gap: 6px;
  margin-top: 12px;
}

.check-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 6px 8px;
  padding: 7px 8px;
  border-left: 2px solid var(--acceptance-accent);
  background: var(--acceptance-surface);
  border-radius: 5px;
}

.check-row.is-failed {
  border-left-color: var(--acceptance-danger);
}

.check-row > span {
  color: var(--acceptance-accent);
}

.check-row.is-failed > span {
  color: var(--acceptance-danger);
}

.check-row strong {
  color: var(--acceptance-ink);
  font-size: 10px;
  font-weight: 600;
}

.check-row code {
  grid-column: 2;
  color: var(--acceptance-faint);
  font-size: 8px;
}

.audit-row {
  align-items: flex-start;
  padding: 8px;
  background: var(--acceptance-surface);
  border: 1px solid var(--acceptance-line);
  border-radius: 6px;
}

.audit-row > span:first-child {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.audit-row strong {
  color: var(--acceptance-ink);
  font-size: 10px;
  overflow-wrap: anywhere;
}

.audit-row small {
  color: var(--acceptance-faint);
  font-size: 8px;
}

.comparison-section {
  margin-top: 19px;
}

.comparison-baseline {
  padding: 5px 8px;
  color: #087f73;
  background: #e9fbf7;
  border: 1px solid rgba(37, 191, 174, 0.3);
  border-radius: 999px;
}

.baseline-empty {
  display: flex;
  align-items: center;
  gap: 11px;
  min-height: 90px;
  margin-top: 15px;
  color: var(--acceptance-muted);
  font-size: 11px;
}

.baseline-empty strong {
  color: var(--acceptance-ink-strong);
}

.baseline-empty p {
  margin: 5px 0 0;
  line-height: 1.5;
}

.comparison-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  margin-top: 15px;
}

.comparison-summary-grid article {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 10px;
  background: var(--acceptance-surface-raised);
  border: 1px solid var(--acceptance-line);
  border-radius: 7px;
}

.comparison-summary-grid article > strong {
  color: var(--acceptance-ink-strong);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
  overflow-wrap: anywhere;
}

.comparison-summary-grid article > span {
  color: var(--acceptance-muted);
  font-size: 9px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.comparison-state-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  margin-top: 15px;
}

.comparison-state-grid > div {
  display: grid;
  gap: 6px;
  padding: 9px 10px;
  background: var(--acceptance-surface-raised);
  border: 1px solid var(--acceptance-line);
  border-radius: 6px;
}

.comparison-state-grid span {
  color: var(--acceptance-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
}

.comparison-state-grid strong {
  color: var(--acceptance-accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.comparison-state-grid strong.is-changed {
  color: var(--acceptance-warning);
}

.comparison-state-grid strong.is-neutral {
  color: var(--acceptance-muted);
}

.metric-delta-list {
  margin-top: 15px;
  padding-top: 14px;
  border-top: 1px solid var(--acceptance-line);
}

.comparison-subheading {
  margin: 0;
  color: var(--acceptance-accent);
  font-size: 9px;
  letter-spacing: 0.04em;
}

.comparison-subheading code {
  color: var(--acceptance-faint);
  font-size: 8px;
}

.metric-delta-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(190px, auto) minmax(92px, auto);
  margin-top: 6px;
  padding: 9px 10px;
  background: var(--acceptance-surface-raised);
  border: 1px solid var(--acceptance-line);
  border-radius: 6px;
}

.metric-delta-row strong {
  color: var(--acceptance-ink);
  font-size: 10px;
}

.metric-delta-row code,
.metric-delta-row > span {
  color: var(--acceptance-muted);
  font-size: 9px;
  text-align: right;
}

.metric-delta-row.is-positive > span {
  color: var(--acceptance-accent);
}

.metric-delta-row.is-negative > span {
  color: var(--acceptance-danger);
}

.change-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
  margin-top: 15px;
  padding-top: 14px;
  border-top: 1px solid var(--acceptance-line);
}

.change-grid article {
  min-width: 0;
  padding: 10px;
  background: var(--acceptance-surface-raised);
  border: 1px solid var(--acceptance-line);
  border-radius: 7px;
}

.change-list {
  display: grid;
  gap: 7px;
  margin: 9px 0 0;
}

.change-list > div {
  display: grid;
  gap: 4px;
}

.change-list dt {
  color: var(--acceptance-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  text-transform: uppercase;
}

.change-list dd {
  margin: 0;
  color: var(--acceptance-ink);
  font-size: 10px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

@media (max-width: 760px) {
  .acceptance-header {
    grid-template-columns: 1fr;
    gap: 17px;
  }

  .acceptance-header::before {
    background-position: 68% center;
    opacity: 0.58;
  }

  .acceptance-header-actions {
    width: 100%;
  }

  .acceptance-header-actions button {
    flex: 1 1 50%;
  }

  .acceptance-scope-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px 0;
  }

  .acceptance-scope-metrics > span:nth-child(3) {
    padding-left: 0;
    border-left: 0;
  }

  .history-empty {
    align-items: start;
    grid-template-columns: auto 1fr;
  }

  .history-empty-outputs {
    grid-column: 2;
    justify-content: flex-start;
  }

  .acceptance-boundary {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .summary-grid,
  .comparison-summary-grid,
  .change-grid {
    grid-template-columns: 1fr;
  }

  .comparison-state-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 480px) {
  .acceptance-header,
  .acceptance-boundary,
  .acceptance-history,
  .run-summary,
  .comparison-section,
  .acceptance-loading,
  .acceptance-error {
    border-radius: 10px;
  }

  .acceptance-header-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .acceptance-header-actions button {
    width: 100%;
  }

  .acceptance-scope-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .acceptance-scope-metrics {
    grid-template-columns: 1fr;
  }

  .acceptance-scope-metrics > span,
  .acceptance-scope-metrics > span:nth-child(3) {
    padding: 9px 0;
    border-top: 1px solid rgba(110, 148, 212, 0.24);
    border-left: 0;
  }

  .acceptance-scope-metrics > span:first-child {
    padding-top: 0;
    border-top: 0;
  }

  .acceptance-scope-route {
    line-height: 1.7;
  }

  .history-empty {
    grid-template-columns: 1fr;
  }

  .history-empty .empty-mark,
  .history-empty-outputs {
    grid-column: 1;
  }

  .history-item-heading,
  .section-heading,
  .metric-delta-row {
    align-items: flex-start;
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .history-item-heading {
    display: flex;
  }

  .summary-statuses {
    justify-content: flex-start;
  }

  .comparison-baseline {
    white-space: normal;
  }

  .comparison-state-grid {
    grid-template-columns: 1fr;
  }

  .metric-delta-row {
    display: grid;
    gap: 5px;
  }

  .metric-delta-row code,
  .metric-delta-row > span {
    text-align: left;
  }

  .fact-list > div {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .audit-row {
    align-items: flex-start;
    flex-direction: column;
  }
}

/* F-061: Chinese conclusion layer first; technical IDs and raw values stay compact. */
.acceptance-kicker,
.card-kicker,
.comparison-subheading,
.section-count,
.section-caption,
.acceptance-error > span,
.fact-list dt,
.download-row,
.history-item-facts,
.history-item-heading small {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.technical-label {
  margin-left: 6px;
  color: var(--acceptance-faint);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.03em;
}

.acceptance-boundary {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.acceptance-boundary summary {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
}

.acceptance-loading,
.acceptance-error,
.detail-loading,
.history-placeholder,
.run-empty,
.baseline-empty {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.acceptance-loading strong {
  font-size: var(--type-body-size, 15px);
}

.acceptance-loading small {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.acceptance-error > span {
  font-weight: 700;
}

.acceptance-scope-heading small,
.acceptance-scope-route,
.acceptance-scope-metrics small {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.history-item-heading small,
.history-item-facts,
.latest-badge {
  font-size: var(--type-label-size, 12px);
}

.status-pill,
.audit-status,
.summary-card h4.is-ready,
.summary-card h4.is-partial,
.summary-card h4.is-unavailable,
.summary-card h4.is-passed,
.summary-card h4.is-failed {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.download-row {
  font-size: var(--type-body-small-size, 13px);
}

.card-kicker {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 2px;
}

.card-caption,
.category-copy,
.fact-list dd,
.check-row strong,
.audit-row strong,
.comparison-summary-grid article > span,
.metric-delta-row > span,
.change-list dd {
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.fact-list dt,
.fact-list dd span,
.check-row strong,
.audit-row small,
.comparison-state-grid span,
.comparison-state-grid strong,
.change-list dt {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
  letter-spacing: normal;
  text-transform: none;
}

.fact-list dd {
  font-family: var(--font-ui, system-ui, sans-serif);
}

.snapshot-details {
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-body-small-size, 13px);
}

/* F-062: retain the local evidence artwork as a quiet side rail while the
   acceptance copy remains the primary reading surface. */
.acceptance-runs {
  max-width: 100%;
}

.acceptance-header,
.acceptance-history,
.run-summary,
.comparison-section {
  border-radius: 10px;
  box-shadow: none;
}

.acceptance-header {
  min-height: 0;
  padding: clamp(20px, 2vw, 28px);
  background: var(--acceptance-surface);
}

.acceptance-header::before {
  inset: 14px 14px 14px auto;
  width: min(38%, 520px);
  border-radius: 8px;
  background-position: center;
  background-size: cover;
  opacity: 0.28;
}

.acceptance-header::after {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.98) 0%,
    rgba(255, 255, 255, 0.94) 48%,
    rgba(255, 255, 255, 0.58) 100%
  );
}

.acceptance-header-copy,
.acceptance-scope {
  z-index: 2;
}

.acceptance-scope {
  box-shadow: none;
  border-radius: 9px;
  background: var(--acceptance-surface-raised);
}

.acceptance-kicker {
  color: var(--acceptance-muted);
}

.technical-label {
  margin-left: 6px;
  color: var(--acceptance-faint);
  font-family: var(--font-ui, system-ui, sans-serif);
  font-size: var(--type-label-size, 12px);
  font-weight: 600;
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.acceptance-lede,
.acceptance-boundary,
.acceptance-loading,
.acceptance-error,
.history-empty-copy small,
.card-caption,
.category-copy,
.fact-list dd,
.audit-row strong,
.comparison-summary-grid article > span,
.change-list dd {
  font-size: max(13px, var(--type-body-small-size, 13px));
  line-height: var(--type-body-small-leading, 1.55);
}

.acceptance-header-actions button,
.download-row a {
  min-height: 40px;
  font-size: max(13px, var(--type-body-small-size, 13px));
}

.summary-card,
.comparison-summary-grid article,
.comparison-state-grid > div,
.change-grid article {
  border-radius: 8px;
  box-shadow: none;
}

@media (max-width: 760px) {
  .acceptance-header::before {
    inset: auto 14px 14px;
    width: auto;
    height: 108px;
    opacity: 0.14;
  }

  .acceptance-header::after {
    background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.98) 0%,
      rgba(255, 255, 255, 0.9) 64%,
      rgba(255, 255, 255, 0.7) 100%
    );
  }
}

/* F-063: Acceptance is an evidence summary, not a wall of technical cards.
 * Keep the approved convergence artwork bounded in the header rail, flatten
 * nested rows into sections, and reserve compact typography for raw evidence. */
.acceptance-runs {
  --acceptance-line: var(--line, #dce5ef);
  --acceptance-surface: var(--surface, #ffffff);
  --acceptance-surface-raised: var(--surface-raised, #f8fafc);
  font-family: var(--font-ui);
  font-size: var(--type-body-size, 16px);
  line-height: var(--type-body-leading, 1.62);
}

.acceptance-header,
.acceptance-history,
.run-summary,
.comparison-section {
  border-radius: var(--radius-card, 12px);
  box-shadow: var(--shadow-card, 0 12px 30px rgba(35, 68, 120, 0.08));
}

.acceptance-header h2 {
  font-size: var(--type-page-title-size, 32px);
  line-height: var(--type-heading-leading, 1.22);
}

.acceptance-lede {
  font-size: var(--type-body-size, 16px);
  line-height: var(--type-body-leading, 1.62);
}

.acceptance-kicker,
.card-kicker,
.comparison-subheading,
.section-count,
.section-caption,
.acceptance-error > span,
.fact-list dt,
.history-item-heading small,
.download-row,
.acceptance-boundary,
.loading-mark,
.technical-label {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
  letter-spacing: normal;
}

.section-caption,
.acceptance-boundary,
.acceptance-loading,
.acceptance-error,
.history-placeholder,
.run-empty,
.history-item-facts,
.card-caption,
.category-copy,
.fact-list dd,
.check-row strong,
.audit-row strong,
.baseline-empty,
.baseline-empty p,
.comparison-summary-grid article > span,
.metric-delta-row > span,
.change-list dd {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.acceptance-header-actions button,
.download-row a {
  min-height: 44px;
  border-radius: var(--radius-control, 9px);
  font-size: var(--type-body-small-size, 14px);
}

.status-pill,
.audit-status,
.summary-card h4.is-ready,
.summary-card h4.is-partial,
.summary-card h4.is-unavailable,
.summary-card h4.is-passed,
.summary-card h4.is-failed {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.acceptance-runs code,
.history-item-heading strong,
.comparison-summary-grid article > strong,
.metric-delta-row code,
.comparison-subheading code {
  font-family: var(--font-code);
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
}

.summary-grid {
  gap: 0 24px;
}

.summary-card,
.summary-card.finding-card,
.comparison-summary-grid article,
.comparison-state-grid > div,
.change-grid article,
.check-row,
.audit-row,
.fact-list > div,
.chip-list code,
.metric-delta-row {
  box-shadow: none;
}

.summary-card {
  padding: var(--space-4, 16px) 0;
  background: transparent;
  border: 0;
  border-top: 1px solid var(--acceptance-line);
  border-radius: 0;
}

.summary-card.finding-card {
  padding-right: var(--space-4, 16px);
  padding-left: var(--space-4, 16px);
  background: var(--risk-coral-wash, rgba(255, 93, 93, 0.1));
  border-top-color: var(--risk-coral, #ff5d5d);
}

.summary-card h4 {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.fact-list > div,
.comparison-summary-grid article,
.comparison-state-grid > div,
.change-grid article,
.check-row,
.audit-row,
.metric-delta-row {
  background: transparent;
  border-color: var(--acceptance-line);
  border-radius: 0;
}

.fact-list > div {
  padding-right: 0;
  padding-left: 0;
  border-right: 0;
  border-left: 0;
}

.fact-list dd span {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
}

.status-pill.is-passed,
.status-pill.is-ready,
.audit-status.is-passed {
  color: var(--evidence-teal-strong, #08786e);
  background: var(--evidence-teal-wash, rgba(22, 143, 130, 0.1));
}

.status-pill.is-failed,
.status-pill.is-unavailable,
.audit-status.is-failed {
  color: var(--risk-coral-strong, #c63d46);
  background: var(--risk-coral-wash, rgba(255, 93, 93, 0.1));
}

.status-pill.is-neutral,
.status-pill.is-partial {
  color: var(--warning-amber, #e6a23c);
  background: var(--warning-amber-wash, rgba(230, 162, 60, 0.14));
}

.acceptance-runs :is(button, a):focus-visible {
  outline: 2px solid var(--action-blue, #4f7cff);
  outline-offset: 3px;
}

/* F-063 second visual pass: keep the evidence summary readable when the
 * compact mobile type tokens are active. Disclosure rows are real controls,
 * so their hit area must remain usable even while their body stays collapsed. */
.acceptance-scope-heading small,
.acceptance-scope-route {
  font-size: max(13px, var(--type-label-size, 13px));
  line-height: 1.45;
}

.acceptance-scope-metrics small,
.history-empty-copy small,
.history-empty-outputs > span,
.acceptance-boundary,
.acceptance-header-actions button,
.download-row a {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.acceptance-boundary summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 10px 0;
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

@media (max-width: 760px) {
  /* The scope is the second column of the desktop header. On a narrow screen
   * it becomes the continuation of that same surface, not another card. */
  .acceptance-scope {
    padding: 0;
    background: transparent;
    border: 0;
    box-shadow: none;
  }
}

</style>
