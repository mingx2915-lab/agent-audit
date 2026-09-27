<script setup lang="ts">
import type { BlockedExecution } from "@agent-audit/contracts";
defineProps<{ outcome: BlockedExecution }>();
</script>

<template>
  <section class="blocked-execution" data-testid="blocked-execution" aria-label="权限拦截执行结果" role="status">
    <h3>执行已结束：工具调用被权限拦截</h3>
    <p>当前测试身份无权执行这次工具操作，系统已停止该调用。这是权限检查结果，模型连接没有因此断开。</p>
    <p v-if="outcome.evaluation.findings.length">
      <strong>拦截前仍发现 {{ outcome.evaluation.findings.length }} 项风险。</strong>
      工具被拦截不代表此前的资料访问符合权限；请查看下面的风险证据。
    </p>
    <p v-else>在本次已记录的执行过程中，未发现违反权限规则的行为。这个结论仅针对本次执行。</p>
    <ul v-if="outcome.evaluation.findings.length">
      <li v-for="finding in outcome.evaluation.findings" :key="finding.id">
        <strong>{{ finding.title }}</strong> — {{ finding.summary }}
        <small>证据步骤：{{ finding.evidenceSequences.join("、") }}</small>
      </li>
    </ul>
    <details>
      <summary>查看执行记录与拒绝原因（{{ outcome.traceEvents.length }} 步）</summary>
      <p>{{ outcome.blockedReason }}</p>
      <ol>
        <li v-for="event in outcome.traceEvents" :key="event.sequence">
          <strong>#{{ event.sequence }} · {{ event.type }}</strong> {{ event.summary }}
          <pre>{{ JSON.stringify(event.details, null, 2) }}</pre>
        </li>
      </ol>
    </details>
    <p class="next-step">可根据证据检查权限规则，或执行其他测试场景；无需重新连接模型。</p>
  </section>
</template>

<style scoped>
.blocked-execution { margin: 16px 0; padding: 20px 24px; border: 1px solid #d6e1eb; border-left: 4px solid #d69b39; border-radius: 12px; background: #fff; color: #18334f; }
h3 { margin: 0 0 10px; font-size: 20px; }
p { margin: 8px 0; line-height: 1.65; }
li { margin: 10px 0; line-height: 1.6; }
small { display: block; color: #62758a; }
summary { cursor: pointer; padding: 12px 0; font-weight: 600; }
pre { overflow: auto; max-height: 240px; padding: 12px; background: #f3f6fa; font-size: 13px; white-space: pre-wrap; overflow-wrap: anywhere; }
.next-step { color: #62758a; font-size: 14px; }
</style>
