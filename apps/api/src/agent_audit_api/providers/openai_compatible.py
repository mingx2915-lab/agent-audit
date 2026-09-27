"""Generic OpenAI-compatible Chat Completions Provider Adapter."""

from __future__ import annotations

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


ProviderAuthMode = Literal["none", "bearer"]


def _normalize_base_url(value: str) -> str:
    """Keep the adapter import-independent from the API setup module."""

    from urllib.parse import urlsplit, urlunsplit

    if not isinstance(value, str) or not value.strip():
        raise ProviderConfigurationError("provider baseUrl must not be empty")
    candidate = value.strip()
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in candidate
    ):
        raise ProviderConfigurationError(
            "provider baseUrl contains whitespace or control characters"
        )
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise ProviderConfigurationError("provider baseUrl is not a valid URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ProviderConfigurationError(
            "provider baseUrl must use http or https and include a host"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ProviderConfigurationError("provider baseUrl must not include credentials")
    if parsed.query or parsed.fragment:
        raise ProviderConfigurationError("provider baseUrl must not include a query or fragment")
    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"
    elif not path.endswith("/v1"):
        path = f"{path}/v1"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))


class OpenAICompatibleProvider:
    """Call one explicitly configured OpenAI-compatible Runtime.

    The adapter has no vendor detection, fallback, retry, or model switching.
    ``credential`` is held only by this process object and is never part of a
    public settings DTO or any normalized response.
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        base_url: str,
        model: str,
        auth_mode: ProviderAuthMode | None = None,
        credential: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self.base_url = _normalize_base_url(base_url)
        self.model = model.strip() if isinstance(model, str) else model
        resolved_auth_mode = auth_mode or "none"
        if resolved_auth_mode not in {"none", "bearer"}:
            raise ProviderConfigurationError(
                "unsupported Provider authentication mode"
            )
        self.auth_mode: ProviderAuthMode = resolved_auth_mode
        # ``api_key`` is retained as a narrow compatibility alias for callers
        # constructing adapters directly.  It is never serialized.
        self._credential = credential if credential is not None else api_key

    @property
    def credential_configured(self) -> bool:
        """Whether a bearer value is available, without returning that value."""

        return self.auth_mode == "bearer" and bool(self._credential)

    def _create_client(self) -> Any:
        if self.auth_mode == "bearer" and not self._credential:
            raise ProviderConfigurationError("Bearer credential is not configured")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - only without dependency
            raise ProviderUnavailableError("OpenAI-compatible SDK is not installed") from exc

        # The SDK requires an api_key even for an unauthenticated local
        # endpoint.  This placeholder is not a user credential and is never
        # persisted; bearer endpoints receive the real transient value.
        return AsyncOpenAI(
            api_key=self._credential if self.auth_mode == "bearer" else "not-needed",
            base_url=self.base_url,
            max_retries=0,
        )

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ProviderConfigurationError("OpenAI-compatible model is not configured")
        if self.auth_mode == "bearer" and not self._credential:
            raise ProviderConfigurationError("Bearer credential is not configured")

        client = self._client if self._client is not None else self._create_client()
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
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
            raise ProviderUnavailableError(
                "OpenAI-compatible provider request failed"
            ) from exc
        log_event("provider_call_completed", component="provider", status="passed")
        return normalized


__all__ = ["OpenAICompatibleProvider"]
