import { expect, type Page } from "@playwright/test";
import { test } from "./support/test";
import path from "node:path";
import { chooseOnboardingPath, installConfiguredProviderState } from "./support/first_use";

type EvidenceRequests = {
  businessWrites: string[];
  apiNon2xx: string[];
};

type AttackPlan = {
  id: string;
  name: string;
  basisType: string;
  basisRuleId: string;
};

type Scan = {
  id: string;
  status: string;
  stopReason: string;
  attempts: Array<{
    evaluation: {
      status: string;
      findings: Array<{ id: string; severity: string; ruleId: string | null }>;
    };
  }>;
};

type Replay = {
  status: string;
  before: { evaluation: { status: string } };
  after: { evaluation: { status: string }; executionStatus: string };
};

function apiPath(url: string): string {
  return new URL(url).pathname;
}

function observeWrites(page: Page): EvidenceRequests {
  const evidence: EvidenceRequests = { businessWrites: [], apiNon2xx: [] };
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) {
      evidence.businessWrites.push(`${request.method()} ${apiPath(request.url())}`);
    }
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && apiPath(response.url()).startsWith("/api/")) {
      evidence.apiNon2xx.push(
        `${response.status()} ${response.request().method()} ${apiPath(response.url())}`,
      );
    }
  });
  return evidence;
}

function screenshotRoot(): string {
  const configured = process.env.AGENT_AUDIT_EVIDENCE_SCREENSHOT_DIR?.trim();
  return configured || test.info().outputPath("release-evidence-screenshots");
}

async function loadSourceSinkPlan(page: Page): Promise<AttackPlan> {
  await installConfiguredProviderState(page);
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      apiPath(response.url()) === "/api/attack-plans" &&
      response.ok(),
  );
  await page.goto("/");
  await chooseOnboardingPath(page, "demo");
  const plans = (await (await responsePromise).json()) as AttackPlan[];
  const plan = plans.find((candidate) => candidate.basisType === "source_sink");
  expect(plan).toBeDefined();
  if (!plan) {
    throw new Error("source_sink plan is unavailable");
  }
  await expect(page.getByTestId("workspace-guided")).toBeVisible();
  await expect(page.getByTestId("guided-plan")).toContainText(plan.name);
  return plan;
}

async function saveEvidenceScreenshot(page: Page, name: string): Promise<string> {
  const destination = path.join(screenshotRoot(), name);
  await page.screenshot({ path: destination, fullPage: true });
  return destination;
}

test("controlled_test captures the real guided not-run page without business writes", async ({
  page,
}) => {
  const evidence = observeWrites(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const plan = await loadSourceSinkPlan(page);

  await expect(page.getByTestId("guided-chain-preview")).toBeVisible();
  await expect(page.getByTestId("guided-finding-summary")).toContainText(
    "开始一次验收，结果会显示在这里",
  );
  await expect(page.getByTestId("guided-run-replay")).toBeDisabled();
  const screenshot = await saveEvidenceScreenshot(page, "guided-not-run.png");

  expect(screenshot).toContain("guided-not-run.png");
  expect(plan.basisRuleId).toEqual(expect.any(String));
  expect(evidence.businessWrites).toEqual([]);
  expect(evidence.apiNon2xx).toEqual([]);
});

test("controlled_test captures Critical Finding and passed Replay from real production routes", async ({
  page,
}) => {
  const evidence = observeWrites(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const plan = await loadSourceSinkPlan(page);
  const scanResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/scans" &&
      response.ok(),
  );
  await page.getByTestId("guided-start-scan").click();
  const scan = (await (await scanResponsePromise).json()) as Scan;
  const finding = scan.attempts.at(-1)?.evaluation.findings[0];
  expect(scan.status).toBe("completed");
  expect(scan.stopReason).toBe("finding_detected");
  expect(finding?.severity).toBe("critical");
  expect(finding?.ruleId).toBe("sink_external_message_confidential");
  await expect(page.getByTestId("critical-finding-visual")).toBeVisible();
  await expect(page.getByTestId("guided-finding-summary")).toContainText(finding?.id ?? "");
  await saveEvidenceScreenshot(page, "guided-critical-finding.png");

  const replayResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === `/api/attack-plans/${plan.id}/replay` &&
      response.ok(),
  );
  await page.getByTestId("guided-run-replay").click();
  const replay = (await (await replayResponsePromise).json()) as Replay;
  expect(replay.status).toBe("passed");
  expect(replay.before.evaluation.status).toBe("failed");
  expect(replay.after.evaluation.status).toBe("passed");
  expect(replay.after.executionStatus).toBe("blocked");
  await expect(page.getByTestId("guided-replay-state-visual")).toHaveClass(/is-passed/);
  await expect(page.getByTestId("guided-replay-before")).toContainText(/failed/i);
  await expect(page.getByTestId("guided-replay-after")).toContainText(/passed/i);
  await saveEvidenceScreenshot(page, "guided-replay-passed.png");

  expect(evidence.businessWrites).toEqual([
    "POST /api/scans",
    `POST /api/attack-plans/${plan.id}/replay`,
  ]);
  expect(evidence.apiNon2xx).toEqual([]);
});

test("controlled_test captures one real Acceptance Run summary with one necessary write", async ({
  page,
}) => {
  const evidence = observeWrites(page);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.getByRole("button", { name: "验收证据", exact: true }).click();
  await expect(page.getByTestId("acceptance-runs")).toBeVisible();
  await expect(page.getByTestId("acceptance-run-start")).toBeEnabled();
  expect(evidence.businessWrites).toEqual([]);

  const acceptanceResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      apiPath(response.url()) === "/api/acceptance-runs" &&
      response.ok(),
  );
  await page.getByTestId("acceptance-run-start").click();
  const run = (await (await acceptanceResponsePromise).json()) as {
    id: string;
    status: string;
    verdict: string;
    ciGate: { status: string };
  };
  expect(run.status).toBe("completed");
  expect(run.verdict).toBe(run.ciGate.status);
  await expect(page.getByTestId("acceptance-run-summary")).toBeVisible();
  await expect(page.getByTestId("acceptance-run-summary")).toContainText(run.id);
  await saveEvidenceScreenshot(page, "acceptance-run-summary.png");

  expect(evidence.businessWrites).toEqual(["POST /api/acceptance-runs"]);
  expect(evidence.apiNon2xx).toEqual([]);
});
