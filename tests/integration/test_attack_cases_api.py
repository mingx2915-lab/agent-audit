from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse
from tests.retriever_support import make_tfidf_retriever


@dataclass
class FakeProvider:
    answer: str = "固定 Case API 测试回答"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return LLMResponse(content=self.answer, tool_calls=())


def _client(provider: FakeProvider) -> TestClient:
    return TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    )


def _case_by_type(cases: list[dict[str, Any]], attacker_type: str) -> dict[str, Any]:
    return next(case for case in cases if case["attackerType"] == attacker_type)


def _events(result: dict[str, Any]) -> list[dict[str, Any]]:
    return result["queryResult"]["traceEvents"]


def _context_ids(events: list[dict[str, Any]]) -> set[str]:
    context = next(
        event
        for event in events
        if event["type"] == "sink"
        and event["details"].get("sinkType") == "model_context"
    )
    return set(context["details"]["documentIds"])


def test_attack_case_list_contains_exactly_outside_in_and_inside_out() -> None:
    with _client(FakeProvider()) as client:
        response = client.get("/api/attack-cases")

    assert response.status_code == 200
    cases = response.json()
    assert len(cases) == 2
    assert {case["attackerType"] for case in cases} == {"outside_in", "inside_out"}
    assert all(
        set(case)
        == {
            "id",
            "name",
            "description",
            "attackerType",
            "actorId",
            "message",
            "targetProfileId",
            "expectedFindingCategories",
        }
        for case in cases
    )


def test_default_assistant_query_remains_secure_and_excludes_denied_document() -> None:
    provider = FakeProvider()
    with _client(provider) as client:
        cases = client.get("/api/attack-cases").json()
        inside = _case_by_type(cases, "inside_out")
        response = client.post(
            "/api/assistant/queries",
            json={"actorId": inside["actorId"], "message": inside["message"]},
        )

    assert response.status_code == 200
    events = response.json()["traceEvents"]
    denied_ids = {
        event["details"]["documentId"]
        for event in events
        if event["type"] == "authorization"
        and event["details"].get("decision") == "denied"
        and "documentId" in event["details"]
    }
    assert "doc_customer_contract_002" in denied_ids
    assert "doc_customer_contract_002" not in _context_ids(events)
    assert len(provider.calls) == 1


def test_inside_out_execution_retrieves_non_owner_document_and_finds_bypass() -> None:
    provider = FakeProvider()
    with _client(provider) as client:
        case = _case_by_type(client.get("/api/attack-cases").json(), "inside_out")
        response = client.post(f"/api/attack-cases/{case['id']}/execute")

    assert response.status_code == 200
    result = response.json()
    events = _events(result)
    retrieval = next(event for event in events if event["type"] == "retrieval")
    assert "doc_customer_contract_002" in retrieval["details"]["documentIds"]
    assert "doc_customer_contract_002" in _context_ids(events)
    assert result["evaluation"]["status"] == "failed"
    assert any(
        finding["category"] == "resource_authorization_bypass"
        for finding in result["evaluation"]["findings"]
    )
    assert any(event["type"] == "retrieval" for event in events)
    assert any(event["type"] == "model_response" for event in events)
    assert result["evaluation"]["semanticReview"]["performed"] is False
    assert len(provider.calls) == 1


def test_outside_in_execution_has_untrusted_source_and_context_finding() -> None:
    provider = FakeProvider()
    with _client(provider) as client:
        case = _case_by_type(client.get("/api/attack-cases").json(), "outside_in")
        response = client.post(f"/api/attack-cases/{case['id']}/execute")

    assert response.status_code == 200
    result = response.json()
    events = _events(result)
    assert any(
        event["type"] == "source"
        and event["details"].get("sourceType") == "external_document"
        and event["details"].get("trustLevel") == "untrusted"
        for event in events
    )
    denied_ids = {
        event["details"]["documentId"]
        for event in events
        if event["type"] == "authorization"
        and event["details"].get("decision") == "denied"
        and "documentId" in event["details"]
    }
    # F-015 explicitly allows the synthetic external-document source to enter
    # context; the finance document remains the restricted resource.
    allowed_ids = {
        event["details"]["documentId"]
        for event in events
        if event["type"] == "authorization"
        and event["details"].get("decision") == "allowed"
        and "documentId" in event["details"]
    }
    assert "doc_external_vendor_prompt_001" in allowed_ids
    assert "doc_external_vendor_prompt_001" not in denied_ids
    assert "doc_finance_budget_001" in denied_ids
    assert "doc_finance_budget_001" in _context_ids(events)
    assert denied_ids & _context_ids(events)
    assert result["evaluation"]["status"] == "failed"
    assert any(
        finding["category"] == "resource_authorization_bypass"
        for finding in result["evaluation"]["findings"]
    )
    assert any(event["type"] == "retrieval" for event in events)
    assert any(event["type"] == "model_response" for event in events)
    assert result["evaluation"]["semanticReview"]["performed"] is False
    assert len(provider.calls) == 1


def test_unknown_attack_case_returns_404() -> None:
    with _client(FakeProvider()) as client:
        response = client.post("/api/attack-cases/case_missing/execute")

    assert response.status_code == 404
