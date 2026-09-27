"""F-023 process-local API coverage for Contract Preview and its side effects."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse
from tests.retriever_support import make_tfidf_retriever


@dataclass
class PreviewProvider:
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return LLMResponse(content="不会被 Preview 调用")


class SpyHistoryRepository:
    """A repository double that makes any Preview history access observable."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def save(self, detail) -> None:
        self.calls.append("save")

    def list(self, limit: int = 20):
        self.calls.append("list")
        return []

    def get(self, scan_id: str):
        self.calls.append("get")
        return None

    def append_replay(self, scan_id: str, persisted_replay) -> None:
        self.calls.append("append_replay")


def _client(
    provider: PreviewProvider | None = None,
    repository: SpyHistoryRepository | None = None,
) -> tuple[TestClient, PreviewProvider, SpyHistoryRepository]:
    active_provider = provider or PreviewProvider()
    history_repository = repository or SpyHistoryRepository()
    return (
        TestClient(
            create_app(
                provider=active_provider,
                retriever=make_tfidf_retriever(),
                history_repository=history_repository,
            )
        ),
        active_provider,
        history_repository,
    )


def _payload_and_plans(client: TestClient) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract_response = client.get("/api/security-contract")
    plans_response = client.get("/api/attack-plans")
    assert contract_response.status_code == 200
    assert plans_response.status_code == 200
    return contract_response.json(), plans_response.json()


def test_unchanged_preview_is_read_only_and_returns_complete_shape() -> None:
    client, provider, repository = _client()
    with client:
        active, plans = _payload_and_plans(client)
        response = client.post("/api/security-contract/previews", json=active)
        after_contract = client.get("/api/security-contract")
        after_plans = client.get("/api/attack-plans")

    assert response.status_code == 200, response.text
    preview = response.json()
    assert set(preview) == {
        "contractId",
        "activeVersion",
        "candidateVersion",
        "fieldChanges",
        "planChanges",
        "currentPlans",
        "candidatePlans",
    }
    assert preview["contractId"] == active["id"]
    assert preview["activeVersion"] == active["version"]
    assert preview["candidateVersion"] == active["version"]
    assert preview["fieldChanges"] == []
    assert preview["planChanges"] == []
    assert preview["currentPlans"] == plans
    assert preview["candidatePlans"] == plans
    assert after_contract.json() == active
    assert after_plans.json() == plans
    assert provider.calls == []
    assert repository.calls == []


def test_preview_reports_stable_field_paths_and_planner_plan_impact() -> None:
    client, provider, repository = _client()
    with client:
        active, current_plans = _payload_and_plans(client)
        candidate = deepcopy(active)
        candidate["name"] = "F-023 候选 Contract"
        candidate["resourceRules"] = [
            rule
            for rule in candidate["resourceRules"]
            if rule["id"] != "resource_public_all"
        ]
        candidate["resourceRules"].append(
            {
                "id": "resource_preview_added",
                "description": "F-023 预览新增规则",
                "matchLabels": ["public"],
                "allowedRoles": ["admin"],
                "requireOwnerMatch": False,
            }
        )
        candidate["resourceRules"] = list(reversed(candidate["resourceRules"]))
        owner_rule = next(
            rule
            for rule in candidate["resourceRules"]
            if rule["id"] == "resource_customer_owner"
        )
        owner_rule["requireOwnerMatch"] = False
        customer_tool_rule = next(
            rule
            for rule in candidate["toolRules"]
            if rule["id"] == "tool_customer_owner_read"
        )
        customer_tool_rule["allowedRoles"] = ["sales", "admin"]

        response = client.post("/api/security-contract/previews", json=candidate)
        active_after = client.get("/api/security-contract")
        plans_after = client.get("/api/attack-plans")

    assert response.status_code == 200, response.text
    preview = response.json()
    assert [item["path"] for item in preview["fieldChanges"]] == [
        "name",
        "resourceRules[resource_customer_owner].requireOwnerMatch",
        "resourceRules[resource_preview_added]",
        "resourceRules[resource_public_all]",
        "toolRules[tool_customer_owner_read].allowedRoles",
    ]
    assert [item["kind"] for item in preview["fieldChanges"]] == [
        "changed",
        "changed",
        "added",
        "removed",
        "changed",
    ]
    assert preview["fieldChanges"][0]["beforeValue"] == active["name"]
    assert preview["fieldChanges"][0]["afterValue"] == "F-023 候选 Contract"

    assert [item["planId"] for item in preview["planChanges"]] == [
        "plan_resource_customer_owner",
        "plan_tool_customer_owner_read",
    ]
    assert [item["kind"] for item in preview["planChanges"]] == [
        "removed",
        "changed",
    ]
    assert preview["planChanges"][0]["basisType"] == "resource_owner_scope"
    assert preview["planChanges"][0]["basisRuleId"] == "resource_customer_owner"
    assert preview["planChanges"][1]["basisType"] == "tool_owner_scope"
    assert preview["planChanges"][1]["basisRuleId"] == "tool_customer_owner_read"
    assert preview["currentPlans"] == current_plans
    assert "plan_resource_customer_owner" not in {
        plan["id"] for plan in preview["candidatePlans"]
    }
    changed_plan = next(
        plan
        for plan in preview["candidatePlans"]
        if plan["id"] == "plan_tool_customer_owner_read"
    )
    assert changed_plan["actorId"] == "admin_001"

    assert active_after.json() == active
    assert plans_after.json() == current_plans
    assert provider.calls == []
    assert repository.calls == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"unexpected": True}),
        lambda payload: payload["roles"][0].update({"unexpected": True}),
        lambda payload: payload.update({"version": "invalid"}),
        lambda payload: payload["toolRules"][0].update({"maxRecords": "invalid"}),
    ],
)
def test_preview_rejects_invalid_or_extra_contract_fields_without_provider_calls(
    mutate,
) -> None:
    client, provider, repository = _client()
    with client:
        active, _ = _payload_and_plans(client)
        original = deepcopy(active)
        mutate(active)
        response = client.post("/api/security-contract/previews", json=active)
        after = client.get("/api/security-contract")

    assert response.status_code == 422
    assert response.json()["detail"]
    # Rejected candidates never replace the active Contract, including its version.
    assert after.json() == original
    assert provider.calls == []
    assert repository.calls == []
