from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import asyncio

from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderUsage,
    ProviderUsageSnapshot,
    ProviderUsageTracker,
    normalize_openai_chat_response,
)
from agent_audit_api.providers.deepseek import DeepSeekProvider
from agent_audit_api.providers.ollama import OllamaProvider


def _raw_response(*, usage: Any) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="合成回答", tool_calls=[])
            )
        ],
        usage=usage,
    )


def _client(response: Any) -> tuple[Any, Any]:
    class RecordingCompletions:
        def __init__(self, raw_response: Any) -> None:
            self.response = raw_response
            self.calls: list[dict[str, Any]] = []

        async def create(self, **request: Any) -> Any:
            self.calls.append(request)
            return self.response

    completions = RecordingCompletions(response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_normalize_openai_usage_accepts_complete_prompt_completion_total_fields() -> None:
    response = normalize_openai_chat_response(
        _raw_response(
            usage=SimpleNamespace(
                prompt_tokens=11,
                completion_tokens=7,
                total_tokens=18,
            )
        )
    )

    assert response.usage == ProviderUsage(
        input_tokens=11,
        output_tokens=7,
        total_tokens=18,
    )


def test_normalize_openai_usage_keeps_incomplete_or_invalid_usage_unknown() -> None:
    incomplete = normalize_openai_chat_response(
        _raw_response(
            usage={
                "prompt_tokens": 11,
                "completion_tokens": 7,
            }
        )
    )
    invalid = normalize_openai_chat_response(
        _raw_response(
            usage={
                "prompt_tokens": 11,
                "completion_tokens": -1,
                "total_tokens": 10,
            }
        )
    )

    assert incomplete.usage is None
    assert invalid.usage is None


@dataclass
class ScriptedProvider:
    responses: list[LLMResponse]
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        return self.responses.pop(0)


def test_usage_tracker_snapshot_delta_counts_calls_and_preserves_unknown_entries() -> None:
    known = ProviderUsage(input_tokens=3, output_tokens=2, total_tokens=5)
    provider = ScriptedProvider(
        responses=[
            LLMResponse(content="first", usage=known),
            LLMResponse(content="second", usage=None),
        ]
    )
    tracker = ProviderUsageTracker(provider)
    before = tracker.snapshot()

    asyncio.run(tracker.complete([{"role": "user", "content": "one"}]))
    asyncio.run(tracker.complete([{"role": "user", "content": "two"}]))

    assert isinstance(before, ProviderUsageSnapshot)
    assert tracker.calls_since(before) == 2
    assert tracker.usages_since(before) == (known, None)
    assert tracker.delta(before) == (2, (known, None))
    assert len(provider.calls) == 2


def test_openai_compatible_adapters_forward_normalized_usage() -> None:
    raw = _raw_response(
        usage={
            "prompt_tokens": 13,
            "completion_tokens": 5,
            "total_tokens": 18,
        }
    )
    ollama_client, _ = _client(raw)
    deepseek_client, _ = _client(raw)

    ollama_response = asyncio.run(
        OllamaProvider(client=ollama_client).complete(
            [{"role": "user", "content": "测试"}]
        )
    )
    deepseek_response = asyncio.run(
        DeepSeekProvider(client=deepseek_client).complete(
            [{"role": "user", "content": "测试"}]
        )
    )

    expected = ProviderUsage(input_tokens=13, output_tokens=5, total_tokens=18)
    assert ollama_response.usage == expected
    assert deepseek_response.usage == expected
