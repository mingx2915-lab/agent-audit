import { expect, test, type Locator, type Page } from "@playwright/test";
import { chooseOnboardingPath, installConfiguredProviderState } from "./support/first_use";

type AcceptanceRequests = {
  acceptancePosts: number;
  acceptanceGets: number;
  readinessPosts: number;
  scanPosts: number;
  replayPosts: number;
  apiNon2xx: string[];
  pageErrors: string[];
  consoleErrors: string[];
  requestFailures: string[];
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function observeBrowserHealth(page: Page): AcceptanceRequests {
  const evidence: AcceptanceRequests = {
    acceptancePosts: 0,
    acceptanceGets: 0,
    readinessPosts: 0,
    scanPosts: 0,
    replayPosts: 0,
    apiNon2xx: [],
    pageErrors: [],
    consoleErrors: [],
    requestFailures: [],
  };

  page.on("pageerror", (error) => evidence.pageErrors.push(error.message));
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
    const path = apiPath(request.url());
    if (path === "/api/acceptance-runs") {
      if (request.method() === "POST") {
        evidence.acceptancePosts += 1;
      } else if (request.method() === "GET") {
        evidence.acceptanceGets += 1;
      }
    } else if (request.method() === "POST" && path === "/api/provider-readiness") {
      evidence.readinessPosts += 1;
    } else if (request.method() === "POST" && path === "/api/scans") {
      evidence.scanPosts += 1;
    } else if (
      request.method() === "POST" &&
      /^\/api\/(attack-plans\/[^/]+\/replay|scans\/[^/]+\/replays)$/.test(path)
    ) {
      evidence.replayPosts += 1;
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && apiPath(response.url()).startsWith("/api/")) {
      evidence.apiNon2xx.push(
        `${response.status()} ${response.request().method()} ${response.url()}`,
      );
    }
  });

  return evidence;
}

async function openAcceptance(page: Page): Promise<void> {
  await page.getByRole("button", { name: "验收证据", exact: true }).click();
  await expect(page.getByTestId("acceptance-runs")).toBeVisible();
  await expect(page.getByTestId("acceptance-run-history")).toBeVisible();
}

async function waitForRun(page: Page, beforePostCount: number): Promise<Record<string, any>> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/acceptance-runs" &&
      response.ok(),
  );
  await page.getByTestId("acceptance-run-start").click();
  const response = await responsePromise;
  const run = (await response.json()) as Record<string, any>;
  expect(run.id).toEqual(expect.any(String));
  expect(run.status).toBe("completed");
  expect(run.verdict).toBe(run.ciGate.status);
  expect(beforePostCount).toBeGreaterThanOrEqual(0);
  await expect(page.getByTestId("acceptance-run-summary")).toBeVisible();
  await expect(page.getByTestId("acceptance-run-comparison")).toBeVisible();
  return run;
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

async function downloadAndCheck(
  page: Page,
  locator: Locator,
  filename: string,
): Promise<void> {
  const downloadPromise = page.waitForEvent("download");
  await locator.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(filename);
}

test("Acceptance Run explicit click persists, selects, compares, downloads, and reloads read-only", async ({
  page,
}) => {
  const evidence = observeBrowserHealth(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installConfiguredProviderState(page);
  await page.goto("/");
  expect(evidence.acceptancePosts).toBe(0);

  await openAcceptance(page);
  expect(evidence.acceptancePosts).toBe(0);
  await expect(page.getByTestId("acceptance-run-start")).toBeEnabled();
  await expect(page.getByTestId("acceptance-run-scope")).toContainText(/24[\s\S]*5[\s\S]*2[\s\S]*1/);
  await expect(page.getByTestId("acceptance-run-scope")).toContainText(
    "Readiness → Evidence → Gate → Replay",
  );
  await expect(page.getByTestId("acceptance-run-empty")).toContainText("还没有验收记录");

  const emptyLayout = await page.evaluate(() => {
    const pageBackground = document.querySelector<HTMLElement>(".app-shell")!;
    const hero = document.querySelector<HTMLElement>(".acceptance-header")!;
    const title = document.querySelector<HTMLElement>(".acceptance-header-copy")!;
    const scope = document.querySelector<HTMLElement>("[data-testid='acceptance-run-scope']")!;
    const history = document.querySelector<HTMLElement>("[data-testid='acceptance-run-history']")!;
    const empty = document.querySelector<HTMLElement>("[data-testid='acceptance-run-empty']")!;
    const start = document.querySelector<HTMLElement>("[data-testid='acceptance-run-start']")!;
    const refresh = document.querySelector<HTMLElement>("[data-testid='acceptance-run-refresh']")!;
    return {
      pageBackground: getComputedStyle(pageBackground).backgroundImage,
      scopeIsRightOfTitle: scope.getBoundingClientRect().left > title.getBoundingClientRect().left,
      scopeBackground: getComputedStyle(hero, "::before").backgroundImage,
      historyHeight: history.getBoundingClientRect().height,
      historySurface: getComputedStyle(history).backgroundColor,
      emptyHeight: empty.getBoundingClientRect().height,
      heroHeight: hero.getBoundingClientRect().height,
      startBackground: getComputedStyle(start).backgroundColor,
      refreshBackground: getComputedStyle(refresh).backgroundColor,
    };
  });
  expect(emptyLayout.pageBackground).toContain("acceptance-page-evidence-network");
  expect(emptyLayout.scopeIsRightOfTitle).toBe(true);
  expect(emptyLayout.scopeBackground).toContain("acceptance-evidence-convergence");
  expect(emptyLayout.historyHeight).toBeLessThan(emptyLayout.heroHeight);
  expect(emptyLayout.historySurface).toBe("rgb(255, 255, 255)");
  expect(emptyLayout.emptyHeight).toBeLessThan(110);
  expect(emptyLayout.startBackground).not.toBe("rgba(0, 0, 0, 0)");
  expect(emptyLayout.refreshBackground).toBe("rgba(0, 0, 0, 0)");
  await expectNoPageOverflow(page);

  const first = await waitForRun(page, evidence.acceptancePosts);
  expect(evidence.acceptancePosts).toBe(1);
  expect(first.retrievalEvaluation.metrics.caseCount).toBe(6);
  expect(first.differentialAudits).toHaveLength(2);
  expect(first.ciGate.benchmark.cases).toHaveLength(24);
  expect(first.guidedScan.planId).toBe("plan_sink_confidential_external");
  expect(first.guidedReplay.plan.id).toBe(first.guidedScan.planId);
  await expect(page.getByTestId("acceptance-run-readiness")).toContainText(/READY/i);
  await expect(page.getByTestId("acceptance-run-gate")).toContainText(/24 CASE CI GATE/);
  await expect(page.getByTestId("acceptance-run-scan")).toContainText("plan_sink_confidential_external");
  await expect(page.getByTestId("acceptance-run-replay")).toContainText(/PASSED/i);
  await expect(page.getByTestId("acceptance-run-comparison")).toContainText("无 baseline");

  // A second explicit click creates a second append-only row.  Selecting the
  // first row then reads its complete detail and previous-run comparison.
  const second = await waitForRun(page, evidence.acceptancePosts);
  expect(evidence.acceptancePosts).toBe(2);
  const historyItems = page.getByTestId("acceptance-run-history-item");
  await expect(historyItems).toHaveCount(2);
  const postsBeforeSelection = evidence.acceptancePosts;
  const firstItem = historyItems.filter({ hasText: first.id }).first();
  const firstDetailResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === `/api/acceptance-runs/${first.id}` &&
      response.ok(),
  );
  const firstComparisonResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === `/api/acceptance-runs/${first.id}/comparison` &&
      response.ok(),
  );
  await firstItem.click();
  await firstDetailResponse;
  await firstComparisonResponse;
  expect(evidence.acceptancePosts).toBe(postsBeforeSelection);
  await expect(page.getByTestId("acceptance-run-comparison")).toContainText("无 baseline");
  await expect(page.getByTestId("acceptance-run-summary")).toContainText(first.id);

  const secondItem = historyItems.filter({ hasText: second.id }).first();
  const secondDetailResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === `/api/acceptance-runs/${second.id}` &&
      response.ok(),
  );
  const secondComparisonResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === `/api/acceptance-runs/${second.id}/comparison` &&
      response.ok(),
  );
  await secondItem.click();
  await secondDetailResponse;
  await secondComparisonResponse;
  expect(evidence.acceptancePosts).toBe(postsBeforeSelection);
  await expect(page.getByTestId("acceptance-comparison-previous")).toContainText(first.id);
  await expect(page.getByTestId("acceptance-run-summary")).toContainText(second.id);

  await downloadAndCheck(
    page,
    page.getByTestId("acceptance-run-json-download"),
    `acceptance-run-${second.id}.json`,
  );
  expect(evidence.acceptancePosts).toBe(postsBeforeSelection);
  await downloadAndCheck(
    page,
    page.getByTestId("acceptance-run-markdown-download"),
    `acceptance-run-${second.id}.md`,
  );
  const postsBeforeReload = evidence.acceptancePosts;
  await page.reload();
  expect(evidence.acceptancePosts).toBe(postsBeforeReload);
  await openAcceptance(page);
  await expect(page.getByTestId("acceptance-run-history-item")).toHaveCount(2);
  await expect(page.getByTestId("acceptance-run-summary")).toBeVisible();
  expect(evidence.acceptancePosts).toBe(2);

  // Existing Guided, Provider Readiness, and Contract Editor entry points
  // remain reachable after the advanced Acceptance workspace.
  await page.getByRole("button", { name: "核心验收", exact: true }).click();
  await expect(page.getByTestId("workspace-guided")).toBeVisible();
  await chooseOnboardingPath(page, "demo");
  const guidedScanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("onboarding-demo-run").click();
  await guidedScanResponse;
  await expect(page.getByTestId("guided-finding-summary")).toBeVisible();
  const readinessResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-readiness" &&
      response.ok(),
  );
  await page.getByTestId("run-provider-readiness").click();
  await readinessResponse;
  await expect(
    page
      .getByRole("region", { name: "模型运行就绪检查" })
      .getByTestId("provider-readiness-result"),
  ).toContainText(/READY/i);
  await page.getByRole("button", { name: "设置与计划", exact: true }).click();
  await expect(page.getByTestId("security-contract-editor")).toBeVisible();

  expect(second.id).not.toBe(first.id);
  expect(evidence.acceptanceGets).toBeGreaterThan(0);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("390×844 keeps Acceptance history, summary, comparison, and downloads usable", async ({
  page,
}) => {
  const evidence = observeBrowserHealth(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await openAcceptance(page);
  await expectNoPageOverflow(page);
  await expect(page.getByTestId("acceptance-run-start")).toBeEnabled();
  await expect(page.getByTestId("acceptance-run-scope")).toBeVisible();
  await expect(page.getByTestId("acceptance-run-scope")).toContainText("24");

  const run = await waitForRun(page, evidence.acceptancePosts);
  await expect(page.getByTestId("acceptance-run-summary")).toBeVisible();
  await expect(page.getByTestId("acceptance-run-history")).toBeVisible();
  await expect(page.getByTestId("acceptance-run-downloads")).toBeVisible();
  await expect(page.getByTestId("acceptance-run-comparison")).toBeVisible();
  await expectNoPageOverflow(page);

  const beforeRefreshPosts = evidence.acceptancePosts;
  await page.getByTestId("acceptance-run-refresh").click();
  await expect(page.getByTestId("acceptance-run-summary")).toBeVisible();
  expect(evidence.acceptancePosts).toBe(beforeRefreshPosts);
  expect(run.id).toEqual(expect.any(String));
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});
