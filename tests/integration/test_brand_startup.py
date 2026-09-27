"""F-030 brand asset and real desktop splash lifecycle checks."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MASTER = REPOSITORY_ROOT / "artifacts" / "visuals" / "brand-f030" / "agent-audit-mark-master.png"
WEB_MARK = REPOSITORY_ROOT / "apps" / "web" / "src" / "assets" / "agent-audit-mark.png"
SPLASH_ARTWORK = (
    REPOSITORY_ROOT
    / "apps"
    / "web"
    / "src"
    / "assets"
    / "illustrations"
    / "splash-local-workspace.webp"
)
DESKTOP_MARK = REPOSITORY_ROOT / "apps" / "desktop" / "icon.png"
TAURI_ROOT = REPOSITORY_ROOT / "apps" / "desktop" / "src-tauri"


def test_selected_rgba_master_is_used_without_a_white_frame() -> None:
    assert MASTER.read_bytes() == WEB_MARK.read_bytes() == DESKTOP_MARK.read_bytes()

    with Image.open(MASTER) as image:
        assert image.mode == "RGBA"
        assert image.size == (1254, 1254)
        alpha = image.getchannel("A")
        assert alpha.getextrema() == (0, 255)
        assert all(
            alpha.getpixel(point) <= 1
            for point in ((0, 0), (1253, 0), (0, 1253), (1253, 1253))
        )
        assert alpha.getpixel((627, 627)) >= 250


def test_platform_icons_are_mechanical_derivatives_of_the_selected_mark() -> None:
    required = (
        TAURI_ROOT / "icons" / "32x32.png",
        TAURI_ROOT / "icons" / "128x128.png",
        TAURI_ROOT / "icons" / "icon.png",
        TAURI_ROOT / "icons" / "icon.ico",
        TAURI_ROOT / "icons" / "icon.icns",
    )
    assert all(path.is_file() and path.stat().st_size > 0 for path in required)

    with Image.open(required[0]) as icon:
        assert icon.convert("RGBA").size == (32, 32)
        assert icon.convert("RGBA").getpixel((0, 0))[3] <= 1


def test_web_brand_and_splash_use_the_same_local_asset() -> None:
    app = (REPOSITORY_ROOT / "apps" / "web" / "src" / "App.vue").read_text(
        encoding="utf-8"
    )
    splash = (REPOSITORY_ROOT / "apps" / "web" / "src" / "splash.ts").read_text(
        encoding="utf-8"
    )
    vite = (REPOSITORY_ROOT / "apps" / "web" / "vite.config.ts").read_text(
        encoding="utf-8"
    )

    assert 'from "./assets/agent-audit-mark.png"' in app
    assert 'from "./assets/agent-audit-mark.png"' in splash
    assert '<div class="brand-mark" aria-hidden="true">盾</div>' not in app
    assert 'splash: "splash.html"' in vite
    assert "http://" not in splash and "https://" not in splash


def test_splash_uses_the_local_workspace_artwork_without_changing_runtime_truth() -> None:
    splash_html = (REPOSITORY_ROOT / "apps" / "web" / "splash.html").read_text(
        encoding="utf-8"
    )
    splash = (REPOSITORY_ROOT / "apps" / "web" / "src" / "splash.ts").read_text(
        encoding="utf-8"
    )
    styles = (REPOSITORY_ROOT / "apps" / "web" / "src" / "splash.css").read_text(
        encoding="utf-8"
    )

    with Image.open(SPLASH_ARTWORK) as artwork:
        assert artwork.size == (1440, 880)
        assert artwork.format == "WEBP"

    assert 'id="splash-workspace"' in splash_html
    assert 'from "./assets/illustrations/splash-local-workspace.webp"' in splash
    assert 'document.body.dataset.runtimeState = status.state' in splash
    assert 'body[data-runtime-state="ready"] .splash-artwork' in styles
    assert 'body[data-runtime-state="failed"] .splash-artwork' in styles
    assert 'body[data-runtime-state="stopped"] .splash-artwork' in styles
    assert "prefers-reduced-motion: reduce" in styles


def test_splash_projects_real_sidecar_state_and_closes_before_main_is_shown() -> None:
    splash = (REPOSITORY_ROOT / "apps" / "web" / "src" / "splash.ts").read_text(
        encoding="utf-8"
    )
    native = (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")

    assert 'invoke<DesktopRuntimeStatus>("get_desktop_runtime_status")' in splash
    assert 'invoke("quit_application")' in splash
    assert "setTimeout" in splash
    assert "%" not in splash

    assert 'WebviewUrl::App("splash.html".into())' in native
    assert "status: Mutex::new(DesktopRuntimeStatus::launching())" in native
    assert 'app.get_webview_window("splashscreen")' in native
    assert 'app.get_webview_window("main")' in native
    assert native.index('splash.close()') < native.index('window.show()')
    assert "fn quit_application" in native
    assert 'window.label() == "main"' in native


def test_splash_failure_separates_user_guidance_from_technical_detail() -> None:
    splash_html = (REPOSITORY_ROOT / "apps" / "web" / "splash.html").read_text(
        encoding="utf-8"
    )
    splash = (REPOSITORY_ROOT / "apps" / "web" / "src" / "splash.ts").read_text(
        encoding="utf-8"
    )
    styles = (REPOSITORY_ROOT / "apps" / "web" / "src" / "splash.css").read_text(
        encoding="utf-8"
    )

    assert 'id="startup-guidance"' in splash_html
    assert 'id="startup-impact"' in splash_html
    assert 'id="startup-recovery"' in splash_html
    assert 'id="startup-technical"' in splash_html
    assert 'id="startup-technical-message"' in splash_html
    assert "本次审计尚未开始" in splash
    assert "不会因此被删除或覆盖" in splash
    assert "请退出应用后" in splash
    assert "technicalDetail: status.message" in splash
    assert "detailText.textContent = status.message" not in splash
    assert ".startup-technical pre" in styles
    assert "white-space: pre-wrap" in styles
