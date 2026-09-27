"""F-031 API integration tests for explicit enterprise Runtime connections."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.main import create_app
from agent_audit_api.provider_setup import (
    OLLAMA_DISCOVERY_URL,
    PROVIDER_CREDENTIAL_ENV,
    PROVIDER_SETTINGS_FILENAME,
    ProviderConnectionSettings,
    ProviderSettingsStore,
    ProviderSettingsWriteError,
)
from agent_audit_api.providers.base import LLMResponse, ProviderUnavailableError
from agent_audit_api.providers.openai_compatible import OpenAICompatibleProvider
from agent_audit_api.workspace import WorkspaceService
from tests.retriever_support import make_tfidf_retriever


DEMO_SEED = Path(__file__).resolve().parents[2] / "data" / "demo"
TEST_ORIGIN = "https://runtime.intra.example/team"
TEST_BASE_URL = f"{TEST_ORIGIN}/v1"
OLD_ORIGIN = "https://legacy.runtime.intra.example/team"
OLD_BASE_URL = f"{OLD_ORIGIN}/v1"
NEW_ORIGIN = "https://new.runtime.intra.example/team"
NEW_BASE_URL = f"{NEW_ORIGIN}/v1"
TEST_SECRET = "f031-api-key-never-persist"
OLD_ENV_SECRET = "f031-old-sidecar-key-must-not-cross-origins"
NEW_SECRET = "f031-new-origin-key"


@dataclass
class FakeHTTPResponse:
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


@dataclass
class RecordingProvider:
    model: str = "injected-provider"
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append(([dict(message) for message in messages], tools))
        return LLMResponse(content="injected response")


def _valid_models_payload() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": "enterprise-model",
                "object": "model",
                "created": 1_725_000_000,
                "owned_by": "platform-team",
            }
        ],
    }


def _raw_text_response(content: str) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=[]),
            )
        ]
    )


def _raw_variant_response(message: str = "固定企业 Runtime 变体") -> object:
    return _raw_text_response(
        json.dumps(
            {
                "message": message,
                "mutationReason": "固定测试变体",
            },
            ensure_ascii=False,
        )
    )


def _raw_tool_response() -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="f031-readiness-call",
                            function=SimpleNamespace(
                                name="agent_audit_readiness_probe",
                                arguments='{"nonce":"agent-audit-readiness"}',
                            ),
                        )
                    ],
                )
            )
        ]
    )


def _raw_strict_json_response() -> object:
    return _raw_text_response(
        '{"status":"ready","nonce":"agent-audit-readiness"}'
    )


def _app(
    tmp_path: Path,
    *,
    provider: RecordingProvider | None = None,
    workspace: object | None = None,
) -> tuple[Any, Any, RecordingProvider]:
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
    transport: RecordingTransport,
) -> None:
    import agent_audit_api.provider_setup as provider_setup_module

    monkeypatch.setattr(
        provider_setup_module,
        "_NO_REDIRECT_OPENER",
        SimpleNamespace(open=transport.open),
    )


def _patch_completion_client(
    monkeypatch: pytest.MonkeyPatch,
    completions: CompletionQueue,
) -> None:
    monkeypatch.setattr(
        OpenAICompatibleProvider,
        "_create_client",
        lambda self: completions,
    )


def test_provider_inspection_accepts_model_less_request_and_reads_one_origin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response_body = FakeHTTPResponse(_valid_models_payload())
    transport = RecordingTransport(response_body)
    _patch_inspection_transport(monkeypatch, transport)
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "openai_compatible",
                "baseUrl": f"{TEST_ORIGIN}/",
                "authMode": "none",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload == {
        "status": "available",
        "protocol": "openai_compatible",
        "baseUrl": TEST_BASE_URL,
        "models": [
            {
                "id": "enterprise-model",
                "object": "model",
                "created": 1_725_000_000,
                "ownedBy": "platform-team",
            }
        ],
        "diagnostic": None,
        "modelsEnumerated": True,
    }
    assert transport.calls == [
        (
            f"{TEST_BASE_URL}/models",
            "GET",
            {"Accept": "application/json"},
            5,
        )
    ]
    assert response_body.closed is True
    assert injected.calls == []
    assert not paths.config_dir.exists()


def test_provider_inspection_bearer_is_transient_and_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response_body = FakeHTTPResponse(_valid_models_payload())
    transport = RecordingTransport(response_body)
    _patch_inspection_transport(monkeypatch, transport)
    application, _, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "openai_compatible",
                "baseUrl": TEST_BASE_URL,
                "authMode": "bearer",
                "credential": TEST_SECRET,
            },
        )

    assert response.status_code == 200, response.text
    assert TEST_SECRET not in response.text
    assert transport.calls[0][2] == {
        "Accept": "application/json",
        "Authorization": f"Bearer {TEST_SECRET}",
    }
    assert injected.calls == []


def test_provider_inspection_does_not_echo_secret_in_transport_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport = RecordingTransport(URLError(f"upstream rejected {TEST_SECRET}"))
    _patch_inspection_transport(monkeypatch, transport)
    application, _, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "openai_compatible",
                "baseUrl": TEST_BASE_URL,
                "authMode": "bearer",
                "credential": TEST_SECRET,
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "unavailable"
    assert TEST_SECRET not in response.text
    assert len(transport.calls) == 1
    assert injected.calls == []


@pytest.mark.parametrize(
    "response_object",
    [
        FakeHTTPResponse(raw_body=b"not-json"),
        FakeHTTPResponse({"object": "list", "data": [{"id": ""}]}),
        FakeHTTPResponse({"object": "list", "data": {}}),
        FakeHTTPResponse(status=502, payload={"error": "synthetic upstream"}),
        HTTPError(
            f"{TEST_BASE_URL}/models",
            307,
            "redirect",
            {"Location": "https://outside.example/v1/models"},
            None,
        ),
        URLError("synthetic enterprise unavailable"),
    ],
)
def test_provider_inspection_invalid_redirect_or_transport_has_one_attempt_and_no_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response_object: object,
) -> None:
    transport = RecordingTransport(response_object)
    _patch_inspection_transport(monkeypatch, transport)
    application, _, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "openai_compatible",
                "baseUrl": TEST_BASE_URL,
                "authMode": "none",
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["models"] == []
    assert payload["modelsEnumerated"] is False
    assert payload["diagnostic"]
    assert len(transport.calls) == 1
    assert transport.calls[0][0] == f"{TEST_BASE_URL}/models"
    assert "/api/tags" not in transport.calls[0][0]
    assert "outside.example" not in response.text
    assert injected.calls == []


def test_provider_inspection_forbids_model_and_unknown_fields_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport = RecordingTransport(FakeHTTPResponse(_valid_models_payload()))
    _patch_inspection_transport(monkeypatch, transport)
    application, _, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-inspections",
            json={
                "kind": "openai_compatible",
                "baseUrl": TEST_BASE_URL,
                "model": "must-not-be-required-on-inspection",
            },
        )

    assert response.status_code == 422
    assert transport.calls == []
    assert injected.calls == []


def test_openai_candidate_readiness_runs_four_real_adapter_probes_without_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completions = CompletionQueue(
        [
            _raw_text_response("target connectivity"),
            _raw_tool_response(),
            _raw_text_response("attack connectivity"),
            _raw_strict_json_response(),
        ]
    )
    _patch_completion_client(monkeypatch, completions)
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-candidates/readiness",
            json={
                "settings": {
                    "kind": "openai_compatible",
                    "baseUrl": TEST_BASE_URL,
                    "model": "enterprise-model",
                    "authMode": "none",
                }
            },
        )
        state = client.get("/api/provider-setup")

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready"
    assert result["targetProvider"]["provider"] == "openai_compatible"
    assert result["targetProvider"]["model"] == "enterprise-model"
    assert result["attackProvider"]["provider"] == "openai_compatible"
    assert [probe["id"] for probe in result["targetProvider"]["probes"]] == [
        "target.connectivity",
        "target.tool_calling",
    ]
    assert [probe["id"] for probe in result["attackProvider"]["probes"]] == [
        "attack.connectivity",
        "attack.strict_json",
    ]
    assert len(completions.calls) == 4
    assert completions.calls[1]["tools"][0]["function"]["name"] == (
        "agent_audit_readiness_probe"
    )
    assert injected.calls == []
    assert state.json()["configured"] is False
    assert not paths.config_dir.exists()


def test_bearer_candidate_readiness_and_missing_bearer_save_do_not_leak_or_mutate_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    completions = CompletionQueue(
        [
            _raw_text_response("target connectivity"),
            _raw_tool_response(),
            _raw_text_response("attack connectivity"),
            _raw_strict_json_response(),
        ]
    )
    _patch_completion_client(monkeypatch, completions)
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        readiness = client.post(
            "/api/provider-candidates/readiness",
            json={
                "settings": {
                    "kind": "openai_compatible",
                    "baseUrl": TEST_BASE_URL,
                    "model": "enterprise-model",
                    "authMode": "bearer",
                },
                "credential": TEST_SECRET,
            },
        )
        before = client.get("/api/provider-setup")
        missing = client.put(
            "/api/provider-setup",
            json={
                "settings": {
                    "kind": "openai_compatible",
                    "baseUrl": TEST_BASE_URL,
                    "model": "enterprise-model",
                    "authMode": "bearer",
                }
            },
        )
        after = client.get("/api/provider-setup")

    assert readiness.status_code == 200, readiness.text
    assert TEST_SECRET not in readiness.text
    assert readiness.json()["status"] == "ready"
    assert missing.status_code == 422
    assert TEST_SECRET not in missing.text
    assert before.json() == after.json()
    assert injected.calls == []
    assert not paths.config_dir.exists()


def test_save_openai_runtime_is_immediately_active_and_only_public_settings_persist(
    tmp_path: Path,
) -> None:
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        saved = client.put(
            "/api/provider-setup",
            json={
                "settings": {
                    "kind": "openai_compatible",
                    "baseUrl": f"{TEST_ORIGIN}/",
                    "model": " enterprise-model ",
                    "authMode": "none",
                }
            },
        )
        setup = client.get("/api/provider-setup")
        runtime = client.get("/api/runtime")
        plans = client.get("/api/attack-plans")

    assert saved.status_code == 200, saved.text
    assert saved.json()["settings"] == {
        "kind": "openai_compatible",
        "baseUrl": TEST_BASE_URL,
        "model": "enterprise-model",
        "authMode": "none",
    }
    assert saved.json()["credentialConfigured"] is False
    assert setup.json() == saved.json()
    assert runtime.json()["provider"] == "openai_compatible"
    assert runtime.json()["model"] == "enterprise-model"
    assert plans.status_code == 200
    assert injected.calls == []

    settings_path = paths.config_dir / PROVIDER_SETTINGS_FILENAME
    persisted = json.loads(settings_path.read_text(encoding="utf-8"))
    assert persisted == {
        "kind": "openai_compatible",
        "baseUrl": TEST_BASE_URL,
        "model": "enterprise-model",
        "authMode": "none",
    }
    assert TEST_SECRET not in settings_path.read_text(encoding="utf-8")


def test_save_bearer_runtime_uses_transient_secret_without_artifact_leak(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application, paths, injected = _app(tmp_path)

    with TestClient(application) as client:
        saved = client.put(
            "/api/provider-setup",
            json={
                "settings": {
                    "kind": "openai_compatible",
                    "baseUrl": TEST_BASE_URL,
                    "model": "enterprise-model",
                    "authMode": "bearer",
                },
                "credential": TEST_SECRET,
            }
        )
        setup = client.get("/api/provider-setup")
        runtime = client.get("/api/runtime")

    assert saved.status_code == 200, saved.text
    assert setup.status_code == 200
    assert runtime.status_code == 200
    assert saved.json()["credentialConfigured"] is True
    assert setup.json()["credentialConfigured"] is True
    assert TEST_SECRET not in saved.text
    assert TEST_SECRET not in setup.text
    assert TEST_SECRET not in runtime.text
    settings_path = paths.config_dir / PROVIDER_SETTINGS_FILENAME
    assert TEST_SECRET not in settings_path.read_text(encoding="utf-8")
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "kind": "openai_compatible",
        "baseUrl": TEST_BASE_URL,
        "model": "enterprise-model",
        "authMode": "bearer",
    }
    assert injected.calls == []


def test_bearer_settings_write_failure_is_explicit_and_has_no_plaintext_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application, paths, injected = _app(tmp_path)
    failure = ProviderSettingsWriteError("provider settings file unavailable")
    monkeypatch.setattr(
        ProviderSettingsStore,
        "save",
        lambda self, settings: (_ for _ in ()).throw(failure),
    )

    with TestClient(application) as client:
        response = client.put(
            "/api/provider-setup",
            json={
                "settings": {
                    "kind": "openai_compatible",
                    "baseUrl": TEST_BASE_URL,
                    "model": "enterprise-model",
                    "authMode": "bearer",
                },
                "credential": TEST_SECRET,
            },
        )
        state = client.get("/api/provider-setup")

    assert response.status_code == 500
    assert TEST_SECRET not in response.text
    assert "provider settings file unavailable" in response.text
    assert state.json()["configured"] is False
    assert injected.calls == []
    assert not paths.config_dir.exists()


def test_old_sidecar_secret_is_not_reused_for_a_changed_bearer_origin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A new origin must receive a newly supplied key, never the old env key."""

    paths = resolve_app_paths(tmp_path / "app-home")
    old_settings = ProviderConnectionSettings(
        kind="openai_compatible",
        base_url=OLD_BASE_URL,
        model="legacy-model",
        auth_mode="bearer",
    )
    ProviderSettingsStore(paths.config_dir).save(old_settings)
    monkeypatch.setenv(PROVIDER_CREDENTIAL_ENV, OLD_ENV_SECRET)

    inspection_transport = RecordingTransport(FakeHTTPResponse(_valid_models_payload()))
    _patch_inspection_transport(monkeypatch, inspection_transport)
    captured_credentials: list[str | None] = []
    completions = CompletionQueue([])

    def capture_client(provider: OpenAICompatibleProvider) -> CompletionQueue:
        captured_credentials.append(getattr(provider, "_credential", None))
        return completions

    monkeypatch.setattr(OpenAICompatibleProvider, "_create_client", capture_client)
    application = create_app(
        provider=None,
        retriever=make_tfidf_retriever(),
        app_paths=paths,
        history_path=tmp_path / "history" / "audit.sqlite3",
    )
    new_settings = {
        "kind": "openai_compatible",
        "baseUrl": NEW_BASE_URL,
        "model": "new-model",
        "authMode": "bearer",
    }

    with TestClient(application) as client:
        before = client.get("/api/provider-setup")
        inspection = client.post(
            "/api/provider-inspections",
            json={
                "kind": "openai_compatible",
                "baseUrl": NEW_BASE_URL,
                "authMode": "bearer",
            },
        )
        readiness = client.post(
            "/api/provider-candidates/readiness",
            json={"settings": new_settings},
        )
        save = client.put("/api/provider-setup", json={"settings": new_settings})
        after = client.get("/api/provider-setup")

    assert before.status_code == 200
    assert before.json()["settings"]["baseUrl"] == OLD_BASE_URL
    assert inspection.status_code == 200, inspection.text
    assert inspection.json()["status"] == "unavailable"
    assert inspection.json()["modelsEnumerated"] is False
    assert inspection_transport.calls == []
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["status"] == "unavailable"
    assert all(
        probe["status"] == "failed"
        for role in ("targetProvider", "attackProvider")
        for probe in readiness.json()[role]["probes"]
    )
    assert save.status_code == 422, save.text
    assert after.json() == before.json()
    assert captured_credentials == []
    for response in (inspection, readiness, save, after):
        assert OLD_ENV_SECRET not in response.text
    settings_text = (paths.config_dir / PROVIDER_SETTINGS_FILENAME).read_text(
        encoding="utf-8"
    )
    assert OLD_ENV_SECRET not in settings_text
    assert NEW_BASE_URL not in settings_text


def test_changed_bearer_origin_uses_only_the_new_transient_credential(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A changed address is usable only after the user supplies its new key."""

    paths = resolve_app_paths(tmp_path / "app-home")
    old_settings = ProviderConnectionSettings(
        kind="openai_compatible",
        base_url=OLD_BASE_URL,
        model="legacy-model",
        auth_mode="bearer",
    )
    ProviderSettingsStore(paths.config_dir).save(old_settings)
    monkeypatch.setenv(PROVIDER_CREDENTIAL_ENV, OLD_ENV_SECRET)

    inspection_transport = RecordingTransport(FakeHTTPResponse(_valid_models_payload()))
    _patch_inspection_transport(monkeypatch, inspection_transport)
    completions = CompletionQueue(
        [
            _raw_text_response("target connectivity"),
            _raw_tool_response(),
            _raw_text_response("attack connectivity"),
            _raw_strict_json_response(),
        ]
    )
    captured_credentials: list[str | None] = []

    def capture_client(provider: OpenAICompatibleProvider) -> CompletionQueue:
        captured_credentials.append(getattr(provider, "_credential", None))
        return completions

    monkeypatch.setattr(OpenAICompatibleProvider, "_create_client", capture_client)
    application = create_app(
        provider=None,
        retriever=make_tfidf_retriever(),
        app_paths=paths,
        history_path=tmp_path / "history" / "audit.sqlite3",
    )
    new_settings = {
        "kind": "openai_compatible",
        "baseUrl": NEW_BASE_URL,
        "model": "new-model",
        "authMode": "bearer",
    }

    with TestClient(application) as client:
        inspection = client.post(
            "/api/provider-inspections",
            json={
                "kind": "openai_compatible",
                "baseUrl": NEW_BASE_URL,
                "authMode": "bearer",
                "credential": NEW_SECRET,
            },
        )
        readiness = client.post(
            "/api/provider-candidates/readiness",
            json={"settings": new_settings, "credential": NEW_SECRET},
        )
        save = client.put(
            "/api/provider-setup",
            json={"settings": new_settings, "credential": NEW_SECRET},
        )
        setup = client.get("/api/provider-setup")

    assert inspection.status_code == 200, inspection.text
    assert inspection.json()["status"] == "available"
    assert inspection_transport.calls[0][0] == f"{NEW_BASE_URL}/models"
    assert inspection_transport.calls[0][2]["Authorization"] == f"Bearer {NEW_SECRET}"
    assert OLD_ENV_SECRET not in inspection_transport.calls[0][2]["Authorization"]
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["status"] == "ready"
    assert captured_credentials == [NEW_SECRET] * 4
    assert save.status_code == 200, save.text
    assert setup.json()["settings"]["baseUrl"] == NEW_BASE_URL
    assert setup.json()["credentialConfigured"] is True
    for response in (inspection, readiness, save, setup):
        assert NEW_SECRET not in response.text
        assert OLD_ENV_SECRET not in response.text
    settings_text = (paths.config_dir / PROVIDER_SETTINGS_FILENAME).read_text(
        encoding="utf-8"
    )
    assert NEW_SECRET not in settings_text
    assert OLD_ENV_SECRET not in settings_text


def test_saved_origin_may_reuse_matching_sidecar_secret_for_readiness_and_save(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The startup env key is reusable only for the exact saved connection."""

    paths = resolve_app_paths(tmp_path / "app-home")
    saved_settings = ProviderConnectionSettings(
        kind="openai_compatible",
        base_url=OLD_BASE_URL,
        model="legacy-model",
        auth_mode="bearer",
    )
    ProviderSettingsStore(paths.config_dir).save(saved_settings)
    monkeypatch.setenv(PROVIDER_CREDENTIAL_ENV, OLD_ENV_SECRET)
    completions = CompletionQueue(
        [
            _raw_text_response("target connectivity"),
            _raw_tool_response(),
            _raw_text_response("attack connectivity"),
            _raw_strict_json_response(),
        ]
    )
    captured_credentials: list[str | None] = []

    def capture_client(provider: OpenAICompatibleProvider) -> CompletionQueue:
        captured_credentials.append(getattr(provider, "_credential", None))
        return completions

    monkeypatch.setattr(OpenAICompatibleProvider, "_create_client", capture_client)
    application = create_app(
        provider=None,
        retriever=make_tfidf_retriever(),
        app_paths=paths,
        history_path=tmp_path / "history" / "audit.sqlite3",
    )
    payload = {
        "settings": saved_settings.model_dump(mode="json", by_alias=True),
    }

    with TestClient(application) as client:
        readiness = client.post("/api/provider-candidates/readiness", json=payload)
        save = client.put("/api/provider-setup", json=payload)
        setup = client.get("/api/provider-setup")

    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["status"] == "ready"
    assert len(captured_credentials) == 4
    assert captured_credentials == [OLD_ENV_SECRET] * 4
    assert save.status_code == 200, save.text
    assert save.json()["credentialConfigured"] is True
    assert setup.json()["settings"] == payload["settings"]
    assert setup.json()["credentialConfigured"] is True
    assert OLD_ENV_SECRET not in save.text
    assert OLD_ENV_SECRET not in setup.text


def test_confirmed_openai_bearer_runtime_produces_scan_and_replay_without_secret_in_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = WorkspaceService().create(
        tmp_path / "workspace",
        "F-031 secret boundary Workspace",
        seed_dir=DEMO_SEED,
    )
    completions = CompletionQueue(
        [
            _raw_variant_response(),
            _raw_text_response("safe synthetic response"),
            _raw_variant_response("fixed second enterprise runtime variant"),
            _raw_text_response("safe synthetic response"),
            _raw_text_response("safe replay response"),
            _raw_text_response("safe secure replay response"),
        ]
    )
    _patch_completion_client(monkeypatch, completions)
    application, paths, injected = _app(tmp_path, workspace=workspace)
    history_path = tmp_path / "history" / "audit.sqlite3"

    with TestClient(application) as client:
        saved = client.put(
            "/api/provider-setup",
            json={
                "settings": {
                    "kind": "openai_compatible",
                    "baseUrl": TEST_BASE_URL,
                    "model": "enterprise-model",
                    "authMode": "bearer",
                },
                "credential": TEST_SECRET,
            },
        )
        plans = client.get("/api/attack-plans")
        plan = next(
            item for item in plans.json() if item["basisType"] == "resource_owner_scope"
        )
        scan_response = client.post(
            "/api/scans",
            json={"planId": plan["id"], "maxRounds": 2},
        )
        assert scan_response.status_code == 200, scan_response.text
        scan = scan_response.json()
        detail = client.get(f"/api/scans/{scan['id']}")
        replay = client.post(f"/api/scans/{scan['id']}/replays", json={})
        history = client.get("/api/scans")

    assert saved.status_code == 200
    assert replay.status_code == 200, replay.text
    assert scan["provider"] == "openai_compatible"
    assert detail.status_code == 200
    assert history.status_code == 200
    assert len(completions.calls) == 6
    for body in (saved, scan_response, detail, replay, history):
        assert TEST_SECRET not in body.text
    assert injected.calls == []

    for path in paths.config_dir.parent.rglob("*"):
        if path.is_file():
            assert TEST_SECRET.encode("utf-8") not in path.read_bytes()
    for path in workspace.root.rglob("*"):
        if path.is_file():
            assert TEST_SECRET.encode("utf-8") not in path.read_bytes()
    assert history_path.is_file()
    assert TEST_SECRET.encode("utf-8") not in history_path.read_bytes()
    if paths.logs_dir.exists():
        for path in paths.logs_dir.rglob("*"):
            if path.is_file():
                assert TEST_SECRET.encode("utf-8") not in path.read_bytes()
