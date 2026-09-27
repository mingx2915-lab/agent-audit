"""F-028 HTTP integration coverage for explicit Workspace document import."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.main import create_app
from agent_audit_api.retrieval import RetrieverError, TfidfRetriever
from agent_audit_api.workspace import WorkspaceService
from tests.benchmark_support import GroundTruthProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def _workspace(tmp_path: Path):
    return WorkspaceService().create(
        tmp_path / "workspace",
        "F-028 API Workspace",
        seed_dir=DEMO_SEED,
    )


def _application(
    tmp_path: Path,
    *,
    with_workspace: bool = True,
) -> tuple[Any, Any, GroundTruthProvider]:
    provider = GroundTruthProvider()
    workspace = _workspace(tmp_path) if with_workspace else None
    data = load_demo_data(workspace.documents_path if workspace else None)
    application = create_app(
        provider=provider,
        workspace=workspace,
        retriever=TfidfRetriever(data.documents),
    )
    return application, workspace, provider


def _source(
    source_id: str,
    name: str,
    content: str | None,
    *,
    extension: str | None = None,
    relative_path: str | None = None,
    size_bytes: int | None = None,
    diagnostic: str | None = None,
) -> dict[str, Any]:
    actual_size = len(content.encode("utf-8")) if content is not None else 0
    return {
        "sourceId": source_id,
        "displayName": name,
        "relativePath": relative_path or name,
        "extension": extension or Path(name).suffix,
        "sizeBytes": actual_size if size_bytes is None else size_bytes,
        "content": content,
        "diagnostic": diagnostic,
    }


def _metadata(
    title: str,
    *,
    sensitivity: str = "public",
    business_scope: str = "general",
    owner_id: str | None = None,
    trust_level: str = "trusted",
) -> dict[str, Any]:
    return {
        "title": title,
        "sensitivity": sensitivity,
        "businessScope": business_scope,
        "ownerId": owner_id,
        "trustLevel": trust_level,
    }


def _draft(
    source_id: str,
    name: str,
    content: str | None,
    *,
    metadata: dict[str, Any] | None = None,
    **source_kwargs: Any,
) -> dict[str, Any]:
    return {
        "source": _source(source_id, name, content, **source_kwargs),
        "metadata": metadata or _metadata(Path(name).stem),
    }


def _app_payload(draft: dict[str, Any]) -> dict[str, Any]:
    return {"documents": [draft]}


def _model_context_ids(response: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for event in response["traceEvents"]:
        if event["type"] != "sink":
            continue
        details = event["details"]
        if details.get("sinkId") == "model_context":
            ids.update(details.get("documentIds", []))
    return ids


def test_workspace_catalog_get_is_read_only_and_exposes_safe_summary(tmp_path: Path) -> None:
    application, workspace, provider = _application(tmp_path)
    before_catalog = workspace.documents_file_path.read_text(encoding="utf-8")

    with TestClient(application) as client:
        response = client.get("/api/workspace/documents")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["workspaceName"] == "F-028 API Workspace"
    assert len(payload["documents"]) == len(load_demo_data().documents)
    assert payload["retriever"]["indexedDocumentCount"] == len(load_demo_data().documents)
    assert all("content" not in document for document in payload["documents"])
    assert provider.calls == []
    assert workspace.documents_file_path.read_text(encoding="utf-8") == before_catalog


def test_preview_returns_item_statuses_and_contract_authorization_without_writes(
    tmp_path: Path,
) -> None:
    application, workspace, provider = _application(tmp_path)
    before_catalog = workspace.documents_file_path.read_text(encoding="utf-8")
    ready = _draft(
        "preview-finance",
        "财务预算.md",
        "preview-only finance source with unique marker",
        relative_path="部门/财务预算.md",
        metadata=_metadata(
            "受控财务预算",
            sensitivity="confidential",
            business_scope="finance",
        ),
    )
    unsupported = _draft(
        "preview-image",
        "旧报告.png",
        None,
        extension=".png",
        size_bytes=10,
        metadata=_metadata("旧报告"),
    )
    invalid = _draft(
        "preview-invalid",
        "坏编码.txt",
        "declared size differs",
        size_bytes=999,
        metadata=_metadata("坏编码"),
    )

    with TestClient(application) as client:
        response = client.post(
            "/api/document-imports/previews",
            json={"documents": [ready, unsupported, invalid]},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert (payload["readyCount"], payload["skippedCount"]) == (1, 2)
    assert [item["status"] for item in payload["items"]] == [
        "ready",
        "unsupported",
        "invalid",
    ]
    item = payload["items"][0]
    assert item["titleSuggestion"] == "财务预算"
    assert item["contentPreview"] == ready["source"]["content"]
    assert {entry["actorId"] for entry in item["authorization"]} == {
        "visitor_001",
        "employee_001",
        "sales_001",
        "hr_001",
        "finance_001",
        "admin_001",
    }
    decisions = {entry["actorId"]: entry["allowed"] for entry in item["authorization"]}
    assert decisions["finance_001"] is True
    assert decisions["admin_001"] is True
    assert decisions["visitor_001"] is False
    serialized = json.dumps(payload, ensure_ascii=False)
    assert str(workspace.root) not in serialized
    assert str(tmp_path) not in serialized
    assert provider.calls == []
    assert workspace.documents_file_path.read_text(encoding="utf-8") == before_catalog


def test_preview_rejects_extra_fields_and_nonportable_path_at_http_boundary(
    tmp_path: Path,
) -> None:
    application, workspace, provider = _application(tmp_path)
    extra = _draft("extra", "extra.md", "content")
    extra["metadata"]["unexpected"] = True
    escaped = _draft(
        "escaped",
        "escaped.md",
        "content",
        relative_path="../outside.md",
    )
    absolute_relative = _draft(
        "absolute-relative",
        "absolute-relative.md",
        "content",
        relative_path="C:/Users/demo/absolute-relative.md",
    )
    absolute_display = _draft(
        "absolute-display",
        "C:/Users/demo/absolute-display.md",
        "content",
    )

    with TestClient(application) as client:
        extra_response = client.post(
            "/api/document-imports/previews",
            json=_app_payload(extra),
        )
        escaped_response = client.post(
            "/api/document-imports/previews",
            json=_app_payload(escaped),
        )
        absolute_relative_response = client.post(
            "/api/document-imports/previews",
            json=_app_payload(absolute_relative),
        )
        absolute_display_response = client.post(
            "/api/document-imports/previews",
            json=_app_payload(absolute_display),
        )

    assert extra_response.status_code == 422
    assert escaped_response.status_code == 422
    assert absolute_relative_response.status_code == 422
    assert absolute_display_response.status_code == 422
    assert provider.calls == []
    assert workspace.documents_file_path.read_text(encoding="utf-8") == (
        _workspace_catalog_text(workspace)
    )


def _workspace_catalog_text(workspace: Any) -> str:
    return workspace.documents_file_path.read_text(encoding="utf-8")


def test_commit_appends_twice_preserves_seed_and_updates_index_immediately(
    tmp_path: Path,
) -> None:
    application, workspace, provider = _application(tmp_path)
    original_catalog = json.loads(
        workspace.documents_file_path.read_text(encoding="utf-8")
    )
    original_contract = workspace.security_contract_path.read_text(encoding="utf-8")
    history_sentinel = b"history remains untouched"
    workspace.history_database_path.write_bytes(history_sentinel)

    first = _draft(
        "first-import",
        "第一批.md",
        "first import unique retrieval marker",
        metadata=_metadata("第一批导入资料"),
    )
    second = _draft(
        "second-import",
        "第二批.md",
        "second import unique retrieval marker",
        metadata=_metadata("第二批导入资料"),
    )

    with TestClient(application) as client:
        first_response = client.post("/api/document-imports", json=_app_payload(first))
        second_response = client.post("/api/document-imports", json=_app_payload(second))
        catalog_response = client.get("/api/workspace/documents")

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text
    first_result = first_response.json()
    second_result = second_response.json()
    imported_ids = [first_result["imported"][0]["id"], second_result["imported"][0]["id"]]
    assert len(set(imported_ids)) == 2
    assert [first_result["imported"][0]["title"], second_result["imported"][0]["title"]] == [
        "第一批导入资料",
        "第二批导入资料",
    ]
    assert catalog_response.status_code == 200, catalog_response.text
    catalog = catalog_response.json()
    assert len(catalog["documents"]) == len(original_catalog) + 2
    catalog_ids = {document["id"] for document in catalog["documents"]}
    assert set(imported_ids) <= catalog_ids
    assert catalog["retriever"]["indexedDocumentCount"] == len(original_catalog) + 2
    assert workspace.security_contract_path.read_text(encoding="utf-8") == original_contract
    assert workspace.history_database_path.read_bytes() == history_sentinel
    serialized = workspace.documents_file_path.read_text(encoding="utf-8")
    assert str(workspace.root) not in serialized
    assert str(tmp_path) not in serialized
    assert provider.calls == []


def test_imported_document_enters_allowed_context_but_not_denied_context(
    tmp_path: Path,
) -> None:
    application, workspace, _provider = _application(tmp_path)
    draft = _draft(
        "finance-import",
        "财务导入.md",
        "nebula imported finance authorization marker",
        metadata=_metadata(
            "导入财务资料",
            sensitivity="confidential",
            business_scope="finance",
        ),
    )

    with TestClient(application) as client:
        commit_response = client.post("/api/document-imports", json=_app_payload(draft))
        document_id = commit_response.json()["imported"][0]["id"]
        allowed_response = client.post(
            "/api/assistant/queries",
            json={"actorId": "finance_001", "message": "nebula imported finance authorization marker"},
        )
        denied_response = client.post(
            "/api/assistant/queries",
            json={"actorId": "visitor_001", "message": "nebula imported finance authorization marker"},
        )

    assert commit_response.status_code == 200, commit_response.text
    assert allowed_response.status_code == 200, allowed_response.text
    assert denied_response.status_code == 200, denied_response.text
    assert document_id in _model_context_ids(allowed_response.json())
    assert document_id not in _model_context_ids(denied_response.json())
    denied_authorizations = [
        event
        for event in denied_response.json()["traceEvents"]
        if event["type"] == "authorization"
        and event["details"].get("documentId") == document_id
    ]
    assert denied_authorizations
    assert all(event["details"]["decision"] == "denied" for event in denied_authorizations)
    assert str(workspace.root) not in json.dumps(denied_response.json(), ensure_ascii=False)


@pytest.mark.parametrize("extension", [".pdf", ".docx"])
def test_imported_pdf_and_docx_text_are_isolated_by_real_retrieval_authorization_trace(
    tmp_path: Path,
    extension: str,
) -> None:
    application, workspace, provider = _application(tmp_path)
    marker = f"f035-{extension[1:]}-finance-isolation-marker"
    source = _source(
        f"trace-{extension[1:]}",
        f"财务资料{extension}",
        f"{marker} normalized text",
        extension=extension,
        # Native PDF/DOCX parsing returns normalized text, so this is the
        # original binary size rather than the extracted UTF-8 byte length.
        size_bytes=4096,
    )
    draft = {
        "source": source,
        "metadata": _metadata(
            f"导入{extension[1:].upper()}财务资料",
            sensitivity="confidential",
            business_scope="finance",
        ),
    }

    with TestClient(application) as client:
        commit_response = client.post("/api/document-imports", json={"documents": [draft]})
        assert commit_response.status_code == 200, commit_response.text
        document_id = commit_response.json()["imported"][0]["id"]
        # Import/commit is deterministic and must not call the model.  The
        # two assistant queries below intentionally exercise the real
        # provider-backed Retrieval/Authorization trace.
        assert provider.calls == []
        allowed_response = client.post(
            "/api/assistant/queries",
            json={"actorId": "finance_001", "message": marker},
        )
        denied_response = client.post(
            "/api/assistant/queries",
            json={"actorId": "visitor_001", "message": marker},
        )

    assert allowed_response.status_code == 200, allowed_response.text
    assert denied_response.status_code == 200, denied_response.text
    allowed = allowed_response.json()
    denied = denied_response.json()
    assert document_id in _model_context_ids(allowed)
    assert document_id not in _model_context_ids(denied)
    denied_events = [
        event
        for event in denied["traceEvents"]
        if event["type"] == "authorization"
        and event["details"].get("documentId") == document_id
    ]
    assert denied_events
    assert all(event["details"]["decision"] == "denied" for event in denied_events)
    assert str(workspace.root) not in json.dumps(allowed, ensure_ascii=False)
    assert str(workspace.root) not in json.dumps(denied, ensure_ascii=False)


def test_commit_without_workspace_returns_409_and_does_not_call_provider(tmp_path: Path) -> None:
    application, _workspace_root, provider = _application(tmp_path, with_workspace=False)
    draft = _draft("no-workspace", "doc.md", "content")

    with TestClient(application) as client:
        response = client.post("/api/document-imports", json=_app_payload(draft))

    assert response.status_code == 409, response.text
    assert "active Workspace" in response.json()["detail"]
    assert provider.calls == []


def test_commit_candidate_index_failure_leaves_catalog_and_slot_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application, workspace, provider = _application(tmp_path)
    before_catalog = workspace.documents_file_path.read_text(encoding="utf-8")
    retriever = application.state.retriever
    before_current = retriever.current

    def fail_candidate(_documents: Any) -> Any:
        raise RetrieverError("synthetic candidate build failure")

    monkeypatch.setattr(retriever, "build_candidate", fail_candidate)
    draft = _draft("index-failure", "will-not-commit.md", "content")

    with TestClient(application) as client:
        response = client.post("/api/document-imports", json=_app_payload(draft))

    assert response.status_code == 503, response.text
    assert "rebuild document Retriever" in response.json()["detail"]
    assert workspace.documents_file_path.read_text(encoding="utf-8") == before_catalog
    assert retriever.current is before_current
    assert provider.calls == []


def test_import_rejects_over_limit_items_and_unsupported_only_payload(tmp_path: Path) -> None:
    application, workspace, provider = _application(tmp_path)
    too_many = [
        _draft(f"item-{index}", f"item-{index}.md", "x")
        for index in range(51)
    ]
    unsupported = _draft(
        "only-image",
        "only.png",
        None,
        extension=".png",
        size_bytes=1,
    )

    with TestClient(application) as client:
        too_many_response = client.post(
            "/api/document-imports/previews",
            json={"documents": too_many},
        )
        unsupported_response = client.post(
            "/api/document-imports",
            json=_app_payload(unsupported),
        )

    assert too_many_response.status_code == 422
    assert unsupported_response.status_code == 422
    assert provider.calls == []
    assert len(json.loads(workspace.documents_file_path.read_text(encoding="utf-8"))) == len(
        load_demo_data().documents
    )


def test_import_result_and_catalog_never_echo_absolute_selection_paths(tmp_path: Path) -> None:
    application, workspace, _provider = _application(tmp_path)
    source = _source(
        "portable-selection",
        "notes.md",
        "portable selected content",
        relative_path="nested/notes.md",
    )
    draft = {"source": source, "metadata": _metadata("Portable Notes")}

    with TestClient(application) as client:
        preview = client.post("/api/document-imports/previews", json={"documents": [draft]})
        commit = client.post("/api/document-imports", json={"documents": [draft]})
        catalog = client.get("/api/workspace/documents")

    assert preview.status_code == 200, preview.text
    assert commit.status_code == 200, commit.text
    for payload in (preview.json(), commit.json(), catalog.json()):
        serialized = json.dumps(payload, ensure_ascii=False)
        assert str(workspace.root) not in serialized
        assert str(tmp_path) not in serialized
    assert str(workspace.root) not in workspace.documents_file_path.read_text(encoding="utf-8")


def test_import_result_plans_are_real_active_plans_and_preview_has_no_temporary_targets(
    tmp_path: Path,
) -> None:
    application, workspace, provider = _application(tmp_path)
    draft = _draft(
        "plan-contract",
        "计划资料.md",
        "plan contract import content",
        metadata=_metadata(
            "计划资料",
            sensitivity="confidential",
            business_scope="finance",
        ),
    )

    with TestClient(application) as client:
        preview_response = client.post(
            "/api/document-imports/previews",
            json=_app_payload(draft),
        )
        commit_response = client.post(
            "/api/document-imports",
            json=_app_payload(draft),
        )
        plans_response = client.get("/api/attack-plans")

    assert preview_response.status_code == 200, preview_response.text
    assert commit_response.status_code == 200, commit_response.text
    assert plans_response.status_code == 200, plans_response.text
    preview = preview_response.json()
    result = commit_response.json()
    plans = plans_response.json()
    plan_by_id = {plan["id"]: plan for plan in plans}

    assert preview["planDiagnostic"] is None
    assert all(
        not str(summary["targetId"]).startswith("preview_")
        for summary in preview["executablePlans"]
    )
    assert result["executablePlans"]
    assert {summary["id"] for summary in result["executablePlans"]} == set(plan_by_id)
    for summary in result["executablePlans"]:
        assert summary["id"] in plan_by_id
        active_plan = plan_by_id[summary["id"]]
        for field in (
            "id",
            "name",
            "description",
            "basisType",
            "basisRuleId",
            "attackerType",
            "actorId",
            "targetKind",
            "targetId",
            "targetProfileId",
        ):
            assert summary[field] == active_plan[field]
        assert "message" not in summary
    assert provider.calls == []
    assert str(workspace.root) not in json.dumps(result, ensure_ascii=False)
