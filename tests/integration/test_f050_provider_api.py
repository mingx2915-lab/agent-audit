"""F-050 API boundaries for Anthropic Messages and the fixed adapter v1.

Every transport in this module is an explicit test-only double.  It is
injected into the production seams, performs no network I/O, and must not be
read as evidence that a real Claude Gateway or enterprise bridge was tested.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.app_paths import AppPaths, resolve_app_paths
from agent_audit_api.main import create_app
from agent_audit_api.provider_setup import (
    PROVIDER_SETTINGS_FILENAME,
    ProviderSettingsStore,
    ProviderSettingsWriteError,
)
from agent_audit_api.providers.agent_audit_adapter import (
    AGENT_AUDIT_ADAPTER_COMPLETIONS_PATH,
    AGENT_AUDIT_ADAPTER_MANIFEST_PATH,
    AGENT_AUDIT_ADAPTER_MODELS_PATH,
    AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION,
    AgentAuditAdapterProvider,
)
from agent_audit_api.providers.anthropic import (
    ANTHROPIC_MESSAGES_PATH,
    ANTHROPIC_VERSION,
    AnthropicCompatibleProvider,
)
from agent_audit_api.providers.base import LLMResponse
from tests.retriever_support import make_tfidf_retriever


ANTHROPIC_ORIGIN = "https://claude-gateway.intra.example/team"
ANTHROPIC_BASE_URL = f"{ANTHROPIC_ORIGIN}/v1"
ADAPTER_ORIGIN = "https://bridge.intra.example/team"
ADAPTER_BASE_URL = f"{ADAPTER_ORIGIN}/v1"
MODEL = "enterprise-model"
SECRET = "f050-api-secret-test-only"


@dataclass
class FakeInspectionResponse:
    """Test-only urllib response; never represents a real enterprise server."""

    payload: object = None
    raw_body: bytes | None = None
    status: int = 200
    closed: bool = False

    def read(self) -> bytes:
        if isinstance(self.payload, BaseException):
            raise self.payload
        if self.raw_body is not None:
            return self.raw_body
        return json.dumps(self.payload).encode("utf-8")

    def close(self) -> None:
        self.closed = True


@dataclass
class RecordingOpener:
    """Explicit local inspection double with a complete request ledger."""

    responses: list[object]
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
        if not self.responses:
            raise AssertionError("unexpected test-only inspection request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


@dataclass
class FakeJSONResponse:
    """Test-only async completion response; no socket or gateway is involved."""

    payload: object
    status_code: int = 200

    def json(self) -> object:
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


@dataclass
class RecordingProvider:
    """Injected old runtime used to prove candidate/save isolation."""

    model: str = "old-runtime-model"
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append(([dict(message) for message in messages], tools))
        return LLMResponse(content="old runtime response")


def _app(
    tmp_path: Path,
    *,
    provider: RecordingProvider | None = None,
    workspace: object | None = None,
) -> tuple[Any, AppPaths, RecordingProvider]:
    injected = provider or RecordingProvider()
    paths = resolve_app_paths(tmp_path / "app-home")
    application = create_app(
        provider=injected,
        attack_provider=injected,
        retriever=make_tfidf_retriever(),
        workspace=workspace,
        app_paths=paths,
        history_path=tmp_path / "history" / "audit.sqlite3",
    )
    return application, paths, injected


def _patch_inspection_transport(
    monkeypatch: pytest.MonkeyPatch,
    opener: RecordingOpener,
) -> None:
    import agent_audit_api.provider_setup as provider_setup_module

    monkeypatch.setattr(
        provider_setup_module,
        "_NO_REDIRECT_OPENER",
        type("TestOnlyNoRedirectOpener", (), {"open": opener.open})(),
    )


def _header(headers: dict[str, str], name: str) -> str | None:
    wanted = name.lower()
    return next((value for key, value in headers.items() if key.lower() == wanted), None)


def _anthropic_models() -> dict[str, object]:
    return {
        "data": [
            {
                "type": "model",
                "id": MODEL,
                "created_at": "2026-08-30T00:00:00Z",
                "display_name": "合成企业模型",
            }
        ]
    }


def _anthropic_response(
    *,
    text: str | None = "ok",
    blocks: list[dict[str, object]] | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "msg_f050_api",
        "type": "message",
        "role": "assistant",
        "content": blocks if blocks is not None else [{"type": "text", "text": text}],
        "model": MODEL,
        "stop_reason": "end_turn",
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


def _adapter_manifest(
    *,
    version: str = AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION,
    capabilities: dict[str, object] | None = None,
    protocol: str = "agent_audit_adapter",
) -> dict[str, object]:
    return {
        "protocol": protocol,
        "protocolVersion": version,
        "capabilities": capabilities
        if capabilities is not None
        else {
            "text": True,
            "toolCalling": True,
            "structuredOutput": True,
            "usage": True,
        },
    }


def _adapter_models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL,
                "object": "model",
                "created": 1_725_000_000,
                "owned_by": "enterprise-platform",
            }
        ],
    }


def _adapter_response(
    *,
    content: str | None = "ok",
    tool_calls: list[dict[str, object]] | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "content": content,
        "toolCalls": [] if tool_calls is None else tool_calls,
        "usage": usage,
    }


def _patch_anthropic_post(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[object],
) -> list[tuple[str, dict[str, object], dict[str, str]]]:
    calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

    async def post(
        provider: AnthropicCompatibleProvider,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> object:
        calls.append((url, dict(payload), dict(headers)))
        if not responses:
            raise AssertionError("unexpected test-only Anthropic completion request")
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(AnthropicCompatibleProvider, "_post", post)
    return calls


def _patch_adapter_post(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[object],
) -> list[tuple[str, dict[str, object], dict[str, str]]]:
    calls: list[tuple[str, dict[str, object], dict[str, str]]] = []

    async def post(
        provider: AgentAuditAdapterProvider,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> object:
        calls.append((url, dict(payload), dict(headers)))
        if not responses:
            raise AssertionError("unexpected test-only adapter completion request")
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    monkeypatch.setattr(AgentAuditAdapterProvider, "_post", post)
    return calls


def _ready_anthropic_responses() -> list[object]:
    return [
        FakeJSONResponse(
            _anthropic_response(
                text="target connectivity",
                usage={"input_tokens": 3, "output_tokens": 2},
            )
        ),
        FakeJSONResponse(
            _anthropic_response(
                text=None,
                blocks=[
                    {
                        "type": "tool_use",
                        "id": "readiness-call",
                        "name": "agent_audit_readiness_probe",
                        "input": {"nonce": "agent-audit-readiness"},
                    }
                ],
                usage={"input_tokens": 4, "output_tokens": 2},
            )
        ),
        FakeJSONResponse(_anthropic_response(text="attack connectivity")),
        FakeJSONResponse(
            _anthropic_response(
                text='{"status":"ready","nonce":"agent-audit-readiness"}',
                usage={"input_tokens": 5, "output_tokens": 3},
            )
        ),
    ]


def _ready_adapter_responses() -> list[object]:
    return [
        FakeJSONResponse(
            _adapter_response(
                content="target connectivity",
                usage={"inputTokens": 3, "outputTokens": 2, "totalTokens": 5},
            )
        ),
        FakeJSONResponse(
            _adapter_response(
                content=None,
                tool_calls=[
                    {
                        "id": "readiness-call",
                        "name": "agent_audit_readiness_probe",
                        "arguments": {"nonce": "agent-audit-readiness"},
                    }
                ],
                usage={"inputTokens": 4, "outputTokens": 2, "totalTokens": 6},
            )
        ),
        FakeJSONResponse(_adapter_response(content="attack connectivity")),
        FakeJSONResponse(
            _adapter_response(
                content='{"status":"ready","nonce":"agent-audit-readiness"}',
                usage={"inputTokens": 5, "outputTokens": 3, "totalTokens": 8},
            )
        ),
    ]


def test_anthropic_inspection_api_uses_one_explicit_origin_and_x_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    body = FakeInspectionResponse(_anthropic_models())
    opener = RecordingOpener([body])
    _patch_inspection_transport(monkeypatch, opener)
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "anthropic_compatible",
                "baseUrl": f"{ANTHROPIC_ORIGIN}/",
                "authMode": "x_api_key",
                "credential": SECRET,
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["protocol"] == "anthropic_compatible"
    assert payload["baseUrl"] == ANTHROPIC_BASE_URL
    assert payload["models"] == [
        {
            "id": MODEL,
            "object": "model",
            "created": None,
            "ownedBy": None,
        }
    ]
    assert payload["modelsEnumerated"] is True
    assert len(opener.calls) == 1
    url, method, headers, timeout = opener.calls[0]
    assert (url, method, timeout) == (
        f"{ANTHROPIC_BASE_URL}/models",
        "GET",
        5,
    )
    assert _header(headers, "x-api-key") == SECRET
    assert _header(headers, "anthropic-version") == ANTHROPIC_VERSION
    assert _header(headers, "content-type") == "application/json"
    assert body.closed is True
    assert SECRET not in response.text
    assert injected.calls == []
    assert not paths.config_dir.exists()


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError(
            f"{ANTHROPIC_BASE_URL}/models",
            401,
            "unauthorized",
            {},
            None,
        ),
        HTTPError(
            f"{ANTHROPIC_BASE_URL}/models",
            503,
            "upstream",
            {},
            None,
        ),
        HTTPError(
            f"{ANTHROPIC_BASE_URL}/models",
            307,
            "redirect",
            {"Location": "https://outside.example/v1/models"},
            None,
        ),
        URLError("synthetic unavailable"),
        TimeoutError("synthetic timeout"),
        FakeInspectionResponse(raw_body=b"not-json"),
        FakeInspectionResponse({"data": [{"id": ""}]}),
    ],
)
def test_anthropic_inspection_failure_is_readable_one_attempt_without_scan_or_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: object,
) -> None:
    opener = RecordingOpener([failure])
    _patch_inspection_transport(monkeypatch, opener)
    application, _, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "anthropic_compatible",
                "baseUrl": ANTHROPIC_BASE_URL,
                "authMode": "bearer",
                "credential": SECRET,
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["protocol"] is None
    assert payload["models"] == []
    assert payload["modelsEnumerated"] is False
    assert payload["diagnostic"]
    assert len(opener.calls) == 1
    assert "/api/tags" not in opener.calls[0][0]
    assert "outside.example" not in response.text
    assert SECRET not in response.text
    assert injected.calls == []


def test_adapter_inspection_api_returns_fixed_v1_manifest_and_models_without_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = FakeInspectionResponse(_adapter_manifest())
    models = FakeInspectionResponse(_adapter_models())
    opener = RecordingOpener([manifest, models])
    _patch_inspection_transport(monkeypatch, opener)
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "agent_audit_adapter",
                "baseUrl": ADAPTER_ORIGIN,
                "authMode": "x_api_key",
                "credential": SECRET,
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["protocol"] == "agent_audit_adapter"
    assert payload["protocolVersion"] == AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION
    assert payload["capabilities"] == {
        "text": True,
        "toolCalling": True,
        "structuredOutput": True,
        "usage": True,
    }
    assert payload["manifest"] == _adapter_manifest()
    assert payload["models"][0]["id"] == MODEL
    assert payload["modelsEnumerated"] is True
    assert [call[0] for call in opener.calls] == [
        f"{ADAPTER_BASE_URL}{AGENT_AUDIT_ADAPTER_MANIFEST_PATH}",
        f"{ADAPTER_BASE_URL}{AGENT_AUDIT_ADAPTER_MODELS_PATH}",
    ]
    assert all(call[1] == "GET" and call[3] == 5 for call in opener.calls)
    assert all(_header(call[2], "x-api-key") == SECRET for call in opener.calls)
    assert all(_header(call[2], "content-type") == "application/json" for call in opener.calls)
    assert manifest.closed is True
    assert models.closed is True
    assert SECRET not in response.text
    assert injected.calls == []
    assert not paths.config_dir.exists()


@pytest.mark.parametrize(
    ("manifest", "expected_calls"),
    [
        (_adapter_manifest(version="agent_audit_adapter.v0"), 1),
        (_adapter_manifest(protocol="openai_compatible"), 1),
    ],
)
def test_adapter_inspection_rejects_unsupported_manifest_without_protocol_guessing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    manifest: dict[str, object],
    expected_calls: int,
) -> None:
    opener = RecordingOpener([FakeInspectionResponse(manifest)])
    _patch_inspection_transport(monkeypatch, opener)
    application, _, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "agent_audit_adapter",
                "baseUrl": ADAPTER_BASE_URL,
                "authMode": "none",
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "unavailable"
    assert response.json()["protocol"] is None
    assert response.json()["models"] == []
    assert len(opener.calls) == expected_calls
    assert injected.calls == []


def test_anthropic_candidate_readiness_runs_text_tool_json_usage_once_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _patch_anthropic_post(monkeypatch, _ready_anthropic_responses())
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        before = client.get("/api/provider-setup")
        response = client.post(
            "/api/provider-candidates/readiness",
            json={
                "settings": {
                    "kind": "anthropic_compatible",
                    "baseUrl": ANTHROPIC_BASE_URL,
                    "model": MODEL,
                    "authMode": "x_api_key",
                },
                "credential": SECRET,
            },
        )
        after = client.get("/api/provider-setup")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready"
    assert result["targetProvider"]["provider"] == "anthropic_compatible"
    assert result["attackProvider"]["provider"] == "anthropic_compatible"
    assert [probe["id"] for probe in result["targetProvider"]["probes"]] == [
        "target.connectivity",
        "target.tool_calling",
    ]
    assert [probe["id"] for probe in result["attackProvider"]["probes"]] == [
        "attack.connectivity",
        "attack.strict_json",
    ]
    assert len(calls) == 4
    assert all(call[0] == f"{ANTHROPIC_BASE_URL}{ANTHROPIC_MESSAGES_PATH}" for call in calls)
    assert all(_header(call[2], "x-api-key") == SECRET for call in calls)
    assert all(call[1]["max_tokens"] == 4096 for call in calls)
    assert "/api/tags" not in json.dumps(calls)
    assert SECRET not in response.text
    assert before.json() == after.json()
    assert injected.calls == []
    assert not paths.config_dir.exists()


@pytest.mark.parametrize(
    "failure",
    [
        FakeJSONResponse({"error": "unauthorized"}, status_code=401),
        FakeJSONResponse({"error": "upstream"}, status_code=502),
        TimeoutError("synthetic timeout"),
        FakeJSONResponse({"type": "message", "role": "assistant", "content": [{"type": "image"}]}),
        FakeJSONResponse(ValueError("not JSON")),
    ],
)
def test_anthropic_candidate_failure_is_one_call_per_probe_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: object,
) -> None:
    responses = [failure, *_ready_anthropic_responses()[1:]]
    calls = _patch_anthropic_post(monkeypatch, responses)
    application, _, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-candidates/readiness",
            json={
                "settings": {
                    "kind": "anthropic_compatible",
                    "baseUrl": ANTHROPIC_BASE_URL,
                    "model": MODEL,
                    "authMode": "bearer",
                },
                "credential": SECRET,
            },
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "partial"
    assert result["targetProvider"]["probes"][0]["status"] == "failed"
    assert len(calls) == 4
    assert all(call[0] == f"{ANTHROPIC_BASE_URL}{ANTHROPIC_MESSAGES_PATH}" for call in calls)
    assert SECRET not in response.text
    assert injected.calls == []


def test_adapter_candidate_readiness_requires_manifest_then_runs_canonical_probes_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    opener = RecordingOpener(
        [FakeInspectionResponse(_adapter_manifest()), FakeInspectionResponse(_adapter_models())]
    )
    _patch_inspection_transport(monkeypatch, opener)
    calls = _patch_adapter_post(monkeypatch, _ready_adapter_responses())
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        before = client.get("/api/provider-setup")
        response = client.post(
            "/api/provider-candidates/readiness",
            json={
                "settings": {
                    "kind": "agent_audit_adapter",
                    "baseUrl": ADAPTER_BASE_URL,
                    "model": MODEL,
                    "authMode": "none",
                }
            },
        )
        after = client.get("/api/provider-setup")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready"
    assert result["targetProvider"]["provider"] == "agent_audit_adapter"
    assert result["attackProvider"]["provider"] == "agent_audit_adapter"
    assert [call[0] for call in opener.calls] == [
        f"{ADAPTER_BASE_URL}{AGENT_AUDIT_ADAPTER_MANIFEST_PATH}",
        f"{ADAPTER_BASE_URL}{AGENT_AUDIT_ADAPTER_MODELS_PATH}",
    ]
    assert len(calls) == 4
    assert all(call[0] == f"{ADAPTER_BASE_URL}{AGENT_AUDIT_ADAPTER_COMPLETIONS_PATH}" for call in calls)
    assert all(call[1]["protocolVersion"] == AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION for call in calls)
    assert all(call[1]["maxTokens"] == 4096 for call in calls)
    assert before.json() == after.json()
    assert SECRET not in response.text
    assert injected.calls == []
    assert not paths.config_dir.exists()


def test_adapter_candidate_readiness_rejects_false_capability_before_completion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = _adapter_manifest(
        capabilities={
            "text": True,
            "toolCalling": True,
            "structuredOutput": False,
            "usage": True,
        }
    )
    opener = RecordingOpener(
        [FakeInspectionResponse(manifest), FakeInspectionResponse(_adapter_models())]
    )
    _patch_inspection_transport(monkeypatch, opener)
    calls = _patch_adapter_post(monkeypatch, _ready_adapter_responses())
    application, _, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-candidates/readiness",
            json={
                "settings": {
                    "kind": "agent_audit_adapter",
                    "baseUrl": ADAPTER_BASE_URL,
                    "model": MODEL,
                    "authMode": "none",
                }
            },
        )

    assert response.status_code == 422, response.text
    assert "capabilities" in response.text
    assert len(opener.calls) == 2
    assert calls == []
    assert SECRET not in response.text
    assert injected.calls == []


def test_missing_x_api_key_save_leaves_old_runtime_and_settings_unchanged(
    tmp_path: Path,
) -> None:
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        before = client.get("/api/provider-setup")
        response = client.put(
            "/api/provider-setup",
            json={
                "settings": {
                    "kind": "anthropic_compatible",
                    "baseUrl": ANTHROPIC_BASE_URL,
                    "model": MODEL,
                    "authMode": "x_api_key",
                }
            },
        )
        after = client.get("/api/provider-setup")

    assert response.status_code == 422, response.text
    assert before.json() == after.json()
    assert "credential" in response.text.lower()
    assert not paths.config_dir.exists()
    assert injected.calls == []


def test_x_api_key_save_failure_does_not_replace_old_runtime_or_echo_secret(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application, paths, injected = _app(tmp_path)
    failure = ProviderSettingsWriteError("synthetic settings storage failure")
    monkeypatch.setattr(
        ProviderSettingsStore,
        "save",
        lambda self, settings: (_ for _ in ()).throw(failure),
    )

    with TestClient(application) as client:
        before = client.get("/api/provider-setup")
        response = client.put(
            "/api/provider-setup",
            json={
                "settings": {
                    "kind": "anthropic_compatible",
                    "baseUrl": ANTHROPIC_BASE_URL,
                    "model": MODEL,
                    "authMode": "x_api_key",
                },
                "credential": SECRET,
            },
        )
        after = client.get("/api/provider-setup")
        runtime = client.get("/api/runtime")

    assert response.status_code == 500, response.text
    assert "synthetic settings storage failure" in response.text
    assert SECRET not in response.text
    assert before.json() == after.json()
    assert runtime.json()["model"] == injected.model
    assert not paths.config_dir.exists()
    assert injected.calls == []


def test_x_api_key_save_persists_only_public_settings_and_never_secret_artifacts(
    tmp_path: Path,
) -> None:
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        saved = client.put(
            "/api/provider-setup",
            json={
                "settings": {
                    "kind": "anthropic_compatible",
                    "baseUrl": ANTHROPIC_BASE_URL,
                    "model": MODEL,
                    "authMode": "x_api_key",
                },
                "credential": SECRET,
            },
        )
        setup = client.get("/api/provider-setup")
        runtime = client.get("/api/runtime")

    assert saved.status_code == 200, saved.text
    assert setup.status_code == 200
    assert runtime.status_code == 200
    assert saved.json()["settings"] == {
        "kind": "anthropic_compatible",
        "baseUrl": ANTHROPIC_BASE_URL,
        "model": MODEL,
        "authMode": "x_api_key",
    }
    assert saved.json()["credentialConfigured"] is True
    assert runtime.json()["provider"] == "anthropic_compatible"
    assert runtime.json()["model"] == MODEL
    for response in (saved, setup, runtime):
        assert SECRET not in response.text

    settings_path = paths.config_dir / PROVIDER_SETTINGS_FILENAME
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "kind": "anthropic_compatible",
        "baseUrl": ANTHROPIC_BASE_URL,
        "model": MODEL,
        "authMode": "x_api_key",
    }
    # Settings, history, trace/finding exports, and logs all live below this
    # isolated test root when they are created.  A byte scan keeps the secret
    # boundary explicit without inventing a production storage abstraction.
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SECRET.encode("utf-8") not in path.read_bytes(), path
    assert injected.calls == []
