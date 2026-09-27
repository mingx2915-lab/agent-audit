from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs"
WEB_NATIVE = ROOT / "apps" / "web" / "src" / "native.ts"


def test_native_diagnostics_save_is_zip_only_bounded_and_explicit() -> None:
    source = NATIVE.read_text(encoding="utf-8")
    assert "const MAX_DIAGNOSTICS_ARCHIVE_BYTES: usize = 16 * 1024 * 1024;" in source
    assert "fn save_diagnostics_archive(" in source
    assert '.add_filter("AgentAudit 本地诊断包", &["zip"])' in source
    assert "诊断包建议文件名必须是不含路径的 .zip 文件名" in source
    assert "诊断包必须保存为 .zip 文件" in source
    assert "return Ok(false);" in source


def test_native_diagnostics_save_is_create_new_no_clobber_and_never_overwrites() -> None:
    source = NATIVE.read_text(encoding="utf-8")
    section = source[
        source.index("fn write_new_diagnostics_archive") : source.index(
            "fn save_diagnostics_archive"
        )
    ]
    assert "if target.exists()" in section
    assert ".create_new(true)" in section
    assert "file.sync_all()" in section
    assert "fs::hard_link(&temporary, target)" in section
    assert "fs::remove_file(&temporary)" in section
    assert "fs::remove_file(&temporary)" in section
    assert "fs::write(target" not in section
    assert "fs::rename(&temporary, target)" not in section
    assert ".truncate(true)" not in section


def test_web_native_has_no_browser_filesystem_fallback() -> None:
    source = WEB_NATIVE.read_text(encoding="utf-8")
    assert 'invoke<boolean>("save_diagnostics_archive"' in source
    assert "诊断包原生保存需要桌面窗口" in source
    assert "setDiagnosticsTransport" in source
    assert "writeFile" not in source
