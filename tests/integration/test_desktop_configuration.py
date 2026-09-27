"""F-026 structural checks for the Tauri desktop delivery contract."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ROOT = REPOSITORY_ROOT / "apps" / "desktop"
TAURI_ROOT = DESKTOP_ROOT / "src-tauri"


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{path.name} must contain an object"
    return payload


def test_tauri_config_declares_a_hidden_independent_agent_audit_window() -> None:
    config = _read_json(TAURI_ROOT / "tauri.conf.json")
    build = config["build"]
    app = config["app"]
    bundle = config["bundle"]
    assert isinstance(build, dict)
    assert isinstance(app, dict)
    assert isinstance(bundle, dict)

    assert config["productName"] == "知盾 AgentAudit"
    assert config["identifier"] == "com.agent-audit.desktop"
    assert build["frontendDist"] == "../../web/dist"
    assert isinstance(build["beforeBuildCommand"], str)

    windows = app["windows"]
    assert isinstance(windows, list)
    assert len(windows) == 1
    window = windows[0]
    assert isinstance(window, dict)
    assert window["label"] == "main"
    assert window["title"] == "知盾 AgentAudit"
    assert window["visible"] is False
    assert window["fullscreen"] is False
    assert "url" not in window

    assert bundle["active"] is True
    assert "targets" not in bundle
    assert bundle["externalBin"] == ["binaries/agent-audit-sidecar"]
    windows_config = _read_json(TAURI_ROOT / "tauri.windows.conf.json")
    windows_bundle = windows_config["bundle"]
    assert isinstance(windows_bundle, dict)
    assert windows_bundle["targets"] == ["nsis"]
    nsis = windows_bundle["windows"]["nsis"]
    assert isinstance(nsis, dict)
    assert nsis["installMode"] == "currentUser"


def test_platform_configs_declare_real_windows_and_linux_targets() -> None:
    windows = _read_json(TAURI_ROOT / "tauri.windows.conf.json")
    linux = _read_json(TAURI_ROOT / "tauri.linux.conf.json")
    assert windows["bundle"]["targets"] == ["nsis"]
    assert set(linux["bundle"]["targets"]) == {"deb", "appimage"}


def test_linux_sidecar_and_desktop_scripts_are_platform_native_and_rebuildable() -> None:
    sidecar_script = (DESKTOP_ROOT / "scripts" / "build-sidecar.sh").read_text(
        encoding="utf-8"
    )
    desktop_script = (DESKTOP_ROOT / "scripts" / "build-linux.sh").read_text(
        encoding="utf-8"
    )
    assert "PyInstaller" in sidecar_script
    assert "x86_64-unknown-linux-gnu" in sidecar_script
    assert "@agent-audit/desktop" in desktop_script
    assert "--target" in desktop_script
    assert "build-sidecar.sh" in desktop_script
    assert (DESKTOP_ROOT / "scripts" / "agent-audit-sidecar.spec").is_file()


def test_tauri_capability_allows_only_loopback_sidecar_lifecycle_arguments() -> None:
    capability = _read_json(TAURI_ROOT / "capabilities" / "default.json")
    permissions = capability["permissions"]
    assert isinstance(permissions, list)
    sidecar_permission = next(
        permission
        for permission in permissions
        if isinstance(permission, dict)
        and permission.get("identifier") == "shell:allow-spawn"
    )
    allow = sidecar_permission["allow"]
    assert isinstance(allow, list)
    assert len(allow) == 1
    entry = allow[0]
    assert isinstance(entry, dict)
    assert entry["name"] == "binaries/agent-audit-sidecar"
    assert entry["sidecar"] is True

    args = entry["args"]
    assert isinstance(args, list)
    assert args[:2] == ["--host", "127.0.0.1"]
    assert "--port" in args
    assert "--workspace" in args
    assert "--target" not in args
    assert "--case" not in args
    assert "--contract" not in args

    app_security = _read_json(TAURI_ROOT / "tauri.conf.json")["app"]
    assert isinstance(app_security, dict)
    security = app_security["security"]
    assert isinstance(security, dict)
    csp = str(security["csp"])
    assert "http://127.0.0.1:*" in csp
    assert "http://localhost" not in csp


def test_desktop_package_is_a_workspace_member_with_local_build_commands() -> None:
    package = _read_json(DESKTOP_ROOT / "package.json")

    assert package["name"] == "@agent-audit/desktop"
    scripts = package["scripts"]
    assert isinstance(scripts, dict)
    assert scripts["dev"] == "tauri dev"
    assert scripts["build"] == "tauri build"
    assert scripts["typecheck"] == "tsc --noEmit"
    dependencies = package["dependencies"]
    assert isinstance(dependencies, dict)
    assert "@tauri-apps/api" in dependencies
    assert "@tauri-apps/plugin-dialog" in dependencies
    assert "@tauri-apps/plugin-shell" in dependencies


def test_native_dialog_module_exposes_system_file_and_folder_choices() -> None:
    source = (DESKTOP_ROOT / "src" / "native.ts").read_text(encoding="utf-8")

    assert 'from "@tauri-apps/plugin-dialog"' in source
    assert "export function pickWorkspaceDirectory" in source
    assert "export function pickWorkspaceFiles" in source
    assert "export function chooseExportPath" in source
    assert "directory: true" in source
    assert "multiple: true" in source
    assert "extensions: [\"json\"]" in source
    assert "extensions: [\"md\"]" in source


def test_renderer_routes_api_calls_through_the_desktop_aware_origin_adapter() -> None:
    app_source = (REPOSITORY_ROOT / "apps" / "web" / "src" / "App.vue").read_text(
        encoding="utf-8"
    )
    api_source = (REPOSITORY_ROOT / "apps" / "web" / "src" / "api.ts").read_text(
        encoding="utf-8"
    )
    main_source = (REPOSITORY_ROOT / "apps" / "web" / "src" / "main.ts").read_text(
        encoding="utf-8"
    )

    assert 'import { apiFetch } from "./api"' in app_source
    assert "fetch(" not in app_source
    assert "apiFetch(" in app_source
    assert "__TAURI_INTERNALS__" in api_source
    assert 'invoke<string>("get_api_base")' in api_source
    assert "http://" not in api_source
    assert "initializeApiBase" in main_source
    assert "无法连接本机后台" in main_source


def test_native_shell_owns_only_a_loopback_sidecar_and_stops_it_on_close() -> None:
    native_source = (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")
    cargo_source = (TAURI_ROOT / "Cargo.toml").read_text(encoding="utf-8")

    assert 'const SIDECAR_HOST: &str = "127.0.0.1";' in native_source
    assert 'app.shell().sidecar(SIDECAR_NAME)' in native_source
    assert "WindowEvent::CloseRequested" in native_source
    assert 'window.label() == "main"' in native_source
    assert "api.prevent_close();" in native_source
    assert "let _ = window.hide();" in native_source
    assert "if state.begin_shutdown()" in native_source
    assert "std::thread::spawn(move ||" in native_source
    assert "app.state::<SidecarState>().stop_child();" in native_source
    assert "app.exit(0);" in native_source
    assert "CommandEvent::Terminated" in native_source
    assert "tauri-plugin-opener" not in cargo_source
    assert "open::that" not in native_source


def test_provider_secret_uses_native_store_clear_and_sidecar_env_only() -> None:
    """Lock the Desktop credential boundary to the OS store and child env."""

    native_source = (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")
    cargo_source = (TAURI_ROOT / "Cargo.toml").read_text(encoding="utf-8")
    web_native_source = (
        REPOSITORY_ROOT / "apps" / "web" / "src" / "native.ts"
    ).read_text(encoding="utf-8")
    provider_setup_source = (
        REPOSITORY_ROOT / "apps" / "web" / "src" / "components" / "ProviderSetupView.vue"
    ).read_text(encoding="utf-8")

    # Windows and Linux use their native keyring backends; there is no file or
    # process-local replacement in the Desktop implementation.
    assert 'keyring = { version = "3.6.3", default-features = false, features = ["windows-native"] }' in cargo_source
    assert 'keyring = { version = "3.6.3", default-features = false, features = ["sync-secret-service", "crypto-rust", "vendored"] }' in cargo_source
    assert 'const PROVIDER_CREDENTIAL_SERVICE: &str = "com.agent-audit.desktop";' in native_source
    assert 'const PROVIDER_CREDENTIAL_ACCOUNT: &str = "active-provider-api-key";' in native_source
    assert 'const PROVIDER_SECRET_ENV: &str = "AGENT_AUDIT_PROVIDER_API_KEY";' in native_source
    assert "fn read_provider_secret_from_store()" in native_source
    assert "fn write_provider_secret_to_store(secret: &str)" in native_source
    assert "fn remove_provider_secret_from_store()" in native_source
    assert "entry.get_password()" in native_source
    assert "entry.set_password(secret)" in native_source
    assert "entry.delete_credential()" in native_source
    assert "ProviderSecretLookup::Unavailable" in native_source
    assert ".map_err(|_|" in native_source

    # Startup injects only an existing key into the child process.  Missing or
    # unavailable stores do not create a plaintext environment fallback.
    assert "if let ProviderSecretLookup::Present(secret) = state.provider_secret()" in native_source
    assert "command = command.env(PROVIDER_SECRET_ENV, secret);" in native_source
    assert "store_provider_secret," in native_source
    assert "delete_provider_secret," in native_source

    # Browser mode exposes an explicit unavailable boundary, and the UI stores
    # the key before the API PUT so a failed native write cannot fall through to
    # a plaintext request or config file.
    assert 'invoke<void>("store_provider_secret", { secret })' in web_native_source
    assert 'invoke<void>("delete_provider_secret")' in web_native_source
    assert "Bearer API Key" in web_native_source
    assert "storeProviderSecret" in provider_setup_source
    assert "const sameSavedConnection = computed" in provider_setup_source
    assert "saved.baseUrl === draftSettings.value.baseUrl" in provider_setup_source
    assert "\u6362\u4e86\u4f01\u4e1a\u5730\u5740\u540e\u8bf7\u91cd\u65b0\u8f93\u5165\u5bc6\u94a5\u518d\u68c0\u67e5" in provider_setup_source
    assert "if (draftSettings.value.authMode === \"bearer\" && credential.trim())" in provider_setup_source
    save_function = provider_setup_source[
        provider_setup_source.index("async function confirmProvider") :
    ]
    assert save_function.index("await storeProviderSecret(credential)") < save_function.index(
        'apiFetch("/api/provider-setup"'
    )


@pytest.mark.skipif(os.name != "nt", reason="F-026 bundle smoke is Windows-only")
def test_built_desktop_executable_smoke_uses_an_actual_artifact() -> None:
    """Start and close a real built executable when the caller supplies one.

    A source/config check cannot prove that a Windows bundle launches.  The
    test therefore only runs when the build pipeline explicitly points at the
    produced executable; without that artifact it remains an honest pending
    smoke rather than pretending that source files are a bundle.
    """

    artifact_value = os.environ.get("AGENT_AUDIT_DESKTOP_ARTIFACT")
    if not artifact_value:
        pytest.skip("set AGENT_AUDIT_DESKTOP_ARTIFACT to a built AgentAudit .exe")
    artifact = Path(artifact_value).expanduser().resolve()
    assert artifact.is_file(), f"desktop artifact does not exist: {artifact}"
    assert artifact.suffix.lower() == ".exe", "desktop smoke requires a Windows executable"

    with tempfile.TemporaryDirectory(prefix="agent-audit-desktop-smoke-") as home:
        workspace_manifest = (
            Path(home)
            / "workspaces"
            / "default"
            / "agent-audit-workspace.json"
        )
        started_at = time.monotonic()
        process = subprocess.Popen(
            [str(artifact)],
            cwd=artifact.parent,
            env={**os.environ, "AGENT_AUDIT_HOME": home},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if workspace_manifest.is_file():
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.25)
            assert process.poll() is None, "desktop executable exited before becoming usable"
            assert workspace_manifest.is_file(), (
                "desktop executable did not initialize its default Workspace"
            )
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(
                        [
                            str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"),
                            "/PID",
                            str(process.pid),
                            "/T",
                            "/F",
                        ],
                        check=False,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        assert time.monotonic() - started_at < 30
