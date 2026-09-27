"""Safe, stage-aware diagnostics for Provider trust boundaries.

Provider failures cross several API surfaces: model discovery, endpoint
inspection, readiness probes, and an actual audit execution.  The public API
currently exposes one diagnostic string on each of those surfaces, so this
module keeps the projection deterministic and deliberately does not inspect
exception text.  A status code, a known exception type, and the operation
stage are the only inputs used to choose the user-facing explanation.

The raw exception remains available to local logging through normal exception
chaining.  It is never copied into an API response, because SDK/HTTP bodies
may contain credentials or provider-specific sensitive data.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Literal
from urllib.error import HTTPError, URLError

ProviderDiagnosticStage = Literal[
    "configuration",
    "discovery",
    "inspection",
    "manifest",
    "readiness",
    "execution",
]


def _exception_chain(error: BaseException) -> Iterator[BaseException]:
    """Yield known exception links without traversing arbitrary payloads."""

    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current
        for attribute in ("__cause__", "__context__", "reason"):
            nested = getattr(current, attribute, None)
            if isinstance(nested, BaseException) and id(nested) not in seen:
                pending.append(nested)


def _status_value(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
        return int(value)
    return None


def provider_error_status(error: BaseException) -> int | None:
    """Return an HTTP status carried by a known error, without reading bodies."""

    for current in _exception_chain(error):
        if isinstance(current, HTTPError):
            status = _status_value(current.code)
            if status is not None:
                return status
        for attribute in ("status_code", "status"):
            status = _status_value(getattr(current, attribute, None))
            if status is not None:
                return status
        response = getattr(current, "response", None)
        for attribute in ("status_code", "status"):
            status = _status_value(getattr(response, attribute, None))
            if status is not None:
                return status
    return None


def _is_timeout(error: BaseException) -> bool:
    for current in _exception_chain(error):
        if isinstance(current, (TimeoutError, socket.timeout)):
            return True
        try:
            import httpx
        except ImportError:  # pragma: no cover - dependency is part of the API app
            httpx = None  # type: ignore[assignment]
        if httpx is not None and isinstance(current, httpx.TimeoutException):
            return True
        try:
            import openai
        except ImportError:  # pragma: no cover - dependency is part of the API app
            openai = None  # type: ignore[assignment]
        if openai is not None and isinstance(current, openai.APITimeoutError):
            return True
    return False


def _is_connection_failure(error: BaseException) -> bool:
    for current in _exception_chain(error):
        if isinstance(current, (ConnectionError, OSError, URLError)) and not isinstance(
            current, (HTTPError, TimeoutError, socket.timeout)
        ):
            return True
        try:
            import httpx
        except ImportError:  # pragma: no cover - dependency is part of the API app
            httpx = None  # type: ignore[assignment]
        if httpx is not None and isinstance(current, httpx.NetworkError):
            return True
        try:
            import openai
        except ImportError:  # pragma: no cover - dependency is part of the API app
            openai = None  # type: ignore[assignment]
        if openai is not None and isinstance(current, openai.APIConnectionError):
            return True
    return False


def _provider_label(provider_kind: str | None) -> str:
    labels = {
        "ollama": "本机 Ollama",
        "openai_compatible": "企业 AI 服务",
        "anthropic_compatible": "企业 AI 服务",
        "agent_audit_adapter": "企业 AI 适配服务",
        "deepseek": "DeepSeek 服务",
    }
    return labels.get(provider_kind or "", "AI 服务")


def _stage_label(
    stage: ProviderDiagnosticStage,
    probe_id: str | None,
) -> str:
    if probe_id == "target.connectivity":
        return "目标连接检查"
    if probe_id == "target.tool_calling":
        return "工具调用能力检查"
    if probe_id == "attack.connectivity":
        return "攻击连接检查"
    if probe_id == "attack.strict_json":
        return "结构化结果检查"
    return {
        "configuration": "连接设置",
        "discovery": "模型查找",
        "inspection": "地址检查",
        "manifest": "适配协议检查",
        "readiness": "能力检查",
        "execution": "本次操作",
    }[stage]


def _status_diagnostic(
    status: int,
    *,
    provider_kind: str | None,
    stage: ProviderDiagnosticStage,
    probe_id: str | None,
) -> str:
    label = _provider_label(provider_kind)
    phase = _stage_label(stage, probe_id)
    if status in {401, 403}:
        if stage == "discovery":
            return (
                f"{label}拒绝了模型查询（HTTP {status}）。"
                "请确认本机地址运行的是 Ollama，再重新查找。"
            )
        return (
            f"认证失败：{label}拒绝了{phase}（HTTP {status}）。"
            "请重新输入凭据后再检查。"
        )
    if status in {408, 504}:
        return (
            f"{phase}超时：{label}在规定时间内没有完成响应（HTTP {status}）。"
            "请确认服务状态后重新检查。"
        )
    if status == 429:
        return (
            f"{label}暂时限制了{phase}请求（HTTP 429）。"
            "请稍后重新检查，不会自动重复请求。"
        )
    if 300 <= status <= 399:
        return (
            f"{phase}返回了重定向（HTTP {status}），系统没有继续访问其他地址。"
            "请填写最终服务地址后重新检查。"
        )
    if status == 404:
        if stage == "discovery":
            return (
                f"{label}地址没有提供模型列表（HTTP 404）。"
                "请确认 Ollama 正在 127.0.0.1:11434 运行。"
            )
        return (
            f"{label}地址没有提供{phase}所需的接口（HTTP 404）。"
            "请确认填写的是服务地址，再重新检查。"
        )
    if 500 <= status <= 599:
        return (
            f"{label}在{phase}时返回服务错误（HTTP {status}）。"
            "请确认服务状态后重新检查。"
        )
    if 400 <= status <= 499:
        return (
            f"{label}拒绝了{phase}请求（HTTP {status}）。"
            "请确认地址、模型和认证方式后重新检查。"
        )
    return (
        f"{label}的{phase}未完成（HTTP {status}）。"
        "请确认服务状态后重新检查。"
    )


def _response_diagnostic(
    *,
    provider_kind: str | None,
    stage: ProviderDiagnosticStage,
    probe_id: str | None,
) -> str:
    label = _provider_label(provider_kind)
    if stage == "discovery":
        return (
            f"已连接{label}，但模型列表无法识别。"
            "请确认服务正常后重新查找。"
        )
    if stage == "manifest":
        return (
            f"{label}已响应，但适配协议清单无法识别。"
            "请确认地址提供 AgentAudit adapter v1 清单后重新检查。"
        )
    if stage == "inspection":
        if provider_kind == "anthropic_compatible":
            endpoint = "Anthropic 模型列表接口"
        elif provider_kind == "agent_audit_adapter":
            endpoint = "AgentAudit adapter 接口"
        else:
            endpoint = "OpenAI-compatible /v1/models 接口"
        return (
            f"{label}已响应，但没有返回可识别的模型列表。"
            f"请确认地址提供{endpoint}后重新检查。"
        )
    if probe_id == "target.tool_calling":
        return (
            f"{label}已响应，但未按要求完成工具调用检查。"
            "请确认所选模型支持 Tool Calling 后重新检查。"
        )
    if probe_id == "attack.strict_json":
        return (
            f"{label}已响应，但未按要求返回结构化结果。"
            "请确认所选模型支持严格 JSON 后重新检查。"
        )
    if stage == "readiness":
        return (
            f"{label}已响应，但{_stage_label(stage, probe_id)}返回内容无法识别。"
            "请确认模型与协议匹配后重新检查。"
        )
    return (
        f"{label}返回了无法识别的结果，本次检查未形成有效结论。"
        "请检查模型和协议设置后重新执行。"
    )


def provider_error_diagnostic(
    error: BaseException,
    *,
    stage: ProviderDiagnosticStage,
    provider_kind: str | None = None,
    probe_id: str | None = None,
    status_code: int | None = None,
) -> str:
    """Project one Provider error to a safe, actionable Chinese diagnostic.

    ``status_code`` is accepted from a response object when the adapter has
    already checked it.  Otherwise the function looks only at typed status
    attributes in the exception chain.  It never branches on ``str(error)``.
    """

    # Import lazily because ``providers.__init__`` exports the concrete
    # adapters, and those adapters use this module for their inspection
    # diagnostics.  Keeping the type lookup at the call boundary avoids a
    # cycle for callers that import this helper directly.
    from .providers.base import (
        ProviderConfigurationError,
        ProviderResponseError,
        ProviderUnavailableError,
    )

    status = _status_value(status_code) if status_code is not None else None
    if status is None:
        status = provider_error_status(error)
    if status is not None:
        return _status_diagnostic(
            status,
            provider_kind=provider_kind,
            stage=stage,
            probe_id=probe_id,
        )

    if isinstance(error, ProviderConfigurationError):
        if stage == "execution":
            return (
                "AI 连接设置尚未完成，本次操作没有开始。"
                "请先补充模型和认证信息，再重新执行。"
            )
        return (
            f"{_stage_label(stage, probe_id)}所需的连接设置不完整。"
            "请补充模型和认证信息后重新检查。"
        )

    if _is_timeout(error):
        label = _provider_label(provider_kind)
        phase = _stage_label(stage, probe_id)
        if stage == "execution":
            return (
                f"{label}响应超时，本次操作未形成有效结论。"
                "请确认服务状态后重新执行。"
            )
        return (
            f"{phase}超时：{label}在规定时间内没有完成响应。"
            "请确认服务状态后重新检查。"
        )

    response_invalid = bool(getattr(error, "provider_response_invalid", False))
    if isinstance(error, ProviderResponseError) or response_invalid or (
        stage in {"discovery", "inspection", "manifest"}
        and isinstance(error, (TypeError, ValueError, UnicodeError))
    ):
        return _response_diagnostic(
            provider_kind=provider_kind,
            stage=stage,
            probe_id=probe_id,
        )

    if _is_connection_failure(error):
        label = _provider_label(provider_kind)
        phase = _stage_label(stage, probe_id)
        if stage == "discovery":
            return (
                f"无法连接{label}：本机模型服务没有响应。"
                "请确认 Ollama 已安装并正在运行，然后重新查找。"
            )
        if stage == "execution":
            return (
                f"无法连接{label}，本次操作未形成有效结论。"
                "请确认服务地址或本机模型服务可达后重新执行。"
            )
        return (
            f"无法连接{label}：{phase}没有收到响应。"
            "请确认地址可达且服务已启动后重新检查。"
        )

    if isinstance(error, ProviderUnavailableError):
        label = _provider_label(provider_kind)
        phase = _stage_label(stage, probe_id)
        if stage == "execution":
            return (
                f"{label}未完成本次操作，本次检查未形成有效结论。"
                "请确认服务和模型可用后重新执行。"
            )
        return (
            f"{label}未完成{phase}。请确认服务和模型可用后重新检查。"
        )

    # Programming errors are normally allowed to propagate.  This branch is
    # for a caller that deliberately passes an unknown failure to the API
    # boundary; it still avoids echoing arbitrary exception text.
    label = _provider_label(provider_kind)
    phase = _stage_label(stage, probe_id)
    if stage == "execution":
        return (
            f"{label}执行{phase}时发生未分类失败，本次检查未形成有效结论。"
            "请查看技术诊断后重新执行。"
        )
    return f"{label}{phase}未完成，请查看技术诊断后重新检查。"


__all__ = [
    "ProviderDiagnosticStage",
    "provider_error_diagnostic",
    "provider_error_status",
]
