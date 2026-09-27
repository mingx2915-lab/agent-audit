<script setup lang="ts">
import { computed } from "vue";
import type {
  AttackPlanBasisType,
  PlanCompatibilityResult,
  ProviderProbeId,
  ProviderProbeResult,
  ProviderReadinessResult,
  ProviderReadinessStatus,
  ProviderRoleReadiness,
} from "@agent-audit/contracts";

const props = withDefaults(
  defineProps<{
    result: ProviderReadinessResult | null;
    loading: boolean;
    error: string;
    title?: string;
    titleId?: string;
    lede?: string;
    runLabel?: string;
    runTestId?: string;
    runDisabled?: boolean;
    presentation?: "full" | "candidate";
  }>(),
  {
    title: "模型运行就绪检查",
    titleId: "provider-readiness-title",
    lede: "运行一次检查，确认当前模型能完成验收。",
    runLabel: "检查 Provider 就绪",
    runTestId: "run-provider-readiness",
    runDisabled: false,
    presentation: "full",
  },
);

const emit = defineEmits<{
  (event: "run"): void;
}>();

type ProviderRoleEntry = {
  key: "target" | "attack";
  title: string;
  description: string;
  provider: ProviderRoleReadiness;
};

type CandidateProbeSlot = {
  id: ProviderProbeId;
  testId: string;
  label: string;
  description: string;
};

type CandidateProbeState = "unchecked" | "loading" | ProviderProbeResult["status"];

type CandidateProbeView = CandidateProbeSlot & {
  probe: ProviderProbeResult | null;
  state: CandidateProbeState;
};

const isCandidate = computed(() => props.presentation === "candidate");

const candidateProbeSlots: readonly CandidateProbeSlot[] = [
  {
    id: "target.connectivity",
    testId: "target-connectivity",
    label: "目标连通性",
    description: "Target connectivity",
  },
  {
    id: "target.tool_calling",
    testId: "target-tool-calling",
    label: "目标工具调用",
    description: "Target Tool Calling",
  },
  {
    id: "attack.connectivity",
    testId: "attack-connectivity",
    label: "攻击连通性",
    description: "Attack connectivity",
  },
  {
    id: "attack.strict_json",
    testId: "attack-strict-json",
    label: "严格 JSON",
    description: "Attack strict JSON",
  },
];

const statusLabels: Record<ProviderReadinessStatus, string> = {
  ready: "READY · 已就绪",
  partial: "PARTIAL · 部分兼容",
  unavailable: "UNAVAILABLE · 不可用",
};

const statusDescriptions: Record<ProviderReadinessStatus, string> = {
  ready: "必需能力已通过。",
  partial: "部分能力通过，仍有失败项。",
  unavailable: "探针均未通过。",
};

const overallStatusDescriptions: Record<ProviderReadinessStatus, string> = {
  ready: "两侧 Provider 的必需能力已通过。",
  partial: "至少一侧仍有能力未通过。",
  unavailable: "两侧 Provider 都未通过探针。",
};

const probeLabels: Record<ProviderProbeId, string> = {
  "target.connectivity": "Connectivity · 连通性",
  "target.tool_calling": "Native Tool Calling · 原生 Tool Calling",
  "attack.connectivity": "Connectivity · 连通性",
  "attack.strict_json": "Strict JSON · 严格 JSON",
};

const basisLabels: Record<AttackPlanBasisType, string> = {
  resource_owner_scope: "Resource owner-match",
  tool_owner_scope: "Tool owner-match",
  source_sink: "Source → Sink",
  tool_record_limit: "Tool record limit",
};

const providerEntries = computed<ProviderRoleEntry[]>(() => {
  if (!props.result) {
    return [];
  }

  return [
    {
      key: "target",
      title: "Target Provider",
      description: "执行请求，并按权限决定是否调用工具。",
      provider: props.result.targetProvider,
    },
    {
      key: "attack",
      title: "Attack Provider",
      description: "生成受控攻击消息，返回结构化结果。",
      provider: props.result.attackProvider,
    },
  ];
});

const candidateProbeViews = computed<CandidateProbeView[]>(() =>
  candidateProbeSlots.map((slot) => {
    const provider = slot.id.startsWith("target.")
      ? props.result?.targetProvider
      : props.result?.attackProvider;
    const probe = provider?.probes.find((candidate) => candidate.id === slot.id) ?? null;

    let state: CandidateProbeState = "unchecked";
    if (props.loading) {
      state = "loading";
    } else if (probe) {
      state = probe.status;
    }

    return { ...slot, probe, state };
  }),
);

function statusLabel(status: ProviderReadinessStatus): string {
  return statusLabels[status];
}

function statusDescription(status: ProviderReadinessStatus): string {
  return statusDescriptions[status];
}

function overallStatusDescription(status: ProviderReadinessStatus): string {
  return overallStatusDescriptions[status];
}

function statusClass(status: ProviderReadinessStatus): string {
  return `is-${status}`;
}

function probeLabel(probe: ProviderProbeResult): string {
  return probeLabels[probe.id] ?? probe.id;
}

function probeStatusLabel(status: ProviderProbeResult["status"]): string {
  return status === "passed" ? "PASSED · 通过" : "FAILED · 失败";
}

function probeStatusClass(status: ProviderProbeResult["status"]): string {
  return status === "passed" ? "is-passed" : "is-failed";
}

function formatDuration(durationMs: number): string {
  if (!Number.isFinite(durationMs)) {
    return String(durationMs);
  }

  return `${Number.isInteger(durationMs) ? durationMs : durationMs.toFixed(2)} ms`;
}

function detailLabel(probe: ProviderProbeResult): string {
  if (probe.detail?.trim()) {
    return probe.detail;
  }

  return probe.status === "passed" ? "探针通过，无错误诊断。" : "Provider 未提供错误诊断。";
}

function basisLabel(basisType: AttackPlanBasisType): string {
  return basisLabels[basisType] ?? basisType;
}

function probeIdsLabel(probeIds: ProviderProbeId[]): string {
  return probeIds.length > 0 ? probeIds.join(" · ") : "—";
}

function planStatusLabel(status: PlanCompatibilityResult["status"]): string {
  return status === "compatible" ? "COMPATIBLE · 兼容" : "INCOMPATIBLE · 不兼容";
}

function planStatusClass(status: PlanCompatibilityResult["status"]): string {
  return status === "compatible" ? "is-compatible" : "is-incompatible";
}

function providerModel(provider: ProviderRoleReadiness): string {
  return provider.model ?? "未配置模型";
}

function candidateOverallLabel(): string {
  if (props.loading) {
    return "… 检查中";
  }

  return props.result ? statusLabel(props.result.status) : "未检查";
}

function candidateOverallClass(): string {
  if (props.loading) {
    return "is-loading";
  }

  return props.result ? statusClass(props.result.status) : "is-unchecked";
}

function candidateOverallDescription(): string {
  if (props.loading) {
    return "四项能力检查中。";
  }

  return props.result ? overallStatusDescription(props.result.status) : "完成一次显式检查后显示结果。";
}

function candidateProbeStatusLabel(state: CandidateProbeState): string {
  if (state === "loading") {
    return "检查中";
  }

  if (state === "unchecked") {
    return "— 未检查";
  }

  return state === "passed" ? "✓ 通过" : "! 未通过";
}

function candidateProbeStatusClass(state: CandidateProbeState): string {
  if (state === "loading") {
    return "is-loading";
  }

  if (state === "unchecked") {
    return "is-unchecked";
  }

  return state === "passed" ? "is-passed" : "is-failed";
}
</script>

<template>
  <section
    class="provider-readiness"
    :class="{ 'is-candidate': isCandidate }"
    :aria-labelledby="props.titleId"
  >
    <template v-if="isCandidate">
      <section class="candidate-readiness-card" data-testid="provider-readiness-result" aria-live="polite">
        <header class="candidate-readiness-header">
          <div class="readiness-heading">
            <p class="readiness-kicker">运行状态</p>
            <h2 :id="props.titleId">{{ props.title }}</h2>
            <p class="readiness-lede">{{ props.lede }}</p>
          </div>

          <div class="candidate-readiness-controls">
            <div class="candidate-overall">
              <span class="candidate-overall-label">总状态</span>
              <span class="overall-status" :class="candidateOverallClass()">
                {{ candidateOverallLabel() }}
              </span>
              <span class="candidate-overall-description">{{ candidateOverallDescription() }}</span>
            </div>
            <button
              class="readiness-run"
              :data-testid="props.runTestId"
              type="button"
              :disabled="props.loading || props.runDisabled"
              :aria-busy="props.loading"
              @click="emit('run')"
            >
              {{ props.loading ? "检查中…" : props.result ? "重新检查" : props.runLabel }}
            </button>
          </div>
        </header>

        <div class="candidate-probe-grid" aria-label="四项 Readiness 探针">
          <article
            v-for="slot in candidateProbeViews"
            :key="slot.id"
            class="candidate-probe-slot"
            :class="candidateProbeStatusClass(slot.state)"
            :data-testid="`provider-readiness-probe-${slot.testId}`"
          >
            <div class="candidate-probe-copy">
              <strong>{{ slot.label }}</strong>
              <span>{{ slot.description }}</span>
            </div>
            <span
              class="candidate-probe-status"
              :class="candidateProbeStatusClass(slot.state)"
              :data-testid="`provider-readiness-probe-${slot.testId}-status`"
            >
              {{ candidateProbeStatusLabel(slot.state) }}
            </span>
          </article>
        </div>

        <div v-if="props.error" class="readiness-error candidate-readiness-error" role="alert">
          <span class="readiness-error-label">READINESS ERROR</span>
          <p>{{ props.error }}</p>
        </div>

        <details class="candidate-technical-details" data-testid="provider-readiness-technical-details">
          <summary>查看技术详情</summary>
          <div v-if="props.result" class="candidate-technical-body">
            <dl class="result-meta candidate-result-meta">
              <div>
                <dt>Readiness ID</dt>
                <dd><code>{{ props.result.id }}</code></dd>
              </div>
              <div>
                <dt>Checked at</dt>
                <dd><code>{{ props.result.checkedAt }}</code></dd>
              </div>
              <div>
                <dt>Evidence boundary</dt>
                <dd>能力证据，不是安全 Finding</dd>
              </div>
            </dl>

            <div class="provider-grid candidate-provider-grid" aria-label="Provider role readiness">
              <article
                v-for="entry in providerEntries"
                :key="entry.key"
                class="provider-card candidate-provider-card"
                :class="`provider-${entry.key}`"
              >
                <header class="provider-card-header">
                  <div>
                    <p class="provider-card-kicker">{{ entry.key.toUpperCase() }} ROLE</p>
                    <h3>{{ entry.title }}</h3>
                    <p>{{ entry.description }}</p>
                  </div>
                  <span class="role-status" :class="statusClass(entry.provider.status)">
                    {{ statusLabel(entry.provider.status) }}
                  </span>
                </header>

                <dl class="provider-facts">
                  <div>
                    <dt>Provider</dt>
                    <dd><code>{{ entry.provider.provider }}</code></dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd><code>{{ providerModel(entry.provider) }}</code></dd>
                  </div>
                  <div>
                    <dt>Role</dt>
                    <dd><code>{{ entry.provider.role }}</code><span>{{ entry.title }}</span></dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd><code>{{ entry.provider.status }}</code><span>{{ statusDescription(entry.provider.status) }}</span></dd>
                  </div>
                </dl>

                <div class="probe-section">
                  <div class="subheading">
                    <div>
                      <p>能力探针</p>
                      <span>每项执行一次</span>
                    </div>
                    <code>{{ entry.provider.probes.length }} probes</code>
                  </div>

                  <div v-if="entry.provider.probes.length > 0" class="probe-list">
                    <article
                      v-for="probe in entry.provider.probes"
                      :key="probe.id"
                      class="probe-card"
                      :class="probeStatusClass(probe.status)"
                    >
                      <div class="probe-heading">
                        <div>
                          <strong>{{ probeLabel(probe) }}</strong>
                          <code>{{ probe.id }}</code>
                        </div>
                        <span class="probe-status" :class="probeStatusClass(probe.status)">
                          {{ probeStatusLabel(probe.status) }}
                        </span>
                      </div>
                      <dl class="probe-facts">
                        <div>
                          <dt>Status</dt>
                          <dd><code>{{ probe.status }}</code></dd>
                        </div>
                        <div>
                          <dt>Duration</dt>
                          <dd><code>{{ formatDuration(probe.durationMs) }}</code></dd>
                        </div>
                      </dl>
                      <div class="probe-detail">
                        <span>Detail</span>
                        <p>{{ detailLabel(probe) }}</p>
                      </div>
                    </article>
                  </div>
                  <p v-else class="empty-copy">本次 Provider 没有返回探针记录。</p>
                </div>
              </article>
            </div>

            <section class="compatibility-section candidate-compatibility-section" aria-labelledby="candidate-compatibility-title">
              <div class="subheading compatibility-heading">
                <div>
                  <p class="readiness-kicker">计划兼容性</p>
                  <h3 id="candidate-compatibility-title">验收计划兼容矩阵</h3>
                  <span>由本次探针结果和固定需求映射得出。</span>
                </div>
                <code>{{ props.result.planCompatibility.length }} plans</code>
              </div>

              <div v-if="props.result.planCompatibility.length > 0" class="plan-matrix" role="table" aria-label="Plan compatibility matrix">
                <div class="plan-matrix-head" role="row">
                  <span role="columnheader">Plan / basis</span>
                  <span role="columnheader">Status</span>
                  <span role="columnheader">requiredProbeIds</span>
                  <span role="columnheader">failedProbeIds</span>
                </div>
                <article
                  v-for="plan in props.result.planCompatibility"
                  :key="plan.planId"
                  class="plan-row"
                  role="row"
                >
                  <div role="cell" class="plan-identity">
                    <strong>{{ plan.planId }}</strong>
                    <code>{{ basisLabel(plan.basisType) }}</code>
                    <small>{{ plan.basisType }}</small>
                  </div>
                  <div role="cell" class="plan-compatibility-status">
                    <span :class="planStatusClass(plan.status)">{{ planStatusLabel(plan.status) }}</span>
                    <code>{{ plan.status }}</code>
                  </div>
                  <div role="cell" class="plan-probe-list">
                    <span class="matrix-label">requiredProbeIds</span>
                    <code>{{ probeIdsLabel(plan.requiredProbeIds) }}</code>
                  </div>
                  <div role="cell" class="plan-probe-list">
                    <span class="matrix-label">failedProbeIds</span>
                    <code>{{ probeIdsLabel(plan.failedProbeIds) }}</code>
                  </div>
                </article>
              </div>
              <p v-else class="empty-copy">当前结果没有返回 Contract-derived Plan 兼容记录。</p>
            </section>

            <details class="scan-boundary-note">
              <summary>这项结果怎么看</summary>
              <span>READY、PARTIAL、UNAVAILABLE 只描述 Provider 探针，不是 Finding，也不会阻止 Scan。安全结论仍由 Security Contract 与真实 Trace 判断。</span>
            </details>
          </div>
          <p v-else class="candidate-technical-empty">检查后可查看 Provider、耗时和 Plan 兼容证据。</p>
        </details>
      </section>
    </template>

    <template v-else>
    <header class="readiness-header">
      <div class="readiness-heading">
        <p class="readiness-kicker">运行状态</p>
        <h2 :id="props.titleId">{{ props.title }}</h2>
        <p class="readiness-lede">{{ props.lede }}</p>
      </div>
      <button
        class="readiness-run"
        :data-testid="props.runTestId"
        type="button"
        :disabled="props.loading || props.runDisabled"
        :aria-busy="props.loading"
        @click="emit('run')"
      >
        {{ props.loading ? "检查中…" : props.runLabel }}
      </button>
    </header>

    <details class="readiness-boundary">
      <summary>检查说明</summary>
      <span>
        只验证 Provider 响应能力；不会执行 Mock Enterprise Tool，也不会读取浏览器中的 Secret 或提交密钥。
      </span>
    </details>

    <div v-if="props.error" class="readiness-error" role="alert">
      <span class="readiness-error-label">READINESS ERROR</span>
      <p>{{ props.error }}</p>
    </div>

    <div v-if="props.loading" class="readiness-loading" role="status" aria-live="polite">
      <span class="loading-mark" aria-hidden="true">…</span>
      <div>
        <strong>正在检查模型能力</strong>
        <p>连接、Tool Calling、Strict JSON 各检查一次。</p>
      </div>
    </div>

    <section class="readiness-result" data-testid="provider-readiness-result" aria-live="polite">
      <template v-if="props.result">
        <div class="result-overview">
          <div>
            <p class="readiness-kicker">本次结果</p>
            <h3>本次运行就绪结论</h3>
            <p class="result-summary">{{ overallStatusDescription(props.result.status) }}</p>
          </div>
          <span class="overall-status" :class="statusClass(props.result.status)">
            {{ statusLabel(props.result.status) }}
          </span>
        </div>

        <dl class="result-meta">
          <div>
            <dt>Readiness ID</dt>
            <dd><code>{{ props.result.id }}</code></dd>
          </div>
          <div>
            <dt>Checked at</dt>
            <dd><code>{{ props.result.checkedAt }}</code></dd>
          </div>
          <div>
            <dt>Evidence boundary</dt>
            <dd>能力证据，不是安全 Finding</dd>
          </div>
        </dl>

        <div class="provider-grid" aria-label="Provider role readiness">
          <article
            v-for="entry in providerEntries"
            :key="entry.key"
            class="provider-card"
            :class="`provider-${entry.key}`"
          >
            <header class="provider-card-header">
              <div>
                <p class="provider-card-kicker">{{ entry.key.toUpperCase() }} ROLE</p>
                <h3>{{ entry.title }}</h3>
                <p>{{ entry.description }}</p>
              </div>
              <span class="role-status" :class="statusClass(entry.provider.status)">
                {{ statusLabel(entry.provider.status) }}
              </span>
            </header>

            <dl class="provider-facts">
              <div>
                <dt>Provider</dt>
                <dd><code>{{ entry.provider.provider }}</code></dd>
              </div>
              <div>
                <dt>Model</dt>
                <dd><code>{{ providerModel(entry.provider) }}</code></dd>
              </div>
              <div>
                <dt>Role</dt>
                <dd><code>{{ entry.provider.role }}</code><span>{{ entry.title }}</span></dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd><code>{{ entry.provider.status }}</code><span>{{ statusDescription(entry.provider.status) }}</span></dd>
              </div>
            </dl>

            <div class="probe-section">
              <div class="subheading">
                <div>
                <p>能力探针</p>
                <span>每项执行一次</span>
                </div>
                <code>{{ entry.provider.probes.length }} probes</code>
              </div>

              <div v-if="entry.provider.probes.length > 0" class="probe-list">
                <article
                  v-for="probe in entry.provider.probes"
                  :key="probe.id"
                  class="probe-card"
                  :class="probeStatusClass(probe.status)"
                >
                  <div class="probe-heading">
                    <div>
                      <strong>{{ probeLabel(probe) }}</strong>
                      <code>{{ probe.id }}</code>
                    </div>
                    <span class="probe-status" :class="probeStatusClass(probe.status)">
                      {{ probeStatusLabel(probe.status) }}
                    </span>
                  </div>
                  <dl class="probe-facts">
                    <div>
                      <dt>Status</dt>
                      <dd><code>{{ probe.status }}</code></dd>
                    </div>
                    <div>
                      <dt>Duration</dt>
                      <dd><code>{{ formatDuration(probe.durationMs) }}</code></dd>
                    </div>
                  </dl>
                  <div class="probe-detail">
                    <span>Detail</span>
                    <p>{{ detailLabel(probe) }}</p>
                  </div>
                </article>
              </div>
              <p v-else class="empty-copy">本次 Provider 没有返回探针记录。</p>
            </div>
          </article>
        </div>

        <section class="compatibility-section" aria-labelledby="compatibility-title">
          <div class="subheading compatibility-heading">
            <div>
              <p class="readiness-kicker">计划兼容性</p>
              <h3 id="compatibility-title">验收计划兼容矩阵</h3>
              <span>由本次探针结果和固定需求映射得出。</span>
            </div>
            <code>{{ props.result.planCompatibility.length }} plans</code>
          </div>

          <div v-if="props.result.planCompatibility.length > 0" class="plan-matrix" role="table" aria-label="Plan compatibility matrix">
            <div class="plan-matrix-head" role="row">
              <span role="columnheader">Plan / basis</span>
              <span role="columnheader">Status</span>
              <span role="columnheader">requiredProbeIds</span>
              <span role="columnheader">failedProbeIds</span>
            </div>
            <article
              v-for="plan in props.result.planCompatibility"
              :key="plan.planId"
              class="plan-row"
              role="row"
            >
              <div role="cell" class="plan-identity">
                <strong>{{ plan.planId }}</strong>
                <code>{{ basisLabel(plan.basisType) }}</code>
                <small>{{ plan.basisType }}</small>
              </div>
              <div role="cell" class="plan-compatibility-status">
                <span :class="planStatusClass(plan.status)">{{ planStatusLabel(plan.status) }}</span>
                <code>{{ plan.status }}</code>
              </div>
              <div role="cell" class="plan-probe-list">
                <span class="matrix-label">requiredProbeIds</span>
                <code>{{ probeIdsLabel(plan.requiredProbeIds) }}</code>
              </div>
              <div role="cell" class="plan-probe-list">
                <span class="matrix-label">failedProbeIds</span>
                <code>{{ probeIdsLabel(plan.failedProbeIds) }}</code>
              </div>
            </article>
          </div>
          <p v-else class="empty-copy">当前结果没有返回 Contract-derived Plan 兼容记录。</p>
        </section>

        <details class="scan-boundary-note">
          <summary>这项结果怎么看</summary>
          <span>READY、PARTIAL、UNAVAILABLE 只描述 Provider 探针，不是 Finding，也不会阻止 Scan。安全结论仍由 Security Contract 与真实 Trace 判断。</span>
        </details>
      </template>

      <div v-else class="readiness-empty">
        <span class="empty-mark" aria-hidden="true">◎</span>
        <div>
          <p class="readiness-kicker">尚未运行</p>
          <h3>尚未检查</h3>
          <p>点击上方按钮开始检查。</p>
        </div>
      </div>
    </section>
    </template>
  </section>
</template>

<style scoped>
.provider-readiness {
  --readiness-ink-strong: var(--ink-strong, #132238);
  --readiness-ink: var(--ink, #26364c);
  --readiness-muted: var(--ink-muted, #64748b);
  --readiness-faint: var(--ink-faint, #94a3b8);
  --readiness-line: var(--line, #dbe4ef);
  --readiness-surface: var(--surface, #ffffff);
  --readiness-surface-raised: var(--surface-raised, #f8fafc);
  --readiness-action: var(--action-blue, #4f7cff);
  --readiness-accent: var(--evidence-teal, #25bfae);
  --readiness-warning: var(--warning-amber, #e6a23c);
  --readiness-danger: var(--risk-coral, #ff5d5d);
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  color: var(--readiness-ink);
}

.provider-readiness,
.provider-readiness * {
  min-width: 0;
}

.provider-readiness.is-candidate {
  max-width: 1180px;
}

.candidate-readiness-card {
  overflow: hidden;
  border: 1px solid var(--readiness-line);
  border-radius: 14px;
  background: var(--readiness-surface);
}

.candidate-readiness-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px 16px;
  background:
    linear-gradient(135deg, rgba(79, 124, 255, 0.08), transparent 54%),
    var(--readiness-surface);
  border-bottom: 1px solid var(--readiness-line);
}

.candidate-readiness-header .readiness-heading h2 {
  font-size: clamp(20px, 2.4vw, 25px);
}

.candidate-readiness-controls {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 13px;
}

.candidate-overall {
  display: grid;
  grid-template-columns: auto auto;
  align-items: center;
  gap: 4px 8px;
  min-width: 0;
}

.candidate-overall-label {
  color: var(--readiness-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.candidate-overall-description {
  grid-column: 1 / -1;
  max-width: 210px;
  color: var(--readiness-muted);
  font-size: 9px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.candidate-readiness-controls .readiness-run {
  min-height: 38px;
  padding: 0 14px;
}

.candidate-probe-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 14px 20px 16px;
}

.candidate-probe-slot {
  display: flex;
  min-width: 0;
  min-height: 58px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 11px;
  background: var(--readiness-surface-raised);
  border: 1px solid var(--readiness-line);
  border-top: 2px solid var(--readiness-faint);
  border-radius: 9px;
}

.candidate-probe-slot.is-loading {
  border-top-color: var(--readiness-warning);
}

.candidate-probe-slot.is-passed {
  border-top-color: var(--readiness-accent);
}

.candidate-probe-slot.is-failed {
  border-top-color: var(--readiness-danger);
}

.candidate-probe-copy {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.candidate-probe-copy strong {
  color: var(--readiness-ink-strong);
  font-size: 10px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.candidate-probe-copy span {
  color: var(--readiness-muted);
  font-size: 9px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.candidate-probe-status {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  padding: 4px 6px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  line-height: 1.25;
  white-space: nowrap;
}

.candidate-overall .overall-status.is-unchecked,
.candidate-probe-status.is-unchecked {
  color: var(--readiness-muted);
  background: #f1f5f9;
  border-color: var(--readiness-line);
}

.candidate-overall .overall-status.is-loading,
.candidate-probe-status.is-loading {
  color: #8a5b11;
  background: #fff8e8;
  border-color: rgba(230, 162, 60, 0.4);
}

.candidate-probe-status.is-passed {
  color: #087f73;
  background: #e9fbf7;
  border-color: rgba(37, 191, 174, 0.34);
}

.candidate-probe-status.is-failed {
  color: #a33a3a;
  background: #fff3f2;
  border-color: rgba(255, 93, 93, 0.32);
}

.candidate-readiness-error {
  margin: 0 20px 13px;
}

.candidate-technical-details {
  margin: 0 20px 17px;
  padding-top: 11px;
  border-top: 1px solid var(--readiness-line);
}

.candidate-technical-details summary {
  width: fit-content;
  color: var(--readiness-action);
  cursor: pointer;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  letter-spacing: 0.04em;
}

.candidate-technical-body {
  padding-top: 3px;
}

.candidate-result-meta {
  margin-top: 12px;
}

.candidate-provider-grid {
  margin-top: 10px;
}

.candidate-provider-card {
  padding: 12px;
}

.candidate-compatibility-section {
  margin-top: 15px;
}

.candidate-technical-empty {
  margin: 10px 0 0;
  color: var(--readiness-muted);
  font-size: 10px;
  line-height: 1.5;
}

.readiness-header,
.readiness-result,
.readiness-loading,
.readiness-boundary,
.readiness-error {
  border: 1px solid var(--readiness-line);
  border-radius: 14px;
  background: var(--readiness-surface);
}

.readiness-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: clamp(21px, 4vw, 34px);
  background:
    linear-gradient(135deg, rgba(79, 124, 255, 0.08), transparent 48%),
    var(--readiness-surface);
}

.readiness-heading {
  min-width: 0;
}

.readiness-kicker,
.provider-card-kicker,
.subheading p,
.readiness-error-label,
.matrix-label,
.probe-detail > span,
.readiness-empty p,
.result-meta dt,
.provider-facts dt,
.probe-facts dt {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}

.readiness-kicker {
  margin: 0;
  color: var(--readiness-accent);
  font-size: 10px;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.readiness-heading h2 {
  margin: 8px 0 0;
  color: var(--readiness-ink-strong);
  font-size: clamp(22px, 3vw, 31px);
  font-weight: 700;
  letter-spacing: -0.025em;
  line-height: 1.2;
}

.readiness-lede {
  max-width: 650px;
  margin: 11px 0 0;
  color: var(--readiness-muted);
  font-size: 12px;
  line-height: 1.65;
}

.readiness-run {
  flex: 0 0 auto;
  min-height: 44px;
  padding: 0 17px;
  color: #ffffff;
  background: var(--readiness-action);
  border: 1px solid var(--readiness-action);
  border-radius: 8px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 750;
  white-space: nowrap;
}

.readiness-run:hover:not(:disabled) {
  background: #3f68df;
}

.readiness-run:focus-visible,
.plan-matrix a:focus-visible {
  outline: 2px solid var(--readiness-action);
  outline-offset: 3px;
}

.readiness-run:disabled {
  cursor: wait;
  opacity: 0.65;
}

.readiness-boundary {
  margin-top: 11px;
  padding: 11px 14px;
  color: var(--readiness-muted);
  font-size: 10px;
  line-height: 1.55;
}

.readiness-boundary summary {
  width: fit-content;
  color: var(--readiness-action);
  cursor: pointer;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  letter-spacing: 0.04em;
}

.readiness-boundary > span {
  display: block;
  margin-top: 6px;
}

.readiness-error {
  margin-top: 11px;
  padding: 12px 14px;
  color: #8f2d2d;
  background: #fff3f2;
  border-color: rgba(255, 93, 93, 0.35);
}

.readiness-error-label {
  color: var(--readiness-danger);
  font-size: 9px;
  letter-spacing: 0.07em;
}

.readiness-error p {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.readiness-loading {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-top: 11px;
  padding: 13px 15px;
  border-color: rgba(230, 162, 60, 0.4);
}

.loading-mark {
  display: grid;
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--readiness-warning);
  border: 1px solid rgba(230, 162, 60, 0.42);
  border-radius: 50%;
  font-size: 15px;
}

.readiness-loading strong {
  color: var(--readiness-ink-strong);
  font-size: 12px;
}

.readiness-loading p {
  margin: 3px 0 0;
  color: var(--readiness-muted);
  font-size: 10px;
  line-height: 1.45;
}

.readiness-result {
  margin-top: 11px;
  padding: clamp(16px, 3vw, 25px);
}

.result-overview,
.provider-card-header,
.probe-heading,
.compatibility-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 15px;
}

.result-overview h3,
.compatibility-heading h3,
.readiness-empty h3 {
  margin: 6px 0 0;
  color: var(--readiness-ink-strong);
  font-size: 17px;
  font-weight: 650;
  line-height: 1.3;
}

.result-summary {
  margin: 6px 0 0;
  color: var(--readiness-muted);
  font-size: 11px;
  line-height: 1.55;
}

.overall-status,
.role-status,
.probe-status,
.plan-compatibility-status span {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  padding: 5px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  line-height: 1.2;
  white-space: nowrap;
}

.overall-status.is-ready,
.role-status.is-ready,
.probe-status.is-passed,
.plan-compatibility-status span.is-compatible {
  color: #087f73;
  background: #e9fbf7;
  border-color: rgba(37, 191, 174, 0.34);
}

.overall-status.is-partial,
.role-status.is-partial,
.overall-status.is-unavailable,
.role-status.is-unavailable,
.probe-status.is-failed,
.plan-compatibility-status span.is-incompatible {
  color: #8a5b11;
  background: #fff8e8;
  border-color: rgba(230, 162, 60, 0.4);
}

.overall-status.is-unavailable,
.role-status.is-unavailable,
.probe-status.is-failed,
.plan-compatibility-status span.is-incompatible {
  color: #a33a3a;
  background: #fff3f2;
  border-color: rgba(255, 93, 93, 0.32);
}

.result-meta,
.provider-facts,
.probe-facts {
  display: grid;
  margin: 0;
}

.result-meta {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 17px;
}

.result-meta > div,
.provider-facts > div,
.probe-facts > div {
  min-width: 0;
  padding: 10px 11px;
  background: var(--readiness-surface-raised);
  border: 1px solid var(--readiness-line);
  border-radius: 8px;
}

.result-meta dt,
.provider-facts dt,
.probe-facts dt {
  color: var(--readiness-faint);
  font-size: 8px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.result-meta dd,
.provider-facts dd,
.probe-facts dd {
  margin: 6px 0 0;
  color: var(--readiness-ink);
  font-size: 10px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 11px;
  margin-top: 11px;
}

.provider-card {
  min-width: 0;
  padding: 14px;
  background: var(--readiness-surface-raised);
  border: 1px solid var(--readiness-line);
  border-radius: 10px;
}

.provider-target {
  border-top: 2px solid rgba(37, 191, 174, 0.58);
}

.provider-attack {
  border-top: 2px solid rgba(230, 162, 60, 0.62);
}

.provider-card-kicker {
  margin: 0;
  color: var(--readiness-faint);
  font-size: 8px;
  letter-spacing: 0.08em;
}

.provider-card-header h3 {
  margin: 5px 0 0;
  color: var(--readiness-ink-strong);
  font-size: 15px;
  font-weight: 680;
  line-height: 1.3;
}

.provider-card-header p:last-child {
  margin: 5px 0 0;
  color: var(--readiness-muted);
  font-size: 10px;
  line-height: 1.5;
}

.provider-facts {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  margin-top: 13px;
}

.provider-facts dd {
  display: grid;
  gap: 3px;
}

code {
  color: var(--readiness-accent);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.probe-section,
.compatibility-section {
  margin-top: 14px;
  padding-top: 13px;
  border-top: 1px solid var(--readiness-line);
}

.subheading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.subheading p {
  margin: 0;
  color: var(--readiness-accent);
  font-size: 9px;
  letter-spacing: 0.07em;
}

.subheading span {
  display: block;
  margin-top: 4px;
  color: var(--readiness-faint);
  font-size: 9px;
  line-height: 1.4;
}

.subheading > code,
.compatibility-heading > code {
  color: var(--readiness-faint);
  font-size: 8px;
}

.probe-list {
  display: grid;
  gap: 7px;
  margin-top: 9px;
}

.probe-card {
  min-width: 0;
  padding: 10px;
  background: var(--readiness-surface);
  border: 1px solid var(--readiness-line);
  border-left: 2px solid var(--readiness-accent);
  border-radius: 7px;
}

.probe-card.is-failed {
  border-left-color: var(--readiness-danger);
}

.probe-heading > div {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.probe-heading strong {
  color: var(--readiness-ink-strong);
  font-size: 10px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.probe-heading code {
  color: var(--readiness-faint);
  font-size: 8px;
}

.probe-facts {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  margin-top: 8px;
}

.probe-facts > div {
  padding: 7px 8px;
  background: var(--readiness-surface-raised);
}

.probe-facts dd {
  margin-top: 4px;
}

.probe-detail {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--readiness-line);
}

.probe-detail > span {
  color: var(--readiness-faint);
  font-size: 8px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.probe-detail p {
  margin: 4px 0 0;
  color: var(--readiness-ink);
  font-size: 10px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.compatibility-section {
  margin-top: 19px;
}

.compatibility-heading h3 {
  font-size: 15px;
}

.plan-matrix {
  display: grid;
  gap: 7px;
  margin-top: 11px;
}

.plan-matrix-head,
.plan-row {
  display: grid;
  grid-template-columns: minmax(145px, 1.05fr) minmax(130px, 0.8fr) minmax(180px, 1.4fr) minmax(180px, 1.4fr);
  gap: 9px;
  align-items: start;
}

.plan-matrix-head {
  padding: 0 10px;
  color: var(--readiness-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.plan-row {
  padding: 10px;
  background: var(--readiness-surface-raised);
  border: 1px solid var(--readiness-line);
  border-radius: 7px;
}

.plan-identity,
.plan-compatibility-status,
.plan-probe-list {
  display: grid;
  min-width: 0;
  gap: 4px;
}

.plan-identity strong {
  color: var(--readiness-ink-strong);
  font-size: 10px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.plan-identity code {
  color: var(--readiness-accent);
  font-size: 8px;
}

.plan-identity small {
  color: var(--readiness-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  overflow-wrap: anywhere;
}

.plan-compatibility-status code {
  color: var(--readiness-faint);
  font-size: 8px;
}

.matrix-label {
  color: var(--readiness-faint);
  font-size: 8px;
}

.plan-probe-list code {
  color: var(--readiness-ink);
  font-size: 8px;
  line-height: 1.45;
}

.empty-copy {
  margin: 10px 0 0;
  color: var(--readiness-muted);
  font-size: 10px;
  line-height: 1.55;
}

.scan-boundary-note {
  display: block;
  margin: 16px 0 0;
  padding: 10px 12px;
  color: var(--readiness-muted);
  background: #f0fbf9;
  border-left: 2px solid rgba(37, 191, 174, 0.52);
  border-radius: 4px 7px 7px 4px;
  font-size: 10px;
  line-height: 1.6;
}

.scan-boundary-note summary {
  width: fit-content;
  color: #087f73;
  cursor: pointer;
}

.scan-boundary-note > span {
  display: block;
  margin-top: 6px;
}

.readiness-empty {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 116px;
}

.empty-mark {
  display: grid;
  width: 31px;
  height: 31px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--readiness-faint);
  border: 1px solid var(--readiness-line);
  border-radius: 50%;
  font-size: 17px;
}

.readiness-empty h3 {
  margin-top: 3px;
  font-size: 15px;
}

.readiness-empty p:last-child {
  margin: 5px 0 0;
  color: var(--readiness-muted);
  font-size: 10px;
  line-height: 1.5;
}

@media (max-width: 760px) {
  .candidate-readiness-header {
    align-items: stretch;
    flex-direction: column;
    gap: 13px;
    padding: 16px;
  }

  .candidate-readiness-controls {
    justify-content: space-between;
  }

  .candidate-probe-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding-right: 14px;
    padding-left: 14px;
  }

  .candidate-readiness-error {
    margin-right: 14px;
    margin-left: 14px;
  }

  .candidate-technical-details {
    margin-right: 14px;
    margin-left: 14px;
  }

  .readiness-header {
    align-items: stretch;
    flex-direction: column;
    gap: 17px;
  }

  .readiness-run {
    width: 100%;
  }

  .provider-grid {
    grid-template-columns: 1fr;
  }

  .plan-matrix-head {
    display: none;
  }

  .plan-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .plan-identity,
  .plan-compatibility-status {
    padding-bottom: 7px;
    border-bottom: 1px solid var(--readiness-line);
  }
}

@media (max-width: 480px) {
  .candidate-readiness-card {
    border-radius: 10px;
  }

  .candidate-readiness-controls {
    align-items: stretch;
    flex-direction: column;
    gap: 10px;
  }

  .candidate-readiness-controls .readiness-run {
    width: 100%;
  }

  .candidate-overall-description {
    max-width: none;
  }

  .readiness-header,
  .readiness-result,
  .readiness-boundary,
  .readiness-error,
  .readiness-loading {
    border-radius: 10px;
  }

  .readiness-boundary {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .result-overview,
  .provider-card-header,
  .probe-heading,
  .compatibility-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .result-meta,
  .provider-facts {
    grid-template-columns: 1fr;
  }

  .provider-facts dd {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .plan-row {
    grid-template-columns: 1fr;
    gap: 9px;
  }

  .plan-identity,
  .plan-compatibility-status {
    padding-bottom: 0;
    border-bottom: 0;
  }

  .readiness-empty {
    align-items: flex-start;
    min-height: 100px;
  }
}

@media (max-width: 360px) {
  .candidate-probe-grid {
    grid-template-columns: 1fr;
  }
}

/* F-063: keep Readiness as a compact state/evidence surface. Business copy
 * follows the shared scale; IDs, statuses and matrix values remain the
 * technical layer. The candidate technical disclosure stays collapsed by
 * default, while the full view keeps its existing evidence selectors. */
.provider-readiness {
  --readiness-faint: var(--ink-muted, #64748b);
  --readiness-line: var(--line, #dce5ef);
  --readiness-surface: var(--surface, #ffffff);
  --readiness-surface-raised: var(--surface-raised, #f8fafc);
  font-family: var(--font-ui);
  font-size: var(--type-body-size, 16px);
  line-height: var(--type-body-leading, 1.62);
}

.candidate-readiness-card,
.readiness-header,
.readiness-result,
.readiness-loading,
.readiness-boundary,
.readiness-error {
  border-radius: var(--radius-card, 12px);
  box-shadow: var(--shadow-card, 0 12px 30px rgba(35, 68, 120, 0.08));
}

.candidate-readiness-header,
.readiness-header {
  background: var(--surface, #ffffff);
}

.readiness-kicker,
.provider-card-kicker,
.subheading p,
.readiness-error-label,
.matrix-label,
.probe-detail > span,
.result-meta dt,
.provider-facts dt,
.probe-facts dt {
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.readiness-lede,
.result-summary,
.readiness-boundary,
.readiness-error p,
.readiness-loading p,
.readiness-empty p:last-child,
.empty-copy,
.scan-boundary-note > span,
.candidate-technical-empty {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.candidate-overall-label,
.candidate-overall-description,
.candidate-probe-copy span,
.candidate-probe-status,
.candidate-technical-details summary,
.readiness-boundary summary,
.scan-boundary-note summary {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
  letter-spacing: normal;
  text-transform: none;
}

.candidate-probe-copy strong,
.result-overview h3,
.compatibility-heading h3,
.readiness-empty h3,
.readiness-loading strong {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.candidate-probe-status,
.overall-status,
.role-status,
.probe-status,
.plan-compatibility-status span {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.readiness-run,
.candidate-readiness-controls .readiness-run {
  min-height: 44px;
  border-radius: var(--radius-control, 9px);
  font-size: var(--type-body-small-size, 14px);
}

.readiness-run:hover:not(:disabled) {
  background: var(--action-blue-strong, #345fe7);
}

.provider-readiness code,
.result-meta dd,
.provider-facts dd,
.probe-facts dd,
.plan-probe-list code,
.plan-identity code,
.plan-identity small,
.plan-compatibility-status code {
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
}

/* Provider/probe cards are evidence rows inside a single result surface;
 * remove their competing fills and shadows without changing the DOM or
 * the data-test anchors. */
.provider-readiness .provider-card,
.provider-readiness .probe-card,
.provider-readiness .result-meta > div,
.provider-readiness .provider-facts > div,
.provider-readiness .probe-facts > div,
.provider-readiness .plan-row {
  background: transparent;
  box-shadow: none;
}

.provider-readiness .provider-card {
  border-radius: 0;
}

.provider-readiness .probe-card,
.provider-readiness .plan-row {
  border-radius: var(--radius-control, 9px);
}

.provider-readiness .result-meta > div,
.provider-readiness .provider-facts > div,
.provider-readiness .probe-facts > div {
  border-color: var(--line, #dce5ef);
}

.candidate-probe-slot {
  border-radius: var(--radius-control, 9px);
  box-shadow: none;
}

.candidate-probe-status.is-loading,
.overall-status.is-loading {
  color: var(--warning-amber, #e6a23c);
  background: var(--warning-amber-wash, rgba(230, 162, 60, 0.14));
}

/* F-063 second visual pass: preserve a readable state explanation on the
 * narrow viewport and give each collapsed technical layer a usable target. */
.readiness-lede,
.result-summary,
.readiness-boundary,
.readiness-error p,
.readiness-loading p,
.readiness-empty p:last-child,
.empty-copy,
.scan-boundary-note > span,
.candidate-technical-empty {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.candidate-technical-details summary,
.readiness-boundary summary,
.scan-boundary-note summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 10px 0;
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.readiness-run,
.candidate-readiness-controls .readiness-run {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.candidate-overall-description,
.candidate-probe-copy span {
  font-size: max(13px, var(--type-label-size, 13px));
  line-height: 1.45;
}

.provider-readiness code,
.result-meta dd,
.provider-facts dd,
.probe-facts dd,
.plan-probe-list code,
.plan-identity code,
.plan-identity small,
.plan-compatibility-status code {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}

.candidate-probe-status.is-passed,
.overall-status.is-ready,
.role-status.is-ready,
.probe-status.is-passed,
.plan-compatibility-status span.is-compatible {
  color: var(--evidence-teal-strong, #08786e);
  background: var(--evidence-teal-wash, rgba(22, 143, 130, 0.1));
}

.candidate-probe-status.is-failed,
.overall-status.is-unavailable,
.role-status.is-unavailable,
.probe-status.is-failed,
.plan-compatibility-status span.is-incompatible {
  color: var(--risk-coral-strong, #c63d46);
  background: var(--risk-coral-wash, rgba(255, 93, 93, 0.1));
}

.provider-readiness :is(button, a):focus-visible {
  outline: 2px solid var(--action-blue, #4f7cff);
  outline-offset: 3px;
}
</style>
