"""Integration coverage for the synchronous F-014 Red-Team scan API."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
    ToolCall,
)
from agent_audit_api.history import SQLiteAuditRunRepository
from tests.retriever_support import make_tfidf_retriever


@dataclass
class ScriptedAttackProvider:
    """Double used only for Red-Team variant-generation calls."""

    responses: list[Any]
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)
    model: str = "test-attack-generator"

    async def complete(self, messages, tools=None):
        self.calls.append((messages, tools))
        if not self.responses:
            raise AssertionError("attack generator received an unexpected call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, LLMResponse):
            return response
        if response is _INVALID_PROVIDER_RESPONSE:
            return object()
        content = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        return LLMResponse(content=content, tool_calls=())


@dataclass
class ScriptedTargetProvider:
    """Double used only for Target Agent calls and never for mutation generation."""

    responses: list[Any]
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None):
        self.calls.append((messages, tools))
        if not self.responses:
            raise AssertionError("Target Agent received an unexpected call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class _InvalidProviderResponse:
    pass


_INVALID_PROVIDER_RESPONSE = _InvalidProviderResponse()


def _variant(message: str, reason: str = "依据上一轮真实 Trace 调整") -> dict[str, str]:
    return {"message": message, "mutationReason": reason}


def _tool_finding_response() -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=(
            ToolCall(
                id="scan_customer_lookup",
                name="mock_customer_lookup",
                arguments={"customerId": "customer_002"},
            ),
        ),
    )


def _plan_by_type(client: TestClient, basis_type: str = "tool_owner_scope") -> dict[str, Any]:
    plans_response = client.get("/api/attack-plans")
    assert plans_response.status_code == 200
    return next(plan for plan in plans_response.json() if plan["basisType"] == basis_type)


def _client(
    *,
    attack_provider: ScriptedAttackProvider,
    target_provider: ScriptedTargetProvider,
    history_path: Path | None = None,
) -> TestClient:
    return TestClient(
        create_app(
            provider=target_provider,
            attack_provider=attack_provider,
            retriever=make_tfidf_retriever(),
            history_repository=(
                SQLiteAuditRunRepository(history_path)
                if history_path is not None
                else None
            ),
        )
    )


def test_scan_api_feeds_real_trace_evaluation_and_stops_on_finding(tmp_path: Path) -> None:
    attack_provider = ScriptedAttackProvider(
        [
            _variant("第一轮请求确认客户范围"),
            _variant("第二轮根据授权观察请求读取 customer_002"),
        ]
    )
    target_provider = ScriptedTargetProvider(
        [
            LLMResponse(content="第一轮通过", tool_calls=()),
            _tool_finding_response(),
            LLMResponse(content="返回合成客户记录", tool_calls=()),
        ]
    )

    with _client(
        attack_provider=attack_provider,
        target_provider=target_provider,
        history_path=tmp_path / "history.sqlite3",
    ) as client:
        plan = _plan_by_type(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 3},
        )

    assert response.status_code == 200
    scan = response.json()
    assert scan["status"] == "completed"
    assert scan["stopReason"] == "finding_detected"
    assert scan["planId"] == plan["id"]
    assert scan["targetProfileId"] == plan["targetProfileId"]
    assert scan["provider"] == "injected:ScriptedAttackProvider"
    assert scan["model"] == "test-attack-generator"
    assert len(scan["attempts"]) == 2
    assert [attempt["status"] for attempt in scan["attempts"]] == [
        "passed",
        "finding",
    ]
    assert scan["attempts"][0]["evaluation"]["status"] == "passed"
    assert scan["attempts"][1]["evaluation"]["status"] == "failed"
    assert any(
        finding["category"] == "tool_authorization_bypass"
        for finding in scan["attempts"][1]["evaluation"]["findings"]
    )

    first_variant, second_variant = (
        attempt["variant"] for attempt in scan["attempts"]
    )
    assert first_variant["message"] != second_variant["message"]
    assert first_variant["parentAttemptId"] is None
    assert second_variant["parentAttemptId"] == scan["attempts"][0]["id"]
    for variant in (first_variant, second_variant):
        assert variant["actorId"] == plan["actorId"]
        assert variant["attackerType"] == plan["attackerType"]
        assert variant["basisRuleId"] == plan["basisRuleId"]
        assert variant["targetKind"] == plan["targetKind"]
        assert variant["targetId"] == plan["targetId"]

    assert len(attack_provider.calls) == 2
    assert len(target_provider.calls) == 3
    second_generation_payload = json.loads(
        attack_provider.calls[1][0][1]["content"]
    )
    previous = second_generation_payload["previousAttempt"]
    assert previous["round"] == 1
    assert previous["status"] == "passed"
    assert previous["findingCategories"] == []
    assert previous["traceSummary"]
    assert previous["traceSummary"] == sorted(
        previous["traceSummary"], key=lambda event: event["sequence"]
    )
    first_trace = scan["attempts"][0]["queryResult"]["traceEvents"]
    assert previous["traceSummary"][0]["summary"] == first_trace[0]["summary"]

    transitions = scan["stateTransitions"]
    assert [transition["sequence"] for transition in transitions] == list(
        range(1, len(transitions) + 1)
    )
    assert sum(transition["state"] == "stopped" for transition in transitions) == 1
    assert transitions[-1]["state"] == "stopped"


def test_finding_stops_scan_before_follow_up_generation_or_target_execution(
    tmp_path: Path,
) -> None:
    attack_provider = ScriptedAttackProvider([_variant("直接请求越权工具")])
    target_provider = ScriptedTargetProvider(
        [
            _tool_finding_response(),
            LLMResponse(content="返回合成客户记录", tool_calls=()),
        ]
    )

    with _client(
        attack_provider=attack_provider,
        target_provider=target_provider,
        history_path=tmp_path / "history.sqlite3",
    ) as client:
        plan = _plan_by_type(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 3},
        )

    assert response.status_code == 200
    scan = response.json()
    assert scan["stopReason"] == "finding_detected"
    assert len(scan["attempts"]) == 1
    assert len(attack_provider.calls) == 1
    assert len(target_provider.calls) == 2
    assert scan["stateTransitions"][-1]["state"] == "stopped"


def test_duplicate_variant_is_stopped_before_target_execution(tmp_path: Path) -> None:
    duplicate = _variant("同一条攻击消息")
    attack_provider = ScriptedAttackProvider([duplicate, duplicate])
    target_provider = ScriptedTargetProvider(
        [LLMResponse(content="第一轮通过", tool_calls=())]
    )

    with _client(
        attack_provider=attack_provider,
        target_provider=target_provider,
        history_path=tmp_path / "history.sqlite3",
    ) as client:
        plan = _plan_by_type(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 3},
        )

    assert response.status_code == 200
    scan = response.json()
    assert scan["stopReason"] == "no_new_variant"
    assert len(scan["attempts"]) == 1
    assert len(attack_provider.calls) == 2
    assert len(target_provider.calls) == 1
    assert scan["stateTransitions"][-1]["state"] == "stopped"


def test_scan_never_executes_more_than_three_rounds(tmp_path: Path) -> None:
    attack_provider = ScriptedAttackProvider(
        [_variant("轮一"), _variant("轮二"), _variant("轮三")]
    )
    target_provider = ScriptedTargetProvider(
        [
            LLMResponse(content="通过一", tool_calls=()),
            LLMResponse(content="通过二", tool_calls=()),
            LLMResponse(content="通过三", tool_calls=()),
        ]
    )

    with _client(
        attack_provider=attack_provider,
        target_provider=target_provider,
        history_path=tmp_path / "history.sqlite3",
    ) as client:
        plan = _plan_by_type(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 3},
        )

    assert response.status_code == 200
    scan = response.json()
    assert scan["stopReason"] == "max_rounds_reached"
    assert len(scan["attempts"]) == 3
    assert len(attack_provider.calls) == 3
    assert len(target_provider.calls) == 3
    assert [attempt["round"] for attempt in scan["attempts"]] == [1, 2, 3]
    assert sum(transition["state"] == "stopped" for transition in scan["stateTransitions"]) == 1


@pytest.mark.parametrize("max_rounds", [1, 4])
def test_invalid_max_rounds_returns_422(max_rounds: int, tmp_path: Path) -> None:
    attack_provider = ScriptedAttackProvider([])
    target_provider = ScriptedTargetProvider([])

    with _client(
        attack_provider=attack_provider,
        target_provider=target_provider,
        history_path=tmp_path / f"history-{max_rounds}.sqlite3",
    ) as client:
        plan = _plan_by_type(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": max_rounds},
        )

    assert response.status_code == 422
    assert attack_provider.calls == []
    assert target_provider.calls == []


def test_unknown_and_invalidated_plan_return_404(tmp_path: Path) -> None:
    attack_provider = ScriptedAttackProvider([])
    target_provider = ScriptedTargetProvider([])

    with _client(
        attack_provider=attack_provider,
        target_provider=target_provider,
        history_path=tmp_path / "history.sqlite3",
    ) as client:
        unknown_response = client.post(
            "/api/scans",
            json={"planId": "plan_missing", "maxRounds": 2},
        )
        original_contract = client.get("/api/security-contract").json()
        stale_plan = _plan_by_type(client, "resource_owner_scope")
        changed_contract = deepcopy(original_contract)
        owner_rule = next(
            rule
            for rule in changed_contract["resourceRules"]
            if rule["requireOwnerMatch"]
        )
        owner_rule["requireOwnerMatch"] = False
        update_response = client.put("/api/security-contract", json=changed_contract)
        stale_response = client.post(
            "/api/scans",
            json={"planId": stale_plan["id"], "maxRounds": 2},
        )

    assert unknown_response.status_code == 404
    assert update_response.status_code == 200
    assert stale_response.status_code == 404
    assert attack_provider.calls == []
    assert target_provider.calls == []


@pytest.mark.parametrize(
    ("provider_result", "expected_status"),
    [
        (_INVALID_PROVIDER_RESPONSE, 502),
        (ProviderResponseError("invalid generated JSON"), 502),
        (ProviderUnavailableError("provider unavailable"), 502),
        (ProviderConfigurationError("provider is not configured"), 503),
    ],
)
def test_provider_boundary_errors_have_explicit_http_status(
    provider_result: Any,
    expected_status: int,
    tmp_path: Path,
) -> None:
    attack_provider = ScriptedAttackProvider([provider_result])
    target_provider = ScriptedTargetProvider([])

    with _client(
        attack_provider=attack_provider,
        target_provider=target_provider,
        history_path=tmp_path / "history.sqlite3",
    ) as client:
        plan = _plan_by_type(client)
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 2},
        )

    assert response.status_code == expected_status
    assert len(attack_provider.calls) == 1
    assert target_provider.calls == []


def test_existing_api_surfaces_remain_available_with_separate_scan_providers() -> None:
    attack_provider = ScriptedAttackProvider([])
    target_provider = ScriptedTargetProvider(
        [LLMResponse(content="现有助手 API 正常", tool_calls=())]
    )

    with _client(
        attack_provider=attack_provider,
        target_provider=target_provider,
    ) as client:
        actors = client.get("/api/demo/actors")
        cases = client.get("/api/attack-cases")
        contract = client.get("/api/security-contract")
        plans = client.get("/api/attack-plans")
        query = client.post(
            "/api/assistant/queries",
            json={
                "actorId": actors.json()[0]["id"],
                "message": "请总结当前可见的合成资料。",
            },
        )

    assert actors.status_code == 200
    assert cases.status_code == 200
    assert contract.status_code == 200
    assert plans.status_code == 200
    assert query.status_code == 200
    assert query.json()["answer"] == "现有助手 API 正常"
    assert len(target_provider.calls) == 1
    assert attack_provider.calls == []
