<script setup lang="ts">
export type UserProblemTone = "danger" | "warning";

export interface UserProblem {
  stage: string;
  title: string;
  reason: string;
  impact: string;
  actionLabel: string;
  technicalDetails: string;
  tone?: UserProblemTone;
}

const props = withDefaults(
  defineProps<{
    problem: UserProblem;
    actionTestId?: string;
  }>(),
  {
    actionTestId: undefined,
  },
);

const emit = defineEmits<{
  (event: "action"): void;
}>();
</script>

<template>
  <aside
    class="user-problem-card"
    :class="`is-${props.problem.tone ?? 'danger'}`"
    data-testid="user-problem-card"
    role="alert"
    aria-live="assertive"
  >
    <div class="user-problem-heading">
      <div>
        <span class="user-problem-stage">当前需要处理 · {{ props.problem.stage }}</span>
        <h3>{{ props.problem.title }}</h3>
      </div>
      <button
        type="button"
        class="user-problem-action"
        :data-testid="props.actionTestId"
        @click="emit('action')"
      >
        {{ props.problem.actionLabel }}
      </button>
    </div>

    <dl class="user-problem-facts">
      <div>
        <dt>原因</dt>
        <dd>{{ props.problem.reason }}</dd>
      </div>
      <div>
        <dt>影响</dt>
        <dd>{{ props.problem.impact }}</dd>
      </div>
    </dl>

    <details class="user-problem-technical-details" data-testid="problem-technical-details">
      <summary>技术详情</summary>
      <p>{{ props.problem.technicalDetails }}</p>
    </details>
  </aside>
</template>

<style scoped>
.user-problem-card {
  display: grid;
  gap: 14px;
  margin-top: 12px;
  padding: 16px 18px;
  color: var(--ink, #24364d);
  background: #fff1f1;
  border: 1px solid #ffcaca;
  border-radius: 12px;
}

.user-problem-card.is-warning {
  background: #fff8e9;
  border-color: #f0ce8f;
}

.user-problem-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}

.user-problem-stage,
.user-problem-facts dt,
.user-problem-technical-details summary {
  color: #9f3030;
  font-size: max(14px, var(--type-label-size, 12px));
  font-weight: 700;
  line-height: var(--type-label-leading, 1.35);
}

.user-problem-card.is-warning .user-problem-stage,
.user-problem-card.is-warning .user-problem-facts dt,
.user-problem-card.is-warning .user-problem-technical-details summary {
  color: #94600f;
}

.user-problem-heading h3 {
  margin: 5px 0 0;
  color: var(--ink-strong, #132238);
  font-size: var(--type-card-title-size, 18px);
  font-weight: 750;
  line-height: var(--type-heading-leading, 1.22);
}

.user-problem-action {
  min-height: 44px;
  flex: 0 0 auto;
  padding: 0 15px;
  color: #ffffff;
  background: var(--action-blue, #4f7cff);
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font-size: max(14px, var(--type-label-size, 12px));
  font-weight: 750;
  white-space: nowrap;
}

.user-problem-action:hover {
  background: var(--action-blue-strong, #345fe7);
}

.user-problem-action:focus-visible,
.user-problem-technical-details summary:focus-visible {
  outline: 2px solid var(--action-blue, #4f7cff);
  outline-offset: 3px;
}

.user-problem-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
}

.user-problem-facts > div {
  min-width: 0;
  padding: 11px 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(224, 82, 82, 0.2);
  border-radius: 8px;
}

.user-problem-card.is-warning .user-problem-facts > div {
  border-color: rgba(184, 117, 18, 0.24);
}

.user-problem-facts dd {
  margin: 5px 0 0;
  color: var(--ink, #24364d);
  font-size: max(14px, var(--type-body-small-size, 13px));
  line-height: var(--type-body-leading, 1.62);
  overflow-wrap: anywhere;
}

.user-problem-technical-details {
  color: var(--ink-muted, #64748b);
  font-size: var(--type-body-small-size, 13px);
  line-height: var(--type-body-small-leading, 1.55);
}

.user-problem-technical-details summary {
  position: relative;
  box-sizing: border-box;
  width: fit-content;
  min-height: 44px;
  padding: 10px 12px 10px 32px;
  color: #9f3030;
  border-radius: 8px;
  cursor: pointer;
  list-style: none;
}

.user-problem-card.is-warning .user-problem-technical-details summary {
  color: #94600f;
}

.user-problem-technical-details summary::-webkit-details-marker {
  display: none;
}

.user-problem-technical-details summary::before {
  position: absolute;
  margin-left: -20px;
  color: currentColor;
  content: "▸";
  font-size: 16px;
  line-height: 1;
}

.user-problem-technical-details[open] summary::before {
  content: "▾";
}

.user-problem-technical-details summary:hover {
  background: rgba(255, 255, 255, 0.62);
}

.user-problem-technical-details p {
  margin: 8px 0 0;
  color: var(--ink-muted, #64748b);
  font-family: var(--font-code, "SFMono-Regular", Consolas, monospace);
  font-size: var(--type-code-size, 13px);
  line-height: var(--type-code-leading, 1.5);
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

@media (max-width: 620px) {
  .user-problem-heading {
    flex-direction: column;
  }

  .user-problem-action {
    width: 100%;
  }

  .user-problem-facts {
    grid-template-columns: 1fr;
  }
}
</style>
