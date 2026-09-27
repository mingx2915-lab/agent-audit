import { expect } from "@playwright/test";
import { test } from "./support/test";


test("preview is read-only and browser export is an explicit local download", async ({ page }) => {
  const methods: string[] = [];
  const nonLoopback: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/diagnostics/")) methods.push(`${request.method()} ${url.pathname}`);
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) nonLoopback.push(request.url());
  });

  await page.goto("/");
  await page.getByRole("button", { name: "设置与计划" }).click();
  const view = page.getByTestId("local-diagnostics");
  await expect(view).toBeVisible();
  await expect(view).toContainText("将包含");
  await expect(view).toContainText("明确排除");
  await expect(view).toContainText("凭据与环境变量中的 Secret");
  await expect(view).toContainText("全程本地处理·不上传");
  await expect(view).toContainText("仅供运维排障");
  await expect(view).toContainText("不构成根因判断");
  await expect.poll(() => methods).toEqual(["GET /api/diagnostics/preview"]);

  const downloadPromise = page.waitForEvent("download");
  await page.getByTestId("diagnostics-export").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^agent-audit-diagnostics-\d{8}T\d{6}Z\.zip$/);
  await expect(page.getByTestId("diagnostics-notice")).toContainText("浏览器下载");
  expect(methods).toEqual([
    "GET /api/diagnostics/preview",
    "POST /api/diagnostics/export",
  ]);
  expect(nonLoopback).toEqual([]);
});


test("desktop cancel reports no write and narrow viewport has no overflow", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "__AGENT_AUDIT_DIAGNOSTICS__", {
      value: {
        saveDiagnosticsArchive: async () => false,
      },
      configurable: true,
    });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  let exportPosts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/diagnostics/export") {
      exportPosts += 1;
    }
  });
  await page.goto("/");
  await page.evaluate(() => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { value: {}, configurable: true });
  });
  await page.getByRole("button", { name: "设置与计划" }).click();
  await page.getByTestId("diagnostics-export").click();
  await expect(page.getByTestId("diagnostics-notice")).toContainText("已取消保存；没有写入诊断包");
  expect(exportPosts).toBe(1);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
