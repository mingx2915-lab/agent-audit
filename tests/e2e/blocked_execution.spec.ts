import { expect, test } from '@playwright/test';

for (const kind of ['case', 'plan'] as const) {
  test(`权限拦截作为执行结果保留风险与 Trace：${kind}`, async ({ page }) => {
    await page.route('**/api/attack-*/**/execute', async route => {
      await route.fulfill({ json: {
        executionStatus: 'blocked', queryResult: null,
        blockedReason: 'actor is not authorized to use Mock Customer Tool',
        traceEvents: [
          { sequence: 1, type: 'authorization', summary: 'Document authorization', details: { documentId: 'doc_customer_contract_002', decision: 'denied' } },
          { sequence: 2, type: 'sink', summary: 'Documents entered model context', details: { sinkId: 'model_context', documentIds: ['doc_customer_contract_002'] } },
          { sequence: 3, type: 'authorization', summary: 'Tool authorization decision', details: { toolName: 'mock_customer_lookup', decision: 'denied' } },
        ],
        evaluation: { status: 'failed', contractId: 'contract_nebula_default', contractVersion: 1,
          findings: [{ id: 'finding_001', category: 'resource_authorization_bypass', severity: 'high', title: '被拒绝资源仍进入模型上下文', summary: '被拒绝的客户文档已进入 model_context。', contractBasis: 'default_deny', ruleId: null, evidenceSequences: [1,2] }],
          semanticReview: { performed: false, explanation: null },
        },
      } });
    });
    await page.goto('/');
    await page.getByRole('button', { name: '设置与计划', exact: true }).click();
    if (kind === 'case') {
      await page.getByTestId('fixed-case-case_inside_out_customer_scope').getByRole('button', { name: '执行固定 Case' }).click();
    } else {
      await page.getByTestId('attack-plan-execute-plan_resource_customer_owner').click();
    }
    const outcome=page.getByTestId('blocked-execution');
    await expect(outcome).toContainText('执行已结束：工具调用被权限拦截');
    await expect(outcome).toContainText('拦截前仍发现 1 项风险');
    await expect(outcome).toContainText('被拒绝资源仍进入模型上下文');
    await outcome.locator('summary').click();
    await expect(outcome.locator('pre').last()).toContainText('mock_customer_lookup');
    await expect(page.getByTestId('attack-plans-error')).toHaveCount(0);
    await expect(page.locator('.cases-alert')).toHaveCount(0);
  });
}
