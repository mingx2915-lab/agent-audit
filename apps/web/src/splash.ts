import { invoke } from "@tauri-apps/api/core";
import brandMarkUrl from "./assets/agent-audit-mark.png";
import workspaceArtworkUrl from "./assets/illustrations/splash-local-workspace.webp";
import "./splash.css";

interface DesktopRuntimeStatus {
  state: "starting" | "ready" | "failed" | "stopped";
  apiBase: string | null;
  port: number | null;
  processId: number | null;
  message: string | null;
}

const mark = document.querySelector<HTMLImageElement>("#splash-mark");
const workspaceArtwork = document.querySelector<HTMLImageElement>("#splash-workspace");
const statusText = document.querySelector<HTMLParagraphElement>("#startup-status");
const detailText = document.querySelector<HTMLParagraphElement>("#startup-detail");
const guidance = document.querySelector<HTMLDivElement>("#startup-guidance");
const impactText = document.querySelector<HTMLParagraphElement>("#startup-impact");
const recoveryText = document.querySelector<HTMLParagraphElement>("#startup-recovery");
const technicalDetails = document.querySelector<HTMLDetailsElement>("#startup-technical");
const technicalMessage = document.querySelector<HTMLPreElement>("#startup-technical-message");
const exitButton = document.querySelector<HTMLButtonElement>("#startup-exit");

if (mark) mark.src = brandMarkUrl;
if (workspaceArtwork) workspaceArtwork.src = workspaceArtworkUrl;

function hideGuidance(): void {
  if (guidance) guidance.hidden = true;
  if (technicalDetails) technicalDetails.open = false;
}

function showGuidance(options: {
  impact: string;
  recovery: string;
  technicalDetail?: string | null;
}): void {
  if (!guidance || !impactText || !recoveryText || !technicalDetails || !technicalMessage) return;
  guidance.hidden = false;
  impactText.textContent = options.impact;
  recoveryText.textContent = options.recovery;
  technicalMessage.textContent = options.technicalDetail?.trim() || "未提供额外技术信息";
  technicalDetails.open = false;
}

function renderStatus(status: DesktopRuntimeStatus): boolean {
  if (!statusText || !detailText || !exitButton) return false;
  document.body.dataset.runtimeState = status.state;
  hideGuidance();
  if (status.state === "starting" && status.port === null) {
    statusText.textContent = "正在准备 Workspace";
    detailText.textContent = "正在确认本地目录与当前企业审计空间";
    return true;
  }
  if (status.state === "starting") {
    statusText.textContent = "正在启动本地审计服务";
    detailText.textContent = "正在检查 Sidecar 健康状态，仅连接 127.0.0.1";
    return true;
  }
  if (status.state === "ready") {
    statusText.textContent = "本地审计环境已就绪";
    detailText.textContent = "正在进入 Guided Audit";
    return false;
  }
  if (status.state === "failed") {
    statusText.textContent = "本地运行环境未能启动";
    detailText.textContent = "当前 Workspace 或本地后台没有通过启动检查。";
    showGuidance({
      impact: "本次审计尚未开始，你的 Workspace 文件不会因此被删除或覆盖。",
      recovery: "请退出应用后，从开始菜单或安装目录重新打开；如果仍然失败，请保留下面的技术详情用于排查。",
      technicalDetail: status.message,
    });
    exitButton.hidden = false;
    return false;
  }
  statusText.textContent = "本地审计服务已停止";
  detailText.textContent = "应用当前没有连接本地审计后台。";
  showGuidance({
    impact: "当前页面不会执行 Scan、Replay 或资料写入。",
    recovery: "请退出应用后重新打开；如果问题重复出现，再查看技术详情。",
  });
  exitButton.hidden = false;
  return false;
}

async function refreshStatus(): Promise<void> {
  try {
    const status = await invoke<DesktopRuntimeStatus>("get_desktop_runtime_status");
    if (renderStatus(status)) window.setTimeout(() => void refreshStatus(), 120);
  } catch (error) {
    if (statusText && detailText && exitButton) {
      document.body.dataset.runtimeState = "failed";
      statusText.textContent = "无法读取本地启动状态";
      detailText.textContent = "桌面窗口暂时无法确认本地后台是否已经就绪。";
      showGuidance({
        impact: "本次审计尚未开始，现有 Workspace 数据不受影响。",
        recovery: "请退出应用后重新打开；如果仍然失败，请保留下面的技术详情用于排查。",
        technicalDetail: error instanceof Error ? error.message : String(error),
      });
      exitButton.hidden = false;
    }
  }
}

exitButton?.addEventListener("click", () => {
  exitButton.disabled = true;
  void invoke("quit_application");
});

void refreshStatus();
