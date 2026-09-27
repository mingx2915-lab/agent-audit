from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse, ToolCall
from tests.retriever_support import make_tfidf_retriever


@dataclass
class FakeProvider:
    """Deterministic provider double; no network or production key is used."""

    answer: str = "这是测试 Provider 返回的合成回答。"
    tool_call: ToolCall | None = None
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if self.tool_call is not None and len(self.calls) == 1:
            return LLMResponse(content="", tool_calls=(self.tool_call,))
        return LLMResponse(content=self.answer, tool_calls=())


class InvalidProvider:
    async def complete(self, messages, tools=None):
        return object()


def _client(provider: FakeProvider) -> TestClient:
    return TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    )


def test_demo_actors_route_returns_contract_shape() -> None:
    client = _client(FakeProvider())

    response = client.get("/api/demo/actors")

    assert response.status_code == 200
    actors = response.json()
    assert actors
    assert all(set(actor) == {"id", "displayName", "role"} for actor in actors)
    sales_actor = next(actor for actor in actors if actor["id"] == "sales_001")
    assert sales_actor == {
        "id": "sales_001",
        "displayName": "张三",
        "role": "sales",
    }


def test_query_rejects_unknown_actor_without_calling_provider() -> None:
    provider = FakeProvider()
    client = _client(provider)

    response = client.post(
        "/api/assistant/queries",
        json={"actorId": "actor_missing", "message": "查询客户合同"},
    )

    assert response.status_code == 404
    assert provider.calls == []


@pytest.mark.parametrize("message", ["", "   ", "\n\t"])
def test_query_rejects_empty_message_without_calling_provider(message: str) -> None:
    provider = FakeProvider()
    client = _client(provider)

    response = client.post(
        "/api/assistant/queries",
        json={"actorId": "sales_001", "message": message},
    )

    assert response.status_code in {400, 422}
    assert provider.calls == []


def test_retrieval_query_uses_fake_provider_and_records_trace(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = FakeProvider(answer="合同摘要（Fake Provider）。")
    client = _client(provider)

    response = client.post(
        "/api/assistant/queries",
        json={"actorId": "sales_001", "message": "总结我的客户合同"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["queryId"]
    assert payload["actor"] == {
        "id": "sales_001",
        "displayName": "张三",
        "role": "sales",
    }
    assert payload["answer"] == "合同摘要（Fake Provider）。"
    assert len(provider.calls) == 1

    events = payload["traceEvents"]
    assert events
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    event_types = [event["type"] for event in events]
    assert event_types[0] == "input"
    assert event_types[1] == "source"
    assert "retrieval" in event_types
    assert "authorization" in event_types
    assert event_types[-2] == "model_response"
    assert event_types[-1] == "sink"

    input_event = events[0]
    assert input_event["details"] == {
        "actorId": "sales_001",
        "message": "总结我的客户合同",
    }

    retrieval_event = next(event for event in events if event["type"] == "retrieval")
    assert retrieval_event["details"]["query"] == "总结我的客户合同"
    assert retrieval_event["details"]["documentIds"]
    assert len(retrieval_event["details"]["documentIds"]) == len(
        retrieval_event["details"]["scores"]
    )

    authorization_events = [
        event for event in events if event["type"] == "authorization"
    ]
    assert authorization_events
    for event in authorization_events:
        assert set(event["details"]) == {
            "actorId",
            "documentId",
            "decision",
            "ruleId",
        }
        assert event["details"]["actorId"] == "sales_001"
        assert event["details"]["decision"] in {"allowed", "denied"}
        assert event["details"]["ruleId"] is None or isinstance(
            event["details"]["ruleId"], str
        )

    model_event = next(event for event in events if event["type"] == "model_response")
    assert model_event["details"] == {
        "content": "合同摘要（Fake Provider）。",
        "toolCallCount": 0,
    }


def test_tool_query_executes_mock_tool_and_records_arguments_and_result(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = FakeProvider(
        answer="客户摘要（Fake Provider）。",
        tool_call=ToolCall(
            id="call_customer_001",
            name="mock_customer_lookup",
            arguments={"customerId": "customer_001"},
        ),
    )
    client = _client(provider)

    response = client.post(
        "/api/assistant/queries",
        json={"actorId": "sales_001", "message": "查询客户 customer_001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "客户摘要（Fake Provider）。"
    assert len(provider.calls) == 2

    events = payload["traceEvents"]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    event_types = [event["type"] for event in events]
    assert event_types[0] == "input"
    assert event_types[1] == "source"
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert event_types[-2] == "model_response"
    assert event_types[-1] == "sink"

    tool_call_event = next(event for event in events if event["type"] == "tool_call")
    assert tool_call_event["details"] == {
        "toolName": "mock_customer_lookup",
        "arguments": {"customerId": "customer_001"},
    }

    tool_result_event = next(
        event for event in events if event["type"] == "tool_result"
    )
    tool_result_details = tool_result_event["details"]
    assert tool_result_details["toolName"] == "mock_customer_lookup"
    assert tool_result_details["success"] is True
    assert tool_result_details["summary"]
    assert tool_result_details["data"] == {
        "customerId": "customer_001",
        "name": "蓝海科技（合成）",
        "ownerId": "sales_001",
        "summary": (
            "SYNTHETIC / DEMO ONLY。企业版客户，合同状态为 active，"
            "续约窗口在 2026 年第四季度。"
        ),
    }


def test_explicit_provider_injection_does_not_require_deepseek_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = FakeProvider(answer="离线测试回答")

    with TestClient(
        create_app(provider=provider, retriever=make_tfidf_retriever())
    ) as client:
        response = client.post(
            "/api/assistant/queries",
            json={"actorId": "sales_001", "message": "查询公开资料"},
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "离线测试回答"


def test_invalid_provider_response_is_reported_as_gateway_error(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with TestClient(
        create_app(
            provider=InvalidProvider(),
            retriever=make_tfidf_retriever(),
        )
    ) as client:
        response = client.post(
            "/api/assistant/queries",
            json={"actorId": "sales_001", "message": "查询公开资料"},
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert any(term in detail for term in ("无法识别", "未形成有效结论", "未完成"))
    assert "重新" in detail
    assert "invalid response" not in detail.lower()
