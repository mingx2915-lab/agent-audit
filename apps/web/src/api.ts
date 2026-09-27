/**
 * Resolve the API origin once at application startup.
 *
 * Browser development keeps the existing same-origin `/api` contract. A
 * packaged Tauri window asks the native shell for the loopback Sidecar origin
 * so the Vue renderer never needs to know a port or a machine path.
 */
let apiBase = "";
const DESKTOP_STARTUP_TIMEOUT_MS = 35_000;
const DESKTOP_STARTUP_POLL_MS = 120;

type DesktopRuntimeStatus = {
  state: "starting" | "ready" | "failed" | "stopped";
  message?: string | null;
};

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

function normalizeApiBase(value: string): string {
  return value.trim().replace(/\/$/, "");
}

export async function initializeApiBase(): Promise<void> {
  if (!isTauriRuntime()) {
    apiBase = "";
    return;
  }

  const { invoke } = await import("@tauri-apps/api/core");
  const deadline = Date.now() + DESKTOP_STARTUP_TIMEOUT_MS;
  let lastError = "桌面后台尚未就绪";

  while (Date.now() < deadline) {
    try {
      apiBase = normalizeApiBase(await invoke<string>("get_api_base"));
      return;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }

    let status: DesktopRuntimeStatus | null = null;
    try {
      status = await invoke<DesktopRuntimeStatus>("get_desktop_runtime_status");
    } catch {
      // The shell can still be completing its startup registration.
    }
    if (status?.state === "failed" || status?.state === "stopped") {
      throw new Error(status.message?.trim() || lastError);
    }

    await new Promise<void>((resolve) => window.setTimeout(resolve, DESKTOP_STARTUP_POLL_MS));
  }

  throw new Error(`等待本机后台超时：${lastError}`);
}

export function apiUrl(path: string): string {
  if (!path.startsWith("/")) {
    throw new Error("API path must start with '/'");
  }

  return `${apiBase}${path}`;
}

export function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  if (typeof input === "string") {
    return fetch(apiUrl(input), init);
  }

  if (input instanceof URL && input.origin === window.location.origin) {
    return fetch(apiUrl(`${input.pathname}${input.search}${input.hash}`), init);
  }

  return fetch(input, init);
}
