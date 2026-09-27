import { expect, test, type Page } from "@playwright/test";
import {
  chooseOnboardingPath,
  installConfiguredProviderState,
} from "./support/first_use";

type Scan = {
  planId: string;
  status: string;
  attempts: Array<{
    status: string;
    evaluation: { findings: Array<{ severity: string }> };
  }>;
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
  expect(widths.document).toBeLessThanOrEqual(widths.viewport + 1);
  expect(widths.body).toBeLessThanOrEqual(widths.viewport + 1);
}

async function expectNoEarlyStateArtwork(page: Page): Promise<void> {
  const forbidden = [
    "audit-chain-data-flow",
    "finding-evidence-focus",
    "evidence-pulse",
    "replay-before-blocked",
    "replay-after-connected",
    "provider-readiness-blocked",
    "provider-readiness-connected",
  ];
  const matches = await page.evaluate((assetNames) => {
    const onboarding = document.querySelector<HTMLElement>(
      "[data-testid='enterprise-onboarding']",
    );
    if (!onboarding) {
      return ["missing onboarding"];
    }

    const elements = [onboarding, ...onboarding.querySelectorAll<HTMLElement>("*")];
    const candidates = elements.flatMap((element) => [
      element instanceof HTMLImageElement ? element.currentSrc : "",
      getComputedStyle(element).backgroundImage,
      getComputedStyle(element, "::before").backgroundImage,
      getComputedStyle(element, "::after").backgroundImage,
    ]);
    return candidates.filter((candidate) =>
      assetNames.some((assetName) => candidate.includes(assetName)),
    );
  }, forbidden);
  expect(matches).toEqual([]);
}

async function expectReadableTextContrast(page: Page): Promise<void> {
  const contrast = await page.evaluate(() => {
    type Color = { r: number; g: number; b: number; a: number };

    function parseColor(value: string): Color | null {
      const match = value.match(/rgba?\(([^)]+)\)/);
      if (!match) {
        return null;
      }
      const channels = match[1]!.split(",").map((channel) => Number.parseFloat(channel.trim()));
      if (channels.length < 3 || channels.some((channel) => Number.isNaN(channel))) {
        return null;
      }
      return {
        r: channels[0]!,
        g: channels[1]!,
        b: channels[2]!,
        a: channels[3] ?? 1,
      };
    }

    function luminance(color: Color): number {
      const linear = [color.r, color.g, color.b].map((channel) => {
        const normalized = channel / 255;
        return normalized <= 0.03928
          ? normalized / 12.92
          : ((normalized + 0.055) / 1.055) ** 2.4;
      });
      return 0.2126 * linear[0]! + 0.7152 * linear[1]! + 0.0722 * linear[2]!;
    }

    function backgroundFor(element: HTMLElement): Color {
      let current: HTMLElement | null = element;
      while (current) {
        const color = parseColor(getComputedStyle(current).backgroundColor);
        if (color && color.a >= 0.98) {
          return color;
        }
        current = current.parentElement;
      }
      return parseColor(getComputedStyle(document.body).backgroundColor) ?? {
        r: 255,
        g: 255,
        b: 255,
        a: 1,
      };
    }

    const selectors = [
      "[data-testid='enterprise-onboarding'] h2",
      "[data-testid='enterprise-onboarding'] .enterprise-onboarding-choice strong",
      "[data-testid='enterprise-onboarding'] .enterprise-onboarding-choice small",
      "[data-testid='enterprise-onboarding'] .enterprise-onboarding-choice-step-label",
      "[data-testid='enterprise-onboarding'] .enterprise-onboarding-choice-action",
    ];
    return selectors.flatMap((selector) =>
      [...document.querySelectorAll<HTMLElement>(selector)]
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        })
        .map((element) => {
          const style = getComputedStyle(element);
          const textColor = parseColor(style.color) ?? { r: 0, g: 0, b: 0, a: 1 };
          const backgroundColor = backgroundFor(element);
          const ratio =
            (Math.max(luminance(textColor), luminance(backgroundColor)) + 0.05) /
            (Math.min(luminance(textColor), luminance(backgroundColor)) + 0.05);
          const fontSize = Number.parseFloat(style.fontSize);
          const fontWeight = Number.parseInt(style.fontWeight, 10);
          const required = fontSize >= 18 || (fontSize >= 14 && fontWeight >= 700) ? 3 : 4.5;
          return { selector, ratio, required };
        }),
    );
  });

  expect(contrast.length).toBeGreaterThan(0);
  for (const sample of contrast) {
    expect(sample.ratio, `${sample.selector} contrast`).toBeGreaterThanOrEqual(sample.required);
  }
}

test("F-063 first-use stage exposes real paths without early state artwork", async ({ page }) => {
  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");

  const onboarding = page.getByTestId("enterprise-onboarding");
  const stage = page.getByTestId("onboarding-choices");
  await expect(onboarding).toBeVisible();
  await expect(stage).toBeVisible();
  await expect(stage.locator(".enterprise-onboarding-choice")).toHaveCount(2);
  await expectNoEarlyStateArtwork(page);

  const navigationMetrics = await page.locator(".workspace-nav").evaluate((element) => {
    const style = getComputedStyle(element);
    const items = [...element.querySelectorAll<HTMLElement>(".workspace-nav-item")];
    return {
      itemCount: items.length,
      gap: style.gap,
      borderWidth: style.borderTopWidth,
      borderRadius: Number.parseFloat(style.borderTopLeftRadius),
      itemBorders: items.map((item) => {
        const itemStyle = getComputedStyle(item);
        return {
          borderRadius: Number.parseFloat(itemStyle.borderTopLeftRadius),
          rightWidth: itemStyle.borderRightWidth,
        };
      }),
    };
  });
  expect(navigationMetrics.itemCount).toBe(4);
  expect(navigationMetrics.gap).toBe("0px");
  expect(navigationMetrics.borderWidth).not.toBe("0px");
  expect(navigationMetrics.borderRadius).toBeGreaterThanOrEqual(8);
  expect(navigationMetrics.itemBorders.every((item) => item.borderRadius === 0)).toBe(true);
  expect(navigationMetrics.itemBorders.slice(0, -1).every((item) => item.rightWidth !== "0px")).toBe(
    true,
  );
  expect(navigationMetrics.itemBorders.at(-1)?.rightWidth).toBe("0px");

  const stageMetrics = await stage.evaluate((element) => {
    const style = getComputedStyle(element);
    const cards = [...element.querySelectorAll<HTMLElement>(".enterprise-onboarding-choice")];
    const cardRects = cards.map((card) => {
      const rect = card.getBoundingClientRect();
      return { left: rect.left, right: rect.right, width: rect.width, height: rect.height };
    });
    const cardAlphas = cards.map((card) => {
      const button = card.querySelector<HTMLElement>("button");
      const background = button ? getComputedStyle(button).backgroundColor : "";
      const match = background.match(/rgba?\([^,]+,[^,]+,[^,]+,\s*([0-9.]+)\)/);
      return match ? Number.parseFloat(match[1]!) : 1;
    });
    return {
      background: style.backgroundColor,
      cardRects,
      cardAlphas,
    };
  });
  expect(stageMetrics.cardRects).toHaveLength(2);
  expect(stageMetrics.cardRects[0]!.height).toBeGreaterThanOrEqual(300);
  expect(
    Math.abs(stageMetrics.cardRects[0]!.height - stageMetrics.cardRects[1]!.height),
  ).toBeLessThanOrEqual(1);
  expect(stageMetrics.cardRects.every((rect) => rect.width > 0 && rect.left >= -1)).toBe(true);
  expect(stageMetrics.background).not.toContain("11, 35, 64");
  expect(stageMetrics.cardAlphas.every((alpha) => alpha >= 0.86 && alpha <= 0.92)).toBe(true);

  await expect(
    page.getByTestId("onboarding-demo-steps").locator(".enterprise-onboarding-choice-step-label"),
  ).toHaveText(["连接 AI", "运行固定检查", "查看风险证据", "模拟复测"]);
  await expect(
    page.getByTestId("onboarding-custom-steps").locator(".enterprise-onboarding-choice-step-label"),
  ).toHaveText(["连接 AI", "添加业务资料", "确认权限边界", "运行安全检查"]);
  await expect(page.getByTestId("onboarding-demo")).toContainText("开始合成演示");
  await expect(page.getByTestId("onboarding-custom")).toContainText("开始验收我的助手");

  const controls = await stage.locator("button").evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }),
  );
  expect(controls.length).toBe(2);
  expect(controls.every((rect) => rect.width >= 44 && rect.height >= 44)).toBe(true);
  await expectReadableTextContrast(page);
  await expectNoPageOverflow(page);
});

test("F-063 compact desktop keeps first-use actions visible at 1024px", async ({ page }) => {
  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto("/");
  await page.getByTestId("display-scale-standard").click();

  const metrics = await page.evaluate(() => ({
    viewportHeight: window.innerHeight,
    actions: [...document.querySelectorAll<HTMLElement>(
      "[data-testid='onboarding-choices'] .enterprise-onboarding-choice-action",
    )].map((element) => {
      const rect = element.getBoundingClientRect();
      return { bottom: rect.bottom, height: rect.height };
    }),
  }));

  expect(metrics.actions).toHaveLength(2);
  expect(metrics.actions.every((action) => action.height >= 44)).toBe(true);
  expect(metrics.actions.every((action) => action.bottom <= metrics.viewportHeight + 1)).toBe(true);
  await expectNoPageOverflow(page);
});

test("F-063 first-use stage remains usable at 390px and in standard display scale", async ({
  page,
}) => {
  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await expect(page.getByTestId("display-scale-large")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("display-scale-standard").click();
  await expect(page.getByTestId("display-scale-standard")).toHaveAttribute("aria-pressed", "true");

  const displayControls = await page.locator(".display-scale-control button").evaluateAll((elements) =>
    elements.map((element) => {
      const rect = element.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }),
  );
  expect(displayControls).toHaveLength(2);
  expect(displayControls.every((rect) => rect.width >= 44 && rect.height >= 44)).toBe(true);

  const stage = page.getByTestId("onboarding-choices");
  await expect(stage).toBeVisible();
  const metrics = await stage.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const cards = [...element.querySelectorAll<HTMLElement>(".enterprise-onboarding-choice")];
    return {
      rect: { left: rect.left, right: rect.right, width: rect.width },
      cardRects: cards.map((card) => {
        const cardRect = card.getBoundingClientRect();
        return { left: cardRect.left, right: cardRect.right, width: cardRect.width, height: cardRect.height };
      }),
      zoom: getComputedStyle(document.documentElement).zoom,
    };
  });
  expect(metrics.zoom).toBe("1");
  expect(metrics.cardRects).toHaveLength(2);
  expect(metrics.cardRects.every((rect) => rect.left >= -1 && rect.right <= 391)).toBe(true);
  expect(metrics.rect.right).toBeLessThanOrEqual(391);
  expect(metrics.cardRects[0]!.height).toBeGreaterThanOrEqual(250);
  await expectReadableTextContrast(page);
  await expectNoEarlyStateArtwork(page);
  await expectNoPageOverflow(page);
});

test("F-063 folds the completed path while keeping the real scan request and result first", async ({
  page,
}) => {
  const businessWrites: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" || request.method() === "PUT") {
      businessWrites.push(`${request.method()} ${apiPath(request.url())}`);
    }
  });

  await installConfiguredProviderState(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const plansResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  await plansResponse;

  const scanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("guided-start-scan").click();
  const scan = (await (await scanResponse).json()) as Scan;
  const latestAttempt = scan.attempts.at(-1);
  expect(scan.status).toBe("completed");
  expect(latestAttempt?.evaluation.findings.some((finding) => finding.severity === "critical")).toBe(
    true,
  );
  expect(businessWrites).toEqual(["POST /api/scans"]);

  const completedBar = page.getByTestId("onboarding-completed-bar");
  await expect(completedBar).toBeVisible();
  await expect(completedBar).toHaveAttribute("data-state", "completed");
  await expect(completedBar).toContainText("当前路径");
  await expect(completedBar).toContainText("使用合成演示");
  await expect(completedBar).toContainText("已完成检查");
  await expect(page.getByTestId("onboarding-choices")).toHaveCount(0);
  await expect(page.getByTestId("onboarding-path")).toHaveCount(0);
  await expect(page.getByTestId("guided-finding-summary")).toBeVisible();
  await expect(page.getByTestId("critical-finding-visual")).toBeVisible();

  const findingDisclosureMetrics = await page
    .locator(".finding-evidence-details > summary, .finding-original-details > summary")
    .evaluateAll((summaries) =>
      summaries.map((summary) => {
        const rect = summary.getBoundingClientRect();
        const style = getComputedStyle(summary);
        return {
          height: rect.height,
          fontSize: Number.parseFloat(style.fontSize),
          chevron: getComputedStyle(summary, "::before").backgroundImage,
        };
      }),
    );
  expect(findingDisclosureMetrics).toHaveLength(2);
  expect(findingDisclosureMetrics.every((metric) => metric.height >= 44)).toBe(true);
  expect(findingDisclosureMetrics.every((metric) => metric.fontSize >= 14)).toBe(true);
  expect(findingDisclosureMetrics.every((metric) => metric.chevron !== "none")).toBe(true);

  const compactHeight = await completedBar.evaluate((element) => element.getBoundingClientRect().height);
  expect(compactHeight).toBeGreaterThanOrEqual(56);
  expect(compactHeight).toBeLessThanOrEqual(72);
  const resetBox = await completedBar.getByTestId("onboarding-reset").boundingBox();
  expect(resetBox?.width ?? 0).toBeGreaterThanOrEqual(44);
  expect(resetBox?.height ?? 0).toBeGreaterThanOrEqual(44);

  const criticalImageSource = await page
    .getByTestId("critical-finding-visual")
    .locator(".finding-evidence-focus")
    .evaluate((image) => (image as HTMLImageElement).currentSrc);
  expect(criticalImageSource).toContain("finding-evidence-focus.webp");

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileCompactHeight = await completedBar.evaluate((element) =>
    element.getBoundingClientRect().height,
  );
  expect(mobileCompactHeight).toBeGreaterThanOrEqual(56);
  expect(mobileCompactHeight).toBeLessThanOrEqual(72);
  const mobileResetBox = await completedBar.getByTestId("onboarding-reset").boundingBox();
  expect(mobileResetBox?.width ?? 0).toBeGreaterThanOrEqual(44);
  expect(mobileResetBox?.height ?? 0).toBeGreaterThanOrEqual(44);
  await expectNoPageOverflow(page);

  await page.getByTestId("onboarding-reset").click();
  await expect(page.getByTestId("onboarding-choices")).toBeVisible();
  await expect(page.getByTestId("onboarding-completed-bar")).toHaveCount(0);
  expect(businessWrites).toEqual(["POST /api/scans"]);
  await expectNoPageOverflow(page);
});

test("F-063 keeps all workspace destinations in one compact rail at intermediate width", async ({
  page,
}) => {
  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 592, height: 844 });
  await page.goto("/");
  await page.getByTestId("display-scale-large").click();

  const metrics = await page.locator(".workspace-nav").evaluate((navigation) => {
    const navigationRect = navigation.getBoundingClientRect();
    const items = [...navigation.querySelectorAll<HTMLElement>(".workspace-nav-item")];
    return {
      navigation: {
        left: navigationRect.left,
        right: navigationRect.right,
        height: navigationRect.height,
      },
      items: items.map((item) => {
        const rect = item.getBoundingClientRect();
        return {
          left: rect.left,
          right: rect.right,
          top: rect.top,
          height: rect.height,
        };
      }),
    };
  });

  expect(metrics.items).toHaveLength(4);
  expect(metrics.navigation.left).toBeGreaterThanOrEqual(0);
  expect(metrics.navigation.right).toBeLessThanOrEqual(593);
  expect(metrics.navigation.height).toBeGreaterThanOrEqual(44);
  expect(metrics.navigation.height).toBeLessThanOrEqual(96);
  expect(new Set(metrics.items.map((item) => Math.round(item.top))).size).toBe(1);
  expect(
    metrics.items.every(
      (item) =>
        item.left >= metrics.navigation.left - 1 &&
        item.right <= metrics.navigation.right + 1 &&
        item.height >= 44,
    ),
  ).toBe(true);
  await expectNoPageOverflow(page);
});

test("F-063 aligns Fixed Case categories and separates Plan cards", async ({ page }) => {
  await installConfiguredProviderState(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const plansResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  await plansResponse;
  await page.getByRole("button", { name: /设置与计划/ }).click();

  const caseMetrics = await page.locator(".case-card").evaluateAll((cards) =>
    cards.map((card) => {
      const expectations = card.querySelector<HTMLElement>(".case-expectations")!;
      const label = expectations.querySelector<HTMLElement>(":scope > span")!;
      const category = card.querySelector<HTMLElement>(".case-category-tag")!;
      const action = card.querySelector<HTMLElement>(".case-execute-button")!;
      const categoryStyle = getComputedStyle(category);
      const labelRect = label.getBoundingClientRect();
      const categoryRect = category.getBoundingClientRect();
      return {
        expectationTop: Math.round(expectations.getBoundingClientRect().top),
        categoryTop: Math.round(categoryRect.top),
        labelCenter: Math.round(labelRect.top + labelRect.height / 2),
        categoryCenter: Math.round(categoryRect.top + categoryRect.height / 2),
        actionBottom: Math.round(action.getBoundingClientRect().bottom),
        categoryColor: categoryStyle.color,
        categoryBackground: categoryStyle.backgroundColor,
        categoryWeight: Number.parseInt(categoryStyle.fontWeight, 10),
      };
    }),
  );
  expect(caseMetrics).toHaveLength(2);
  expect(new Set(caseMetrics.map((metric) => metric.expectationTop)).size).toBe(1);
  expect(new Set(caseMetrics.map((metric) => metric.categoryTop)).size).toBe(1);
  expect(new Set(caseMetrics.map((metric) => metric.actionBottom)).size).toBe(1);
  expect(
    caseMetrics.every((metric) => Math.abs(metric.labelCenter - metric.categoryCenter) <= 1),
  ).toBe(true);
  expect(caseMetrics.every((metric) => metric.categoryBackground !== "rgba(0, 0, 0, 0)")).toBe(
    true,
  );
  expect(caseMetrics.every((metric) => metric.categoryColor !== "rgb(144, 147, 153)")).toBe(true);
  expect(caseMetrics.every((metric) => metric.categoryWeight >= 600)).toBe(true);

  const workspace = page.getByTestId("attack-plans-workspace");
  await expect(workspace).toBeVisible();
  const setupWorkspaceGap = await page.locator(".setup-workspace").evaluateAll((sections) => {
    const first = sections[0]?.getBoundingClientRect();
    const second = sections[1]?.getBoundingClientRect();
    return first && second ? second.top - first.bottom : 0;
  });
  expect(setupWorkspaceGap).toBeGreaterThanOrEqual(16);
  const technicalDetails = workspace.getByTestId("attack-plan-technical-details");
  await expect(technicalDetails).not.toHaveAttribute("open", "");
  const planMetrics = await workspace.evaluate((element) => {
    const list = element.querySelector<HTMLElement>(".attack-plans-list")!;
    const panel = element.querySelector<HTMLElement>(".attack-plans-list-panel")!;
    const detail = element.querySelector<HTMLElement>(".attack-plan-detail")!;
    const cards = [...element.querySelectorAll<HTMLElement>(".attack-plan-row")];
    return {
      columns: getComputedStyle(list).gridTemplateColumns.split(" ").length,
      panelBottom: Math.round(panel.getBoundingClientRect().bottom),
      listBottom: Math.round(list.getBoundingClientRect().bottom),
      detailBottom: Math.round(detail.getBoundingClientRect().bottom),
      cards: cards.map((card) => {
        const rect = card.getBoundingClientRect();
        const style = getComputedStyle(card);
        return {
          left: Math.round(rect.left),
          top: Math.round(rect.top),
          bottom: Math.round(rect.bottom),
          borderWidth: style.borderTopWidth,
          borderRadius: Number.parseFloat(style.borderTopLeftRadius),
        };
      }),
    };
  });
  expect(planMetrics.columns).toBe(2);
  expect(planMetrics.cards).toHaveLength(4);
  expect(new Set(planMetrics.cards.map((card) => card.left)).size).toBe(2);
  expect(new Set(planMetrics.cards.map((card) => card.top)).size).toBe(2);
  expect(new Set(planMetrics.cards.map((card) => card.bottom)).size).toBe(2);
  expect(planMetrics.cards.every((card) => card.borderWidth !== "0px")).toBe(true);
  expect(planMetrics.cards.every((card) => card.borderRadius >= 8)).toBe(true);
  expect(Math.abs(planMetrics.panelBottom - planMetrics.detailBottom)).toBeLessThanOrEqual(1);
  expect(Math.abs(planMetrics.listBottom - planMetrics.detailBottom)).toBeLessThanOrEqual(1);

  const technicalSummary = technicalDetails.locator("summary");
  const technicalSummaryMetrics = await technicalSummary.evaluate((summary) => {
    const rect = summary.getBoundingClientRect();
    const style = getComputedStyle(summary);
    return {
      height: rect.height,
      fontSize: Number.parseFloat(style.fontSize),
      chevron: getComputedStyle(summary, "::before").backgroundImage,
    };
  });
  expect(technicalSummaryMetrics.height).toBeGreaterThanOrEqual(44);
  expect(technicalSummaryMetrics.fontSize).toBeGreaterThanOrEqual(14);
  expect(technicalSummaryMetrics.chevron).not.toBe("none");
  await technicalSummary.click();
  await expect(technicalDetails).toHaveAttribute("open", "");

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileColumns = await workspace
    .locator(".attack-plans-list")
    .evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length);
  expect(mobileColumns).toBe(1);
  await expectNoPageOverflow(page);
});

test("F-063 keeps scan, replay, and saved evidence inside the 390px viewport", async ({
  page,
}) => {
  await installConfiguredProviderState(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  const plansResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  await plansResponse;

  const scanResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("guided-start-scan").click();
  await scanResponse;

  const replayResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()).includes("/replay") &&
      response.ok(),
  );
  await page.getByTestId("guided-run-replay").click();
  await replayResponse;

  await page.getByRole("button", { name: "验收证据", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".scan-overview").first()).toBeVisible();
  await expect(page.locator(".replay-overview").first()).toBeVisible();

  const viewportViolations = await page
    .locator(".scan-overview, .replay-overview, .replay-attempt")
    .evaluateAll((roots) => {
      const viewportWidth = document.documentElement.clientWidth;
      return roots.flatMap((root) =>
        [root, ...root.querySelectorAll<HTMLElement>("*")]
          .filter((element) => {
            const rect = element.getBoundingClientRect();
            const style = getComputedStyle(element);
            return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden";
          })
          .filter((element) => {
            const rect = element.getBoundingClientRect();
            return rect.left < -1 || rect.right > viewportWidth + 1;
          })
          .map((element) => ({
            className: element.className,
            left: element.getBoundingClientRect().left,
            right: element.getBoundingClientRect().right,
          })),
      );
    });
  expect(viewportViolations).toEqual([]);

  const evidenceDisclosures = await page
    .locator(".history-snapshot-details > summary, .scan-attempt-evidence > summary")
    .evaluateAll((summaries) =>
      summaries
        .filter((summary) => {
          const rect = summary.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        })
        .map((summary) => ({
          height: summary.getBoundingClientRect().height,
          fontSize: Number.parseFloat(getComputedStyle(summary).fontSize),
          chevron: getComputedStyle(summary, "::before").backgroundImage,
        })),
    );
  expect(evidenceDisclosures.length).toBeGreaterThan(0);
  expect(evidenceDisclosures.every((metric) => metric.height >= 44)).toBe(true);
  expect(evidenceDisclosures.every((metric) => metric.fontSize >= 14)).toBe(true);
  expect(evidenceDisclosures.every((metric) => metric.chevron !== "none")).toBe(true);
  await expectNoPageOverflow(page);
});

test("F-063 gives Provider Readiness artwork enough depth and keeps disclosures easy to open", async ({
  page,
}) => {
  await installUnconfiguredProviderState(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await chooseOnboardingPath(page, "custom");
  await page.getByTestId("onboarding-next-action").click();

  const setup = page.getByTestId("provider-setup");
  await expect(setup).toBeVisible();
  const visual = setup.getByTestId("provider-readiness-visual");
  const desktopVisual = await visual.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const image = element.querySelector<HTMLImageElement>("img")!;
    return {
      height: rect.height,
      imageFit: getComputedStyle(image).objectFit,
    };
  });
  expect(desktopVisual.height).toBeGreaterThanOrEqual(196);
  expect(desktopVisual.height).toBeLessThanOrEqual(300);
  expect(desktopVisual.imageFit).toBe("cover");

  const disclosureTargets = await setup.locator("details > summary").evaluateAll((summaries) =>
    summaries
      .map((summary) => {
        const rect = summary.getBoundingClientRect();
        return { width: rect.width, height: rect.height };
      })
      .filter((rect) => rect.width > 0 && rect.height > 0),
  );
  expect(disclosureTargets.length).toBeGreaterThan(0);
  expect(disclosureTargets.every((rect) => rect.width >= 44 && rect.height >= 44)).toBe(true);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileHeight = await visual.evaluate((element) => element.getBoundingClientRect().height);
  expect(mobileHeight).toBeGreaterThanOrEqual(160);
  expect(mobileHeight).toBeLessThanOrEqual(240);
  await expectNoPageOverflow(page);
});

test("F-063 workspace directories preserve input and never execute business actions", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByRole("button", { name: "设置与计划", exact: true }).click();
  await expect(page.getByTestId("attack-plans-list")).toBeVisible();
  await page.locator("#query-message").fill("保留这条尚未提交的查询");
  const mutations: string[] = [];
  page.on("request", (request) => {
    if (["POST", "PUT", "DELETE", "PATCH"].includes(request.method())) mutations.push(request.url());
  });
  for (const link of await page.getByTestId("setup-section-nav").locator("a").all()) {
    const href = await link.getAttribute("href");
    expect(href).toBeTruthy();
    await link.click();
    await expect(page.locator(href!)).toBeInViewport();
    const position = await page.locator(href!).evaluate((element) => ({
      top: element.getBoundingClientRect().top,
      barBottom: document.querySelector(".topbar")!.getBoundingClientRect().bottom,
    }));
    expect(position.top).toBeGreaterThanOrEqual(position.barBottom);
  }
  await expect(page.locator("#query-message")).toHaveValue("保留这条尚未提交的查询");
  await page.getByRole("button", { name: "验收证据", exact: true }).click();
  for (const link of await page.getByTestId("evidence-section-nav").locator("a").all()) {
    const href = await link.getAttribute("href");
    await link.click();
    await expect(page.locator(href!)).toBeInViewport();
  }
  expect(mutations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page);
});

test("F-063 result reading order reaches real Finding, Trace, and Replay without rerunning", async ({ page }) => {
  await installConfiguredProviderState(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  await expect(page.locator(".enterprise-onboarding-header")).toHaveCount(0);
  await page.getByTestId("guided-start-scan").click();
  await expect(page.getByTestId("guided-result-nav")).toBeVisible();
  const mutations: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST") mutations.push(request.url());
  });
  for (const link of await page.getByTestId("guided-result-nav").locator("a").all()) {
    const href = await link.getAttribute("href");
    await link.click();
    await expect(page.locator(href!)).toBeInViewport();
  }
  expect(mutations).toEqual([]);
  await page.getByTestId("guided-run-replay").click();
  await expect(page.getByTestId("guided-replay-state-visual")).toBeVisible();
  expect(mutations).toHaveLength(1);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoPageOverflow(page);
});
