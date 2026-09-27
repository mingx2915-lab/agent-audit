"""DeepSeek OpenAI-compatible Provider Adapter."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any

from ..diagnostic_logging import log_event
from .base import (
    LLMResponse,
    Message,
    ProviderConfigurationError,
    ProviderError,
    ProviderUnavailableError,
    normalize_openai_chat_response,
)


class DeepSeekProvider:
    """Call DeepSeek Flash with thinking explicitly disabled."""

    MODEL = "deepseek-v4-flash"
    BASE_URL = "https://api.deepseek.com"
    THINKING_EXTRA_BODY = {"thinking": {"type": "disabled"}}
    model = MODEL
    base_url = BASE_URL

    def __init__(self, client: Any | None = None) -> None:
        # ``client`` exists solely for explicit unit-test doubles. Production calls
        # construct the OpenAI-compatible client from DEEPSEEK_API_KEY below.
        self._client = client

    @staticmethod
    def _create_client(api_key: str) -> Any:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without dependency installation
            raise ProviderUnavailableError("OpenAI-compatible SDK is not installed") from exc
        return AsyncOpenAI(
            api_key=api_key,
            base_url=DeepSeekProvider.BASE_URL,
            max_retries=0,
        )

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        """Complete a chat request using only ``DEEPSEEK_API_KEY`` for auth."""

        api_key = os.getenv("DEEPSEEK_API_KEY")
        if self._client is None and not api_key:
            raise ProviderConfigurationError("DEEPSEEK_API_KEY is not configured")
        client = self._client if self._client is not None else self._create_client(api_key or "")
        request: dict[str, Any] = {
            "model": self.MODEL,
            "messages": [dict(message) for message in messages],
            "extra_body": {"thinking": {"type": "disabled"}},
        }
        if tools is not None:
            request["tools"] = [dict(tool) for tool in tools]
        log_event("provider_call_started", component="provider", status="started")
        try:
            raw_response = await client.chat.completions.create(**request)
            normalized = normalize_openai_chat_response(raw_response)
        except ProviderError as exc:
            log_event(
                "provider_call_failed",
                component="provider",
                status="failed",
                error_type=type(exc).__name__,
                level="error",
            )
            raise
        except Exception as exc:
            log_event(
                "provider_call_failed",
                component="provider",
                status="failed",
                error_type=type(exc).__name__,
                level="error",
            )
            raise ProviderUnavailableError("DeepSeek provider request failed") from exc
        log_event("provider_call_completed", component="provider", status="passed")
        return normalized
