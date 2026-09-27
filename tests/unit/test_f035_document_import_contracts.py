"""F-035 document format, diagnostic, plan and atomicity contracts.

The native picker is responsible for turning PDF/DOCX bytes into normalized
UTF-8 text.  These tests exercise the API trust boundary with the exact
standardized payload that the picker returns; native byte parsing is covered
separately by the Desktop smoke/contract tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import agent_audit_api.document_import as document_import_module
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.document_import import (
    DocumentImportCommitRequest,
    DocumentImportDraft,
    DocumentImportMetadata,
    DocumentImportPreviewRequest,
    DocumentImportService,
    DocumentImportSource,
    DocumentImportStorageError,
    MAX_DOCUMENT_SIZE_BYTES,
)
from agent_audit_api.planning import ContractAttackPlanner
from agent_audit_api.retrieval import ReloadableRetriever, TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.tools import MockCustomerExportTool, MockCustomerTool, MockMailTool
from agent_audit_api.workspace import WorkspaceService


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def _metadata(title: str, *, scope: str = "general") -> DocumentImportMetadata:
    return DocumentImportMetadata(
        title=title,
        sensitivity="confidential" if scope != "general" else "public",
        business_scope=scope,  # type: ignore[arg-type]
        owner_id=None,
        trust_level="trusted",
    )


def _source(
    source_id: str,
    name: str,
    content: str | None,
    *,
    extension: str | None = None,
    size_bytes: int | None = None,
    status: str | None = None,
    diagnostic: str | None = None,
    diagnostic_code: str | None = None,
) -> DocumentImportSource:
    suffix = extension or Path(name).suffix
    actual_size = len(content.encode("utf-8")) if content is not None else 0
    return DocumentImportSource(
        source_id=source_id,
        display_name=name,
        relative_path=f"selected/{name}",
        extension=suffix,
        size_bytes=actual_size if size_bytes is None else size_bytes,
        content=content,
        diagnostic=diagnostic,
        status=status,  # type: ignore[arg-type]
        diagnostic_code=diagnostic_code,  # type: ignore[arg-type]
    )


def _draft(source: DocumentImportSource, title: str | None = None) -> DocumentImportDraft:
    return DocumentImportDraft(
        source=source,
        metadata=_metadata(title or source.display_name.rsplit(".", 1)[0]),
    )


def _service(
    tmp_path: Path,
    *,
    contract=None,
    with_tools: bool = True,
) -> tuple[object, DocumentImportService, ReloadableRetriever]:
    workspace = WorkspaceService().create(
        tmp_path / "workspace",
        "F-035 format test Workspace",
        seed_dir=DEMO_SEED,
    )
    data = load_demo_data(workspace.documents_path)
    initial = TfidfRetriever(data.documents)
    retriever = ReloadableRetriever(
        initial,
        factory=lambda documents: TfidfRetriever(documents),
    )
    service = DocumentImportService(
        workspace=workspace,
        actors=data.actors,
        documents=data.documents,
        contract=contract or load_security_contract(workspace.contract_path),
        retriever=retriever,
        customers=data.customers,
        customer_tool=MockCustomerTool(data.customers) if with_tools else None,
        mail_tool=MockMailTool() if with_tools else None,
        export_tool=MockCustomerExportTool(data.customers) if with_tools else None,
    )
    return workspace, service, retriever


@pytest.mark.parametrize(
    ("extension", "content", "size_bytes"),
    [
        (".txt", "F-035 plain text business note", None),
        (".md", "# F-035 Markdown\n业务流程说明", None),
        # PDF/DOCX content is already normalized by the native picker.  Their
        # source byte size intentionally differs from extracted UTF-8 length.
        (".pdf", "F-035 PDF extracted business note", 1_024),
        (".docx", "F-035 DOCX extracted business note", 2_048),
    ],
)
def test_normalized_payload_for_txt_md_pdf_docx_is_ready(
    tmp_path: Path,
    extension: str,
    content: str,
    size_bytes: int | None,
) -> None:
    _workspace, service, _retriever = _service(tmp_path, with_tools=False)
    name = f"业务资料{extension}"
    source = _source(
        f"ready-{extension[1:]}",
        name,
        content,
        extension=extension,
        size_bytes=size_bytes,
    )

    preview = service.preview(
        DocumentImportPreviewRequest(documents=[_draft(source)])
    )

    item = preview.items[0]
    assert item.status == "ready"
    assert item.diagnostic is None
    assert item.diagnostic_code is None
    assert item.content_preview == content


@pytest.mark.parametrize(
    ("extension", "diagnostic_code", "diagnostic"),
    [
        (".pdf", "encrypted", "文档已加密，当前版本无法读取"),
        (".pdf", "no_text", "文档不包含可提取文本"),
        (".pdf", "parse_failed", "PDF 文档解析失败"),
        (".docx", "invalid_utf8", "DOCX 文本编码无效"),
        (".docx", "read_failed", "无法读取 DOCX 文档"),
    ],
)
def test_each_picker_diagnostic_code_is_an_invalid_item(
    tmp_path: Path,
    extension: str,
    diagnostic_code: str,
    diagnostic: str,
) -> None:
    _workspace, service, _retriever = _service(tmp_path, with_tools=False)
    source = _source(
        f"invalid-{diagnostic_code}",
        f"坏资料{extension}",
        None,
        extension=extension,
        status="ready",
        diagnostic=diagnostic,
        diagnostic_code=diagnostic_code,
    )

    item = service.preview(
        DocumentImportPreviewRequest(documents=[_draft(source)])
    ).items[0]

    assert item.status == "invalid"
    assert item.diagnostic_code == diagnostic_code
    assert item.diagnostic == diagnostic
    assert item.content_preview is None
    assert item.authorization == []


def test_diagnostic_keeps_real_reason_but_never_echoes_absolute_source_path(
    tmp_path: Path,
) -> None:
    _workspace, service, _retriever = _service(tmp_path, with_tools=False)
    source = _source(
        "path-hidden",
        "unreadable.pdf",
        None,
        extension=".pdf",
        diagnostic_code="read_failed",
        diagnostic=r"读取 C:\Users\operator\Secrets\unreadable.pdf 失败",
    )

    item = service.preview(
        DocumentImportPreviewRequest(documents=[_draft(source)])
    ).items[0]

    assert item.status == "invalid"
    assert item.diagnostic_code == "read_failed"
    assert item.diagnostic == "无法读取文件，请检查文件权限"
    assert "C:\\Users" not in item.diagnostic


def test_api_recomputes_status_and_rejects_stale_native_hints(
    tmp_path: Path,
) -> None:
    _workspace, service, _retriever = _service(tmp_path, with_tools=False)
    valid = _source(
        "stale-invalid",
        "valid.md",
        "valid content",
        status="invalid",
    )
    encrypted = _source(
        "stale-ready",
        "encrypted.pdf",
        None,
        extension=".pdf",
        status="ready",
        diagnostic_code="encrypted",
    )

    preview = service.preview(
        DocumentImportPreviewRequest(documents=[_draft(valid), _draft(encrypted)])
    )

    assert [item.status for item in preview.items] == ["ready", "invalid"]
    assert preview.items[0].diagnostic_code is None
    assert preview.items[1].diagnostic_code == "encrypted"


def test_oversize_and_unsupported_items_have_distinct_status_codes(
    tmp_path: Path,
) -> None:
    _workspace, service, _retriever = _service(tmp_path, with_tools=False)
    oversized = _source(
        "oversized",
        "large.docx",
        "small normalized text",
        extension=".docx",
        size_bytes=MAX_DOCUMENT_SIZE_BYTES + 1,
        status="ready",
        diagnostic_code="too_large",
        diagnostic="单个文件不能超过 2 MiB",
    )
    unsupported = _source(
        "unsupported",
        "image.png",
        None,
        extension=".png",
    )

    preview = service.preview(
        DocumentImportPreviewRequest(
            documents=[_draft(oversized), _draft(unsupported)]
        )
    )

    assert [item.status for item in preview.items] == ["invalid", "unsupported"]
    assert [item.diagnostic_code for item in preview.items] == [
        "too_large",
        "unsupported_format",
    ]
    assert all(item.authorization == [] for item in preview.items)


def test_executable_plan_summaries_are_projected_from_real_active_plans(
    tmp_path: Path,
) -> None:
    _workspace, service, _retriever = _service(tmp_path, with_tools=True)
    data = load_demo_data()
    contract = load_security_contract()
    expected = ContractAttackPlanner(
        contract=contract,
        actors=data.actors,
        documents=data.documents,
        customers=data.customers,
        customer_tool=MockCustomerTool(data.customers),
        mail_tool=MockMailTool(),
        export_tool=MockCustomerExportTool(data.customers),
    ).plan()

    preview = service.preview(
        DocumentImportPreviewRequest(
            documents=[
                _draft(
                    _source("plan-input", "plan-input.md", "plan input"),
                    "Plan input",
                )
            ]
        )
    )
    summaries = {summary.id: summary for summary in preview.executable_plans}

    assert set(summaries) == {plan.id for plan in expected}
    assert preview.plan_diagnostic is None
    for plan in expected:
        summary = summaries[plan.id]
        for field in (
            "id",
            "name",
            "description",
            "basis_type",
            "basis_rule_id",
            "attacker_type",
            "actor_id",
            "target_kind",
            "target_id",
            "target_profile_id",
        ):
            assert getattr(summary, field) == getattr(plan, field)
        assert "message" not in summary.model_dump()


def test_no_plan_reports_active_contract_gap_instead_of_fabricating_a_plan(
    tmp_path: Path,
) -> None:
    active = load_security_contract()
    contract_without_rules = active.model_copy(
        update={"resource_rules": [], "tool_rules": [], "sink_rules": []}
    )
    _workspace, service, _retriever = _service(
        tmp_path,
        contract=contract_without_rules,
        with_tools=True,
    )

    preview = service.preview(
        DocumentImportPreviewRequest(
            documents=[_draft(_source("no-plan", "no-plan.md", "content"))]
        )
    )

    assert preview.executable_plans == []
    assert preview.plan_diagnostic == (
        "当前 active Contract 没有可执行的 Resource、Tool 或 Sink Rule"
    )


def test_batch_commit_keeps_exception_item_and_confirmed_metadata(
    tmp_path: Path,
) -> None:
    workspace, service, retriever = _service(tmp_path, with_tools=False)
    before_count = retriever.indexed_document_count
    finance_source = _source(
        "batch-finance",
        "预算.docx",
        "batch finance content",
        extension=".docx",
        size_bytes=777,
    )
    public_source = _source(
        "batch-public",
        "说明.txt",
        "batch public content",
    )
    failed_source = _source(
        "batch-failed",
        "空白.pdf",
        " ",
        extension=".pdf",
        size_bytes=111,
        diagnostic_code="no_text",
        diagnostic="文档不包含可提取文本",
    )
    finance_draft = DocumentImportDraft(
        source=finance_source,
        metadata=DocumentImportMetadata(
            title="确认后的财务资料",
            sensitivity="confidential",
            business_scope="finance",
            owner_id="finance_001",
            trust_level="trusted",
        ),
    )
    public_draft = _draft(public_source, "确认后的公开说明")
    failed_draft = _draft(failed_source, "例外项")

    result = service.commit(
        DocumentImportCommitRequest(
            documents=[finance_draft, public_draft, failed_draft]
        )
    )

    assert [item.title for item in result.imported] == [
        "确认后的财务资料",
        "确认后的公开说明",
    ]
    assert result.imported[0].labels == ["confidential", "finance"]
    assert result.imported[0].owner_id == "finance_001"
    assert result.skipped[0].source_id == "batch-failed"
    assert result.skipped[0].status == "invalid"
    assert result.skipped[0].diagnostic_code == "no_text"
    assert result.retriever.indexed_document_count == before_count + 2
    assert len(json.loads(workspace.documents_file_path.read_text(encoding="utf-8"))) == before_count + 2


def test_storage_failure_preserves_catalog_retriever_and_service_documents(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace, service, retriever = _service(tmp_path, with_tools=False)
    before_catalog = workspace.documents_file_path.read_text(encoding="utf-8")
    before_current = retriever.current
    before_documents = service.documents

    def fail_storage(_path: Path, _documents) -> None:
        raise DocumentImportStorageError("synthetic catalog write failure")

    monkeypatch.setattr(document_import_module, "_atomic_write_documents", fail_storage)

    with pytest.raises(DocumentImportStorageError, match="synthetic catalog write failure"):
        service.commit(
            DocumentImportCommitRequest(
                documents=[_draft(_source("atomic", "atomic.md", "atomic content"))]
            )
        )

    assert workspace.documents_file_path.read_text(encoding="utf-8") == before_catalog
    assert retriever.current is before_current
    assert service.documents == before_documents
