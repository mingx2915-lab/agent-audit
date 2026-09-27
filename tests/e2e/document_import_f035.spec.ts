import { expect, test, type Locator, type Page } from "@playwright/test";
import {
  chooseOnboardingPath,
  installConfiguredProviderState,
  installSyntheticCatalogView,
} from "./support/first_use";

type ImportedSource = {
  sourceId: string;
  displayName: string;
  relativePath: string;
  extension: string;
  sizeBytes: number;
  content: string | null;
  diagnostic: string | null;
  status: "ready" | "unsupported" | "invalid";
  diagnosticCode?: string | null;
};

type PickerWindow = Window & {
  /** Explicit Test-only seam; this is not evidence of a system dialog. */
  __AGENT_AUDIT_DOCUMENT_PICKER__?: {
    selectDocumentFiles: () => Promise<ImportedSource[]>;
    selectDocumentFolder: () => Promise<ImportedSource[]>;
  };
  __AGENT_AUDIT_DOCUMENT_PICKER_CALLS__?: number;
};

type BrowserEvidence = {
  scanPosts: number;
  previewPosts: number;
  commitPosts: number;
  readinessPosts: number;
  assistantPosts: number;
  apiNon2xx: string[];
  pageErrors: string[];
  consoleErrors: string[];
  requestFailures: string[];
};

type AttackPlanSummary = {
  id: string;
  name: string;
  basisType: string;
  targetId: string;
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function observeBrowserHealth(page: Page): BrowserEvidence {
  const evidence: BrowserEvidence = {
    scanPosts: 0,
    previewPosts: 0,
    commitPosts: 0,
    readinessPosts: 0,
    assistantPosts: 0,
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
    if (request.method() !== "POST") {
      return;
    }
    if (path === "/api/document-imports/previews") {
      evidence.previewPosts += 1;
    } else if (path === "/api/document-imports") {
      evidence.commitPosts += 1;
    } else if (path === "/api/scans") {
      evidence.scanPosts += 1;
    } else if (path === "/api/provider-readiness") {
      evidence.readinessPosts += 1;
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

function mixedSources(): ImportedSource[] {
  return [
    {
      sourceId: "f035-pdf-001",
      displayName: "finance-budget.pdf",
      relativePath: "approved/finance-budget.pdf",
      extension: ".pdf",
      sizeBytes: 4_096,
      content: "F-035 PDF normalized finance budget marker",
      diagnostic: null,
      status: "ready",
    },
    {
      sourceId: "f035-docx-001",
      displayName: "employee-guide.docx",
      relativePath: "approved/employee-guide.docx",
      extension: ".docx",
      sizeBytes: 8_192,
      content: "F-035 DOCX normalized employee guide marker",
      diagnostic: null,
      status: "ready",
    },
    {
      sourceId: "f035-txt-001",
      displayName: "support-note.txt",
      relativePath: "approved/support-note.txt",
      extension: ".txt",
      sizeBytes: new TextEncoder().encode("F-035 TXT support note marker").length,
      content: "F-035 TXT support note marker",
      diagnostic: null,
      status: "ready",
    },
    {
      sourceId: "f035-md-001",
      displayName: "product-faq.md",
      relativePath: "approved/product-faq.md",
      extension: ".md",
      sizeBytes: new TextEncoder().encode("# F-035 MD FAQ marker").length,
      content: "# F-035 MD FAQ marker",
      diagnostic: null,
      status: "ready",
    },
    {
      sourceId: "f035-unrelated-001",
      displayName: "thumbnail.png",
      relativePath: "approved/thumbnail.png",
      extension: ".png",
      sizeBytes: 1_024,
      content: null,
      diagnostic: "当前版本不支持此文件格式",
      status: "unsupported",
      diagnosticCode: "unsupported_format",
    },
  ];
}

async function installMixedFolderPicker(page: Page): Promise<void> {
  await page.addInitScript(({ configuredSources }) => {
    // This deterministic browser seam stands in for a selected result only;
    // it must never be described as proof that the OS dialog opened.
    const sources = configuredSources;
    const target = window as PickerWindow;
    target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ = 0;
    target.__AGENT_AUDIT_DOCUMENT_PICKER__ = {
      selectDocumentFiles: async () => {
        target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ =
          (target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0) + 1;
        return sources;
      },
      selectDocumentFolder: async () => {
        target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ =
          (target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0) + 1;
        return sources;
      },
    };
  }, { configuredSources: mixedSources() });
}

async function installStringErrorPicker(page: Page): Promise<void> {
  await page.addInitScript(() => {
    // Explicit Test-only transport for the native boundary error path.  It is
    // intentionally not a replacement for a real OS file-dialog smoke test.
    const target = window as PickerWindow;
    target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ = 0;
    target.__AGENT_AUDIT_DOCUMENT_PICKER__ = {
      selectDocumentFiles: async () => {
        target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ =
          (target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0) + 1;
        throw "拒绝访问：所选资料文件夹没有读取权限（synthetic picker error）";
      },
      selectDocumentFolder: async () => {
        target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ =
          (target.__AGENT_AUDIT_DOCUMENT_PICKER_CALLS__ ?? 0) + 1;
        throw "拒绝访问：所选资料文件夹没有读取权限（synthetic picker error）";
      },
    };
  });
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

async function chooseElementPlusOption(page: Page, label: string): Promise<void> {
  await page
    .locator(".el-select-dropdown__item:visible")
    .filter({ hasText: label })
    .first()
    .click();
}

async function openElementPlusSelect(container: Locator, label: string): Promise<void> {
  await container
    .getByLabel(label, { exact: true })
    .locator("xpath=ancestor::div[contains(@class, 'el-select__wrapper')]")
    .click();
}

test("F-035 custom path imports a mixed folder and enters a real Contract Plan", async ({
  page,
}) => {
  const evidence = observeBrowserHealth(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await installMixedFolderPicker(page);
  await installConfiguredProviderState(page);

  await page.goto("/");
  await expect(page.getByTestId("enterprise-onboarding")).toBeVisible();
  await expect(page.getByTestId("onboarding-choices")).toBeVisible();
  expect(evidence.scanPosts).toBe(0);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.commitPosts).toBe(0);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.assistantPosts).toBe(0);
  expect(await pickerCalls(page)).toBe(0);
  await expectNoPageOverflow(page);

  const initialCatalogResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/workspace/documents" &&
      response.ok(),
  );
  await page.getByTestId("onboarding-custom").click();
  const initialCatalogResponse = await initialCatalogResponsePromise;
  const initialCatalog = (await initialCatalogResponse.json()) as {
    documents: Array<{ labels: string[] }>;
  };
  expect(initialCatalog.documents.length).toBeGreaterThan(0);
  const seedOnlyCatalog = initialCatalog.documents.every(
    (document) =>
      document.labels.includes("SYNTHETIC") && document.labels.includes("DEMO ONLY"),
  );
  if (seedOnlyCatalog) {
    // This is the fresh-server evidence: the bundled catalog is visibly
    // synthetic/demo-only and cannot count as a user's connected knowledge.
    expect(
      initialCatalog.documents.every(
        (document) =>
          document.labels.includes("SYNTHETIC") && document.labels.includes("DEMO ONLY"),
      ),
    ).toBe(true);
  } else {
    expect(
      initialCatalog.documents.some(
        (document) =>
          !document.labels.includes("SYNTHETIC") || !document.labels.includes("DEMO ONLY"),
      ),
    ).toBe(true);
  }
  // Selecting a path is presentation only; no model, scan, or file picker
  // action may happen before the user clicks the next explicit operation.
  await expect(page.getByTestId("onboarding-path")).toContainText("验收我的知识助手");
  // Seed documents are explicitly demo-only and must not satisfy the custom
  // path's real-document step before this Commit.
  if (seedOnlyCatalog) {
    await expect(page.getByTestId("onboarding-step-documents")).toBeVisible();
    await expect(
      page.locator(".enterprise-onboarding-step").filter({ hasText: "选择首次检查" }),
    ).toBeVisible();
    await expect(page.getByTestId("onboarding-path")).not.toContainText(
      "已完成一次真实 Trace 验收",
    );
  } else {
    // The full suite may have imported a real document in an earlier browser
    // test.  In that legitimate persisted state the step is already complete,
    // and the component must report the real count rather than seed metadata.
    await expect(page.getByTestId("onboarding-step-documents")).toHaveCount(0);
    await expect(page.getByTestId("onboarding-path")).toContainText("当前 Workspace 有");
  }
  expect(evidence.scanPosts).toBe(0);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.assistantPosts).toBe(0);
  expect(await pickerCalls(page)).toBe(0);

  await page.getByTestId("document-import-open").click();
  await page.getByTestId("document-import-folder").click();
  await expect(page.getByTestId("document-import-item")).toHaveCount(5);
  expect(await pickerCalls(page)).toBe(1);
  await expect(page.getByTestId("document-import-selection")).toContainText("5 项资料");
  await expectNoPageOverflow(page);

  const batchControls = page.getByTestId("document-import-batch-controls");
  await openElementPlusSelect(batchControls, "批量资料类别");
  await chooseElementPlusOption(page, "财务 Finance");
  await batchControls.getByRole("button", { name: "应用类别", exact: true }).click();
  await openElementPlusSelect(batchControls, "批量敏感等级");
  await chooseElementPlusOption(page, "机密 Confidential");
  await batchControls.getByRole("button", { name: "应用等级", exact: true }).click();

  // The second supported item is the explicit exception to the batch scope.
  const exceptionItem = page.getByTestId("document-import-item").nth(1);
  await openElementPlusSelect(exceptionItem, "资料业务范围");
  await chooseElementPlusOption(page, "通用 General");
  await expect(exceptionItem).toContainText("employee-guide.docx");
  await page.getByTestId("document-import-metadata-confirmed").click();

  const previewResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/document-imports/previews" &&
      response.ok(),
  );
  await page.getByTestId("document-import-preview-submit").click();
  const previewResponse = await previewResponsePromise;
  const preview = (await previewResponse.json()) as {
    items: Array<{ sourceId: string; status: string; diagnosticCode?: string | null }>;
    readyCount: number;
    skippedCount: number;
    planDiagnostic: string | null;
    executablePlans: AttackPlanSummary[];
  };
  expect(preview.readyCount).toBe(4);
  expect(preview.skippedCount).toBe(1);
  expect(preview.items.map((item) => item.status)).toEqual([
    "ready",
    "ready",
    "ready",
    "ready",
    "unsupported",
  ]);
  expect(preview.items[4]?.diagnosticCode).toBe("unsupported_format");
  expect(preview.planDiagnostic).toBeNull();
  expect(preview.executablePlans.length).toBeGreaterThan(0);
  expect(preview.executablePlans.every((plan) => !plan.targetId.startsWith("preview_"))).toBe(
    true,
  );
  await expect(page.getByTestId("document-import-preview")).toContainText("4 ready");
  await expect(page.getByTestId("document-import-preview")).toContainText("1 skipped");
  await expectNoPageOverflow(page);

  const commitRequestPromise = page.waitForRequest(
    (request) =>
      request.method() === "POST" && apiPath(request.url()) === "/api/document-imports",
  );
  const commitResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/document-imports" &&
      response.ok(),
  );
  const catalogResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/workspace/documents" &&
      response.ok(),
  );
  await page.getByTestId("document-import-confirm").click();
  const commitRequest = await commitRequestPromise;
  const commitPayload = JSON.parse(commitRequest.postData() ?? "{}");
  const submitted = commitPayload.documents as Array<{
    source: ImportedSource;
    metadata: { businessScope: string; sensitivity: string };
  }>;
  expect(submitted).toHaveLength(5);
  expect(submitted.some((draft) => draft.source.extension === ".png")).toBe(true);
  expect(submitted.filter((draft) => draft.metadata.businessScope === "finance")).toHaveLength(4);
  expect(
    submitted.find((draft) => draft.source.sourceId === "f035-docx-001")?.metadata.businessScope,
  ).toBe("general");
  expect(JSON.stringify(commitPayload)).not.toMatch(/[A-Za-z]:[\\/]/);
  expect(JSON.stringify(commitPayload)).not.toContain("\\\\");

  const commitResponse = await commitResponsePromise;
  const result = (await commitResponse.json()) as {
    imported: Array<{ id: string; labels: string[] }>;
    skipped: Array<{ sourceId: string; status: string; diagnosticCode?: string }>;
    retriever: { indexedDocumentCount: number };
    executablePlans: AttackPlanSummary[];
    planDiagnostic: string | null;
  };
  await catalogResponsePromise;
  expect(result.imported).toHaveLength(4);
  expect(result.skipped).toEqual([
    expect.objectContaining({
      sourceId: "f035-unrelated-001",
      status: "unsupported",
      diagnosticCode: "unsupported_format",
    }),
  ]);
  expect(result.retriever.indexedDocumentCount).toBeGreaterThan(0);
  expect(result.planDiagnostic).toBeNull();
  expect(result.executablePlans.length).toBeGreaterThan(0);
  expect(
    result.imported.every(
      (document: { labels: string[] }) =>
        !document.labels.includes("SYNTHETIC") && !document.labels.includes("DEMO ONLY"),
    ),
  ).toBe(true);
  const activePlans = (await page.evaluate(async () => {
    const response = await fetch("/api/attack-plans");
    if (!response.ok) {
      throw new Error(`attack plan lookup failed: ${response.status}`);
    }
    return response.json();
  })) as AttackPlanSummary[];
  const activePlanById = new Map(activePlans.map((plan) => [plan.id, plan]));
  for (const plan of result.executablePlans) {
    expect(activePlanById.get(plan.id)).toEqual(expect.objectContaining(plan));
  }
  const sourceSinkPlan = result.executablePlans.find(
    (plan) => plan.basisType === "source_sink",
  );
  expect(sourceSinkPlan).toBeDefined();
  if (!sourceSinkPlan) {
    throw new Error("Commit did not return a source_sink Contract-derived Plan");
  }

  // A successful Commit updates the real Workspace catalog.  The production
  // first-use gate therefore advances from the document body to the guided
  // audit body; continue through that explicit user-facing action.
  await expect(page.getByTestId("workspace-guided")).toBeVisible();
  await expect(page.getByTestId("guided-plan")).toContainText(sourceSinkPlan.name);
  const scanRequestPromise = page.waitForRequest(
    (request) => request.method() === "POST" && apiPath(request.url()) === "/api/scans",
  );
  const scanResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("guided-start-scan").click();
  const scanRequest = await scanRequestPromise;
  expect(JSON.parse(scanRequest.postData() ?? "{}")).toEqual(
    expect.objectContaining({ planId: sourceSinkPlan.id }),
  );
  const scan = (await scanResponsePromise.then((response) => response.json())) as {
    planId: string;
    attempts: Array<{ queryResult: { traceEvents: Array<{ details: Record<string, unknown> }> } }>;
  };
  expect(scan.planId).toBe(sourceSinkPlan.id);
  expect(scan.attempts.length).toBeGreaterThan(0);
  expect(JSON.stringify(scan)).not.toMatch(/[A-Za-z]:[\\/]/);
  await expect(page.getByTestId("guided-finding-summary")).toBeVisible();
  await expectNoPageOverflow(page);

  expect(evidence.scanPosts).toBe(1);
  expect(evidence.previewPosts).toBe(1);
  expect(evidence.commitPosts).toBe(1);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.assistantPosts).toBe(0);
  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("F-035 dual entry choice is explicit and does not run external actions", async ({ page }) => {
  const evidence = observeBrowserHealth(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await installMixedFolderPicker(page);
  await page.goto("/");

  await expect(page.getByTestId("onboarding-choices")).toBeVisible();
  await expect(page.getByTestId("onboarding-demo")).toContainText("使用合成演示");
  await expect(page.getByTestId("onboarding-custom")).toContainText("验收我的知识助手");
  await page.getByTestId("onboarding-demo").click();
  await expect(page.getByTestId("onboarding-path")).toContainText("使用合成演示");
  await expect(page.getByTestId("onboarding-path")).toContainText("仓库内合成资料");
  expect(evidence.scanPosts).toBe(0);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.commitPosts).toBe(0);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.assistantPosts).toBe(0);
  expect(await pickerCalls(page)).toBe(0);

  await page.getByTestId("onboarding-reset").click();
  await page.getByTestId("onboarding-custom").click();
  await expect(page.getByTestId("onboarding-path")).toContainText("验收我的知识助手");
  expect(evidence.scanPosts).toBe(0);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.commitPosts).toBe(0);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.assistantPosts).toBe(0);
  expect(await pickerCalls(page)).toBe(0);
  await expectNoPageOverflow(page);

  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("F-035 preserves a native string error without writing Workspace", async ({ page }) => {
  const evidence = observeBrowserHealth(page);
  await installStringErrorPicker(page);
  await installConfiguredProviderState(page);
  await installSyntheticCatalogView(page);
  await page.goto("/");
  await chooseOnboardingPath(page, "custom");
  await expect(page.getByTestId("document-import")).toBeVisible();

  await page.getByTestId("document-import-open").click();
  await page.getByTestId("document-import-files").click();
  await expect(page.getByTestId("document-import-error")).toContainText(
    "拒绝访问：所选资料文件夹没有读取权限",
  );
  expect(await pickerCalls(page)).toBe(1);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.commitPosts).toBe(0);
  expect(evidence.scanPosts).toBe(0);
  expect(evidence.readinessPosts).toBe(0);
  expect(evidence.assistantPosts).toBe(0);
  await expectNoPageOverflow(page);

  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});
