import { expect, type Page } from "@playwright/test";
import { test } from "./support/test";
import { openProviderSetupFromFirstUse } from "./support/first_use";

// These browser routes are explicit test-only API doubles.  They do not
// represent a Claude Gateway or an enterprise adapter and never contact one.
const TEST_SECRET = "f050-browser-secret-test-only";
const ANTHROPIC_BASE_URL = "https://claude-gateway.intra.example/team/v1";
const ADAPTER_BASE_URL = "https://bridge.intra.example/team/v1";
const MODEL = "enterprise-model";
const ADAPTER_VERSION = "agent_audit_adapter.v1";

type SetupOptions = {
  configured?: boolean;
  gateConfigured?: boolean;
};

type ApiEvidence = {
  calls: Array<{ method: string; path: string; body: unknown }>;
  inspectionBodies: unknown[];
  readinessBodies: unknown[];
  setupBodies: unknown[];
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function runtimeSnapshot(provider = "test-e2e", model: string | null = null) {
  return {
    provider,
    model,
    retrieverEngine: "tfidf",
    retrieverModel: "tfidf-test",
    retrieverDimensions: null,
    indexedDocumentCount: 20,
  };
}

function setupState(configured: boolean, kind = "openai_compatible", model = MODEL) {
  return {
    configured,
    settings: configured
      ? {
          kind,
          baseUrl: kind === "agent_audit_adapter" ? ADAPTER_BASE_URL : ANTHROPIC_BASE_URL,
          model,
          authMode: "none",
        }
      : null,
    credentialConfigured: false,
    runtimeSnapshot: configured
      ? runtimeSnapshot(kind, model)
      : runtimeSnapshot(),
  };
}

function inspectionResult(kind: "anthropic_compatible" | "agent_audit_adapter") {
  const adapter = kind === "agent_audit_adapter";
  const capabilities = adapter
    ? {
        text: true,
        toolCalling: true,
        structuredOutput: true,
        usage: true,
      }
    : null;
  return {
    status: "available",
    protocol: kind,
    baseUrl: adapter ? ADAPTER_BASE_URL : ANTHROPIC_BASE_URL,
    models: [],
    diagnostic: null,
    modelsEnumerated: true,
    protocolVersion: adapter ? ADAPTER_VERSION : null,
    capabilities,
    manifest: adapter
      ? {
          protocol: "agent_audit_adapter",
          protocolVersion: ADAPTER_VERSION,
          capabilities,
        }
      : null,
  };
}

function readinessResult(kind: "anthropic_compatible" | "agent_audit_adapter", model: string) {
  const probes = (ids: string[]) =>
    ids.map((id) => ({ id, status: "passed", durationMs: 0.1, detail: null }));
  return {
    id: `readiness_f050_${kind}`,
    checkedAt: "2026-08-30T00:00:00Z",
    status: "ready",
    targetProvider: {
      role: "target",
      provider: kind,
      model,
      status: "ready",
      probes: probes(["target.connectivity", "target.tool_calling"]),
    },
    attackProvider: {
      role: "attack",
      provider: kind,
      model,
      status: "ready",
      probes: probes(["attack.connectivity", "attack.strict_json"]),
    },
    planCompatibility: [],
  };
}

async function installProviderApi(
  page: Page,
  options: SetupOptions = {},
): Promise<ApiEvidence> {
  const configured = options.configured ?? false;
  const gateConfigured = options.gateConfigured ?? configured;
  const evidence: ApiEvidence = {
    calls: [],
    inspectionBodies: [],
    readinessBodies: [],
    setupBodies: [],
  };
  const initialState = configured
    ? setupState(true, "openai_compatible", "legacy-model")
    : setupState(false);
  let setupGets = 0;

  await page.route("**/api/provider-setup", async (route) => {
    const request = route.request();
    const method = request.method();
    const body = request.postDataJSON() as unknown;
    evidence.calls.push({ method, path: "/api/provider-setup", body });
    if (method === "GET") {
      setupGets += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          configured && !gateConfigured && setupGets === 1
            ? setupState(false)
            : initialState,
        ),
      });
      return;
    }
    if (method === "PUT") {
      evidence.setupBodies.push(body);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(setupState(true, "anthropic_compatible", MODEL)),
      });
      return;
    }
    await route.continue();
  });

  await page.route("**/api/provider-discoveries/ollama", async (route) => {
    const request = route.request();
    const body = request.postDataJSON() as unknown;
    evidence.calls.push({
      method: request.method(),
      path: "/api/provider-discoveries/ollama",
      body,
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        endpoint: "http://127.0.0.1:11434",
        status: "available",
        models: [{ name: "qwen3:8b", sizeBytes: 8_000, modifiedAt: null }],
        diagnostic: null,
      }),
    });
  });

  await page.route("**/api/provider-inspections", async (route) => {
    const request = route.request();
    const body = request.postDataJSON() as Record<string, unknown>;
    evidence.calls.push({
      method: request.method(),
      path: "/api/provider-inspections",
      body,
    });
    evidence.inspectionBodies.push(body);
    const kind = body.kind === "agent_audit_adapter"
      ? "agent_audit_adapter"
      : "anthropic_compatible";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(inspectionResult(kind)),
    });
  });

  await page.route("**/api/provider-candidates/readiness", async (route) => {
    const request = route.request();
    const body = request.postDataJSON() as Record<string, unknown>;
    evidence.calls.push({
      method: request.method(),
      path: "/api/provider-candidates/readiness",
      body,
    });
    evidence.readinessBodies.push(body);
    const settings = (body.settings ?? {}) as Record<string, unknown>;
    const kind = settings.kind === "agent_audit_adapter"
      ? "agent_audit_adapter"
      : "anthropic_compatible";
    const model = typeof settings.model === "string" ? settings.model : MODEL;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(readinessResult(kind, model)),
    });
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

test("F-050 Anthropic 手选只在用户动作后请求，支持 x-api-key、手填模型与 stale", async ({
  page,
}) => {
  const evidence = await installProviderApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await openProviderSetupFromFirstUse(page);

  const setup = page.getByTestId("provider-setup");
  await expect(setup).toBeVisible();
  await expect(page.getByTestId("display-scale-large")).toHaveAttribute("aria-pressed", "true");
  expect(evidence.calls.filter((call) => call.method !== "GET")).toEqual([]);

  await setup.getByTestId("provider-setup-manual").click();
  await setup.getByTestId("provider-setup-protocol").selectOption("anthropic_compatible");
  await expect(setup.getByTestId("provider-setup-auth-mode")).toHaveValue("x_api_key");
  await expect(setup.getByTestId("provider-setup-secret")).toBeVisible();
  await setup
    .getByTestId("provider-setup-base-url")
    .fill("https://claude-gateway.intra.example/team");
  await setup.getByTestId("provider-setup-secret").fill(TEST_SECRET);

  const inspectionResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-inspections" &&
      response.ok(),
  );
  await setup.getByTestId("provider-setup-inspect").click();
  await inspectionResponse;
  expect(evidence.inspectionBodies).toEqual([
    {
      kind: "anthropic_compatible",
      baseUrl: "https://claude-gateway.intra.example/team",
      authMode: "x_api_key",
      credential: TEST_SECRET,
    },
  ]);
  await expect(setup.getByTestId("provider-setup-model")).toBeVisible();

  const manualModel = `claude-enterprise-${"x".repeat(80)}`;
  await setup.getByTestId("provider-setup-model").fill(manualModel);
  const readinessResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/provider-candidates/readiness" &&
      response.ok(),
  );
  await setup.getByTestId("provider-setup-check").click();
  await readinessResponse;
  expect(evidence.readinessBodies).toEqual([
    {
      settings: {
        kind: "anthropic_compatible",
        baseUrl: ANTHROPIC_BASE_URL,
        model: manualModel,
        authMode: "x_api_key",
      },
      credential: TEST_SECRET,
    },
  ]);
  await expect(setup.getByTestId("provider-readiness-visual")).toHaveAttribute(
    "data-state",
    "connected",
  );
  // Browser mode may render the READY action, but must refuse persistence of
  // a secret and issue no plaintext PUT without the Desktop credential-store
  // boundary.
  await expect(setup.getByTestId("provider-setup-confirm")).toBeEnabled();
  await setup.getByTestId("provider-setup-confirm").click();
  await expect(setup.getByTestId("provider-setup-error")).toContainText("浏览器模式不会明文保存");
  expect(evidence.setupBodies).toEqual([]);
  expect(evidence.calls.filter((call) => call.path.includes("/api/tags"))).toEqual([]);

  // Any address/protocol/credential edit invalidates the previously checked
  // candidate before another user-triggered Readiness call.
  await setup.getByTestId("provider-setup-base-url").fill("https://new.claude.intra.example/team");
  await expect(setup.getByTestId("provider-readiness-visual")).toHaveAttribute(
    "data-state",
    "blocked",
  );
  await expect(setup.getByText("草稿已变化，之前的兼容性结果已过期。请重新检查兼容性。")).toBeVisible();
  expect(evidence.readinessBodies).toHaveLength(1);

  // Exercise both display-scale choices at the acceptance viewport.  The
  // app intentionally keeps narrow layout zoom at 1 while large text remains
  // selectable and does not create page-level horizontal overflow.
  await page.getByTestId("display-scale-standard").click();
  await expect(page.getByTestId("display-scale-standard")).toHaveAttribute("aria-pressed", "true");
  await expectNoPageOverflow(page);
  await page.getByTestId("display-scale-large").click();
  await expect(page.getByTestId("display-scale-large")).toHaveAttribute("aria-pressed", "true");
  await expectNoPageOverflow(page);
  expect(await page.locator("body").innerText()).not.toContain(TEST_SECRET);
});

test("F-050 Adapter v1 选择协议并手填模型后才运行候选检查", async ({ page }) => {
  const evidence = await installProviderApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await openProviderSetupFromFirstUse(page);
  const setup = page.getByTestId("provider-setup");
  await expect(setup).toBeVisible();
  expect(evidence.calls.filter((call) => call.method !== "GET")).toEqual([]);

  await setup.getByTestId("provider-setup-manual").click();
  await setup.getByTestId("provider-setup-protocol").selectOption("agent_audit_adapter");
  await expect(setup.getByTestId("provider-setup-auth-mode")).toHaveValue("none");
  await setup.getByTestId("provider-setup-base-url").fill("https://bridge.intra.example/team");

  await setup.getByTestId("provider-setup-inspect").click();
  expect(evidence.inspectionBodies).toEqual([
    {
      kind: "agent_audit_adapter",
      baseUrl: "https://bridge.intra.example/team",
      authMode: "none",
    },
  ]);
  await expect(setup.getByTestId("provider-setup-capabilities")).toContainText(ADAPTER_VERSION);
  await expect(setup.getByTestId("provider-setup-model")).toBeVisible();

  const manualModel = `adapter-enterprise-${"m".repeat(80)}`;
  await setup.getByTestId("provider-setup-model").fill(manualModel);
  await setup.getByTestId("provider-setup-check").click();
  await expect(setup.getByTestId("provider-readiness-visual")).toHaveAttribute(
    "data-state",
    "connected",
  );
  expect(evidence.readinessBodies).toEqual([
    {
      settings: {
        kind: "agent_audit_adapter",
        baseUrl: ADAPTER_BASE_URL,
        model: manualModel,
        authMode: "none",
      },
    },
  ]);
  expect(evidence.calls.filter((call) => call.path.includes("/api/tags"))).toEqual([]);
  await expectNoPageOverflow(page);
});

test("F-050 已保存连接取消编辑不发请求并恢复旧设置", async ({ page }) => {
  const evidence = await installProviderApi(page, { configured: true, gateConfigured: false });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await openProviderSetupFromFirstUse(page);

  const setup = page.getByTestId("provider-setup");
  await expect(setup.getByTestId("provider-setup-compact")).toBeVisible();
  const beforeNonGet = evidence.calls.filter((call) => call.method !== "GET");
  expect(beforeNonGet).toEqual([]);

  await setup.getByTestId("provider-setup-edit").click();
  await setup.getByTestId("provider-setup-protocol").selectOption("agent_audit_adapter");
  await setup.getByTestId("provider-setup-base-url").fill("https://changed.intra.example/team");
  await setup.getByTestId("provider-setup-cancel").click();

  await expect(setup.getByTestId("provider-setup-compact")).toBeVisible();
  await expect(page.getByTestId("provider-setup-status")).toContainText("legacy-model");
  expect(evidence.calls.filter((call) => call.method !== "GET")).toEqual([]);
  await expectNoPageOverflow(page);
});
