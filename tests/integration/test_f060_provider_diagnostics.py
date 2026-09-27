"""F-060 regression coverage for actionable, bounded Provider diagnostics.

The tests use explicit in-process transport/provider doubles.  They verify the
public API boundaries and observable request count, without starting Ollama,
calling a real enterprise endpoint, or invoking a real model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent_audit_api import provider_setup as provider_setup_module
from agent_audit_api.main import create_app
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderUnavailableError,
)
from tests.retriever_support import make_tfidf_retriever


@dataclass
class FakeResponse:
    payload: object = None
    raw_body: bytes | None = None
    status: int = 200
    closed: bool = False

    def read(self) -> bytes:
        if self.raw_body is not None:
            return self.raw_body
        return json.dumps(self.payload).encode("utf-8")

    def close(self) -> None:
        self.closed = True


@dataclass
class RecordingTransport:
    result: object
    calls: list[tuple[str, str, int]] = field(default_factory=list)

    def open(self, request, *, timeout: int) -> object:
        self.calls.append((request.full_url, request.get_method(), timeout))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@dataclass
class IdleProvider:
    """Provider double that should not be touched by setup diagnostics."""

    model: str = "f060-test-provider"
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append(([dict(message) for message in messages], tools))
        return LLMResponse(content="unused F-060 response")


@dataclass
class FailingAttackProvider:
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)
    model: str = "f060-provider-502"

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append(([dict(message) for message in messages], tools))
        raise ProviderUnavailableError("synthetic provider outage")


def _app(*, provider: object | None = None, attack_provider: object | None = None):
    target = provider or IdleProvider()
    attack = attack_provider or target
    return create_app(
        provider=target,
        attack_provider=attack,
        retriever=make_tfidf_retriever(),
    )


def _patch_setup_transport(monkeypatch: pytest.MonkeyPatch, transport: RecordingTransport) -> None:
    monkeypatch.setattr(
        provider_setup_module,
        "_NO_REDIRECT_OPENER",
        SimpleNamespace(open=transport.open),
    )


def _assert_user_diagnostic(
    diagnostic: str | None,
    *,
    required_terms: tuple[str, ...],
    forbidden_terms: tuple[str, ...] = (),
) -> None:
    assert diagnostic
    assert any("\u4e00" <= character <= "\u9fff" for character in diagnostic)
    for term in required_terms:
        assert term in diagnostic
    for term in forbidden_terms:
        assert term not in diagnostic


def test_f060_ollama_unavailable_is_actionable_and_does_not_retry_or_call_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = RecordingTransport(URLError("connection refused"))
    _patch_setup_transport(monkeypatch, transport)

    with TestClient(_app()) as client:
        response = client.post("/api/provider-discoveries/ollama", json={})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["models"] == []
    _assert_user_diagnostic(
        payload["diagnostic"],
        required_terms=("Ollama", "重新"),
        forbidden_terms=("URLError", "OSError", "TimeoutError"),
    )
    assert [call[0] for call in transport.calls] == [
        "http://127.0.0.1:11434/api/tags"
    ]


def test_f060_ollama_without_models_is_a_waiting_action_not_a_successful_ready_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = RecordingTransport(FakeResponse({"models": []}))
    _patch_setup_transport(monkeypatch, transport)

    with TestClient(_app()) as client:
        response = client.post("/api/provider-discoveries/ollama", json={})

    assert response.status_code == 200, response.text
    payload = response.json()
    # The endpoint remains available, while the empty model list gives the UI
    # a stable actionable diagnostic instead of pretending a model is ready.
    assert payload["status"] == "available"
    assert payload["models"] == []
    _assert_user_diagnostic(
        payload["diagnostic"],
        required_terms=("模型", "重新"),
    )
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("failure", "required_terms"),
    [
        (
            HTTPError(
                "https://runtime.intra.example/team/v1/models",
                401,
                "unauthorized",
                {},
                None,
            ),
            ("401", "重新"),
        ),
        (TimeoutError("synthetic timeout"), ("超时", "重新")),
        (FakeResponse(raw_body=b"not-json"), ("响应", "重新")),
    ],
)
def test_f060_enterprise_inspection_has_stable_chinese_diagnostics_and_one_origin(
    monkeypatch: pytest.MonkeyPatch,
    failure: object,
    required_terms: tuple[str, ...],
) -> None:
    transport = RecordingTransport(failure)
    _patch_setup_transport(monkeypatch, transport)

    with TestClient(_app()) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "openai_compatible",
                "baseUrl": "https://runtime.intra.example/team",
                "authMode": "none",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["models"] == []
    assert payload["modelsEnumerated"] is False
    _assert_user_diagnostic(
        payload["diagnostic"],
        required_terms=required_terms,
        forbidden_terms=("HTTPError", "URLError", "TimeoutError", "ValueError"),
    )
    assert len(transport.calls) == 1
    assert transport.calls[0][0] == "https://runtime.intra.example/team/v1/models"
    assert "/api/tags" not in response.text


def test_f060_provider_502_is_actionable_without_retry_or_fallback() -> None:
    target = IdleProvider(model="f060-target")
    attack = FailingAttackProvider()

    with TestClient(_app(provider=target, attack_provider=attack)) as client:
        plans_response = client.get("/api/attack-plans")
        assert plans_response.status_code == 200
        plan = next(
            plan
            for plan in plans_response.json()
            if plan["basisType"] == "source_sink"
        )
        response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 2},
        )

    assert response.status_code == 502, response.text
    detail = response.json()["detail"]
    # The public response remains the existing {detail: string} shape.  It must
    # explain the failed stage/action in Chinese; exception chaining keeps the
    # raw provider diagnostic available to local technical diagnostics without
    # echoing potentially sensitive provider text into the public response.
    _assert_user_diagnostic(
        detail,
        required_terms=("检查", "重新"),
    )
    assert "synthetic provider outage" not in detail
    assert response.headers.get("X-AgentAudit-Operation-Id")
    assert len(attack.calls) == 1
    assert target.calls == []
