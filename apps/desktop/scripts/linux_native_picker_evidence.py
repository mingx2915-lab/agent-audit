#!/usr/bin/env python3
"""Exercise the packaged Linux file picker through a real WebView session.

This harness deliberately has two separate control planes:

* the official Tauri ``tauri-driver``/``WebKitWebDriver`` stack locates and
  clicks WebView elements by their ``data-testid``;
* ``xdotool`` is used only after a titled native GTK file chooser appears, to
  enter the path of an isolated synthetic Markdown file.

The script does not inject a browser transport and does not call the API's
Preview, Commit, or Scan endpoints.  A missing driver, missing native dialog,
or any failed assertion is a failed evidence run rather than a pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_VALUES = {"passed", "failed", "not_verified"}
ELEMENT_KEY = "element-6066-11e4-a52e-4f735466cecf"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(id_: str, status: str, detail: str = "") -> dict[str, str]:
    if status not in STATUS_VALUES:
        raise ValueError("invalid evidence status")
    return {"id": id_, "status": status, "detail": detail}


def wait_for_port(url: str, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if 200 <= response.status < 500:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    return False


def process_group_members(group_id: int) -> set[int]:
    result = subprocess.run(
        ["ps", "-e", "-o", "pid=,pgid="],
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    members: set[int] = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].isdigit() and int(fields[1]) == group_id:
            members.add(int(fields[0]))
    return members


def stop_process_group(process: subprocess.Popen[str], group_id: int) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            pass
    # tauri-driver owns the app process.  Verify and close its complete
    # process group, without broad pkill/killall patterns.
    members = process_group_members(group_id)
    if members:
        try:
            os.killpg(group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and process_group_members(group_id):
            time.sleep(0.1)


class WebDriverError(RuntimeError):
    pass


def webdriver_route_label(method: str, path: str) -> str:
    """Describe a WebDriver route without exposing transient element/session IDs."""
    parts = path.split("/")
    for index, part in enumerate(parts[:-1]):
        if part in {"session", "element"} and parts[index + 1]:
            parts[index + 1] = f":{part}"
    return f"{method.upper()} {'/'.join(parts)}"


class WebDriverClient:
    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session_id: str | None = None

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        payload = None
        headers = {"Accept": "application/json"}
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=payload, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # WebDriver protocol errors are a closed vocabulary.  Keep only
            # the protocol error token; never copy a driver response body,
            # which could contain environment details.
            detail = f"webdriver_http_{exc.code}"
            try:
                raw_error = exc.read()
                payload = json.loads(raw_error.decode("utf-8"))
                error = payload.get("value", {}).get("error")
                normalized_error = error.replace(" ", "_") if isinstance(error, str) else ""
                if normalized_error in {
                    "element_not_interactable",
                    "stale_element_reference",
                    "no_such_element",
                    "invalid_argument",
                    "unknown_error",
                    "timeout",
                }:
                    detail = f"webdriver_{normalized_error}"
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                pass
            raise WebDriverError(detail) from exc
        except (OSError, urllib.error.URLError) as exc:
            route = webdriver_route_label(method, path)
            raise WebDriverError(
                f"webdriver request unavailable: {type(exc).__name__} at {route}"
            ) from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WebDriverError("webdriver returned invalid JSON") from exc
        if isinstance(value, dict) and value.get("value") is not None:
            error = value["value"]
            if isinstance(error, dict) and error.get("error"):
                raise WebDriverError(str(error["error"]))
        return value

    def create_session(self, application: Path, args: list[str]) -> str:
        response = self.request(
            "POST",
            "/session",
            {
                "capabilities": {
                    "alwaysMatch": {
                        "browserName": "wry",
                        "tauri:options": {
                            "application": str(application),
                            "args": args,
                        },
                    },
                    "firstMatch": [{}],
                }
            },
        )
        value = response.get("value") if isinstance(response, dict) else None
        if not isinstance(value, dict):
            raise WebDriverError("webdriver session response has no value")
        session_id = value.get("sessionId") or response.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise WebDriverError("webdriver session id missing")
        self.session_id = session_id
        return session_id

    def close(self) -> None:
        if self.session_id is not None:
            try:
                self.request("DELETE", f"/session/{self.session_id}")
            except WebDriverError:
                pass
            self.session_id = None

    def session_request(
        self, method: str, suffix: str, body: dict[str, Any] | None = None
    ) -> Any:
        if self.session_id is None:
            raise WebDriverError("webdriver session is not active")
        return self.request(method, f"/session/{self.session_id}{suffix}", body)

    def find(self, selector: str) -> str:
        response = self.session_request(
            "POST", "/element", {"using": "css selector", "value": selector}
        )
        value = response.get("value") if isinstance(response, dict) else None
        if not isinstance(value, dict):
            raise WebDriverError(f"element not found: {selector}")
        element = value.get(ELEMENT_KEY) or value.get("ELEMENT")
        if not isinstance(element, str):
            raise WebDriverError(f"element id missing: {selector}")
        return element

    def find_all(self, selector: str) -> list[str]:
        response = self.session_request(
            "POST", "/elements", {"using": "css selector", "value": selector}
        )
        value = response.get("value") if isinstance(response, dict) else None
        if not isinstance(value, list):
            raise WebDriverError(f"element list invalid: {selector}")
        elements: list[str] = []
        for item in value:
            if isinstance(item, dict):
                element = item.get(ELEMENT_KEY) or item.get("ELEMENT")
                if isinstance(element, str):
                    elements.append(element)
        return elements

    def click(self, element: str) -> None:
        self.session_request("POST", f"/element/{element}/click", {})

    def execute(self, script: str, args: list[Any] | None = None) -> Any:
        response = self.session_request(
            "POST",
            "/execute/sync",
            {"script": script, "args": args or []},
        )
        return response.get("value") if isinstance(response, dict) else None

    def scroll_into_view(self, selector: str) -> None:
        response = self.session_request(
            "POST",
            "/execute/sync",
            {
                "script": (
                    "const element = document.querySelector(arguments[0]);"
                    "if (!element) return false;"
                    "element.scrollIntoView({block: 'center', inline: 'nearest'});"
                    "return true;"
                ),
                "args": [selector],
            },
        )
        value = response.get("value") if isinstance(response, dict) else None
        if value is not True:
            raise WebDriverError(f"element_not_scrollable:{selector}")

    def text(self, element: str) -> str:
        response = self.session_request("GET", f"/element/{element}/text")
        value = response.get("value") if isinstance(response, dict) else None
        return value if isinstance(value, str) else ""

    def resource_urls(self) -> list[str]:
        response = self.session_request(
            "POST",
            "/execute/sync",
            {
                "script": (
                    "return performance.getEntriesByType('resource')"
                    ".map((entry) => entry.name);"
                ),
                "args": [],
            },
        )
        value = response.get("value") if isinstance(response, dict) else None
        if not isinstance(value, list):
            raise WebDriverError("resource timing result is not a list")
        return [item for item in value if isinstance(item, str)]


def wait_for_element(driver: WebDriverClient, selector: str, timeout: float = 45.0) -> str:
    deadline = time.monotonic() + timeout
    last_error = "element_not_found"
    while time.monotonic() < deadline:
        try:
            return driver.find(selector)
        except WebDriverError as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise WebDriverError(f"{selector}:{last_error}")


def select_standard_display_scale(
    driver: WebDriverClient, timeout: float = 45.0
) -> dict[str, Any]:
    """Select the visible product control before exercising the picker.

    The packaged app defaults to the user-facing ``large`` display scale.
    WebKitWebDriver can otherwise miscalculate interactability for controls
    below the viewport because the product applies CSS ``zoom``.  The scale
    selector is a real application control in the top bar, so selecting it
    through the standard WebDriver element-click endpoint makes the later
    file-picker clicks use the same production path as a user.
    """

    selector = "[data-testid='display-scale-standard']"
    scale_element = wait_for_element(driver, selector, timeout=timeout)
    driver.scroll_into_view(selector)
    scale_element = wait_for_element(driver, selector, timeout=timeout)
    selection_mode = "webdriver_element_click"
    try:
        driver.click(scale_element)
    except WebDriverError as exc:
        if str(exc) != "webdriver_element_not_interactable":
            raise
        # WebKitWebDriver 0.55 reports the top-bar control as non-interactable
        # while the product's default CSS zoom=1.2 is active, even though the
        # control is visible.  This is a driver compatibility precondition,
        # not a business action: set the same preference through the isolated
        # WebDriver storage and then perform all business clicks by the normal
        # element endpoint.  Record this path in the evidence observation.
        selection_mode = "webdriver_compatibility_precondition"
        written = driver.execute(
            """
            if (document.documentElement.dataset.displayScale === 'standard') {
              return false;
            }
            localStorage.setItem('agent-audit.display-scale', 'standard');
            setTimeout(() => location.reload(), 0);
            return true;
            """
        )
        if written is not True:
            raise WebDriverError("display_scale_precondition_not_applied")
    deadline = time.monotonic() + timeout
    last_state: Any = None
    while time.monotonic() < deadline:
        try:
            state = driver.execute(
                """
                return {
                  scale: document.documentElement.dataset.displayScale || null,
                  zoom: getComputedStyle(document.documentElement).zoom || null,
                  stored: localStorage.getItem('agent-audit.display-scale') || null,
                };
                """
            )
            last_state = state
            if (
                isinstance(state, dict)
                and state.get("scale") == "standard"
                and state.get("stored") == "standard"
                and state.get("zoom") in {"1", "1.0"}
            ):
                state["selectionMode"] = selection_mode
                return state
        except WebDriverError:
            pass
        time.sleep(0.25)
    raise WebDriverError(f"display_scale_not_standard:{last_state!r}")


def action_counts(resource_urls: list[str]) -> dict[str, int]:
    # The app legitimately loads the persisted scan list with
    # ``GET /api/scans?limit=20`` on startup.  A resource-timing URL does not
    # expose the HTTP method, so count only the exact collection endpoint for
    # the execution action; query-bearing history reads are not a Scan.
    scan_endpoint_count = sum(
        url.split("?", 1)[0].rstrip("/").endswith("/api/scans")
        and "?limit=" not in url
        for url in resource_urls
    )
    return {
        "preview": sum("/api/document-imports/previews" in url for url in resource_urls),
        "commit": sum("/api/document-imports" in url and "/previews" not in url for url in resource_urls),
        "scan": scan_endpoint_count,
    }


def visible_window_titles() -> list[str]:
    """Return bounded titles for visible X11 windows for diagnostics only."""

    xdotool = shutil.which("xdotool")
    if xdotool is None:
        return []
    result = subprocess.run(
        [xdotool, "search", "--onlyvisible", "--name", "."],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    titles: list[str] = []
    for window_id in result.stdout.splitlines():
        window_id = window_id.strip()
        if not window_id:
            continue
        title_result = subprocess.run(
            [xdotool, "getwindowname", window_id],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        title = title_result.stdout.strip()
        if title:
            titles.append(title[:128])
    return titles[:8]


def activate_app_window(window_title: str = "知盾 AgentAudit", timeout: float = 45.0) -> str:
    """Focus the one visible packaged app window by its exact X11 title."""

    xdotool = shutil.which("xdotool")
    if xdotool is None:
        raise WebDriverError("xdotool_unavailable")
    deadline = time.monotonic() + timeout
    candidates: list[str] = []
    while time.monotonic() < deadline:
        result = subprocess.run(
            [xdotool, "search", "--onlyvisible", "--name", f"^{window_title}$"],
            text=True,
            encoding="utf-8",
            errors="strict",
            capture_output=True,
            check=False,
        )
        candidates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(candidates) == 1:
            break
        if len(candidates) > 1:
            raise WebDriverError(
                f"app_window_identity_unverified:count={len(candidates)}"
            )
        time.sleep(0.2)
    if len(candidates) != 1:
        raise WebDriverError(
            f"app_window_identity_unverified:count={len(candidates)}"
        )
    window_id = candidates[0]
    result = subprocess.run(
        [xdotool, "windowactivate", "--sync", window_id],
        text=True,
        encoding="utf-8",
        errors="strict",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise WebDriverError("app_window_activation_failed")
    return window_id


def wait_for_dialog(
    window_title: str,
    timeout: float = 20.0,
    click_result: dict[str, Any] | None = None,
) -> str:
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        raise WebDriverError("xdotool_unavailable")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if click_result is not None and click_result.get("done"):
            error = click_result.get("error")
            if isinstance(error, WebDriverError):
                raise error
            if error is not None:
                raise WebDriverError(f"webdriver_file_click_{type(error).__name__}")
            # An async Tauri command legitimately returns from the WebDriver
            # click before its native GTK chooser is mapped.  Keep polling
            # the exact title instead of treating that normal ordering as a
            # failed selection.
        result = subprocess.run(
            [xdotool, "search", "--onlyvisible", "--name", f"^{window_title}$"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        candidates = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise WebDriverError(
                f"native_dialog_identity_unverified:count={len(candidates)}"
            )
        time.sleep(0.2)
    titles = "|".join(visible_window_titles()) or "none"
    suffix = (
        ":click_returned_without_dialog"
        if click_result is not None and click_result.get("done") and click_result.get("error") is None
        else ""
    )
    raise WebDriverError(f"native_dialog_not_found:{window_title}{suffix}:visible_titles={titles}")


def choose_path_in_dialog(window_id: str, path: Path) -> None:
    xdotool = shutil.which("xdotool")
    if xdotool is None:
        raise WebDriverError("xdotool_unavailable")
    activate = subprocess.run(
        [xdotool, "windowactivate", "--sync", window_id],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if activate.returncode != 0:
        raise WebDriverError("xdotool_failed:windowactivate")

    # Send keys to the active X11 focus rather than directly to the top-level
    # frame.  GTK routes keyboard events to the focused location entry/button;
    # ``--window`` targets the frame and leaves the child widget unfocused.
    # Before every event, verify that the active window is still this exact
    # titled chooser so no unrelated application can receive the input.
    commands = [
        [xdotool, "key", "--clearmodifiers", "ctrl+l"],
        [xdotool, "type", "--clearmodifiers", "--delay", "12", str(path)],
        [xdotool, "key", "--clearmodifiers", "Return"],
        # GTK's location entry first resolves the typed path; the native
        # chooser's Open action is then activated through its keyboard
        # mnemonic.  This remains scoped to the exact titled dialog and does
        # not guess a screen coordinate or click a WebView element.
        [xdotool, "key", "--clearmodifiers", "alt+o"],
    ]
    for command in commands:
        active = subprocess.run(
            [xdotool, "getactivewindow"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        ).stdout.strip()
        if active != window_id:
            raise WebDriverError("native_dialog_focus_lost")
        result = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise WebDriverError(f"xdotool_failed:{command[1]}")

    # GTK may first commit the location entry before closing a file chooser.
    # If the mnemonic was handled after the location commit, a second Return
    # is scoped to the same titled native dialog only.
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        result = subprocess.run(
            [xdotool, "search", "--onlyvisible", "--name", "选择企业资料"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if window_id not in result.stdout.split():
            return
        active = subprocess.run(
            [xdotool, "getactivewindow"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        ).stdout.strip()
        if active != window_id:
            raise WebDriverError("native_dialog_focus_lost")
        subprocess.run(
            [xdotool, "key", "--clearmodifiers", "Return"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        time.sleep(0.25)
    raise WebDriverError("native_dialog_did_not_close")


def picker_dom_diagnostic(driver: WebDriverClient) -> dict[str, Any]:
    """Capture bounded UI state when the native chooser does not appear."""

    state = driver.execute(
        """
        const text = (element) => (element?.innerText || '').trim().slice(0, 160);
        const files = document.querySelector('[data-testid="document-import-files"]');
        return {
          errors: [...document.querySelectorAll('[data-testid="document-import-error"]')]
            .map(text).filter(Boolean).slice(0, 3),
          filesButton: files ? {
            disabled: Boolean(files.disabled),
            busy: files.getAttribute('aria-busy'),
            text: text(files),
          } : null,
          pickerOpen: Boolean(document.querySelector('[data-testid="document-import-open"]')),
          selectionCount: document.querySelectorAll('[data-testid="document-import-item"]').length,
        };
        """
    )
    return state if isinstance(state, dict) else {"state": "unavailable"}


def isolated_environment(root: Path) -> dict[str, str]:
    names = {
        "HOME": root / "home",
        "XDG_CONFIG_HOME": root / "config",
        "XDG_DATA_HOME": root / "data",
        "XDG_STATE_HOME": root / "state",
        "XDG_CACHE_HOME": root / "cache",
        "XDG_RUNTIME_DIR": root / "run",
    }
    for path in names.values():
        path.mkdir(parents=True, exist_ok=True)
    names["XDG_RUNTIME_DIR"].chmod(0o700)
    allow = {
        "PATH",
        "LANG",
        "LC_ALL",
        "DISPLAY",
        "XAUTHORITY",
        "DBUS_SESSION_BUS_ADDRESS",
    }
    env = {key: os.environ[key] for key in allow if key in os.environ}
    env.update({key: str(value) for key, value in names.items()})
    env.pop("AGENT_AUDIT_HOME", None)
    for key in (
        "AGENT_AUDIT_PROVIDER_API_KEY",
        "PROVIDER_API_KEY",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_HOST",
        "GNOME_KEYRING_CONTROL",
    ):
        env.pop(key, None)
    return env


def run_artifact_picker(
    label: str,
    application: Path,
    application_args: list[str],
    runtime_root: Path,
    synthetic_file: Path,
    driver_bin: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    env = isolated_environment(runtime_root)
    # File selection is independent of inference. Seed a saved non-secret
    # connection fixture to reach the current onboarding's documents step;
    # this is not evidence that a model connection or Readiness passed.
    provider_settings = Path(env["XDG_CONFIG_HOME"]) / "agent-audit" / "provider-settings.json"
    provider_settings.parent.mkdir(parents=True, exist_ok=True)
    provider_settings.write_text(
        json.dumps({
            "kind": "ollama",
            "baseUrl": "http://127.0.0.1:11434/v1",
            "model": "native-picker-fixture",
            "authMode": "none",
        }),
        encoding="utf-8",
    )
    env["TAURI_WEBVIEW_AUTOMATION"] = "true"
    runtime_root.mkdir(parents=True, exist_ok=True)
    driver_log_path = runtime_root / "tauri-driver.log"
    driver_log = driver_log_path.open("w", encoding="utf-8")
    try:
        driver_process = subprocess.Popen(
            [driver_bin, "--port", "4444", "--native-port", "4445"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=driver_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        group_id = os.getpgid(driver_process.pid)
    except OSError as exc:
        driver_log.close()
        if "driver_process" in locals():
            driver_process.kill()
            driver_process.wait(timeout=5)
        return check(f"{label}_native_file_selection", "failed", f"driver_start_{type(exc).__name__}"), {
            "application": application.name,
            "displayName": synthetic_file.name,
            "driver": "tauri-driver",
            "nativeDriver": "WebKitWebDriver",
            "nativeControl": "xdotool",
            "initialActions": {"preview": 0, "commit": 0, "scan": 0},
        }
    driver = WebDriverClient("http://127.0.0.1:4444")
    observation: dict[str, Any] = {
        "application": application.name,
        "displayName": synthetic_file.name,
        "driver": "tauri-driver",
        "nativeDriver": "WebKitWebDriver",
        "nativeControl": "xdotool",
        "providerPrecondition": {
            "type": "saved_non_secret_settings_fixture",
            "inferenceVerified": False,
            "readinessVerified": False,
        },
        "initialActions": {
            "preview": 0,
            "commit": 0,
            "scan": 0,
        },
    }
    try:
        stage = "driver_ready"
        if not wait_for_port("http://127.0.0.1:4444/status", timeout=30):
            return check(f"{label}_native_file_selection", "failed", "tauri_driver_unavailable"), observation
        stage = "create_session"
        driver.create_session(application, application_args)
        stage = "activate_window"
        activate_app_window()
        observation["appWindowActivated"] = True
        stage = "select_display_scale"
        observation["displayScale"] = select_standard_display_scale(driver)
        stage = "choose_onboarding_path"
        path_selector = "[data-testid='onboarding-custom']"
        wait_for_element(driver, path_selector)
        driver.scroll_into_view(path_selector)
        driver.click(wait_for_element(driver, path_selector))
        stage = "open_document_import"
        open_element = wait_for_element(driver, "[data-testid='document-import-open']")
        initial_actions = action_counts(driver.resource_urls())
        observation["initialActions"] = initial_actions
        if initial_actions != {"preview": 0, "commit": 0, "scan": 0}:
            return check(f"{label}_native_file_selection", "failed", "implicit_action_on_initial_load"), observation
        # The packaged window opens at 1600x1000 while the full onboarding
        # page is taller.  Scroll through WebDriver before its native click
        # command; this keeps interaction in the real WebView and avoids
        # using xdotool for application controls.
        driver.scroll_into_view("[data-testid='document-import-open']")
        open_element = wait_for_element(driver, "[data-testid='document-import-open']")
        driver.click(open_element)
        stage = "open_native_file_chooser"
        files_element = wait_for_element(driver, "[data-testid='document-import-files']")
        driver.scroll_into_view("[data-testid='document-import-files']")
        files_element = wait_for_element(driver, "[data-testid='document-import-files']")

        # WebDriver's native click command blocks while the application waits
        # for the GTK chooser.  Keep that exact command in a daemon thread
        # while xdotool operates only on the exact titled native dialog.
        click_result: dict[str, Any] = {"done": False, "error": None}

        def click_files() -> None:
            try:
                driver.click(files_element)
            except Exception as exc:  # propagate the driver diagnostic below
                click_result["error"] = exc
            finally:
                click_result["done"] = True

        click_thread = threading.Thread(target=click_files, name="webdriver-file-click", daemon=True)
        click_thread.start()
        try:
            window_id = wait_for_dialog("选择企业资料", click_result=click_result)
        except WebDriverError:
            observation["clickThread"] = {
                "done": bool(click_result["done"]),
                "error": (
                    (
                        f"WebDriverError:{click_result['error']}"
                        if isinstance(click_result["error"], WebDriverError)
                        else type(click_result["error"]).__name__
                    )
                    if click_result["error"] is not None
                    else None
                ),
            }
            try:
                observation["dialogDiagnostic"] = picker_dom_diagnostic(driver)
            except WebDriverError:
                observation["dialogDiagnostic"] = {"state": "webdriver_unavailable"}
            raise
        stage = "select_native_file"
        choose_path_in_dialog(window_id, synthetic_file)
        stage = "verify_selected_file"
        click_thread.join(timeout=15)
        if not click_result["done"]:
            raise WebDriverError("webdriver_file_click_timeout")
        if click_result["error"] is not None:
            error = click_result["error"]
            if isinstance(error, WebDriverError):
                raise error
            raise WebDriverError(f"webdriver_file_click_{type(error).__name__}")
        item = wait_for_element(driver, "[data-testid='document-import-item']")
        item_text = driver.text(item)
        observation["selectedItemText"] = item_text
        if synthetic_file.name not in item_text:
            return check(f"{label}_native_file_selection", "failed", "selected_item_not_returned"), observation
        # No selection operation is allowed to implicitly enter a later stage.
        selection_actions = action_counts(driver.resource_urls())
        observation["selectionActions"] = selection_actions
        if selection_actions != {"preview": 0, "commit": 0, "scan": 0}:
            return check(f"{label}_native_file_selection", "failed", "implicit_action_on_selection"), observation
        if driver.find_all("[data-testid='document-import-preview']"):
            return check(f"{label}_native_file_selection", "failed", "preview_started_on_selection"), observation
        if driver.find_all("[data-testid='document-import-result']"):
            return check(f"{label}_native_file_selection", "failed", "commit_result_on_selection"), observation
        observation["returnedToWebView"] = True
        return check(f"{label}_native_file_selection", "passed"), observation
    except WebDriverError as exc:
        observation["failureStage"] = stage
        observation["driverExitCode"] = driver_process.poll()
        observation["driverGroupMemberCount"] = len(process_group_members(group_id))
        return check(f"{label}_native_file_selection", "failed", str(exc)), observation
    finally:
        driver.close()
        stop_process_group(driver_process, group_id)
        driver_log.close()
        if "failureStage" in observation and driver_log_path.is_file():
            lines = driver_log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            observation["driverLogTail"] = [
                line.replace(str(runtime_root), "<runtime>")
                .replace(str(application), "<application>")[:400]
                for line in lines[-40:]
            ]


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--appimage", type=Path, required=True)
    parser.add_argument("--deb", type=Path, required=True)
    parser.add_argument("--deb-desktop", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--driver", default=os.environ.get("TAURI_DRIVER_BIN", "tauri-driver"))
    args = parser.parse_args()

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, str]] = []
    observations: dict[str, Any] = {}
    if platform.system().lower() != "linux" or platform.machine() != "x86_64":
        checks.extend(
            [
                check("appimage_native_file_selection", "not_verified", "linux_x86_64_required"),
                check("deb_native_file_selection", "not_verified", "linux_x86_64_required"),
            ]
        )
    else:
        driver = shutil.which(args.driver) if os.path.basename(args.driver) == args.driver else args.driver
        webdriver = shutil.which("WebKitWebDriver")
        xdotool = shutil.which("xdotool")
        if driver is None or not Path(driver).is_file() or webdriver is None or xdotool is None:
            missing = ",".join(
                name
                for name, value in (
                    ("tauri-driver", driver),
                    ("WebKitWebDriver", webdriver),
                    ("xdotool", xdotool),
                )
                if value is None
            )
            detail = f"runner_dependency_unavailable:{missing or 'driver'}"
            checks.extend(
                [
                    check("appimage_native_file_selection", "not_verified", detail),
                    check("deb_native_file_selection", "not_verified", detail),
                ]
            )
        else:
            with tempfile.TemporaryDirectory(prefix="agent-audit-linux-picker-") as raw:
                root = Path(raw)
                synthetic = root / "synthetic-picker.md"
                synthetic.write_text(
                    "F-055 isolated synthetic file selection evidence.\n", encoding="utf-8"
                )
                app_status, app_observation = run_artifact_picker(
                    "appimage",
                    args.appimage.resolve(),
                    ["--appimage-extract-and-run"],
                    root / "appimage-runtime",
                    synthetic,
                    str(driver),
                )
                deb_status, deb_observation = run_artifact_picker(
                    "deb",
                    args.deb_desktop.resolve(),
                    [],
                    root / "deb-runtime",
                    synthetic,
                    str(driver),
                )
                checks.extend([app_status, deb_status])
                observations.update(
                    {"appimage": app_observation, "deb": deb_observation}
                )

    artifacts = []
    for path in (args.appimage.resolve(), args.deb.resolve()):
        if path.is_file() and not path.is_symlink():
            artifacts.append({"name": path.name, "sha256": sha256(path), "sizeBytes": path.stat().st_size})
    counts = {status: sum(item["status"] == status for item in checks) for status in STATUS_VALUES}
    status = "failed" if counts["failed"] else ("incomplete" if counts["not_verified"] else "passed")
    payload = {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "status": status,
        "tool": "tauri-driver+WebKitWebDriver+xdotool",
        "artifacts": artifacts,
        "checks": checks,
        "observations": observations,
        "boundaries": [
            "The file chooser was a real GTK native dialog from the packaged desktop artifact.",
            "WebView controls were located by data-testid through official Tauri WebDriver tooling.",
            "The synthetic file contains no enterprise data and no browser test transport was installed.",
        ],
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
