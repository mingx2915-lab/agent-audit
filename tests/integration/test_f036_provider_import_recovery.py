"""F-036 regression coverage for Provider failures and bounded imports.

These tests intentionally exercise the HTTP boundary with isolated injected
dependencies.  A Provider error must remain an explicit error: the API must
not silently retry, switch Provider roles, or manufacture a Finding from an
incomplete Trace.  The import case uses the real Workspace-backed importer so
Preview, atomic Commit, and the immediately published Retriever are checked
as one vertical slice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.main import create_app
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from agent_audit_api.retrieval import TfidfRetriever
from agent_audit_api.workspace import WorkspaceService
from tests.benchmark_support import GroundTruthProvider
from tests.retriever_support import make_tfidf_retriever


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


@dataclass
class _RaisingProvider:
    """Provider double that records every attempted completion and then fails."""

    error: BaseException
    model: str = "f036-failing-provider"
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append(([dict(message) for message in messages], tools))
        raise self.error


@dataclass
class _FixedVariantProvider:
    """Variant generator double; it never acts as a Target fallback."""

    model: str = "f036-attack-generator"
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        copied_messages = [dict(message) for message in messages]
        self.calls.append((copied_messages, tools))
        payload = json.loads(copied_messages[-1]["content"])
        baseline = payload["baseline"]
        return LLMResponse(
            content=json.dumps(
                {
                    "message": f"{baseline['message']}（F-036 固定变体）",
                    "mutationReason": "F-036 synthetic variant",
                },
                ensure_ascii=False,
            )
        )


def _scan_client(
    *,
    target_provider: Any,
    attack_provider: Any,
    history_path: Path,
) -> TestClient:
    return TestClient(
        create_app(
            provider=target_provider,
            attack_provider=attack_provider,
            retriever=make_tfidf_retriever(),
            history_path=history_path,
        )
    )


def _plan(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/attack-plans")
    assert response.status_code == 200, response.text
    return next(
        item
        for item in response.json()
        if item["basisType"] == "resource_owner_scope"
    )


def _workspace(tmp_path: Path):
    return WorkspaceService().create(
        tmp_path / "workspace",
        "F-036 mixed import Workspace",
        seed_dir=DEMO_SEED,
    )


def _source(
    source_id: str,
    display_name: str,
    content: str | None,
    *,
    extension: str | None = None,
    size_bytes: int | None = None,
    diagnostic: str | None = None,
    diagnostic_code: str | None = None,
) -> dict[str, Any]:
    suffix = extension or Path(display_name).suffix
    actual_size = len(content.encode("utf-8")) if content is not None else 0
    return {
        "sourceId": source_id,
        "displayName": display_name,
        "relativePath": display_name,
        "extension": suffix,
        "sizeBytes": actual_size if size_bytes is None else size_bytes,
        "content": content,
        "diagnostic": diagnostic,
        "diagnosticCode": diagnostic_code,
    }


def _draft(
    source_id: str,
    display_name: str,
    content: str | None,
    *,
    extension: str | None = None,
    size_bytes: int | None = None,
    diagnostic: str | None = None,
    diagnostic_code: str | None = None,
    sensitivity: str = "public",
    business_scope: str = "general",
) -> dict[str, Any]:
    return {
        "source": _source(
            source_id,
            display_name,
            content,
            extension=extension,
            size_bytes=size_bytes,
            diagnostic=diagnostic,
            diagnostic_code=diagnostic_code,
        ),
        "metadata": {
            "title": Path(display_name).stem,
            "sensitivity": sensitivity,
            "businessScope": business_scope,
            "ownerId": None,
            "trustLevel": "trusted",
        },
    }


def test_target_provider_failure_is_single_attempt_and_not_a_finding(tmp_path: Path) -> None:
    """A failed Target call cannot become a fallback result or pseudo Finding."""

    failure = ProviderResponseError("synthetic invalid Provider response")
    target = _RaisingProvider(failure)
    attack = _FixedVariantProvider()
    history_path = tmp_path / "history" / "audit.sqlite3"

    with _scan_client(
        target_provider=target,
        attack_provider=attack,
        history_path=history_path,
    ) as client:
        plan = _plan(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 3},
        )
        history = client.get("/api/scans")

    assert response.status_code == 502, response.text
    detail = response.json()["detail"]
    assert any(term in detail for term in ("无法识别", "未形成有效结论", "未完成"))
    assert "重新" in detail
    assert str(failure) not in detail
    assert len(attack.calls) == 1
    assert len(target.calls) == 1
    assert history.status_code == 200, history.text
    assert history.json() == []
    # No incomplete attempt can be represented as an evaluation/Finding.
    assert "finding" not in response.text.lower()


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (ProviderConfigurationError("synthetic Provider is not configured"), 503),
        (ProviderUnavailableError("synthetic Provider connection refused"), 502),
    ],
)
def test_attack_provider_failure_does_not_execute_target_or_persist_scan(
    error: BaseException,
    status_code: int,
    tmp_path: Path,
) -> None:
    """Variant generation is a hard boundary; Target must not be a fallback."""

    attack = _RaisingProvider(error)
    target = GroundTruthProvider()
    history_path = tmp_path / "history" / "audit.sqlite3"

    with _scan_client(
        target_provider=target,
        attack_provider=attack,
        history_path=history_path,
    ) as client:
        plan = _plan(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 2},
        )
        history = client.get("/api/scans")

    assert response.status_code == status_code, response.text
    detail = response.json()["detail"]
    assert any(term in detail for term in ("连接设置", "未完成", "未形成有效结论"))
    assert "重新" in detail
    assert str(error) not in detail
    assert len(attack.calls) == 1
    assert target.calls == []
    assert history.status_code == 200, history.text
    assert history.json() == []


def test_fifty_mixed_documents_preview_commit_and_immediate_retrieval(
    tmp_path: Path,
) -> None:
    """The max batch preserves order/statuses and publishes one new index."""

    workspace = _workspace(tmp_path)
    data = load_demo_data(workspace.documents_path)
    provider = GroundTruthProvider()
    application = create_app(
        provider=provider,
        workspace=workspace,
        retriever=TfidfRetriever(data.documents),
    )
    before_catalog = workspace.documents_file_path.read_bytes()

    ready: list[dict[str, Any]] = []
    extensions = (".md", ".txt", ".pdf", ".docx")
    for index in range(40):
        extension = extensions[index % len(extensions)]
        marker = f"f036-batch-{index:02d}-unique-retrieval-marker"
        # PDF/DOCX size_bytes intentionally models the original binary source;
        # the importer receives normalized text at this boundary.
        ready.append(
            _draft(
                f"f036-ready-{index:02d}",
                f"F036 ready {index:02d}{extension}",
                f"{marker} normalized source text",
                extension=extension,
                size_bytes=(4096 if extension in {".pdf", ".docx"} else None),
            )
        )
    skipped = [
        _draft(
            f"f036-unsupported-{index:02d}",
            f"F036 image {index:02d}.png",
            None,
            extension=".png",
            size_bytes=2048,
        )
        for index in range(5)
    ]
    skipped.extend(
        _draft(
            f"f036-invalid-{index:02d}",
            f"F036 invalid {index:02d}.pdf",
            None,
            extension=".pdf",
            size_bytes=4096,
            diagnostic="native parser did not produce text",
            diagnostic_code="no_text",
        )
        for index in range(5)
    )
    documents = [*ready, *skipped]
    assert len(documents) == 50

    with TestClient(application) as client:
        preview_response = client.post(
            "/api/document-imports/previews",
            json={"documents": documents},
        )
        # Preview must not alter either the persisted catalog or Provider usage.
        assert preview_response.status_code == 200, preview_response.text
        preview = preview_response.json()
        assert (preview["readyCount"], preview["skippedCount"]) == (40, 10)
        assert [item["status"] for item in preview["items"]] == [
            *("ready" for _ in range(40)),
            *("unsupported" for _ in range(5)),
            *("invalid" for _ in range(5)),
        ]
        assert [item["sourceId"] for item in preview["items"]] == [
            item["source"]["sourceId"] for item in documents
        ]
        assert provider.calls == []
        assert workspace.documents_file_path.read_bytes() == before_catalog

        commit_response = client.post(
            "/api/document-imports",
            json={"documents": documents},
        )
        assert commit_response.status_code == 200, commit_response.text
        commit = commit_response.json()
        assert len(commit["imported"]) == 40
        assert len(commit["skipped"]) == 10
        assert [item["sourceId"] for item in commit["skipped"][:5]] == [
            item["source"]["sourceId"] for item in skipped[:5]
        ]
        assert commit["retriever"]["indexedDocumentCount"] == len(data.documents) + 40

        catalog_response = client.get("/api/workspace/documents")
        assert catalog_response.status_code == 200, catalog_response.text
        catalog = catalog_response.json()
        assert len(catalog["documents"]) == len(data.documents) + 40
        imported_ids = {item["id"] for item in commit["imported"]}
        assert imported_ids <= {item["id"] for item in catalog["documents"]}

        # The new in-memory Retriever must be observable by the next request,
        # and only then does this deterministic Provider receive one call.
        retrieval_response = client.post(
            "/api/assistant/queries",
            json={
                "actorId": "visitor_001",
                "message": "f036-batch-03-unique-retrieval-marker",
            },
        )

    assert retrieval_response.status_code == 200, retrieval_response.text
    trace = retrieval_response.json()
    model_context_ids = {
        document_id
        for event in trace["traceEvents"]
        if event["type"] == "sink"
        and event["details"].get("sinkId") == "model_context"
        for document_id in event["details"].get("documentIds", [])
    }
    # Public imported docs are allowed to this actor, so the marker's document
    # must survive Retrieval -> Authorization -> model context.
    imported_by_title = {item["title"]: item["id"] for item in commit["imported"]}
    assert imported_by_title["F036 ready 03"] in imported_ids
    assert imported_by_title["F036 ready 03"] in model_context_ids
    assert len(provider.calls) == 1
    assert workspace.documents_file_path.read_bytes() != before_catalog
