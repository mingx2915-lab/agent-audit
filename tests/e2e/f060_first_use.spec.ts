import { expect, test, type Page } from "@playwright/test";

type FirstUseRequests = {
  discoveryPosts: number;
  inspectionPosts: number;
  candidateReadinessPosts: number;
  readinessPosts: number;
  importPreviewPosts: number;
  importCommitPosts: number;
  scanPosts: number;
  replayPosts: number;
  assistantPosts: number;
  providerSetupPuts: number;
  apiPosts: string[];
  requestFailures: string[];
  apiNon2xx: string[];
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function observeFirstUseRequests(page: Page): FirstUseRequests {
  const evidence: FirstUseRequests = {
    discoveryPosts: 0,
    inspectionPosts: 0,
    candidateReadinessPosts: 0,
    readinessPosts: 0,
    importPreviewPosts: 0,
    importCommitPosts: 0,
    scanPosts: 0,
    replayPosts: 0,
    assistantPosts: 0,
    providerSetupPuts: 0,
    apiPosts: [],
    requestFailures: [],
    apiNon2xx: [],
  };

  page.on("requestfailed", (request) => {
    evidence.requestFailures.push(
      `${request.method()} ${request.url()}: ${request.failure()?.errorText ?? "unknown"}`,
    );
  });
  page.on("request", (request) => {
    const path = apiPath(request.url());
    const method = request.method();
    if (method === "PUT" && path === "/api/provider-setup") {
      evidence.providerSetupPuts += 1;
    }
    if (method !== "POST") {
      return;
    }
    evidence.apiPosts.push(`${method} ${path}`);
    if (path === "/api/provider-discoveries/ollama") {
      evidence.discoveryPosts += 1;
    } else if (path === "/api/provider-inspections") {
      evidence.inspectionPosts += 1;
    } else if (path === "/api/provider-candidates/readiness") {
      evidence.candidateReadinessPosts += 1;
    } else if (path === "/api/provider-readiness") {
      evidence.readinessPosts += 1;
    } else if (path === "/api/document-imports/previews") {
      evidence.importPreviewPosts += 1;
    } else if (path === "/api/document-imports") {
      evidence.importCommitPosts += 1;
    } else if (path === "/api/scans") {
      evidence.scanPosts += 1;
    } else if (/^\/api\/(?:attack-plans\/[^/]+\/replay|scans\/[^/]+\/replays)$/.test(path)) {
      evidence.replayPosts += 1;
    } else if (path === "/api/assistant/queries") {
      evidence.assistantPosts += 1;
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

async function expectNoBusinessPosts(evidence: FirstUseRequests): Promise<void> {
  expect(evidence.apiPosts).toEqual([]);
  expect(evidence.discoveryPosts).toBe(0);
  expect(evidence.inspectionPosts).toBe(0);
  expect(evidence.candidateReadinessPosts).toBe(0);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.importPreviewPosts).toBe(0);
  expect(evidence.importCommitPosts).toBe(0);
  expect(evidence.scanPosts).toBe(0);
  expect(evidence.replayPosts).toBe(0);
  expect(evidence.assistantPosts).toBe(0);
  expect(evidence.providerSetupPuts).toBe(0);
}

async function installUnconfiguredProviderState(page: Page): Promise<void> {
  await page.route("**/api/provider-setup", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    // Keep the real runtime snapshot but make this browser context represent
    // a clean first launch.  This changes only status presentation; all
    // business operations still go through the production API server.
    const response = await route.fetch();
    const payload = (await response.json()) as Record<string, unknown>;
    payload.configured = false;
    payload.settings = null;
    payload.credentialConfigured = false;
    await route.fulfill({ response, json: payload });
  });
}

async function expectNoFullFirstRunBodies(page: Page): Promise<void> {
  await expect(page.getByTestId("provider-setup")).toHaveCount(0);
  await expect(page.getByTestId("document-import")).toHaveCount(0);
  await expect(page.locator(".guided-audit-flow")).toHaveCount(0);
  await expect(page.getByTestId("guided-replay-comparison")).toHaveCount(0);
}

async function expectNoPageOverflow(page: Page): Promise<void> {
  const metrics = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewport);
  expect(metrics.bodyWidth).toBeLessThanOrEqual(metrics.viewport);
}

async function expectReadableOnboardingCopy(page: Page): Promise<void> {
  const copy = page
    .getByTestId("enterprise-onboarding")
    .locator(
      ".enterprise-onboarding-header p:not(.section-kicker), .enterprise-onboarding-choice small",
    );
  await expect(copy).toHaveCount(3);
  const sizes = await copy.evaluateAll((elements) =>
    elements.map((element) => Number.parseFloat(window.getComputedStyle(element).fontSize)),
  );
  for (const size of sizes) {
    expect(size).toBeGreaterThanOrEqual(14);
  }
}

test("F-060 first launch gates full bodies until a path is chosen", async ({ page }) => {
  const evidence = observeFirstUseRequests(page);
  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  await expect(page.getByTestId("enterprise-onboarding")).toBeVisible();
  await expect(page.getByTestId("onboarding-choices")).toBeVisible();
  await expectNoFullFirstRunBodies(page);
  await expectNoBusinessPosts(evidence);

  // Picking a path is presentation state only.  It may reveal the next
  // local task, but it must not discover, probe, import, execute, or save.
  await page.getByTestId("onboarding-custom").click();
  await expect(page.getByTestId("onboarding-path")).toContainText("验收我的知识助手");
  await expect(page.getByTestId("onboarding-step-provider")).toBeVisible();
  await expect(page.getByTestId("document-import")).toHaveCount(0);
  await expect(page.locator(".guided-audit-flow")).toHaveCount(0);
  await expectNoBusinessPosts(evidence);

  await page.getByTestId("onboarding-reset").click();
  await page.getByTestId("onboarding-demo").click();
  await expect(page.getByTestId("onboarding-path")).toContainText("使用合成演示");
  await expectNoBusinessPosts(evidence);
  await expect(page.getByTestId("document-import")).toHaveCount(0);
  await expect(page.locator(".guided-audit-flow")).toHaveCount(0);
  await expect(page.getByTestId("onboarding-demo-connect")).toBeVisible();

  const demoText = await page.getByTestId("onboarding-path").innerText();
  expect(demoText).not.toContain("立即查看固定演示资料、真实 Trace、Finding 和 Replay");
  expect(demoText).toMatch(/待完成|先连接|需要连接/);
  expect(demoText).not.toMatch(/系统失败|执行失败/);
  await expectNoPageOverflow(page);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("F-060 path selection keeps the next connection action explicit", async ({ page }) => {
  const evidence = observeFirstUseRequests(page);
  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.getByTestId("onboarding-demo").click();
  await expect(page.getByTestId("onboarding-demo-connect")).toBeVisible();
  await expectNoBusinessPosts(evidence);

  // The connection body is opened only by the explicit CTA.  Opening it is
  // still local navigation and must not run discovery or Readiness.
  await page.getByTestId("onboarding-demo-connect").click();
  await expect(page.getByTestId("provider-setup")).toBeVisible();
  await expectNoBusinessPosts(evidence);
  await expect(page.getByTestId("provider-setup-discover")).toBeVisible();
  await expect(page.getByTestId("provider-setup-error")).toHaveCount(0);
  await expectNoPageOverflow(page);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("F-060 presents a recoverable Ollama error with folded technical detail", async ({ page }) => {
  const evidence = observeFirstUseRequests(page);
  await installUnconfiguredProviderState(page);
  const rawDiagnostic = "synthetic loopback diagnostic: connection refused";
  await page.route("**/api/provider-discoveries/ollama", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        endpoint: "http://127.0.0.1:11434",
        status: "unavailable",
        models: [],
        diagnostic: rawDiagnostic,
      }),
    });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByTestId("onboarding-custom").click();
  await page.getByTestId("onboarding-next-action").click();

  const setup = page.getByTestId("provider-setup");
  await expect(setup).toBeVisible();
  const discoveryResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-discoveries/ollama" &&
      response.ok(),
  );
  await setup.getByTestId("provider-setup-discover").click();
  await discoveryResponse;

  const error = setup.getByTestId("provider-setup-error");
  await expect(error).toBeVisible();
  const errorText = await error.innerText();
  expect(errorText).toMatch(/查找|连接|检查/);
  expect(errorText).toMatch(/不能|无法|暂时|影响/);
  expect(errorText).toMatch(/重新检测|重新检查|启动|处理/);
  expect(errorText).not.toMatch(/系统失败|OSError|URLError|TimeoutError/);

  const technicalDetails = error.locator("details");
  await expect(technicalDetails).toHaveCount(1);
  await technicalDetails.locator("summary").click();
  await expect(technicalDetails).toContainText(rawDiagnostic);
  await expect(setup.getByTestId("provider-setup-discover")).toBeEnabled();
  expect(evidence.discoveryPosts).toBe(1);
  expect(evidence.apiPosts).toEqual(["POST /api/provider-discoveries/ollama"]);
  expect(evidence.candidateReadinessPosts).toBe(0);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.scanPosts).toBe(0);
  expect(evidence.importPreviewPosts).toBe(0);
  expect(evidence.importCommitPosts).toBe(0);
  expect(evidence.providerSetupPuts).toBe(0);
  await expectNoPageOverflow(page);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("F-060 keeps onboarding copy readable at supported widths and display scales", async ({ page }) => {
  const evidence = observeFirstUseRequests(page);
  await installUnconfiguredProviderState(page);
  for (const width of [1440, 1920, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.goto("/");
    await expect(page.getByTestId("onboarding-choices")).toBeVisible();
    await expectReadableOnboardingCopy(page);
    await expectNoPageOverflow(page);

    await page.getByTestId("display-scale-standard").click();
    await expect(page.getByTestId("display-scale-standard")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expectReadableOnboardingCopy(page);
    await expectNoPageOverflow(page);

    await page.getByTestId("display-scale-large").click();
    await expect(page.getByTestId("display-scale-large")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expectReadableOnboardingCopy(page);
    await expectNoPageOverflow(page);
  }

  await expectNoBusinessPosts(evidence);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});
