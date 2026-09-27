import { expect, test, type Locator, type Page } from "@playwright/test";
import { chooseOnboardingPath, installConfiguredProviderState } from "./support/first_use";

type AttackPlan = {
  id: string;
  name: string;
  basisType: string;
};

type ScanAttempt = {
  status: string;
  evaluation: { findings: Array<{ id: string; severity: string }> };
};

type Scan = {
  planId: string;
  status: string;
  stopReason: string;
  attempts: ScanAttempt[];
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

async function loadPlans(page: Page, filter?: (plans: AttackPlan[]) => AttackPlan[]): Promise<AttackPlan[]> {
  await installConfiguredProviderState(page);
  if (filter) {
    await page.route("**/api/attack-plans", async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }

      const response = await route.fetch();
      const plans = (await response.json()) as AttackPlan[];
      await route.fulfill({ response, json: filter(plans) });
    });
  }

  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  return (await (await responsePromise).json()) as AttackPlan[];
}

async function openSetup(page: Page): Promise<void> {
  await page.getByRole("button", { name: "设置与计划", exact: true }).click();
  await expect(page.getByTestId("workspace-setup")).toBeVisible();
}

async function openLive(page: Page): Promise<void> {
  await page.getByRole("button", { name: "扫描记录", exact: true }).click();
  await expect(page.getByTestId("workspace-live")).toBeVisible();
}

async function sourceSinkPlan(plans: AttackPlan[]): Promise<AttackPlan> {
  const plan = plans.find((candidate) => candidate.basisType === "source_sink");
  expect(plan).toBeDefined();
  if (!plan) {
    throw new Error("source_sink Attack Plan is required for F-061 visual evidence");
  }
  return plan;
}

async function runGuidedScan(page: Page, plan: AttackPlan): Promise<Scan> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("guided-start-scan").click();
  const scan = (await (await responsePromise).json()) as Scan;
  expect(scan).toMatchObject({ planId: plan.id, status: "completed" });
  return scan;
}

async function runGuidedReplay(page: Page, plan: AttackPlan): Promise<void> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === `/api/attack-plans/${plan.id}/replay` &&
      response.ok(),
  );
  await expect(page.getByTestId("guided-run-replay")).toBeEnabled();
  await page.getByTestId("guided-run-replay").click();
  const replay = (await (await responsePromise).json()) as { status: string; plan: AttackPlan };
  expect(replay).toMatchObject({ status: "passed", plan: { id: plan.id } });
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

async function bodySmallSize(page: Page): Promise<number> {
  return page.evaluate(() =>
    Number.parseFloat(
      window.getComputedStyle(document.documentElement).getPropertyValue("--type-body-small-size"),
    ),
  );
}

async function expectNoPageOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport);
}

function colorChannels(value: string): [number, number, number] | null {
  const match = value.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/u);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

function isRiskColor(value: string): boolean {
  const channels = colorChannels(value);
  return channels !== null && channels[0] > channels[1] + 20 && channels[0] > channels[2] + 20;
}

function isNonTransparent(value: string): boolean {
  return value !== "transparent" && value !== "rgba(0, 0, 0, 0)";
}

function isLightSurface(value: string): boolean {
  const channels = colorChannels(value);
  if (value === "transparent" || value === "rgba(0, 0, 0, 0)") {
    return true;
  }
  return channels === null || channels[0] + channels[1] + channels[2] > 300;
}

test("F-061 keeps the real attack-chain background and distinguishes Finding strategy evidence", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const plans = await loadPlans(page);
  const plan = await sourceSinkPlan(plans);

  const chain = page.getByTestId("guided-attack-chain");
  const backdrop = page.getByTestId("guided-chain-flow-backdrop");
  await expect(chain).toBeVisible();
  await expect(backdrop).toHaveCount(1);
  await expect(backdrop).toBeVisible();
  await expect(backdrop).toHaveAttribute("alt", "");

  const scan = await runGuidedScan(page, plan);
  const latestAttempt = scan.attempts.at(-1);
  expect(latestAttempt).toBeDefined();
  expect(latestAttempt?.status).toBe("finding");
  expect(latestAttempt?.evaluation.findings.length).toBeGreaterThan(0);

  // The same decorative flow remains in the result state; only the semantic
  // node/evidence layer changes with the real Scan response.
  await expect(backdrop).toHaveCount(1);
  await expect(backdrop).toBeVisible();
  await expect(chain.locator("li.chain-node")).toHaveCount(6);

  await openLive(page);
  const live = page.getByTestId("workspace-live");
  const transitions = live.locator(".scan-transitions li");
  await expect(transitions).not.toHaveCount(0);
  await expectMinimumFontSize(transitions, await bodySmallSize(page));
  await expectMinimumFontSize(transitions.locator(":scope > span:last-child"), await bodySmallSize(page));
  const transitionStyles = await transitions.evaluateAll((elements) =>
    elements.map((element) => ({
      backgroundColor: window.getComputedStyle(element).backgroundColor,
      color: window.getComputedStyle(element).color,
    })),
  );
  for (const style of transitionStyles) {
    expect(style.backgroundColor).not.toBe("rgba(6, 14, 26, 0.42)");
    expect(style.backgroundColor).not.toBe("rgb(6, 14, 26)");
    expect(isLightSurface(style.backgroundColor)).toBe(true);
  }

  const findingAttempt = live.locator(".scan-attempt").filter({ hasText: "FINDING · 发现" });
  await expect(findingAttempt).toHaveCount(1);
  const findingReason = findingAttempt.locator(".scan-mutation-reason");
  await expect(findingReason).toHaveCount(1);
  await expect(findingReason).toContainText("本轮攻击策略");
  await expectMinimumFontSize(findingReason, 14);
  const findingReasonLabel = findingReason.locator(".scan-strategy-label");
  await expect(findingReasonLabel).toHaveCount(1);
  const findingReasonStyle = await findingReason.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return {
      backgroundColor: style.backgroundColor,
      borderLeftColor: style.borderLeftColor,
    };
  });
  const findingReasonLabelColor = await findingReasonLabel.evaluate((element) => window.getComputedStyle(element).color);
  expect(isRiskColor(findingReasonLabelColor)).toBe(true);
  expect(isNonTransparent(findingReasonStyle.backgroundColor)).toBe(true);
  expect(isRiskColor(findingReasonStyle.borderLeftColor)).toBe(true);

  // A real multi-round Scan may also contain a passed Attempt.  When the
  // controlled provider produces one, assert the complementary evidence tone
  // without treating the absence of a passed round as a fabricated result.
  const passedAttempts = live.locator(".scan-attempt").filter({ hasText: "PASSED · 通过" });
  if (await passedAttempts.count() > 0) {
    const passedReason = passedAttempts.first().locator(".scan-mutation-reason");
    await expect(passedReason).toHaveCount(1);
    await expect(passedReason).toContainText("本轮攻击策略");
    await expectMinimumFontSize(passedReason, 14);
    const passedReasonLabel = passedReason.locator(".scan-strategy-label");
    await expect(passedReasonLabel).toHaveCount(1);
    const passedReasonStyle = await passedReason.evaluate((element) => {
      const style = window.getComputedStyle(element);
      return {
        backgroundColor: style.backgroundColor,
        borderLeftColor: style.borderLeftColor,
      };
    });
    const passedReasonLabelColor = await passedReasonLabel.evaluate((element) => window.getComputedStyle(element).color);
    expect(isRiskColor(passedReasonLabelColor)).toBe(false);
    expect(isNonTransparent(passedReasonStyle.backgroundColor)).toBe(true);
    expect(isRiskColor(passedReasonStyle.borderLeftColor)).toBe(false);
  }
});

test("F-061 hides the misleading plan dropdown for one Plan and preserves switching for multiple Plans", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const singlePlan = await loadPlans(page, (plans) => {
    const sourceSink = plans.find((plan) => plan.basisType === "source_sink");
    return sourceSink ? [sourceSink] : [];
  });
  expect(singlePlan).toHaveLength(1);
  await openSetup(page);
  const staticPlan = page.getByTestId("scan-plan-static");
  await expect(staticPlan).toBeVisible();
  await expect(staticPlan).toContainText(singlePlan[0]?.name ?? "");
  await expect(page.getByTestId("scan-plan-select")).toHaveCount(0);

  await page.unroute("**/api/attack-plans");
  const multiPlanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.reload();
  await chooseOnboardingPath(page, "demo");
  const plans = (await (await multiPlanResponse).json()) as AttackPlan[];
  expect(plans.length).toBeGreaterThan(1);
  // The real multi-plan response is already loaded by the page.  Read it from
  // the visible list so the switching assertion remains UI-observable.
  await openSetup(page);
  const planSelect = page.getByTestId("scan-plan-select");
  await expect(planSelect).toBeVisible();
  await planSelect.click();
  const options = page.locator(".el-select-dropdown:visible .el-select-dropdown__item");
  await expect(options).toHaveCount(plans.length);
  const secondPlanName = plans[1]?.name;
  expect(secondPlanName).toBeTruthy();
  if (secondPlanName) {
    await options.nth(1).click();
    await expect(planSelect).toContainText(secondPlanName);
  }
});

test("F-061 aligns fixed Case actions at 1440px and keeps setup single-column at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await loadPlans(page);
  await openSetup(page);

  const cards = page.locator(".case-card");
  await expect(cards).toHaveCount(2);
  const buttons = cards.locator(".case-execute-button");
  await expect(buttons).toHaveCount(2);
  const bottoms = await buttons.evaluateAll((elements) =>
    elements.map((element) => element.getBoundingClientRect().bottom),
  );
  expect(Math.max(...bottoms) - Math.min(...bottoms)).toBeLessThanOrEqual(1);

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page);
  await expect(cards).toHaveCount(2);
  await expect(buttons).toHaveCount(2);
});

test("F-061 keeps judge-readable prose in Attack Chain Report and Acceptance evidence", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const plans = await loadPlans(page);
  const plan = await sourceSinkPlan(plans);
  await runGuidedScan(page, plan);
  await runGuidedReplay(page, plan);
  await page.getByRole("button", { name: "验收证据", exact: true }).click();
  const findings = page.getByTestId("workspace-findings");
  await expect(findings).toBeVisible();

  const reportResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/attack-chain-reports" &&
      response.ok(),
  );
  await findings.getByRole("button", { name: "生成攻击链报告", exact: true }).click();
  await reportResponse;
  const report = page.locator(".attack-chain-report-card");
  await expect(report).toBeVisible();
  await expectMinimumFontSize(
    report.locator(
      ".report-executive-summary p, .report-remediation > div:first-child > p, .report-plan-grid strong, .report-answer p, .report-blocked-answer p, .report-finding > strong, .report-finding > p, .report-no-findings, .report-trace-node > p",
    ),
    14,
  );

  const acceptance = page.getByTestId("acceptance-runs");
  await expect(acceptance).toBeVisible();
  await expect(acceptance.getByTestId("acceptance-run-start")).toBeEnabled();
  const acceptanceResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/acceptance-runs" &&
      response.ok(),
  );
  await acceptance.getByTestId("acceptance-run-start").click();
  await acceptanceResponse;
  await expect(acceptance.getByTestId("acceptance-run-summary")).toBeVisible();
  await expectMinimumFontSize(
    acceptance.locator(
      ".acceptance-lede, .acceptance-run-button, .acceptance-refresh, .acceptance-boundary > span, .history-item-facts, .summary-card .card-caption, .summary-card .category-copy, .summary-card .fact-list dd, .audit-row strong, .baseline-empty p, [data-testid=\"acceptance-remediation-advisory\"]",
    ),
    12,
  );
  await expectNoPageOverflow(page);
});
