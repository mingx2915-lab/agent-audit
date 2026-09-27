"""Anthropic Messages API Provider Adapter.

The application core speaks one OpenAI-shaped canonical input (system/user,
assistant ``tool_calls`` and ``role=tool``).  This module owns the explicit
conversion to Anthropic's content-block protocol and the strict conversion
back to :class:`LLMResponse`.  It intentionally uses one HTTP request per
completion, does not follow redirects, and never exposes a credential in an
exception or response DTO.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..diagnostic_logging import log_event
from ..provider_diagnostics import provider_error_diagnostic
from .base import (
    LLMResponse,
    Message,
    ProviderConfigurationError,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    ToolCall,
    normalize_openai_messages,
    normalize_openai_tools,
)
from .openai_compatible import _normalize_base_url


ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MESSAGES_PATH = "/messages"
ANTHROPIC_MODELS_PATH = "/models"
ProviderAuthMode = Literal["none", "bearer", "x_api_key"]


def _string_field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _anthropic_messages(
    messages: Sequence[Message],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return ``(messages, system_blocks)`` in Anthropic wire format."""

    canonical = normalize_openai_messages(messages)
    converted: list[dict[str, object]] = []
    system_blocks: list[dict[str, object]] = []
    for message in canonical:
        role = message["role"]
        content = message["content"]
        if role == "system":
            # Anthropic puts system content at the request top level.
            if not isinstance(content, str):
                raise ProviderResponseError("Anthropic system message content is invalid")
            system_blocks.append({"type": "text", "text": content})
            continue
        if role == "tool":
            tool_call_id = message.get("tool_call_id")
            if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                raise ProviderResponseError("Anthropic tool result id is invalid")
            if not isinstance(content, str):
                raise ProviderResponseError("Anthropic tool result content is invalid")
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": content,
                        }
                    ],
                }
            )
            continue

        if role == "user":
            if not isinstance(content, str):
                raise ProviderResponseError("Anthropic user message content is invalid")
            converted.append(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": content}],
                }
            )
            continue

        if role != "assistant":
            raise ProviderResponseError("Anthropic message role is invalid")
        blocks: list[dict[str, object]] = []
        if content is not None:
            if not isinstance(content, str):
                raise ProviderResponseError("Anthropic assistant content is invalid")
            blocks.append({"type": "text", "text": content})
        raw_calls = message.get("tool_calls", [])
        if not isinstance(raw_calls, Sequence) or isinstance(raw_calls, (str, bytes)):
            raise ProviderResponseError("Anthropic assistant tool calls are invalid")
        for raw_call in raw_calls:
            if not isinstance(raw_call, Mapping):
                raise ProviderResponseError("Anthropic assistant tool call is invalid")
            call_id = raw_call.get("id")
            name = raw_call.get("name")
            arguments = raw_call.get("arguments")
            if (
                not isinstance(call_id, str)
                or not call_id.strip()
                or not isinstance(name, str)
                or not name.strip()
                or not isinstance(arguments, Mapping)
            ):
                raise ProviderResponseError("Anthropic assistant tool call is invalid")
            blocks.append(
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": name,
                    "input": dict(arguments),
                }
            )
        if not blocks:
            raise ProviderResponseError("Anthropic assistant message is empty")
        converted.append({"role": "assistant", "content": blocks})
    if not converted:
        raise ProviderResponseError("Anthropic request has no non-system messages")
    return converted, system_blocks


def to_anthropic_request_payload(
    messages: Sequence[Message],
    tools: Sequence[Mapping[str, object]] | None,
    *,
    model: str,
    max_tokens: int,
) -> dict[str, object]:
    """Convert canonical target inputs to one strict Messages request."""

    if not isinstance(model, str) or not model.strip():
        raise ProviderConfigurationError("Anthropic model is not configured")
    if type(max_tokens) is not int or max_tokens <= 0:
        raise ProviderConfigurationError("Anthropic max_tokens must be positive")
    anthropic_messages, system_blocks = _anthropic_messages(messages)
    payload: dict[str, object] = {
        "model": model.strip(),
        "max_tokens": max_tokens,
        "messages": anthropic_messages,
    }
    if system_blocks:
        payload["system"] = system_blocks
    if tools is not None:
        anthropic_tools: list[dict[str, object]] = []
        for tool in normalize_openai_tools(tools):
            converted: dict[str, object] = {
                "name": tool["name"],
                "input_schema": tool["input_schema"],
            }
            if "description" in tool:
                converted["description"] = tool["description"]
            anthropic_tools.append(converted)
        payload["tools"] = anthropic_tools
    return payload


def _strict_usage(raw_usage: object) -> tuple[int, int, int] | None:
    if raw_usage is None:
        return None
    if not isinstance(raw_usage, Mapping):
        raise ProviderResponseError("Anthropic response usage is invalid")
    input_tokens = raw_usage.get("input_tokens")
    output_tokens = raw_usage.get("output_tokens")
    if (
        type(input_tokens) is not int
        or input_tokens < 0
        or type(output_tokens) is not int
        or output_tokens < 0
    ):
        raise ProviderResponseError("Anthropic response usage is invalid")
    return input_tokens, output_tokens, input_tokens + output_tokens


def normalize_anthropic_response(raw_response: object) -> LLMResponse:
    """Strictly normalize one Anthropic ``message`` response."""

    if not isinstance(raw_response, Mapping):
        raise ProviderResponseError("Anthropic response must be a JSON object")
    if raw_response.get("type") != "message":
        raise ProviderResponseError("Anthropic response type is invalid")
    if raw_response.get("role") != "assistant":
        raise ProviderResponseError("Anthropic response role is invalid")
    raw_content = raw_response.get("content")
    if not isinstance(raw_content, list):
        raise ProviderResponseError("Anthropic response content must be an array")

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    seen_tool_ids: set[str] = set()
    for index, block in enumerate(raw_content):
        if not isinstance(block, Mapping):
            raise ProviderResponseError(
                f"Anthropic response content block at index {index} is invalid"
            )
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if not isinstance(text, str):
                raise ProviderResponseError(
                    f"Anthropic text block at index {index} is invalid"
                )
            text_parts.append(text)
            continue
        if block_type != "tool_use":
            raise ProviderResponseError(
                f"Anthropic response content block at index {index} has unsupported type"
            )
        call_id = block.get("id")
        name = block.get("name")
        arguments = block.get("input")
        if (
            not isinstance(call_id, str)
            or not call_id.strip()
            or not isinstance(name, str)
            or not name.strip()
            or not isinstance(arguments, Mapping)
        ):
            raise ProviderResponseError(
                f"Anthropic tool_use block at index {index} is invalid"
            )
        if call_id in seen_tool_ids:
            raise ProviderResponseError("Anthropic response contains duplicate tool_use ids")
        seen_tool_ids.add(call_id)
        tool_calls.append(ToolCall(id=call_id, name=name, arguments=dict(arguments)))

    usage_values = _strict_usage(raw_response.get("usage"))
    content = "".join(text_parts).strip() or None
    if content is None and not tool_calls:
        raise ProviderResponseError("Anthropic response content is empty")
    from .base import ProviderUsage

    usage = (
        ProviderUsage(
            input_tokens=usage_values[0],
            output_tokens=usage_values[1],
            total_tokens=usage_values[2],
        )
        if usage_values is not None
        else None
    )
    return LLMResponse(content=content, tool_calls=tuple(tool_calls), usage=usage)


def parse_anthropic_models_payload(payload: object) -> list[dict[str, object]]:
    """Parse the read-only model list shape used by Anthropic-compatible APIs.

    Anthropic's model listing has a ``data`` array and does not require the
    OpenAI ``object=list`` envelope.  Only the stable public ``id`` and
    optional ``type``/``created_at``/``display_name`` fields are retained.
    """

    if not isinstance(payload, Mapping) or type(payload.get("data")) is not list:
        raise ProviderResponseError("Anthropic models response data must be an array")
    models: list[dict[str, object]] = []
    for index, item in enumerate(payload["data"]):
        if not isinstance(item, Mapping):
            raise ProviderResponseError(f"Anthropic model at index {index} is invalid")
        model_id = item.get("id")
        if (
            not isinstance(model_id, str)
            or not model_id.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in model_id)
        ):
            raise ProviderResponseError(f"Anthropic model at index {index} has an invalid id")
        model_type = item.get("type")
        if model_type is not None and model_type != "model":
            raise ProviderResponseError(f"Anthropic model at index {index} has an invalid type")
        created_at = item.get("created_at")
        if created_at is not None and not isinstance(created_at, str):
            raise ProviderResponseError(
                f"Anthropic model at index {index} has an invalid created_at"
            )
        display_name = item.get("display_name")
        if display_name is not None and (
            not isinstance(display_name, str)
            or any(ord(character) < 32 or ord(character) == 127 for character in display_name)
        ):
            raise ProviderResponseError(
                f"Anthropic model at index {index} has an invalid display_name"
            )
        models.append(
            {
                "id": model_id.strip(),
                "object": "model",
                "created": None,
                "owned_by": None,
            }
        )
    return models


class _NoRedirectInspectionHandler(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


_NO_REDIRECT_INSPECTION_OPENER = build_opener(_NoRedirectInspectionHandler())


def inspect_anthropic_endpoint(
    *,
    base_url: str,
    auth_mode: ProviderAuthMode | None = None,
    credential: str | None = None,
    opener: Any | None = None,
) -> Any:
    """Inspect exactly one explicit Anthropic-compatible ``/v1/models`` URL."""

    # Imports remain local to avoid a module cycle: provider_setup dispatches
    # here only after its own DTO classes and transport helpers are loaded.
    from ..provider_setup import (
        ProviderModelCandidate,
        ProtocolInspectionResult,
        _auth_headers,
        normalize_provider_base_url,
    )

    normalized = normalize_provider_base_url(base_url)
    try:
        headers = {
            **_auth_headers(auth_mode, credential),
            "Content-Type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }
    except ProviderConfigurationError as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="anthropic_compatible",
            ),
            models_enumerated=False,
        )
    request = Request(
        f"{normalized.rstrip('/')}{ANTHROPIC_MODELS_PATH}",
        method="GET",
        headers=headers,
    )
    if opener is None:
        from ..provider_setup import _NO_REDIRECT_OPENER

        open_url = _NO_REDIRECT_OPENER.open
    else:
        open_url = opener
    response: object | None = None
    try:
        response = open_url(request, timeout=5)
        status = _response_status(response)
        if status is not None and not 200 <= status < 300:
            raise ProviderResponseError(
                f"Anthropic models endpoint returned HTTP {status}",
                status_code=status,
            )
        read = getattr(response, "read", None)
        if not callable(read):
            raise ProviderResponseError("Anthropic models response body is unreadable")
        payload = json.loads(read())
        raw_models = parse_anthropic_models_payload(payload)
        models = [ProviderModelCandidate.model_validate(item) for item in raw_models]
    except HTTPError as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="anthropic_compatible",
            ),
            models_enumerated=False,
        )
    except (OSError, URLError, TimeoutError) as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="anthropic_compatible",
            ),
            models_enumerated=False,
        )
    except (ProviderResponseError, TypeError, ValueError, UnicodeError) as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="anthropic_compatible",
            ),
            models_enumerated=False,
        )
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
    return ProtocolInspectionResult(
        status="available",
        protocol="anthropic_compatible",
        base_url=normalized,
        models=models,
        diagnostic=None,
        models_enumerated=True,
    )


async def _maybe_await(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


async def _response_json(response: object) -> object:
    """Read a JSON object from httpx or a deliberately tiny test client."""

    if isinstance(response, Mapping):
        return response
    json_method = getattr(response, "json", None)
    if not callable(json_method):
        raise ProviderResponseError("Anthropic response body is unreadable")
    try:
        payload = await _maybe_await(json_method())
    except Exception as exc:
        raise ProviderResponseError("Anthropic response is not valid JSON") from exc
    return payload


def _response_status(response: object) -> int | None:
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return int(status)
    status = getattr(response, "status", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return int(status)
    return None


class AnthropicCompatibleProvider:
    """Call one explicitly configured Anthropic Messages endpoint."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        base_url: str,
        model: str,
        auth_mode: ProviderAuthMode | None = None,
        credential: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self.base_url = _normalize_base_url(base_url)
        self.model = model.strip() if isinstance(model, str) else model
        resolved_auth_mode = auth_mode or "none"
        if resolved_auth_mode not in {"none", "bearer", "x_api_key"}:
            raise ProviderConfigurationError("unsupported Provider authentication mode")
        self.auth_mode: ProviderAuthMode = resolved_auth_mode
        self._credential = credential if credential is not None else api_key
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ProviderConfigurationError("Anthropic max_tokens must be positive")
        self.max_tokens = max_tokens

    @property
    def credential_configured(self) -> bool:
        return self.auth_mode in {"bearer", "x_api_key"} and bool(self._credential)

    def _headers(self) -> dict[str, str]:
        if self.auth_mode in {"bearer", "x_api_key"} and not self._credential:
            raise ProviderConfigurationError(
                f"{self.auth_mode} credential is not configured"
            )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
        }
        if self.auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {self._credential}"
        elif self.auth_mode == "x_api_key":
            headers["x-api-key"] = str(self._credential)
        return headers

    async def _post(self, url: str, payload: Mapping[str, object], headers: Mapping[str, str]) -> object:
        if self._client is not None:
            post = getattr(self._client, "post", None)
            if not callable(post):
                raise ProviderConfigurationError("Anthropic client does not support POST")
            try:
                return await _maybe_await(
                    post(url, headers=dict(headers), json=dict(payload), timeout=30)
                )
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderUnavailableError("Anthropic provider request failed") from exc
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - packaged dependency check
            raise ProviderUnavailableError("HTTP client is not installed") from exc
        try:
            transport = httpx.AsyncHTTPTransport(retries=0)
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=30,
                transport=transport,
            ) as client:
                return await client.post(
                    url,
                    headers=dict(headers),
                    json=dict(payload),
                )
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("Anthropic provider request failed") from exc

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ProviderConfigurationError("Anthropic model is not configured")
        payload = to_anthropic_request_payload(
            messages,
            tools,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        url = f"{self.base_url.rstrip('/')}{ANTHROPIC_MESSAGES_PATH}"
        log_event("provider_call_started", component="provider", status="started")
        try:
            response = await self._post(url, payload, self._headers())
            status = _response_status(response)
            if status is not None and not 200 <= status < 300:
                raise ProviderUnavailableError(
                    f"Anthropic provider request failed with HTTP {status}",
                    status_code=status,
                )
            raw_payload = await _response_json(response)
            normalized = normalize_anthropic_response(raw_payload)
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
            # Keep the transport trust boundary deterministic even when a
            # caller-provided/test transport replaces ``_post`` itself.
            raise ProviderUnavailableError("Anthropic provider request failed") from exc
        log_event("provider_call_completed", component="provider", status="passed")
        return normalized


__all__ = [
    "ANTHROPIC_MESSAGES_PATH",
    "ANTHROPIC_MODELS_PATH",
    "ANTHROPIC_VERSION",
    "AnthropicCompatibleProvider",
    "inspect_anthropic_endpoint",
    "parse_anthropic_models_payload",
    "normalize_anthropic_response",
    "to_anthropic_request_payload",
]
