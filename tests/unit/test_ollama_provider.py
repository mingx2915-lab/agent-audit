import asyncio
from types import SimpleNamespace

import pytest

from agent_audit_api.providers.base import ProviderConfigurationError
from agent_audit_api.providers.deepseek import DeepSeekProvider
from agent_audit_api.providers.ollama import OllamaProvider
from agent_audit_api.providers.runtime import create_runtime_provider


class RecordingCompletions:
    def __init__(self, response) -> None:
        self.request = None
        self.response = response

    async def create(self, **request):
        self.request = request
        return self.response


def _client(response):
    completions = RecordingCompletions(response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


def test_ollama_provider_uses_explicit_model_tools_and_no_reasoning() -> None:
    raw_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="本地回答", tool_calls=[]))]
    )
    client, completions = _client(raw_response)
    provider = OllamaProvider(
        client=client,
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3:8b",
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
            [{"role": "user", "content": "调用工具"}],
            tools=tools,
        )
    )

    assert response.content == "本地回答"
    assert completions.request == {
        "model": "qwen3:8b",
        "messages": [{"role": "user", "content": "调用工具"}],
        "reasoning_effort": "none",
        "tools": tools,
    }


def test_ollama_provider_normalizes_openai_compatible_tool_call() -> None:
    raw_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call_local_001",
                            function=SimpleNamespace(
                                name="mock_customer_lookup",
                                arguments='{"customerId":"customer_001"}',
                            ),
                        )
                    ],
                )
            )
        ]
    )
    client, _ = _client(raw_response)

    response = asyncio.run(
        OllamaProvider(client=client).complete(
            [{"role": "user", "content": "查询 customer_001"}]
        )
    )

    assert response.content is None
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "mock_customer_lookup"
    assert response.tool_calls[0].arguments == {"customerId": "customer_001"}


def test_runtime_provider_selection_is_explicit(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_AUDIT_LLM_PROVIDER", raising=False)
    assert isinstance(create_runtime_provider(), DeepSeekProvider)

    monkeypatch.setenv("AGENT_AUDIT_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    provider = create_runtime_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://127.0.0.1:11434/v1"
    assert provider.model == "qwen3:8b"

    monkeypatch.setenv("AGENT_AUDIT_LLM_PROVIDER", "automatic")
    with pytest.raises(ProviderConfigurationError, match="unsupported LLM provider"):
        create_runtime_provider()
