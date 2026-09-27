import { expect, type Locator, type Page } from "@playwright/test";
import { test } from "./support/test";
import { chooseOnboardingPath, installConfiguredProviderState } from "./support/first_use";

type AuditRequests = {
  scanPosts: number;
  replayPosts: number;
  readinessPosts: number;
  apiNon2xx: string[];
  pageErrors: string[];
  consoleErrors: string[];
  requestFailures: string[];
};

type AttackPlan = {
  id: string;
  name: string;
  basisType: string;
  basisRuleId: string;
  attackerType: string;
  actorId: string;
  targetKind: string;
  targetId: string;
  message: string;
  targetProfileId: string;
};

type TraceEvent = {
  sequence: number;
  type: string;
  summary: string;
  details: Record<string, unknown>;
};

type Finding = {
  id: string;
  category: string;
  severity: string;
  title: string;
  summary: string;
  ruleId: string | null;
  evidenceSequences: number[];
};

type ScanAttempt = {
  round: number;
  status: string;
  queryResult: { actor: { id: string }; traceEvents: TraceEvent[] };
  evaluation: { status: string; findings: Finding[] };
};

type Scan = {
  id: string;
  planId: string;
  status: string;
  stopReason: string;
  attempts: ScanAttempt[];
};

type ReplayAttempt = {
  profileId: string;
  executionStatus: string;
  evaluation: { status: string; findings: Finding[] };
  traceEvents: TraceEvent[];
  blockedReason: string | null;
};

type Replay = {
  id: string;
  status: string;
  plan: AttackPlan;
  before: ReplayAttempt;
  after: ReplayAttempt;
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function isReplayPath(path: string): boolean {
  return (
    /^\/api\/attack-plans\/[^/]+\/replay$/.test(path) ||
    /^\/api\/scans\/[^/]+\/replays$/.test(path)
  );
}

function observeBrowserHealth(page: Page): AuditRequests {
  const evidence: AuditRequests = {
    scanPosts: 0,
    replayPosts: 0,
    readinessPosts: 0,
    apiNon2xx: [],
    pageErrors: [],
    consoleErrors: [],
    requestFailures: [],
  };

  page.on("pageerror", (error) => {
    evidence.pageErrors.push(error.message);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      evidence.consoleErrors.push(message.text());
    }
  });
  page.on("requestfailed", (request) => {
    evidence.requestFailures.push(
      `${request.method()} ${request.url()}: ${request.failure()?.errorText ?? "unknown"}`,
    );
  });
  page.on("request", (request) => {
    if (request.method() !== "POST") {
      return;
    }

    const path = apiPath(request.url());
    if (path === "/api/scans") {
      evidence.scanPosts += 1;
    } else if (isReplayPath(path)) {
      evidence.replayPosts += 1;
    } else if (path === "/api/provider-readiness") {
      evidence.readinessPosts += 1;
    }
  });
  page.on("response", (response) => {
    if (response.status() < 400 || !apiPath(response.url()).startsWith("/api/")) {
      return;
    }

    evidence.apiNon2xx.push(
      `${response.status()} ${response.request().method()} ${response.url()}`,
    );
  });

  return evidence;
}

async function loadPlans(page: Page): Promise<AttackPlan[]> {
  await installConfiguredProviderState(page);
  const plansResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  return (await (await plansResponse).json()) as AttackPlan[];
}

async function waitForGuided(page: Page, plan: AttackPlan): Promise<void> {
  await expect(page.getByTestId("workspace-guided")).toBeVisible();
  await expect(page.getByTestId("guided-plan")).toContainText(plan.name);
  await expect(page.getByTestId("guided-attack-chain")).toBeVisible();
  await expect(page.getByTestId("guided-finding-summary")).toBeVisible();
  await expect(page.getByTestId("guided-replay-comparison")).toBeVisible();
  await expect(page.getByTestId("remediation-advisory")).toContainText("仅供参考");
  await expect(page.getByTestId("remediation-advisory")).toContainText("不会修改企业系统");
  await expect(page.getByTestId("remediation-advisory")).toContainText("根因分析与变更审批");
}

async function runProviderReadiness(page: Page): Promise<void> {
  const readinessResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-readiness" &&
      response.ok(),
  );
  await page.getByTestId("run-provider-readiness").click();
  const result = (await (await readinessResponse).json()) as {
    status: string;
    targetProvider: { role: string; status: string; probes: unknown[] };
    attackProvider: { role: string; status: string; probes: unknown[] };
    planCompatibility: unknown[];
  };
  expect(result.status).toBe("ready");
  expect(result.targetProvider.role).toBe("target");
  expect(result.targetProvider.status).toBe("ready");
  expect(result.targetProvider.probes).toHaveLength(2);
  expect(result.attackProvider.role).toBe("attack");
  expect(result.attackProvider.status).toBe("ready");
  expect(result.attackProvider.probes).toHaveLength(2);
  expect(result.planCompatibility).toHaveLength(4);
  await expect(
    page
      .getByRole("region", { name: "模型运行就绪检查" })
      .getByTestId("provider-readiness-result"),
  ).toContainText("READY");
  const fullReadiness = page.getByRole("region", { name: "模型运行就绪检查" });
  await expect(fullReadiness.locator(".candidate-readiness-card")).toHaveCount(0);
  await expect(fullReadiness.locator(".candidate-probe-grid")).toHaveCount(0);
  await expect(fullReadiness.locator(".readiness-empty")).toHaveCount(0);
  await expect(fullReadiness.locator(".provider-grid")).toBeVisible();
}

async function openAdvancedSetup(page: Page): Promise<void> {
  await page.getByRole("button", { name: "设置与计划", exact: true }).click();
  await expect(page.getByTestId("workspace-setup")).toBeVisible();
}

async function waitForSetup(page: Page): Promise<void> {
  await expect(page.getByTestId("workspace-setup")).toBeVisible();
  await expect(page.getByTestId("runtime-summary")).toContainText("embedding");
  await expect(page.getByTestId("scan-plan-select")).toBeVisible();
  await expect(page.getByTestId("start-scan")).toBeEnabled();
}

async function openLiveWorkspace(page: Page): Promise<void> {
  await page.getByRole("button", { name: "扫描记录", exact: true }).click();
  await expect(page.getByTestId("workspace-live")).toBeVisible();
}

async function restoreScanFromHistory(page: Page, scanId: string): Promise<void> {
  await openLiveWorkspace(page);
  await expect(page.getByTestId("scan-history")).toBeVisible();
  const historyItem = page.locator(".history-item").filter({ hasText: scanId }).first();
  await expect(historyItem).toBeVisible();
  const detailResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === `/api/scans/${scanId}` &&
      response.ok(),
  );
  await historyItem.getByTestId("restore-scan").click();
  await detailResponse;
  await expect(page.getByText(`已恢复 ${scanId}`)).toBeVisible();
}

async function openFindings(page: Page): Promise<void> {
  await page.getByTestId("open-findings").click();
  await expect(page.getByTestId("workspace-findings")).toBeVisible();
  await expect(page.getByTestId("history-detail")).toBeVisible();
}

async function expectUsable(locator: Locator): Promise<void> {
  await locator.scrollIntoViewIfNeeded();
  await expect(locator).toBeVisible();
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box?.width ?? 0).toBeGreaterThan(0);
  expect(box?.height ?? 0).toBeGreaterThan(0);
}

async function expectNoPageOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(widths.documentWidth).toBeLessThanOrEqual(widths.innerWidth);
  expect(widths.bodyWidth).toBeLessThanOrEqual(widths.innerWidth);
}

async function expectChineseReadableText(locator: Locator): Promise<void> {
  const count = await locator.count();
  expect(count).toBeGreaterThan(0);
  const texts = await locator.allTextContents();
  for (const text of texts) {
    expect(text.trim()).not.toBe("");
    expect(text).toMatch(/[\u3400-\u9fff]/u);
  }
}

async function expectMinimumFontSize(locator: Locator, minimumPx: number): Promise<void> {
  const count = await locator.count();
  expect(count).toBeGreaterThan(0);
  const sizes = await locator.evaluateAll((elements) =>
    elements.map((element) => Number.parseFloat(window.getComputedStyle(element).fontSize)),
  );
  for (const size of sizes) {
    expect(size).toBeGreaterThanOrEqual(minimumPx);
  }
}

async function assertHumanReadableGuidedEvidence(
  page: Page,
  finding: Finding,
  traceEvents: TraceEvent[],
): Promise<void> {
  const chain = page.getByTestId("guided-attack-chain");
  const nodes = chain.locator("li.chain-node");
  await expect(nodes).toHaveCount(6);

  // The first reading layer must describe the business flow in Chinese. Stable
  // internal identifiers belong to the evidence details, not the node titles.
  const story = page.getByTestId("guided-chain-story");
  await expect(story).toBeVisible();
  await expectChineseReadableText(story);
  const storyText = await story.innerText();
  expect(storyText.length).toBeGreaterThan(20);
  expect(storyText).not.toMatch(/external_document|mock_mail_send|external_message|finding_\d+/);

  await expect(nodes.locator(".chain-node-label")).toHaveText([
    "操作人",
    "输入来源",
    "读取资料",
    "权限判断",
    "工具动作",
    "数据去向",
  ]);
  const nodeTitles = nodes.locator(".chain-node-title");
  await expect(nodeTitles).toHaveCount(6);
  await expectChineseReadableText(nodeTitles);
  await expectMinimumFontSize(nodeTitles, 11);
  const nodeTitleText = await nodeTitles.allTextContents();
  for (const text of nodeTitleText) {
    expect(text).not.toMatch(/external_document|mock_mail_send|external_message|finding_\d+/);
  }
  const nodeCaptions = nodes.locator(".chain-node-caption");
  await expectChineseReadableText(nodeCaptions);
  const nodeDescriptions = nodes.locator(".chain-node-description");
  await expectChineseReadableText(nodeDescriptions);

  // Node evidence opens in a full-width panel below the six-node overview, so
  // neither the selected node nor its siblings should stretch vertically.
  const authorizationNode = nodes.nth(3);
  const authorizationToggle = authorizationNode.locator("button.chain-evidence-toggle");
  await expect(authorizationToggle).toHaveCount(1);
  const heightsBefore = await nodes.evaluateAll((elements) =>
    elements.map((element) => element.getBoundingClientRect().height),
  );
  if ((page.viewportSize()?.width ?? 0) > 900) {
    expect(Math.max(...heightsBefore) - Math.min(...heightsBefore)).toBeLessThanOrEqual(1);
  }
  await authorizationToggle.click();
  await expect(authorizationToggle).toHaveAttribute("aria-expanded", "true");
  const evidencePanel = page.getByTestId("chain-evidence-panel");
  await expect(evidencePanel).toBeVisible();
  await expect(evidencePanel).toContainText("权限判断证据");
  await expect(evidencePanel.locator(".chain-facts, .chain-evidence-events").first()).toBeVisible();
  const heightsAfter = await nodes.evaluateAll((elements) =>
    elements.map((element) => element.getBoundingClientRect().height),
  );
  for (let index = 0; index < heightsBefore.length; index += 1) {
    expect(Math.abs(heightsAfter[index] - heightsBefore[index])).toBeLessThanOrEqual(1);
  }

  const chainBounds = await chain.boundingBox();
  const panelBounds = await evidencePanel.boundingBox();
  expect(chainBounds).not.toBeNull();
  expect(panelBounds).not.toBeNull();
  if (chainBounds && panelBounds) {
    expect(panelBounds.width).toBeGreaterThan(chainBounds.width * 0.75);
  }

  // Raw node JSON remains a second-level affordance inside the panel.
  const nodeRawDetails = evidencePanel.locator("details.chain-event-json");
  expect(await nodeRawDetails.count()).toBeGreaterThan(0);
  for (let index = 0; index < (await nodeRawDetails.count()); index += 1) {
    const rawDetails = nodeRawDetails.nth(index);
    await expect(rawDetails).not.toHaveAttribute("open");
    await expect(rawDetails.locator("pre")).toBeHidden();
  }

  const findingCard = page
    .getByTestId("guided-finding-summary")
    .locator(".finding-card")
    .filter({ hasText: finding.id })
    .first();
  await expect(findingCard).toBeVisible();
  const findingIdBlock = findingCard.locator('[data-testid="finding-id-block"]');
  await expect(findingIdBlock).toHaveCount(1);
  await expect(findingIdBlock).toContainText("Finding 编号");
  await expect(findingIdBlock.locator("code")).toHaveText(finding.id);
  const findingIdPlacement = await findingIdBlock.evaluate((element) => ({
    display: window.getComputedStyle(element).display,
    backgroundColor: window.getComputedStyle(element).backgroundColor,
    insideFindingImage: Boolean(element.closest(".finding-heading.is-critical")),
  }));
  expect(findingIdPlacement.display).not.toBe("inline");
  expect(findingIdPlacement.backgroundColor).not.toBe("rgba(0, 0, 0, 0)");
  expect(findingIdPlacement.insideFindingImage).toBe(false);
  await expectMinimumFontSize(findingIdBlock.locator("code"), 12);

  const fullTrace = page.locator("details.guided-trace-details");
  await expect(fullTrace).toBeVisible();
  await expect(fullTrace.locator(":scope > summary")).toContainText("完整 Trace");
  await fullTrace.locator(":scope > summary").click();
  await expect(fullTrace).toHaveAttribute("open", "");
  const traceCards = fullTrace.locator(".trace-event");
  await expect(traceCards).toHaveCount(traceEvents.length);
  const traceTitles = traceCards.locator(":scope > .trace-event-title");
  await expect(traceTitles).toHaveCount(traceEvents.length);
  await expectChineseReadableText(traceTitles);
  await expectMinimumFontSize(traceTitles, 14);

  const traceHeadings = traceCards.locator(".trace-event-heading");
  await expectMinimumFontSize(traceHeadings, 11);
  const traceFactRows = fullTrace.locator(".trace-facts > div");
  expect(await traceFactRows.count()).toBeGreaterThan(0);
  await expectMinimumFontSize(traceFactRows.locator(":scope > span"), 10);
  await expectMinimumFontSize(traceFactRows.locator(":scope > code"), 11);
  for (let index = 0; index < (await traceFactRows.count()); index += 1) {
    const row = traceFactRows.nth(index);
    await expect(row.locator(":scope > span")).not.toHaveText("");
    await expect(row.locator(":scope > code")).not.toHaveText("");
  }

  const traceRawDetails = fullTrace.locator("details.trace-event-json");
  await expect(traceRawDetails).toHaveCount(traceEvents.length);
  for (let index = 0; index < (await traceRawDetails.count()); index += 1) {
    const rawDetails = traceRawDetails.nth(index);
    await expect(rawDetails).not.toHaveAttribute("open");
    const rawParagraphs = rawDetails.locator("p");
    await expect(rawParagraphs).toHaveCount(2);
    await expect(rawParagraphs.first()).toBeHidden();
    await expect(rawParagraphs.last()).toBeHidden();
    await expect(rawDetails.locator("pre")).toBeHidden();
  }
}

function latestAttempt(scan: Scan): ScanAttempt {
  const attempt = scan.attempts[scan.attempts.length - 1];
  expect(attempt).toBeDefined();
  return attempt;
}

function sourceSinkPlan(plans: AttackPlan[]): AttackPlan {
  const plan = plans.find((candidate) => candidate.basisType === "source_sink");
  expect(plan).toBeDefined();
  if (!plan) {
    throw new Error("source_sink Attack Plan is not available");
  }
  return plan;
}

async function runGuidedScan(
  page: Page,
  plan: AttackPlan,
): Promise<{ scan: Scan; finding: Finding; traceEvents: TraceEvent[] }> {
  const scanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("guided-start-scan").click();
  const scan = (await (await scanResponse).json()) as Scan;
  expect(scan.planId).toBe(plan.id);
  expect(scan.status).toBe("completed");
  expect(scan.stopReason).toBe("finding_detected");

  const attempt = latestAttempt(scan);
  expect(attempt.evaluation.status).toBe("failed");
  const finding = attempt.evaluation.findings[0];
  expect(finding).toBeDefined();
  if (!finding) {
    throw new Error("source_sink Scan returned no Finding");
  }
  expect(finding.category).toBe("external_sink_policy_violation");
  expect(finding.severity).toBe("critical");
  expect(finding.ruleId).toBe("sink_external_message_confidential");
  return {
    scan,
    finding,
    traceEvents: attempt.queryResult.traceEvents,
  };
}

async function assertGuidedFinding(
  page: Page,
  plan: AttackPlan,
  finding: Finding,
  traceEvents: TraceEvent[],
): Promise<void> {
  const chain = page.getByTestId("guided-attack-chain");
  const summary = page.getByTestId("guided-finding-summary");
  await expect(chain).toBeVisible();
  await expect(summary).toBeVisible();
  await expect(summary).toContainText(finding.ruleId ?? "default deny");
  await expect(summary).toContainText("Critical");
  await expect(summary).toContainText(finding.id);
  await expect(summary.getByTestId("critical-finding-visual")).toBeVisible();

  expect(traceEvents.some((event) => event.type === "source")).toBe(true);
  expect(traceEvents.some((event) => event.type === "retrieval")).toBe(true);
  expect(traceEvents.some((event) => event.type === "authorization")).toBe(true);
  expect(traceEvents.some((event) => event.type === "tool_call")).toBe(true);
  expect(traceEvents.some((event) => event.type === "sink")).toBe(true);
  await expect(chain).not.toContainText(plan.actorId);
  await expect(chain).not.toContainText("external_document");
  await expect(chain).not.toContainText("mock_mail_send");

  const nodes = chain.locator("li.chain-node");
  const evidencePanel = page.getByTestId("chain-evidence-panel");
  const expectNodeEvidence = async (index: number, expected: string): Promise<void> => {
    await nodes.nth(index).locator("button.chain-evidence-toggle").click();
    await expect(evidencePanel).toBeVisible();
    await expect(evidencePanel).toContainText(expected);
  };
  await expectNodeEvidence(0, plan.actorId);
  await expectNodeEvidence(1, "external_document");
  await expectNodeEvidence(2, "doc_finance_budget_001");
  await expectNodeEvidence(4, "mock_mail_send");
  await expectNodeEvidence(5, "external_message");
}

async function runGuidedReplay(page: Page, plan: AttackPlan): Promise<Replay> {
  const replayResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === `/api/attack-plans/${plan.id}/replay` &&
      response.ok(),
  );
  const replayButton = page.getByTestId("guided-run-replay");
  await expect(replayButton).toBeEnabled();
  await replayButton.click();
  const replay = (await (await replayResponse).json()) as Replay;
  expect(replay.status).toBe("passed");
  expect(replay.plan.id).toBe(plan.id);
  expect(replay.before.evaluation.status).toBe("failed");
  expect(replay.after.evaluation.status).toBe("passed");
  expect(replay.after.executionStatus).toBe("blocked");
  return replay;
}

test("guided source→sink Scan and Replay use real evidence and persist without refresh writes", async ({
  page,
}) => {
  const evidence = observeBrowserHealth(page);
  const plans = await loadPlans(page);
  const plan = sourceSinkPlan(plans);

  expect(evidence.readinessPosts).toBe(0);
  await waitForGuided(page, plan);
  const guided = page.getByTestId("workspace-guided");
  await expect(page.getByRole("heading", { name: "AI 是否会把企业机密发送到外部？" })).toBeVisible();
  await expect(guided).toContainText("内容来源");
  await expect(guided).toContainText("数据去向");
  await expect(guided.getByTestId("guided-start-scan")).toBeEnabled();
  await expect(guided.getByTestId("guided-run-replay")).toBeDisabled();
  const chainPreview = guided.getByTestId("guided-chain-preview");
  await expect(chainPreview).toBeVisible();
  await expect(chainPreview.getByRole("listitem")).toHaveCount(6);
  await expect(chainPreview).toContainText("发起用户");
  await expect(chainPreview).toContainText("输入资料");
  await expect(chainPreview).toContainText("知识资源");
  await expect(chainPreview).toContainText("权限判断");
  await expect(chainPreview).toContainText("工具动作");
  await expect(chainPreview).toContainText("数据去向");
  await expect(chainPreview).not.toContainText(plan.actorId);
  await expect(chainPreview).not.toContainText(plan.basisRuleId);
  const chainBackdrop = guided.getByTestId("guided-chain-flow-backdrop");
  await expect(chainBackdrop).toHaveCount(1);
  await expect(chainBackdrop).toHaveAttribute("alt", "");

  const { scan, finding, traceEvents } = await runGuidedScan(page, plan);
  // Provider Readiness is part of the post-Scan result stage; it is not
  // mounted before the first explicit business check completes.
  await runProviderReadiness(page);
  expect(evidence.readinessPosts).toBe(1);
  await assertGuidedFinding(page, plan, finding, traceEvents);
  await assertHumanReadableGuidedEvidence(page, finding, traceEvents);
  // The decorative data-flow layer remains behind the real result nodes; the
  // semantic Scan and Trace evidence is still rendered by the foreground UI.
  await expect(chainBackdrop).toHaveCount(1);
  await expect(chainBackdrop).toBeVisible();
  const replay = await runGuidedReplay(page, plan);
  const comparison = page.getByTestId("guided-replay-comparison");
  await expect(comparison).toBeVisible();
  const replayVisual = comparison.getByTestId("guided-replay-state-visual");
  await expect(replayVisual).toHaveClass(/is-passed/);
  await expect(comparison.getByTestId("guided-replay-before-visual")).toHaveAttribute("alt", "");
  await expect(comparison.getByTestId("guided-replay-after-visual")).toHaveAttribute("alt", "");
  await expect(comparison.getByTestId("guided-replay-before")).toContainText(/failed/i);
  await expect(comparison.getByTestId("guided-replay-after")).toContainText(/passed/i);
  await expect(comparison.getByTestId("guided-replay-after")).toContainText(/blocked/i);
  await expect(comparison).toContainText(plan.actorId);
  await expect(comparison).toContainText(plan.message);
  expect(replay.before.traceEvents.some((event) => event.type === "sink")).toBe(true);
  expect(replay.after.traceEvents.some((event) => event.type === "authorization")).toBe(true);
  expect(
    replay.after.traceEvents.some(
      (event) =>
        event.type === "sink" && event.details.sinkType === "external_message",
    ),
  ).toBe(false);

  const countsBeforeReload = {
    scanPosts: evidence.scanPosts,
    replayPosts: evidence.replayPosts,
    readinessPosts: evidence.readinessPosts,
  };
  await page.reload();
  await chooseOnboardingPath(page, "demo");
  await waitForGuided(page, plan);
  expect(evidence.scanPosts).toBe(countsBeforeReload.scanPosts);
  expect(evidence.replayPosts).toBe(countsBeforeReload.replayPosts);
  expect(evidence.readinessPosts).toBe(countsBeforeReload.readinessPosts);

  // Keep the F-020 persistence path covered using the same real source_sink Scan.
  await openAdvancedSetup(page);
  await waitForSetup(page);
  await restoreScanFromHistory(page, scan.id);
  await openFindings(page);
  const historyDetail = page.getByTestId("history-detail");
  await expect(historyDetail).toContainText("CONTRACT SNAPSHOT");
  await expect(historyDetail).toContainText("PLAN SNAPSHOT");
  await expect(historyDetail).toContainText("PROFILE SNAPSHOT");
  await expect(historyDetail).toContainText("RUNTIME SNAPSHOT");
  await expect(historyDetail).toContainText("source_sink");
  await expect(historyDetail.getByTestId("scan-finding").first()).toBeVisible();

  const persistedReplayResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === `/api/scans/${scan.id}/replays` &&
      response.ok(),
  );
  await page.getByTestId("start-persisted-replay").click();
  const persistedReplayPayload = (await (await persistedReplayResponse).json()) as {
    id: string;
    replay: Replay;
  };
  expect(persistedReplayPayload.id).toEqual(expect.any(String));
  expect(persistedReplayPayload.replay.id).toEqual(expect.any(String));
  expect(persistedReplayPayload.replay.before.evaluation.status).toBe("failed");
  expect(persistedReplayPayload.replay.after.evaluation.status).toBe("passed");
  const persistedReplay = page.getByTestId("persisted-replay").last();
  await expect(persistedReplay).toBeVisible();
  await expect(persistedReplay.getByTestId("replay-before")).toContainText(/failed/i);
  await expect(persistedReplay.getByTestId("replay-after")).toContainText(/passed/i);

  const countsBeforeSecondReload = {
    scanPosts: evidence.scanPosts,
    replayPosts: evidence.replayPosts,
    readinessPosts: evidence.readinessPosts,
  };
  await page.reload();
  await chooseOnboardingPath(page, "demo");
  await waitForGuided(page, plan);
  expect(evidence.scanPosts).toBe(countsBeforeSecondReload.scanPosts);
  expect(evidence.replayPosts).toBe(countsBeforeSecondReload.replayPosts);
  expect(evidence.readinessPosts).toBe(countsBeforeSecondReload.readinessPosts);
  await openAdvancedSetup(page);
  await waitForSetup(page);
  await restoreScanFromHistory(page, scan.id);
  await openFindings(page);
  const restoredReplay = page.getByTestId("persisted-replay").last();
  await expect(restoredReplay).toBeVisible();
  await expect(restoredReplay.getByTestId("replay-before")).toContainText(/failed/i);
  await expect(restoredReplay.getByTestId("replay-after")).toContainText(/passed/i);

  expect(evidence.scanPosts).toBe(1);
  expect(evidence.replayPosts).toBe(2);
  expect(evidence.readinessPosts).toBe(1);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("390×844 guided core path keeps Scan, attack chain, Finding, and Replay usable without page overflow", async ({
  page,
}) => {
  const evidence = observeBrowserHealth(page);
  await page.setViewportSize({ width: 390, height: 844 });
  const plans = await loadPlans(page);
  const plan = sourceSinkPlan(plans);
  await waitForGuided(page, plan);

  await expectUsable(page.getByTestId("guided-start-scan"));
  await expectNoPageOverflow(page);
  const { finding, traceEvents } = await runGuidedScan(page, plan);
  await expectUsable(page.getByTestId("guided-attack-chain"));
  await expectUsable(page.getByTestId("guided-finding-summary"));
  await assertGuidedFinding(page, plan, finding, traceEvents);
  await assertHumanReadableGuidedEvidence(page, finding, traceEvents);
  await expectNoPageOverflow(page);

  const replay = await runGuidedReplay(page, plan);
  await expectUsable(page.getByTestId("guided-replay-comparison"));
  const before = page.getByTestId("guided-replay-before");
  const after = page.getByTestId("guided-replay-after");
  await expectUsable(before);
  await expectUsable(after);
  await expect(before).toContainText(/failed/i);
  await expect(after).toContainText(/passed/i);
  await expect(after).toContainText(/blocked/i);
  expect(replay.before.evaluation.status).toBe("failed");
  expect(replay.after.evaluation.status).toBe("passed");
  expect(replay.after.executionStatus).toBe("blocked");
  await expectNoPageOverflow(page);

  expect(evidence.scanPosts).toBe(1);
  expect(evidence.replayPosts).toBe(1);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("Provider 502 keeps a readable error and restores both Scan buttons", async ({ page }) => {
  const evidence = observeBrowserHealth(page);
  const plans = await loadPlans(page);
  const toolPlan = plans.find((plan) => plan.basisType === "tool_owner_scope");
  expect(toolPlan).toBeDefined();
  if (!toolPlan) {
    return;
  }

  await openAdvancedSetup(page);
  await waitForSetup(page);
  await page.getByTestId("scan-plan-select").click();
  const planOption = page
    .locator(".el-select-dropdown__item")
    .filter({ hasText: toolPlan.id })
    .first();
  await expect(planOption).toBeVisible();
  await planOption.click();

  const failedScanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.status() === 502,
  );
  await page.getByTestId("start-scan").click();
  await failedScanResponse;

  await expect(page.getByTestId("workspace-setup")).toBeVisible();
  const setupProblem = page.getByRole("alert").filter({
    hasText: /本次检查|服务|模型/u,
  });
  await expect(setupProblem).toBeVisible();
  await expect(setupProblem).toContainText(/检查|连接|服务|结果/);
  await expect(setupProblem).toContainText(/重新|再次|确认/);
  await expect(setupProblem).not.toContainText("synthetic E2E target provider unavailable");
  await expect(page.getByTestId("start-scan")).toBeEnabled();
  await page.getByRole("button", { name: "核心验收", exact: true }).click();
  await expect(page.getByTestId("workspace-guided")).toBeVisible();
  await expect(page.getByTestId("guided-start-scan")).toBeEnabled();
  const guidedProblem = page.getByTestId("guided-problem");
  await expect(guidedProblem).toBeVisible();
  await expect(guidedProblem).toContainText(/检查|连接|服务|结果/);
  await expect(guidedProblem).toContainText(/重新|再次|确认/);
  await expect(guidedProblem).not.toContainText("synthetic E2E target provider unavailable");

  expect(evidence.scanPosts).toBe(1);
  expect(evidence.replayPosts).toBe(0);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.apiNon2xx).toHaveLength(1);
  expect(evidence.apiNon2xx[0]).toContain("502 POST");
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("rapid guided Scan double-click sends one request and restores the control", async ({
  page,
}) => {
  const evidence = observeBrowserHealth(page);
  const plans = await loadPlans(page);
  const plan = sourceSinkPlan(plans);
  await waitForGuided(page, plan);

  let releaseScan!: () => void;
  const scanGate = new Promise<void>((resolve) => {
    releaseScan = resolve;
  });
  await page.route("**/api/scans", async (route) => {
    await scanGate;
    await route.continue();
  });

  const scanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  const startButton = page.getByTestId("guided-start-scan");
  await expect(page.getByTestId("running-evidence-pulse")).toHaveCount(0);
  await startButton.dblclick();
  await expect(startButton).toBeDisabled();
  await expect(page.getByTestId("running-evidence-pulse")).toBeVisible();
  expect(evidence.scanPosts).toBe(1);

  releaseScan();
  await scanResponse;
  await expect(startButton).toBeEnabled();
  await expect(page.getByTestId("running-evidence-pulse")).toHaveCount(0);
  await page.unroute("**/api/scans");

  expect(evidence.scanPosts).toBe(1);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});
