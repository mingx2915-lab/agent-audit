"""F-036 adapter-construction checks for the SDK retry boundary."""

from __future__ import annotations

from typing import Any

import pytest

from agent_audit_api.providers.deepseek import DeepSeekProvider
from agent_audit_api.providers.ollama import OllamaProvider


def test_ollama_client_disables_sdk_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    sentinel = object()

    def create_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("openai.AsyncOpenAI", create_client)
    provider = OllamaProvider(
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3:8b",
    )

    assert provider._create_client() is sentinel
    assert captured == {
        "api_key": "ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "max_retries": 0,
    }


def test_deepseek_client_disables_sdk_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DeepSeek must use the same single-attempt SDK boundary as other adapters."""

    captured: dict[str, Any] = {}
    sentinel = object()

    def create_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("openai.AsyncOpenAI", create_client)

    assert DeepSeekProvider._create_client("synthetic-api-key") is sentinel
    assert captured == {
        "api_key": "synthetic-api-key",
        "base_url": "https://api.deepseek.com",
        "max_retries": 0,
    }
