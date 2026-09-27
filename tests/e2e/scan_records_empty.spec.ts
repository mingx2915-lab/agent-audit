import { expect, test, type Page } from "@playwright/test";

function apiPath(url: string): string {
  return new URL(url).pathname;
}

async function openEmptyScanRecords(page: Page): Promise<void> {
  // This is a UI-only empty-state fixture. Other E2E specs intentionally persist
  // real scans in the shared test server, so only the read response is isolated;
  // no production action or write response is mocked here.
  await page.route("**/api/scans?limit=20", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    });
  });

  const historyResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.goto("/");
  await historyResponse;
  await page.getByRole("button", { name: "扫描记录", exact: true }).click();
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

test("F-046 presents one actionable empty Scan Records workspace without starting work", async ({
  page,
}) => {
  const postPaths: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST") {
      postPaths.push(apiPath(request.url()));
    }
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await openEmptyScanRecords(page);

  await expect(page.getByTestId("workspace-live")).toBeVisible();
  await expect(page.getByTestId("scan-history")).toBeVisible();
  await expect(page.getByTestId("scan-records-empty")).toHaveCount(1);
  await expect(page.getByText("扫描 Scan", { exact: true })).toBeVisible();
  await expect(page.getByText("尝试 Attempt", { exact: true })).toBeVisible();
  await expect(page.getByText("证据 Trace", { exact: true })).toBeVisible();
  await expect(page.getByText("风险 Finding", { exact: true })).toBeVisible();
  await expect(page.locator(".el-empty")).toHaveCount(0);
  expect(postPaths).toEqual([]);

  const refreshResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("scan-empty-refresh").click();
  await refreshResponse;
  expect(postPaths).toEqual([]);

  await page.getByTestId("scan-empty-start").click();
  await expect(page.getByTestId("workspace-guided")).toBeVisible();
  expect(postPaths).toEqual([]);
});

test("F-046 keeps the compact Scan Records task legible at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openEmptyScanRecords(page);

  await expect(page.getByTestId("scan-records-empty")).toBeVisible();
  expect((await page.getByTestId("scan-empty-start").boundingBox())?.width ?? 0).toBeGreaterThan(250);
  await expectNoPageOverflow(page);
});
