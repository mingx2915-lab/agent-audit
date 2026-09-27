import type { DocumentImportSource } from "@agent-audit/contracts";

/** Preserve errors returned by Tauri commands, including plain strings. */
export function nativeErrorMessage(
  error: unknown,
  fallback = "桌面操作失败",
): string {
  if (typeof error === "string" && error.trim()) {
    return error.trim();
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  if (error !== null && typeof error === "object") {
    const record = error as Record<string, unknown>;
    for (const key of ["message", "detail", "error"]) {
      const value = record[key];
      if (typeof value === "string" && value.trim()) {
        return value.trim();
      }
    }
  }
  return fallback;
}

export interface WorkspaceBackupTransport {
  saveWorkspaceBackup(bytes: Uint8Array, suggestedName: string): Promise<boolean | void>;
  selectWorkspaceBackup(): Promise<Uint8Array | number[] | null>;
  activateWorkspace(relativeDirectory: string): Promise<void>;
}

export interface DiagnosticsTransport {
  saveDiagnosticsArchive(bytes: Uint8Array, suggestedName: string): Promise<boolean | void>;
}

export interface DocumentPickerTransport {
  selectDocumentFiles(): Promise<DocumentImportSource[]>;
  selectDocumentFolder(): Promise<DocumentImportSource[]>;
}

declare global {
  interface Window {
    /** Explicit browser/E2E seam; production uses the Tauri commands below. */
    __AGENT_AUDIT_DOCUMENT_PICKER__?: DocumentPickerTransport;
    /** Explicit browser/E2E seam for the desktop-only Workspace operations. */
    __AGENT_AUDIT_WORKSPACE_BACKUP__?: WorkspaceBackupTransport;
    /** Alias used by browser/E2E fixtures for the complete Workspace seam. */
    __AGENT_AUDIT_WORKSPACE_TRANSPORT__?: WorkspaceBackupTransport;
    /** Explicit browser/E2E seam for the desktop-only diagnostics save boundary. */
    __AGENT_AUDIT_DIAGNOSTICS__?: DiagnosticsTransport;
  }
}

let documentPickerTransport: DocumentPickerTransport | null = null;
let workspaceBackupTransport: WorkspaceBackupTransport | null = null;
let diagnosticsTransport: DiagnosticsTransport | null = null;

/**
 * Install a deterministic picker for browser tests or local development.
 * The seam is opt-in; ordinary browser use does not silently inspect files.
 */
export function setDocumentPickerTransport(
  transport: DocumentPickerTransport | null,
): void {
  documentPickerTransport = transport;
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

export function isDesktopRuntime(): boolean {
  return isTauriRuntime();
}

function configuredTransport(): DocumentPickerTransport | null {
  return documentPickerTransport ?? window.__AGENT_AUDIT_DOCUMENT_PICKER__ ?? null;
}

async function invokeDocumentPicker(
  command: "select_document_files" | "select_document_folder",
): Promise<DocumentImportSource[]> {
  try {
    const transport = configuredTransport();
    if (transport) {
      return command === "select_document_files"
        ? await transport.selectDocumentFiles()
        : await transport.selectDocumentFolder();
    }

    if (!isTauriRuntime()) {
      throw new Error("资料选择需要桌面窗口；开发或 E2E 请注入 DocumentPickerTransport");
    }

    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke<DocumentImportSource[]>(command);
  } catch (error) {
    throw new Error(nativeErrorMessage(error, "无法读取所选资料"));
  }
}

export function selectDocumentFiles(): Promise<DocumentImportSource[]> {
  return invokeDocumentPicker("select_document_files");
}

export function selectDocumentFolder(): Promise<DocumentImportSource[]> {
  return invokeDocumentPicker("select_document_folder");
}

export const pickDocumentFiles = selectDocumentFiles;
export const pickDocumentFolder = selectDocumentFolder;

function configuredWorkspaceTransport(): WorkspaceBackupTransport | null {
  return (
    workspaceBackupTransport ??
    window.__AGENT_AUDIT_WORKSPACE_BACKUP__ ??
    window.__AGENT_AUDIT_WORKSPACE_TRANSPORT__ ??
    null
  );
}

export function setWorkspaceBackupTransport(
  transport: WorkspaceBackupTransport | null,
): void {
  workspaceBackupTransport = transport;
}

export async function saveWorkspaceBackup(
  bytes: Uint8Array,
  suggestedName: string,
): Promise<boolean | void> {
  const transport = configuredWorkspaceTransport();
  if (transport) {
    return transport.saveWorkspaceBackup(bytes, suggestedName);
  }
  if (!isTauriRuntime()) {
    throw new Error("Workspace 备份保存需要桌面窗口；开发或 E2E 请注入 WorkspaceBackupTransport");
  }

  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("save_workspace_backup", {
    bytes: Array.from(bytes),
    suggestedName,
  });
}

export async function selectWorkspaceBackup(): Promise<Uint8Array | null> {
  const transport = configuredWorkspaceTransport();
  if (transport) {
    const bytes = await transport.selectWorkspaceBackup();
    return bytes === null || bytes === undefined
      ? null
      : bytes instanceof Uint8Array
        ? bytes
        : new Uint8Array(bytes);
  }
  if (!isTauriRuntime()) {
    throw new Error("Workspace 备份选择需要桌面窗口；开发或 E2E 请注入 WorkspaceBackupTransport");
  }

  const { invoke } = await import("@tauri-apps/api/core");
  const bytes = await invoke<number[] | null>("select_workspace_backup");
  return bytes ? new Uint8Array(bytes) : null;
}

export async function activateWorkspace(relativeDirectory: string): Promise<void> {
  const transport = configuredWorkspaceTransport();
  if (transport) {
    await transport.activateWorkspace(relativeDirectory);
    return;
  }
  if (!isTauriRuntime()) {
    throw new Error("Workspace 切换需要桌面窗口；请重启桌面端加载恢复后的 Workspace");
  }

  const { invoke } = await import("@tauri-apps/api/core");
  await invoke<void>("activate_workspace", { relativeDirectory });
}

export const pickWorkspaceBackup = selectWorkspaceBackup;

export function setDiagnosticsTransport(transport: DiagnosticsTransport | null): void {
  diagnosticsTransport = transport;
}

export async function saveDiagnosticsArchive(
  bytes: Uint8Array,
  suggestedName: string,
): Promise<boolean | void> {
  const transport = diagnosticsTransport ?? window.__AGENT_AUDIT_DIAGNOSTICS__ ?? null;
  if (transport) {
    return transport.saveDiagnosticsArchive(bytes, suggestedName);
  }
  if (!isTauriRuntime()) {
    throw new Error("诊断包原生保存需要桌面窗口");
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<boolean>("save_diagnostics_archive", {
    bytes: Array.from(bytes),
    suggestedName,
  });
}

/**
 * Store a bearer value through the Tauri shell's OS credential-store command.
 * Browser mode deliberately has no fallback: it cannot persist bearer
 * credentials and must ask the user to use the packaged desktop app.
 */
export async function storeProviderSecret(secret: string): Promise<void> {
  if (!secret.trim()) {
    throw new Error("Provider API Key 不能为空");
  }
  if (!isTauriRuntime()) {
    throw new Error("Provider API Key 只能保存在桌面端系统凭据存储中");
  }

  const { invoke } = await import("@tauri-apps/api/core");
  await invoke<void>("store_provider_secret", { secret });
}

/** Delete the active Provider API Key (Bearer API Key or x-api-key) from the desktop OS credential store. */
export async function deleteProviderSecret(): Promise<void> {
  if (!isTauriRuntime()) {
    throw new Error("Provider API Key 只能由桌面端系统凭据存储管理");
  }

  const { invoke } = await import("@tauri-apps/api/core");
  await invoke<void>("delete_provider_secret");
}
