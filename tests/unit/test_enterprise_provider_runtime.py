"""F-031 unit coverage for explicit enterprise Runtime connections.

These tests use the public setup/adapter seams and an in-process transport
double.  They never call an enterprise service, Ollama, or a public model.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from agent_audit_api.provider_setup import (
    PROVIDER_SETTINGS_FILENAME,
    ProviderConnectionSettings,
    ProviderInspectionError,
    ProviderSettingsStore,
    inspect_openai_compatible_endpoint,
    inspect_provider_endpoint,
    parse_openai_models_payload,
)
from agent_audit_api.providers.base import (
    ProviderConfigurationError,
    ToolCall,
)
from agent_audit_api.providers.openai_compatible import OpenAICompatibleProvider
from agent_audit_api.providers.runtime import create_runtime_provider
from agent_audit_api.readiness import (
    _READINESS_NONCE,
    _READINESS_TOOL_NAME,
    ProviderReadinessRunner,
)


TEST_ORIGIN = "https://runtime.intra.example/team"
TEST_BASE_URL = f"{TEST_ORIGIN}/v1"
TEST_SECRET = "enterprise-secret-for-tests"


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
    response: object
    calls: list[tuple[str, str, dict[str, str], int]] = field(default_factory=list)

    def open(self, request, *, timeout: int) -> object:
        self.calls.append(
            (
                request.full_url,
                request.get_method(),
                dict(request.header_items()),
                timeout,
            )
        )
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def _valid_models_payload() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": "  enterprise-model  ",
                "object": "model",
                "created": 1_725_000_000,
                "owned_by": "  platform-team  ",
                "provider_extension": {"ignored": True},
            },
            {"id": "small-model", "object": "model"},
        ],
    }


def test_parse_openai_models_payload_strictly_normalizes_public_fields() -> None:
    models = parse_openai_models_payload(_valid_models_payload())

    assert [model.model_dump(mode="json", by_alias=True) for model in models] == [
        {
            "id": "enterprise-model",
            "object": "model",
            "created": 1_725_000_000,
            "ownedBy": "platform-team",
        },
        {
            "id": "small-model",
            "object": "model",
            "created": None,
            "ownedBy": None,
        },
    ]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"object": "list"},
        {"object": "not-a-list", "data": []},
        {"object": "list", "data": {}},
        {"object": "list", "data": [None]},
        {"object": "list", "data": [{"id": ""}]},
        {"object": "list", "data": [{"id": 123}]},
        {"object": "list", "data": [{"id": "x", "object": "deployment"}]},
        {"object": "list", "data": [{"id": "x", "created": -1}]},
        {"object": "list", "data": [{"id": "x", "created": True}]},
        {"object": "list", "data": [{"id": "x", "owned_by": {}}]},
    ],
)
def test_parse_openai_models_payload_rejects_untrusted_shapes(payload: object) -> None:
    with pytest.raises(ProviderInspectionError):
        parse_openai_models_payload(payload)


def test_inspection_reads_only_one_explicit_v1_models_origin_without_auth() -> None:
    response = FakeResponse(_valid_models_payload())
    transport = RecordingTransport(response)

    result = inspect_openai_compatible_endpoint(
        base_url=f"{TEST_ORIGIN}/",
        auth_mode="none",
        opener=transport.open,
    )

    assert result.status == "available"
    assert result.protocol == "openai_compatible"
    assert result.base_url == TEST_BASE_URL
    assert result.models_enumerated is True
    assert [model.id for model in result.models] == [
        "enterprise-model",
        "small-model",
    ]
    assert result.diagnostic is None
    assert response.closed is True
    assert transport.calls == [
        (
            f"{TEST_BASE_URL}/models",
            "GET",
            {"Accept": "application/json"},
            5,
        )
    ]


def test_inspection_sends_bearer_only_to_explicit_models_request_and_never_returns_it() -> None:
    response = FakeResponse(_valid_models_payload())
    transport = RecordingTransport(response)

    result = inspect_openai_compatible_endpoint(
        base_url=TEST_BASE_URL,
        auth_mode="bearer",
        credential=TEST_SECRET,
        opener=transport.open,
    )

    assert result.status == "available"
    assert transport.calls[0][2] == {
        "Accept": "application/json",
        "Authorization": f"Bearer {TEST_SECRET}",
    }
    serialized = json.dumps(result.model_dump(mode="json", by_alias=True))
    assert TEST_SECRET not in serialized


def test_bearer_inspection_without_credential_is_unavailable_without_transport_call() -> None:
    transport = RecordingTransport(FakeResponse(_valid_models_payload()))

    result = inspect_openai_compatible_endpoint(
        base_url=TEST_BASE_URL,
        auth_mode="bearer",
        opener=transport.open,
    )

    assert result.status == "unavailable"
    assert result.models == []
    assert result.models_enumerated is False
    assert result.diagnostic
    assert any(term in result.diagnostic for term in ("设置", "认证", "检查"))
    assert "重新" in result.diagnostic
    assert "Bearer credential is not configured" not in result.diagnostic
    assert transport.calls == []
    assert TEST_SECRET not in json.dumps(result.model_dump(mode="json"))


def test_inspection_rejects_redirect_without_following_location_or_fallback() -> None:
    redirect = HTTPError(
        f"{TEST_BASE_URL}/models",
        307,
        "redirect",
        {"Location": "https://outside.example/v1/models"},
        None,
    )
    transport = RecordingTransport(redirect)

    result = inspect_openai_compatible_endpoint(
        base_url=TEST_BASE_URL,
        opener=transport.open,
    )

    assert result.status == "unavailable"
    assert result.models == []
    assert result.models_enumerated is False
    assert "307" in (result.diagnostic or "")
    assert "outside.example" not in (result.diagnostic or "")
    assert [call[0] for call in transport.calls] == [f"{TEST_BASE_URL}/models"]


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(raw_body=b"not-json"),
        FakeResponse({"object": "list", "data": [{"id": ""}]}),
        FakeResponse({"object": "list", "data": {}}),
        FakeResponse(status=502, payload={"error": "upstream"}),
    ],
)
def test_inspection_reports_invalid_or_http_responses_without_second_path(response) -> None:
    transport = RecordingTransport(response)

    result = inspect_openai_compatible_endpoint(
        base_url=TEST_BASE_URL,
        opener=transport.open,
    )

    assert result.status == "unavailable"
    assert result.models == []
    assert result.models_enumerated is False
    assert result.diagnostic
    assert len(transport.calls) == 1
    assert response.closed is True


def test_inspection_does_not_fallback_to_loopback_after_transport_failure() -> None:
    transport = RecordingTransport(URLError("enterprise unavailable"))

    result = inspect_openai_compatible_endpoint(
        base_url=TEST_BASE_URL,
        opener=transport.open,
    )

    assert result.status == "unavailable"
    assert len(transport.calls) == 1
    assert transport.calls[0][0] == f"{TEST_BASE_URL}/models"
    assert "/api/tags" not in transport.calls[0][0]


def test_inspect_provider_endpoint_dispatches_openai_compatible_kind() -> None:
    transport = RecordingTransport(FakeResponse(_valid_models_payload()))
    settings = ProviderConnectionSettings(
        kind="openai_compatible",
        base_url=TEST_BASE_URL,
        model="enterprise-model",
        auth_mode="none",
    )

    result = inspect_provider_endpoint(settings, opener=transport.open)

    assert result.protocol == "openai_compatible"
    assert result.models_enumerated is True
    assert [call[0] for call in transport.calls] == [f"{TEST_BASE_URL}/models"]


@dataclass
class CompletionQueue:
    responses: list[object]
    calls: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **request: object) -> object:
        self.calls.append(request)
        if not self.responses:
            raise AssertionError("unexpected OpenAI-compatible completion call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _raw_text_response(content: str) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=[]),
            )
        ]
    )


def _raw_tool_response() -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="enterprise-readiness-call",
                            function=SimpleNamespace(
                                name=_READINESS_TOOL_NAME,
                                arguments=json.dumps(
                                    {"nonce": _READINESS_NONCE},
                                    separators=(",", ":"),
                                ),
                            ),
                        )
                    ],
                ),
            )
        ]
    )


def test_openai_compatible_adapter_forwards_normal_completion_and_normalizes_result() -> None:
    completions = CompletionQueue([_raw_text_response("企业 Runtime 回答")])
    provider = OpenAICompatibleProvider(
        client=completions,
        base_url=TEST_BASE_URL,
        model="enterprise-model",
    )

    response = asyncio.run(
        provider.complete([{"role": "user", "content": "普通问题"}])
    )

    assert response.content == "企业 Runtime 回答"
    assert response.tool_calls == ()
    assert completions.calls == [
        {
            "model": "enterprise-model",
            "messages": [{"role": "user", "content": "普通问题"}],
        }
    ]


def test_openai_compatible_adapter_normalizes_native_tool_call() -> None:
    completions = CompletionQueue([_raw_tool_response()])
    provider = OpenAICompatibleProvider(
        client=completions,
        base_url=TEST_BASE_URL,
        model="enterprise-model",
    )
    tools = [
        {
            "type": "function",
            "function": {
                "name": "mock_customer_lookup",
                "parameters": {"type": "object"},
            },
        }
    ]

    response = asyncio.run(
        provider.complete(
            [{"role": "user", "content": "查询客户"}],
            tools=tools,
        )
    )

    assert response.content is None
    assert response.tool_calls == (
        ToolCall(
            id="enterprise-readiness-call",
            name=_READINESS_TOOL_NAME,
            arguments={"nonce": _READINESS_NONCE},
        ),
    )
    assert completions.calls[0]["tools"] == tools


def test_openai_compatible_adapter_passes_target_tool_and_attack_strict_json_readiness() -> None:
    target_completions = CompletionQueue(
        [_raw_text_response("target connectivity"), _raw_tool_response()]
    )
    attack_completions = CompletionQueue(
        [
            _raw_text_response("attack connectivity"),
            _raw_text_response(
                json.dumps(
                    {"status": "ready", "nonce": _READINESS_NONCE},
                    separators=(",", ":"),
                )
            ),
        ]
    )
    target = OpenAICompatibleProvider(
        client=target_completions,
        base_url=TEST_BASE_URL,
        model="target-enterprise-model",
    )
    attack = OpenAICompatibleProvider(
        client=attack_completions,
        base_url=TEST_BASE_URL,
        model="attack-enterprise-model",
    )

    result = asyncio.run(ProviderReadinessRunner(target, attack, []).run())

    assert result.status == "ready"
    assert result.target_provider.provider == "openai_compatible"
    assert result.target_provider.model == "target-enterprise-model"
    assert result.attack_provider.provider == "openai_compatible"
    assert result.attack_provider.model == "attack-enterprise-model"
    assert [probe.id for probe in result.target_provider.probes] == [
        "target.connectivity",
        "target.tool_calling",
    ]
    assert [probe.id for probe in result.attack_provider.probes] == [
        "attack.connectivity",
        "attack.strict_json",
    ]
    assert len(target_completions.calls) == 2
    assert target_completions.calls[1]["tools"]
    assert len(attack_completions.calls) == 2
    assert "strict JSON readiness probe" in str(
        attack_completions.calls[1]["messages"]
    )


def test_openai_compatible_bearer_requires_credential_and_never_serializes_it() -> None:
    provider = OpenAICompatibleProvider(
        client=CompletionQueue([]),
        base_url=TEST_BASE_URL,
        model="enterprise-model",
        auth_mode="bearer",
    )

    assert provider.credential_configured is False
    with pytest.raises(ProviderConfigurationError, match="Bearer credential"):
        asyncio.run(provider.complete([{"role": "user", "content": "test"}]))

    authenticated = OpenAICompatibleProvider(
        client=CompletionQueue([_raw_text_response("ok")]),
        base_url=TEST_BASE_URL,
        model="enterprise-model",
        auth_mode="bearer",
        credential=TEST_SECRET,
    )
    assert authenticated.credential_configured is True
    assert TEST_SECRET not in json.dumps(
        {
            key: value
            for key, value in authenticated.__dict__.items()
            if key != "_credential"
        },
        default=str,
    )


def test_runtime_factory_uses_explicit_settings_and_transient_credential(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_AUDIT_PROVIDER_API_KEY", raising=False)
    settings = ProviderConnectionSettings(
        kind="openai_compatible",
        base_url=TEST_BASE_URL,
        model="enterprise-model",
        auth_mode="bearer",
    )

    provider = create_runtime_provider(settings=settings, credential=TEST_SECRET)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == TEST_BASE_URL
    assert provider.model == "enterprise-model"
    assert provider.auth_mode == "bearer"
    assert provider.credential_configured is True


def test_openai_compatible_client_disables_sdk_retries(monkeypatch) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def create_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("openai.AsyncOpenAI", create_client)
    provider = OpenAICompatibleProvider(
        base_url=TEST_BASE_URL,
        model="enterprise-model",
        auth_mode="bearer",
        credential=TEST_SECRET,
    )

    assert provider._create_client() is sentinel
    assert captured == {
        "api_key": TEST_SECRET,
        "base_url": TEST_BASE_URL,
        "max_retries": 0,
    }


def test_legacy_ollama_settings_file_loads_as_none_auth_without_secret_loss(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    legacy_payload = {
        "kind": "ollama",
        "baseUrl": "http://127.0.0.1:11434/v1",
        "model": "qwen3:8b",
    }
    path = config_dir / PROVIDER_SETTINGS_FILENAME
    path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    store = ProviderSettingsStore(config_dir)
    settings = store.load()
    assert settings is not None
    assert settings.kind == "ollama"
    assert settings.base_url == legacy_payload["baseUrl"]
    assert settings.model == legacy_payload["model"]
    assert settings.auth_mode == "none"

    store.save(settings)

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["kind"] == legacy_payload["kind"]
    assert persisted["baseUrl"] == legacy_payload["baseUrl"]
    assert persisted["model"] == legacy_payload["model"]
    assert persisted.get("authMode", "none") == "none"
    assert "apiKey" not in path.read_text(encoding="utf-8")
