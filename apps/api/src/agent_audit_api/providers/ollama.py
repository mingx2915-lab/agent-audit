"""Local Ollama OpenAI-compatible Provider Adapter."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from ..diagnostic_logging import log_event
from .base import (
    LLMResponse,
    Message,
    ProviderConfigurationError,
    ProviderError,
    ProviderUnavailableError,
    normalize_openai_chat_response,
)


class OllamaProvider:
    """Call an explicitly configured local Ollama model without thinking."""

    DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
    DEFAULT_MODEL = "qwen3:8b"

    def __init__(
        self,
        client: Any | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        auth_mode: Literal["none", "bearer"] | None = None,
        credential: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)
        self.model = model or os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)
        resolved_auth_mode = auth_mode or "none"
        if resolved_auth_mode not in {"none", "bearer"}:
            raise ProviderConfigurationError(
                "unsupported Provider authentication mode"
            )
        self.auth_mode: Literal["none", "bearer"] = resolved_auth_mode
        self._credential = credential if credential is not None else api_key

    @property
    def credential_configured(self) -> bool:
        """Whether a bearer value is available without exposing the value."""

        return self.auth_mode == "bearer" and bool(self._credential)

    def _create_client(self) -> Any:
        if self.auth_mode == "bearer" and not self._credential:
            raise ProviderConfigurationError("Bearer credential is not configured")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - only without installed dependency
            raise ProviderUnavailableError("OpenAI-compatible SDK is not installed") from exc
        return AsyncOpenAI(
            api_key=self._credential if self.auth_mode == "bearer" else "ollama",
            base_url=self.base_url,
            max_retries=0,
        )

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        if not self.base_url.strip():
            raise ProviderConfigurationError("OLLAMA_BASE_URL is not configured")
        if not self.model.strip():
            raise ProviderConfigurationError("OLLAMA_MODEL is not configured")
        if self.auth_mode == "bearer" and not self._credential:
            raise ProviderConfigurationError("Bearer credential is not configured")
        client = self._client if self._client is not None else self._create_client()
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "reasoning_effort": "none",
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
            raise ProviderUnavailableError("Ollama provider request failed") from exc
        log_event("provider_call_completed", component="provider", status="passed")
        return normalized


__all__ = ["OllamaProvider"]
