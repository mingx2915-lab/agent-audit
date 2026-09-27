<script setup lang="ts">
import { computed, nextTick, ref, watch, type ComponentPublicInstance } from "vue";
import type {
  AttackPlan,
  AttackPlanBasisType,
  AttackPlanTargetKind,
  AttackerType,
  FindingCategory,
  RedTeamScan,
} from "@agent-audit/contracts";

/**
 * The parent owns execution, replay and policy decisions.  This component is
 * deliberately a presentation/selection surface for the existing DTOs.
 */
const props = withDefaults(
  defineProps<{
    plans: AttackPlan[];
    loading?: boolean;
    error?: string;
    selectedPlanId?: string | null;
    executingPlanId?: string | null;
    replayingPlanId?: string | null;
    actionsDisabled?: boolean;
    /** Only pass a real, completed Scan when its plan is eligible for Replay. */
    currentScan?: Pick<RedTeamScan, "id" | "planId" | "status"> | null;
    /** A display-only projection supplied by the parent; no authorization is reimplemented here. */
    policySummary?: (plan: AttackPlan) => string | null;
  }>(),
  {
    loading: false,
    error: "",
    selectedPlanId: null,
    executingPlanId: null,
    replayingPlanId: null,
    actionsDisabled: false,
    currentScan: null,
    policySummary: () => null,
  },
);

const emit = defineEmits<{
  (event: "select", plan: AttackPlan): void;
  (event: "execute", plan: AttackPlan): void;
  (event: "replay", plan: AttackPlan): void;
}>();

const attackerLabels: Record<AttackerType, string> = {
  outside_in: "Outside-in · 外部攻击",
  inside_out: "Inside-out · 内部滥用",
};

const attackerShortLabels: Record<AttackerType, string> = {
  outside_in: "外部攻击",
  inside_out: "内部滥用",
};

const targetLabels: Record<AttackPlanTargetKind, string> = {
  knowledge_document: "知识文档",
  customer_record: "客户记录",
  external_sink: "外部 Sink",
  customer_export: "客户 Export",
};

const basisLabels: Record<AttackPlanBasisType, string> = {
  resource_owner_scope: "Resource owner-match",
  tool_owner_scope: "Tool owner-match",
  source_sink: "Source → Sink",
  tool_record_limit: "Tool record limit",
};

const findingCategoryLabels: Record<FindingCategory, string> = {
  resource_authorization_bypass: "资源授权绕过",
  tool_authorization_bypass: "工具授权绕过",
  external_sink_policy_violation: "外部 Sink 策略违规",
  tool_business_policy_violation: "工具业务约束违规",
};

const localSelectedPlanId = ref("");
const planButtonRefs = new Map<string, HTMLButtonElement>();

const planIds = computed(() => props.plans.map((plan) => plan.id).join("\u0000"));

watch(
  [planIds, () => props.selectedPlanId],
  () => {
    if (props.selectedPlanId && props.plans.some((plan) => plan.id === props.selectedPlanId)) {
      localSelectedPlanId.value = props.selectedPlanId;
      return;
    }

    if (!props.plans.some((plan) => plan.id === localSelectedPlanId.value)) {
      localSelectedPlanId.value = props.plans[0]?.id ?? "";
    }
  },
  { immediate: true },
);

const selectedPlanId = computed(() => {
  if (props.plans.some((plan) => plan.id === localSelectedPlanId.value)) {
    return localSelectedPlanId.value;
  }

  return props.plans[0]?.id ?? "";
});

const selectedPlan = computed<AttackPlan | null>(
  () => props.plans.find((plan) => plan.id === selectedPlanId.value) ?? null,
);

const operationDisabled = computed(
  () =>
    props.actionsDisabled ||
    Boolean(props.executingPlanId) ||
    Boolean(props.replayingPlanId),
);

const canReplaySelectedPlan = computed(
  () =>
    Boolean(
      selectedPlan.value &&
        props.currentScan?.id &&
        props.currentScan.status === "completed" &&
        props.currentScan.planId === selectedPlan.value.id,
    ),
);

function attackerLabel(type: AttackerType): string {
  return attackerLabels[type];
}

function attackerShortLabel(type: AttackerType): string {
  return attackerShortLabels[type];
}

function targetLabel(kind: AttackPlanTargetKind): string {
  return targetLabels[kind];
}

function basisLabel(type: AttackPlanBasisType): string {
  return basisLabels[type];
}

function findingCategoryLabel(category: FindingCategory): string {
  return findingCategoryLabels[category];
}

function policyText(plan: AttackPlan): string {
  return props.policySummary(plan)?.trim() || "未提供 Policy 摘要；请查看当前 Contract 规则。";
}

function selectPlan(planId: string): void {
  const plan = props.plans.find((candidate) => candidate.id === planId);
  if (!plan) {
    return;
  }

  localSelectedPlanId.value = plan.id;
  emit("select", plan);
}

function executePlan(plan: AttackPlan): void {
  selectPlan(plan.id);
  emit("execute", plan);
}

function replayPlan(plan: AttackPlan): void {
  selectPlan(plan.id);
  emit("replay", plan);
}

function setPlanButtonRef(
  planId: string,
  element: Element | ComponentPublicInstance | null,
): void {
  if (element instanceof HTMLButtonElement) {
    planButtonRefs.set(planId, element);
    return;
  }

  planButtonRefs.delete(planId);
}

function focusPlanButton(planId: string): void {
  void nextTick(() => {
    planButtonRefs.get(planId)?.focus();
  });
}

function moveSelection(index: number, offset: number): void {
  if (props.plans.length === 0) {
    return;
  }

  const nextIndex = (index + offset + props.plans.length) % props.plans.length;
  const nextPlan = props.plans[nextIndex];
  if (!nextPlan) {
    return;
  }

  selectPlan(nextPlan.id);
  focusPlanButton(nextPlan.id);
}

function handlePlanKeydown(event: KeyboardEvent, index: number): void {
  switch (event.key) {
    case "ArrowDown":
      event.preventDefault();
      moveSelection(index, 1);
      break;
    case "ArrowUp":
      event.preventDefault();
      moveSelection(index, -1);
      break;
    case "Home":
      event.preventDefault();
      selectPlan(props.plans[0]?.id ?? "");
      focusPlanButton(props.plans[0]?.id ?? "");
      break;
    case "End":
      event.preventDefault();
      selectPlan(props.plans.at(-1)?.id ?? "");
      focusPlanButton(props.plans.at(-1)?.id ?? "");
      break;
    default:
      break;
  }
}
</script>

<template>
  <section
    class="attack-plans-workspace"
    aria-labelledby="attack-plans-workspace-title"
    data-testid="attack-plans-workspace"
  >
    <header class="attack-plans-header">
      <div>
        <p class="attack-plans-eyebrow">CONTRACT / PLANS</p>
        <h2 id="attack-plans-workspace-title">可执行测试计划</h2>
        <p class="attack-plans-lede">先选一个验证目标，再查看它的规则依据与执行边界。</p>
      </div>
      <span v-if="!props.loading && props.plans.length > 0" class="attack-plans-count">
        {{ props.plans.length }} 项计划
      </span>
    </header>

    <div v-if="props.error" class="attack-plans-error" role="alert" data-testid="attack-plans-error">
      {{ props.error }}
    </div>

    <div v-if="props.loading" class="attack-plans-state" aria-live="polite" data-testid="attack-plans-loading">
      <span class="attack-plans-state-mark" aria-hidden="true">…</span>
      <div>
        <strong>正在读取测试计划</strong>
        <p>等待当前 Security Contract 的 Plan。</p>
      </div>
    </div>

    <div v-else-if="props.plans.length === 0" class="attack-plans-state" data-testid="attack-plans-empty">
      <span class="attack-plans-state-mark" aria-hidden="true">—</span>
      <div>
        <strong>当前没有可执行计划</strong>
        <p>请先确认资料与 Security Contract，再回到这里开始验收。</p>
      </div>
    </div>

    <div v-else class="attack-plans-layout">
      <div class="attack-plans-list-panel">
        <div class="attack-plans-list-heading" aria-hidden="true">
          <span>验证目标</span>
          <span>选择计划查看详情</span>
        </div>
        <ul
          class="attack-plans-list"
          role="listbox"
          aria-label="Attack Plan 列表"
          :aria-activedescendant="selectedPlan ? `attack-plan-select-${selectedPlan.id}` : undefined"
          data-testid="attack-plans-list"
        >
          <li
            v-for="(plan, index) in props.plans"
            :key="plan.id"
            class="attack-plan-row"
            :class="{ 'is-selected': selectedPlan?.id === plan.id }"
            :data-testid="`attack-plan-row-${plan.id}`"
          >
            <button
              :id="`attack-plan-select-${plan.id}`"
              :ref="(element) => setPlanButtonRef(plan.id, element)"
              type="button"
              role="option"
              class="attack-plan-select"
              :aria-selected="selectedPlan?.id === plan.id"
              :tabindex="selectedPlan?.id === plan.id ? 0 : -1"
              :data-testid="`attack-plan-select-${plan.id}`"
              @click="selectPlan(plan.id)"
              @keydown="handlePlanKeydown($event, index)"
            >
              <span class="attack-plan-select-copy">
                <span class="attack-plan-type">{{ attackerLabel(plan.attackerType) }}</span>
                <strong class="attack-plan-name">{{ plan.name }}</strong>
                <span class="attack-plan-facts">
                  <span><b>测试身份</b> <code>{{ plan.actorId }}</code></span>
                  <span><b>验证对象</b> {{ targetLabel(plan.targetKind) }} <code>{{ plan.targetId }}</code></span>
                </span>
              </span>
              <span class="attack-plan-selection-indicator" aria-hidden="true">↗</span>
            </button>
            <button
              type="button"
              class="attack-plan-execute"
              :data-testid="`attack-plan-execute-${plan.id}`"
              :disabled="operationDisabled"
              :aria-busy="props.executingPlanId === plan.id"
              @click.stop="executePlan(plan)"
            >
              {{ props.executingPlanId === plan.id ? "执行中" : "执行" }}
            </button>
          </li>
        </ul>
      </div>

      <article
        v-if="selectedPlan"
        class="attack-plan-detail"
        aria-labelledby="attack-plan-detail-title"
        data-testid="attack-plan-detail"
      >
        <header class="attack-plan-detail-header">
          <div>
            <p class="attack-plan-detail-eyebrow">
              {{ attackerShortLabel(selectedPlan.attackerType) }} · 选中计划
            </p>
            <h3 id="attack-plan-detail-title">{{ selectedPlan.name }}</h3>
            <p class="attack-plan-detail-description">{{ selectedPlan.description }}</p>
          </div>
          <span class="attack-plan-detail-target">
            {{ targetLabel(selectedPlan.targetKind) }}
            <code>{{ selectedPlan.targetId }}</code>
          </span>
        </header>

        <section class="attack-plan-goal" aria-labelledby="attack-plan-goal-title">
          <span id="attack-plan-goal-title" class="attack-plan-section-label">验证目标</span>
          <p>以 <code>{{ selectedPlan.actorId }}</code> 检查对 {{ targetLabel(selectedPlan.targetKind) }} 的业务边界。</p>
        </section>

        <details class="attack-plan-technical" data-testid="attack-plan-technical-details">
          <summary>技术详情</summary>
          <dl class="attack-plan-detail-facts">
            <div>
              <dt>Plan ID</dt>
              <dd><code>{{ selectedPlan.id }}</code></dd>
            </div>
            <div>
              <dt>Rule</dt>
              <dd>
                <code>{{ selectedPlan.basisRuleId }}</code>
                <span>{{ basisLabel(selectedPlan.basisType) }}</span>
              </dd>
            </div>
            <div>
              <dt>Profile</dt>
              <dd><code>{{ selectedPlan.targetProfileId }}</code></dd>
            </div>
            <div class="attack-plan-detail-message">
              <dt>Message</dt>
              <dd><blockquote>“{{ selectedPlan.message }}”</blockquote></dd>
            </div>
            <div class="attack-plan-detail-expected">
              <dt>Expected</dt>
              <dd>
                <ul v-if="selectedPlan.expectedFindingCategories.length > 0" class="attack-plan-category-list">
                  <li v-for="category in selectedPlan.expectedFindingCategories" :key="category">
                    {{ findingCategoryLabel(category) }}
                  </li>
                </ul>
                <span v-else>无预期 Finding 类别</span>
              </dd>
            </div>
            <div>
              <dt>Policy</dt>
              <dd>{{ policyText(selectedPlan) }}</dd>
            </div>
          </dl>
        </details>

        <div v-if="canReplaySelectedPlan" class="attack-plan-detail-actions" data-testid="attack-plan-scan-context">
          <div>
            <span class="attack-plan-section-label">下一步 · 同一计划复测</span>
            <p>当前 Scan <code>{{ props.currentScan?.id }}</code> 已完成，可在此上下文发起 Replay。</p>
          </div>
          <button
            type="button"
            class="attack-plan-replay"
            :data-testid="`attack-plan-replay-${selectedPlan.id}`"
            :disabled="operationDisabled"
            :aria-busy="props.replayingPlanId === selectedPlan.id"
            @click="replayPlan(selectedPlan)"
          >
            {{ props.replayingPlanId === selectedPlan.id ? "Replay 中" : "Replay" }}
          </button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.attack-plans-workspace {
  --plan-display: var(--type-section-title-size, 26px);
  --plan-heading: var(--type-card-title-size, 19px);
  --plan-body: var(--type-body-size, 16px);
  --plan-body-small: var(--type-body-small-size, 14px);
  --plan-label: var(--type-label-size, 13px);
  --plan-code: var(--type-code-size, 13px);
  --plan-leading-body: var(--type-body-leading, 1.6);
  --plan-leading-heading: var(--type-heading-leading, 1.25);
  --plan-space-1: var(--space-1, 4px);
  --plan-space-2: var(--space-2, 8px);
  --plan-space-3: var(--space-3, 12px);
  --plan-space-4: var(--space-4, 16px);
  --plan-space-5: var(--layout-section-gap, var(--space-5, 20px));
  --plan-space-6: var(--layout-section-gap, var(--space-6, 24px));
  width: 100%;
  max-width: var(--layout-reading-max, var(--content-wide, 1440px));
  margin: 0 auto;
  color: var(--ink, #24364d);
}

.attack-plans-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--plan-space-6);
  margin-bottom: var(--plan-space-4);
}

.attack-plans-eyebrow,
.attack-plan-detail-eyebrow,
.attack-plan-section-label {
  margin: 0;
  color: var(--action-blue-strong, #345fe7);
  font-size: var(--plan-label);
  font-weight: 650;
  letter-spacing: 0.045em;
}

.attack-plans-eyebrow {
  text-transform: uppercase;
}

.attack-plans-header h2 {
  margin: var(--plan-space-1) 0 0;
  color: var(--ink-strong, #132238);
  font-size: var(--plan-display);
  font-weight: 680;
  letter-spacing: -0.025em;
  line-height: var(--plan-leading-heading);
}

.attack-plans-lede {
  max-width: 60ch;
  margin: var(--plan-space-2) 0 0;
  color: var(--ink-muted, #64748b);
  font-size: var(--plan-body);
  line-height: var(--plan-leading-body);
}

.attack-plans-count {
  flex: 0 0 auto;
  color: var(--ink-muted, #64748b);
  font-size: var(--plan-body-small);
  line-height: 1.4;
}

.attack-plans-error,
.attack-plans-state,
.attack-plans-list-panel,
.attack-plan-detail {
  border: 1px solid var(--line, #dce5ef);
  border-radius: var(--radius-lg, 14px);
  background: var(--surface, #ffffff);
  box-shadow: 0 12px 32px rgba(24, 50, 83, 0.06);
}

.attack-plans-error {
  margin-bottom: var(--plan-space-4);
  padding: var(--plan-space-3) var(--plan-space-4);
  color: var(--risk-coral-strong, #c63d46);
  background: var(--risk-coral-wash, rgba(224, 82, 82, 0.1));
  font-size: var(--plan-body-small);
  line-height: var(--plan-leading-body);
  overflow-wrap: anywhere;
}

.attack-plans-state {
  display: flex;
  align-items: flex-start;
  gap: var(--plan-space-4);
  padding: var(--plan-space-6);
}

.attack-plans-state-mark {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--action-blue-strong, #345fe7);
  background: var(--action-blue-wash, rgba(79, 124, 255, 0.1));
  border: 1px solid var(--line-bright, #c5d3e3);
  border-radius: 50%;
  font-size: var(--plan-heading);
  line-height: 1;
}

.attack-plans-state strong {
  display: block;
  color: var(--ink-strong, #132238);
  font-size: var(--plan-heading);
  line-height: var(--plan-leading-heading);
}

.attack-plans-state p {
  margin: var(--plan-space-2) 0 0;
  color: var(--ink-muted, #64748b);
  font-size: var(--plan-body);
  line-height: var(--plan-leading-body);
}

.attack-plans-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr);
  align-items: stretch;
  gap: var(--plan-space-6);
}

.attack-plans-list-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: visible;
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.attack-plans-list-heading {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--plan-space-3);
  padding: 0 var(--plan-space-1) var(--plan-space-3);
  color: var(--ink-muted, #64748b);
  background: transparent;
  border: 0;
  font-size: var(--plan-label);
  font-weight: 650;
}

.attack-plans-list-heading span:last-child {
  padding-right: 2px;
}

.attack-plans-list {
  display: grid;
  flex: 1 1 auto;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: minmax(0, 1fr);
  align-items: stretch;
  gap: var(--plan-space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}

.attack-plan-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: 1fr auto;
  align-items: stretch;
  gap: var(--plan-space-4);
  min-width: 0;
  padding: var(--plan-space-4);
  background: var(--surface, #ffffff);
  border: 1px solid var(--line, #dce5ef);
  border-radius: var(--radius-lg, 14px);
  box-shadow: 0 10px 26px rgba(24, 50, 83, 0.055);
}

.attack-plan-row.is-selected {
  background: var(--action-blue-wash, rgba(79, 124, 255, 0.1));
  border-color: rgba(79, 124, 255, 0.34);
  box-shadow:
    inset 3px 0 0 var(--action-blue, #4f7cff),
    0 10px 26px rgba(24, 50, 83, 0.07);
}

.attack-plan-select {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--plan-space-3);
  padding: 0;
  color: inherit;
  text-align: left;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.attack-plan-select-copy {
  display: flex;
  height: 100%;
  flex-direction: column;
  min-width: 0;
  gap: var(--plan-space-1);
}

.attack-plan-type {
  color: var(--action-blue-strong, #345fe7);
  font-size: var(--plan-label);
  font-weight: 650;
  line-height: 1.35;
}

.attack-plan-name {
  color: var(--ink-strong, #132238);
  font-size: var(--plan-heading);
  font-weight: 680;
  line-height: var(--plan-leading-heading);
  overflow-wrap: anywhere;
}

.attack-plan-description {
  display: -webkit-box;
  overflow: hidden;
  color: var(--ink-muted, #64748b);
  font-size: var(--plan-body-small);
  line-height: var(--plan-leading-body);
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.attack-plan-facts {
  display: flex;
  flex-wrap: wrap;
  gap: var(--plan-space-2) var(--plan-space-4);
  margin-top: auto;
  padding-top: var(--plan-space-3);
  color: var(--ink, #24364d);
  font-size: var(--plan-body-small);
  line-height: 1.45;
}

.attack-plan-facts span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.attack-plan-facts b {
  margin-right: var(--plan-space-1);
  color: var(--ink-muted, #64748b);
  font-weight: 650;
}

.attack-plans-workspace code {
  color: var(--action-blue-strong, #345fe7);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: var(--plan-code);
  overflow-wrap: anywhere;
  word-break: break-word;
}

.attack-plan-selection-indicator {
  flex: 0 0 auto;
  align-self: flex-start;
  color: var(--ink-faint, #8a99ad);
  font-size: var(--plan-heading);
  line-height: 1;
  opacity: 0;
  transition: opacity 140ms ease, color 140ms ease;
}

.attack-plan-row.is-selected .attack-plan-selection-indicator,
.attack-plan-select:hover .attack-plan-selection-indicator,
.attack-plan-select:focus-visible .attack-plan-selection-indicator {
  color: var(--action-blue-strong, #345fe7);
  opacity: 1;
}

.attack-plan-execute,
.attack-plan-replay {
  min-width: 76px;
  min-height: 44px;
  align-self: end;
  padding: var(--plan-space-2) var(--plan-space-3);
  border-radius: var(--radius-sm, 8px);
  font-size: var(--plan-body-small);
  font-weight: 680;
  line-height: 1.3;
  cursor: pointer;
  transition: background-color 140ms ease, border-color 140ms ease, color 140ms ease;
}

.attack-plan-execute {
  justify-self: end;
  color: #ffffff;
  background: var(--action-blue, #4f7cff);
  border: 1px solid var(--action-blue, #4f7cff);
}

.attack-plan-execute:hover:not(:disabled),
.attack-plan-execute:focus-visible:not(:disabled) {
  background: var(--action-blue-strong, #345fe7);
  border-color: var(--action-blue-strong, #345fe7);
}

.attack-plan-execute:disabled,
.attack-plan-replay:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.attack-plan-detail {
  min-width: 0;
  min-height: 100%;
  padding: var(--plan-space-6);
  position: static;
}

.attack-plan-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--plan-space-5);
  min-width: 0;
}

.attack-plan-detail-header > div {
  min-width: 0;
}

.attack-plan-detail h3 {
  margin: var(--plan-space-1) 0 0;
  color: var(--ink-strong, #132238);
  font-size: var(--plan-heading);
  font-weight: 680;
  line-height: var(--plan-leading-heading);
  overflow-wrap: anywhere;
}

.attack-plan-detail-description {
  margin: var(--plan-space-2) 0 0;
  color: var(--ink, #24364d);
  font-size: var(--plan-body);
  line-height: var(--plan-leading-body);
  overflow-wrap: anywhere;
}

.attack-plan-detail-target {
  display: grid;
  flex: 0 0 auto;
  max-width: 42%;
  justify-items: end;
  gap: var(--plan-space-1);
  color: var(--ink-muted, #64748b);
  font-size: var(--plan-body-small);
  line-height: 1.35;
  text-align: right;
}

.attack-plan-goal {
  margin-top: var(--plan-space-5);
  padding: var(--plan-space-4);
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line, #dce5ef);
  border-radius: var(--radius-sm, 8px);
}

.attack-plan-goal p {
  margin: var(--plan-space-2) 0 0;
  color: var(--ink, #24364d);
  font-size: var(--plan-body);
  line-height: var(--plan-leading-body);
  overflow-wrap: anywhere;
}

.attack-plan-technical {
  margin-top: var(--plan-space-5);
  border-top: 1px solid var(--line, #dce5ef);
}

.attack-plan-technical summary {
  position: relative;
  display: flex;
  min-height: 44px;
  align-items: center;
  padding: 10px 12px 10px 34px;
  color: var(--ink-strong, #132238);
  border-radius: var(--radius-control, 8px);
  font-size: max(14px, var(--type-body-small-size, 14px));
  font-weight: 650;
  line-height: var(--type-body-small-leading, 1.55);
  cursor: pointer;
  list-style: none;
}

.attack-plan-technical summary::-webkit-details-marker {
  display: none;
}

.attack-plan-technical summary::before {
  position: absolute;
  left: 12px;
  width: 14px;
  height: 14px;
  background: var(--disclosure-chevron) center / 14px 14px no-repeat;
  content: "";
  transition: transform 160ms ease;
}

.attack-plan-technical[open] summary::before {
  transform: rotate(90deg);
}

.attack-plan-technical summary:hover {
  background: var(--surface-raised, #f7f9fc);
}

.attack-plan-detail-facts {
  display: grid;
  gap: var(--plan-space-3);
  margin: var(--plan-space-3) 0 0;
}

.attack-plan-detail-facts > div {
  display: grid;
  grid-template-columns: minmax(74px, 0.25fr) minmax(0, 0.75fr);
  gap: var(--plan-space-4);
  align-items: start;
  min-width: 0;
  padding-top: var(--plan-space-3);
  border-top: 1px solid var(--line, #dce5ef);
}

.attack-plan-detail-facts dt {
  color: var(--ink-muted, #64748b);
  font-size: var(--plan-label);
  font-weight: 650;
  line-height: 1.45;
}

.attack-plan-detail-facts dd {
  min-width: 0;
  margin: 0;
  color: var(--ink, #24364d);
  font-size: var(--plan-body-small);
  line-height: var(--plan-leading-body);
  overflow-wrap: anywhere;
}

.attack-plan-detail-facts dd > span {
  display: block;
  margin-top: var(--plan-space-1);
  color: var(--ink-muted, #64748b);
  font-size: var(--plan-body-small);
}

.attack-plan-detail-message blockquote {
  margin: 0;
  padding-left: var(--plan-space-3);
  color: var(--ink, #24364d);
  border-left: 3px solid var(--action-blue, #4f7cff);
  font-size: var(--plan-body-small);
  line-height: var(--plan-leading-body);
  overflow-wrap: anywhere;
}

.attack-plan-category-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--plan-space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.attack-plan-category-list li {
  padding: var(--plan-space-1) var(--plan-space-2);
  color: var(--ink, #24364d);
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line, #dce5ef);
  border-radius: 999px;
  font-size: var(--plan-body-small);
  line-height: 1.4;
}

.attack-plan-detail-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--plan-space-5);
  margin-top: var(--plan-space-5);
  padding-top: var(--plan-space-4);
  border-top: 1px solid var(--line, #dce5ef);
}

.attack-plan-detail-actions > div {
  min-width: 0;
}

.attack-plan-detail-actions p {
  margin: var(--plan-space-1) 0 0;
  color: var(--ink-muted, #64748b);
  font-size: var(--plan-body-small);
  line-height: var(--plan-leading-body);
  overflow-wrap: anywhere;
}

.attack-plan-replay {
  flex: 0 0 auto;
  color: var(--ink-strong, #132238);
  background: var(--surface, #ffffff);
  border: 1px solid var(--line-bright, #c5d3e3);
}

.attack-plan-replay:hover:not(:disabled),
.attack-plan-replay:focus-visible:not(:disabled) {
  color: var(--action-blue-strong, #345fe7);
  background: var(--action-blue-wash, rgba(79, 124, 255, 0.1));
  border-color: var(--action-blue, #4f7cff);
}

.attack-plan-select:focus-visible,
.attack-plan-execute:focus-visible,
.attack-plan-replay:focus-visible,
.attack-plan-technical summary:focus-visible {
  outline: 3px solid rgba(79, 124, 255, 0.34);
  outline-offset: 3px;
}

@media (max-width: 1280px) {
  .attack-plans-layout {
    grid-template-columns: 1fr;
  }

  .attack-plans-list {
    flex: 0 0 auto;
    grid-auto-rows: auto;
  }

  .attack-plan-detail {
    position: static;
  }
}

@media (max-width: 760px) {
  .attack-plans-list {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .attack-plans-header,
  .attack-plan-detail-header,
  .attack-plan-detail-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .attack-plans-header {
    gap: var(--plan-space-2);
  }

  .attack-plans-header h2 {
    font-size: var(--plan-heading);
  }

  .attack-plans-layout {
    gap: var(--plan-space-4);
  }

  .attack-plans-list-heading {
    display: none;
  }

  .attack-plan-row {
    grid-template-columns: minmax(0, 1fr);
    gap: var(--plan-space-3);
    padding: var(--plan-space-4);
  }

  .attack-plan-execute,
  .attack-plan-replay {
    width: 100%;
  }

  .attack-plan-detail {
    padding: var(--plan-space-4);
  }

  .attack-plan-detail-target {
    max-width: 100%;
    justify-items: start;
    text-align: left;
  }

  .attack-plan-detail-facts > div {
    grid-template-columns: 1fr;
    gap: var(--plan-space-1);
  }

  .attack-plan-detail-actions {
    gap: var(--plan-space-3);
  }
}

@media (prefers-reduced-motion: reduce) {
  .attack-plan-selection-indicator,
  .attack-plan-execute,
  .attack-plan-replay {
    transition: none;
  }
}
</style>
