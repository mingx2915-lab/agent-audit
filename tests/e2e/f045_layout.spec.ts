import { expect, test, type Page } from "@playwright/test";
import { chooseOnboardingPath, installConfiguredProviderState } from "./support/first_use";

type AttackPlan = {
  id: string;
  name: string;
  basisType: string;
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

async function loadPlans(page: Page): Promise<AttackPlan[]> {
  await installConfiguredProviderState(page);
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  return (await (await responsePromise).json()) as AttackPlan[];
}

async function openWorkspace(page: Page, name: "设置与计划" | "验收证据"): Promise<void> {
  await page.getByRole("button", { name, exact: true }).click();
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

test("F-045 uses bounded wide-screen type and aligned Plan actions without eager Replay", async ({
  page,
}) => {
  const postPaths: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST") {
      postPaths.push(apiPath(request.url()));
    }
  });

  for (const viewport of [
    { width: 1440, height: 900, expectedH2: "26px" },
    { width: 1920, height: 1080, expectedH2: "29px" },
    { width: 2560, height: 1440, expectedH2: "29px" },
  ]) {
    await page.setViewportSize(viewport);
    const plans = await loadPlans(page);
    expect(plans.length).toBeGreaterThanOrEqual(4);
    await openWorkspace(page, "设置与计划");

    const workspace = page.getByTestId("attack-plans-workspace");
    await expect(workspace).toBeVisible();
    await expect(workspace.locator("h2")).toHaveCSS("font-size", viewport.expectedH2);
    expect((await workspace.boundingBox())?.width ?? Number.POSITIVE_INFINITY).toBeLessThanOrEqual(
      1729,
    );

    const executeButtons = workspace.locator('[data-testid^="attack-plan-execute-"]');
    await expect(executeButtons).toHaveCount(plans.length);
    const buttonBoxes = await executeButtons.evaluateAll((buttons) =>
      buttons.map((button) => {
        const box = button.getBoundingClientRect();
        return {
          x: Math.round(box.x),
          bottom: Math.round(box.bottom),
          width: Math.round(box.width),
          height: Math.round(box.height),
        };
      }),
    );
    expect(new Set(buttonBoxes.map((box) => box.x)).size).toBe(2);
    expect(new Set(buttonBoxes.map((box) => box.bottom)).size).toBe(
      Math.ceil(plans.length / 2),
    );
    expect(new Set(buttonBoxes.map((box) => box.width)).size).toBe(1);
    expect(buttonBoxes.every((box) => box.height >= 44)).toBe(true);

    await expect(workspace.locator('[data-testid^="attack-plan-replay-"]')).toHaveCount(0);
    const firstPlanSelect = workspace.getByTestId(`attack-plan-select-${plans[0]?.id}`);
    await firstPlanSelect.focus();
    await firstPlanSelect.press("ArrowDown");
    await expect(workspace.getByTestId("attack-plan-detail")).toContainText(plans[1]?.name ?? "");
    await workspace.getByTestId(`attack-plan-select-${plans.at(-1)?.id}`).click();
    await expect(workspace.getByTestId("attack-plan-detail")).toContainText(
      plans.at(-1)?.name ?? "",
    );
    expect(postPaths).toEqual([]);
  }
});

test("F-045 only reveals Plan Replay after a completed same-Plan Scan", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const plans = await loadPlans(page);
  const sourceSink = plans.find((plan) => plan.basisType === "source_sink");
  expect(sourceSink).toBeDefined();
  if (!sourceSink) {
    throw new Error("source_sink Plan is required for F-045 Replay visibility");
  }

  await expect(page.getByTestId("guided-start-scan")).toBeEnabled();
  const scanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("guided-start-scan").click();
  const scan = (await (await scanResponse).json()) as { planId: string; status: string };
  expect(scan).toMatchObject({ planId: sourceSink.id, status: "completed" });

  await openWorkspace(page, "设置与计划");
  const workspace = page.getByTestId("attack-plans-workspace");
  await expect(workspace.getByTestId(`attack-plan-replay-${sourceSink.id}`)).toBeVisible();
  await expect(workspace.locator('[data-testid^="attack-plan-replay-"]')).toHaveCount(1);
});

test("F-045 keeps Differential selection local until the explicit run and fits mobile", async ({
  page,
}) => {
  let differentialPosts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && apiPath(request.url()) === "/api/differential-audits") {
      differentialPosts += 1;
    }
  });

  await page.setViewportSize({ width: 1920, height: 1080 });
  await loadPlans(page);
  await openWorkspace(page, "验收证据");

  const workspace = page.getByTestId("differential-audit-workspace");
  await expect(workspace).toBeVisible();
  await expect(workspace.locator("h2")).toHaveCSS("font-size", "29px");
  await expect(workspace.getByTestId("differential-summary")).toBeVisible();
  await expect(workspace.getByTestId("differential-idle")).toContainText("尚无对比结果");
  expect(differentialPosts).toBe(0);

  const taskSelect = workspace.getByTestId("differential-task-select");
  const taskValues = await taskSelect.locator("option").evaluateAll((options) =>
    options.map((option) => (option as HTMLOptionElement).value),
  );
  expect(taskValues.length).toBeGreaterThan(1);
  await taskSelect.selectOption(taskValues[1] ?? taskValues[0]);
  expect(differentialPosts).toBe(0);

  const auditResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/differential-audits" &&
      response.ok(),
  );
  await workspace.getByTestId("differential-run").click();
  const audit = (await (await auditResponse).json()) as { rows: unknown[] };
  expect(audit.rows.length).toBeGreaterThan(0);
  expect(differentialPosts).toBe(1);
  await expect(workspace.getByTestId("differential-result")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(workspace.getByTestId("differential-selection")).toBeVisible();
  await expectNoPageOverflow(page);
});
