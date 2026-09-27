"""Unit coverage for the strict, single-call Provider readiness probes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
    ToolCall,
)
from agent_audit_api.readiness import (
    ProviderReadinessRunner,
    _READINESS_NONCE,
    _READINESS_TOOL_NAME,
    _overall_status,
    _required_probe_ids,
    _role_status,
)


@dataclass
class ScriptedProvider:
    """A provider double that makes every call and response observable."""

    responses: list[Any]
    model: str = "test-model"
    calls: list[tuple[list[dict[str, Any]], Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append(([dict(message) for message in messages], tools))
        if not self.responses:
            raise AssertionError("readiness provider received an unexpected call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _valid_target_responses() -> list[LLMResponse]:
    return [
        LLMResponse(content="target connectivity", tool_calls=()),
        LLMResponse(
            content=None,
            tool_calls=(
                ToolCall(
                    id="readiness-tool-call",
                    name=_READINESS_TOOL_NAME,
                    arguments={"nonce": _READINESS_NONCE},
                ),
            ),
        ),
    ]


def _valid_attack_responses() -> list[LLMResponse]:
    return [
        LLMResponse(content="attack connectivity", tool_calls=()),
        LLMResponse(
            content=json.dumps(
                {"status": "ready", "nonce": _READINESS_NONCE},
                separators=(",", ":"),
            ),
            tool_calls=(),
        ),
    ]


def _plans() -> tuple[SimpleNamespace, ...]:
    return tuple(
        SimpleNamespace(id=f"plan-{basis_type}", basis_type=basis_type)
        for basis_type in (
            "resource_owner_scope",
            "tool_owner_scope",
            "source_sink",
            "tool_record_limit",
        )
    )


def _runner(
    *,
    target_responses: list[Any] | None = None,
    attack_responses: list[Any] | None = None,
) -> tuple[ProviderReadinessRunner, ScriptedProvider, ScriptedProvider]:
    target = ScriptedProvider(
        list(_valid_target_responses() if target_responses is None else target_responses),
        model="target-test-model",
    )
    attack = ScriptedProvider(
        list(_valid_attack_responses() if attack_responses is None else attack_responses),
        model="attack-test-model",
    )
    return ProviderReadinessRunner(target, attack, _plans()), target, attack


def _run_valid() -> tuple[Any, ScriptedProvider, ScriptedProvider]:
    runner, target, attack = _runner()
    return asyncio.run(runner.run()), target, attack


def test_all_four_probes_are_single_calls_and_providers_stay_isolated() -> None:
    result, target, attack = _run_valid()

    assert len(target.calls) == 2
    assert len(attack.calls) == 2
    assert target.responses == []
    assert attack.responses == []

    assert target.calls[0][1] is None
    assert target.calls[1][1] is not None
    assert target.calls[1][1][0]["function"]["name"] == _READINESS_TOOL_NAME
    assert attack.calls[0][1] is None
    assert attack.calls[1][1] is None

    assert "Connectivity probe" in target.calls[0][0][-1]["content"]
    assert "Tool Calling readiness probe" in target.calls[1][0][0]["content"]
    assert "strict JSON readiness probe" in attack.calls[1][0][0]["content"]
    assert [probe.id for probe in result.target_provider.probes] == [
        "target.connectivity",
        "target.tool_calling",
    ]
    assert [probe.id for probe in result.attack_provider.probes] == [
        "attack.connectivity",
        "attack.strict_json",
    ]


@pytest.mark.parametrize(
    ("probe_id", "response"),
    [
        (
            "target.connectivity",
            LLMResponse(content="", tool_calls=()),
        ),
        (
            "target.connectivity",
            LLMResponse(content="target text", tool_calls=(ToolCall("id", "other", {}),)),
        ),
        (
            "target.connectivity",
            LLMResponse(content=None, tool_calls=(ToolCall("id", "other", {}),)),
        ),
        (
            "attack.connectivity",
            LLMResponse(content=None, tool_calls=()),
        ),
        (
            "attack.connectivity",
            LLMResponse(content="attack text", tool_calls=(ToolCall("id", "other", {}),)),
        ),
        (
            "attack.connectivity",
            LLMResponse(content=None, tool_calls=(ToolCall("id", "other", {}),)),
        ),
    ],
)
def test_connectivity_requires_non_empty_text_without_tool_calls(
    probe_id: str,
    response: LLMResponse,
) -> None:
    with pytest.raises(ProviderResponseError):
        ProviderReadinessRunner._validate_probe_response(probe_id, response)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "content",
    [
        "```json\n{\"status\":\"ready\",\"nonce\":\"agent-audit-readiness\"}\n```",
        '{"status":"ready"}',
        '{"status":"ready","nonce":"agent-audit-readiness","extra":true}',
        '{"status":"not-ready","nonce":"agent-audit-readiness"}',
        "[]",
        "null",
        "NaN",
    ],
)
def test_strict_json_rejects_wrappers_wrong_shape_and_wrong_values(content: str) -> None:
    with pytest.raises(ProviderResponseError):
        ProviderReadinessRunner._validate_probe_response(
            "attack.strict_json",
            LLMResponse(content=content, tool_calls=()),
        )


def test_strict_json_accepts_only_the_exact_bare_object() -> None:
    ProviderReadinessRunner._validate_probe_response(
        "attack.strict_json",
        LLMResponse(
            content='{"status":"ready","nonce":"agent-audit-readiness"}',
            tool_calls=(),
        ),
    )


def test_strict_json_rejects_any_tool_call_even_with_valid_text() -> None:
    with pytest.raises(ProviderResponseError):
        ProviderReadinessRunner._validate_probe_response(
            "attack.strict_json",
            LLMResponse(
                content='{"status":"ready","nonce":"agent-audit-readiness"}',
                tool_calls=(ToolCall("id", _READINESS_TOOL_NAME, {"nonce": _READINESS_NONCE}),),
            ),
        )


@pytest.mark.parametrize(
    "tool_calls",
    [
        (),
        (
            ToolCall(
                "id",
                "wrong_tool",
                {"nonce": _READINESS_NONCE},
            ),
        ),
        (
            ToolCall(
                "id-1",
                _READINESS_TOOL_NAME,
                {"nonce": _READINESS_NONCE},
            ),
            ToolCall(
                "id-2",
                _READINESS_TOOL_NAME,
                {"nonce": _READINESS_NONCE},
            ),
        ),
        (
            ToolCall("id", _READINESS_TOOL_NAME, {}),
        ),
        (
            ToolCall("id", _READINESS_TOOL_NAME, {"nonce": "wrong"}),
        ),
        (
            ToolCall(
                "id",
                _READINESS_TOOL_NAME,
                {"nonce": _READINESS_NONCE, "extra": True},
            ),
        ),
    ],
)
def test_tool_calling_requires_one_named_call_with_exact_arguments(tool_calls) -> None:
    with pytest.raises(ProviderResponseError):
        ProviderReadinessRunner._validate_probe_response(
            "target.tool_calling",
            LLMResponse(content="text only", tool_calls=tool_calls),
        )


def test_tool_calling_accepts_one_named_call_with_exact_arguments() -> None:
    ProviderReadinessRunner._validate_probe_response(
        "target.tool_calling",
        LLMResponse(
            content=None,
            tool_calls=(
                ToolCall("id", _READINESS_TOOL_NAME, {"nonce": _READINESS_NONCE}),
            ),
        ),
    )


@pytest.mark.parametrize(
    "error",
    [
        ProviderConfigurationError("missing provider configuration"),
        ProviderUnavailableError("provider unavailable"),
        ProviderResponseError("malformed provider response"),
    ],
)
def test_provider_errors_are_recorded_once_without_retry_or_fallback(error: Exception) -> None:
    runner, target, attack = _runner(
        target_responses=[error, _valid_target_responses()[1]],
        attack_responses=[_valid_attack_responses()[0], error],
    )

    result = asyncio.run(runner.run())

    assert len(target.calls) == 2
    assert len(attack.calls) == 2
    assert result.target_provider.probes[0].status == "failed"
    target_detail = result.target_provider.probes[0].detail
    assert any(term in target_detail for term in ("检查", "设置", "服务", "结果"))
    assert "重新" in target_detail
    assert str(error) not in target_detail
    assert result.attack_provider.probes[1].status == "failed"
    attack_detail = result.attack_provider.probes[1].detail
    assert any(term in attack_detail for term in ("检查", "设置", "服务", "结果"))
    assert "重新" in attack_detail
    assert str(error) not in attack_detail
    assert result.target_provider.probes[1].status == "passed"
    assert result.attack_provider.probes[0].status == "passed"


def test_unexpected_exception_is_not_converted_to_probe_failure() -> None:
    runner, target, attack = _runner(
        target_responses=[RuntimeError("programming error")],
        attack_responses=_valid_attack_responses(),
    )

    with pytest.raises(RuntimeError, match="programming error"):
        asyncio.run(runner.run())
    assert len(target.calls) == 1
    assert len(attack.calls) == 0


def test_probe_durations_are_non_negative() -> None:
    result, _, _ = _run_valid()

    for role in (result.target_provider, result.attack_provider):
        assert all(probe.duration_ms >= 0 for probe in role.probes)


def test_role_and_overall_statuses_distinguish_ready_partial_and_unavailable() -> None:
    passed = SimpleNamespace(status="passed")
    failed = SimpleNamespace(status="failed")

    assert _role_status([passed, passed]) == "ready"
    assert _role_status([passed, failed]) == "partial"
    assert _role_status([failed, failed]) == "unavailable"
    assert _overall_status("ready", "ready") == "ready"
    assert _overall_status("unavailable", "unavailable") == "unavailable"
    assert _overall_status("ready", "unavailable") == "partial"
    assert _overall_status("partial", "ready") == "partial"


def test_four_plan_requirement_mappings_and_failed_probe_ids_are_traceable() -> None:
    result, _, _ = _run_valid()
    by_basis = {item.basis_type: item for item in result.plan_compatibility}

    assert set(by_basis) == {
        "resource_owner_scope",
        "tool_owner_scope",
        "source_sink",
        "tool_record_limit",
    }
    assert by_basis["resource_owner_scope"].required_probe_ids == [
        "target.connectivity",
        "attack.connectivity",
        "attack.strict_json",
    ]
    for basis_type in (
        "tool_owner_scope",
        "source_sink",
        "tool_record_limit",
    ):
        assert by_basis[basis_type].required_probe_ids == [
            "target.connectivity",
            "target.tool_calling",
            "attack.connectivity",
            "attack.strict_json",
        ]
    assert all(item.status == "compatible" for item in by_basis.values())
    assert all(item.failed_probe_ids == [] for item in by_basis.values())
    assert _required_probe_ids("resource_owner_scope") == tuple(
        by_basis["resource_owner_scope"].required_probe_ids
    )


def test_failed_probe_ids_include_only_required_failed_probes() -> None:
    runner, _, _ = _runner(
        target_responses=[
            _valid_target_responses()[0],
            ProviderResponseError("tool calling unavailable"),
        ],
        attack_responses=_valid_attack_responses(),
    )
    result = asyncio.run(runner.run())
    by_basis = {item.basis_type: item for item in result.plan_compatibility}

    assert by_basis["resource_owner_scope"].status == "compatible"
    assert by_basis["resource_owner_scope"].failed_probe_ids == []
    for basis_type in ("tool_owner_scope", "source_sink", "tool_record_limit"):
        assert by_basis[basis_type].status == "incompatible"
        assert by_basis[basis_type].failed_probe_ids == ["target.tool_calling"]
