<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import type {
  ActorRole,
  AttackPlan,
  AttackPlanBasisType,
  AttackPlanChange,
  ContractChangeKind,
  ContractFieldChange,
  SecurityContract,
  SecurityContractPreview,
  SinkType,
  ToolRule,
} from "@agent-audit/contracts";

type EditorMode = "visual" | "json";
type ListField = "matchLabels" | "blockedSourceTrustLevels";
type RuleCollection = "resourceRules" | "sinkRules";

const props = withDefaults(
  defineProps<{
    contract: SecurityContract | null;
    loading?: boolean;
    saving?: boolean;
    preview?: SecurityContractPreview | null;
    previewLoading?: boolean;
    error?: string;
    notice?: string;
  }>(),
  {
    loading: false,
    saving: false,
    preview: null,
    previewLoading: false,
    error: "",
    notice: "",
  },
);

const emit = defineEmits<{
  (event: "preview", candidate: SecurityContract): void;
  (event: "save", candidate: SecurityContract): void;
  (event: "cancel"): void;
}>();

const editing = ref(false);
const mode = ref<EditorMode>("visual");
const draft = ref<SecurityContract | null>(null);
const jsonText = ref("");
const jsonError = ref("");
const localError = ref("");
const draftRevision = ref(0);
const previewRevision = ref<number | null>(null);
const previewRequestRevision = ref<number | null>(null);
const previewSeen = ref<SecurityContractPreview | null>(null);
const pendingListValues = reactive<Record<string, string>>({});

const roleLabels: Record<ActorRole, string> = {
  visitor: "访客",
  employee: "员工",
  sales: "销售",
  hr: "人力资源",
  finance_manager: "财务经理",
  admin: "管理员",
};

const sinkLabels: Record<SinkType, string> = {
  external_message: "外部消息",
  customer_export: "客户导出",
};

const basisLabels: Record<AttackPlanBasisType, string> = {
  resource_owner_scope: "Resource owner-match",
  tool_owner_scope: "Tool owner-match",
  source_sink: "Source → Sink",
  tool_record_limit: "Tool record limit",
};

const changeLabels: Record<ContractChangeKind, string> = {
  added: "新增",
  removed: "删除",
  changed: "变化",
};

const changeClasses: Record<ContractChangeKind, string> = {
  added: "is-added",
  removed: "is-removed",
  changed: "is-changed",
};

const roleOptions = computed<ActorRole[]>(() =>
  (draft.value?.roles ?? []).map((role) => role.id),
);

const currentContract = computed(() => props.contract);

const candidatePlanCount = computed(() => props.preview?.candidatePlans.length ?? 0);
const currentPlanCount = computed(() => props.preview?.currentPlans.length ?? 0);

const hasCurrentPreview = computed(
  () =>
    Boolean(props.preview) &&
    previewRevision.value !== null &&
    previewRevision.value === draftRevision.value &&
    previewRequestRevision.value === null &&
    !props.previewLoading &&
    !jsonError.value,
);

const previewIsExpired = computed(() => editing.value && !hasCurrentPreview.value);

const canPreview = computed(
  () => Boolean(draft.value) && !props.previewLoading && !props.saving && !jsonError.value,
);

const canSave = computed(
  () => Boolean(draft.value) && hasCurrentPreview.value && !props.saving,
);

watch(
  () => props.contract,
  (next) => {
    const wasEditing = editing.value;
    resetDraft(next);
    if (wasEditing) {
      // A new active Contract is authoritative (normally after a successful PUT).
      // Drop the draft so the editor cannot keep showing a stale candidate.
      editing.value = false;
      mode.value = "visual";
    }
  },
  { immediate: true },
);

watch(
  () => props.preview,
  (next) => {
    if (!next || previewRequestRevision.value === null || next === previewSeen.value) {
      return;
    }

    previewSeen.value = next;
    previewRevision.value = previewRequestRevision.value;
    previewRequestRevision.value = null;
  },
);

watch(
  () => props.notice,
  (next) => {
    if (!next || !editing.value) {
      return;
    }

    editing.value = false;
    mode.value = "visual";
    resetDraft(props.contract);
  },
);

function cloneContract(value: SecurityContract): SecurityContract {
  return JSON.parse(JSON.stringify(value)) as SecurityContract;
}

function formatJson(value: SecurityContract | null): string {
  return value ? JSON.stringify(value, null, 2) : "";
}

function resetDraft(contract: SecurityContract | null): void {
  draft.value = contract ? cloneContract(contract) : null;
  jsonText.value = formatJson(contract);
  jsonError.value = "";
  localError.value = "";
  draftRevision.value = 0;
  previewRevision.value = null;
  previewRequestRevision.value = null;
  previewSeen.value = props.preview;
  Object.keys(pendingListValues).forEach((key) => delete pendingListValues[key]);
}

function beginEdit(): void {
  if (!props.contract || props.loading) {
    return;
  }

  resetDraft(props.contract);
  editing.value = true;
  mode.value = "visual";
}

function cancelEdit(): void {
  editing.value = false;
  mode.value = "visual";
  resetDraft(props.contract);
  emit("cancel");
}

function touchDraft(): void {
  if (!draft.value) {
    return;
  }

  draftRevision.value += 1;
  previewRevision.value = null;
  previewRequestRevision.value = null;
  localError.value = "";
  if (mode.value === "visual") {
    jsonText.value = formatJson(draft.value);
  }
}

function updateJsonDraft(): void {
  jsonError.value = "";
  localError.value = "";

  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText.value) as unknown;
  } catch {
    jsonError.value = "JSON 格式无效；请修正原文后再预览或保存。";
    draftRevision.value += 1;
    previewRevision.value = null;
    previewRequestRevision.value = null;
    return;
  }

  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    jsonError.value = "Contract JSON 必须是一个对象；当前原文已保留。";
    draftRevision.value += 1;
    previewRevision.value = null;
    previewRequestRevision.value = null;
    return;
  }

  const object = parsed as Record<string, unknown>;
  const collectionFields = ["roles", "resourceRules", "toolRules", "sinkRules"];
  const hasCollections = collectionFields.every((field) => Array.isArray(object[field]));
  const hasObjectItems = hasCollections && collectionFields.every((field) =>
    (object[field] as unknown[]).every(
      (item) => item !== null && typeof item === "object" && !Array.isArray(item),
    ),
  );
  if (!hasObjectItems) {
    jsonError.value = "Contract JSON 缺少 roles/resourceRules/toolRules/sinkRules 数组；当前原文已保留。";
    draftRevision.value += 1;
    previewRevision.value = null;
    previewRequestRevision.value = null;
    return;
  }

  draft.value = parsed as SecurityContract;
  draftRevision.value += 1;
  previewRevision.value = null;
  previewRequestRevision.value = null;
}

function chooseMode(nextMode: EditorMode): void {
  if (mode.value === nextMode) {
    return;
  }

  if (nextMode === "json" && draft.value && !jsonError.value) {
    jsonText.value = formatJson(draft.value);
  }

  mode.value = nextMode;
}

function requestPreview(): void {
  if (!draft.value || !canPreview.value) {
    return;
  }

  localError.value = "";
  previewSeen.value = props.preview;
  previewRevision.value = null;
  previewRequestRevision.value = draftRevision.value;
  emit("preview", cloneContract(draft.value));
}

function saveDraft(): void {
  if (!draft.value || !canSave.value) {
    return;
  }

  emit("save", cloneContract(draft.value));
}

function draftRoleLabel(role: ActorRole): string {
  return roleLabels[role] ?? role;
}

function sinkTypeLabel(type: SinkType): string {
  return sinkLabels[type] ?? type;
}

function basisTypeLabel(type: AttackPlanBasisType | null): string {
  return type ? basisLabels[type] ?? type : "—";
}

function changeLabel(kind: ContractChangeKind): string {
  return changeLabels[kind];
}

function changeClass(kind: ContractChangeKind): string {
  return changeClasses[kind];
}

function displayValue(value: unknown): string {
  if (value === undefined) {
    return "—";
  }
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }

  const serialized = JSON.stringify(value);
  return serialized ?? String(value);
}

function listKey(collection: RuleCollection, ruleId: string, field: ListField): string {
  return `${collection}.${ruleId}.${field}`;
}

function listDraftValue(collection: RuleCollection, ruleId: string, field: ListField): string {
  const key = listKey(collection, ruleId, field);
  return pendingListValues[key] ?? "";
}

function setListDraftValue(
  collection: RuleCollection,
  ruleId: string,
  field: ListField,
  value: string,
): void {
  pendingListValues[listKey(collection, ruleId, field)] = value;
}

function addListValue(
  collection: RuleCollection,
  ruleId: string,
  field: ListField,
  values: string[],
): void {
  const key = listKey(collection, ruleId, field);
  const value = pendingListValues[key] ?? "";
  if (!value.trim()) {
    localError.value = "列表项不能为空；请输入值后再添加。";
    return;
  }

  values.push(value);
  pendingListValues[key] = "";
  touchDraft();
}

function removeListValue(values: string[], index: number): void {
  values.splice(index, 1);
  touchDraft();
}

function updateMaxRecords(rule: ToolRule, event: Event): void {
  const value = (event.target as HTMLInputElement).value;
  if (value === "") {
    rule.maxRecords = null;
    touchDraft();
    return;
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    localError.value = "maxRecords 必须是 number 或 null。";
    return;
  }

  rule.maxRecords = parsed;
  touchDraft();
}

function updateContractVersion(event: Event): void {
  if (!draft.value) {
    return;
  }

  const value = (event.target as HTMLInputElement).value;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    localError.value = "Contract version 必须是 number。";
    return;
  }

  draft.value.version = parsed;
  touchDraft();
}

function planName(plan: AttackPlan): string {
  return plan.name || plan.id;
}

function planChangeLabel(change: AttackPlanChange): string {
  return `${changeLabel(change.kind)} · ${change.planId}`;
}

function fieldPathLabel(change: ContractFieldChange): string {
  return change.path.replace(/\[([^\]]+)\]/g, " · $1");
}

function fieldChangeValue(value: unknown): string {
  return displayValue(value);
}
</script>

<template>
  <section class="security-contract-editor" data-testid="security-contract-editor" aria-labelledby="security-contract-editor-title">
    <header class="contract-editor-header">
      <div>
        <p class="editor-kicker">策略配置</p>
        <h2 id="security-contract-editor-title">当前 Security Contract</h2>
        <p class="editor-subtitle">编辑角色、资源、工具和外发规则。</p>
      </div>
      <div class="editor-header-actions">
        <span class="editor-mode-label">{{ editing ? (mode === "visual" ? "可视化草稿" : "高级 JSON") : "只读" }}</span>
        <button
          v-if="!editing"
          class="editor-button editor-button-secondary"
          data-testid="contract-visual-edit"
          type="button"
          :disabled="props.loading || !currentContract"
          @click="beginEdit"
        >
          可视化编辑
        </button>
      </div>
    </header>

    <details class="editor-boundary">
      <summary><span class="boundary-dot" aria-hidden="true"></span>编辑说明</summary>
      <span>Preview 只计算当前 Contract 与派生 Plan 影响，不执行 Provider、Tool 或写入 active Contract。</span>
    </details>

    <p v-if="props.notice" class="editor-notice" role="status">{{ props.notice }}</p>
    <p v-if="props.error" class="editor-error" role="alert">{{ props.error }}</p>
    <p v-if="jsonError" class="editor-error" role="alert">{{ jsonError }}</p>
    <p v-if="localError" class="editor-error" role="alert">{{ localError }}</p>

    <div v-if="props.loading" class="editor-loading" role="status" aria-live="polite">
      <span class="loading-mark" aria-hidden="true">…</span>
      <span>正在读取 Security Contract…</span>
    </div>

    <template v-else-if="currentContract && !editing">
      <div class="contract-identity" aria-label="Contract 元信息">
        <code>{{ currentContract.id }}</code>
        <span>{{ currentContract.name }}</span>
        <span>v{{ currentContract.version }}</span>
      </div>

      <dl class="contract-summary-metrics">
        <div>
          <dt>Roles</dt>
          <dd>{{ currentContract.roles.length }}</dd>
        </div>
        <div>
          <dt>ResourceRules</dt>
          <dd>{{ currentContract.resourceRules.length }}</dd>
        </div>
        <div>
          <dt>ToolRules</dt>
          <dd>{{ currentContract.toolRules.length }}</dd>
        </div>
        <div>
          <dt>SinkRules</dt>
          <dd>{{ currentContract.sinkRules.length }}</dd>
        </div>
      </dl>

      <div class="read-only-groups">
        <article class="read-only-group">
          <div class="group-heading">
            <div>
              <h3>角色</h3>
            </div>
            <span>{{ currentContract.roles.length }} entries</span>
          </div>
          <ul class="read-only-list role-summary-grid">
            <li v-for="role in currentContract.roles" :key="role.id">
              <span>{{ role.displayName }}</span>
              <code>{{ role.id }}</code>
            </li>
          </ul>
        </article>

        <article class="read-only-group">
          <div class="group-heading">
            <div>
              <h3>资源授权</h3>
            </div>
            <span>{{ currentContract.resourceRules.length }} rules</span>
          </div>
          <ul class="read-only-list rule-summary-grid">
            <li v-for="rule in currentContract.resourceRules" :key="rule.id">
              <span>{{ rule.description }}</span>
              <code>{{ rule.id }}</code>
              <small>{{ rule.matchLabels.join(" · ") || "任意标签" }} · {{ rule.requireOwnerMatch ? "owner-match" : "owner unrestricted" }}</small>
            </li>
          </ul>
        </article>

        <article class="read-only-group">
          <div class="group-heading">
            <div>
              <h3>动作与外发</h3>
            </div>
            <span>{{ currentContract.toolRules.length + currentContract.sinkRules.length }} rules</span>
          </div>
          <ul class="read-only-list rule-summary-grid">
            <li v-for="rule in currentContract.toolRules" :key="rule.id">
              <span>{{ rule.toolName }} · {{ rule.action }}</span>
              <code>{{ rule.id }}</code>
              <small>{{ rule.maxRecords === null ? "maxRecords=null" : `maxRecords=${rule.maxRecords}` }} · {{ rule.requireApproval ? "approval required" : "approval not required" }}</small>
            </li>
            <li v-for="rule in currentContract.sinkRules" :key="rule.id">
              <span>{{ sinkTypeLabel(rule.sinkType) }}</span>
              <code>{{ rule.id }}</code>
              <small>{{ rule.allowExternal ? "external allowed" : "external blocked" }} · {{ rule.requireApproval ? "approval required" : "approval not required" }}</small>
            </li>
          </ul>
        </article>
      </div>
    </template>

    <div v-else-if="editing && draft" class="editor-workspace">
      <div class="draft-toolbar">
        <div>
          <div class="contract-identity draft-identity">
            <code>{{ draft.id }}</code>
            <span>{{ draft.name }}</span>
            <span>candidate v{{ draft.version }}</span>
          </div>
          <p class="draft-status" :class="{ 'is-expired': previewIsExpired, 'is-ready': hasCurrentPreview }">
            <span class="draft-status-dot" aria-hidden="true"></span>
            <template v-if="props.previewLoading">正在计算 Preview…</template>
            <template v-else-if="hasCurrentPreview">Preview 与当前 Draft 一致</template>
            <template v-else-if="props.preview && previewIsExpired">当前 Draft 已变化，旧 Preview 已过期</template>
            <template v-else>尚未预览当前 Draft</template>
          </p>
        </div>
        <div class="mode-switch" role="tablist" aria-label="Contract 编辑模式">
          <button
            class="mode-switch-button"
            :class="{ 'is-active': mode === 'visual' }"
            data-testid="contract-mode-visual"
            type="button"
            role="tab"
            :aria-selected="mode === 'visual'"
            @click="chooseMode('visual')"
          >
            Visual
          </button>
          <button
            class="mode-switch-button"
            :class="{ 'is-active': mode === 'json' }"
            data-testid="contract-mode-json"
            type="button"
            role="tab"
            :aria-selected="mode === 'json'"
            @click="chooseMode('json')"
          >
            Advanced JSON
          </button>
        </div>
      </div>

      <div v-if="mode === 'json'" class="json-editor-pane">
        <label class="input-label" for="security-contract-json-draft">完整 Contract JSON</label>
        <textarea
          id="security-contract-json-draft"
          v-model="jsonText"
          class="contract-json-input"
          data-testid="contract-json-draft"
          rows="18"
          spellcheck="false"
          aria-label="Security Contract JSON 编辑器"
          aria-describedby="security-contract-json-help"
          @input="updateJsonDraft"
        ></textarea>
        <p id="security-contract-json-help" class="input-help">
          JSON 模式与 Visual 模式使用同一个 Draft；解析失败时保留原文，并阻止 Preview/Save。
        </p>
      </div>

      <div v-else class="visual-editor-pane">
        <section class="metadata-editor" aria-labelledby="contract-metadata-title">
          <div class="section-heading">
            <div>
              <p class="group-kicker">Contract 信息</p>
              <h3 id="contract-metadata-title">Contract 基本信息</h3>
            </div>
            <span class="section-note">ID 保持稳定</span>
          </div>
          <div class="form-grid form-grid-three">
            <label class="input-field">
              <span class="input-label">Contract ID</span>
              <input :value="draft.id" readonly aria-readonly="true" />
            </label>
            <label class="input-field">
              <span class="input-label">名称</span>
              <input v-model="draft.name" data-testid="contract-name-input" @input="touchDraft" />
            </label>
            <label class="input-field">
              <span class="input-label">Version</span>
              <input :value="draft.version" type="number" min="1" step="1" data-testid="contract-version-input" @input="updateContractVersion" />
            </label>
          </div>
        </section>

        <section class="rule-editor-section" aria-labelledby="roles-title">
          <div class="section-heading">
            <div>
              <h3 id="roles-title">当前角色</h3>
            </div>
            <span class="section-note">不可新增或删除角色 ID</span>
          </div>
          <div class="rule-card-grid">
            <article v-for="role in draft.roles" :key="role.id" class="rule-card role-card">
              <div class="rule-card-heading">
                <div>
                  <span class="rule-kind">ROLE</span>
                  <h4>{{ role.displayName }}</h4>
                </div>
                <code>{{ role.id }}</code>
              </div>
              <label class="input-field">
                <span class="input-label">显示名</span>
                <input v-model="role.displayName" :aria-label="`${role.id} displayName`" @input="touchDraft" />
              </label>
            </article>
          </div>
        </section>

        <section class="rule-editor-section" aria-labelledby="resources-title">
          <div class="section-heading">
            <div>
              <p class="group-kicker">资源规则</p>
              <h3 id="resources-title">ResourceRule</h3>
            </div>
            <span class="section-note">{{ draft.resourceRules.length }} rules · IDs 保持稳定</span>
          </div>
          <div class="rule-card-grid">
            <article v-for="rule in draft.resourceRules" :key="rule.id" class="rule-card">
              <div class="rule-card-heading">
                <div>
                  <span class="rule-kind">RESOURCE RULE</span>
                  <h4>{{ rule.description }}</h4>
                </div>
                <code>{{ rule.id }}</code>
              </div>
              <div class="form-grid">
                <label class="input-field input-field-wide">
                  <span class="input-label">Description</span>
                  <input v-model="rule.description" :aria-label="`${rule.id} description`" @input="touchDraft" />
                </label>
                <div class="list-field">
                  <span class="input-label">Match labels</span>
                  <div class="token-list">
                    <span v-for="(label, index) in rule.matchLabels" :key="`${rule.id}-label-${index}`" class="token-item">
                      <input v-model="rule.matchLabels[index]" :aria-label="`${rule.id} matchLabels ${index + 1}`" @input="touchDraft" />
                      <button type="button" class="token-remove" :aria-label="`删除 ${rule.id} label ${index + 1}`" @click="removeListValue(rule.matchLabels, index)">×</button>
                    </span>
                  </div>
                  <div class="list-add-row">
                    <input
                      :value="listDraftValue('resourceRules', rule.id, 'matchLabels')"
                      :aria-label="`${rule.id} 新增 match label`"
                      placeholder="新增 label"
                      @input="setListDraftValue('resourceRules', rule.id, 'matchLabels', ($event.target as HTMLInputElement).value)"
                      @keyup.enter="addListValue('resourceRules', rule.id, 'matchLabels', rule.matchLabels)"
                    />
                    <button type="button" class="token-add" @click="addListValue('resourceRules', rule.id, 'matchLabels', rule.matchLabels)">添加</button>
                  </div>
                </div>
                <label class="input-field">
                  <span class="input-label">Allowed roles</span>
                  <select v-model="rule.allowedRoles" multiple :aria-label="`${rule.id} allowed roles`" @change="touchDraft">
                    <option v-for="role in roleOptions" :key="role" :value="role">{{ draftRoleLabel(role) }} · {{ role }}</option>
                  </select>
                </label>
                <label class="boolean-field">
                  <input v-model="rule.requireOwnerMatch" type="checkbox" :aria-label="`${rule.id} require owner match`" @change="touchDraft" />
                  <span><strong>Require owner-match</strong><small>只允许与资源 owner 相符的身份</small></span>
                </label>
              </div>
            </article>
          </div>
        </section>

        <section class="rule-editor-section" aria-labelledby="tools-title">
          <div class="section-heading">
            <div>
              <p class="group-kicker">工具规则</p>
              <h3 id="tools-title">ToolRule</h3>
            </div>
            <span class="section-note">{{ draft.toolRules.length }} rules · IDs 保持稳定</span>
          </div>
          <div class="rule-card-grid">
            <article v-for="rule in draft.toolRules" :key="rule.id" class="rule-card">
              <div class="rule-card-heading">
                <div>
                  <span class="rule-kind">TOOL RULE</span>
                  <h4>{{ rule.toolName }} · {{ rule.action }}</h4>
                </div>
                <code>{{ rule.id }}</code>
              </div>
              <div class="form-grid">
                <label class="input-field input-field-wide">
                  <span class="input-label">Description</span>
                  <input v-model="rule.description" :aria-label="`${rule.id} description`" @input="touchDraft" />
                </label>
                <label class="input-field">
                  <span class="input-label">Tool</span>
                  <input v-model="rule.toolName" :aria-label="`${rule.id} toolName`" @input="touchDraft" />
                </label>
                <label class="input-field">
                  <span class="input-label">Action</span>
                  <input v-model="rule.action" :aria-label="`${rule.id} action`" @input="touchDraft" />
                </label>
                <label class="input-field">
                  <span class="input-label">Allowed roles</span>
                  <select v-model="rule.allowedRoles" multiple :aria-label="`${rule.id} allowed roles`" @change="touchDraft">
                    <option v-for="role in roleOptions" :key="role" :value="role">{{ draftRoleLabel(role) }} · {{ role }}</option>
                  </select>
                </label>
                <label class="input-field">
                  <span class="input-label">maxRecords</span>
                  <input :value="rule.maxRecords ?? ''" type="number" min="1" step="1" :aria-label="`${rule.id} maxRecords`" @input="updateMaxRecords(rule, $event)" />
                  <small class="input-help">留空表示 null</small>
                </label>
                <label class="boolean-field">
                  <input v-model="rule.requireOwnerMatch" type="checkbox" :aria-label="`${rule.id} require owner match`" @change="touchDraft" />
                  <span><strong>Require owner-match</strong><small>工具对象 owner 必须相符</small></span>
                </label>
                <label class="boolean-field">
                  <input v-model="rule.requireApproval" type="checkbox" :aria-label="`${rule.id} require approval`" @change="touchDraft" />
                  <span><strong>Require approval</strong><small>没有批准时阻止动作</small></span>
                </label>
              </div>
            </article>
          </div>
        </section>

        <section class="rule-editor-section" aria-labelledby="sinks-title">
          <div class="section-heading">
            <div>
              <p class="group-kicker">外发规则</p>
              <h3 id="sinks-title">SinkRule</h3>
            </div>
            <span class="section-note">{{ draft.sinkRules.length }} rules · IDs 保持稳定</span>
          </div>
          <div class="rule-card-grid">
            <article v-for="rule in draft.sinkRules" :key="rule.id" class="rule-card">
              <div class="rule-card-heading">
                <div>
                  <span class="rule-kind">SINK RULE</span>
                  <h4>{{ sinkTypeLabel(rule.sinkType) }}</h4>
                </div>
                <code>{{ rule.id }}</code>
              </div>
              <div class="form-grid">
                <label class="input-field input-field-wide">
                  <span class="input-label">Description</span>
                  <input v-model="rule.description" :aria-label="`${rule.id} description`" @input="touchDraft" />
                </label>
                <label class="input-field">
                  <span class="input-label">Sink type</span>
                  <select v-model="rule.sinkType" :aria-label="`${rule.id} sinkType`" @change="touchDraft">
                    <option value="external_message">外部消息 · external_message</option>
                    <option value="customer_export">客户导出 · customer_export</option>
                  </select>
                </label>
                <label class="input-field">
                  <span class="input-label">Allowed roles</span>
                  <select v-model="rule.allowedRoles" multiple :aria-label="`${rule.id} allowed roles`" @change="touchDraft">
                    <option v-for="role in roleOptions" :key="role" :value="role">{{ draftRoleLabel(role) }} · {{ role }}</option>
                  </select>
                </label>
                <div class="list-field">
                  <span class="input-label">Match labels</span>
                  <div class="token-list">
                    <span v-for="(label, index) in rule.matchLabels" :key="`${rule.id}-label-${index}`" class="token-item">
                      <input v-model="rule.matchLabels[index]" :aria-label="`${rule.id} matchLabels ${index + 1}`" @input="touchDraft" />
                      <button type="button" class="token-remove" :aria-label="`删除 ${rule.id} label ${index + 1}`" @click="removeListValue(rule.matchLabels, index)">×</button>
                    </span>
                  </div>
                  <div class="list-add-row">
                    <input
                      :value="listDraftValue('sinkRules', rule.id, 'matchLabels')"
                      :aria-label="`${rule.id} 新增 match label`"
                      placeholder="新增 label"
                      @input="setListDraftValue('sinkRules', rule.id, 'matchLabels', ($event.target as HTMLInputElement).value)"
                      @keyup.enter="addListValue('sinkRules', rule.id, 'matchLabels', rule.matchLabels)"
                    />
                    <button type="button" class="token-add" @click="addListValue('sinkRules', rule.id, 'matchLabels', rule.matchLabels)">添加</button>
                  </div>
                </div>
                <div class="list-field">
                  <span class="input-label">Blocked source trust levels</span>
                  <div class="token-list">
                    <span v-for="(trustLevel, index) in rule.blockedSourceTrustLevels" :key="`${rule.id}-trust-${index}`" class="token-item">
                      <input v-model="rule.blockedSourceTrustLevels[index]" :aria-label="`${rule.id} blockedSourceTrustLevels ${index + 1}`" @input="touchDraft" />
                      <button type="button" class="token-remove" :aria-label="`删除 ${rule.id} trust level ${index + 1}`" @click="removeListValue(rule.blockedSourceTrustLevels, index)">×</button>
                    </span>
                  </div>
                  <div class="list-add-row">
                    <input
                      :value="listDraftValue('sinkRules', rule.id, 'blockedSourceTrustLevels')"
                      :aria-label="`${rule.id} 新增 blocked source trust level`"
                      placeholder="新增 trust level"
                      @input="setListDraftValue('sinkRules', rule.id, 'blockedSourceTrustLevels', ($event.target as HTMLInputElement).value)"
                      @keyup.enter="addListValue('sinkRules', rule.id, 'blockedSourceTrustLevels', rule.blockedSourceTrustLevels)"
                    />
                    <button type="button" class="token-add" @click="addListValue('sinkRules', rule.id, 'blockedSourceTrustLevels', rule.blockedSourceTrustLevels)">添加</button>
                  </div>
                </div>
                <label class="boolean-field">
                  <input v-model="rule.allowExternal" type="checkbox" :aria-label="`${rule.id} allow external`" @change="touchDraft" />
                  <span><strong>Allow external</strong><small>允许数据到 external destination</small></span>
                </label>
                <label class="boolean-field">
                  <input v-model="rule.requireApproval" type="checkbox" :aria-label="`${rule.id} require approval`" @change="touchDraft" />
                  <span><strong>Require approval</strong><small>外发前需要显式批准</small></span>
                </label>
              </div>
            </article>
          </div>
        </section>
      </div>

      <section v-if="props.preview || props.previewLoading" class="preview-panel" data-testid="contract-preview-panel" aria-labelledby="contract-preview-title">
        <div class="section-heading preview-heading">
          <div>
            <p class="group-kicker">预览 / Contract 与 Plan</p>
            <h3 id="contract-preview-title">保存前影响预览</h3>
          </div>
          <span v-if="props.previewLoading" class="preview-status is-loading">计算中…</span>
          <span v-else-if="hasCurrentPreview" class="preview-status is-ready">与当前 Draft 一致</span>
          <span v-else class="preview-status is-expired">已过期</span>
        </div>

        <div v-if="props.previewLoading" class="preview-loading" role="status" aria-live="polite">
          <span class="loading-mark" aria-hidden="true">…</span>
          <span>服务端正在依据 active Contract 和真实 Planner 计算结构化影响。</span>
        </div>

        <template v-if="props.preview">
          <div class="preview-overview">
            <div>
              <span>Contract</span>
              <strong>{{ props.preview.contractId }}</strong>
              <small>active v{{ props.preview.activeVersion }} → candidate v{{ props.preview.candidateVersion }}</small>
            </div>
            <div>
              <span>Field changes</span>
              <strong>{{ props.preview.fieldChanges.length }}</strong>
              <small>结构化字段变化</small>
            </div>
            <div>
              <span>Plan changes</span>
              <strong>{{ props.preview.planChanges.length }}</strong>
              <small>{{ currentPlanCount }} → {{ candidatePlanCount }} plans</small>
            </div>
          </div>

          <div class="impact-columns">
            <article class="impact-card">
              <div class="impact-card-heading">
                <div>
                  <p class="group-kicker">字段变化</p>
                  <h4>字段变化</h4>
                </div>
                <span>{{ props.preview.fieldChanges.length }}</span>
              </div>
              <ul v-if="props.preview.fieldChanges.length > 0" class="impact-list">
                <li v-for="change in props.preview.fieldChanges" :key="`${change.path}-${change.kind}`" :class="changeClass(change.kind)">
                  <div class="impact-row-heading">
                    <span class="impact-kind">{{ changeLabel(change.kind) }}</span>
                    <code>{{ fieldPathLabel(change) }}</code>
                  </div>
                  <div class="impact-values">
                    <span><small>before</small><code>{{ fieldChangeValue(change.beforeValue) }}</code></span>
                    <span><small>after</small><code>{{ fieldChangeValue(change.afterValue) }}</code></span>
                  </div>
                </li>
              </ul>
              <p v-else class="impact-empty">没有字段变化。</p>
            </article>

            <article class="impact-card">
              <div class="impact-card-heading">
                <div>
                  <p class="group-kicker">Plan 变化</p>
                  <h4>Attack Plan 变化</h4>
                </div>
                <span>{{ props.preview.planChanges.length }}</span>
              </div>
              <ul v-if="props.preview.planChanges.length > 0" class="impact-list">
                <li v-for="change in props.preview.planChanges" :key="`${change.planId}-${change.kind}`" :class="changeClass(change.kind)">
                  <div class="impact-row-heading">
                    <span class="impact-kind">{{ changeLabel(change.kind) }}</span>
                    <code>{{ change.planId }}</code>
                  </div>
                  <p class="impact-plan-basis">{{ basisTypeLabel(change.basisType) }} · {{ change.basisRuleId ?? "无 basisRuleId" }}</p>
                </li>
              </ul>
              <p v-else class="impact-empty">Planner 输出没有变化。</p>
            </article>
          </div>

          <details class="plan-snapshot-details">
            <summary>展开当前 / candidate Plan 摘要</summary>
            <div class="plan-snapshot-columns">
              <div>
                <p class="snapshot-label">CURRENT · {{ props.preview.currentPlans.length }}</p>
                <ul class="snapshot-list">
                  <li v-for="plan in props.preview.currentPlans" :key="`current-${plan.id}`">
                    <strong>{{ planName(plan) }}</strong>
                    <code>{{ plan.id }}</code>
                    <small>{{ basisTypeLabel(plan.basisType) }} · {{ plan.basisRuleId }}</small>
                  </li>
                </ul>
              </div>
              <div>
                <p class="snapshot-label">CANDIDATE · {{ props.preview.candidatePlans.length }}</p>
                <ul class="snapshot-list">
                  <li v-for="plan in props.preview.candidatePlans" :key="`candidate-${plan.id}`">
                    <strong>{{ planName(plan) }}</strong>
                    <code>{{ plan.id }}</code>
                    <small>{{ basisTypeLabel(plan.basisType) }} · {{ plan.basisRuleId }}</small>
                  </li>
                </ul>
              </div>
            </div>
          </details>
        </template>
      </section>

      <div class="editor-actions">
        <button class="editor-button editor-button-secondary" data-testid="contract-cancel" type="button" :disabled="props.saving" @click="cancelEdit">
          取消
        </button>
        <button class="editor-button editor-button-secondary" data-testid="contract-preview" type="button" :disabled="!canPreview" :aria-busy="props.previewLoading" @click="requestPreview">
          {{ props.previewLoading ? "预览中…" : "预览影响" }}
        </button>
        <button class="editor-button editor-button-primary" data-testid="contract-save" type="button" :disabled="!canSave" :aria-busy="props.saving" @click="saveDraft">
          {{ props.saving ? "保存中…" : "保存 Contract" }}
        </button>
      </div>
    </div>

    <div v-else class="editor-empty" role="status">暂时无法读取 Security Contract。</div>
  </section>
</template>

<style scoped>
.security-contract-editor {
  min-width: 0;
  color: var(--ink, #26364c);
  --editor-action: var(--action-blue, #4f7cff);
  --editor-evidence: var(--evidence-teal, #168f82);
  --editor-risk: var(--risk-coral, #e05252);
  --editor-warning: var(--warning-amber, #b87512);
  --editor-surface: var(--surface, #ffffff);
  --editor-raised: var(--surface-raised, #f8fafc);
}

.contract-editor-header,
.draft-toolbar,
.section-heading,
.rule-card-heading,
.group-heading,
.preview-heading,
.impact-card-heading,
.editor-actions,
.editor-header-actions {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.contract-editor-header {
  gap: 20px;
}

.editor-kicker,
.group-kicker,
.editor-mode-label,
.rule-kind,
.snapshot-label {
  margin: 0;
  color: var(--ink-faint, #94a3b8);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.contract-editor-header h2 {
  margin: 7px 0 0;
  color: var(--ink-strong, #132238);
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.editor-subtitle,
.editor-boundary,
.input-help,
.draft-status,
.input-field small,
.boolean-field small,
.read-only-list small,
.preview-overview small,
.impact-plan-basis,
.snapshot-list small {
  color: var(--ink-muted, #64748b);
  font-size: 10px;
  line-height: 1.5;
}

.editor-subtitle {
  margin: 8px 0 0;
  font-size: 12px;
}

.editor-header-actions {
  align-items: center;
  flex-shrink: 0;
}

.editor-mode-label {
  white-space: nowrap;
}

.editor-button {
  min-height: 34px;
  padding: 8px 13px;
  border-radius: 7px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 650;
  transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
}

.editor-button:disabled,
.mode-switch-button:disabled,
.token-add:disabled,
.token-remove:disabled {
  cursor: not-allowed;
  opacity: 0.48;
}

.editor-button-secondary {
  color: var(--action-blue, #4f7cff);
  background: transparent;
  border: 1px solid rgba(79, 124, 255, 0.42);
}

.editor-button-secondary:hover:not(:disabled) {
  color: #ffffff;
  background: var(--action-blue, #4f7cff);
  border-color: var(--action-blue, #4f7cff);
}

.editor-button-primary {
  color: #ffffff;
  background: var(--evidence-teal, #25bfae);
  border: 1px solid var(--evidence-teal, #25bfae);
}

.editor-button-primary:hover:not(:disabled) {
  background: #1fa895;
  border-color: #1fa895;
}

.editor-button-primary:disabled {
  color: rgba(7, 24, 32, 0.55);
  background: var(--evidence-teal-wash, rgba(22, 143, 130, 0.16));
  border-color: transparent;
}

.editor-boundary {
  margin: 18px 0 0;
}

.editor-boundary summary {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  color: var(--action-blue, #4f7cff);
  cursor: pointer;
  font-size: 10px;
}

.editor-boundary > span {
  display: block;
  margin: 6px 0 0 13px;
}

.boundary-dot,
.draft-status-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 5px;
  margin-top: 5px;
  background: var(--editor-evidence);
  border-radius: 50%;
}

.editor-notice,
.editor-error,
.editor-loading,
.preview-loading {
  margin: 15px 0 0;
  padding: 10px 12px;
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 7px;
  font-size: 11px;
  line-height: 1.5;
}

.editor-notice {
  color: #087f73;
  background: #e9fbf7;
  border-color: rgba(37, 191, 174, 0.3);
}

.editor-error {
  color: #8f2d2d;
  background: #fff3f2;
  border-color: rgba(255, 93, 93, 0.35);
  overflow-wrap: anywhere;
}

.editor-loading,
.preview-loading {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--ink-muted, #64748b);
  background: #f1f5ff;
  border-color: rgba(79, 124, 255, 0.26);
}

.loading-mark {
  color: var(--action-blue, #4f7cff);
  font-size: 17px;
  line-height: 1;
}

.contract-identity {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 21px;
  color: var(--ink-muted, #64748b);
  font-size: 11px;
}

.contract-identity code,
.read-only-list code,
.rule-card-heading code,
.snapshot-list code {
  color: var(--editor-evidence);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
}

.contract-identity span:last-child {
  padding-left: 10px;
  color: var(--ink-faint, #8a99ad);
  border-left: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 10px;
}

.contract-summary-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 17px 0 0;
}

.contract-summary-metrics > div {
  min-width: 0;
  padding: 10px;
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 7px;
}

.contract-summary-metrics dt {
  color: var(--ink-faint, #8a99ad);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  overflow-wrap: anywhere;
}

.contract-summary-metrics dd {
  margin: 6px 0 0;
  color: var(--ink-strong, #132238);
  font-size: 19px;
  font-weight: 700;
}

.read-only-groups {
  display: grid;
  gap: 10px;
  margin-top: 16px;
}

.read-only-group,
.metadata-editor,
.rule-editor-section,
.preview-panel {
  min-width: 0;
  padding: 15px;
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 9px;
}

.group-heading {
  align-items: baseline;
}

.group-heading h3,
.section-heading h3 {
  margin: 5px 0 0;
  color: var(--ink-strong, #132238);
  font-size: 14px;
  font-weight: 650;
}

.group-heading > span,
.section-note,
.impact-card-heading > span {
  flex-shrink: 0;
  color: var(--ink-faint, #8a99ad);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.read-only-list,
.impact-list,
.snapshot-list {
  display: grid;
  gap: 7px;
  margin: 11px 0 0;
  padding: 0;
  list-style: none;
}

.read-only-list li {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 5px;
  align-items: baseline;
  min-width: 0;
  padding: 9px 10px;
  background: var(--surface, #ffffff);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 6px;
}

.read-only-list li > span {
  min-width: 0;
  color: var(--ink, #24364d);
  font-size: 11px;
  overflow-wrap: anywhere;
}

.read-only-list small {
  grid-column: 1 / -1;
  color: var(--ink-faint, #8a99ad);
  overflow-wrap: anywhere;
}

.editor-workspace {
  display: grid;
  gap: 14px;
  margin-top: 20px;
}

.draft-toolbar {
  align-items: flex-end;
  min-width: 0;
  padding-bottom: 2px;
}

.draft-identity {
  margin-top: 0;
}

.draft-status {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 8px 0 0;
}

.draft-status.is-expired {
  color: #8a5b11;
}

.draft-status.is-expired .draft-status-dot {
  background: var(--warning-amber, #e6a23c);
}

.draft-status.is-ready {
  color: #087f73;
}

.mode-switch {
  display: inline-flex;
  max-width: 100%;
  padding: 3px;
  background: var(--surface-raised, #f8fafc);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 7px;
}

.mode-switch-button {
  min-height: 29px;
  padding: 6px 9px;
  color: var(--ink-muted, #64748b);
  background: transparent;
  border: 0;
  border-radius: 5px;
  cursor: pointer;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.mode-switch-button.is-active {
  color: #ffffff;
  background: var(--action-blue, #4f7cff);
}

.visual-editor-pane {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.section-heading {
  align-items: baseline;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 11px;
  margin-top: 13px;
}

.form-grid-three {
  grid-template-columns: minmax(105px, 0.8fr) minmax(0, 1.5fr) minmax(92px, 0.55fr);
}

.input-field,
.list-field {
  display: grid;
  min-width: 0;
  gap: 6px;
}

.input-field-wide {
  grid-column: 1 / -1;
}

.input-label {
  color: var(--ink, #24364d);
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.03em;
}

.input-field input,
.input-field select,
.list-add-row input,
.token-item input,
.contract-json-input {
  width: 100%;
  min-width: 0;
  color: var(--ink-strong, #132238);
  background: var(--surface, #ffffff);
  border: 1px solid var(--line-bright, rgba(160, 181, 207, 0.28));
  border-radius: 6px;
  outline: none;
  font-size: 11px;
}

.input-field input,
.list-add-row input,
.token-item input {
  min-height: 34px;
  padding: 7px 9px;
}

.input-field select {
  min-height: 76px;
  padding: 6px 7px;
}

.input-field input[readonly] {
  color: var(--ink-faint, #8a99ad);
  background: var(--surface-raised, #f8fafc);
}

.input-field input:focus,
.input-field select:focus,
.list-add-row input:focus,
.token-item input:focus,
.contract-json-input:focus {
  border-color: rgba(79, 124, 255, 0.68);
  box-shadow: 0 0 0 3px rgba(79, 124, 255, 0.1);
}

.input-field input::placeholder,
.list-add-row input::placeholder {
  color: var(--ink-faint, #8a99ad);
}

.input-help {
  margin: 0;
  color: var(--ink-faint, #8a99ad);
}

.boolean-field {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  min-width: 0;
  padding: 9px 10px;
  background: var(--surface, #ffffff);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 6px;
  cursor: pointer;
}

.boolean-field input {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
  margin: 1px 0 0;
  accent-color: var(--editor-action);
}

.boolean-field span {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.boolean-field strong {
  color: var(--ink, #24364d);
  font-size: 10px;
}

.boolean-field small {
  overflow-wrap: anywhere;
}

.rule-card-grid {
  display: grid;
  gap: 10px;
  margin-top: 13px;
}

.rule-card {
  min-width: 0;
  padding: 13px;
  background: var(--surface, #ffffff);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 8px;
}

.rule-card-heading {
  align-items: baseline;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line, rgba(160, 181, 207, 0.16));
}

.rule-card-heading h4 {
  margin: 5px 0 0;
  color: var(--ink-strong, #132238);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.list-field {
  grid-column: 1 / -1;
}

.token-list {
  display: grid;
  gap: 6px;
}

.token-item {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
}

.token-item input {
  flex: 1 1 auto;
}

.token-remove,
.token-add {
  min-height: 32px;
  padding: 6px 9px;
  color: var(--ink-muted, #64748b);
  background: rgba(160, 181, 207, 0.08);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 5px;
  cursor: pointer;
  font-size: 10px;
}

.token-remove {
  flex: 0 0 30px;
  padding: 5px;
  color: var(--risk-coral, #e05252);
}

.token-remove:hover:not(:disabled) {
  background: var(--risk-coral-wash, rgba(224, 82, 82, 0.1));
  border-color: rgba(224, 82, 82, 0.38);
}

.token-add {
  color: var(--editor-evidence);
  border-color: rgba(22, 143, 130, 0.3);
}

.token-add:hover:not(:disabled) {
  background: var(--evidence-teal-wash, rgba(22, 143, 130, 0.1));
}

.list-add-row {
  display: flex;
  min-width: 0;
  gap: 6px;
  margin-top: 6px;
}

.list-add-row input {
  flex: 1 1 auto;
}

.json-editor-pane {
  min-width: 0;
}

.contract-json-input {
  display: block;
  min-height: 390px;
  margin-top: 7px;
  padding: 13px;
  resize: vertical;
  color: var(--ink, #24364d);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 10px;
  line-height: 1.6;
  white-space: pre;
}

.json-editor-pane > .input-help {
  margin-top: 7px;
}

.preview-panel {
  background: var(--editor-raised);
}

.preview-status {
  flex-shrink: 0;
  padding: 5px 8px;
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 999px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.preview-status.is-loading {
  color: var(--editor-action);
  border-color: rgba(79, 124, 255, 0.35);
}

.preview-status.is-ready {
  color: var(--editor-evidence);
  border-color: rgba(22, 143, 130, 0.35);
}

.preview-status.is-expired {
  color: var(--editor-warning);
  border-color: rgba(184, 117, 18, 0.35);
}

.preview-overview {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 13px;
}

.preview-overview > div {
  min-width: 0;
  padding: 10px;
  background: var(--editor-surface);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 6px;
}

.preview-overview span,
.preview-overview strong,
.preview-overview small {
  display: block;
  overflow-wrap: anywhere;
}

.preview-overview span {
  color: var(--ink-faint, #8a99ad);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
}

.preview-overview strong {
  margin-top: 5px;
  color: var(--ink-strong, #132238);
  font-size: 15px;
}

.preview-overview small {
  margin-top: 3px;
}

.impact-columns,
.plan-snapshot-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 9px;
  margin-top: 10px;
}

.impact-card {
  min-width: 0;
  padding: 11px;
  background: var(--editor-surface);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 7px;
}

.impact-card-heading {
  align-items: baseline;
}

.impact-card-heading h4 {
  margin: 4px 0 0;
  color: var(--ink-strong, #132238);
  font-size: 12px;
}

.impact-list li {
  min-width: 0;
  padding: 8px;
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-left-width: 2px;
  border-radius: 5px;
}

.impact-list li.is-added {
  border-left-color: var(--editor-evidence);
}

.impact-list li.is-removed {
  border-left-color: var(--editor-risk);
}

.impact-list li.is-changed {
  border-left-color: var(--editor-action);
}

.impact-row-heading {
  display: flex;
  min-width: 0;
  align-items: baseline;
  gap: 7px;
}

.impact-row-heading code {
  min-width: 0;
  color: var(--ink, #24364d);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  overflow-wrap: anywhere;
}

.impact-kind {
  flex: 0 0 auto;
  color: var(--ink-muted, #64748b);
  font-size: 9px;
}

.impact-values {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 6px;
  margin-top: 7px;
}

.impact-values span {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.impact-values small {
  color: var(--ink-faint, #8a99ad);
  font-size: 8px;
}

.impact-values code {
  min-width: 0;
  padding: 4px 5px;
  color: var(--ink, #24364d);
  background: var(--editor-raised);
  border-radius: 4px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 8px;
  line-height: 1.4;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.impact-plan-basis {
  margin: 6px 0 0;
  overflow-wrap: anywhere;
}

.impact-empty {
  margin: 11px 0 0;
  color: var(--ink-faint, #8a99ad);
  font-size: 10px;
}

.plan-snapshot-details {
  margin-top: 10px;
  border-top: 1px solid var(--line, rgba(160, 181, 207, 0.16));
}

.plan-snapshot-details summary {
  padding-top: 10px;
  color: var(--ink-muted, #64748b);
  cursor: pointer;
  font-size: 10px;
}

.snapshot-label {
  margin-top: 10px;
}

.snapshot-list li {
  display: grid;
  min-width: 0;
  gap: 3px;
  padding: 8px;
  background: var(--editor-surface);
  border: 1px solid var(--line, rgba(160, 181, 207, 0.16));
  border-radius: 5px;
}

.snapshot-list strong {
  color: var(--ink, #24364d);
  font-size: 10px;
  overflow-wrap: anywhere;
}

.snapshot-list small {
  overflow-wrap: anywhere;
}

.editor-actions {
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 1px;
}

.editor-empty {
  margin-top: 22px;
  padding: 22px;
  color: var(--ink-muted, #64748b);
  text-align: center;
  border: 1px dashed var(--line-bright, rgba(160, 181, 207, 0.28));
  border-radius: 8px;
  font-size: 11px;
}

@media (max-width: 760px) {
  .contract-editor-header,
  .draft-toolbar,
  .section-heading,
  .editor-header-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .editor-header-actions {
    width: 100%;
    gap: 9px;
  }

  .editor-header-actions .editor-button {
    width: 100%;
  }

  .contract-summary-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mode-switch {
    width: 100%;
  }

  .mode-switch-button {
    flex: 1 1 0;
  }

  .form-grid,
  .form-grid-three,
  .impact-columns,
  .plan-snapshot-columns {
    grid-template-columns: 1fr;
  }

  .editor-actions {
    align-items: stretch;
    flex-direction: column-reverse;
  }

  .editor-actions .editor-button {
    width: 100%;
  }
}

@media (max-width: 390px) {
  .read-only-group,
  .metadata-editor,
  .rule-editor-section,
  .preview-panel {
    padding: 12px;
  }

  .contract-summary-metrics {
    gap: 6px;
  }

  .contract-summary-metrics > div {
    padding: 8px;
  }

  .rule-card {
    padding: 10px;
  }

  .impact-values {
    grid-template-columns: 1fr;
  }

  .read-only-list li {
    grid-template-columns: 1fr;
  }

  .read-only-list code {
    grid-row: 2;
  }
}

/* F-063: keep Contract editing dense in data, not in typography. The
 * surrounding workspace owns the main surface; groups and rule cards use
 * dividers so the editor does not become a stack of cards inside a card. */
.security-contract-editor {
  --editor-line: var(--line, #dce5ef);
  --editor-surface: var(--surface, #ffffff);
  --editor-raised: var(--surface-raised, #f8fafc);
  font-family: var(--font-ui);
  font-size: var(--type-body-size, 16px);
  line-height: var(--type-body-leading, 1.62);
}

.contract-editor-header h2 {
  font-size: var(--type-section-title-size, 24px);
  line-height: var(--type-heading-leading, 1.22);
}

.editor-kicker,
.group-kicker,
.editor-mode-label,
.rule-kind,
.snapshot-label,
.input-label,
.section-note,
.group-heading > span,
.impact-card-heading > span {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
  letter-spacing: normal;
}

.editor-subtitle,
.editor-boundary,
.editor-boundary > span,
.input-help,
.draft-status,
.input-field small,
.boolean-field small,
.read-only-list small,
.preview-overview small,
.impact-plan-basis,
.snapshot-list small,
.editor-notice,
.editor-error,
.editor-loading,
.preview-loading,
.editor-empty {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.editor-boundary summary,
.plan-snapshot-details summary {
  font-family: var(--font-ui);
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.editor-button,
.mode-switch-button,
.token-add,
.token-remove {
  min-height: 44px;
  border-radius: var(--radius-control, 9px);
  font-family: var(--font-ui);
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.mode-switch-button {
  padding: 8px 12px;
}

.contract-identity {
  font-size: var(--type-body-small-size, 14px);
}

.contract-identity code,
.read-only-list code,
.rule-card-heading code,
.snapshot-list code,
.impact-row-heading code,
.impact-values code,
.plan-snapshot-details code {
  font-family: var(--font-code);
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
}

.contract-summary-metrics dt {
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.read-only-group,
.metadata-editor,
.rule-editor-section,
.preview-panel {
  padding: var(--space-4, 16px) 0;
  background: transparent;
  border: 0;
  border-top: 1px solid var(--editor-line);
  border-radius: 0;
  box-shadow: none;
}

.group-heading h3,
.section-heading h3,
.impact-card-heading h4 {
  font-size: var(--type-card-title-size, 18px);
  line-height: var(--type-heading-leading, 1.22);
}

.read-only-list li,
.rule-card,
.impact-card,
.snapshot-list li {
  background: transparent;
  border-color: var(--editor-line);
  box-shadow: none;
}

.read-only-list li > span,
.boolean-field strong,
.impact-kind,
.preview-overview > div > span {
  font-size: var(--type-body-small-size, 14px);
  line-height: var(--type-body-small-leading, 1.55);
}

.input-field input,
.input-field select,
.list-add-row input,
.token-item input,
.contract-json-input {
  min-height: 44px;
  border-radius: var(--radius-control, 9px);
  font-family: var(--font-ui);
  font-size: var(--type-body-size, 16px);
}

.input-field select {
  min-height: 88px;
}

.boolean-field {
  border-color: var(--editor-line);
  border-radius: var(--radius-control, 9px);
}

.boolean-field small,
.input-help,
.impact-values small {
  font-size: var(--type-label-size, 12px);
  line-height: var(--type-label-leading, 1.35);
}

.preview-overview {
  border-color: var(--editor-line);
  background: var(--editor-raised);
  border-radius: var(--radius-control, 9px);
}

.impact-list li,
.snapshot-list li {
  border-radius: var(--radius-control, 9px);
}

.security-contract-editor :is(button, input, select, textarea):focus-visible {
  outline: 2px solid var(--action-blue, #4f7cff);
  outline-offset: 2px;
}

/* F-063 second visual pass: keep rule evidence dense without shrinking the
 * explanatory copy or making disclosure rows hard to activate on mobile. */
.editor-subtitle,
.editor-boundary,
.editor-boundary > span,
.input-help,
.draft-status,
.input-field small,
.boolean-field small,
.read-only-list small,
.preview-overview small,
.impact-plan-basis,
.snapshot-list small,
.editor-notice,
.editor-error,
.editor-loading,
.preview-loading,
.editor-empty {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.editor-boundary summary,
.plan-snapshot-details summary {
  display: flex;
  align-items: center;
  min-height: 44px;
  padding: 10px 0;
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.editor-button,
.mode-switch-button,
.token-add,
.token-remove {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.contract-identity > span:last-child {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}

.contract-identity {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.read-only-list li > span,
.boolean-field strong,
.impact-kind,
.preview-overview > div > span {
  font-size: max(14px, var(--type-body-small-size, 14px));
  line-height: var(--type-body-small-leading, 1.55);
}

.contract-identity code,
.read-only-list code,
.rule-card-heading code,
.snapshot-list code,
.impact-row-heading code,
.impact-values code,
.plan-snapshot-details code {
  font-size: max(13px, var(--type-code-size, 13px));
  line-height: var(--type-code-leading, 1.5);
}

/* Keep each rule's name, identifier and attributes in one reading column. */
.role-summary-grid, .rule-summary-grid { gap: 12px; }
.role-summary-grid li, .rule-summary-grid li {
  align-content: start;
  padding: 14px 16px;
  background: linear-gradient(135deg, #f6fafc, #ffffff);
  border-color: #d9e5ed;
  border-left: 3px solid #8abebc;
  border-radius: 8px;
}
.role-summary-grid code, .rule-summary-grid code {
  justify-self: start;
  max-width: 100%;
  overflow-wrap: anywhere;
  white-space: normal;
  color: #527786;
}
.rule-summary-grid small { margin-top: 4px; padding-top: 8px; border-top: 1px solid var(--editor-line); }
@media (min-width: 600px) {
  .role-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (min-width: 1000px) {
  .role-summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .rule-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
