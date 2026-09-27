"""Process-local API coverage for the F-027 Provider setup flow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

from agent_audit_api.app_paths import AppPaths, resolve_app_paths
from agent_audit_api.main import create_app
from agent_audit_api.provider_setup import (
    OLLAMA_DISCOVERY_ENDPOINT,
    OLLAMA_DISCOVERY_URL,
    PROVIDER_SETTINGS_FILENAME,
    ProviderSettingsReadError,
    ProviderSettingsStore,
    ProviderSettingsWriteError,
)
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderUnavailableError,
    ToolCall,
)
from agent_audit_api.providers.ollama import OllamaProvider
from agent_audit_api.readiness import _READINESS_NONCE, _READINESS_TOOL_NAME
from agent_audit_api.workspace import WorkspaceService
from tests.retriever_support import make_tfidf_retriever


DEMO_SEED = Path(__file__).resolve().parents[2] / "data" / "demo"


@dataclass
class RecordingProvider:
    """Injected provider used to prove that setup reads are side-effect free."""

    model: str = "injected-before-setup"
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append(([dict(message) for message in messages], tools))
        return LLMResponse(content="injected provider response")


@dataclass
class FakeTagsResponse:
    payload: object
    status: int = 200
    closed: bool = False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def close(self) -> None:
        self.closed = True


@dataclass
class RawCompletionClient:
    """Minimal OpenAI-compatible client for candidate/runtime Ollama calls."""

    responses: list[Any]
    requests: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **request: Any) -> object:
        self.requests.append(request)
        if self.responses:
            response = self.responses.pop(0)
        else:
            response = _raw_text_response("runtime test response")
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


def _raw_tool_response(name: str, arguments: dict[str, object]) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="f027-readiness-call",
                            function=SimpleNamespace(
                                name=name,
                                arguments=json.dumps(arguments, separators=(",", ":")),
                            ),
                        )
                    ],
                ),
            )
        ]
    )


def _valid_candidate_responses() -> list[object]:
    return [
        _raw_text_response("candidate connectivity"),
        _raw_tool_response(
            _READINESS_TOOL_NAME,
            {"nonce": _READINESS_NONCE},
        ),
        _raw_text_response("candidate attack connectivity"),
        _raw_text_response(
            json.dumps(
                {"status": "ready", "nonce": _READINESS_NONCE},
                separators=(",", ":"),
            )
        ),
    ]


def _app(
    tmp_path: Path,
    *,
    provider: RecordingProvider | None = None,
    workspace: object | None = None,
    history_path: Path | None = None,
) -> tuple[Any, AppPaths, RecordingProvider]:
    injected = provider or RecordingProvider()
    paths = resolve_app_paths(tmp_path / "app-home")
    application = create_app(
        provider=injected,
        attack_provider=injected,
        retriever=make_tfidf_retriever(),
        workspace=workspace,
        app_paths=paths,
        history_path=history_path,
    )
    return application, paths, injected


def _patch_discovery_transport(monkeypatch: pytest.MonkeyPatch, opener) -> None:
    """Patch the actual no-redirect transport used by the route."""

    import agent_audit_api.provider_setup as provider_setup_module

    monkeypatch.setattr(
        provider_setup_module,
        "_NO_REDIRECT_OPENER",
        SimpleNamespace(open=opener),
    )


def _patch_ollama_client(monkeypatch: pytest.MonkeyPatch, client: RawCompletionClient):
    created: list[tuple[str | None, str | None]] = []

    def create_client(provider: OllamaProvider) -> RawCompletionClient:
        created.append((provider.base_url, provider.model))
        return client

    monkeypatch.setattr(OllamaProvider, "_create_client", create_client)
    return created


def test_get_provider_setup_is_unconfigured_and_does_not_discover_or_complete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    opener_calls: list[str] = []

    def unexpected_opener(request, *, timeout: int):
        opener_calls.append(request.full_url)
        raise AssertionError("GET /api/provider-setup must not call Ollama discovery")

    _patch_discovery_transport(monkeypatch, unexpected_opener)
    application, paths, provider = _app(tmp_path)

    with TestClient(application) as client:
        response = client.get("/api/provider-setup")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["settings"] is None
    assert payload["runtimeSnapshot"]["model"] == provider.model
    assert provider.calls == []
    assert opener_calls == []
    assert not paths.config_dir.exists()


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/provider-discoveries/ollama", {"unexpected": True}),
        (
            "/api/provider-candidates/readiness",
            {
                "settings": {
                    "kind": "ollama",
                    "baseUrl": "http://127.0.0.1:11434",
                    "model": "qwen3:8b",
                    "apiKey": "must-not-be-accepted",
                }
            },
        ),
        (
            "/api/provider-setup",
            {
                "settings": {
                    "kind": "ollama",
                    "baseUrl": "http://127.0.0.1:11434",
                    "model": "qwen3:8b",
                    "apiKey": "must-not-be-accepted",
                }
            },
        ),
    ],
)
def test_provider_setup_routes_reject_extra_fields_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path: str,
    payload: dict[str, object],
) -> None:
    discovery_calls: list[str] = []

    def unexpected_opener(request, *, timeout: int):
        discovery_calls.append(request.full_url)
        raise AssertionError("invalid request must not reach discovery transport")

    _patch_discovery_transport(monkeypatch, unexpected_opener)
    application, paths, provider = _app(tmp_path)
    candidate_client = RawCompletionClient(_valid_candidate_responses())
    _patch_ollama_client(monkeypatch, candidate_client)

    with TestClient(application) as client:
        response = client.post(path, json=payload) if path != "/api/provider-setup" else client.put(path, json=payload)

    assert response.status_code == 422
    assert discovery_calls == []
    assert candidate_client.requests == []
    assert provider.calls == []
    assert not paths.config_dir.exists()


@pytest.mark.parametrize(
    "tags_payload",
    [
        {"models": [{"name": "qwen3:8b", "size": 1, "modified_at": None}]},
        {"models": []},
    ],
)
def test_discovery_uses_only_fixed_loopback_tags_endpoint_and_returns_service_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tags_payload: dict[str, object],
) -> None:
    calls: list[tuple[str, int]] = []
    tags_response = FakeTagsResponse(tags_payload)

    def opener(request, *, timeout: int):
        calls.append((request.full_url, timeout))
        return tags_response

    _patch_discovery_transport(monkeypatch, opener)
    application, _, provider = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post("/api/provider-discoveries/ollama", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["endpoint"] == OLLAMA_DISCOVERY_ENDPOINT
    assert payload["status"] == "available"
    assert calls == [(OLLAMA_DISCOVERY_URL, 5)]
    assert tags_response.closed is True
    assert provider.calls == []
    if tags_payload["models"]:
        assert payload["models"][0] == {
            "name": "qwen3:8b",
            "sizeBytes": 1,
            "modifiedAt": None,
        }
    else:
        assert payload["models"] == []


@pytest.mark.parametrize(
    "failure",
    [
        URLError("connection refused"),
        TimeoutError("timed out"),
        OSError("socket unavailable"),
    ],
)
def test_discovery_reports_unavailable_without_model_completion_or_network_scan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: Exception,
) -> None:
    calls: list[str] = []

    def opener(request, *, timeout: int):
        calls.append(request.full_url)
        raise failure

    _patch_discovery_transport(monkeypatch, opener)
    application, _, provider = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post("/api/provider-discoveries/ollama", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["endpoint"] == OLLAMA_DISCOVERY_ENDPOINT
    assert payload["status"] == "unavailable"
    assert payload["models"] == []
    diagnostic = payload["diagnostic"]
    assert any(term in diagnostic for term in ("连接", "超时"))
    assert "Ollama" in diagnostic
    assert "重新" in diagnostic
    assert type(failure).__name__ not in payload["diagnostic"]
    assert str(failure) not in diagnostic
    assert calls == [OLLAMA_DISCOVERY_URL]
    assert provider.calls == []


def test_discovery_redirect_is_unavailable_and_does_not_follow_location(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    redirect = HTTPError(
        OLLAMA_DISCOVERY_URL,
        302,
        "redirect",
        {"Location": "https://outside.example/api/tags"},
        None,
    )

    def opener(request, *, timeout: int):
        calls.append(request.full_url)
        raise redirect

    _patch_discovery_transport(monkeypatch, opener)
    application, _, provider = _app(tmp_path)

    with TestClient(application) as client:
        response = client.post("/api/provider-discoveries/ollama", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert "302" in payload["diagnostic"]
    assert calls == [OLLAMA_DISCOVERY_URL]
    assert provider.calls == []


def test_candidate_readiness_uses_candidate_for_target_and_attack_without_mutating_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application, paths, injected_provider = _app(tmp_path)
    candidate_client = RawCompletionClient(_valid_candidate_responses())
    created = _patch_ollama_client(monkeypatch, candidate_client)

    with TestClient(application) as client:
        before = client.get("/api/provider-setup")
        response = client.post(
            "/api/provider-candidates/readiness",
            json={
                "settings": {
                    "kind": "ollama",
                    "baseUrl": "https://ollama.intra.example/team/",
                    "model": " candidate-model ",
                }
            },
        )
        after = client.get("/api/provider-setup")

    assert before.status_code == 200
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ready"
    assert result["targetProvider"]["role"] == "target"
    assert result["targetProvider"]["provider"] == "ollama"
    assert result["targetProvider"]["model"] == "candidate-model"
    assert result["attackProvider"]["role"] == "attack"
    assert result["attackProvider"]["model"] == "candidate-model"
    assert len(result["targetProvider"]["probes"]) == 2
    assert len(result["attackProvider"]["probes"]) == 2
    assert {item["basisType"] for item in result["planCompatibility"]} == {
        "resource_owner_scope",
        "tool_owner_scope",
        "source_sink",
        "tool_record_limit",
    }
    assert len(result["planCompatibility"]) == 4
    assert all(item["status"] == "compatible" for item in result["planCompatibility"])
    assert created == [
        ("https://ollama.intra.example/team/v1", "candidate-model")
    ] * 4
    assert len(candidate_client.requests) == 4
    assert all(request["model"] == "candidate-model" for request in candidate_client.requests)
    assert after.json() == before.json()
    assert injected_provider.calls == []
    assert not paths.config_dir.exists()


def test_candidate_provider_error_is_readiness_evidence_not_http_502_or_persistence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application, paths, injected_provider = _app(tmp_path)
    candidate_client = RawCompletionClient(
        [
            ProviderUnavailableError("candidate unavailable"),
            *_valid_candidate_responses()[1:],
        ]
    )
    _patch_ollama_client(monkeypatch, candidate_client)

    with TestClient(application) as client:
        response = client.post(
            "/api/provider-candidates/readiness",
            json={
                "settings": {
                    "kind": "ollama",
                    "baseUrl": "http://127.0.0.1:11434",
                    "model": "candidate-model",
                }
            },
        )
        setup = client.get("/api/provider-setup")

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "partial"
    assert result["targetProvider"]["status"] == "partial"
    assert result["targetProvider"]["probes"][0]["status"] == "failed"
    detail = result["targetProvider"]["probes"][0]["detail"]
    assert any(term in detail for term in ("检查", "服务", "结果"))
    assert "重新" in detail
    assert "candidate unavailable" not in detail
    assert result["attackProvider"]["status"] == "ready"
    assert setup.json()["configured"] is False
    assert injected_provider.calls == []
    assert not paths.config_dir.exists()


def test_confirmed_setup_persists_non_secret_values_updates_runtime_and_survives_rebuild(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = WorkspaceService().create(
        tmp_path / "workspace",
        "F-027 setup test workspace",
        seed_dir=DEMO_SEED,
    )
    history_path = tmp_path / "history" / "audit.sqlite3"
    application, paths, injected_provider = _app(
        tmp_path,
        workspace=workspace,
        history_path=history_path,
    )
    runtime_client = RawCompletionClient([])
    created = _patch_ollama_client(monkeypatch, runtime_client)

    settings_payload = {
        "settings": {
            "kind": "ollama",
            "baseUrl": "http://127.0.0.1:11434/",
            "model": " qwen3:8b ",
        }
    }
    with TestClient(application) as client:
        saved = client.put("/api/provider-setup", json=settings_payload)
        runtime = client.get("/api/runtime")
        plans = client.get("/api/attack-plans")
        resource_plan = next(
            plan for plan in plans.json() if plan["basisType"] == "resource_owner_scope"
        )
        invocation = client.post(
            f"/api/attack-plans/{resource_plan['id']}/execute"
        )
        # Force creation of the configured history path before checking that
        # Provider setup did not leak into SQLite.
        assert client.get("/api/scans").status_code == 200

    assert saved.status_code == 200
    saved_payload = saved.json()
    assert saved_payload["configured"] is True
    assert saved_payload["settings"] == {
        "kind": "ollama",
        "baseUrl": "http://127.0.0.1:11434/v1",
        "model": "qwen3:8b",
        "authMode": "none",
    }
    assert saved_payload["runtimeSnapshot"]["provider"] == "ollama"
    assert saved_payload["runtimeSnapshot"]["model"] == "qwen3:8b"
    assert runtime.json()["provider"] == "ollama"
    assert runtime.json()["model"] == "qwen3:8b"
    assert invocation.status_code == 200
    assert injected_provider.calls == []
    assert created[-1] == ("http://127.0.0.1:11434/v1", "qwen3:8b")
    assert runtime_client.requests
    assert all(request["model"] == "qwen3:8b" for request in runtime_client.requests)

    settings_path = paths.config_dir / PROVIDER_SETTINGS_FILENAME
    assert json.loads(settings_path.read_text(encoding="utf-8")) == {
        "kind": "ollama",
        "baseUrl": "http://127.0.0.1:11434/v1",
        "model": "qwen3:8b",
        "authMode": "none",
    }
    settings_text = settings_path.read_text(encoding="utf-8")
    assert "apiKey" not in settings_text
    assert not any(path.name == PROVIDER_SETTINGS_FILENAME for path in workspace.root.rglob("*"))
    assert not any(path.name == PROVIDER_SETTINGS_FILENAME for path in workspace.exports_path.rglob("*"))
    assert history_path.is_file()
    history_text = history_path.read_bytes().decode("utf-8", errors="ignore")
    assert "provider-settings" not in history_text
    assert "apiKey" not in history_text

    rebuilt = create_app(
        provider=None,
        retriever=make_tfidf_retriever(),
        app_paths=paths,
        history_path=history_path,
    )
    with TestClient(rebuilt) as client:
        restored = client.get("/api/provider-setup")

    assert restored.status_code == 200
    restored_payload = restored.json()
    assert restored_payload["configured"] is True
    assert restored_payload["settings"] == saved_payload["settings"]
    assert restored_payload["runtimeSnapshot"]["provider"] == "ollama"
    assert restored_payload["runtimeSnapshot"]["model"] == "qwen3:8b"


def test_provider_setup_write_and_existing_corrupt_config_fail_clearly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application, paths, _ = _app(tmp_path)
    failure = ProviderSettingsWriteError("unable to write provider settings: disk full")
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
                    "kind": "ollama",
                    "baseUrl": "http://127.0.0.1:11434",
                    "model": "qwen3:8b",
                }
            },
        )
        state = client.get("/api/provider-setup")

    assert response.status_code == 500
    assert "disk full" in response.json()["detail"]
    assert state.json()["configured"] is False
    assert not paths.config_dir.exists()

    corrupt_paths = resolve_app_paths(tmp_path / "corrupt-home")
    corrupt_store = ProviderSettingsStore(corrupt_paths.config_dir)
    corrupt_store.config_dir.mkdir(parents=True)
    corrupt_store.path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ProviderSettingsReadError, match="unable to read provider settings"):
        create_app(
            provider=None,
            retriever=make_tfidf_retriever(),
            app_paths=corrupt_paths,
        )


def test_explicit_provider_injection_is_isolated_from_desktop_settings(
    tmp_path: Path,
) -> None:
    paths = resolve_app_paths(tmp_path / "injected-home")
    store = ProviderSettingsStore(paths.config_dir)
    store.config_dir.mkdir(parents=True)
    store.path.write_text("{not-json", encoding="utf-8")
    injected = RecordingProvider(model="isolated-test-provider")

    application = create_app(
        provider=injected,
        attack_provider=injected,
        retriever=make_tfidf_retriever(),
        app_paths=paths,
        history_path=tmp_path / "injected-history.sqlite3",
    )
    with TestClient(application) as client:
        response = client.get("/api/provider-setup")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["settings"] is None
    assert payload["runtimeSnapshot"]["model"] == "isolated-test-provider"
    assert injected.calls == []
