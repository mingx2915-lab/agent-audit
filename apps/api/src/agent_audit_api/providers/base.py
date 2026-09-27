"""Provider protocol and vendor-neutral normalized response types."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


Message = Mapping[str, Any]

# ``Message`` is kept as the public input type used by the existing target
# code.  The adapter boundary below gives the four providers one strict
# canonical vocabulary without forcing the target to know a wire protocol.
OpenAIMessage = dict[str, object]
OpenAITool = dict[str, object]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class ProviderUsage:
    """Token usage reported by any configured model provider."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class ProviderUsageSnapshot:
    """Position in a provider call stream used for benchmark deltas."""

    call_count: int
    usage_count: int


@dataclass(frozen=True)
class LLMResponse:
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    usage: ProviderUsage | None = None


class LLMProvider(Protocol):
    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        """Return one normalized model response, optionally containing Tool Calls."""


class ProviderUsageTracker:
    """Count actual provider adapter calls and preserve reported usage."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
        self.call_count = 0
        self.usages: list[ProviderUsage | None] = []

    def snapshot(self) -> ProviderUsageSnapshot:
        """Return a stable cursor without exposing the wrapped provider."""

        return ProviderUsageSnapshot(
            call_count=self.call_count,
            usage_count=len(self.usages),
        )

    def calls_since(self, snapshot: ProviderUsageSnapshot) -> int:
        """Return calls made after ``snapshot``."""

        self._validate_snapshot(snapshot)
        return self.call_count - snapshot.call_count

    def usages_since(
        self,
        snapshot: ProviderUsageSnapshot,
    ) -> tuple[ProviderUsage | None, ...]:
        """Return normalized usage values recorded after ``snapshot``."""

        self._validate_snapshot(snapshot)
        return tuple(self.usages[snapshot.usage_count :])

    def delta(
        self,
        snapshot: ProviderUsageSnapshot,
    ) -> tuple[int, tuple[ProviderUsage | None, ...]]:
        """Return call count and usage values recorded after ``snapshot``."""

        return self.calls_since(snapshot), self.usages_since(snapshot)

    def _validate_snapshot(self, snapshot: ProviderUsageSnapshot) -> None:
        if not isinstance(snapshot, ProviderUsageSnapshot):
            raise TypeError("snapshot must be a ProviderUsageSnapshot")
        if snapshot.call_count < 0 or snapshot.usage_count < 0:
            raise ValueError("snapshot positions must not be negative")
        if snapshot.call_count > self.call_count or snapshot.usage_count > len(self.usages):
            raise ValueError("snapshot is ahead of the provider tracker")

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        try:
            response = await self._provider.complete(messages, tools=tools)
        except Exception:
            self.usages.append(None)
            raise
        self.usages.append(response.usage if isinstance(response, LLMResponse) else None)
        return response


class ProviderError(RuntimeError):
    """Base class for safe, user-facing provider failures."""


class ProviderConfigurationError(ProviderError):
    """Raised when the required provider environment is not configured."""


class ProviderUnavailableError(ProviderError):
    """Raised when the provider cannot be reached."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        # A response status can be known even when the adapter does not expose
        # the provider response body.  Keeping it on the typed error lets the
        # API boundary render a safe diagnostic without parsing exception text.
        self.status_code = status_code


class ProviderResponseError(ProviderError):
    """Raised when a provider response cannot be normalized safely."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        # Inspection/readiness may reject a response object after observing an
        # HTTP status.  Carry that typed fact separately from the diagnostic
        # message; response bodies are intentionally never retained.
        self.status_code = status_code


def _strict_tool_arguments(value: Any, *, context: str) -> dict[str, object]:
    """Parse one canonical function argument object without repairing it."""

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderResponseError(f"{context} arguments are invalid") from exc
    if not isinstance(value, Mapping):
        raise ProviderResponseError(f"{context} arguments are invalid")
    return dict(value)


def normalize_openai_messages(
    messages: Sequence[Message],
) -> list[OpenAIMessage]:
    """Normalize the target's OpenAI-shaped messages for adapter conversion.

    The target currently emits ``assistant.tool_calls`` and ``role=tool``.
    Those fields are deliberately validated here so Anthropic and the fixed
    enterprise bridge cannot silently pass an unsupported shape through.
    """

    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        raise ProviderResponseError("provider messages must be an array")
    normalized: list[OpenAIMessage] = []
    for index, raw_message in enumerate(messages):
        if not isinstance(raw_message, Mapping):
            raise ProviderResponseError(f"provider message at index {index} is invalid")
        role = raw_message.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ProviderResponseError(f"provider message at index {index} has an invalid role")

        if role in {"system", "user"}:
            content = raw_message.get("content")
            if not isinstance(content, str):
                raise ProviderResponseError(
                    f"provider {role} message at index {index} has invalid content"
                )
            normalized.append({"role": role, "content": content})
            continue

        if role == "tool":
            tool_call_id = raw_message.get("tool_call_id")
            content = raw_message.get("content")
            if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                raise ProviderResponseError(
                    f"provider tool message at index {index} has invalid tool_call_id"
                )
            if not isinstance(content, str):
                raise ProviderResponseError(
                    f"provider tool message at index {index} has invalid content"
                )
            canonical_tool: OpenAIMessage = {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content,
            }
            name = raw_message.get("name")
            if name is not None:
                if not isinstance(name, str) or not name.strip():
                    raise ProviderResponseError(
                        f"provider tool message at index {index} has invalid name"
                    )
                canonical_tool["name"] = name
            normalized.append(canonical_tool)
            continue

        # Assistant messages may contain text, Tool Calls, or both.  A null
        # content is valid only when at least one Tool Call is present.
        content = raw_message.get("content")
        if content is not None and not isinstance(content, str):
            raise ProviderResponseError(
                f"provider assistant message at index {index} has invalid content"
            )
        raw_tool_calls = raw_message.get("tool_calls", [])
        if not isinstance(raw_tool_calls, Sequence) or isinstance(
            raw_tool_calls,
            (str, bytes),
        ):
            raise ProviderResponseError(
                f"provider assistant message at index {index} has invalid tool_calls"
            )
        tool_calls: list[dict[str, object]] = []
        for call_index, raw_call in enumerate(raw_tool_calls):
            if not isinstance(raw_call, Mapping):
                raise ProviderResponseError(
                    f"provider tool call at index {call_index} is invalid"
                )
            call_id = raw_call.get("id")
            function = raw_call.get("function")
            if not isinstance(call_id, str) or not call_id.strip() or not isinstance(
                function,
                Mapping,
            ):
                raise ProviderResponseError("provider tool call is invalid")
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ProviderResponseError("provider tool call name is invalid")
            arguments = _strict_tool_arguments(
                function.get("arguments"),
                context="provider tool call",
            )
            tool_calls.append(
                {
                    "id": call_id,
                    "name": name,
                    "arguments": arguments,
                }
            )
        if content is None and not tool_calls:
            raise ProviderResponseError(
                f"provider assistant message at index {index} is empty"
            )
        canonical_assistant: OpenAIMessage = {
            "role": "assistant",
            "content": content,
        }
        if tool_calls:
            canonical_assistant["tool_calls"] = tool_calls
        normalized.append(canonical_assistant)
    return normalized


def normalize_openai_tools(
    tools: Sequence[Mapping[str, object]] | None,
) -> list[OpenAITool]:
    """Normalize OpenAI function definitions to one fixed tool DTO."""

    if tools is None:
        return []
    if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
        raise ProviderResponseError("provider tools must be an array")
    normalized: list[OpenAITool] = []
    for index, raw_tool in enumerate(tools):
        if not isinstance(raw_tool, Mapping) or raw_tool.get("type") != "function":
            raise ProviderResponseError(f"provider tool at index {index} is invalid")
        function = raw_tool.get("function")
        if not isinstance(function, Mapping):
            raise ProviderResponseError(f"provider tool at index {index} is invalid")
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ProviderResponseError(f"provider tool at index {index} has invalid name")
        description = function.get("description")
        if description is not None and not isinstance(description, str):
            raise ProviderResponseError(
                f"provider tool at index {index} has invalid description"
            )
        input_schema = function.get("parameters")
        if not isinstance(input_schema, Mapping):
            raise ProviderResponseError(
                f"provider tool at index {index} has invalid parameters"
            )
        canonical: OpenAITool = {
            "name": name.strip(),
            "input_schema": dict(input_schema),
        }
        if description is not None:
            canonical["description"] = description
        normalized.append(canonical)
    return normalized


def normalize_bridge_response(raw_response: Any) -> LLMResponse:
    """Normalize a fixed bridge response with strict content/tool/usage types."""

    if not isinstance(raw_response, Mapping):
        raise ProviderResponseError("canonical provider response must be an object")
    if "content" not in raw_response:
        raise ProviderResponseError("canonical provider response content is missing")
    unknown_response_fields = set(raw_response) - {"content", "toolCalls", "usage"}
    if unknown_response_fields:
        raise ProviderResponseError("canonical provider response contains unknown fields")
    raw_content = raw_response.get("content")
    if raw_content is not None and not isinstance(raw_content, str):
        raise ProviderResponseError("canonical provider response content is invalid")

    # The bridge contract is deliberately camelCase.  Internal snake_case
    # input is converted by the bridge client before crossing this boundary;
    # accepting both shapes here would make the wire contract ambiguous.
    raw_tool_calls = raw_response.get("toolCalls", [])
    if not isinstance(raw_tool_calls, Sequence) or isinstance(
        raw_tool_calls,
        (str, bytes),
    ):
        raise ProviderResponseError("canonical provider toolCalls are invalid")
    tool_calls: list[ToolCall] = []
    for index, raw_call in enumerate(raw_tool_calls):
        if not isinstance(raw_call, Mapping):
            raise ProviderResponseError(f"canonical provider tool call at index {index} is invalid")
        if set(raw_call) - {"id", "name", "arguments"}:
            raise ProviderResponseError(
                f"canonical provider tool call at index {index} contains unknown fields"
            )
        call_id = raw_call.get("id")
        name = raw_call.get("name")
        if not isinstance(call_id, str) or not call_id.strip():
            raise ProviderResponseError("canonical provider tool call id is invalid")
        if not isinstance(name, str) or not name.strip():
            raise ProviderResponseError("canonical provider tool call name is invalid")
        arguments = raw_call.get("arguments")
        if not isinstance(arguments, Mapping):
            raise ProviderResponseError("canonical provider tool call arguments are invalid")
        tool_calls.append(
            ToolCall(id=call_id, name=name, arguments=dict(arguments))
        )

    raw_usage = raw_response.get("usage")
    usage: ProviderUsage | None
    if raw_usage is None:
        usage = None
    else:
        if not isinstance(raw_usage, Mapping):
            raise ProviderResponseError("canonical provider usage is invalid")
        if set(raw_usage) - {"inputTokens", "outputTokens", "totalTokens"}:
            raise ProviderResponseError("canonical provider usage contains unknown fields")
        input_tokens = raw_usage.get("inputTokens")
        output_tokens = raw_usage.get("outputTokens")
        total_tokens = raw_usage.get("totalTokens")
        if (
            type(input_tokens) is not int
            or input_tokens < 0
            or type(output_tokens) is not int
            or output_tokens < 0
            or type(total_tokens) is not int
            or total_tokens < 0
            or total_tokens != input_tokens + output_tokens
        ):
            raise ProviderResponseError("canonical provider usage is invalid")
        usage = ProviderUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    normalized_content = raw_content.strip() if isinstance(raw_content, str) else None
    if not normalized_content and not tool_calls:
        raise ProviderResponseError("canonical provider response content is empty")
    return LLMResponse(
        content=normalized_content,
        tool_calls=tuple(tool_calls),
        usage=usage,
    )




def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def normalize_openai_chat_response(raw_response: Any) -> LLMResponse:
    """Normalize one OpenAI-compatible Chat Completions response."""

    choices = _field(raw_response, "choices")
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
        raise ProviderResponseError("provider response has no choices")
    message = _field(choices[0], "message")
    if message is None:
        raise ProviderResponseError("provider response has no message")

    raw_content = _field(message, "content")
    if raw_content is not None and not isinstance(raw_content, str):
        raise ProviderResponseError("provider response content is invalid")

    raw_tool_calls = _field(message, "tool_calls", []) or []
    if not isinstance(raw_tool_calls, Sequence) or isinstance(raw_tool_calls, (str, bytes)):
        raise ProviderResponseError("provider tool calls are invalid")
    tool_calls: list[ToolCall] = []
    for raw_tool_call in raw_tool_calls:
        call_id = _field(raw_tool_call, "id")
        function = _field(raw_tool_call, "function")
        name = _field(function, "name") if function is not None else None
        raw_arguments = _field(function, "arguments") if function is not None else None
        if not isinstance(call_id, str) or not call_id.strip():
            raise ProviderResponseError("provider tool call id is invalid")
        if not isinstance(name, str) or not name.strip():
            raise ProviderResponseError("provider tool call name is invalid")
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise ProviderResponseError("provider tool call arguments are invalid") from exc
        else:
            arguments = raw_arguments
        if not isinstance(arguments, Mapping):
            raise ProviderResponseError("provider tool call arguments are invalid")
        tool_calls.append(
            ToolCall(id=call_id, name=name, arguments=dict(arguments))
        )

    normalized_content = raw_content.strip() if isinstance(raw_content, str) else None
    if not normalized_content and not tool_calls:
        raise ProviderResponseError("provider response content is empty")
    return LLMResponse(
        content=normalized_content,
        tool_calls=tuple(tool_calls),
        usage=_normalize_usage(_field(raw_response, "usage")),
    )


def _normalize_usage(raw_usage: Any) -> ProviderUsage | None:
    """Normalize complete OpenAI usage only; incomplete usage stays unknown."""

    if raw_usage is None:
        return None
    input_tokens = _field(raw_usage, "prompt_tokens", _field(raw_usage, "input_tokens"))
    output_tokens = _field(
        raw_usage,
        "completion_tokens",
        _field(raw_usage, "output_tokens"),
    )
    total_tokens = _field(raw_usage, "total_tokens")
    if (
        type(input_tokens) is not int
        or input_tokens < 0
        or type(output_tokens) is not int
        or output_tokens < 0
        or type(total_tokens) is not int
        or total_tokens < 0
    ):
        return None
    return ProviderUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
