"""F-017 integration coverage for Embedding evaluation and permission traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse
from agent_audit_api.retrieval import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    RetrieverInferenceError,
)
from agent_audit_api.retrieval_evaluation import FIXED_RETRIEVAL_EVALUATION_CASES


_DOCUMENT_IDS = (
    "doc_product_overview_001",
    "doc_customer_contract_001",
    "doc_customer_contract_002",
    "doc_demo_usage_guide_001",
    "doc_finance_budget_001",
    "doc_hr_handbook_001",
    "doc_external_vendor_prompt_001",
)

_QUERY_TARGETS = {
    case.query: (case.expected_document_id,)
    for case in FIXED_RETRIEVAL_EVALUATION_CASES
}
_QUERY_TARGETS.update(
    {
        "请查看 customer_002 远山物流客户合同和续约状态。": (
            "doc_customer_contract_002",
        ),
    }
)


def _vector(*components: tuple[int, float]) -> tuple[float, ...]:
    values = [0.0] * EMBEDDING_DIMENSIONS
    for index, value in components:
        values[index] = value
    return tuple(values)


@dataclass
class FakeEmbedder:
    """Deterministic model double; it never downloads or runs BGE."""

    document_inputs: list[tuple[str, ...]] = field(default_factory=list)
    query_inputs: list[str] = field(default_factory=list)

    def embed(self, documents: Sequence[str]) -> Iterable[Sequence[float]]:
        values = tuple(documents)
        self.document_inputs.append(values)
        assert len(values) == len(_DOCUMENT_IDS)
        assert all("\n" in document for document in values)
        return tuple(_vector((index, 1.0)) for index in range(len(values)))

    def query_embed(self, query: str) -> Iterable[Sequence[float]]:
        self.query_inputs.append(query)
        target_ids = _QUERY_TARGETS[query]
        return tuple(
            _vector(
                *((_DOCUMENT_IDS.index(document_id), 1.0 / len(target_ids))
                  for document_id in target_ids)
            )
            for _ in (0,)
        )


@dataclass
class FakeProvider:
    answer: str = "Embedding API 测试回答"
    calls: list[tuple[Sequence[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return LLMResponse(content=self.answer, tool_calls=())


class FailingEmbedder:
    """Model boundary failure used to prove there is no TF-IDF fallback."""

    def __init__(self) -> None:
        self.document_calls = 0
        self.query_calls = 0

    def embed(self, documents: Sequence[str]) -> Iterable[Sequence[float]]:
        self.document_calls += 1
        raise RetrieverInferenceError("deterministic embedding model failure")

    def query_embed(self, query: str) -> Iterable[Sequence[float]]:
        self.query_calls += 1
        raise RetrieverInferenceError("deterministic embedding model failure")


def _client(provider: FakeProvider, embedder: FakeEmbedder | FailingEmbedder) -> TestClient:
    return TestClient(create_app(provider=provider, embedder=embedder))


def _events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload["traceEvents"]


def _context_ids(events: list[dict[str, Any]]) -> set[str]:
    context = next(
        event
        for event in events
        if event["type"] == "sink"
        and event["details"].get("sinkType") == "model_context"
    )
    return set(context["details"]["documentIds"])


def test_fixed_evaluation_shape_ranks_embedding_without_provider_call() -> None:
    provider = FakeProvider()
    embedder = FakeEmbedder()

    with _client(provider, embedder) as client:
        response = client.post("/api/retrieval-evaluations")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "id",
        "selectedEngine",
        "modelName",
        "dimensions",
        "indexedDocumentCount",
        "cases",
        "metrics",
    }
    assert payload["selectedEngine"] == "embedding"
    assert payload["modelName"] == EMBEDDING_MODEL_NAME
    assert payload["dimensions"] == EMBEDDING_DIMENSIONS
    assert payload["indexedDocumentCount"] == len(_DOCUMENT_IDS)
    assert len(payload["cases"]) == 6
    assert [case["caseId"] for case in payload["cases"]] == [
        case.case_id for case in FIXED_RETRIEVAL_EVALUATION_CASES
    ]
    for actual, fixed in zip(payload["cases"], FIXED_RETRIEVAL_EVALUATION_CASES):
        assert actual["query"] == fixed.query
        assert actual["expectedDocumentId"] == fixed.expected_document_id
        assert actual["embeddingExpectedRank"] == 1
        assert [item["rank"] for item in actual["embeddingResults"]] == [1, 2, 3]
        assert actual["embeddingResults"][0]["documentId"] == fixed.expected_document_id
        assert all(set(item) == {"rank", "documentId", "title", "score"} for item in actual["embeddingResults"])
        assert actual["tfidfResults"]
    assert payload["metrics"]["caseCount"] == 6
    assert payload["metrics"]["embeddingTop1Hits"] == 6
    assert payload["metrics"]["embeddingMrr"] == 1.0
    assert provider.calls == []
    assert embedder.query_inputs == [case.query for case in FIXED_RETRIEVAL_EVALUATION_CASES]


def test_evaluation_endpoint_rejects_arbitrary_query_and_expected_fields() -> None:
    provider = FakeProvider()
    embedder = FakeEmbedder()

    with _client(provider, embedder) as client:
        response = client.post(
            "/api/retrieval-evaluations",
            json={
                "query": "不应由客户端控制",
                "expectedDocumentId": "doc_product_overview_001",
            },
        )

    assert response.status_code == 422
    assert embedder.document_inputs == []
    assert embedder.query_inputs == []
    assert provider.calls == []


def test_model_error_is_503_without_pseudo_results_or_tfidf_fallback() -> None:
    provider = FakeProvider()
    embedder = FailingEmbedder()

    with _client(provider, embedder) as client:
        response = client.post("/api/retrieval-evaluations")

    assert response.status_code == 503
    body = response.json()
    assert "cases" not in body
    assert "metrics" not in body
    assert "deterministic embedding model failure" in body["detail"]
    assert embedder.document_calls == 1
    assert provider.calls == []


def test_injected_embedding_retriever_is_shared_by_evaluation_and_assistant() -> None:
    provider = FakeProvider()
    embedder = FakeEmbedder()

    with _client(provider, embedder) as client:
        evaluation = client.post("/api/retrieval-evaluations")
        assistant = client.post(
            "/api/assistant/queries",
            json={
                "actorId": "finance_001",
                "message": "各团队明年的钱应该怎么分配？",
            },
        )

    assert evaluation.status_code == 200
    assert assistant.status_code == 200
    assert len(embedder.document_inputs) == 1
    assert embedder.query_inputs[-1] == "各团队明年的钱应该怎么分配？"
    assert len(provider.calls) == 1


def test_secure_permission_trace_keeps_visitor_finance_candidate_out_of_context() -> None:
    provider = FakeProvider()
    embedder = FakeEmbedder()

    with _client(provider, embedder) as client:
        response = client.post(
            "/api/assistant/queries",
            json={
                "actorId": "visitor_001",
                "message": "各团队明年的钱应该怎么分配？",
            },
        )

    assert response.status_code == 200
    events = _events(response.json())
    retrieval = next(event for event in events if event["type"] == "retrieval")
    details = retrieval["details"]
    assert details["engineId"] == "embedding"
    assert details["modelName"] == EMBEDDING_MODEL_NAME
    assert details["dimensions"] == EMBEDDING_DIMENSIONS
    assert details["candidates"]
    assert all(set(candidate) == {"documentId", "score"} for candidate in details["candidates"])
    assert "doc_finance_budget_001" in details["documentIds"]
    finance_auth = next(
        event
        for event in events
        if event["type"] == "authorization"
        and event["details"].get("documentId") == "doc_finance_budget_001"
    )
    assert finance_auth["details"]["decision"] == "denied"
    assert "doc_finance_budget_001" not in _context_ids(events)
    assert len(provider.calls) == 1


def test_finance_actor_can_enter_the_same_embedding_candidate_into_context() -> None:
    provider = FakeProvider()
    embedder = FakeEmbedder()

    with _client(provider, embedder) as client:
        response = client.post(
            "/api/assistant/queries",
            json={
                "actorId": "finance_001",
                "message": "各团队明年的钱应该怎么分配？",
            },
        )

    assert response.status_code == 200
    events = _events(response.json())
    finance_auth = next(
        event
        for event in events
        if event["type"] == "authorization"
        and event["details"].get("documentId") == "doc_finance_budget_001"
    )
    assert finance_auth["details"]["decision"] == "allowed"
    assert "doc_finance_budget_001" in _context_ids(events)


def test_vulnerable_profile_still_finds_embedding_resource_bypass() -> None:
    provider = FakeProvider()
    embedder = FakeEmbedder()

    with _client(provider, embedder) as client:
        cases = client.get("/api/attack-cases").json()
        case = next(item for item in cases if item["id"] == "case_inside_out_customer_scope")
        response = client.post(f"/api/attack-cases/{case['id']}/execute")

    assert response.status_code == 200
    result = response.json()
    events = _events(result["queryResult"])
    retrieval = next(event for event in events if event["type"] == "retrieval")
    assert retrieval["details"]["engineId"] == "embedding"
    assert retrieval["details"]["modelName"] == EMBEDDING_MODEL_NAME
    assert "doc_customer_contract_002" in retrieval["details"]["documentIds"]
    assert "doc_customer_contract_002" in _context_ids(events)
    assert result["evaluation"]["status"] == "failed"
    finding = next(
        finding
        for finding in result["evaluation"]["findings"]
        if finding["category"] == "resource_authorization_bypass"
    )
    assert finding["evidenceSequences"]

