import { defineConfig } from "@playwright/test";

const e2ePython =
  process.env.AGENT_AUDIT_E2E_PYTHON?.trim() ||
  (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : "python");

const noProxyHosts = new Set(
  (process.env.NO_PROXY ?? process.env.no_proxy ?? "")
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean),
);
noProxyHosts.add("127.0.0.1");
noProxyHosts.add("localhost");
const noProxy = [...noProxyHosts].join(",");
process.env.NO_PROXY = noProxy;
process.env.no_proxy = noProxy;

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./artifacts/acceptance/generated/playwright-output",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: `${e2ePython} -m uvicorn tests.e2e.support.server:app --host 127.0.0.1 --port 8000`,
      url: "http://127.0.0.1:8000/api/runtime",
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command:
        "npm run dev --workspace @agent-audit/web -- --host 127.0.0.1 --port 5173 --strictPort",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
