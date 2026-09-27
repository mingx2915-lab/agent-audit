from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse, ProviderUnavailableError
from tests.retriever_support import make_tfidf_retriever
from agent_audit_api.schemas import TraceEvent


@dataclass
class FakeProvider:
    answer: str = "语义补充解释"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return LLMResponse(content=self.answer, tool_calls=())


class InvalidProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=None):
        self.calls += 1
        return object()


class UnavailableProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages, tools=None):
        self.calls += 1
        raise ProviderUnavailableError("provider unavailable in test")


def _event(sequence: int, event_type: str, details: dict[str, Any]) -> TraceEvent:
    return TraceEvent(
        sequence=sequence,
        type=event_type,
        summary=f"{event_type} event",
        details=details,
        occurred_at="2026-08-26T00:00:00Z",
    )


def _resource_finding_trace() -> list[TraceEvent]:
    return [
        _event(1, "input", {"actorId": "sales_001", "message": "query"}),
        _event(
            2,
            "authorization",
            {
                "actorId": "sales_001",
                "documentId": "doc_denied",
                "decision": "denied",
                "ruleId": None,
            },
        ),
        _event(
            3,
            "sink",
            {
                "sinkId": "model_context",
                "sinkType": "model_context",
                "documentIds": ["doc_denied"],
                "includesToolResult": False,
            },
        ),
        _event(4, "model_response", {"content": "answer", "toolCallCount": 0}),
    ]


def _normal_trace() -> list[TraceEvent]:
    return [
        _event(1, "input", {"actorId": "sales_001", "message": "query"}),
        _event(
            2,
            "authorization",
            {
                "actorId": "sales_001",
                "documentId": "doc_allowed",
                "decision": "allowed",
                "ruleId": "resource_customer_owner",
            },
        ),
        _event(
            3,
            "sink",
            {
                "sinkId": "model_context",
                "sinkType": "model_context",
                "documentIds": ["doc_allowed"],
                "includesToolResult": False,
            },
        ),
        _event(4, "model_response", {"content": "answer", "toolCallCount": 0}),
        _event(
            5,
            "sink",
            {
                "sinkId": "actor_response",
                "sinkType": "actor_response",
                "actorId": "sales_001",
            },
        ),
    ]


def _payload(trace_events: list[TraceEvent], include: bool) -> dict[str, object]:
    return {
        "traceEvents": [event.model_dump(by_alias=True) for event in trace_events],
        "includeSemanticReview": include,
    }


def test_deterministic_evaluation_api_works_without_deepseek_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with TestClient(
        create_app(provider=None, retriever=make_tfidf_retriever())
    ) as client:
        response = client.post(
            "/api/evaluations",
            json=_payload(_normal_trace(), include=False),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["findings"] == []
    assert body["semanticReview"] == {
        "performed": False,
        "explanation": None,
    }


def test_include_false_returns_finding_without_calling_provider() -> None:
    provider = FakeProvider()

    with TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    ) as client:
        response = client.post(
            "/api/evaluations",
            json=_payload(_resource_finding_trace(), include=False),
        )

    assert response.status_code == 200
    assert len(provider.calls) == 0
    body = response.json()
    assert body["status"] == "failed"
    assert len(body["findings"]) == 1
    assert body["findings"][0]["category"] == "resource_authorization_bypass"
    assert body["findings"][0]["evidenceSequences"] == [2, 3]
    assert body["semanticReview"]["performed"] is False


def test_include_true_without_finding_does_not_call_provider() -> None:
    provider = FakeProvider()

    with TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    ) as client:
        response = client.post(
            "/api/evaluations",
            json=_payload(_normal_trace(), include=True),
        )

    assert response.status_code == 200
    assert provider.calls == []
    body = response.json()
    assert body["status"] == "passed"
    assert body["findings"] == []
    assert body["semanticReview"] == {
        "performed": False,
        "explanation": None,
    }


def test_semantic_review_only_adds_explanation_and_preserves_deterministic_result() -> None:
    deterministic_provider = FakeProvider(answer="must not be called")
    review_provider = FakeProvider(answer="补充：拒绝资源仍进入模型上下文。")

    with TestClient(
        create_app(
            provider=deterministic_provider,
            retriever=make_tfidf_retriever(),
        )
    ) as client:
        deterministic_response = client.post(
            "/api/evaluations",
            json=_payload(_resource_finding_trace(), include=False),
        )
    with TestClient(
        create_app(
            provider=review_provider,
            retriever=make_tfidf_retriever(),
        )
    ) as client:
        reviewed_response = client.post(
            "/api/evaluations",
            json=_payload(_resource_finding_trace(), include=True),
        )

    assert deterministic_response.status_code == 200
    assert reviewed_response.status_code == 200
    deterministic = deterministic_response.json()
    reviewed = reviewed_response.json()
    assert len(review_provider.calls) == 1
    assert reviewed["status"] == deterministic["status"]
    assert reviewed["contractId"] == deterministic["contractId"]
    assert reviewed["contractVersion"] == deterministic["contractVersion"]
    assert reviewed["findings"] == deterministic["findings"]
    assert reviewed["semanticReview"] == {
        "performed": True,
        "explanation": "补充：拒绝资源仍进入模型上下文。",
    }


@pytest.mark.parametrize(
    "provider_factory",
    [InvalidProvider, UnavailableProvider],
)
def test_semantic_provider_errors_map_to_gateway_error(provider_factory) -> None:
    provider = provider_factory()

    with TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    ) as client:
        response = client.post(
            "/api/evaluations",
            json=_payload(_resource_finding_trace(), include=True),
        )

    assert response.status_code == 502
    assert provider.calls == 1
    detail = response.json()["detail"]
    assert any(term in detail for term in ("无法识别", "未形成有效结论", "未完成"))
    assert "重新" in detail
    assert "invalid response" not in detail.lower()
    assert "provider unavailable in test" not in detail
