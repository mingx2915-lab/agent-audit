"""Explicit runtime Provider selection."""

from __future__ import annotations

import os

from .base import LLMProvider, ProviderConfigurationError
from .agent_audit_adapter import AgentAuditAdapterProvider
from .anthropic import AnthropicCompatibleProvider
from .deepseek import DeepSeekProvider
from .ollama import OllamaProvider
from .openai_compatible import OpenAICompatibleProvider


PROVIDER_CREDENTIAL_ENV = "AGENT_AUDIT_PROVIDER_API_KEY"


def create_runtime_provider(
    settings: object | None = None,
    *,
    credential: str | None = None,
    use_environment_credential: bool = False,
) -> LLMProvider:
    """Create the explicit configured Runtime or the legacy env Provider.

    ``settings`` contains no secret.  A bearer value is supplied through the
    transient ``credential`` argument.  The Desktop-injected process
    environment variable is read only when the caller explicitly opts into
    that boundary (active startup, or a confirmed same-connection update);
    candidate inspection/readiness/save callers do not inherit it implicitly.
    This module does not read or write a keyring.
    """

    if settings is not None:
        kind = getattr(settings, "kind", None)
        base_url = getattr(settings, "base_url", None)
        model = getattr(settings, "model", None)
        auth_mode = getattr(settings, "auth_mode", None) or "none"
        if kind not in {
            "ollama",
            "openai_compatible",
            "anthropic_compatible",
            "agent_audit_adapter",
        }:
            raise ProviderConfigurationError("unsupported Provider connection kind")
        if auth_mode not in {"none", "bearer", "x_api_key"}:
            raise ProviderConfigurationError(
                "unsupported Provider authentication mode"
            )
        if kind in {"ollama", "openai_compatible"} and auth_mode == "x_api_key":
            raise ProviderConfigurationError(
                "x_api_key authentication is unsupported for this Provider kind"
            )
        if not isinstance(base_url, str) or not isinstance(model, str):
            raise ProviderConfigurationError("Provider connection settings are invalid")
        resolved_credential = (
            credential
            if auth_mode in {"bearer", "x_api_key"}
            else None
        )
        if (
            resolved_credential is None
            and auth_mode in {"bearer", "x_api_key"}
            and use_environment_credential
        ):
            resolved_credential = os.getenv(PROVIDER_CREDENTIAL_ENV)
        if kind == "ollama":
            return OllamaProvider(
                base_url=base_url,
                model=model,
                auth_mode=auth_mode,
                credential=resolved_credential,
            )
        if kind == "openai_compatible":
            return OpenAICompatibleProvider(
                base_url=base_url,
                model=model,
                auth_mode=auth_mode,
                credential=resolved_credential,
            )
        if kind == "anthropic_compatible":
            return AnthropicCompatibleProvider(
                base_url=base_url,
                model=model,
                auth_mode=auth_mode,
                credential=resolved_credential,
            )
        return AgentAuditAdapterProvider(
            base_url=base_url,
            model=model,
            auth_mode=auth_mode,
            credential=resolved_credential,
        )

    name = os.getenv("AGENT_AUDIT_LLM_PROVIDER", "deepseek").strip().lower()
    if name == "deepseek":
        return DeepSeekProvider()
    if name == "ollama":
        return OllamaProvider()
    raise ProviderConfigurationError(f"unsupported LLM provider: {name or '<empty>'}")


__all__ = ["PROVIDER_CREDENTIAL_ENV", "create_runtime_provider"]
