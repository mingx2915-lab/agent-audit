"""Integration coverage for the explicit Provider readiness API."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
from agent_audit_api.readiness import _READINESS_NONCE, _READINESS_TOOL_NAME
from tests.retriever_support import make_tfidf_retriever


@dataclass
class ScriptedProvider:
    """Provider double with distinct response queues for each injected role."""

    responses: list[Any]
    model: str
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append(([dict(message) for message in messages], tools))
        if not self.responses:
            raise AssertionError("readiness provider received an unexpected call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _target_responses() -> list[LLMResponse]:
    return [
        LLMResponse(content="target connectivity", tool_calls=()),
        LLMResponse(
            content=None,
            tool_calls=(
                ToolCall(
                    "target-readiness-call",
                    _READINESS_TOOL_NAME,
                    {"nonce": _READINESS_NONCE},
                ),
            ),
        ),
    ]


def _attack_responses() -> list[LLMResponse]:
    return [
        LLMResponse(content="attack connectivity", tool_calls=()),
        LLMResponse(
            content=json.dumps(
                {"status": "ready", "nonce": _READINESS_NONCE},
                separators=(",", ":"),
            ),
            tool_calls=(),
        ),
    ]


def _client(
    target: ScriptedProvider,
    attack: ScriptedProvider | None = None,
    *,
    raise_server_exceptions: bool = True,
) -> TestClient:
    return TestClient(
        create_app(
            provider=target,
            attack_provider=attack or target,
            retriever=make_tfidf_retriever(),
        ),
        raise_server_exceptions=raise_server_exceptions,
    )


def test_readiness_api_runs_each_role_once_and_returns_four_plan_requirements() -> None:
    target = ScriptedProvider(_target_responses(), model="target-test-model")
    attack = ScriptedProvider(_attack_responses(), model="attack-test-model")

    with _client(target, attack) as client:
        response = client.post("/api/provider-readiness", json={})

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ready"
    assert result["targetProvider"]["role"] == "target"
    assert result["targetProvider"]["model"] == "target-test-model"
    assert result["targetProvider"]["status"] == "ready"
    assert result["attackProvider"]["role"] == "attack"
    assert result["attackProvider"]["model"] == "attack-test-model"
    assert result["attackProvider"]["status"] == "ready"

    assert len(target.calls) == 2
    assert len(attack.calls) == 2
    assert target.responses == []
    assert attack.responses == []
    assert target.calls[0][1] is None
    assert target.calls[1][1][0]["function"]["name"] == _READINESS_TOOL_NAME
    assert attack.calls[0][1] is None
    assert attack.calls[1][1] is None
    target_messages = " ".join(
        message["content"]
        for call in target.calls
        for message in call[0]
    )
    attack_messages = " ".join(
        message["content"]
        for call in attack.calls
        for message in call[0]
    )
    assert "strict JSON readiness probe" not in target_messages
    assert "Tool Calling readiness probe" not in attack_messages

    plans = result["planCompatibility"]
    assert len(plans) == 4
    assert {plan["basisType"] for plan in plans} == {
        "resource_owner_scope",
        "tool_owner_scope",
        "source_sink",
        "tool_record_limit",
    }
    by_basis = {plan["basisType"]: plan for plan in plans}
    assert by_basis["resource_owner_scope"]["requiredProbeIds"] == [
        "target.connectivity",
        "attack.connectivity",
        "attack.strict_json",
    ]
    for basis_type in ("tool_owner_scope", "source_sink", "tool_record_limit"):
        assert by_basis[basis_type]["requiredProbeIds"] == [
            "target.connectivity",
            "target.tool_calling",
            "attack.connectivity",
            "attack.strict_json",
        ]
    assert all(plan["status"] == "compatible" for plan in plans)
    assert all(plan["failedProbeIds"] == [] for plan in plans)

    for role in (result["targetProvider"], result["attackProvider"]):
        assert all(probe["durationMs"] >= 0 for probe in role["probes"])


def test_readiness_api_accepts_empty_object_body() -> None:
    target = ScriptedProvider(_target_responses(), model="target-test-model")
    attack = ScriptedProvider(_attack_responses(), model="attack-test-model")

    with _client(target, attack) as client:
        response = client.post("/api/provider-readiness", json={})

    assert response.status_code == 200
    assert len(target.calls) == 2
    assert len(attack.calls) == 2


def test_readiness_api_forbids_extra_request_fields() -> None:
    target = ScriptedProvider(_target_responses(), model="target-test-model")
    attack = ScriptedProvider(_attack_responses(), model="attack-test-model")

    with _client(target, attack) as client:
        response = client.post(
            "/api/provider-readiness",
            json={"unexpected": True},
        )

    assert response.status_code == 422
    assert target.calls == []
    assert attack.calls == []


@pytest.mark.parametrize(
    "error",
    [
        ProviderConfigurationError("missing provider configuration"),
        ProviderUnavailableError("provider unavailable"),
        ProviderResponseError("malformed provider response"),
    ],
)
def test_provider_errors_are_failed_probe_details_in_structured_200(
    error: Exception,
) -> None:
    target = ScriptedProvider(
        [error, _target_responses()[1]],
        model="target-test-model",
    )
    attack = ScriptedProvider(_attack_responses(), model="attack-test-model")

    with _client(target, attack) as client:
        response = client.post("/api/provider-readiness", json={})

    assert response.status_code == 200
    result = response.json()
    failed_probe = result["targetProvider"]["probes"][0]
    assert failed_probe["id"] == "target.connectivity"
    assert failed_probe["status"] == "failed"
    detail = failed_probe["detail"]
    assert any(term in detail for term in ("检查", "设置", "服务", "结果"))
    assert "重新" in detail
    assert str(error) not in detail
    assert result["targetProvider"]["status"] == "partial"
    assert result["attackProvider"]["status"] == "ready"
    assert result["status"] == "partial"
    assert len(target.calls) == 2
    assert len(attack.calls) == 2


def test_failed_attack_probe_is_reported_without_retry_or_cross_role_fallback() -> None:
    target = ScriptedProvider(_target_responses(), model="target-test-model")
    error = ProviderUnavailableError("attack provider unavailable")
    attack = ScriptedProvider(
        [_attack_responses()[0], error],
        model="attack-test-model",
    )

    with _client(target, attack) as client:
        response = client.post("/api/provider-readiness", json={})

    assert response.status_code == 200
    result = response.json()
    assert result["targetProvider"]["status"] == "ready"
    assert result["attackProvider"]["status"] == "partial"
    assert result["status"] == "partial"
    failed_probe = result["attackProvider"]["probes"][1]
    assert failed_probe["id"] == "attack.strict_json"
    assert failed_probe["status"] == "failed"
    detail = failed_probe["detail"]
    assert any(term in detail for term in ("检查", "设置", "服务", "结果"))
    assert "重新" in detail
    assert str(error) not in detail
    assert len(target.calls) == 2
    assert len(attack.calls) == 2


def test_all_failed_probes_report_unavailable_and_plan_failed_probe_ids() -> None:
    target = ScriptedProvider(
        [
            ProviderConfigurationError("target not configured"),
            ProviderUnavailableError("target unavailable"),
        ],
        model="target-test-model",
    )
    attack = ScriptedProvider(
        [
            ProviderResponseError("attack response malformed"),
            ProviderUnavailableError("attack unavailable"),
        ],
        model="attack-test-model",
    )

    with _client(target, attack) as client:
        response = client.post("/api/provider-readiness", json={})

    assert response.status_code == 200
    result = response.json()
    assert result["targetProvider"]["status"] == "unavailable"
    assert result["attackProvider"]["status"] == "unavailable"
    assert result["status"] == "unavailable"
    by_basis = {plan["basisType"]: plan for plan in result["planCompatibility"]}
    assert by_basis["resource_owner_scope"]["failedProbeIds"] == [
        "target.connectivity",
        "attack.connectivity",
        "attack.strict_json",
    ]
    for basis_type in ("tool_owner_scope", "source_sink", "tool_record_limit"):
        assert by_basis[basis_type]["failedProbeIds"] == [
            "target.connectivity",
            "target.tool_calling",
            "attack.connectivity",
            "attack.strict_json",
        ]


def test_unexpected_exception_is_exposed_as_500_instead_of_being_a_failed_probe() -> None:
    target = ScriptedProvider(
        [RuntimeError("unexpected programming error")],
        model="target-test-model",
    )
    attack = ScriptedProvider(_attack_responses(), model="attack-test-model")

    with _client(
        target,
        attack,
        raise_server_exceptions=False,
    ) as client:
        response = client.post("/api/provider-readiness", json={})

    assert response.status_code == 500
    assert len(target.calls) == 1
    assert len(attack.calls) == 0
