import { expect, type Page } from "@playwright/test";
import { test } from "./support/test";
import {
  chooseOnboardingPath,
  installConfiguredProviderState,
} from "./support/first_use";

type AttackPlan = {
  id: string;
  basisType: string;
};

type ScanAttempt = {
  status: string;
  evaluation: { findings: Array<{ severity: string }> };
};

type Scan = {
  planId: string;
  status: string;
  attempts: ScanAttempt[];
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

async function installUnconfiguredProviderState(page: Page): Promise<void> {
  await page.route("**/api/provider-setup", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }

    const response = await route.fetch();
    const payload = (await response.json()) as Record<string, unknown>;
    payload.configured = false;
    payload.settings = null;
    payload.credentialConfigured = false;
    await route.fulfill({ response, json: payload });
  });
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

test("F-062 first-use structure stays bounded and path selection remains local", async ({
  page,
}) => {
  const apiPosts: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" || request.method() === "PUT") {
      apiPosts.push(`${request.method()} ${apiPath(request.url())}`);
    }
  });

  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/");

  const onboarding = page.getByTestId("enterprise-onboarding");
  const choices = page.getByTestId("onboarding-choices");
  await expect(onboarding).toBeVisible();
  await expect(choices).toBeVisible();
  await expect(choices.getByRole("button")).toHaveCount(2);
  await expect(page.getByTestId("provider-setup")).toHaveCount(0);
  await expect(page.getByTestId("document-import")).toHaveCount(0);

  const firstScreen = await page.evaluate(() => {
    const choices = document.querySelector<HTMLElement>("[data-testid='onboarding-choices']")!;
    const rows = [...choices.querySelectorAll<HTMLElement>(".enterprise-onboarding-choice")];
    const rowRects = rows.map((row) => row.getBoundingClientRect());
    return {
      choiceRows: rows.length,
      rowRects: rowRects.map((rect) => ({
        left: rect.left,
        right: rect.right,
        width: rect.width,
        height: rect.height,
      })),
    };
  });
  expect(firstScreen.choiceRows).toBe(2);
  expect(firstScreen.rowRects.every((rect) => rect.width > 0 && rect.height >= 44)).toBe(true);
  expect(
    firstScreen.rowRects.every(
      (rect) => rect.left >= -1 && rect.right <= 1601,
    ),
  ).toBe(true);

  await page.getByTestId("onboarding-custom").click();
  await expect(page.getByTestId("onboarding-path")).toContainText("验收我的知识助手");
  await expect(page.getByTestId("onboarding-step-provider")).toBeVisible();
  expect(apiPosts).toEqual([]);
  await expectNoPageOverflow(page);
});

test("F-062 keeps the real Critical Finding hierarchy and evidence expansion isolated", async ({
  page,
}) => {
  await installConfiguredProviderState(page);
  await page.setViewportSize({ width: 1600, height: 1000 });
  const plansResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  const plans = (await (await plansResponse).json()) as AttackPlan[];
  const plan = plans.find((candidate) => candidate.basisType === "source_sink");
  expect(plan).toBeDefined();
  if (!plan) {
    throw new Error("F-062 needs the real source_sink Attack Plan");
  }

  const scanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("guided-start-scan").click();
  const scan = (await (await scanResponse).json()) as Scan;
  const latestAttempt = scan.attempts.at(-1);
  expect(scan.planId).toBe(plan.id);
  expect(scan.status).toBe("completed");
  expect(latestAttempt?.status).toBe("finding");
  expect(latestAttempt?.evaluation.findings.some((finding) => finding.severity === "critical")).toBe(
    true,
  );

  const guided = page.getByTestId("guided-finding-summary");
  await expect(guided).toBeVisible();
  const criticalFinding = guided.locator(".finding-card").filter({
    has: page.locator(".finding-heading.is-critical"),
  });
  await expect(criticalFinding).toHaveCount(1);
  await expect(criticalFinding.locator(".finding-heading-content")).toContainText("严重风险");
  await expect(criticalFinding.locator(".finding-id-block")).toBeVisible();
  await expect(page.getByTestId("guided-result-context").locator(".guided-result-context-item")).toHaveCount(4);
  await expect(criticalFinding.locator(".finding-evidence-details")).toBeVisible();
  const evidenceImage = criticalFinding.locator(".finding-evidence-focus");
  await expect(evidenceImage).toBeVisible();
  await expect
    .poll(() =>
      evidenceImage.evaluate((element) => {
        const image = element as HTMLImageElement;
        return (
          image.currentSrc.includes("finding-evidence-focus.webp") &&
          image.complete &&
          image.naturalWidth > 0
        );
      }),
    )
    .toBe(true);

  const imagePlacement = await criticalFinding.evaluate((card) => {
    const image = card.querySelector<HTMLElement>(".finding-evidence-focus")!;
    const content = card.querySelector<HTMLElement>(".finding-heading-content")!;
    return {
      imageSource: (image as HTMLImageElement).currentSrc,
      contentText: content.innerText,
    };
  });
  expect(imagePlacement.imageSource).toContain("finding-evidence-focus.webp");
  expect(imagePlacement.contentText).toContain("严重风险");

  const chain = page.getByTestId("guided-attack-chain");
  const nodes = chain.locator(".chain-node");
  await expect(nodes).toHaveCount(6);
  const before = await nodes.evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { height: rect.height };
    }),
  );
  const toggle = chain.locator(".chain-evidence-toggle").first();
  await expect(toggle).toBeVisible();
  await toggle.click();
  await expect(chain.getByTestId("chain-evidence-panel")).toBeVisible();
  const after = await nodes.evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { height: rect.height };
    }),
  );
  expect(after).toHaveLength(before.length);
  for (let index = 0; index < before.length; index += 1) {
    expect(Math.abs(after[index]!.height - before[index]!.height)).toBeLessThanOrEqual(1);
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page);
});

test("F-062 keeps Provider Readiness artwork local to its real blocked state", async ({ page }) => {
  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await chooseOnboardingPath(page, "custom");
  await page.getByTestId("onboarding-next-action").click();

  const setup = page.getByTestId("provider-setup");
  await expect(setup).toBeVisible();
  const readinessVisual = setup.getByTestId("provider-readiness-visual");
  await expect(readinessVisual).toHaveAttribute("data-state", "blocked");
  await expect(readinessVisual.locator("img")).toHaveAttribute(
    "src",
    /provider-readiness-blocked\.webp/,
  );
  await expect
    .poll(() => readinessVisual.locator("img").evaluate((image: HTMLImageElement) =>
      image.complete && image.naturalWidth > 0,
    ))
    .toBe(true);
  await expect(readinessVisual).toContainText("尚未");

  const imagePlacement = await readinessVisual.evaluate((visual) => {
    const image = visual.querySelector<HTMLElement>("img")!;
    const copy = visual.querySelector<HTMLElement>(".provider-setup-flow-copy")!;
    const numericZIndex = (element: HTMLElement) => {
      const value = getComputedStyle(element).zIndex;
      return value === "auto" ? 0 : Number.parseInt(value, 10);
    };
    return {
      imageSource: (image as HTMLImageElement).currentSrc,
      copyText: copy.innerText,
      imageZIndex: numericZIndex(image),
      copyZIndex: numericZIndex(copy),
    };
  });
  expect(imagePlacement.imageSource).toContain("provider-readiness-blocked.webp");
  expect(imagePlacement.copyText).toContain("尚未");
  expect(imagePlacement.copyZIndex).toBeGreaterThan(imagePlacement.imageZIndex);
  await expectNoPageOverflow(page);
});
