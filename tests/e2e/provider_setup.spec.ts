import { expect, type Locator, type Page } from "@playwright/test";
import { test } from "./support/test";
import {
  chooseOnboardingPath,
  installUnconfiguredAppGate,
  installSyntheticCatalogView,
  openProviderSetupFromFirstUse,
} from "./support/first_use";

type ProviderSetupRequests = {
  setupGets: number;
  discoveryPosts: number;
  inspectionPosts: number;
  candidateReadinessPosts: number;
  setupPuts: number;
  apiNon2xx: string[];
  pageErrors: string[];
  consoleErrors: string[];
  requestFailures: string[];
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function observeProviderSetup(page: Page): ProviderSetupRequests {
  const evidence: ProviderSetupRequests = {
    setupGets: 0,
    discoveryPosts: 0,
    inspectionPosts: 0,
    candidateReadinessPosts: 0,
    setupPuts: 0,
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
    if (path === "/api/provider-setup" && request.method() === "GET") {
      evidence.setupGets += 1;
    } else if (
      path === "/api/provider-discoveries/ollama" &&
      request.method() === "POST"
    ) {
      evidence.discoveryPosts += 1;
    } else if (path === "/api/provider-inspections" && request.method() === "POST") {
      evidence.inspectionPosts += 1;
    } else if (
      path === "/api/provider-candidates/readiness" &&
      request.method() === "POST"
    ) {
      evidence.candidateReadinessPosts += 1;
    } else if (path === "/api/provider-setup" && request.method() === "PUT") {
      evidence.setupPuts += 1;
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

async function expectNoPageOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(widths.documentWidth).toBeLessThanOrEqual(widths.innerWidth);
  expect(widths.bodyWidth).toBeLessThanOrEqual(widths.innerWidth);
}

async function waitForProviderSetup(page: Page): Promise<void> {
  if (await page.getByTestId("onboarding-choices").count()) {
    await openProviderSetupFromFirstUse(page);
  }
  await expect(page.getByTestId("provider-setup")).toBeVisible();
}

const candidateProbeIds = [
  "target-connectivity",
  "target-tool-calling",
  "attack-connectivity",
  "attack-strict-json",
] as const;

async function expectCandidateProbeStatuses(
  providerSetup: Locator,
  expectedStatus: string,
): Promise<void> {
  const readiness = providerSetup.getByTestId("provider-readiness-result");
  await expect(readiness).toBeVisible();
  await expect(providerSetup.locator(".readiness-empty")).toHaveCount(0);
  await expect(readiness.locator(".candidate-probe-slot")).toHaveCount(4);

  for (const probeId of candidateProbeIds) {
    const slot = providerSetup.getByTestId(`provider-readiness-probe-${probeId}`);
    await expect(slot).toBeVisible();
    await expect(
      providerSetup.getByTestId(`provider-readiness-probe-${probeId}-status`),
    ).toContainText(expectedStatus);
  }
}

test("连接页桌面端采用三栏，窄屏收敛为单列且没有空洞 Readiness 卡", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await openProviderSetupFromFirstUse(page);

  const providerSetup = page.getByTestId("provider-setup");
  await expect(providerSetup.getByTestId("provider-readiness-visual")).toHaveAttribute(
    "data-state",
    "blocked",
  );
  await expectCandidateProbeStatuses(providerSetup, "— 未检查");
  await expect(providerSetup.locator(".provider-setup-confirm-row")).toBeVisible();

  const localMethod = providerSetup.locator(".provider-setup-local-method");
  const localTarget = providerSetup.locator(".provider-setup-local-target");
  const localAction = providerSetup.locator(".provider-setup-local-action");
  const desktopBoxes = await Promise.all(
    [localMethod, localTarget, localAction].map((cell) => cell.boundingBox()),
  );
  if (desktopBoxes.some((box) => box === null)) {
    throw new Error("本机连接三栏没有完整渲染");
  }
  const [desktopMethod, desktopTarget, desktopAction] = desktopBoxes as [
    NonNullable<(typeof desktopBoxes)[number]>,
    NonNullable<(typeof desktopBoxes)[number]>,
    NonNullable<(typeof desktopBoxes)[number]>,
  ];
  expect(desktopMethod.x).toBeLessThan(desktopTarget.x);
  expect(desktopTarget.x).toBeLessThan(desktopAction.x);
  expect(desktopMethod.width).toBeGreaterThan(0);
  expect(desktopTarget.width).toBeGreaterThan(0);
  expect(desktopAction.width).toBeGreaterThan(0);

  await page.setViewportSize({ width: 390, height: 844 });
  await expectCandidateProbeStatuses(providerSetup, "— 未检查");
  const narrowBoxes = await Promise.all(
    [localMethod, localTarget, localAction].map((cell) => cell.boundingBox()),
  );
  if (narrowBoxes.some((box) => box === null)) {
    throw new Error("窄屏本机连接列没有完整渲染");
  }
  const [narrowMethod, narrowTarget, narrowAction] = narrowBoxes as [
    NonNullable<(typeof narrowBoxes)[number]>,
    NonNullable<(typeof narrowBoxes)[number]>,
    NonNullable<(typeof narrowBoxes)[number]>,
  ];
  expect(Math.abs(narrowMethod.x - narrowTarget.x)).toBeLessThanOrEqual(2);
  expect(Math.abs(narrowTarget.x - narrowAction.x)).toBeLessThanOrEqual(2);
  expect(narrowMethod.y).toBeLessThan(narrowTarget.y);
  expect(narrowTarget.y).toBeLessThan(narrowAction.y);
  await expectNoPageOverflow(page);
});

test("首次连接只由用户显式发现、检查、确认，刷新不重跑模型动作", async ({ page }) => {
  const evidence = observeProviderSetup(page);
  const appGate = await installUnconfiguredAppGate(page);
  await installSyntheticCatalogView(page);
  await page.setViewportSize({ width: 390, height: 844 });

  const initialSetupResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/provider-setup" &&
      response.ok(),
  );
  await page.goto("/");
  await initialSetupResponse;
  await openProviderSetupFromFirstUse(page);
  const setupPanel = page.getByTestId("provider-setup");
  await expect(page.getByTestId("provider-setup-status")).toContainText("尚未连接 AI");
  await expect(page.getByTestId("workspace-guided")).toBeVisible();
  await expectCandidateProbeStatuses(setupPanel, "— 未检查");

  // First-run GET is a read-only status check.  In particular, no discovery,
  // candidate readiness, confirmation PUT, or model completion is triggered.
  expect(evidence.discoveryPosts).toBe(0);
  expect(evidence.inspectionPosts).toBe(0);
  expect(evidence.candidateReadinessPosts).toBe(0);
  expect(evidence.setupPuts).toBe(0);
  await expectNoPageOverflow(page);

  const discoveryResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-discoveries/ollama" &&
      response.ok(),
  );
  await page.getByTestId("provider-setup-discover").click();
  const discovery = await (await discoveryResponse).json();
  expect(discovery.endpoint).toBe("http://127.0.0.1:11434");
  expect(discovery.status).toBe("available");
  expect(discovery.models).toEqual([
    {
      name: "qwen3:8b",
      sizeBytes: 8000,
      modifiedAt: "2026-08-28T00:00:00Z",
    },
    {
      name: "llama3.2:3b",
      sizeBytes: 3000,
      modifiedAt: "2026-08-28T00:00:00Z",
    },
  ]);
  expect(evidence.discoveryPosts).toBe(1);
  await expect(setupPanel.getByText("本项目不限定模型名称", { exact: false })).toBeVisible();
  await expect(setupPanel.getByTestId("provider-setup-model").locator("option")).toHaveCount(3);

  await page.getByTestId("provider-setup-model").selectOption("qwen3:8b");
  const readinessResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-candidates/readiness" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-check").click();
  const readiness = await (await readinessResponse).json();
  expect(readiness.status).toBe("ready");
  await expect(setupPanel.getByTestId("provider-readiness-visual")).toHaveAttribute(
    "data-state",
    "connected",
  );
  expect(readiness.targetProvider.role).toBe("target");
  expect(readiness.attackProvider.role).toBe("attack");
  expect(readiness.planCompatibility).toHaveLength(4);
  expect(evidence.candidateReadinessPosts).toBe(1);
  await expectCandidateProbeStatuses(setupPanel, "✓ 通过");
  await expect(setupPanel.getByTestId("provider-readiness-technical-details")).toBeVisible();

  // Changing a checked draft invalidates the result before confirmation.  The
  // user must restore the draft and perform a fresh explicit readiness check.
  await setupPanel.getByTestId("provider-setup-manual").click();
  await setupPanel.getByTestId("provider-setup-base-url").fill("https://ollama.intra.example");
  await expect(setupPanel.getByTestId("provider-readiness-visual")).toHaveAttribute(
    "data-state",
    "blocked",
  );
  await expect(setupPanel.getByText("草稿已变化，之前的兼容性结果已过期。请重新检查兼容性。")).toBeVisible();
  await expect(setupPanel.getByTestId("provider-setup-confirm")).toBeDisabled();
  await expectCandidateProbeStatuses(setupPanel, "— 未检查");
  expect(evidence.setupPuts).toBe(0);
  await expectNoPageOverflow(page);

  await setupPanel.getByTestId("provider-setup-auto").click();
  const restoredDiscoveryResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-discoveries/ollama" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-discover").click();
  await restoredDiscoveryResponse;
  await setupPanel.getByTestId("provider-setup-model").selectOption("qwen3:8b");
  const restoredReadinessResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-candidates/readiness" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-check").click();
  const restoredReadiness = await (await restoredReadinessResponse).json();
  expect(restoredReadiness.status).toBe("ready");
  await expect(setupPanel.getByTestId("provider-readiness-visual")).toHaveAttribute(
    "data-state",
    "connected",
  );
  expect(evidence.candidateReadinessPosts).toBe(2);
  await expectCandidateProbeStatuses(setupPanel, "✓ 通过");
  await expect(setupPanel.getByTestId("provider-setup-confirm")).toBeEnabled();

  const putRequest = page.waitForRequest(
    (request) =>
      request.method() === "PUT" && apiPath(request.url()) === "/api/provider-setup",
  );
  const putResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      apiPath(response.url()) === "/api/provider-setup" &&
      response.ok(),
  );
  const documentCatalogResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/workspace/documents",
  );
  await setupPanel.getByTestId("provider-setup-confirm").click();
  const request = await putRequest;
  await putResponse;
  const documentCatalog = await documentCatalogResponse;
  expect(documentCatalog.ok()).toBeTruthy();
  expect(JSON.parse(request.postData() ?? "{}")).toEqual({
    settings: {
      kind: "ollama",
      baseUrl: "http://127.0.0.1:11434",
      model: "qwen3:8b",
      authMode: "none",
    },
  });
  expect(evidence.setupPuts).toBe(1);
  // Saving advances the selected custom path to the next business step; the
  // connection body is not mounted in parallel with that step.
  await expect(page.locator(".enterprise-onboarding-step").first()).toHaveClass(/is-complete/);
  await expect(page.getByTestId("document-import")).toBeVisible();
  const nextAction = page.getByTestId("onboarding-next-action");
  await expect(nextAction).toBeFocused();
  await expect(nextAction).toBeInViewport({ ratio: 1 });
  await expectNoPageOverflow(page);

  // Reload only reads the saved Setup state.  It does not discover, probe, or
  // save a model implicitly, and it does not issue a completion request.
  const beforeReload = {
    discoveryPosts: evidence.discoveryPosts,
    inspectionPosts: evidence.inspectionPosts,
    candidateReadinessPosts: evidence.candidateReadinessPosts,
    setupPuts: evidence.setupPuts,
  };
  const reloadSetupResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/provider-setup" &&
      response.ok(),
  );
  appGate.forceNextAppRead();
  await page.reload();
  await reloadSetupResponse;
  await waitForProviderSetup(page);
  await expect(page.getByTestId("provider-setup-compact")).toBeVisible();
  await expect(page.getByTestId("provider-setup-status")).toContainText("已连接");
  expect(evidence.discoveryPosts).toBe(beforeReload.discoveryPosts);
  expect(evidence.inspectionPosts).toBe(beforeReload.inspectionPosts);
  expect(evidence.candidateReadinessPosts).toBe(beforeReload.candidateReadinessPosts);
  expect(evidence.setupPuts).toBe(beforeReload.setupPuts);

  // Editing an already saved setup is local draft state.  Cancel restores the
  // compact saved view without issuing another PUT, readiness, or discovery.
  const beforeCancel = {
    setupGets: evidence.setupGets,
    discoveryPosts: evidence.discoveryPosts,
    inspectionPosts: evidence.inspectionPosts,
    candidateReadinessPosts: evidence.candidateReadinessPosts,
    setupPuts: evidence.setupPuts,
  };
  const reloadedSetupPanel = page.getByTestId("provider-setup");
  await reloadedSetupPanel.getByTestId("provider-setup-edit").click();
  await reloadedSetupPanel.getByTestId("provider-setup-manual").click();
  await reloadedSetupPanel
    .getByTestId("provider-setup-base-url")
    .fill("https://ollama.intra.example");
  await expect(reloadedSetupPanel.getByTestId("provider-setup-confirm")).toBeDisabled();
  await reloadedSetupPanel.getByTestId("provider-setup-cancel").click();
  await expect(reloadedSetupPanel.getByTestId("provider-setup-edit")).toBeVisible();
  await expect(reloadedSetupPanel.getByTestId("provider-setup-auto")).toHaveCount(0);
  await expect(reloadedSetupPanel.getByTestId("provider-setup-status")).toContainText("qwen3:8b");
  expect(evidence.setupGets).toBe(beforeCancel.setupGets);
  expect(evidence.discoveryPosts).toBe(beforeCancel.discoveryPosts);
  expect(evidence.inspectionPosts).toBe(beforeCancel.inspectionPosts);
  expect(evidence.candidateReadinessPosts).toBe(beforeCancel.candidateReadinessPosts);
  expect(evidence.setupPuts).toBe(beforeCancel.setupPuts);
  await expectNoPageOverflow(page);

  // The test transport's third call fails.  The UI exposes a readable
  // diagnostic and restores the button instead of leaving it stuck loading.
  await reloadedSetupPanel.getByTestId("provider-setup-edit").click();
  await reloadedSetupPanel.getByTestId("provider-setup-auto").click();
  const failedDiscoveryResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-discoveries/ollama" &&
      response.ok(),
  );
  await reloadedSetupPanel.getByTestId("provider-setup-discover").click();
  await failedDiscoveryResponse;
  await expect(reloadedSetupPanel.getByTestId("provider-setup-error")).toContainText(
    "无法连接本机 Ollama",
  );
  await expect(reloadedSetupPanel.getByTestId("provider-setup-error")).not.toContainText("OSError");
  await expect(reloadedSetupPanel.getByTestId("provider-setup-discover")).toBeEnabled();
  expect(evidence.discoveryPosts).toBe(3);
  expect(evidence.inspectionPosts).toBe(0);
  expect(evidence.candidateReadinessPosts).toBe(2);
  expect(evidence.setupPuts).toBe(1);
  await expectNoPageOverflow(page);

  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("合成演示确认连接后定位运行按钮，不自动开始检查", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  // Keep this layout regression independent of the shared transport's
  // intentional discovery-failure counter used by the preceding test.
  await page.route("**/api/provider-discoveries/ollama", (route) => route.fulfill({
    json: { endpoint: "http://127.0.0.1:11434", status: "available", models: [
      { name: "qwen3:8b", sizeBytes: 8000, modifiedAt: "2026-08-28T00:00:00Z" },
    ], diagnostic: null },
  }));
  await page.route("**/api/provider-setup", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const response = await route.fetch();
    await route.fulfill({ response, json: {
      ...(await response.json()), configured: false, settings: null, credentialConfigured: false,
    } });
  });
  let scans = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && apiPath(request.url()) === "/api/scans") scans += 1;
  });
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  await page.getByTestId("onboarding-demo-connect").click();
  await page.getByTestId("provider-setup-discover").click();
  await expect(page.getByTestId("provider-setup-model").locator("option")).toHaveCount(2);
  await page.getByTestId("provider-setup-model").selectOption("qwen3:8b");
  await page.getByTestId("provider-setup-check").click();
  await expect(page.getByTestId("provider-setup-confirm")).toBeEnabled();
  await page.getByTestId("provider-setup-confirm").click();
  const run = page.getByTestId("onboarding-demo-run");
  await expect(run).toBeFocused();
  await expect(run).toBeInViewport({ ratio: 1 });
  expect(scans).toBe(0);
});

test("企业地址通过真实 Test-only API 读取模型并完成候选 Readiness 后只保存一次", async ({
  page,
}) => {
  const evidence = observeProviderSetup(page);
  await installUnconfiguredAppGate(page);
  await installSyntheticCatalogView(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await openProviderSetupFromFirstUse(page);

  const setupPanel = page.getByTestId("provider-setup");
  await expect(setupPanel.getByTestId("provider-setup-compact")).toBeVisible();
  await setupPanel.getByTestId("provider-setup-edit").click();
  await setupPanel.getByTestId("provider-setup-manual").click();
  await setupPanel
    .getByTestId("provider-setup-base-url")
    .fill("https://runtime.intra.example/team");

  const inspectionResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-inspections" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-inspect").click();
  const inspection = await (await inspectionResponse).json();
  expect(inspection).toMatchObject({
    status: "available",
    protocol: "openai_compatible",
    baseUrl: "https://runtime.intra.example/team/v1",
    modelsEnumerated: true,
  });
  expect(inspection.models).toEqual([
    {
      id: "enterprise-model",
      object: "model",
      created: 1_725_000_000,
      ownedBy: "platform-team",
    },
  ]);
  expect(evidence.discoveryPosts).toBe(0);
  expect(evidence.inspectionPosts).toBe(1);

  await setupPanel.getByTestId("provider-setup-model").selectOption("enterprise-model");
  const readinessResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-candidates/readiness" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-check").click();
  const readiness = await (await readinessResponse).json();
  expect(readiness.status).toBe("ready");
  expect(readiness.targetProvider.provider).toBe("openai_compatible");
  expect(readiness.attackProvider.provider).toBe("openai_compatible");
  expect(evidence.candidateReadinessPosts).toBe(1);
  await expectCandidateProbeStatuses(setupPanel, "✓ 通过");

  const putRequest = page.waitForRequest(
    (request) =>
      request.method() === "PUT" && apiPath(request.url()) === "/api/provider-setup",
  );
  const putResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      apiPath(response.url()) === "/api/provider-setup" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-confirm").click();
  const request = await putRequest;
  await putResponse;
  expect(JSON.parse(request.postData() ?? "{}")).toEqual({
    settings: {
      kind: "openai_compatible",
      baseUrl: "https://runtime.intra.example/team/v1",
      model: "enterprise-model",
      authMode: "none",
    },
  });
  expect(evidence.discoveryPosts).toBe(0);
  expect(evidence.inspectionPosts).toBe(1);
  expect(evidence.candidateReadinessPosts).toBe(1);
  expect(evidence.setupPuts).toBe(1);
  await expect(page.locator(".enterprise-onboarding-step").first()).toHaveClass(/is-complete/);
  await expect(page.getByTestId("document-import")).toBeVisible();
  await expectNoPageOverflow(page);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("企业地址未枚举模型时仍可手填模型并完成同一 Readiness 流程", async ({ page }) => {
  const evidence = observeProviderSetup(page);
  await installUnconfiguredAppGate(page);
  await installSyntheticCatalogView(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await openProviderSetupFromFirstUse(page);

  const setupPanel = page.getByTestId("provider-setup");
  await expect(setupPanel.getByTestId("provider-setup-compact")).toBeVisible();
  await setupPanel.getByTestId("provider-setup-edit").click();
  await setupPanel.getByTestId("provider-setup-manual").click();
  await setupPanel
    .getByTestId("provider-setup-base-url")
    .fill("https://manual.runtime.intra.example/team");

  const inspectionResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-inspections" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-inspect").click();
  const inspection = await (await inspectionResponse).json();
  expect(inspection).toMatchObject({
    status: "available",
    protocol: "openai_compatible",
    baseUrl: "https://manual.runtime.intra.example/team/v1",
    models: [],
    modelsEnumerated: true,
  });
  await expect(setupPanel.getByTestId("provider-setup-model")).toBeVisible();
  await setupPanel.getByTestId("provider-setup-model").fill("manual-enterprise-model");

  const readinessResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-candidates/readiness" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-check").click();
  const readiness = await (await readinessResponse).json();
  expect(readiness.status).toBe("ready");
  expect(readiness.targetProvider.model).toBe("manual-enterprise-model");
  expect(readiness.attackProvider.model).toBe("manual-enterprise-model");
  expect(evidence.discoveryPosts).toBe(0);
  expect(evidence.inspectionPosts).toBe(1);
  expect(evidence.candidateReadinessPosts).toBe(1);
  await expectCandidateProbeStatuses(setupPanel, "✓ 通过");

  const putRequest = page.waitForRequest(
    (request) =>
      request.method() === "PUT" && apiPath(request.url()) === "/api/provider-setup",
  );
  const putResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      apiPath(response.url()) === "/api/provider-setup" &&
      response.ok(),
  );
  await setupPanel.getByTestId("provider-setup-confirm").click();
  const request = await putRequest;
  await putResponse;
  expect(JSON.parse(request.postData() ?? "{}")).toEqual({
    settings: {
      kind: "openai_compatible",
      baseUrl: "https://manual.runtime.intra.example/team/v1",
      model: "manual-enterprise-model",
      authMode: "none",
    },
  });
  expect(evidence.setupPuts).toBe(1);
  await expect(page.locator(".enterprise-onboarding-step").first()).toHaveClass(/is-complete/);
  await expect(page.getByTestId("document-import")).toBeVisible();
  await expectNoPageOverflow(page);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

type ProviderSecretTestWindow = Window & {
  __AGENT_AUDIT_PROVIDER_SECRET_MODE__?: "fail" | "success";
  __AGENT_AUDIT_PROVIDER_SECRET_CALLS__?: number;
  __TAURI_INTERNALS__?: {
    invoke: (command: string, args?: unknown) => Promise<unknown>;
  };
};

test("企业 Bearer 使用新密钥，凭据存储失败时不发送明文保存请求", async ({ page }) => {
  const newSecret = "f031-e2e-new-origin-key";
  const oldSecret = "f031-e2e-old-sidecar-key";
  let setupPuts = 0;
  let inspectionBody: Record<string, unknown> | null = null;
  let readinessBody: Record<string, unknown> | null = null;
  let savedBody: Record<string, unknown> | null = null;

  const runtimeSnapshot = {
    provider: "test-e2e",
    model: null,
    retrieverEngine: "embedding",
    retrieverModel: "test-embedder",
    retrieverDimensions: 384,
    indexedDocumentCount: 20,
  };
  const unconfiguredState = {
    configured: false,
    settings: null,
    credentialConfigured: false,
    runtimeSnapshot,
  };
  const configuredState = {
    configured: true,
    settings: {
      kind: "openai_compatible",
      baseUrl: "https://new.runtime.intra.example/team/v1",
      model: "enterprise-model",
      authMode: "bearer",
    },
    credentialConfigured: true,
    runtimeSnapshot: {
      ...runtimeSnapshot,
      provider: "openai_compatible",
      model: "enterprise-model",
    },
  };
  const inspectionResult = {
    status: "available",
    protocol: "openai_compatible",
    baseUrl: "https://new.runtime.intra.example/team/v1",
    models: [
      {
        id: "enterprise-model",
        object: "model",
        created: 1_725_000_000,
        ownedBy: "platform-team",
      },
    ],
    diagnostic: null,
    modelsEnumerated: true,
  };
  const readinessResult = {
    id: "readiness_f031_e2e",
    checkedAt: "2026-08-28T00:00:00Z",
    status: "ready",
    targetProvider: {
      role: "target",
      provider: "openai_compatible",
      model: "enterprise-model",
      status: "ready",
      probes: [
        { id: "target.connectivity", status: "passed", durationMs: 0.1, detail: null },
        { id: "target.tool_calling", status: "passed", durationMs: 0.1, detail: null },
      ],
    },
    attackProvider: {
      role: "attack",
      provider: "openai_compatible",
      model: "enterprise-model",
      status: "ready",
      probes: [
        { id: "attack.connectivity", status: "passed", durationMs: 0.1, detail: null },
        { id: "attack.strict_json", status: "passed", durationMs: 0.1, detail: null },
      ],
    },
    planCompatibility: [],
  };
  const corsHeaders = {
    "access-control-allow-origin": "http://127.0.0.1:5173",
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "GET,POST,PUT,OPTIONS",
  };

  await page.addInitScript(() => {
    const target = window as ProviderSecretTestWindow;
    target.__AGENT_AUDIT_PROVIDER_SECRET_MODE__ = "fail";
    target.__AGENT_AUDIT_PROVIDER_SECRET_CALLS__ = 0;
    target.__TAURI_INTERNALS__ = {
      invoke: async (command: string) => {
        if (command === "get_api_base") {
          return "http://127.0.0.1:8000";
        }
        if (command === "store_provider_secret") {
          target.__AGENT_AUDIT_PROVIDER_SECRET_CALLS__ =
            (target.__AGENT_AUDIT_PROVIDER_SECRET_CALLS__ ?? 0) + 1;
          if (target.__AGENT_AUDIT_PROVIDER_SECRET_MODE__ === "fail") {
            throw new Error("synthetic credential store unavailable");
          }
        }
        return undefined;
      },
    };
  });
  await page.route("**/api/provider-setup", async (route) => {
    const method = route.request().method();
    if (method === "OPTIONS") {
      await route.continue();
      return;
    }
    if (method === "GET") {
      await route.fulfill({ status: 200, headers: corsHeaders, contentType: "application/json", body: JSON.stringify(unconfiguredState) });
      return;
    }
    setupPuts += 1;
    savedBody = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
    await route.fulfill({ status: 200, headers: corsHeaders, contentType: "application/json", body: JSON.stringify(configuredState) });
  });
  await page.route("**/api/provider-inspections", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.continue();
      return;
    }
    inspectionBody = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
    await route.fulfill({ status: 200, headers: corsHeaders, contentType: "application/json", body: JSON.stringify(inspectionResult) });
  });
  await page.route("**/api/provider-candidates/readiness", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.continue();
      return;
    }
    readinessBody = JSON.parse(route.request().postData() ?? "{}") as Record<string, unknown>;
    await route.fulfill({ status: 200, headers: corsHeaders, contentType: "application/json", body: JSON.stringify(readinessResult) });
  });

  await installSyntheticCatalogView(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await chooseOnboardingPath(page, "custom");
  await expect(page.getByTestId("onboarding-step-provider")).toBeVisible();
  await page.getByTestId("onboarding-next-action").click();
  const setupPanel = page.getByTestId("provider-setup");
  await expect(setupPanel).toBeVisible();
  await setupPanel.getByTestId("provider-setup-manual").click();
  await setupPanel.getByTestId("provider-setup-base-url").fill("https://new.runtime.intra.example/team");
  await setupPanel.getByTestId("provider-setup-auth-mode").selectOption("bearer");
  await setupPanel.getByTestId("provider-setup-secret").fill(newSecret);

  const inspectionResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && apiPath(response.url()) === "/api/provider-inspections",
  );
  await setupPanel.getByTestId("provider-setup-inspect").click();
  await inspectionResponse;
  expect(inspectionBody).toEqual({
    kind: "openai_compatible",
    baseUrl: "https://new.runtime.intra.example/team",
    authMode: "bearer",
    credential: newSecret,
  });
  expect(JSON.stringify(inspectionBody)).not.toContain(oldSecret);
  await setupPanel.getByTestId("provider-setup-model").selectOption("enterprise-model");

  const readinessResponse = page.waitForResponse(
    (response) => response.request().method() === "POST" && apiPath(response.url()) === "/api/provider-candidates/readiness",
  );
  await setupPanel.getByTestId("provider-setup-check").click();
  await readinessResponse;
  expect(readinessBody).toEqual({
    settings: {
      kind: "openai_compatible",
      baseUrl: "https://new.runtime.intra.example/team/v1",
      model: "enterprise-model",
      authMode: "bearer",
    },
    credential: newSecret,
  });
  expect(JSON.stringify(readinessBody)).not.toContain(oldSecret);
  await expect(setupPanel.getByTestId("provider-setup-confirm")).toBeEnabled();

  await setupPanel.getByTestId("provider-setup-confirm").click();
  await expect(setupPanel.getByTestId("provider-setup-error")).toContainText(
    "synthetic credential store unavailable",
  );
  expect(setupPuts).toBe(0);
  expect(
    await page.evaluate(
      () => (window as ProviderSecretTestWindow).__AGENT_AUDIT_PROVIDER_SECRET_CALLS__,
    ),
  ).toBe(1);
  expect(await page.locator("body").innerText()).not.toContain(newSecret);

  await page.evaluate(() => {
    (window as ProviderSecretTestWindow).__AGENT_AUDIT_PROVIDER_SECRET_MODE__ = "success";
  });
  const saveResponse = page.waitForResponse(
    (response) => response.request().method() === "PUT" && apiPath(response.url()) === "/api/provider-setup",
  );
  await setupPanel.getByTestId("provider-setup-confirm").click();
  await saveResponse;
  expect(setupPuts).toBe(1);
  expect(savedBody).toEqual({
    settings: {
      kind: "openai_compatible",
      baseUrl: "https://new.runtime.intra.example/team/v1",
      model: "enterprise-model",
      authMode: "bearer",
    },
    credential: newSecret,
  });
  expect(JSON.stringify(savedBody)).not.toContain(oldSecret);
  expect(await page.locator("body").innerText()).not.toContain(newSecret);
  await expect(page.locator(".enterprise-onboarding-step").first()).toHaveClass(/is-complete/);
  await expect(page.getByTestId("document-import")).toBeVisible();

  const widths = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(widths.documentWidth).toBeLessThanOrEqual(widths.innerWidth);
  expect(widths.bodyWidth).toBeLessThanOrEqual(widths.innerWidth);
});
