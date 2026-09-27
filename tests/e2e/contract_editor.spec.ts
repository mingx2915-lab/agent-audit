import { expect, type Page } from "@playwright/test";
import { test } from "./support/test";
import { chooseOnboardingPath, installConfiguredProviderState } from "./support/first_use";

type ContractEditorRequests = {
  previewPosts: number;
  contractPuts: number;
  planGets: number;
  apiNon2xx: string[];
  pageErrors: string[];
  consoleErrors: string[];
  requestFailures: string[];
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function observeContractEditorHealth(page: Page): ContractEditorRequests {
  const evidence: ContractEditorRequests = {
    previewPosts: 0,
    contractPuts: 0,
    planGets: 0,
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
    if (request.method() === "POST" && path === "/api/security-contract/previews") {
      evidence.previewPosts += 1;
    } else if (request.method() === "PUT" && path === "/api/security-contract") {
      evidence.contractPuts += 1;
    } else if (request.method() === "GET" && path === "/api/attack-plans") {
      evidence.planGets += 1;
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

async function openContractEditor(page: Page): Promise<void> {
  await installConfiguredProviderState(page);
  const contractResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/security-contract" &&
      response.ok(),
  );
  await page.goto("/");
  await contractResponse;
  await page.getByRole("button", { name: "设置与计划", exact: true }).click();
  await expect(page.getByTestId("security-contract-editor")).toBeVisible();
}

async function enterVisualDraft(page: Page): Promise<void> {
  await page.getByTestId("contract-visual-edit").click();
  await expect(page.getByTestId("contract-mode-visual")).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByTestId("contract-preview")).toBeEnabled();
  await expect(page.getByTestId("contract-save")).toBeDisabled();
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

async function previewAndSave(page: Page, name: string): Promise<void> {
  const nameInput = page.getByTestId("contract-name-input");
  await nameInput.fill(name);
  await expect(page.getByTestId("contract-save")).toBeDisabled();

  const previewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/security-contract/previews" &&
      response.ok(),
  );
  await page.getByTestId("contract-preview").click();
  await previewResponse;
  await expect(page.getByTestId("contract-preview-panel")).toBeVisible();
  await expect(page.getByTestId("contract-preview-panel")).toContainText("name");
  await expect(page.getByTestId("contract-save")).toBeEnabled();

  const putResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      apiPath(response.url()) === "/api/security-contract" &&
      response.ok(),
  );
  const planResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.getByTestId("contract-save").click();
  await putResponse;
  await planResponse;
  await expect(page.getByTestId("contract-visual-edit")).toBeVisible();
  await expect(
    page.getByTestId("security-contract-editor").getByText("Contract 已保存", { exact: false }),
  ).toBeVisible();
  await expect(page.getByTestId("security-contract-editor")).toContainText(name);
}

test("Contract editor keeps Draft, Preview, Save and Cancel side effects explicit", async ({
  page,
}) => {
  const evidence = observeContractEditorHealth(page);
  await openContractEditor(page);

  // Page load and navigation only read the active Contract/Plans.
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.contractPuts).toBe(0);
  const planGetsBeforeEdit = evidence.planGets;

  await enterVisualDraft(page);
  const nameInput = page.getByTestId("contract-name-input");

  // Visual and Advanced JSON operate on one draft in both directions.
  await nameInput.fill("F-023 visual draft");
  await page.getByTestId("contract-mode-json").click();
  const jsonDraft = page.getByTestId("contract-json-draft");
  await expect(jsonDraft).toHaveValue(/"name": "F-023 visual draft"/);

  const jsonCandidate = JSON.parse(await jsonDraft.inputValue()) as Record<string, unknown>;
  jsonCandidate.name = "F-023 JSON draft";
  await jsonDraft.fill(JSON.stringify(jsonCandidate, null, 2));
  await page.getByTestId("contract-mode-visual").click();
  await expect(nameInput).toHaveValue("F-023 JSON draft");

  // Invalid JSON remains visible and blocks both actions instead of being repaired.
  await page.getByTestId("contract-mode-json").click();
  await jsonDraft.fill("{ invalid JSON");
  await expect(page.getByRole("alert")).toContainText("JSON 格式无效");
  await expect(page.getByTestId("contract-preview")).toBeDisabled();
  await expect(page.getByTestId("contract-save")).toBeDisabled();

  const validCandidate = JSON.parse(
    JSON.stringify(jsonCandidate),
  ) as Record<string, unknown>;
  validCandidate.name = "F-023 preview candidate";
  await jsonDraft.fill(JSON.stringify(validCandidate, null, 2));
  await page.getByTestId("contract-mode-visual").click();
  await expect(nameInput).toHaveValue("F-023 preview candidate");

  const previewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/security-contract/previews" &&
      response.ok(),
  );
  await page.getByTestId("contract-preview").click();
  await previewResponse;
  await expect(page.getByTestId("contract-preview-panel")).toBeVisible();
  await expect(page.getByTestId("contract-save")).toBeEnabled();

  // Any new draft edit expires the previously returned Preview and re-locks Save.
  await nameInput.fill("F-023 changed after preview");
  await expect(page.getByText("当前 Draft 已变化，旧 Preview 已过期")).toBeVisible();
  await expect(page.getByTestId("contract-save")).toBeDisabled();

  const putsBeforeSave = evidence.contractPuts;
  const planGetsBeforeSave = evidence.planGets;
  await previewAndSave(page, "F-023 saved Contract");
  expect(evidence.previewPosts).toBe(2);
  expect(evidence.contractPuts).toBe(putsBeforeSave + 1);
  expect(evidence.planGets).toBe(planGetsBeforeSave + 1);
  expect(evidence.planGets).toBeGreaterThan(planGetsBeforeEdit);

  // A canceled edit restores the saved active Contract and never sends PUT.
  await page.getByTestId("contract-visual-edit").click();
  await expect(page.getByTestId("contract-name-input")).toHaveValue("F-023 saved Contract");
  await page.getByTestId("contract-name-input").fill("F-023 canceled draft");
  const putsBeforeCancel = evidence.contractPuts;
  await page.getByTestId("contract-cancel").click();
  await expect(page.getByTestId("contract-visual-edit")).toBeVisible();
  expect(evidence.contractPuts).toBe(putsBeforeCancel);
  const activeAfterCancel = await page.request.get("/api/security-contract");
  expect(activeAfterCancel.ok()).toBe(true);
  expect((await activeAfterCancel.json()).name).toBe("F-023 saved Contract");

  // Existing Guided/Readiness entry points remain reachable after editor use.
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
  const readiness = await (await readinessResponse).json();
  expect(readiness.status).toBe("ready");
  await expect(
    page
      .getByRole("region", { name: "模型运行就绪检查" })
      .getByTestId("provider-readiness-result"),
  ).toContainText("READY");

  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);

});

test("390×844 supports Visual edit → Preview → Save without page overflow", async ({
  page,
}) => {
  const evidence = observeContractEditorHealth(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await openContractEditor(page);
  await expectNoPageOverflow(page);
  await enterVisualDraft(page);
  await expectNoPageOverflow(page);

  await previewAndSave(page, "F-023 mobile Contract");
  await expectNoPageOverflow(page);
  await expect(page.getByTestId("security-contract-editor")).toBeVisible();
  expect(evidence.previewPosts).toBe(1);
  expect(evidence.contractPuts).toBe(1);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});
