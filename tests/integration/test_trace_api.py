from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse, ToolCall
from tests.retriever_support import make_tfidf_retriever


@dataclass
class FakeProvider:
    answer: str = "这是 F-005 测试回答。"
    tool_call: ToolCall | None = None
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if self.tool_call is not None and len(self.calls) == 1:
            return LLMResponse(content="", tool_calls=(self.tool_call,))
        return LLMResponse(content=self.answer, tool_calls=())


def _client(provider: FakeProvider) -> TestClient:
    return TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    )


def _assert_continuous_sequence(events: list[dict[str, Any]]) -> None:
    assert events
    assert [event["sequence"] for event in events] == list(
        range(1, len(events) + 1)
    )


def _assert_user_input_source(event: dict[str, Any], actor_id: str) -> None:
    assert event["type"] == "source"
    details = event["details"]
    assert details["sourceId"]
    assert details["sourceType"] == "user_input"
    assert details["actorId"] == actor_id
    assert details["trustLevel"] == "trusted"


def _assert_document_sources(
    events: list[dict[str, Any]], retrieved_ids: list[str]
) -> None:
    document_sources = [
        event
        for event in events
        if event["type"] == "source" and "documentId" in event["details"]
    ]
    assert [event["details"]["documentId"] for event in document_sources] == retrieved_ids
    for event in document_sources:
        details = event["details"]
        assert details["sourceId"]
        assert details["sourceType"]
        assert details["trustLevel"]
        assert details["documentId"] in retrieved_ids


def test_retrieval_trace_records_sources_authorized_context_and_actor_sink() -> None:
    provider = FakeProvider(answer="合同摘要（F-005）。")

    with _client(provider) as client:
        response = client.post(
            "/api/assistant/queries",
            json={"actorId": "sales_001", "message": "总结我的客户合同"},
        )

    assert response.status_code == 200
    events = response.json()["traceEvents"]
    _assert_continuous_sequence(events)

    input_event, user_source_event, retrieval_event = events[:3]
    assert input_event["type"] == "input"
    _assert_user_input_source(user_source_event, "sales_001")
    assert retrieval_event["type"] == "retrieval"
    retrieved_ids = retrieval_event["details"]["documentIds"]
    assert retrieved_ids
    _assert_document_sources(events, retrieved_ids)

    authorization_events = [
        event
        for event in events
        if event["type"] == "authorization"
        and "documentId" in event["details"]
    ]
    assert [event["details"]["documentId"] for event in authorization_events] == retrieved_ids
    allowed_ids = {
        event["details"]["documentId"]
        for event in authorization_events
        if event["details"]["decision"] == "allowed"
    }

    model_context_sinks = [
        event
        for event in events
        if event["type"] == "sink"
        and event["details"].get("sinkType") == "model_context"
    ]
    assert len(model_context_sinks) == 1
    first_context = model_context_sinks[0]["details"]
    assert first_context["sinkId"] == "model_context"
    assert first_context["includesToolResult"] is False
    assert set(first_context["documentIds"]) == allowed_ids
    assert set(first_context["documentIds"]) <= set(retrieved_ids)

    response_sink = events[-1]
    assert response_sink["type"] == "sink"
    assert response_sink["details"] == {
        "sinkId": "actor_response",
        "sinkType": "actor_response",
        "actorId": "sales_001",
    }
    assert events[-2]["type"] == "model_response"

    expected_types = ["input", "source", "retrieval"]
    expected_types.extend(value for _ in retrieved_ids for value in ("source", "authorization"))
    expected_types.extend(["sink", "model_response", "sink"])
    assert [event["type"] for event in events] == expected_types


def test_tool_trace_records_second_context_sink_with_tool_result() -> None:
    provider = FakeProvider(
        answer="客户摘要（F-005）。",
        tool_call=ToolCall(
            id="call_customer_001",
            name="mock_customer_lookup",
            arguments={"customerId": "customer_001"},
        ),
    )

    with _client(provider) as client:
        response = client.post(
            "/api/assistant/queries",
            json={"actorId": "sales_001", "message": "查询客户 customer_001"},
        )

    assert response.status_code == 200
    events = response.json()["traceEvents"]
    _assert_continuous_sequence(events)
    retrieval_event = next(event for event in events if event["type"] == "retrieval")
    retrieved_ids = retrieval_event["details"]["documentIds"]
    assert retrieved_ids
    _assert_document_sources(events, retrieved_ids)

    context_sinks = [
        event
        for event in events
        if event["type"] == "sink"
        and event["details"].get("sinkType") == "model_context"
    ]
    assert len(context_sinks) == 2
    first_context, second_context = [event["details"] for event in context_sinks]
    assert first_context["includesToolResult"] is False
    assert second_context["includesToolResult"] is True
    assert first_context["documentIds"] == second_context["documentIds"]

    tool_authorization = next(
        event
        for event in events
        if event["type"] == "authorization"
        and "toolName" in event["details"]
    )
    assert tool_authorization["details"]["ruleId"] == "tool_customer_owner_read"
    assert tool_authorization["details"]["decision"] == "allowed"
    assert next(event for event in events if event["type"] == "tool_call")
    assert next(event for event in events if event["type"] == "tool_result")
    assert events[-2]["type"] == "model_response"
    assert events[-1]["details"] == {
        "sinkId": "actor_response",
        "sinkType": "actor_response",
        "actorId": "sales_001",
    }

    expected_types = ["input", "source", "retrieval"]
    expected_types.extend(value for _ in retrieved_ids for value in ("source", "authorization"))
    expected_types.extend(
        [
            "sink",
            "authorization",
            "tool_call",
            "tool_result",
            "sink",
            "model_response",
            "sink",
        ]
    )
    assert [event["type"] for event in events] == expected_types
