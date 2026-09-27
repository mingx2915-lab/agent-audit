"""Unit coverage for the F-027 Provider setup trust boundaries."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from agent_audit_api.provider_setup import (
    OLLAMA_DISCOVERY_ENDPOINT,
    OLLAMA_DISCOVERY_URL,
    PROVIDER_SETTINGS_FILENAME,
    OllamaDiscoveryError,
    ProviderConnectionSettings,
    ProviderSettingsReadError,
    ProviderSettingsStore,
    discover_ollama_models,
    normalize_ollama_base_url,
    parse_ollama_tags_payload,
)


@dataclass
class FakeTagsResponse:
    payload: object
    status: int = 200
    closed: bool = False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def close(self) -> None:
        self.closed = True


def test_normalize_ollama_base_url_uses_service_root_and_openai_v1_path() -> None:
    assert normalize_ollama_base_url("  http://127.0.0.1:11434/  ") == (
        "http://127.0.0.1:11434/v1"
    )
    assert normalize_ollama_base_url("HTTPS://ollama.intra.example///") == (
        "https://ollama.intra.example/v1"
    )
    assert normalize_ollama_base_url("https://ollama.intra.example/team/v1/") == (
        "https://ollama.intra.example/team/v1"
    )
    assert OLLAMA_DISCOVERY_ENDPOINT == "http://127.0.0.1:11434"
    assert OLLAMA_DISCOVERY_URL == "http://127.0.0.1:11434/api/tags"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "ftp://ollama.example",
        "//ollama.example",
        "http://user:password@ollama.example",
        "http://ollama.example?token=secret",
        "http://ollama.example#fragment",
        "http://ollama.example:99999",
        "http://ollama.example/path with spaces",
    ],
)
def test_normalize_ollama_base_url_rejects_ambiguous_or_secret_bearing_values(
    value: str,
) -> None:
    with pytest.raises(ValueError):
        normalize_ollama_base_url(value)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"models": {}},
        {"models": [None]},
        {"models": [{"name": "", "size": 1, "modified_at": None}]},
        {"models": [{"name": "qwen3:8b", "size": "large"}]},
        {"models": [{"name": "qwen3:8b", "size": -1}]},
        {"models": [{"name": "qwen3:8b", "modified_at": 123}]},
    ],
)
def test_parse_ollama_tags_payload_is_strict(payload: object) -> None:
    with pytest.raises(OllamaDiscoveryError):
        parse_ollama_tags_payload(payload)


def test_discovery_returns_real_models_and_only_calls_fixed_tags_url() -> None:
    calls: list[tuple[str, int]] = []
    response = FakeTagsResponse(
        {
            "models": [
                {
                    "name": " qwen3:8b ",
                    "size": 8_000,
                    "modified_at": "2026-08-28T00:00:00Z",
                },
                {"name": "llama3.2", "size": None, "modified_at": None},
            ]
        }
    )

    def opener(request, *, timeout: int):
        calls.append((request.full_url, timeout))
        return response

    result = discover_ollama_models(opener=opener)

    assert result.endpoint == OLLAMA_DISCOVERY_ENDPOINT
    assert result.status == "available"
    assert [model.name for model in result.models] == ["qwen3:8b", "llama3.2"]
    assert result.models[0].size_bytes == 8_000
    assert result.models[0].modified_at == "2026-08-28T00:00:00Z"
    assert result.diagnostic is None
    assert calls == [(OLLAMA_DISCOVERY_URL, 5)]
    assert response.closed is True


def test_discovery_accepts_empty_model_array_without_fallback() -> None:
    result = discover_ollama_models(
        opener=lambda request, *, timeout: FakeTagsResponse({"models": []})
    )

    assert result.endpoint == OLLAMA_DISCOVERY_ENDPOINT
    assert result.status == "available"
    assert result.models == []
    assert result.diagnostic
    assert "模型" in result.diagnostic
    assert "安装" in result.diagnostic
    assert "重新" in result.diagnostic


@pytest.mark.parametrize(
    "error",
    [
        URLError("connection refused"),
        TimeoutError("timed out"),
        OSError("socket unavailable"),
    ],
)
def test_discovery_reports_unavailable_transport_without_retry(error: Exception) -> None:
    calls: list[str] = []

    def opener(request, *, timeout: int):
        calls.append(request.full_url)
        raise error

    result = discover_ollama_models(opener=opener)

    assert result.endpoint == OLLAMA_DISCOVERY_ENDPOINT
    assert result.status == "unavailable"
    assert result.models == []
    assert result.diagnostic
    assert any(term in result.diagnostic for term in ("连接", "超时"))
    assert "Ollama" in result.diagnostic
    assert "重新" in result.diagnostic
    assert type(error).__name__ not in result.diagnostic
    assert str(error) not in result.diagnostic
    assert calls == [OLLAMA_DISCOVERY_URL]


def test_discovery_does_not_follow_redirect_or_call_location() -> None:
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

    result = discover_ollama_models(opener=opener)

    assert result.status == "unavailable"
    assert result.models == []
    assert "302" in (result.diagnostic or "")
    assert calls == [OLLAMA_DISCOVERY_URL]


def test_provider_settings_store_persists_only_non_secret_settings_and_round_trips(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "config")
    settings = ProviderConnectionSettings(
        kind="ollama",
        base_url="http://127.0.0.1:11434",
        model=" qwen3:8b ",
    )

    assert store.load() is None
    store.save(settings)
    assert store.path == tmp_path / "config" / PROVIDER_SETTINGS_FILENAME
    assert json.loads(store.path.read_text(encoding="utf-8")) == {
        "kind": "ollama",
        "baseUrl": "http://127.0.0.1:11434/v1",
        "model": "qwen3:8b",
        "authMode": "none",
    }
    assert "apiKey" not in store.path.read_text(encoding="utf-8")
    assert store.load() == settings


def test_provider_settings_store_rejects_corrupt_or_invalid_existing_file(
    tmp_path: Path,
) -> None:
    store = ProviderSettingsStore(tmp_path / "config")
    store.config_dir.mkdir(parents=True)
    store.path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ProviderSettingsReadError, match="unable to read provider settings"):
        store.load()

    store.path.write_text(
        json.dumps({"kind": "ollama", "baseUrl": "ftp://invalid", "model": "x"}),
        encoding="utf-8",
    )
    with pytest.raises(ProviderSettingsReadError, match="provider settings are invalid"):
        store.load()


def test_provider_connection_settings_forbid_api_key_and_unknown_fields() -> None:
    with pytest.raises(ValueError):
        ProviderConnectionSettings.model_validate(
            {
                "kind": "ollama",
                "baseUrl": "http://127.0.0.1:11434",
                "model": "qwen3:8b",
                "apiKey": "secret",
            }
        )
