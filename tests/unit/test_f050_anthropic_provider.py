"""F-050 unit coverage for the Anthropic Messages adapter.

The client used here is an explicit test-only HTTP double.  It does not
pretend to be a Claude Gateway and never opens a network connection.  The
production adapter, request URL, headers, content blocks and strict response
normalization remain under test.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from agent_audit_api.providers.anthropic import (
    ANTHROPIC_MESSAGES_PATH,
    ANTHROPIC_VERSION,
    AnthropicCompatibleProvider,
    normalize_anthropic_response,
    to_anthropic_request_payload,
)
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
    ProviderUsage,
    ToolCall,
)


TEST_BASE_URL = "https://claude-gateway.intra.example/team/v1"
TEST_MODEL = "claude-enterprise"
TEST_SECRET = "f050-anthropic-secret-test-only"


@dataclass
class FakeHTTPResponse:
    """Explicit local response double for the adapter's injected client."""

    payload: object
    status_code: int = 200

    def json(self) -> object:
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


@dataclass
class RecordingHTTPClient:
    """Test-only client; no real enterprise gateway is involved."""

    responses: list[object]
    calls: list[dict[str, object]] = field(default_factory=list)

    async def post(self, url: str, **request: object) -> FakeHTTPResponse:
        self.calls.append({"url": url, **request})
        if not self.responses:
            raise AssertionError("unexpected Anthropic request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        assert isinstance(response, FakeHTTPResponse)
        return response


def _text_response(
    *blocks: dict[str, object],
    usage: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "msg_f050_001",
        "type": "message",
        "role": "assistant",
        "content": list(blocks),
        "model": TEST_MODEL,
        "stop_reason": "end_turn",
    }
    if usage is not None:
        payload["usage"] = usage
    return payload


def _provider(
    client: RecordingHTTPClient,
    *,
    auth_mode: str = "none",
    credential: str | None = None,
) -> AnthropicCompatibleProvider:
    return AnthropicCompatibleProvider(
        client=client,
        base_url=TEST_BASE_URL,
        model=TEST_MODEL,
        auth_mode=auth_mode,
        credential=credential,
    )


def test_anthropic_text_request_uses_fixed_messages_path_version_and_max_tokens() -> None:
    client = RecordingHTTPClient(
        [FakeHTTPResponse(_text_response({"type": "text", "text": "企业回答"}))]
    )
    provider = _provider(client)

    response = asyncio.run(
        provider.complete(
            [
                {"role": "system", "content": "遵守企业规则"},
                {"role": "user", "content": "请总结政策"},
            ]
        )
    )

    assert response == LLMResponse(content="企业回答")
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["url"] == f"{TEST_BASE_URL}{ANTHROPIC_MESSAGES_PATH}"
    assert request["timeout"] == 30
    assert request["headers"] == {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
    }
    assert request["json"] == {
        "model": TEST_MODEL,
        "max_tokens": 4096,
        "system": [{"type": "text", "text": "遵守企业规则"}],
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": "请总结政策"}],
            }
        ],
    }


def test_anthropic_request_converts_tool_use_and_tool_result_blocks() -> None:
    payload = to_anthropic_request_payload(
        [
            {"role": "user", "content": "查询客户"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_customer_001",
                        "function": {
                            "name": "mock_customer_lookup",
                            "arguments": '{"customerId":"customer_001"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_customer_001",
                "content": '{"name":"合成客户"}',
            },
        ],
        [
            {
                "type": "function",
                "function": {
                    "name": "mock_customer_lookup",
                    "description": "查找合成客户",
                    "parameters": {
                        "type": "object",
                        "properties": {"customerId": {"type": "string"}},
                    },
                },
            }
        ],
        model=TEST_MODEL,
        max_tokens=123,
    )

    assert payload == {
        "model": TEST_MODEL,
        "max_tokens": 123,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "查询客户"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call_customer_001",
                        "name": "mock_customer_lookup",
                        "input": {"customerId": "customer_001"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_customer_001",
                        "content": '{"name":"合成客户"}',
                    }
                ],
            },
        ],
        "tools": [
            {
                "name": "mock_customer_lookup",
                "description": "查找合成客户",
                "input_schema": {
                    "type": "object",
                    "properties": {"customerId": {"type": "string"}},
                },
            }
        ],
    }


def test_anthropic_response_normalizes_text_json_tool_use_and_usage() -> None:
    raw = _text_response(
        {"type": "text", "text": "先说明"},
        {
            "type": "tool_use",
            "id": "tool_f050_001",
            "name": "mock_customer_lookup",
            "input": {"customerId": "customer_001"},
        },
        {"type": "text", "text": "后续说明"},
        usage={"input_tokens": 17, "output_tokens": 8},
    )

    result = normalize_anthropic_response(raw)

    assert result.content == "先说明后续说明"
    assert result.tool_calls == (
        ToolCall(
            id="tool_f050_001",
            name="mock_customer_lookup",
            arguments={"customerId": "customer_001"},
        ),
    )
    assert result.usage == ProviderUsage(
        input_tokens=17,
        output_tokens=8,
        total_tokens=25,
    )


@pytest.mark.parametrize(
    ("auth_mode", "credential", "header_name", "header_value"),
    [
        ("bearer", TEST_SECRET, "Authorization", f"Bearer {TEST_SECRET}"),
        ("x_api_key", TEST_SECRET, "x-api-key", TEST_SECRET),
    ],
)
def test_anthropic_auth_headers_are_fixed_and_secret_is_not_in_normalized_result(
    auth_mode: str,
    credential: str,
    header_name: str,
    header_value: str,
) -> None:
    client = RecordingHTTPClient(
        [FakeHTTPResponse(_text_response({"type": "text", "text": "ok"}))]
    )
    response = asyncio.run(
        _provider(client, auth_mode=auth_mode, credential=credential).complete(
            [{"role": "user", "content": "测试"}]
        )
    )

    headers = client.calls[0]["headers"]
    assert isinstance(headers, dict)
    assert headers[header_name] == header_value
    assert "Authorization" not in headers or header_name == "Authorization"
    assert "x-api-key" not in headers or header_name == "x-api-key"
    assert TEST_SECRET not in json.dumps(response, default=str, ensure_ascii=False)


@pytest.mark.parametrize("auth_mode", ["bearer", "x_api_key"])
def test_anthropic_missing_credential_fails_before_http_request(auth_mode: str) -> None:
    client = RecordingHTTPClient([])
    provider = _provider(client, auth_mode=auth_mode)

    with pytest.raises(ProviderConfigurationError, match="credential is not configured"):
        asyncio.run(provider.complete([{"role": "user", "content": "测试"}]))

    assert client.calls == []


@pytest.mark.parametrize(
    "response",
    [
        FakeHTTPResponse({"error": {"type": "authentication_error"}}, status_code=401),
        FakeHTTPResponse({"error": {"type": "upstream_error"}}, status_code=502),
        FakeHTTPResponse({"error": {"type": "overloaded_error"}}, status_code=503),
    ],
)
def test_anthropic_http_failures_are_single_attempts_without_fallback(response: FakeHTTPResponse) -> None:
    client = RecordingHTTPClient([response])
    provider = _provider(client, auth_mode="x_api_key", credential=TEST_SECRET)

    with pytest.raises(ProviderUnavailableError) as raised:
        asyncio.run(provider.complete([{"role": "user", "content": "测试"}]))

    assert f"HTTP {response.status_code}" in str(raised.value)
    assert len(client.calls) == 1
    assert "/api/tags" not in str(client.calls)
    assert TEST_SECRET not in str(raised.value)


def test_anthropic_timeout_is_one_attempt_and_has_no_fallback() -> None:
    client = RecordingHTTPClient([TimeoutError("synthetic timeout")])
    provider = _provider(client)

    with pytest.raises(ProviderUnavailableError, match="request failed"):
        asyncio.run(provider.complete([{"role": "user", "content": "测试"}]))

    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "message", "role": "assistant", "content": [{"type": "image"}]},
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": 123}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "duplicate",
                    "name": "one",
                    "input": {},
                },
                {
                    "type": "tool_use",
                    "id": "duplicate",
                    "name": "two",
                    "input": {},
                },
            ],
        },
    ],
)
def test_anthropic_malformed_content_block_fails_without_repair(payload: object) -> None:
    with pytest.raises(ProviderResponseError):
        normalize_anthropic_response(payload)


def test_anthropic_malformed_json_fails_without_second_request() -> None:
    client = RecordingHTTPClient([FakeHTTPResponse(ValueError("not JSON"))])
    provider = _provider(client)

    with pytest.raises(ProviderResponseError, match="not valid JSON"):
        asyncio.run(provider.complete([{"role": "user", "content": "测试"}]))

    assert len(client.calls) == 1


def test_anthropic_invalid_request_shape_fails_before_http_request() -> None:
    client = RecordingHTTPClient([])
    provider = _provider(client)

    with pytest.raises(ProviderResponseError, match="invalid role"):
        asyncio.run(provider.complete([{"role": "developer", "content": "测试"}]))

    assert client.calls == []


def test_anthropic_provider_rejects_invalid_max_tokens_without_http_request() -> None:
    client = RecordingHTTPClient([])
    with pytest.raises(ProviderConfigurationError, match="max_tokens"):
        AnthropicCompatibleProvider(
            client=client,
            base_url=TEST_BASE_URL,
            model=TEST_MODEL,
            max_tokens=0,
        )
    assert client.calls == []

