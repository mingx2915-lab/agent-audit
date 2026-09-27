"""F-028 native file/folder picker boundary checks.

The picker is Rust/Tauri code and is not invoked during Python tests.  These
checks keep the source-level contract narrow: only explicit selections cross
into the renderer, while absolute paths remain native-only.
"""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
NATIVE_SOURCE = (
    REPOSITORY_ROOT / "apps" / "desktop" / "src-tauri" / "src" / "lib.rs"
).read_text(encoding="utf-8")


def test_native_commands_are_explicit_file_and_folder_choices() -> None:
    assert "fn select_document_files" in NATIVE_SOURCE
    assert "fn select_document_folder" in NATIVE_SOURCE
    assert ".dialog()" in NATIVE_SOURCE
    assert ".file()" in NATIVE_SOURCE
    assert "blocking_pick_files" in NATIVE_SOURCE
    assert "blocking_pick_folder" in NATIVE_SOURCE
    assert "select_document_files," in NATIVE_SOURCE
    assert "select_document_folder" in NATIVE_SOURCE


def test_native_picker_returns_cancel_as_an_empty_selection() -> None:
    # Both native dialogs use the same explicit cancel semantics.  This keeps
    # cancellation a local UI action rather than an API commit.
    assert NATIVE_SOURCE.count("return Ok(Vec::new());") >= 1
    assert "let Some(selected) = selected else" in NATIVE_SOURCE
    assert "let Some(selected) = selected else" in NATIVE_SOURCE


def test_native_boundary_only_returns_relative_metadata_and_text_content() -> None:
    assert "relative_path" in NATIVE_SOURCE
    assert 'replace(\'\\\\\', "/")' in NATIVE_SOURCE
    assert "strip_prefix(root)" in NATIVE_SOURCE
    assert "content: Option<String>" in NATIVE_SOURCE
    assert "String::from_utf8(bytes)" in NATIVE_SOURCE
    assert "文件不是有效的 UTF-8 文本" in NATIVE_SOURCE
    assert "当前版本支持 PDF、DOCX、UTF-8 .txt 和 .md" in NATIVE_SOURCE
    assert "status: Option<String>" in NATIVE_SOURCE
    assert "diagnostic_code: Option<String>" in NATIVE_SOURCE

    # No native Path/PathBuf field is serialized as part of the DTO.  The
    # selected absolute path is used only inside the command implementation.
    struct_start = NATIVE_SOURCE.index("struct DocumentImportSource")
    struct_end = NATIVE_SOURCE.index("}\n\n#[derive", struct_start)
    struct_body = NATIVE_SOURCE[struct_start:struct_end]
    assert "Path" not in struct_body
    assert "PathBuf" not in struct_body
    assert "absolute" not in struct_body.lower()


def test_native_picker_has_locked_format_and_count_size_limits() -> None:
    assert "const MAX_DOCUMENT_IMPORT_ITEMS: usize = 50;" in NATIVE_SOURCE
    assert "const MAX_DOCUMENT_SOURCE_BYTES: u64 = 20 * 1024 * 1024;" in NATIVE_SOURCE
    assert "const MAX_DOCUMENT_TEXT_BYTES: usize = 2 * 1024 * 1024;" in NATIVE_SOURCE
    assert "const MAX_DOCX_XML_BYTES: usize = 16 * 1024 * 1024;" in NATIVE_SOURCE
    assert "selected.len() > MAX_DOCUMENT_IMPORT_ITEMS" in NATIVE_SOURCE
    assert "files.len() > MAX_DOCUMENT_IMPORT_ITEMS" in NATIVE_SOURCE
    assert "size_bytes > MAX_DOCUMENT_SOURCE_BYTES" in NATIVE_SOURCE
    assert 'matches!(extension.as_str(), ".txt" | ".md" | ".pdf" | ".docx")' in NATIVE_SOURCE
    assert 'add_filter("业务文档", &["pdf", "docx", "txt", "md"])' in NATIVE_SOURCE


def test_native_parser_extracts_pdf_and_docx_without_network_or_macro_execution() -> None:
    """Keep the real parser boundary visible in the Desktop implementation.

    The parser helpers are private Rust functions and therefore cannot be
    called from the Python unit suite.  This source contract complements the
    conditional real-artifact smoke: PDF text comes from ``pdf-extract`` and
    DOCX reads only ``word/document.xml`` through ``quick-xml``.
    """

    assert "pdf_extract::Document::load_mem" in NATIVE_SOURCE
    assert "pdf_extract::output_doc" in NATIVE_SOURCE
    assert "ZipArchive::new" in NATIVE_SOURCE
    assert 'by_name("word/document.xml")' in NATIVE_SOURCE
    assert "quick_xml::events::Event" in NATIVE_SOURCE
    assert "Reader::from_reader" in NATIVE_SOURCE
    assert "document.encrypted()" in NATIVE_SOURCE
    assert '"encrypted"' in NATIVE_SOURCE
    assert '"no_text"' in NATIVE_SOURCE
    assert '"parse_failed"' in NATIVE_SOURCE
    assert '"too_large"' in NATIVE_SOURCE
    assert "open::that" not in NATIVE_SOURCE
    assert "tauri-plugin-opener" not in NATIVE_SOURCE


def test_native_parser_has_executable_cfg_test_coverage_for_real_minimal_inputs() -> None:
    """Require parser coverage to live beside the private Rust helpers.

    Python cannot call the private Tauri parser without turning the test-only
    seam into a fake parser.  The Desktop crate therefore owns executable
    ``cfg(test)`` fixtures for the real PDF/DOCX libraries and their boundary
    diagnostics; this gate prevents that coverage from silently disappearing.
    """

    assert "#[cfg(test)]\nmod tests" in NATIVE_SOURCE
    for test_name in (
        "extracts_pdf_text_and_reports_empty_or_corrupt_documents",
        "extracts_docx_text_and_rejects_corrupt_or_ole_packages",
        "reports_structured_pdf_encryption_and_enforces_text_limits",
        "enforces_raw_source_boundary_and_folder_skips_are_itemized",
    ):
        assert f"fn {test_name}()" in NATIVE_SOURCE
    assert "minimal_pdf(\"Hello PDF\")" in NATIVE_SOURCE
    assert "minimal_docx(xml)" in NATIVE_SOURCE
    assert "encrypted_pdf()" in NATIVE_SOURCE
    assert "read_selected_folder(folder.clone())" in NATIVE_SOURCE


def test_native_picker_does_not_expose_an_arbitrary_target_or_browser_open() -> None:
    assert '"--target"' not in NATIVE_SOURCE
    assert "open::that" not in NATIVE_SOURCE
    assert "tauri-plugin-opener" not in NATIVE_SOURCE
