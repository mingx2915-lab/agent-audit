<script setup lang="ts">
import { computed } from "vue";
import permissionSculpture from "../assets/illustrations/permission-boundary-generated.png";
import type {
  AttackPlan,
  DocumentCatalog,
  RedTeamScan,
  SecurityContract,
} from "@agent-audit/contracts";

type OnboardingPath = "demo" | "custom";
type OnboardingAction =
  | "connect-provider"
  | "add-documents"
  | "open-contract"
  | "run-guided-audit";
type FirstUseStepIcon = "link" | "checklist" | "shield" | "play" | "document" | "audit";

const firstUseCards = [
  {
    path: "demo",
    index: "01",
    accent: "teal",
    title: "使用合成演示",
    description: "连接 AI，使用内置场景，体验风险发现与修复复测。",
    actionLabel: "开始合成演示",
    steps: [
      { label: "连接 AI", icon: "link" },
      { label: "运行固定检查", icon: "checklist" },
      { label: "查看风险证据", icon: "shield" },
      { label: "模拟复测", icon: "play" },
    ],
  },
  {
    path: "custom",
    index: "02",
    accent: "blue",
    title: "验收我的知识助手",
    description: "连接你的 AI，添加业务资料，再确认角色与权限。",
    actionLabel: "开始验收我的助手",
    steps: [
      { label: "连接 AI", icon: "link" },
      { label: "添加业务资料", icon: "document" },
      { label: "确认权限边界", icon: "shield" },
      { label: "运行安全检查", icon: "audit" },
    ],
  },
] as const satisfies ReadonlyArray<{
  path: OnboardingPath;
  index: string;
  accent: "teal" | "blue";
  title: string;
  description: string;
  actionLabel: string;
  steps: ReadonlyArray<{ label: string; icon: FirstUseStepIcon }>;
}>;

const props = withDefaults(
  defineProps<{
    selectedPath?: OnboardingPath | null;
    providerConfigured: boolean;
    documentCatalog: DocumentCatalog | null;
    contract: SecurityContract | null;
    plans: AttackPlan[];
    guidedPlan: AttackPlan | null;
    scan: RedTeamScan | null;
    providerLoading?: boolean;
    catalogLoading?: boolean;
    plansLoading?: boolean;
    scanLoading?: boolean;
  }>(),
  {
    selectedPath: null,
    providerLoading: false,
    catalogLoading: false,
    plansLoading: false,
    scanLoading: false,
  },
);

const emit = defineEmits<{
  (event: "action", action: OnboardingAction): void;
  (event: "path-change", path: OnboardingPath | null): void;
  (event: "reset"): void;
}>();

const selectedPath = computed(() => props.selectedPath ?? null);

const userDocuments = computed(
  () =>
    props.documentCatalog?.documents.filter(
      (document) => !document.labels.some((label) => label.toUpperCase() === "SYNTHETIC"),
    ) ?? [],
);
const hasDocuments = computed(() => userDocuments.value.length > 0);
const hasPlans = computed(() => hasDocuments.value && props.plans.length > 0);
const hasAudit = computed(
  () => Boolean(props.scan && props.guidedPlan && props.scan.planId === props.guidedPlan.id),
);
const hasCompletedPath = computed(() => selectedPath.value !== null && hasAudit.value);
const hasCustomAudit = computed(() => hasDocuments.value && hasAudit.value);
const hasFinding = computed(() =>
  Boolean(props.scan?.attempts.some((attempt) => attempt.evaluation.findings.length > 0)),
);

const customSteps = computed(() => [
  {
    id: "provider",
    label: "连接 AI",
    detail: props.providerConfigured
      ? "已确认连接，可以开始检查"
      : "连接本机模型或企业 AI 地址",
    complete: props.providerConfigured,
    loading: props.providerLoading,
    action: "connect-provider" as const,
  },
  {
    id: "documents",
    label: "添加业务资料",
    detail: hasDocuments.value
      ? `当前 Workspace 有 ${userDocuments.value.length} 份你导入的业务资料`
      : "选择 AI 实际会检索的 PDF、DOCX、TXT 或 MD",
    complete: hasDocuments.value,
    loading: props.catalogLoading,
    action: "add-documents" as const,
  },
  {
    id: "contract",
    label: "查看权限边界",
    detail: props.contract
      ? `已有权限规则 · v${props.contract.version}，打开后确认本次边界`
      : "用权限规则计算角色、资料和工具的允许/拒绝",
    complete: Boolean(props.contract),
    loading: false,
    action: "open-contract" as const,
  },
  {
    id: "plan",
    label: "选择首次检查",
    detail: props.guidedPlan
      ? `已准备一条检查：${props.guidedPlan.name}`
      : hasPlans.value
        ? `${props.plans.length} 条检查可选`
        : "导入资料后会根据权限规则生成，不手工编造",
    complete: hasPlans.value,
    loading: props.plansLoading,
    action: "open-contract" as const,
  },
  {
    id: "audit",
    label: "运行首次安全检查",
    detail: hasAudit.value
      ? hasFinding.value
        ? "已发现风险，可继续查看同一次复测"
        : "已完成一次检查并记录过程证据"
      : "点击运行后才开始，不会在入口选择时自动执行",
    complete: hasCustomAudit.value,
    loading: props.scanLoading,
    action: "run-guided-audit" as const,
  },
]);

const nextCustomStep = computed(() =>
  customSteps.value.find((step) => !step.complete) ?? customSteps.value.at(-1),
);

function choosePath(path: OnboardingPath): void {
  emit("path-change", path);
}

function resetPath(): void {
  emit("path-change", null);
  emit("reset");
}

function runOrContinue(action: OnboardingAction): void {
  emit("action", action);
}
</script>

<template>
  <section
    class="enterprise-onboarding"
    :aria-labelledby="hasCompletedPath ? undefined : 'enterprise-onboarding-title'"
    :aria-label="hasCompletedPath ? '已完成的首次使用路径' : undefined"
    data-testid="enterprise-onboarding"
  >
    <div
      v-if="hasCompletedPath"
      class="enterprise-onboarding-completed"
      data-testid="onboarding-completed-bar"
      data-state="completed"
      aria-live="polite"
    >
      <div class="enterprise-onboarding-completed-copy">
        <span class="enterprise-onboarding-completed-label">当前路径</span>
        <strong>{{ selectedPath === "custom" ? "验收我的知识助手" : "使用合成演示" }}</strong>
        <span class="enterprise-onboarding-completed-status">
          {{ hasFinding ? "已完成检查 · 发现风险" : "已完成检查" }}
        </span>
      </div>
      <el-button text data-testid="onboarding-reset" @click="resetPath">换一条路径</el-button>
    </div>

    <template v-else>
      <div v-if="selectedPath === null" class="enterprise-onboarding-header onboarding-art-header">
        <div>
          <p class="section-kicker">企业 AI 权限安全 · 首次体验</p>
          <h2 id="enterprise-onboarding-title">AI 会不会越权？用执行证据来验证</h2>
          <p>
            模拟恶意文档与内部用户越权，追踪 AI 读了什么、做了什么，再用同一攻击复测权限配置。
          </p>
          <span class="onboarding-art-note">不上传文件 · 不自动运行模型</span>
        </div>
        <figure class="onboarding-sculpture" aria-label="权限边界概念插画">
          <img :src="permissionSculpture" alt="" width="1536" height="1024" fetchpriority="high" />
          <figcaption>权限边界 · 概念示意</figcaption>
        </figure>
      </div>

      <div
        v-if="selectedPath === null"
        class="enterprise-onboarding-choices"
        data-testid="onboarding-choices"
      >
        <article
          v-for="card in firstUseCards"
          :key="card.path"
          class="enterprise-onboarding-choice"
          :class="`enterprise-onboarding-choice-${card.accent}`"
          :data-testid="`onboarding-${card.path}-card`"
        >
          <button
            type="button"
            class="enterprise-onboarding-choice-button"
            :data-testid="`onboarding-${card.path}`"
            @click="choosePath(card.path)"
          >
            <span class="enterprise-onboarding-choice-heading">
              <span class="enterprise-onboarding-choice-index">{{ card.index }}</span>
              <span class="enterprise-onboarding-choice-copy">
                <span class="onboarding-recommendation">{{ card.path === 'demo' ? '推荐从这里开始' : '带入你的业务场景' }}</span>
                <strong>{{ card.title }}</strong>
                <small>{{ card.description }}</small>
              </span>
            </span>
            <ol
              class="enterprise-onboarding-choice-steps"
              :data-testid="`onboarding-${card.path}-steps`"
              :aria-label="`${card.title}真实步骤`"
            >
              <li
                v-for="(step, index) in card.steps"
                :key="`${card.path}-${step.label}`"
                class="enterprise-onboarding-choice-step"
              >
                <span class="enterprise-onboarding-choice-step-icon" aria-hidden="true">
                  <svg v-if="step.icon === 'link'" viewBox="0 0 24 24" focusable="false">
                    <path d="m9.5 14.5 5-5m-7.2 8.2-1.1 1.1a3.3 3.3 0 0 1-4.7-4.7l3.2-3.2a3.3 3.3 0 0 1 4.7 0m2.6-6.5 1.1-1.1a3.3 3.3 0 0 1 4.7 4.7l-3.2 3.2a3.3 3.3 0 0 1-4.7 0" />
                  </svg>
                  <svg v-else-if="step.icon === 'checklist'" viewBox="0 0 24 24" focusable="false">
                    <rect x="5" y="3" width="14" height="18" rx="2" />
                    <path d="m8 8 1.5 1.5L12 7m-4 6 1.5 1.5L12 12m3-4h1m-1 6h1" />
                  </svg>
                  <svg v-else-if="step.icon === 'document'" viewBox="0 0 24 24" focusable="false">
                    <path d="M6 3h8l4 4v14H6z" />
                    <path d="M14 3v5h4M9 12h6m-6 4h6" />
                  </svg>
                  <svg v-else-if="step.icon === 'play'" viewBox="0 0 24 24" focusable="false">
                    <circle cx="12" cy="12" r="8.5" />
                    <path d="m10 8.5 5 3.5-5 3.5z" />
                  </svg>
                  <svg v-else-if="step.icon === 'audit'" viewBox="0 0 24 24" focusable="false">
                    <path d="m12 3 7 3v5c0 4.5-2.9 7.8-7 10-4.1-2.2-7-5.5-7-10V6z" />
                    <path d="m8.5 12 2.2 2.2 4.8-5" />
                  </svg>
                  <svg v-else viewBox="0 0 24 24" focusable="false">
                    <path d="m12 3 7 3v5c0 4.5-2.9 7.8-7 10-4.1-2.2-7-5.5-7-10V6z" />
                    <path d="m8.5 12 2.2 2.2 4.8-5" />
                  </svg>
                </span>
                <span class="enterprise-onboarding-choice-step-label">{{ step.label }}</span>
                <span
                  v-if="index < card.steps.length - 1"
                  class="enterprise-onboarding-choice-step-arrow"
                  aria-hidden="true"
                >→</span>
              </li>
            </ol>
            <span class="enterprise-onboarding-choice-action">
              <span>{{ card.actionLabel }}</span>
              <span aria-hidden="true">→</span>
            </span>
          </button>
        </article>
      </div>

      <div v-else class="enterprise-onboarding-path" data-testid="onboarding-path">
      <div class="enterprise-onboarding-path-heading">
        <div>
          <span class="enterprise-onboarding-path-kicker">当前路径</span>
          <h3>{{ selectedPath === "demo" ? "使用合成演示" : "验收我的知识助手" }}</h3>
          <p v-if="selectedPath === 'demo'">
            演示只使用仓库内合成资料；确认 AI 连接后，点击运行才会开始一次真实检查。
          </p>
          <p v-else>按下面顺序提供信息；文件只在你明确选择后读取，权限由你确认的规则计算。</p>
        </div>
        <el-button text data-testid="onboarding-reset" @click="resetPath">换一条路径</el-button>
      </div>

        <div v-if="selectedPath === 'demo'" class="enterprise-onboarding-demo-state">
          <div class="enterprise-onboarding-demo-facts">
            <span><strong>身份</strong> 访客 · 销售 · 人力 · 财务 · 管理员</span>
            <span><strong>资料</strong> 公开知识 · 客户合同 · 财务资料</span>
            <span><strong>过程</strong> 内容来源 · 读取资料 · 权限判断 · 动作 · 数据去向</span>
          </div>
          <div v-if="!providerConfigured" class="enterprise-onboarding-next is-warning" data-testid="onboarding-active-task">
            <div>
              <strong>先连接 AI，演示也需要真实连接</strong>
              <p>当前还没有已确认的 AI 连接；不会自动切换或调用模型。</p>
            </div>
            <el-button type="primary" data-testid="onboarding-demo-connect" @click="runOrContinue('connect-provider')">
              连接 AI
            </el-button>
          </div>
          <div v-else-if="!guidedPlan" class="enterprise-onboarding-next is-warning" data-testid="onboarding-active-task">
            <div>
              <strong>当前还没有可运行的检查</strong>
              <p>请打开权限边界，查看缺少的规则或资料。</p>
            </div>
            <el-button plain data-testid="onboarding-demo-contract" @click="runOrContinue('open-contract')">
              查看权限边界
            </el-button>
          </div>
          <div v-else class="enterprise-onboarding-next" data-testid="onboarding-active-task">
            <div>
              <strong>{{ hasAudit ? "演示已完成一次真实检查" : "准备运行合成检查" }}</strong>
              <p>{{ hasAudit ? "回到下方结果查看风险与复测。" : guidedPlan.name }}</p>
            </div>
            <el-button
              type="primary"
              data-testid="onboarding-demo-run"
              :loading="scanLoading"
              :disabled="scanLoading"
              @click="runOrContinue('run-guided-audit')"
            >
              {{ hasAudit ? "再次运行安全检查" : "运行安全检查" }}
            </el-button>
          </div>
        </div>

      <div v-else class="enterprise-onboarding-custom-state">
        <ol class="enterprise-onboarding-steps">
          <li
            v-for="(step, index) in customSteps"
            :key="step.id"
            class="enterprise-onboarding-step"
            :class="{ 'is-complete': step.complete, 'is-current': nextCustomStep?.id === step.id }"
            :aria-current="nextCustomStep?.id === step.id ? 'step' : undefined"
          >
            <span class="enterprise-onboarding-step-index">{{ String(index + 1).padStart(2, '0') }}</span>
            <div class="enterprise-onboarding-step-copy">
              <strong>{{ step.label }}</strong>
              <span>{{ step.detail }}</span>
            </div>
            <span v-if="step.loading" class="enterprise-onboarding-step-state">读取中</span>
            <span v-else-if="step.complete" class="enterprise-onboarding-step-state is-complete">
              {{ step.id === "contract" ? "已加载" : "已完成" }}
            </span>
            <el-button
              v-if="nextCustomStep?.id === step.id"
              text
              size="small"
              :data-testid="`onboarding-step-${step.id}`"
              @click="runOrContinue(step.action)"
            >
              {{ step.id === 'audit' ? '运行' : step.id === 'contract' ? '查看并确认' : '去完成' }} →
            </el-button>
          </li>
        </ol>
        <div v-if="nextCustomStep" class="enterprise-onboarding-next" data-testid="onboarding-active-task">
          <div>
            <span class="enterprise-onboarding-path-kicker">下一步</span>
            <strong>{{ nextCustomStep.label }}</strong>
          </div>
          <el-button
            v-if="nextCustomStep.id !== 'audit'"
            type="primary"
            data-testid="onboarding-next-action"
            @click="runOrContinue(nextCustomStep.action)"
          >
            {{ nextCustomStep.id === 'provider' ? '连接 AI' : nextCustomStep.id === 'documents' ? '添加业务资料' : '查看权限边界' }}
          </el-button>
          <el-button
            v-else
            type="primary"
            data-testid="onboarding-next-action"
            :loading="scanLoading"
            :disabled="scanLoading"
            @click="runOrContinue('run-guided-audit')"
          >
            运行首次安全检查
          </el-button>
        </div>
      </div>
      </div>
      <section v-if="selectedPath === null" class="onboarding-method" aria-label="技术如何支撑安全结论" data-testid="onboarding-method">
        <header>
          <span>看得见的技术，查得到的依据</span>
          <p>模型生成攻击，权限规则与执行证据支撑判定。</p>
        </header>
        <div class="onboarding-method-grid">
          <article><svg class="method-art" viewBox="0 0 280 88" aria-hidden="true"><path d="M30 44H250" stroke="currentColor" stroke-opacity=".2" stroke-dasharray="3 5"/><rect x="24" y="25" width="38" height="38" rx="9" fill="currentColor" opacity=".08"/><circle cx="43" cy="39" r="6" fill="currentColor" opacity=".65"/><path d="M33 55Q43 41 53 55" fill="currentColor" opacity=".65"/><path d="M140 12L166 22V44Q166 64 140 77Q114 64 114 44V22Z" fill="currentColor" opacity=".1" stroke="currentColor"/><path d="M128 44L137 53L153 34" fill="none" stroke="currentColor" stroke-width="3"/><rect x="222" y="23" width="30" height="42" rx="4" fill="none" stroke="currentColor" stroke-opacity=".5"/><path d="M230 35H244M230 44H244M230 53H239" stroke="currentColor"/></svg><span>权限契约 · Security Contract</span><h3>先定义什么能做</h3><p>用身份、资源归属与审批规则，明确业务权限边界。</p></article>
          <article><svg class="method-art" viewBox="0 0 280 88" aria-hidden="true"><path d="M24 44H256" stroke="currentColor" stroke-opacity=".35"/><path d="M94 44V20H186V44" fill="none" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="3 4"/><g fill="currentColor"><circle cx="30" cy="44" r="9" opacity=".3"/><circle cx="94" cy="44" r="9" opacity=".6"/><circle cx="186" cy="44" r="9"/><circle cx="250" cy="44" r="9" opacity=".3"/></g><circle cx="186" cy="44" r="21" fill="none" stroke="#ec8176"/><circle cx="186" cy="44" r="28" fill="none" stroke="#ec8176" stroke-opacity=".25"/><path d="M94 61V69H143" fill="none" stroke="currentColor" stroke-opacity=".35"/></svg><span>过程追踪 · Trace</span><h3>再看实际做了什么</h3><p>串起检索、授权、工具调用和数据去向，定位越权环节。</p></article>
          <article><svg class="method-art" viewBox="0 0 280 88" aria-hidden="true"><path d="M98 25Q140 1 182 25M182 63Q140 87 98 63" fill="none" stroke="currentColor" stroke-opacity=".5"/><path d="M176 16L185 26L173 29M104 72L95 62L107 59" fill="none" stroke="currentColor"/><rect x="44" y="25" width="63" height="38" rx="8" fill="#ec8176" fill-opacity=".1" stroke="#ec8176" stroke-opacity=".5"/><path d="M70 37L82 51M82 37L70 51" stroke="#ec8176" stroke-width="2"/><rect x="173" y="25" width="63" height="38" rx="8" fill="currentColor" fill-opacity=".1" stroke="currentColor" stroke-opacity=".5"/><path d="M193 44L201 52L215 36" fill="none" stroke="currentColor" stroke-width="2"/><path d="M114 44H166" stroke="currentColor" stroke-dasharray="3 4" stroke-opacity=".35"/></svg><span>同攻击复测 · Replay</span><h3>用同一攻击验证修复</h3><p>对比参考配置下的前后证据；模拟复测不修改企业系统。</p></article>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.enterprise-onboarding {
  margin-bottom: 22px;
  padding: 22px 24px;
  background: var(--surface, #ffffff);
  border: 1px solid var(--line);
  border-radius: 15px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.12);
}

.enterprise-onboarding-header,
.enterprise-onboarding-path-heading,
.enterprise-onboarding-next,
.enterprise-onboarding-step {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.enterprise-onboarding-header {
  align-items: center;
}

.enterprise-onboarding-header h2,
.enterprise-onboarding-path-heading h3 {
  margin: 7px 0 0;
  color: var(--ink-strong);
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.enterprise-onboarding .section-kicker {
  color: var(--ink-muted);
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  letter-spacing: normal;
  line-height: var(--type-label-leading, 1.35);
  text-transform: none;
}

.enterprise-onboarding-header p:not(.section-kicker),
.enterprise-onboarding-path-heading p,
.enterprise-onboarding-next p {
  margin: 8px 0 0;
  color: var(--ink-muted);
  font-size: max(14px, var(--type-body-small-size, 13px));
  line-height: var(--type-body-leading, 1.62);
}

.enterprise-onboarding-choices {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 20px;
}

.enterprise-onboarding-choice {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 13px;
  min-width: 0;
  padding: 17px 16px;
  color: var(--ink);
  text-align: left;
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 140ms ease, transform 140ms ease, box-shadow 140ms ease;
}

.enterprise-onboarding-choice:hover,
.enterprise-onboarding-choice:focus-visible {
  border-color: var(--action-blue, #4f7cff);
  box-shadow: 0 8px 20px rgba(79, 124, 255, 0.12);
  outline: none;
  transform: translateY(-1px);
}

.enterprise-onboarding-choice-demo {
  border-color: rgba(37, 191, 174, 0.34);
}

.enterprise-onboarding-choice-custom {
  border-color: rgba(79, 124, 255, 0.34);
}

.enterprise-onboarding-choice-index,
.enterprise-onboarding-step-index {
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.enterprise-onboarding-choice strong,
.enterprise-onboarding-choice small {
  display: block;
}

.enterprise-onboarding-choice strong {
  color: var(--ink-strong);
  font-size: var(--type-card-title-size, 18px);
}

.enterprise-onboarding-choice small {
  margin-top: 5px;
  color: var(--ink-muted);
  font-size: max(14px, var(--type-body-small-size, 13px));
  line-height: var(--type-body-small-leading, 1.55);
}

.enterprise-onboarding-choice-arrow {
  color: var(--action-blue, #4f7cff);
  font-size: 18px;
}

.enterprise-onboarding-path {
  margin-top: 20px;
  padding-top: 17px;
  border-top: 1px solid var(--line);
}

.enterprise-onboarding-path-heading {
  align-items: center;
}

.enterprise-onboarding-path-kicker {
  color: var(--evidence-teal, #25bfae);
  font-size: var(--type-label-size, 12px);
  font-weight: 700;
}

.enterprise-onboarding-path-heading h3 {
  font-size: 16px;
}

.enterprise-onboarding-demo-state,
.enterprise-onboarding-custom-state {
  margin-top: 16px;
}

.enterprise-onboarding-demo-facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.enterprise-onboarding-demo-facts span {
  min-width: 0;
  padding: 11px 12px;
  color: var(--ink-muted);
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: max(14px, var(--type-body-small-size, 13px));
  line-height: var(--type-body-small-leading, 1.55);
}

.enterprise-onboarding-demo-facts strong {
  display: block;
  margin-bottom: 4px;
  color: var(--ink-strong);
  font-size: var(--type-label-size, 12px);
}

.enterprise-onboarding-next {
  align-items: center;
  margin-top: 12px;
  padding: 13px 14px;
  background: #e9fbf7;
  border: 1px solid rgba(37, 191, 174, 0.28);
  border-radius: 8px;
}

.enterprise-onboarding-next.is-warning {
  background: #fff8e6;
  border-color: rgba(217, 153, 22, 0.28);
}

.enterprise-onboarding-next > div {
  min-width: 0;
}

.enterprise-onboarding-next strong {
  color: var(--ink-strong);
  font-size: var(--type-card-title-size, 18px);
}

.enterprise-onboarding-next .el-button {
  flex-shrink: 0;
  margin: 0;
}

.enterprise-onboarding-steps {
  display: grid;
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.enterprise-onboarding-step {
  align-items: center;
  min-width: 0;
  padding: 10px 12px;
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line);
  border-radius: 8px;
}

.enterprise-onboarding-step.is-current {
  border-color: rgba(79, 124, 255, 0.45);
  box-shadow: inset 3px 0 0 var(--action-blue, #4f7cff);
}

.enterprise-onboarding-step.is-complete {
  border-color: rgba(37, 191, 174, 0.28);
}

.enterprise-onboarding-step-copy {
  display: grid;
  flex: 1;
  min-width: 0;
  gap: 3px;
}

.enterprise-onboarding-step-copy strong {
  color: var(--ink-strong);
  font-size: var(--type-label-size, 12px);
}

.enterprise-onboarding-step-copy span {
  overflow-wrap: anywhere;
  color: var(--ink-muted);
  font-size: max(14px, var(--type-body-small-size, 13px));
  line-height: var(--type-body-small-leading, 1.55);
}

.enterprise-onboarding-step-state {
  flex-shrink: 0;
  color: var(--ink-faint);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: var(--type-label-size, 12px);
}

.enterprise-onboarding-step-state.is-complete {
  color: var(--evidence-teal, #168f83);
}

.enterprise-onboarding-step .el-button {
  flex-shrink: 0;
  margin: 0;
  color: var(--action-blue, #4f7cff);
  font-size: var(--type-label-size, 12px);
}

@media (max-width: 760px) {
  .enterprise-onboarding {
    padding: 18px 16px;
  }

  .enterprise-onboarding-header,
  .enterprise-onboarding-path-heading,
  .enterprise-onboarding-next {
    align-items: stretch;
    flex-direction: column;
  }

  .enterprise-onboarding-header h2 {
    font-size: 19px;
  }

  .enterprise-onboarding-header .el-tag {
    align-self: flex-start;
  }

  .enterprise-onboarding-choices,
  .enterprise-onboarding-demo-facts {
    grid-template-columns: 1fr;
  }

  .enterprise-onboarding-choice {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .enterprise-onboarding-next .el-button {
    width: 100%;
  }

  .enterprise-onboarding-step {
    align-items: flex-start;
  }

  .enterprise-onboarding-step-state,
  .enterprise-onboarding-step .el-button {
    align-self: center;
  }
}

/* F-063: the first-use state is a bounded task stage.  The two cards keep
   their existing path events, but make each path's real work visible before
   the user commits to it. */
.enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choices {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 28px;
  padding: 0;
  overflow: visible;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choice {
  display: block;
  min-width: 0;
  min-height: 0;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 10px;
  box-shadow: none;
  transform: none;
}

.enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choice + .enterprise-onboarding-choice {
  border-top: 0;
}

.enterprise-onboarding-choice-button {
  display: flex;
  width: 100%;
  min-height: 320px;
  height: 100%;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  padding: 26px 28px 24px;
  color: var(--ink);
  text-align: left;
  background: rgba(255, 255, 255, 0.9);
  -webkit-backdrop-filter: blur(6px);
  backdrop-filter: blur(6px);
  border: 0;
  border-top: 4px solid var(--action-blue, #4f7cff);
  border-radius: 10px;
  cursor: pointer;
  box-shadow: 0 4px 18px rgba(24, 50, 83, 0.06);
  transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
}

.enterprise-onboarding-choice-teal .enterprise-onboarding-choice-button {
  border-top-color: var(--evidence-teal, #25bfae);
}

.enterprise-onboarding-choice-button:hover,
.enterprise-onboarding-choice-button:focus-visible {
  outline: none;
  box-shadow: 0 8px 24px rgba(24, 50, 83, 0.1);
  transform: translateY(-1px);
}

.enterprise-onboarding-choice-button:focus-visible {
  box-shadow:
    0 0 0 3px rgba(255, 255, 255, 0.9),
    0 0 0 6px rgba(79, 124, 255, 0.7),
    0 16px 28px rgba(2, 14, 32, 0.24);
}

.enterprise-onboarding-choice-heading {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 16px;
}

.enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choice-index {
  display: inline-grid;
  flex: 0 0 auto;
  width: 48px;
  min-width: 48px;
  height: 48px;
  min-height: 48px;
  padding: 0;
  place-items: center;
  color: var(--action-blue-strong, #345fe7);
  background: var(--action-blue-wash, rgba(79, 124, 255, 0.1));
  border-radius: 8px;
  font-family: var(--font-ui);
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
}

.enterprise-onboarding-choice-teal .enterprise-onboarding-choice-index {
  color: var(--evidence-teal-strong, #087f75);
  background: var(--evidence-teal-wash, rgba(37, 191, 174, 0.12));
}

.enterprise-onboarding-choice-copy {
  display: block;
  min-width: 0;
}

.enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choice strong {
  display: block;
  color: var(--ink-strong);
  font-size: 20px;
  font-weight: 700;
  line-height: 1.3;
}

.enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choice small {
  display: block;
  margin-top: 6px;
  overflow-wrap: anywhere;
  color: var(--ink);
  font-size: 16px;
  line-height: 1.5;
}

.enterprise-onboarding-choice-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  margin-top: 32px;
  padding: 0;
  list-style: none;
}

.enterprise-onboarding-choice-step {
  position: relative;
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: var(--ink);
  text-align: center;
}

.enterprise-onboarding-choice-step-arrow {
  position: absolute;
  top: 17px;
  right: -8px;
  color: var(--ink-faint);
  font-size: 22px;
  line-height: 1;
}

.enterprise-onboarding-choice-step-icon {
  display: grid;
  width: 56px;
  height: 56px;
  place-items: center;
  color: var(--action-blue, #4f7cff);
  background: #ffffff;
  border: 2px solid var(--line-bright, #d9e2ef);
  border-radius: 12px;
}

.enterprise-onboarding-choice-teal .enterprise-onboarding-choice-step-icon {
  color: var(--evidence-teal, #25bfae);
}

.enterprise-onboarding-choice-step-icon svg {
  width: 32px;
  height: 32px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.8;
}

.enterprise-onboarding-choice-step-label {
  min-height: 42px;
  color: var(--ink-strong);
  font-size: 14px;
  font-weight: 650;
  line-height: 1.45;
}

.enterprise-onboarding-choice-action {
  display: flex;
  min-height: 50px;
  align-items: center;
  justify-content: space-between;
  margin-top: auto;
  padding: 0 18px;
  color: #ffffff;
  background: var(--action-blue, #4f7cff);
  border-radius: 8px;
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
}

.enterprise-onboarding-choice-teal .enterprise-onboarding-choice-action {
  background: var(--evidence-teal-strong, #08786e);
}

.enterprise-onboarding-completed {
  display: flex;
  min-height: 56px;
  max-height: 72px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 6px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.enterprise-onboarding-completed-copy {
  display: flex;
  min-width: 0;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.enterprise-onboarding-completed-label,
.enterprise-onboarding-completed-status {
  color: var(--ink-muted);
  font-size: max(14px, var(--type-body-small-size, 13px));
  line-height: 1.35;
}

.enterprise-onboarding-completed-label {
  color: var(--evidence-teal, #168f82);
  font-weight: 700;
}

.enterprise-onboarding-completed-copy strong {
  overflow-wrap: anywhere;
  color: var(--ink-strong);
  font-size: var(--type-card-title-size, 18px);
  line-height: 1.25;
}

.enterprise-onboarding-completed-status {
  overflow-wrap: anywhere;
}

.enterprise-onboarding-completed .el-button {
  flex: 0 0 auto;
  min-height: 44px;
  margin: 0;
}

@media (max-width: 760px) {
  .enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choices {
    grid-template-columns: 1fr;
    gap: 12px;
    padding: 0;
  }

  .enterprise-onboarding-choice-button {
    min-height: 0;
    padding: 20px 18px;
  }

  .enterprise-onboarding-choice-heading {
    gap: 12px;
  }

  .enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choice-index {
    width: 40px;
    min-width: 40px;
    height: 40px;
    min-height: 40px;
    font-size: 14px;
  }

  .enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choice strong {
    font-size: 18px;
  }

  .enterprise-onboarding.enterprise-onboarding .enterprise-onboarding-choice small {
    font-size: 15px;
  }

  .enterprise-onboarding-choice-steps {
    row-gap: 18px;
    margin-top: 24px;
  }

  .enterprise-onboarding-choice-step-arrow {
    display: none;
  }

  .enterprise-onboarding-choice-step-icon {
    width: 48px;
    height: 48px;
  }

  .enterprise-onboarding-choice-step-icon svg {
    width: 28px;
    height: 28px;
  }

  .enterprise-onboarding-choice-step-label {
    min-height: 0;
    font-size: 14px;
  }

  .enterprise-onboarding-choice-action {
    min-height: 50px;
    margin-top: 24px;
    font-size: 17px;
  }

  .enterprise-onboarding-demo-facts span + span {
    border-top: 1px solid var(--line);
    border-left: 0;
  }

  .enterprise-onboarding-completed {
    gap: 8px;
  }

  .enterprise-onboarding-completed-copy {
    gap: 4px 8px;
  }

  .enterprise-onboarding-completed .el-button {
    white-space: nowrap;
  }
}
.onboarding-recommendation {
  display: block;
  margin-bottom: 6px;
  color: var(--evidence-teal-strong);
  font-size: 14px;
  font-weight: 650;
}

.onboarding-method {
  margin-top: 28px;
  padding: 24px 0 0;
  border-top: 1px solid var(--line);
}
.onboarding-method header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 20px; }
.onboarding-method header > span { color: var(--ink-strong); font-size: 16px; font-weight: 700; }
.onboarding-method header p, .onboarding-method article p { margin: 0; color: var(--ink-muted); font-size: 14px; line-height: 1.65; }
.onboarding-method-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px; margin-top: 20px; }
.onboarding-method article { min-width: 0; padding: 12px 12px 20px; border: 1px solid var(--line); border-radius: 12px; background: linear-gradient(150deg, #ffffff, #f0f7fb); box-shadow: 0 5px 16px rgba(24, 50, 83, .04); }
.onboarding-method article > span, .onboarding-method article h3, .onboarding-method article p { margin-left: 8px; margin-right: 8px; }
.method-art { display: block; width: 100%; height: 96px; margin-bottom: 18px; padding: 4px 10px; color: #86e3db; background: radial-gradient(ellipse at 50% 100%, #174b60, #0d263f 75%); border: 1px solid #25465d; border-radius: 8px; }
.onboarding-method article > span { color: var(--action-blue-strong); font-size: 14px; font-weight: 600; }
.onboarding-method article h3 { margin: 8px 0; color: var(--ink-strong); font-size: 18px; }
@media (max-width: 760px) { .onboarding-method-grid { grid-template-columns: 1fr; gap: 20px; } }

/* The entry icons share the artwork's glass-and-metal palette. */
.enterprise-onboarding-choice-step-icon {
  background: linear-gradient(145deg, #ffffff 35%, #edf3fc);
  border-color: #c6d5e9;
  box-shadow: 0 3px 0 #e2eaf5, 0 7px 12px rgba(29, 63, 112, .06), inset 0 1px 0 #ffffff;
}
.enterprise-onboarding-choice-teal .enterprise-onboarding-choice-step-icon {
  background: linear-gradient(145deg, #ffffff 35%, #e8f7f4);
  border-color: #b9dad5;
  box-shadow: 0 3px 0 #d9eeea, 0 7px 12px rgba(20, 94, 85, .06), inset 0 1px 0 #ffffff;
}
.enterprise-onboarding-choice-button {
  background-image: linear-gradient(150deg, transparent 65%, rgba(79, 124, 255, .07));
}
.enterprise-onboarding-choice-teal .enterprise-onboarding-choice-button {
  background-image: linear-gradient(150deg, transparent 65%, rgba(37, 191, 174, .07));
}
</style>
