import { open, save } from "@tauri-apps/plugin-dialog";

/** Native path picker primitives reserved for the Workspace UI slice. */
export function pickWorkspaceDirectory(): Promise<string | string[] | null> {
  return open({ directory: true, multiple: false });
}

export function pickWorkspaceFiles(): Promise<string | string[] | null> {
  return open({ directory: false, multiple: true });
}

export function chooseExportPath(): Promise<string | null> {
  return save({
    filters: [
      { name: "AgentAudit JSON", extensions: ["json"] },
      { name: "AgentAudit Markdown", extensions: ["md"] },
    ],
  });
}
