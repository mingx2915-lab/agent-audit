"""Fixed ``agent_audit_adapter.v1`` enterprise bridge Provider.

The bridge is intentionally small and versioned.  Enterprise-specific model
protocols stay outside AgentAudit; the bridge exposes a fixed capability
manifest, a standard model listing, and a canonical completion endpoint.  No
user supplied templates, scripts, headers, or JSONPath expressions are
accepted here.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..diagnostic_logging import log_event
from ..provider_diagnostics import provider_error_diagnostic
from pydantic import (
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from ..schemas import CamelModel
from .base import (
    LLMResponse,
    Message,
    ProviderConfigurationError,
    ProviderError,
    ProviderResponseError,
    ProviderUnavailableError,
    ToolCall,
    normalize_bridge_response,
    normalize_openai_messages,
    normalize_openai_tools,
)
from .openai_compatible import _normalize_base_url


AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION = "agent_audit_adapter.v1"
AGENT_AUDIT_ADAPTER_MANIFEST_PATH = "/manifest"
AGENT_AUDIT_ADAPTER_MODELS_PATH = "/models"
AGENT_AUDIT_ADAPTER_COMPLETIONS_PATH = "/completions"
AGENT_AUDIT_ADAPTER_MAX_TOKENS = 4096


class _WireModel(CamelModel):
    """CamelCase-only wire DTO base for the fixed bridge protocol."""

    model_config = ConfigDict(
        alias_generator=lambda value: value.split("_")[0]
        + "".join(part[:1].upper() + part[1:] for part in value.split("_")[1:]),
        extra="forbid",
        populate_by_name=False,
        validate_by_alias=True,
        validate_by_name=False,
    )


class AgentAuditAdapterCapabilities(_WireModel):
    """Strict capability flags required by the bridge manifest."""

    text: StrictBool
    tool_calling: StrictBool
    structured_output: StrictBool
    usage: StrictBool


# Public name matching the cross-platform Contracts terminology.
ProviderCapabilityManifest = AgentAuditAdapterCapabilities


class AgentAuditAdapterManifest(_WireModel):
    """The only manifest accepted by the v1 bridge."""

    protocol: Literal["agent_audit_adapter"]
    protocol_version: Literal[AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION]
    capabilities: AgentAuditAdapterCapabilities


class CanonicalToolCall(_WireModel):
    """Canonical assistant Tool Call in the bridge wire contract."""

    id: StrictStr
    name: StrictStr
    arguments: dict[str, Any]

    @field_validator("id", "name")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("canonical Tool Call text must not be blank")
        return value


class CanonicalMessage(_WireModel):
    """Canonical message accepted by ``/v1/completions``."""

    role: Literal["system", "user", "assistant", "tool"]
    content: StrictStr | None
    # A missing optional field is represented by a default, but an explicit
    # JSON null is not part of the wire contract (``content`` is the only
    # nullable message field).
    tool_call_id: StrictStr = None  # type: ignore[assignment]
    tool_calls: list[CanonicalToolCall] = None  # type: ignore[assignment]
    name: StrictStr = None  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_shape(self) -> "CanonicalMessage":
        if self.role in {"system", "user"}:
            if (
                self.content is None
                or self.tool_call_id is not None
                or self.tool_calls is not None
                or self.name is not None
            ):
                raise ValueError("canonical user/system message shape is invalid")
        elif self.role == "assistant":
            if self.tool_call_id is not None or self.name is not None:
                raise ValueError("canonical assistant tool_call_id is invalid")
            if self.content is None and not self.tool_calls:
                raise ValueError("canonical assistant message is empty")
        else:
            if (
                self.content is None
                or self.tool_call_id is None
                or self.tool_calls is not None
            ):
                raise ValueError("canonical tool message shape is invalid")
        return self


class CanonicalToolDefinition(_WireModel):
    """Canonical function definition accepted by the bridge."""

    name: StrictStr
    description: StrictStr = None  # type: ignore[assignment]
    input_schema: dict[str, Any]

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("canonical tool name must not be blank")
        return value


class CanonicalUsage(_WireModel):
    """Canonical complete token usage."""

    input_tokens: StrictInt = Field(ge=0)
    output_tokens: StrictInt = Field(ge=0)
    total_tokens: StrictInt = Field(ge=0)

    @model_validator(mode="after")
    def total_must_match(self) -> "CanonicalUsage":
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("canonical usage total does not match input/output tokens")
        return self


class CanonicalCompletionRequest(_WireModel):
    """Strict request schema for ``agent_audit_adapter.v1`` completions."""

    protocol_version: Literal[AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION]
    model: StrictStr
    messages: list[CanonicalMessage]
    tools: list[CanonicalToolDefinition] = None  # type: ignore[assignment]
    max_tokens: StrictInt = Field(gt=0)

    @field_validator("model")
    @classmethod
    def model_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("canonical model must not be blank")
        return value

    @field_validator("messages")
    @classmethod
    def messages_must_not_be_empty(cls, value: list[CanonicalMessage]) -> list[CanonicalMessage]:
        if not value:
            raise ValueError("canonical messages must not be empty")
        return value


class CanonicalCompletionResponse(_WireModel):
    """Strict response schema for ``agent_audit_adapter.v1`` completions."""

    content: StrictStr | None
    tool_calls: list[CanonicalToolCall] = Field(default_factory=list)
    usage: CanonicalUsage | None = None

    @model_validator(mode="after")
    def response_must_contain_content_or_tool_call(self) -> "CanonicalCompletionResponse":
        if (self.content is None or not self.content.strip()) and not self.tool_calls:
            raise ValueError("canonical completion response is empty")
        return self


class AgentAuditAdapterInspectionError(ValueError):
    """Raised for a malformed or unsupported bridge manifest."""

    provider_response_invalid = True

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler())


def parse_agent_audit_adapter_manifest(payload: object) -> AgentAuditAdapterManifest:
    """Validate the fixed v1 manifest without guessing a protocol/version."""

    try:
        return AgentAuditAdapterManifest.model_validate(payload)
    except (TypeError, ValueError) as exc:
        raise AgentAuditAdapterInspectionError(
            "AgentAudit adapter manifest is invalid or unsupported"
        ) from exc


def _response_status(response: object) -> int | None:
    status = getattr(response, "status", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return int(status)
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return int(status)
    return None


def _read_json(response: object) -> object:
    read = getattr(response, "read", None)
    if not callable(read):
        raise AgentAuditAdapterInspectionError("AgentAudit adapter response body is unreadable")
    try:
        raw = read()
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
        raise AgentAuditAdapterInspectionError(
            "AgentAudit adapter response is not valid JSON"
        ) from exc


def _adapter_headers(
    auth_mode: Literal["none", "bearer", "x_api_key"] | None,
    credential: str | None,
) -> dict[str, str]:
    # Reuse the F-031 validator/header semantics.  It never includes a
    # credential in an error string.
    from ..provider_setup import _auth_headers

    return {
        **_auth_headers(auth_mode, credential),
        "Content-Type": "application/json",
    }


def _inspection_request(
    *,
    url: str,
    headers: Mapping[str, str],
    opener: Callable[..., object],
) -> object:
    request = Request(url, method="GET", headers=dict(headers))
    return opener(request, timeout=5)


def inspect_agent_audit_adapter_endpoint(
    *,
    base_url: str,
    auth_mode: Literal["none", "bearer", "x_api_key"] | None = None,
    credential: str | None = None,
    opener: Callable[..., object] | None = None,
) -> Any:
    """Inspect only the fixed manifest and models paths of one explicit origin."""

    # Imported lazily because provider_setup itself is imported while the
    # providers package is initialized by the API's evaluation modules.
    from ..provider_setup import (
        ProviderInspectionError,
        ProviderModelCandidate,
        ProtocolInspectionResult,
        normalize_provider_base_url,
        parse_openai_models_payload,
    )

    normalized = normalize_provider_base_url(base_url)
    root = normalized.rstrip("/")
    try:
        headers = _adapter_headers(auth_mode, credential)
    except ProviderConfigurationError as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="manifest",
                provider_kind="agent_audit_adapter",
            ),
            models_enumerated=False,
        )
    if opener is None:
        # Reuse the setup module's patched no-redirect opener so inspection
        # tests and all provider kinds share the same one-request boundary.
        from ..provider_setup import _NO_REDIRECT_OPENER

        open_url = _NO_REDIRECT_OPENER.open
    else:
        open_url = opener
    manifest_response: object | None = None
    manifest: AgentAuditAdapterManifest | None = None
    manifest_url = f"{root}{AGENT_AUDIT_ADAPTER_MANIFEST_PATH}"
    try:
        manifest_response = _inspection_request(
            url=manifest_url,
            headers=headers,
            opener=open_url,
        )
        status = _response_status(manifest_response)
        if status is not None and not 200 <= status < 300:
            raise AgentAuditAdapterInspectionError(
                f"AgentAudit adapter manifest endpoint returned HTTP {status}",
                status_code=status,
            )
        manifest = parse_agent_audit_adapter_manifest(_read_json(manifest_response))
    except HTTPError as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="manifest",
                provider_kind="agent_audit_adapter",
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
                stage="manifest",
                provider_kind="agent_audit_adapter",
            ),
            models_enumerated=False,
        )
    except (AgentAuditAdapterInspectionError, TypeError, ValueError, UnicodeError) as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="manifest",
                provider_kind="agent_audit_adapter",
            ),
            models_enumerated=False,
        )
    finally:
        close = getattr(manifest_response, "close", None)
        if callable(close):
            close()

    assert manifest is not None
    capabilities_payload = manifest.capabilities.model_dump(
        mode="json",
        by_alias=True,
    )
    manifest_payload = manifest.model_dump(
        mode="json",
        by_alias=True,
    )
    models_response: object | None = None
    models_url = f"{root}{AGENT_AUDIT_ADAPTER_MODELS_PATH}"
    try:
        models_response = _inspection_request(
            url=models_url,
            headers=headers,
            opener=open_url,
        )
        status = _response_status(models_response)
        if status is not None and not 200 <= status < 300:
            raise AgentAuditAdapterInspectionError(
                f"AgentAudit adapter models endpoint returned HTTP {status}",
                status_code=status,
            )
        models = parse_openai_models_payload(_read_json(models_response))
    except HTTPError as exc:
        return ProtocolInspectionResult(
            status="available",
            protocol="agent_audit_adapter",
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="agent_audit_adapter",
            ),
            models_enumerated=False,
            protocol_version=manifest.protocol_version,
            capabilities=capabilities_payload,
            manifest=manifest_payload,
        )
    except (OSError, URLError, TimeoutError) as exc:
        return ProtocolInspectionResult(
            status="available",
            protocol="agent_audit_adapter",
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="agent_audit_adapter",
            ),
            models_enumerated=False,
            protocol_version=manifest.protocol_version,
            capabilities=capabilities_payload,
            manifest=manifest_payload,
        )
    except (ProviderInspectionError, AgentAuditAdapterInspectionError, TypeError, ValueError, UnicodeError) as exc:
        return ProtocolInspectionResult(
            status="available",
            protocol="agent_audit_adapter",
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="agent_audit_adapter",
            ),
            models_enumerated=False,
            protocol_version=manifest.protocol_version,
            capabilities=capabilities_payload,
            manifest=manifest_payload,
        )
    finally:
        close = getattr(models_response, "close", None)
        if callable(close):
            close()

    return ProtocolInspectionResult(
        status="available",
        protocol="agent_audit_adapter",
        base_url=normalized,
        models=models,
        diagnostic=None,
        models_enumerated=True,
        protocol_version=manifest.protocol_version,
        capabilities=capabilities_payload,
        manifest=manifest_payload,
    )


def _canonical_request_payload(
    messages: Sequence[Message],
    tools: Sequence[Mapping[str, object]] | None,
    *,
    model: str,
    max_tokens: int,
) -> dict[str, object]:
    """Convert internal OpenAI-shaped input into the fixed camelCase DTO."""

    canonical_messages = normalize_openai_messages(messages)
    output_messages: list[dict[str, object]] = []
    for message in canonical_messages:
        output: dict[str, object] = {
            "role": message["role"],
            "content": message["content"],
        }
        if "tool_call_id" in message:
            output["toolCallId"] = message["tool_call_id"]
        if "name" in message:
            output["name"] = message["name"]
        raw_calls = message.get("tool_calls")
        if raw_calls:
            output["toolCalls"] = [
                {
                    "id": call["id"],
                    "name": call["name"],
                    "arguments": call["arguments"],
                }
                for call in raw_calls
            ]
        output_messages.append(output)

    output_tools: list[dict[str, object]] | None = None
    if tools is not None:
        output_tools = []
        for tool in normalize_openai_tools(tools):
            converted: dict[str, object] = {
                "name": tool["name"],
                "inputSchema": tool["input_schema"],
            }
            if "description" in tool:
                converted["description"] = tool["description"]
            output_tools.append(converted)
    request_payload: dict[str, object] = {
        "protocolVersion": AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION,
        "model": model,
        "messages": output_messages,
        "maxTokens": max_tokens,
    }
    if output_tools is not None:
        request_payload["tools"] = output_tools
    try:
        validated = CanonicalCompletionRequest.model_validate(request_payload)
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("canonical completion request is invalid") from exc

    # ``content`` is required by the cross-platform bridge DTO even when an
    # assistant message consists solely of Tool Calls.  A blanket
    # ``exclude_none`` dump would silently turn that required ``null`` into an
    # absent field and drift from the frozen wire contract.  Strip only the
    # genuinely optional null fields explicitly.
    dumped = validated.model_dump(mode="json", by_alias=True, exclude_none=False)
    for message in dumped["messages"]:
        if not isinstance(message, dict):  # pragma: no cover - Pydantic invariant
            raise ProviderResponseError("canonical completion request is invalid")
        for optional_field in ("toolCallId", "toolCalls", "name"):
            if message.get(optional_field) is None:
                message.pop(optional_field, None)
    tools_payload = dumped.get("tools")
    if tools_payload is None:
        dumped.pop("tools", None)
    elif isinstance(tools_payload, list):
        for tool in tools_payload:
            if isinstance(tool, dict) and tool.get("description") is None:
                tool.pop("description", None)
    return dumped


async def _maybe_await(value: object) -> object:
    if inspect.isawaitable(value):
        return await value
    return value


async def _response_json(response: object) -> object:
    if isinstance(response, Mapping):
        return response
    json_method = getattr(response, "json", None)
    if not callable(json_method):
        raise ProviderResponseError("AgentAudit adapter response body is unreadable")
    try:
        return await _maybe_await(json_method())
    except Exception as exc:
        raise ProviderResponseError("AgentAudit adapter response is not valid JSON") from exc


class AgentAuditAdapterProvider:
    """Call one explicitly configured ``agent_audit_adapter.v1`` bridge."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        base_url: str,
        model: str,
        auth_mode: Literal["none", "bearer", "x_api_key"] | None = None,
        credential: str | None = None,
        api_key: str | None = None,
        max_tokens: int = AGENT_AUDIT_ADAPTER_MAX_TOKENS,
    ) -> None:
        self._client = client
        self.base_url = _normalize_base_url(base_url)
        self.model = model.strip() if isinstance(model, str) else model
        resolved_auth_mode = auth_mode or "none"
        if resolved_auth_mode not in {"none", "bearer", "x_api_key"}:
            raise ProviderConfigurationError("unsupported Provider authentication mode")
        self.auth_mode = resolved_auth_mode
        self._credential = credential if credential is not None else api_key
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ProviderConfigurationError("AgentAudit adapter max_tokens must be positive")
        self.max_tokens = max_tokens

    @property
    def credential_configured(self) -> bool:
        return self.auth_mode in {"bearer", "x_api_key"} and bool(self._credential)

    def _headers(self) -> dict[str, str]:
        try:
            return _adapter_headers(self.auth_mode, self._credential)
        except ProviderConfigurationError:
            raise

    async def _post(
        self,
        url: str,
        payload: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> object:
        if self._client is not None:
            post = getattr(self._client, "post", None)
            if not callable(post):
                raise ProviderConfigurationError("AgentAudit adapter client does not support POST")
            try:
                return await _maybe_await(
                    post(url, headers=dict(headers), json=dict(payload), timeout=30)
                )
            except ProviderError:
                raise
            except Exception as exc:
                raise ProviderUnavailableError("AgentAudit adapter request failed") from exc
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
            raise ProviderUnavailableError("AgentAudit adapter request failed") from exc

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> LLMResponse:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ProviderConfigurationError("AgentAudit adapter model is not configured")
        payload = _canonical_request_payload(
            messages,
            tools,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        url = f"{self.base_url.rstrip('/')}{AGENT_AUDIT_ADAPTER_COMPLETIONS_PATH}"
        log_event("provider_call_started", component="provider", status="started")
        try:
            response = await self._post(url, payload, self._headers())
            status = _response_status(response)
            if status is not None and not 200 <= status < 300:
                raise ProviderUnavailableError(
                    f"AgentAudit adapter request failed with HTTP {status}",
                    status_code=status,
                )
            raw_payload = await _response_json(response)
            validated = CanonicalCompletionResponse.model_validate(raw_payload)
            normalized = normalize_bridge_response(
                validated.model_dump(mode="json", by_alias=True, exclude_none=False)
            )
        except ProviderError as exc:
            log_event(
                "provider_call_failed",
                component="provider",
                status="failed",
                error_type=type(exc).__name__,
                level="error",
            )
            raise
        except (TypeError, ValueError) as exc:
            log_event(
                "provider_call_failed",
                component="provider",
                status="failed",
                error_type=type(exc).__name__,
                level="error",
            )
            raise ProviderResponseError("AgentAudit adapter completion response is invalid") from exc
        except Exception as exc:
            log_event(
                "provider_call_failed",
                component="provider",
                status="failed",
                error_type=type(exc).__name__,
                level="error",
            )
            # Keep the transport boundary deterministic even if a caller
            # replaces the internal HTTP seam with a test transport.
            raise ProviderUnavailableError("AgentAudit adapter request failed") from exc
        log_event("provider_call_completed", component="provider", status="passed")
        return normalized


__all__ = [
    "AGENT_AUDIT_ADAPTER_COMPLETIONS_PATH",
    "AGENT_AUDIT_ADAPTER_MANIFEST_PATH",
    "AGENT_AUDIT_ADAPTER_MAX_TOKENS",
    "AGENT_AUDIT_ADAPTER_MODELS_PATH",
    "AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION",
    "AgentAuditAdapterCapabilities",
    "AgentAuditAdapterInspectionError",
    "AgentAuditAdapterManifest",
    "AgentAuditAdapterProvider",
    "CanonicalCompletionRequest",
    "CanonicalCompletionResponse",
    "CanonicalMessage",
    "CanonicalToolCall",
    "CanonicalToolDefinition",
    "CanonicalUsage",
    "ProviderCapabilityManifest",
    "inspect_agent_audit_adapter_endpoint",
    "parse_agent_audit_adapter_manifest",
]
