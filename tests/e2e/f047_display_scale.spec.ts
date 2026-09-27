import { expect, test } from "@playwright/test";

function apiPath(url: string): string {
  return new URL(url).pathname;
}

test("F-047 defaults to large display, persists the explicit choice, and never starts work", async ({
  page,
}) => {
  const postPaths: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST") {
      postPaths.push(apiPath(request.url()));
    }
  });

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");

  const standard = page.getByTestId("display-scale-standard");
  const large = page.getByTestId("display-scale-large");
  await expect(large).toHaveAttribute("aria-pressed", "true");
  await expect(standard).toHaveAttribute("aria-pressed", "false");

  const largeMetrics = await page.evaluate(() => ({
    zoom: getComputedStyle(document.documentElement).zoom,
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
    navLabelHeight: document
      .querySelector<HTMLElement>(".workspace-nav-copy strong")
      ?.getBoundingClientRect().height,
  }));
  expect(largeMetrics.zoom).toBe("1.2");
  expect(largeMetrics.document).toBeLessThanOrEqual(largeMetrics.viewport);
  expect(largeMetrics.body).toBeLessThanOrEqual(largeMetrics.viewport);

  await standard.click();
  await expect(standard).toHaveAttribute("aria-pressed", "true");
  const standardMetrics = await page.evaluate(() => ({
    zoom: getComputedStyle(document.documentElement).zoom,
    navLabelHeight: document
      .querySelector<HTMLElement>(".workspace-nav-copy strong")
      ?.getBoundingClientRect().height,
    stored: window.localStorage.getItem("agent-audit.display-scale"),
  }));
  expect(standardMetrics.zoom).toBe("1");
  expect(standardMetrics.stored).toBe("standard");
  expect(largeMetrics.navLabelHeight ?? 0).toBeGreaterThan(standardMetrics.navLabelHeight ?? 0);

  await page.reload();
  await expect(standard).toHaveAttribute("aria-pressed", "true");
  await large.click();
  await expect(large).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(large).toHaveAttribute("aria-pressed", "true");
  expect(postPaths).toEqual([]);
});

test("F-047 keeps the narrow layout unscaled and free of page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByTestId("display-scale-large")).toHaveAttribute("aria-pressed", "true");

  const metrics = await page.evaluate(() => ({
    zoom: getComputedStyle(document.documentElement).zoom,
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
    body: document.body.scrollWidth,
  }));
  expect(metrics.zoom).toBe("1");
  expect(metrics.document).toBeLessThanOrEqual(metrics.viewport);
  expect(metrics.body).toBeLessThanOrEqual(metrics.viewport);
});

test("F-058 keeps display scale available after scrolling to connection setup", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto("/");

  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

  const topbar = page.locator(".topbar");
  await expect(topbar).toBeVisible();
  await expect(page.getByTestId("display-scale-standard")).toBeVisible();
  await expect(page.getByTestId("display-scale-large")).toBeVisible();
  await expect.poll(async () => Math.round((await topbar.boundingBox())?.y ?? -1)).toBe(0);
});
