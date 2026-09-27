"""First-run Provider setup, discovery, and non-secret configuration storage.

The setup surface deliberately has a smaller contract than the existing
runtime Provider factory.  It accepts one explicitly supplied Provider
endpoint and model, stores only those non-secret values, and keeps inspection
and candidate readiness side-effect free with respect to the active runtime.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import Field, field_validator, model_validator

from .history import AuditRuntimeSnapshot
from .provider_diagnostics import provider_error_diagnostic
from .providers.base import ProviderConfigurationError
from .schemas import CamelModel


PROVIDER_SETTINGS_FILENAME = "provider-settings.json"
OLLAMA_DISCOVERY_ENDPOINT = "http://127.0.0.1:11434"
OLLAMA_DISCOVERY_URL = f"{OLLAMA_DISCOVERY_ENDPOINT}/api/tags"
PROVIDER_CREDENTIAL_ENV = "AGENT_AUDIT_PROVIDER_API_KEY"


class _NoRedirectHandler(HTTPRedirectHandler):
    """Keep fixed loopback discovery from following a server redirect."""

    def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler())


class ProviderConnectionSettings(CamelModel):
    """Public, non-secret settings for one confirmed Runtime connection.

    ``auth_mode`` defaults to ``none`` for old F-027 settings files which
    predate the field.  It is never a credential and is always emitted as a
    stable public field on newly serialized DTOs.
    """

    kind: Literal[
        "ollama",
        "openai_compatible",
        "anthropic_compatible",
        "agent_audit_adapter",
    ]
    base_url: str
    model: str
    auth_mode: Literal["none", "bearer", "x_api_key"] = "none"

    @model_validator(mode="after")
    def validate_auth_matrix(self) -> "ProviderConnectionSettings":
        if self.kind in {"ollama", "openai_compatible"} and self.auth_mode == "x_api_key":
            raise ValueError(
                "Ollama 和 OpenAI-compatible 连接不支持 x-api-key，请改用无认证或 Bearer。"
            )
        return self

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return normalize_provider_base_url(value)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("模型名称不能为空")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("模型名称不能包含控制字符")
        return value.strip()


class OllamaModelCandidate(CamelModel):
    """One model returned by Ollama's ``/api/tags`` endpoint."""

    name: str
    size_bytes: int | None = None
    modified_at: str | None = None


class OllamaDiscoveryResult(CamelModel):
    """Structured result of the fixed loopback Ollama discovery request."""

    endpoint: str
    status: Literal["available", "unavailable"]
    models: list[OllamaModelCandidate]
    diagnostic: str | None


class ProviderModelCandidate(CamelModel):
    """One model returned by an OpenAI-compatible ``/v1/models`` endpoint."""

    id: str
    object: Literal["model"] | None = None
    created: int | None = Field(default=None, ge=0)
    owned_by: str | None = None


class ProtocolInspectionResult(CamelModel):
    """Non-secret protocol and model enumeration result for one origin."""

    status: Literal["available", "unavailable"]
    protocol: Literal[
        "ollama",
        "openai_compatible",
        "anthropic_compatible",
        "agent_audit_adapter",
    ] | None
    base_url: str
    models: list[ProviderModelCandidate]
    diagnostic: str | None
    models_enumerated: bool
    # These fields are omitted for the historical Ollama/OpenAI responses
    # when absent, preserving the F-031 wire shape.  Adapter inspection adds
    # them only after a valid fixed v1 manifest is parsed.
    protocol_version: Literal["agent_audit_adapter.v1"] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    capabilities: dict[str, bool] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    manifest: dict[str, object] | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class OllamaDiscoveryRequest(CamelModel):
    """Strict empty body for the fixed local Ollama discovery route."""


class ProviderSetupState(CamelModel):
    """Current confirmed setup plus the normal runtime metadata snapshot."""

    configured: bool
    settings: ProviderConnectionSettings | None
    credential_configured: bool = False
    runtime_snapshot: AuditRuntimeSnapshot


class ProviderCandidateReadinessRequest(CamelModel):
    """Request for one explicit, non-persistent candidate readiness run."""

    settings: ProviderConnectionSettings
    # Transient bearer value supplied for this check only.  It is never part of
    # ProviderConnectionSettings and is never returned or persisted.
    credential: str | None = None

    @field_validator("credential")
    @classmethod
    def validate_credential(cls, value: str | None) -> str | None:
        return _validate_transient_credential(value)


class SaveProviderSettingsRequest(CamelModel):
    """Request for the explicit user confirmation that persists settings."""

    settings: ProviderConnectionSettings
    # Transient bearer value supplied for this process only.  Desktop startup
    # injects the same value through PROVIDER_CREDENTIAL_ENV instead.
    credential: str | None = None

    @field_validator("credential")
    @classmethod
    def validate_credential(cls, value: str | None) -> str | None:
        return _validate_transient_credential(value)


class ProviderInspectionRequest(CamelModel):
    """Inspect one explicitly supplied origin without changing active state."""

    kind: Literal[
        "ollama",
        "openai_compatible",
        "anthropic_compatible",
        "agent_audit_adapter",
    ]
    base_url: str
    auth_mode: Literal["none", "bearer", "x_api_key"]
    credential: str | None = None

    @model_validator(mode="after")
    def validate_auth_matrix(self) -> "ProviderInspectionRequest":
        if self.kind in {"ollama", "openai_compatible"} and self.auth_mode == "x_api_key":
            raise ValueError(
                "Ollama 和 OpenAI-compatible 连接不支持 x-api-key，请改用无认证或 Bearer。"
            )
        return self

    @field_validator("credential")
    @classmethod
    def validate_credential(cls, value: str | None) -> str | None:
        return _validate_transient_credential(value)


class ProviderSettingsError(ProviderConfigurationError):
    """Base class for readable local Provider settings failures."""


class ProviderSettingsReadError(ProviderSettingsError):
    """Raised when an existing settings file cannot be read or validated."""


class ProviderSettingsWriteError(ProviderSettingsError):
    """Raised when confirmed settings cannot be persisted."""


class OllamaDiscoveryError(ValueError):
    """Raised for an invalid Ollama ``/api/tags`` response."""

    provider_response_invalid = True

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_provider_base_url(value: str) -> str:
    """Validate and canonicalize one user-supplied Runtime base URL.

    Only ``http`` and ``https`` are accepted.  Credentials, query strings and
    fragments are forbidden because this setup file is intentionally not a
    Secret store.  A service root is represented as the OpenAI-compatible
    ``/v1`` base; an existing path ending in ``/v1`` is preserved.  No request
    is made while normalizing the value.
    """

    from urllib.parse import urlsplit, urlunsplit

    if not isinstance(value, str) or not value.strip():
        raise ValueError("AI 服务地址不能为空")
    candidate = value.strip()
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in candidate
    ):
        raise ValueError("AI 服务地址不能包含空格或控制字符")
    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        # Accessing ``port`` validates malformed and out-of-range ports.
        _ = parsed.port
        has_credentials = parsed.username is not None or parsed.password is not None
    except ValueError as exc:
        raise ValueError("AI 服务地址格式无效") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("AI 服务地址必须使用 http 或 https")
    if not parsed.netloc or hostname is None or not hostname.strip():
        raise ValueError("AI 服务地址必须包含主机名")
    if has_credentials:
        raise ValueError("AI 服务地址不能包含账号或密码")
    if parsed.query or parsed.fragment or "?" in candidate or "#" in candidate:
        raise ValueError("AI 服务地址不能包含查询参数或片段")

    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"
    elif not path.endswith("/v1"):
        path = f"{path}/v1"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))


def normalize_ollama_base_url(value: str) -> str:
    """Backward-compatible F-027 alias for :func:`normalize_provider_base_url`."""

    return normalize_provider_base_url(value)


def effective_auth_mode(
    settings: ProviderConnectionSettings,
) -> Literal["none", "bearer", "x_api_key"]:
    """Resolve the omitted F-027 auth field without mutating its DTO."""

    return settings.auth_mode or "none"


def _validate_transient_credential(value: str | None) -> str | None:
    """Validate a one-time credential without ever echoing its value."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("凭据不能为空")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("凭据不能包含控制字符")
    return value


class ProviderSettingsStore:
    """Read/write the non-secret setup file below an AppPaths config dir."""

    def __init__(self, config_dir: str | Path) -> None:
        self.config_dir = Path(config_dir)
        self.path = self.config_dir / PROVIDER_SETTINGS_FILENAME

    def load(self) -> ProviderConnectionSettings | None:
        """Load confirmed settings without creating directories or files."""

        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            # A concurrent first-run operation removed the file; a missing
            # configuration is equivalent to an unconfigured installation.
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderSettingsReadError(
                f"unable to read provider settings: {self.path}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise ProviderSettingsReadError(
                "provider settings must contain a JSON object"
            )
        try:
            return ProviderConnectionSettings.model_validate(payload)
        except ValueError as exc:
            raise ProviderSettingsReadError(
                "provider settings are invalid"
            ) from exc

    def save(self, settings: ProviderConnectionSettings) -> None:
        """Persist exactly the public non-secret Provider settings."""

        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            payload = settings.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
            self.path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise ProviderSettingsWriteError(
                f"unable to write provider settings: {self.path}"
            ) from exc


def parse_ollama_tags_payload(payload: object) -> list[OllamaModelCandidate]:
    """Strictly validate the fields needed from an Ollama tags response."""

    if not isinstance(payload, Mapping):
        raise OllamaDiscoveryError("Ollama tags response must be a JSON object")
    raw_models = payload.get("models")
    if type(raw_models) is not list:
        raise OllamaDiscoveryError("Ollama tags response models must be an array")

    models: list[OllamaModelCandidate] = []
    for index, raw_model in enumerate(raw_models):
        if not isinstance(raw_model, Mapping):
            raise OllamaDiscoveryError(
                f"Ollama tags model at index {index} must be an object"
            )
        name = raw_model.get("name")
        if not isinstance(name, str) or not name.strip():
            raise OllamaDiscoveryError(
                f"Ollama tags model at index {index} has an invalid name"
            )
        raw_size = raw_model.get("size")
        if raw_size is not None and (type(raw_size) is not int or raw_size < 0):
            raise OllamaDiscoveryError(
                f"Ollama tags model at index {index} has an invalid size"
            )
        raw_modified_at = raw_model.get("modified_at")
        if raw_modified_at is not None and not isinstance(raw_modified_at, str):
            raise OllamaDiscoveryError(
                f"Ollama tags model at index {index} has an invalid modified_at"
            )
        models.append(
            OllamaModelCandidate(
                name=name.strip(),
                size_bytes=raw_size,
                modified_at=raw_modified_at,
            )
        )
    return models


class ProviderInspectionError(ValueError):
    """Raised when an OpenAI-compatible model response is not trustworthy."""

    provider_response_invalid = True

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        # Keep an observed response status as typed metadata.  The API
        # diagnostic layer must not recover it by parsing exception text.
        self.status_code = status_code


def parse_openai_models_payload(payload: object) -> list[ProviderModelCandidate]:
    """Strictly parse the standard OpenAI ``GET /v1/models`` response.

    Only fields required by the setup UI are retained.  Provider-specific
    extension fields are ignored, but the response envelope and every model ID
    must have the expected JSON types; malformed output is never repaired.
    """

    if not isinstance(payload, Mapping):
        raise ProviderInspectionError("OpenAI models response must be a JSON object")
    envelope = payload.get("object")
    if envelope != "list":
        raise ProviderInspectionError("OpenAI models response object must be list")
    raw_models = payload.get("data")
    if type(raw_models) is not list:
        raise ProviderInspectionError("OpenAI models response data must be an array")

    models: list[ProviderModelCandidate] = []
    for index, raw_model in enumerate(raw_models):
        if not isinstance(raw_model, Mapping):
            raise ProviderInspectionError(
                f"OpenAI model at index {index} must be an object"
            )
        model_id = raw_model.get("id")
        if (
            not isinstance(model_id, str)
            or not model_id.strip()
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in model_id
            )
        ):
            raise ProviderInspectionError(
                f"OpenAI model at index {index} has an invalid id"
            )
        model_object = raw_model.get("object")
        if model_object is not None and model_object != "model":
            raise ProviderInspectionError(
                f"OpenAI model at index {index} has an invalid object"
            )
        created = raw_model.get("created")
        if created is not None and (type(created) is not int or created < 0):
            raise ProviderInspectionError(
                f"OpenAI model at index {index} has an invalid created value"
            )
        owned_by = raw_model.get("owned_by")
        if owned_by is not None and (
            not isinstance(owned_by, str)
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in owned_by
            )
        ):
            raise ProviderInspectionError(
                f"OpenAI model at index {index} has an invalid owned_by value"
            )
        models.append(
            ProviderModelCandidate(
                id=model_id.strip(),
                object=model_object,
                created=created,
                owned_by=owned_by.strip() if isinstance(owned_by, str) else None,
            )
        )
    return models


def _response_status(response: object) -> int | None:
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and not isinstance(status_code, bool):
        return int(status_code)
    status = getattr(response, "status", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return int(status)
    getcode = getattr(response, "getcode", None)
    if callable(getcode):
        code = getcode()
        if isinstance(code, int) and not isinstance(code, bool):
            return int(code)
    return None


def _auth_headers(
    auth_mode: Literal["none", "bearer", "x_api_key"] | None,
    credential: str | None,
) -> dict[str, str]:
    """Build request headers without ever exposing credential in diagnostics."""

    mode = auth_mode or "none"
    if mode == "none":
        return {"Accept": "application/json"}
    if mode != "bearer":
        if mode != "x_api_key":
            raise ProviderConfigurationError("unsupported Provider authentication mode")
        checked = _validate_transient_credential(credential)
        if checked is None:
            raise ProviderConfigurationError("x-api-key credential is not configured")
        return {
            "Accept": "application/json",
            "x-api-key": checked,
        }
    checked = _validate_transient_credential(credential)
    if checked is None:
        raise ProviderConfigurationError("Bearer credential is not configured")
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {checked}",
    }


def _service_root(base_url: str) -> str:
    """Return the explicit service origin/path represented by a normalized base."""

    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(base_url)
    path = parsed.path.rstrip("/")
    if path == "/v1":
        path = ""
    elif path.endswith("/v1"):
        path = path[: -len("/v1")]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def inspect_openai_compatible_endpoint(
    *,
    base_url: str,
    auth_mode: Literal["none", "bearer", "x_api_key"] | None = None,
    credential: str | None = None,
    opener: Callable[..., object] | None = None,
) -> ProtocolInspectionResult:
    """Inspect exactly one explicit OpenAI-compatible ``/v1/models`` URL.

    The function performs one request to the normalized origin.  It does not
    try another path, probe another host, follow redirects, infer a vendor, or
    fall back to Ollama.  The returned DTO contains no credential.
    """

    normalized = normalize_provider_base_url(base_url)
    models_url = f"{normalized.rstrip('/')}/models"
    try:
        headers = _auth_headers(auth_mode, credential)
    except ProviderConfigurationError as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="openai_compatible",
            ),
            models_enumerated=False,
        )
    request = Request(models_url, method="GET", headers=headers)
    open_url = opener or _NO_REDIRECT_OPENER.open
    response: object | None = None
    try:
        response = open_url(request, timeout=5)
        status = _response_status(response)
        if status is not None and not 200 <= status < 300:
            raise ProviderInspectionError(
                f"OpenAI models endpoint returned HTTP {status}",
                status_code=status,
            )
        read = getattr(response, "read", None)
        if not callable(read):
            raise ProviderInspectionError("OpenAI models response body is unreadable")
        payload = json.loads(read())
        models = parse_openai_models_payload(payload)
    except HTTPError as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="openai_compatible",
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
                provider_kind="openai_compatible",
            ),
            models_enumerated=False,
        )
    except (ProviderInspectionError, TypeError, ValueError, UnicodeError) as exc:
        return ProtocolInspectionResult(
            status="unavailable",
            protocol=None,
            base_url=normalized,
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="inspection",
                provider_kind="openai_compatible",
            ),
            models_enumerated=False,
        )
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()

    return ProtocolInspectionResult(
        status="available",
        protocol="openai_compatible",
        base_url=normalized,
        models=models,
        diagnostic=None,
        models_enumerated=True,
    )


def discover_ollama_models(
    *,
    opener: Callable[..., object] | None = None,
    endpoint: str = OLLAMA_DISCOVERY_ENDPOINT,
    auth_mode: Literal["none", "bearer", "x_api_key"] | None = None,
    credential: str | None = None,
) -> OllamaDiscoveryResult:
    """Read the fixed loopback tags endpoint once and return structured state.

    ``opener`` is an explicit test seam.  Production callers use a urllib
    opener that rejects redirects, so a loopback 3xx cannot move discovery to
    a caller-controlled or external target.
    """

    discovery_url = f"{endpoint.rstrip('/')}/api/tags"
    try:
        headers = _auth_headers(auth_mode, credential)
    except ProviderConfigurationError as exc:
        return OllamaDiscoveryResult(
            endpoint=endpoint,
            status="unavailable",
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="discovery",
                provider_kind="ollama",
            ),
        )
    request = Request(
        discovery_url,
        method="GET",
        headers=headers,
    )
    open_url = opener or _NO_REDIRECT_OPENER.open
    response: object | None = None
    try:
        response = open_url(request, timeout=5)
        status = _response_status(response)
        if status is not None and not 200 <= status < 300:
            raise OllamaDiscoveryError(
                f"Ollama tags endpoint returned HTTP {status}",
                status_code=status,
            )
        read = getattr(response, "read", None)
        if not callable(read):
            raise OllamaDiscoveryError("Ollama tags response body is unreadable")
        raw_body = read()
        payload = json.loads(raw_body)
        models = parse_ollama_tags_payload(payload)
    except HTTPError as exc:
        diagnostic = provider_error_diagnostic(
            exc,
            stage="discovery",
            provider_kind="ollama",
        )
        return OllamaDiscoveryResult(
            endpoint=endpoint,
            status="unavailable",
            models=[],
            diagnostic=diagnostic,
        )
    except (OSError, URLError, TimeoutError) as exc:
        return OllamaDiscoveryResult(
            endpoint=endpoint,
            status="unavailable",
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="discovery",
                provider_kind="ollama",
            ),
        )
    except (OllamaDiscoveryError, TypeError, ValueError, UnicodeError) as exc:
        return OllamaDiscoveryResult(
            endpoint=endpoint,
            status="unavailable",
            models=[],
            diagnostic=provider_error_diagnostic(
                exc,
                stage="discovery",
                provider_kind="ollama",
            ),
        )
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()

    return OllamaDiscoveryResult(
        endpoint=endpoint,
        status="available",
        models=models,
        diagnostic=(
            "Ollama 已连接，但本机没有可用模型。"
            "请先安装一个模型，再重新查找。"
            if not models
            else None
        ),
    )


def inspect_provider_endpoint(
    settings: ProviderConnectionSettings | ProviderInspectionRequest,
    *,
    credential: str | None = None,
    opener: Callable[..., object] | None = None,
) -> ProtocolInspectionResult:
    """Inspect one explicitly configured Runtime kind on one explicit origin."""

    if not isinstance(settings, (ProviderConnectionSettings, ProviderInspectionRequest)):
        raise TypeError(
            "settings must be ProviderConnectionSettings or ProviderInspectionRequest"
        )
    resolved_credential = (
        credential
        if credential is not None
        else getattr(settings, "credential", None)
    )
    if settings.kind == "openai_compatible":
        return inspect_openai_compatible_endpoint(
            base_url=settings.base_url,
            auth_mode=settings.auth_mode,
            credential=resolved_credential,
            opener=opener,
        )

    if settings.kind == "anthropic_compatible":
        from .providers.anthropic import inspect_anthropic_endpoint

        return inspect_anthropic_endpoint(
            base_url=settings.base_url,
            auth_mode=settings.auth_mode,
            credential=resolved_credential,
            opener=opener,
        )

    if settings.kind == "agent_audit_adapter":
        from .providers.agent_audit_adapter import inspect_agent_audit_adapter_endpoint

        return inspect_agent_audit_adapter_endpoint(
            base_url=settings.base_url,
            auth_mode=settings.auth_mode,
            credential=resolved_credential,
            opener=opener,
        )

    normalized = normalize_provider_base_url(settings.base_url)
    result = discover_ollama_models(
        opener=opener,
        endpoint=_service_root(normalized),
        auth_mode=settings.auth_mode,
        credential=resolved_credential,
    )
    return ProtocolInspectionResult(
        status=result.status,
        protocol="ollama" if result.status == "available" else None,
        base_url=normalized,
        models=[
            ProviderModelCandidate(
                id=model.name,
                object="model",
                created=None,
                owned_by=None,
            )
            for model in result.models
        ],
        diagnostic=result.diagnostic,
        models_enumerated=result.status == "available",
    )


__all__ = [
    "OLLAMA_DISCOVERY_ENDPOINT",
    "OLLAMA_DISCOVERY_URL",
    "PROVIDER_CREDENTIAL_ENV",
    "PROVIDER_SETTINGS_FILENAME",
    "OllamaDiscoveryError",
    "OllamaDiscoveryRequest",
    "OllamaDiscoveryResult",
    "OllamaModelCandidate",
    "ProviderCandidateReadinessRequest",
    "ProviderConnectionSettings",
    "ProviderInspectionError",
    "ProviderInspectionRequest",
    "ProviderModelCandidate",
    "ProviderSettingsError",
    "ProviderSettingsReadError",
    "ProviderSettingsStore",
    "ProviderSettingsWriteError",
    "ProviderSetupState",
    "ProtocolInspectionResult",
    "SaveProviderSettingsRequest",
    "discover_ollama_models",
    "effective_auth_mode",
    "inspect_openai_compatible_endpoint",
    "inspect_provider_endpoint",
    "normalize_ollama_base_url",
    "normalize_provider_base_url",
    "parse_openai_models_payload",
    "parse_ollama_tags_payload",
]
