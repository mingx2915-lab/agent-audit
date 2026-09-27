"""F-028 document import service and Workspace snapshot contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.document_import import (
    DocumentImportCommitRequest,
    DocumentImportDraft,
    DocumentImportError,
    DocumentImportMetadata,
    DocumentImportPreviewRequest,
    DocumentImportService,
    DocumentImportSource,
    DocumentImportWorkspaceError,
    MAX_DOCUMENT_SIZE_BYTES,
)
from agent_audit_api.retrieval import ReloadableRetriever, RetrieverError, TfidfRetriever
from agent_audit_api.security_contract import load_security_contract
from agent_audit_api.workspace import WorkspaceService


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def _workspace(tmp_path: Path):
    return WorkspaceService().create(
        tmp_path / "workspace",
        "F-028 import test Workspace",
        seed_dir=DEMO_SEED,
    )


def _source(
    source_id: str,
    name: str,
    content: str | None,
    *,
    extension: str | None = None,
    relative_path: str | None = None,
    size_bytes: int | None = None,
    diagnostic: str | None = None,
) -> DocumentImportSource:
    suffix = extension or Path(name).suffix
    actual_size = len(content.encode("utf-8")) if content is not None else 0
    return DocumentImportSource(
        source_id=source_id,
        display_name=name,
        relative_path=relative_path or name,
        extension=suffix,
        size_bytes=actual_size if size_bytes is None else size_bytes,
        content=content,
        diagnostic=diagnostic,
    )


def _metadata(
    title: str,
    *,
    sensitivity: str = "public",
    business_scope: str = "general",
    owner_id: str | None = None,
    trust_level: str = "trusted",
) -> DocumentImportMetadata:
    return DocumentImportMetadata(
        title=title,
        sensitivity=sensitivity,  # type: ignore[arg-type]
        business_scope=business_scope,  # type: ignore[arg-type]
        owner_id=owner_id,
        trust_level=trust_level,  # type: ignore[arg-type]
    )


def _draft(
    source: DocumentImportSource,
    metadata: DocumentImportMetadata | None = None,
) -> DocumentImportDraft:
    return DocumentImportDraft(
        source=source,
        metadata=metadata or _metadata(source.display_name.rsplit(".", 1)[0]),
    )


def _service(tmp_path: Path) -> tuple[object, DocumentImportService, ReloadableRetriever]:
    workspace = _workspace(tmp_path)
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
        contract=load_security_contract(workspace.contract_path),
        retriever=retriever,
    )
    return workspace, service, retriever


def test_preview_is_side_effect_free_and_returns_statuses_and_contract_matrix(
    tmp_path: Path,
) -> None:
    workspace, service, retriever = _service(tmp_path)
    before_catalog = workspace.documents_file_path.read_text(encoding="utf-8")
    before_manifest = workspace.manifest_path.read_text(encoding="utf-8")
    before_retriever = retriever.current

    ready = _draft(
        _source(
            "import-ready",
            "预算说明.md",
            "2026 财务预算说明，仅供受控验收使用。",
            relative_path="部门/预算说明.md",
        ),
        _metadata(
            "受控预算说明",
            sensitivity="confidential",
            business_scope="finance",
        ),
    )
    unsupported = _draft(
        _source("import-zip", "旧附件.png", None, extension=".png", size_bytes=123),
        _metadata("旧附件"),
    )
    invalid = _draft(
        _source("import-bad", "坏文件.txt", "not the declared size", size_bytes=999),
        _metadata("坏文件"),
    )

    preview = service.preview(
        DocumentImportPreviewRequest(documents=[ready, unsupported, invalid])
    )

    assert (preview.contract_id, preview.contract_version) == (
        "contract_nebula_default",
        1,
    )
    assert (preview.ready_count, preview.skipped_count) == (1, 2)
    assert [item.status for item in preview.items] == ["ready", "unsupported", "invalid"]
    assert preview.items[0].title_suggestion == "预算说明"
    assert preview.items[0].content_preview == ready.source.content
    assert preview.items[1].content_preview is None
    assert preview.items[1].diagnostic
    assert preview.items[2].diagnostic == "文件大小与文本内容不一致"

    authorization = {
        item.actor_id: item
        for item in preview.items[0].authorization
    }
    assert authorization["finance_001"].allowed is True
    assert authorization["admin_001"].allowed is True
    assert authorization["visitor_001"].allowed is False
    assert authorization["visitor_001"].rule_id == "resource_finance_manager"

    assert workspace.documents_file_path.read_text(encoding="utf-8") == before_catalog
    assert workspace.manifest_path.read_text(encoding="utf-8") == before_manifest
    assert retriever.current is before_retriever
    assert retriever.indexed_document_count == len(load_demo_data().documents)


@pytest.mark.parametrize(
    "field,value",
    [
        ("display_name", r"C:\\company\\secret.md"),
        ("display_name", "/company/secret.md"),
        ("relative_path", "../secret.md"),
        ("relative_path", r"folder\\secret.md"),
        ("relative_path", r"C:\\company\\secret.md"),
    ],
)
def test_source_rejects_absolute_or_nonportable_paths(field: str, value: str) -> None:
    kwargs = {
        "source_id": "path-check",
        "display_name": "secret.md",
        "relative_path": "secret.md",
        "extension": ".md",
        "size_bytes": 1,
        "content": "x",
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match="absolute|relative|portable|file name"):
        DocumentImportSource(**kwargs)


def test_source_normalizes_extension_but_preserves_relative_display_metadata() -> None:
    source = _source(
        "extension-check",
        "readme.md",
        "hello",
        extension="md",
        relative_path="nested/readme.md",
    )

    assert source.extension == ".md"
    assert source.relative_path == "nested/readme.md"
    assert source.display_name == "readme.md"


def test_commit_appends_snapshot_preserves_seed_contract_history_and_hot_reloads(
    tmp_path: Path,
) -> None:
    workspace, service, retriever = _service(tmp_path)
    original_catalog = json.loads(
        workspace.documents_file_path.read_text(encoding="utf-8")
    )
    original_contract = workspace.security_contract_path.read_text(encoding="utf-8")
    history_sentinel = b"existing acceptance history"
    workspace.history_database_path.write_bytes(history_sentinel)

    finance_draft = _draft(
        _source(
            "new-finance",
            "预算追加.md",
            "导入资料中的独特预算关键词 nebula-import-budget。",
        ),
        _metadata(
            "导入预算追加",
            sensitivity="confidential",
            business_scope="finance",
        ),
    )
    public_draft = _draft(
        _source("new-public", "服务说明.txt", "导入资料中的独特服务关键词 nebula-import-service。"),
        _metadata("导入服务说明"),
    )
    skipped_draft = _draft(
        _source("new-unsupported", "附件.png", None, extension=".png", size_bytes=10),
        _metadata("附件"),
    )

    result = service.commit(
        DocumentImportCommitRequest(
            documents=[finance_draft, public_draft, skipped_draft]
        )
    )

    assert len(result.imported) == 2
    assert len(result.skipped) == 1
    assert result.skipped[0].status == "unsupported"
    assert result.retriever.indexed_document_count == len(original_catalog) + 2
    assert retriever.indexed_document_count == len(original_catalog) + 2
    assert [item.title for item in result.imported] == ["导入预算追加", "导入服务说明"]
    assert retriever.search("nebula-import-budget", limit=1)[0].document.title == "导入预算追加"

    catalog = json.loads(workspace.documents_file_path.read_text(encoding="utf-8"))
    assert len(catalog) == len(original_catalog) + 2
    assert [item["title"] for item in catalog[-2:]] == ["导入预算追加", "导入服务说明"]
    assert workspace.security_contract_path.read_text(encoding="utf-8") == original_contract
    assert workspace.history_database_path.read_bytes() == history_sentinel
    serialized = workspace.documents_file_path.read_text(encoding="utf-8")
    assert str(workspace.root) not in serialized
    assert str(tmp_path) not in serialized


def test_commit_requires_workspace_before_writing_or_rebuilding(tmp_path: Path) -> None:
    data = load_demo_data()
    retriever = TfidfRetriever(data.documents)
    service = DocumentImportService(
        workspace=None,
        actors=data.actors,
        documents=data.documents,
        contract=load_security_contract(),
        retriever=retriever,
    )
    request = DocumentImportCommitRequest(
        documents=[_draft(_source("no-workspace", "doc.md", "content"))]
    )

    with pytest.raises(DocumentImportWorkspaceError, match="active Workspace"):
        service.commit(request)


def test_commit_rebuild_failure_leaves_catalog_and_retriever_untouched(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    data = load_demo_data(workspace.documents_path)
    initial = TfidfRetriever(data.documents)

    def fail_factory(_documents):
        raise RetrieverError("synthetic index failure")

    retriever = ReloadableRetriever(initial, factory=fail_factory)
    service = DocumentImportService(
        workspace=workspace,
        actors=data.actors,
        documents=data.documents,
        contract=load_security_contract(workspace.contract_path),
        retriever=retriever,
    )
    before = workspace.documents_file_path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="rebuild document Retriever"):
        service.commit(
            DocumentImportCommitRequest(
                documents=[_draft(_source("failing", "failing.md", "content"))]
            )
        )

    assert workspace.documents_file_path.read_text(encoding="utf-8") == before
    assert retriever.current is initial
    assert retriever.indexed_document_count == len(data.documents)


def test_two_commits_preserve_the_first_import_in_catalog_and_index(tmp_path: Path) -> None:
    workspace, service, retriever = _service(tmp_path)
    initial_count = len(service.documents)

    first = _draft(
        _source("first", "第一批.md", "first-batch-unique-keyword"),
        _metadata("第一批资料"),
    )
    second = _draft(
        _source("second", "第二批.md", "second-batch-unique-keyword"),
        _metadata("第二批资料"),
    )

    service.commit(DocumentImportCommitRequest(documents=[first]))
    service.commit(DocumentImportCommitRequest(documents=[second]))

    catalog = json.loads(workspace.documents_file_path.read_text(encoding="utf-8"))
    assert len(catalog) == initial_count + 2
    assert {item["title"] for item in catalog[-2:]} == {"第一批资料", "第二批资料"}
    assert retriever.indexed_document_count == initial_count + 2
    assert retriever.search("first-batch-unique-keyword", limit=1)[0].document.title == "第一批资料"
    assert retriever.search("second-batch-unique-keyword", limit=1)[0].document.title == "第二批资料"


def test_commit_rejects_unknown_owner_and_oversized_declared_source(tmp_path: Path) -> None:
    _workspace_root, service, _retriever = _service(tmp_path)

    with pytest.raises(DocumentImportError, match="unknown ownerId"):
        service.preview(
            DocumentImportPreviewRequest(
                documents=[
                    _draft(
                        _source("bad-owner", "owner.md", "content"),
                        _metadata("owner", owner_id="unknown_actor"),
                    )
                ]
            )
        )

    oversized = _draft(
        _source(
            "too-large",
            "large.md",
            "content",
            size_bytes=MAX_DOCUMENT_SIZE_BYTES + 1,
        )
    )
    preview = service.preview(DocumentImportPreviewRequest(documents=[oversized]))
    assert preview.items[0].status == "invalid"
    assert "2 MiB" in (preview.items[0].diagnostic or "")
