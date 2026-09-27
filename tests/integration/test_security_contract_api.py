from dataclasses import dataclass, field
from typing import Any

from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse, ToolCall
from tests.retriever_support import make_tfidf_retriever


@dataclass
class FakeProvider:
    answer: str = "合同摘要（Contract 测试 Provider）。"
    tool_call: ToolCall | None = None
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if self.tool_call is not None and len(self.calls) == 1:
            return LLMResponse(content="", tool_calls=(self.tool_call,))
        return LLMResponse(content=self.answer, tool_calls=())


def _client(provider: FakeProvider | None = None) -> TestClient:
    return TestClient(
        create_app(
            provider=provider or FakeProvider(),
            retriever=make_tfidf_retriever(),
        )
    )


def _contract_payload() -> dict[str, object]:
    return {
        "id": "contract_test_api",
        "name": "测试 Contract",
        "version": 2,
        "roles": [
            {"id": "sales", "displayName": "销售"},
            {"id": "admin", "displayName": "管理员"},
            {"id": "employee", "displayName": "员工"},
        ],
        "resourceRules": [
            {
                "id": "resource_customer_owner",
                "description": "销售只能读取本人客户资料",
                "matchLabels": ["customer", "contract"],
                "allowedRoles": ["sales"],
                "requireOwnerMatch": True,
            }
        ],
        "toolRules": [
            {
                "id": "tool_customer_owner_read",
                "description": "销售只能读取本人客户记录",
                "toolName": "mock_customer_lookup",
                "action": "read",
                "allowedRoles": ["sales"],
                "requireOwnerMatch": True,
                "maxRecords": None,
                "requireApproval": False,
            }
        ],
        "sinkRules": [],
    }


def test_get_security_contract_returns_complete_default_contract() -> None:
    with _client() as client:
        response = client.get("/api/security-contract")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "id",
        "name",
        "version",
        "roles",
        "resourceRules",
        "toolRules",
        "sinkRules",
    }
    assert payload["roles"]
    assert payload["resourceRules"]
    assert payload["toolRules"]


def test_put_security_contract_is_validated_and_applies_to_following_query() -> None:
    provider = FakeProvider(answer="根据更新后的 Contract 生成的回答")
    with _client(provider) as client:
        put_response = client.put("/api/security-contract", json=_contract_payload())
        get_response = client.get("/api/security-contract")
        query_response = client.post(
            "/api/assistant/queries",
            json={"actorId": "sales_001", "message": "customer_001 客户合同"},
        )

    assert put_response.status_code == 200
    assert put_response.json() == _contract_payload()
    assert get_response.status_code == 200
    assert get_response.json() == _contract_payload()
    assert query_response.status_code == 200

    events = query_response.json()["traceEvents"]
    authorization_events = [
        event for event in events if event["type"] == "authorization"
    ]
    assert authorization_events
    resource_events = [
        event
        for event in authorization_events
        if "documentId" in event["details"]
    ]
    assert resource_events
    assert all(
        {"actorId", "documentId", "decision", "ruleId"}
        <= set(event["details"])
        for event in resource_events
    )
    customer_contract_events = [
        event
        for event in resource_events
        if event["details"]["documentId"] == "doc_customer_contract_001"
    ]
    assert customer_contract_events
    assert any(
        event["details"]["decision"] == "allowed"
        and event["details"]["ruleId"] == "resource_customer_owner"
        for event in customer_contract_events
    )


def test_put_rejects_duplicate_rule_ids_and_unknown_role_references() -> None:
    duplicate_rule_payload = _contract_payload()
    duplicate_rule_payload["resourceRules"] = [
        {
            **duplicate_rule_payload["resourceRules"][0],
            "id": "duplicate",
        },
        {
            **duplicate_rule_payload["resourceRules"][0],
            "id": "duplicate",
        },
    ]
    unknown_role_payload = _contract_payload()
    unknown_role_payload["resourceRules"] = [
        {
            **unknown_role_payload["resourceRules"][0],
            "allowedRoles": ["hr"],
        }
    ]

    with _client() as client:
        duplicate_response = client.put(
            "/api/security-contract", json=duplicate_rule_payload
        )
        unknown_role_response = client.put(
            "/api/security-contract", json=unknown_role_payload
        )

    assert duplicate_response.status_code == 422
    assert unknown_role_response.status_code == 422


def test_tool_authorization_trace_contains_rule_id_after_contract_update() -> None:
    provider = FakeProvider(
        answer="客户摘要（Contract 测试 Provider）。",
        tool_call=ToolCall(
            id="call_customer_001",
            name="mock_customer_lookup",
            arguments={"customerId": "customer_001"},
        ),
    )
    with _client(provider) as client:
        put_response = client.put("/api/security-contract", json=_contract_payload())
        query_response = client.post(
            "/api/assistant/queries",
            json={"actorId": "sales_001", "message": "查询 customer_001"},
        )

    assert put_response.status_code == 200
    assert query_response.status_code == 200
    events = query_response.json()["traceEvents"]
    tool_authorization_events = [
        event
        for event in events
        if event["type"] == "authorization"
        and "toolName" in event["details"]
    ]
    assert tool_authorization_events
    assert any(
        event["details"] == {
            "actorId": "sales_001",
            "toolName": "mock_customer_lookup",
            "action": "read",
            "decision": "allowed",
            "ruleId": "tool_customer_owner_read",
        }
        for event in tool_authorization_events
    )
