/// <reference types="vite/client" />

interface Window {
  /** Present in Tauri 2 WebViews; absent during ordinary Vite browser use. */
  __TAURI_INTERNALS__?: unknown;
}
