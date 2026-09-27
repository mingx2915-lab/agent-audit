import { expect, type Page } from "@playwright/test";
import { test } from "./support/test";
import {
  chooseOnboardingPath,
  installConfiguredProviderState,
  installSyntheticCatalogView,
} from "./support/first_use";

type ImportRequests = {
  catalogGets: number;
  previewPosts: number;
  commitPosts: number;
  apiNon2xx: string[];
  pageErrors: string[];
  consoleErrors: string[];
  requestFailures: string[];
};

type PickerWindow = Window & {
  __AGENT_AUDIT_DOCUMENT_PICKER__?: {
    selectDocumentFiles: () => Promise<unknown[]>;
    selectDocumentFolder: () => Promise<unknown[]>;
  };
  __AGENT_AUDIT_DOCUMENT_PICKER_CALLS__?: number;
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function observeImportRequests(page: Page): ImportRequests {
  const evidence: ImportRequests = {
    catalogGets: 0,
    previewPosts: 0,
    commitPosts: 0,
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
    if (request.method() === "GET" && path === "/api/workspace/documents") {
      evidence.catalogGets += 1;
    } else if (request.method() === "POST" && path === "/api/document-imports/previews") {
      evidence.previewPosts += 1;
    } else if (request.method() === "POST" && path === "/api/document-imports") {
      evidence.commitPosts += 1;
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

async function installFilePicker(page: Page, sourceId: string): Promise<void> {
  await page.addInitScript(({ sourceId: configuredSourceId }) => {
    const content = "本地 Workspace 导入资料：明确选择、Preview 后才会写入。";
    const source = {
      sourceId: configuredSourceId,
      displayName: "e2e-import-guidance.md",
      relativePath: "selected/e2e-import-guidance.md",
      extension: ".md",
      sizeBytes: new TextEncoder().encode(content).length,
      content,
      diagnostic: null,
    };
    (window as PickerWindow).__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ = 0;
    (window as PickerWindow).__AGENT_AUDIT_DOCUMENT_PICKER__ = {
      selectDocumentFiles: async () => {
        const target = window as PickerWindow;
        target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ =
          (target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0) + 1;
        return [source];
      },
      selectDocumentFolder: async () => {
        const target = window as PickerWindow;
        target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ =
          (target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0) + 1;
        return [source];
      },
    };
  }, { sourceId });
}

async function installFolderPicker(page: Page, sourceId: string): Promise<void> {
  await page.addInitScript(({ sourceId: configuredSourceId }) => {
    const content = "文件夹选择取消不会修改本地 Workspace。";
    const source = {
      sourceId: configuredSourceId,
      displayName: "e2e-folder-note.txt",
      relativePath: "selected/e2e-folder-note.txt",
      extension: ".txt",
      sizeBytes: new TextEncoder().encode(content).length,
      content,
      diagnostic: null,
    };
    (window as PickerWindow).__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ = 0;
    (window as PickerWindow).__AGENT_AUDIT_DOCUMENT_PICKER__ = {
      selectDocumentFiles: async () => {
        const target = window as PickerWindow;
        target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ =
          (target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0) + 1;
        return [source];
      },
      selectDocumentFolder: async () => {
        const target = window as PickerWindow;
        target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ =
          (target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0) + 1;
        return [source];
      },
    };
  }, { sourceId });
}

async function pickerCalls(page: Page): Promise<number> {
  return page.evaluate(
    () => (window as PickerWindow).__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0,
  );
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

async function waitForCatalog(page: Page): Promise<Record<string, any>> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/workspace/documents" &&
      response.ok(),
  );
  await installConfiguredProviderState(page);
  await installSyntheticCatalogView(page);
  await page.goto("/");
  await chooseOnboardingPath(page, "custom");
  const response = await responsePromise;
  return (await response.json()) as Record<string, any>;
}

test("first-use paths keep core audit and document preparation explicit at 1920px", async ({
  page,
}) => {
  const evidence = observeImportRequests(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installConfiguredProviderState(page);
  await installSyntheticCatalogView(page);
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  const coreAudit = page.locator(".guided-audit-flow");
  await expect(coreAudit).toBeVisible();
  await expect(page.getByTestId("guided-start-scan")).toHaveClass(/guided-start/);
  await expect(page.getByTestId("document-import")).toHaveCount(0);
  const coreAuditBox = await coreAudit.boundingBox();
  expect(coreAuditBox).not.toBeNull();

  await page.getByTestId("onboarding-reset").click();
  const catalogResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/workspace/documents" &&
      response.ok(),
  );
  await chooseOnboardingPath(page, "custom");
  await catalogResponse;
  const preparation = page.getByTestId("document-import");
  const summaryCard = preparation.locator(".document-import-card");
  await expect(preparation).toBeVisible();
  await expect(summaryCard).toBeVisible();
  await expect(page.locator(".guided-audit-flow")).toHaveCount(0);
  const preparationBox = await preparation.boundingBox();
  const summaryBox = await summaryCard.boundingBox();
  expect(preparationBox).not.toBeNull();
  expect(summaryBox).not.toBeNull();
  expect(preparationBox?.width ?? 0).toBeGreaterThan(0);
  expect(summaryBox?.height ?? Number.POSITIVE_INFINITY).toBeLessThan(160);
  await expect(page.getByTestId("document-import-open")).toBeVisible();
  expect(evidence.catalogGets).toBe(1);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.commitPosts).toBe(0);
  await expectNoPageOverflow(page);
});

test("file import stays explicit: GET → metadata → Preview → stale refresh → commit", async ({
  page,
}) => {
  const evidence = observeImportRequests(page);
  await installFilePicker(page, "e2e-import-guidance-001");

  const initialCatalog = await waitForCatalog(page);
  await expect(page.getByTestId("document-import-summary")).toBeVisible();
  await expect(page.getByTestId("document-import-open")).toBeVisible();
  await expect(page.getByTestId("document-import-preview")).toHaveCount(0);
  expect(evidence.catalogGets).toBe(1);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.commitPosts).toBe(0);
  expect(await pickerCalls(page)).toBe(0);
  await expectNoPageOverflow(page);

  await page.getByTestId("document-import-open").click();
  await expect(page.getByTestId("document-catalog")).toBeVisible();
  await page.getByTestId("document-import-files").click();
  await expect(page.getByTestId("document-import-item")).toHaveCount(1);
  expect(await pickerCalls(page)).toBe(1);

  const titleInput = page.getByLabel("资料标题");
  await titleInput.fill("E2E imported guidance");
  const metadataConfirmation = page.getByTestId("document-import-metadata-confirmed");
  const previewButton = page.getByTestId("document-import-preview-submit");
  const commitButton = page.getByTestId("document-import-confirm");
  await expect(previewButton).toBeDisabled();
  await metadataConfirmation.click();
  await expect(previewButton).toBeEnabled();

  const firstPreviewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/document-imports/previews" &&
      response.ok(),
  );
  await previewButton.click();
  const firstPreview = await firstPreviewResponse;
  const firstPreviewPayload = (await firstPreview.json()) as Record<string, any>;
  expect(firstPreviewPayload.readyCount).toBe(1);
  await expect(page.getByTestId("document-import-preview")).toContainText("READY");
  await expect(commitButton).toBeEnabled();
  await expectNoPageOverflow(page);

  // Editing metadata expires the previous Preview and re-locks commit.
  await titleInput.fill("E2E imported guidance v2");
  await expect(page.getByTestId("document-import-preview-stale")).toBeVisible();
  await expect(commitButton).toBeDisabled();
  await expect(previewButton).toBeDisabled();
  await metadataConfirmation.click();

  const secondPreviewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/document-imports/previews" &&
      response.ok(),
  );
  await previewButton.click();
  await secondPreviewResponse;
  await expect(page.getByTestId("document-import-preview-stale")).toHaveCount(0);
  await expect(commitButton).toBeEnabled();
  expect(evidence.previewPosts).toBe(2);

  const commitRequestPromise = page.waitForRequest(
    (request) =>
      request.method() === "POST" && apiPath(request.url()) === "/api/document-imports",
  );
  const commitResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/document-imports" &&
      response.ok(),
  );
  const catalogAfterCommit = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/workspace/documents" &&
      response.ok(),
  );
  await commitButton.click();
  const commitRequest = await commitRequestPromise;
  const commitPayload = JSON.parse(commitRequest.postData() ?? "{}");
  expect(JSON.stringify(commitPayload)).not.toContain("C:\\");
  const commitResult = await (await commitResponse).json();
  expect(commitResult.imported).toHaveLength(1);
  await catalogAfterCommit;

  await expect(page.getByTestId("document-import-result")).toContainText("成功 1 项");
  await expect(page.getByTestId("document-import-summary")).toContainText(
    `${Number(initialCatalog.documents.length)} 份资料`,
  );
  expect(evidence.commitPosts).toBe(1);
  expect(evidence.catalogGets).toBe(2);
  await expectNoPageOverflow(page);

  // A second explicit selection can be canceled locally without another API write.
  await page.getByTestId("document-import-open").click();
  await page.getByTestId("document-import-files").click();
  await expect(page.getByTestId("document-import-item")).toHaveCount(1);
  await page.getByTestId("document-import-cancel").click();
  await expect(page.getByTestId("document-import-selection")).toHaveCount(0);
  await expect(page.getByTestId("document-import-notice")).toContainText("没有写入 Workspace");
  expect(evidence.previewPosts).toBe(2);
  expect(evidence.commitPosts).toBe(1);
  await expectNoPageOverflow(page);

  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("folder picker cancel remains local at 390×844", async ({ page }) => {
  const evidence = observeImportRequests(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await installFolderPicker(page, "e2e-folder-note-001");

  await waitForCatalog(page);
  await expect(page.getByTestId("document-import-summary")).toBeVisible();
  expect(evidence.catalogGets).toBe(1);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.commitPosts).toBe(0);
  expect(await pickerCalls(page)).toBe(0);

  await page.getByTestId("document-import-open").click();
  await page.getByTestId("document-import-folder").click();
  await expect(page.getByTestId("document-import-item")).toHaveCount(1);
  expect(await pickerCalls(page)).toBe(1);
  await page.getByTestId("document-import-cancel").click();
  await expect(page.getByTestId("document-import-selection")).toHaveCount(0);
  await expect(page.getByTestId("document-import-notice")).toContainText("没有写入 Workspace");
  await expectNoPageOverflow(page);

  expect(evidence.catalogGets).toBe(1);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.commitPosts).toBe(0);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});
