import { expect, type Page } from "@playwright/test";

export type OnboardingPath = "demo" | "custom";

/**
 * Keep legacy E2E scenarios on the production first-use path while supplying
 * an already-confirmed provider only in this browser context.  The response
 * is changed at the UI boundary; scans, plans, documents, and readiness still
 * use the real local E2E API server.
 */
export async function installConfiguredProviderState(page: Page): Promise<void> {
  await page.route("**/api/provider-setup", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    const response = await route.fetch();
    const payload = (await response.json()) as Record<string, any>;
    payload.configured = true;
    payload.settings ??= {
      kind: "ollama",
      baseUrl: "http://127.0.0.1:11434",
      model: "qwen3:8b",
      authMode: "none",
    };
    payload.credentialConfigured = false;
    if (payload.runtimeSnapshot && typeof payload.runtimeSnapshot === "object") {
      payload.runtimeSnapshot.provider = payload.settings.kind;
      payload.runtimeSnapshot.model = payload.settings.model;
    }
    await route.fulfill({ response, json: payload });
  });
}

/**
 * Give document-management regressions a fresh synthetic catalog view even
 * when another E2E has already committed a user document to the shared local
 * workspace.  The import/preview/commit requests themselves remain routed to
 * the production API; only this test's read-only catalog projection is
 * isolated so the onboarding task stays on the document step.
 */
export async function installSyntheticCatalogView(page: Page): Promise<void> {
  await page.route("**/api/workspace/documents", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    const response = await route.fetch();
    const payload = (await response.json()) as Record<string, any>;
    if (Array.isArray(payload.documents)) {
      payload.documents = payload.documents.filter(
        (document: Record<string, any>) =>
          Array.isArray(document.labels) &&
          document.labels.some((label: unknown) =>
            typeof label === "string" && label.toUpperCase() === "SYNTHETIC",
          ),
      );
    }
    await route.fulfill({ response, json: payload });
  });
}

/**
 * Force the first App-level status read to remain unconfigured while letting
 * the subsequently mounted ProviderSetupView read the saved state.  This
 * preserves component regressions for a saved connection without rendering a
 * full connection body before the user chooses a path.
 */
export type AppGateControl = {
  forceNextAppRead: () => void;
};

export async function installUnconfiguredAppGate(page: Page): Promise<AppGateControl> {
  let appStatusRead = true;
  let forceAppRead = false;
  await page.route("**/api/provider-setup", async (route) => {
    if (
      route.request().method() !== "GET" ||
      (!appStatusRead && !forceAppRead)
    ) {
      await route.continue();
      return;
    }

    appStatusRead = false;
    forceAppRead = false;
    const response = await route.fetch();
    const payload = (await response.json()) as Record<string, any>;
    payload.configured = false;
    payload.settings = null;
    payload.credentialConfigured = false;
    await route.fulfill({ response, json: payload });
  });

  return {
    forceNextAppRead: () => {
      forceAppRead = true;
    },
  };
}

export async function chooseOnboardingPath(
  page: Page,
  path: OnboardingPath,
): Promise<void> {
  await expect(page.getByTestId("onboarding-choices")).toBeVisible();
  await page.getByTestId(`onboarding-${path}`).click();
  await expect(page.getByTestId("onboarding-path")).toBeVisible();
}

export async function openProviderSetupFromFirstUse(page: Page): Promise<void> {
  await chooseOnboardingPath(page, "custom");
  await expect(page.getByTestId("onboarding-step-provider")).toBeVisible();
  await page.getByTestId("onboarding-next-action").click();
  await expect(page.getByTestId("provider-setup")).toBeVisible();
}
