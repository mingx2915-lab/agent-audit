import { expect, test, type Page } from "@playwright/test";

type WorkspaceRequests = {
  summaryGets: number;
  backupGets: number;
  previewPosts: number;
  restorePosts: number;
  activationPreparationPosts: number;
  activationEvents: string[];
  apiNon2xx: string[];
  pageErrors: string[];
  consoleErrors: string[];
  requestFailures: string[];
};

type BackupTransportState = {
  saveCalls: number;
  selectCalls: number;
  activateCalls: number;
  savedBytes: number;
  suggestedNames: string[];
  activatedDirectories: string[];
};

type BackupWindow = Window & {
  __AGENT_AUDIT_WORKSPACE_BACKUP__?: {
    saveWorkspaceBackup: (bytes: Uint8Array, suggestedName: string) => Promise<boolean>;
    selectWorkspaceBackup: () => Promise<Uint8Array | null>;
    activateWorkspace: (relativeDirectory: string) => Promise<void>;
  };
  __AGENT_AUDIT_WORKSPACE_BACKUP_STATE__?: BackupTransportState;
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function observeWorkspaceRequests(page: Page): WorkspaceRequests {
  const evidence: WorkspaceRequests = {
    summaryGets: 0,
    backupGets: 0,
    previewPosts: 0,
    restorePosts: 0,
    activationPreparationPosts: 0,
    activationEvents: [],
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
    if (request.method() === "GET" && path === "/api/workspace") {
      evidence.summaryGets += 1;
    } else if (request.method() === "GET" && path === "/api/workspace/backups/current") {
      evidence.backupGets += 1;
    } else if (request.method() === "POST" && path === "/api/workspace/backups/previews") {
      evidence.previewPosts += 1;
    } else if (request.method() === "POST" && path === "/api/workspace/restores") {
      evidence.restorePosts += 1;
    } else if (
      request.method() === "POST" &&
      path === "/api/workspace/activation-preparations"
    ) {
      evidence.activationPreparationPosts += 1;
      evidence.activationEvents.push("prepare-request");
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

async function installBackupTransport(
  page: Page,
  options: { selectReturnsSavedBytes: boolean },
): Promise<void> {
  await page.addInitScript(({ selectReturnsSavedBytes }) => {
    const state: BackupTransportState = {
      saveCalls: 0,
      selectCalls: 0,
      activateCalls: 0,
      savedBytes: 0,
      suggestedNames: [],
      activatedDirectories: [],
    };
    let savedArchive: number[] = [];
    const target = window as BackupWindow;
    target.__AGENT_AUDIT_WORKSPACE_BACKUP_STATE__ = state;
    target.__AGENT_AUDIT_WORKSPACE_BACKUP__ = {
      saveWorkspaceBackup: async (bytes, suggestedName) => {
        state.saveCalls += 1;
        state.savedBytes = bytes.byteLength;
        state.suggestedNames.push(suggestedName);
        savedArchive = Array.from(bytes);
        return true;
      },
      selectWorkspaceBackup: async () => {
        state.selectCalls += 1;
        return selectReturnsSavedBytes ? new Uint8Array(savedArchive) : null;
      },
      activateWorkspace: async (relativeDirectory) => {
        state.activateCalls += 1;
        state.activatedDirectories.push(relativeDirectory);
        document.documentElement.dataset.workspaceActivationEvent = "native-invoke";
      },
    };
  }, options);
}

async function openWorkspaceOperations(page: Page): Promise<void> {
  const workspaceResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/workspace" &&
      response.ok(),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "设置与计划", exact: true }).click();
  await workspaceResponse;
  await expect(page.getByTestId("workspace-operations")).toBeVisible();
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

async function transportState(page: Page): Promise<BackupTransportState> {
  return page.evaluate(() => {
    const state = (window as BackupWindow).__AGENT_AUDIT_WORKSPACE_BACKUP_STATE__;
    if (!state) {
      throw new Error("workspace backup transport state is unavailable");
    }
    return state;
  });
}

test("桌面 Workspace 备份链路保持真实 API：保存→选择→Preview→恢复→激活", async ({
  page,
}) => {
  const evidence = observeWorkspaceRequests(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await installBackupTransport(page, { selectReturnsSavedBytes: true });
  await openWorkspaceOperations(page);

  const operations = page.getByTestId("workspace-operations");
  await expect(operations.getByTestId("workspace-operations-summary")).toContainText(
    "当前：",
  );
  expect(evidence.summaryGets).toBe(1);
  expect(evidence.backupGets).toBe(0);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.restorePosts).toBe(0);
  await expectNoPageOverflow(page);

  await operations.getByTestId("workspace-operations-open").click();
  const backupResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/workspace/backups/current" &&
      response.ok(),
  );
  await operations.getByTestId("workspace-backup-save").click();
  await backupResponse;
  await expect(operations.getByTestId("workspace-operations-notice")).toContainText(
    "备份已保存",
  );
  expect(evidence.backupGets).toBe(1);
  const saved = await transportState(page);
  expect(saved.saveCalls).toBe(1);
  expect(saved.savedBytes).toBeGreaterThan(0);
  expect(saved.suggestedNames[0]).toMatch(/^agent-audit-workspace-\d{4}-\d{2}-\d{2}\.zip$/);

  const previewResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/workspace/backups/previews" &&
      response.ok(),
  );
  await operations.getByTestId("workspace-backup-select").click();
  const preview = await (await previewResponse).json();
  expect(preview.formatVersion).toBe(1);
  expect(preview.workspace.active).toBe(false);
  await expect(operations.getByTestId("workspace-backup-preview")).toBeVisible();
  expect(evidence.previewPosts).toBe(1);
  expect(evidence.restorePosts).toBe(0);
  await expectNoPageOverflow(page);

  const restoreResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/workspace/restores" &&
      response.ok(),
  );
  await operations.getByTestId("workspace-backup-restore").click();
  const restored = await (await restoreResponse).json();
  expect(restored.restored).toBe(true);
  expect(restored.restartRequired).toBe(true);
  expect(restored.workspace.active).toBe(false);
  expect(restored.workspace.relativeDirectory).toMatch(/^restored-[^/\\]+$/);
  await expect(operations.getByTestId("workspace-restore-result")).toBeVisible();
  expect(evidence.restorePosts).toBe(1);

  await operations.getByTestId("workspace-activate").click();
  await expect(operations.getByTestId("workspace-operations-notice")).toContainText(
    "请在桌面窗口中重新加载以切换",
  );
  const activated = await transportState(page);
  expect(activated.selectCalls).toBe(1);
  expect(activated.activateCalls).toBe(1);
  expect(evidence.activationPreparationPosts).toBe(1);
  expect(evidence.activationEvents).toEqual(["prepare-request"]);
  expect(
    await page.evaluate(() => document.documentElement.dataset.workspaceActivationEvent),
  ).toBe("native-invoke");
  expect(activated.activatedDirectories).toEqual([restored.workspace.relativeDirectory]);
  expect(evidence.backupGets).toBe(1);
  expect(evidence.previewPosts).toBe(1);
  expect(evidence.restorePosts).toBe(1);
  await expectNoPageOverflow(page);

  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});

test("取消选择只停留在本地，不触发 Preview 或恢复写入", async ({ page }) => {
  const evidence = observeWorkspaceRequests(page);
  await installBackupTransport(page, { selectReturnsSavedBytes: false });
  await openWorkspaceOperations(page);
  const operations = page.getByTestId("workspace-operations");
  await operations.getByTestId("workspace-operations-open").click();

  await operations.getByTestId("workspace-backup-select").click();
  await expect(operations.getByTestId("workspace-operations-notice")).toContainText(
    "已取消选择",
  );
  expect(evidence.backupGets).toBe(0);
  expect(evidence.previewPosts).toBe(0);
  expect(evidence.restorePosts).toBe(0);
  await operations.getByTestId("workspace-backup-cancel").click();
  await expect(operations.getByTestId("workspace-operations-notice")).toContainText(
    "没有写入 Workspace",
  );
  const canceled = await transportState(page);
  expect(canceled.selectCalls).toBe(1);
  expect(canceled.activateCalls).toBe(0);
  await expectNoPageOverflow(page);

  expect(evidence.apiNon2xx).toEqual([]);
  expect(evidence.pageErrors).toEqual([]);
  expect(evidence.consoleErrors).toEqual([]);
  expect(evidence.requestFailures).toEqual([]);
});
