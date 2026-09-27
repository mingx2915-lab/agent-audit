"""F-050 unit coverage for the fixed ``agent_audit_adapter.v1`` bridge.

All transports in this module are explicit test-only doubles.  They are
local objects injected into the production adapter and do not represent or
contact a real enterprise gateway.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest

from agent_audit_api.providers.agent_audit_adapter import (
    AGENT_AUDIT_ADAPTER_COMPLETIONS_PATH,
    AGENT_AUDIT_ADAPTER_MANIFEST_PATH,
    AGENT_AUDIT_ADAPTER_MODELS_PATH,
    AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION,
    AgentAuditAdapterInspectionError,
    AgentAuditAdapterProvider,
    inspect_agent_audit_adapter_endpoint,
    parse_agent_audit_adapter_manifest,
)
from agent_audit_api.providers.base import (
    LLMResponse,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
    ProviderUsage,
    ToolCall,
)


TEST_BASE_URL = "https://bridge.intra.example/team/v1"
TEST_MODEL = "enterprise-bridge-model"
TEST_SECRET = "f050-adapter-secret-test-only"


def _manifest(
    *,
    protocol: str = "agent_audit_adapter",
    version: str = AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION,
    capabilities: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "protocol": protocol,
        "protocolVersion": version,
        "capabilities": capabilities
        if capabilities is not None
        else {
            "text": True,
            "toolCalling": True,
            "structuredOutput": True,
            "usage": True,
        },
    }


def _models() -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": TEST_MODEL,
                "object": "model",
                "created": 1_725_000_000,
                "owned_by": "enterprise-platform",
            }
        ],
    }


@dataclass
class FakeInspectionResponse:
    """Test-only urllib response for manifest/model inspection."""

    payload: object
    status: int = 200
    closed: bool = False

    def read(self) -> bytes:
        if isinstance(self.payload, BaseException):
            raise self.payload
        return json.dumps(self.payload).encode("utf-8")

    def json(self) -> object:
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload

    def close(self) -> None:
        self.closed = True


@dataclass
class RecordingOpener:
    """Explicit test-only opener; it never performs network I/O."""

    responses: list[object]
    calls: list[tuple[str, str, dict[str, str], int]] = field(default_factory=list)

    def open(self, request, *, timeout: int) -> object:
        self.calls.append(
            (
                request.full_url,
                request.get_method(),
                dict(request.header_items()),
                timeout,
            )
        )
        if not self.responses:
            raise AssertionError("unexpected adapter inspection request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


@dataclass
class RecordingAdapterClient:
    """Explicit test-only async client for completion requests."""

    responses: list[object]
    calls: list[dict[str, object]] = field(default_factory=list)

    async def post(self, url: str, **request: object) -> object:
        self.calls.append({"url": url, **request})
        if not self.responses:
            raise AssertionError("unexpected adapter completion request")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _completion_response(
    *,
    content: str | None = "bridge response",
    tool_calls: list[dict[str, object]] | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "content": content,
        "toolCalls": [] if tool_calls is None else tool_calls,
        "usage": usage,
    }


def _header_value(headers: dict[str, str], name: str) -> str | None:
    """Read an injected urllib header case-insensitively."""

    wanted = name.lower()
    return next((value for key, value in headers.items() if key.lower() == wanted), None)


def _provider(
    client: RecordingAdapterClient,
    *,
    auth_mode: str = "none",
    credential: str | None = None,
) -> AgentAuditAdapterProvider:
    return AgentAuditAdapterProvider(
        client=client,
        base_url=TEST_BASE_URL,
        model=TEST_MODEL,
        auth_mode=auth_mode,
        credential=credential,
    )


def test_adapter_manifest_v1_and_capabilities_are_strictly_parsed() -> None:
    parsed = parse_agent_audit_adapter_manifest(_manifest())

    assert parsed.protocol == "agent_audit_adapter"
    assert parsed.protocol_version == AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION
    assert parsed.capabilities.model_dump(mode="json", by_alias=True) == {
        "text": True,
        "toolCalling": True,
        "structuredOutput": True,
        "usage": True,
    }


@pytest.mark.parametrize(
    "payload",
    [
        _manifest(version="agent_audit_adapter.v0"),
        _manifest(protocol="openai_compatible"),
        _manifest(capabilities={"text": True, "toolCalling": True}),
        _manifest(
            capabilities={
                "text": "true",
                "toolCalling": True,
                "structuredOutput": True,
                "usage": True,
            }
        ),
        {"protocol": "agent_audit_adapter", "protocolVersion": AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION},
    ],
)
def test_adapter_manifest_rejects_invalid_version_protocol_or_capability_shape(
    payload: object,
) -> None:
    with pytest.raises(AgentAuditAdapterInspectionError):
        parse_agent_audit_adapter_manifest(payload)


def test_adapter_inspection_reads_only_manifest_and_models_on_one_explicit_origin() -> None:
    manifest_response = FakeInspectionResponse(_manifest())
    models_response = FakeInspectionResponse(_models())
    opener = RecordingOpener([manifest_response, models_response])

    result = inspect_agent_audit_adapter_endpoint(
        base_url="https://bridge.intra.example/team/",
        auth_mode="none",
        opener=opener.open,
    )

    assert result.status == "available"
    assert result.protocol == "agent_audit_adapter"
    assert result.base_url == TEST_BASE_URL
    assert result.models_enumerated is True
    assert [model.id for model in result.models] == [TEST_MODEL]
    assert result.protocol_version == AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION
    assert result.capabilities == {
        "text": True,
        "toolCalling": True,
        "structuredOutput": True,
        "usage": True,
    }
    assert result.manifest == _manifest()
    assert [call[0] for call in opener.calls] == [
        f"{TEST_BASE_URL}{AGENT_AUDIT_ADAPTER_MANIFEST_PATH}",
        f"{TEST_BASE_URL}{AGENT_AUDIT_ADAPTER_MODELS_PATH}",
    ]
    assert all(call[1] == "GET" and call[3] == 5 for call in opener.calls)
    assert all(
        _header_value(call[2], "accept") == "application/json"
        and _header_value(call[2], "content-type") == "application/json"
        for call in opener.calls
    )
    assert manifest_response.closed is True
    assert models_response.closed is True


def test_adapter_inspection_x_api_key_is_sent_only_to_fixed_requests_and_not_result() -> None:
    opener = RecordingOpener(
        [FakeInspectionResponse(_manifest()), FakeInspectionResponse(_models())]
    )

    result = inspect_agent_audit_adapter_endpoint(
        base_url=TEST_BASE_URL,
        auth_mode="x_api_key",
        credential=TEST_SECRET,
        opener=opener.open,
    )

    assert result.status == "available"
    assert all(
        _header_value(call[2], "x-api-key") == TEST_SECRET for call in opener.calls
    )
    assert TEST_SECRET not in json.dumps(result.model_dump(mode="json"), default=str)


def test_adapter_invalid_manifest_stops_before_models_and_does_not_guess_protocol() -> None:
    opener = RecordingOpener([FakeInspectionResponse(_manifest(version="v0"))])

    result = inspect_agent_audit_adapter_endpoint(
        base_url=TEST_BASE_URL,
        opener=opener.open,
    )

    assert result.status == "unavailable"
    assert result.protocol is None
    assert result.models == []
    assert result.models_enumerated is False
    assert len(opener.calls) == 1
    assert opener.calls[0][0].endswith(AGENT_AUDIT_ADAPTER_MANIFEST_PATH)


def test_adapter_redirect_is_not_followed_and_neighbour_origin_is_never_contacted() -> None:
    redirect = HTTPError(
        f"{TEST_BASE_URL}{AGENT_AUDIT_ADAPTER_MANIFEST_PATH}",
        307,
        "redirect",
        {"Location": "https://outside.example/v1/manifest"},
        None,
    )
    opener = RecordingOpener([redirect])

    result = inspect_agent_audit_adapter_endpoint(
        base_url=TEST_BASE_URL,
        opener=opener.open,
    )

    assert result.status == "unavailable"
    assert "307" in (result.diagnostic or "")
    assert "outside.example" not in (result.diagnostic or "")
    assert [call[0] for call in opener.calls] == [
        f"{TEST_BASE_URL}{AGENT_AUDIT_ADAPTER_MANIFEST_PATH}"
    ]


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError(
            f"{TEST_BASE_URL}{AGENT_AUDIT_ADAPTER_MANIFEST_PATH}",
            401,
            "unauthorized",
            {},
            None,
        ),
        HTTPError(
            f"{TEST_BASE_URL}{AGENT_AUDIT_ADAPTER_MANIFEST_PATH}",
            502,
            "upstream",
            {},
            None,
        ),
        URLError("synthetic adapter unavailable"),
        TimeoutError("synthetic adapter timeout"),
    ],
)
def test_adapter_inspection_failure_is_one_attempt_without_fallback(failure: Exception) -> None:
    opener = RecordingOpener([failure])

    result = inspect_agent_audit_adapter_endpoint(
        base_url=TEST_BASE_URL,
        opener=opener.open,
    )

    assert result.status == "unavailable"
    assert len(opener.calls) == 1
    assert "/api/tags" not in str(opener.calls)
    assert "/v1/models" not in str(opener.calls)


def test_adapter_completion_sends_canonical_messages_tools_and_usage_response() -> None:
    client = RecordingAdapterClient(
        [
            FakeInspectionResponse(
                _completion_response(
                    content="bridge answer",
                    tool_calls=[
                        {
                            "id": "bridge-call-001",
                            "name": "mock_customer_lookup",
                            "arguments": {"customerId": "customer_001"},
                        }
                    ],
                    usage={"inputTokens": 21, "outputTokens": 9, "totalTokens": 30},
                )
            )
        ]
    )
    provider = _provider(client)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "mock_customer_lookup",
                "description": "查询合成客户",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    result = asyncio.run(
        provider.complete(
            [
                {"role": "system", "content": "遵守规则"},
                {"role": "user", "content": "查询客户"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "previous-call",
                            "function": {
                                "name": "mock_customer_lookup",
                                "arguments": '{"customerId":"customer_001"}',
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "previous-call",
                    "name": "mock_customer_lookup",
                    "content": '{"name":"合成客户"}',
                },
            ],
            tools=tools,
        )
    )

    assert result == LLMResponse(
        content="bridge answer",
        tool_calls=(
            ToolCall(
                id="bridge-call-001",
                name="mock_customer_lookup",
                arguments={"customerId": "customer_001"},
            ),
        ),
        usage=ProviderUsage(input_tokens=21, output_tokens=9, total_tokens=30),
    )
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request["url"] == f"{TEST_BASE_URL}{AGENT_AUDIT_ADAPTER_COMPLETIONS_PATH}"
    assert request["timeout"] == 30
    assert request["headers"] == {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    assert request["json"] == {
        "protocolVersion": AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION,
        "model": TEST_MODEL,
        "maxTokens": 4096,
        "messages": [
            {"role": "system", "content": "遵守规则"},
            {"role": "user", "content": "查询客户"},
            {
                "role": "assistant",
                "content": None,
                "toolCalls": [
                    {
                        "id": "previous-call",
                        "name": "mock_customer_lookup",
                        "arguments": {"customerId": "customer_001"},
                    }
                ],
            },
            {
                "role": "tool",
                "content": '{"name":"合成客户"}',
                "toolCallId": "previous-call",
                "name": "mock_customer_lookup",
            },
        ],
        "tools": [
            {
                "name": "mock_customer_lookup",
                "description": "查询合成客户",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ],
    }


@pytest.mark.parametrize(
    ("auth_mode", "header_name", "header_value"),
    [
        ("bearer", "Authorization", f"Bearer {TEST_SECRET}"),
        ("x_api_key", "x-api-key", TEST_SECRET),
    ],
)
def test_adapter_auth_headers_are_fixed_and_secret_is_not_in_response(
    auth_mode: str,
    header_name: str,
    header_value: str,
) -> None:
    client = RecordingAdapterClient(
        [FakeInspectionResponse(_completion_response(content="ok"))]
    )
    result = asyncio.run(
        _provider(client, auth_mode=auth_mode, credential=TEST_SECRET).complete(
            [{"role": "user", "content": "测试"}]
        )
    )

    headers = client.calls[0]["headers"]
    assert isinstance(headers, dict)
    assert headers[header_name] == header_value
    assert TEST_SECRET not in json.dumps(result, default=str, ensure_ascii=False)


@pytest.mark.parametrize("auth_mode", ["bearer", "x_api_key"])
def test_adapter_missing_credential_fails_before_completion_request(auth_mode: str) -> None:
    client = RecordingAdapterClient([])

    with pytest.raises(ProviderConfigurationError, match="credential is not configured"):
        asyncio.run(
            _provider(client, auth_mode=auth_mode).complete(
                [{"role": "user", "content": "测试"}]
            )
        )

    assert client.calls == []


@pytest.mark.parametrize("status_code", [401, 500, 502, 503])
def test_adapter_completion_http_failures_are_single_attempts_without_fallback(
    status_code: int,
) -> None:
    client = RecordingAdapterClient(
        [FakeInspectionResponse({"error": "synthetic"}, status=status_code)]
    )

    with pytest.raises(ProviderUnavailableError, match=f"HTTP {status_code}") as raised:
        asyncio.run(
            _provider(client, auth_mode="x_api_key", credential=TEST_SECRET).complete(
                [{"role": "user", "content": "测试"}]
            )
        )

    assert len(client.calls) == 1
    # The credential necessarily crosses the injected transport boundary;
    # only public errors/responses must not echo it.
    assert TEST_SECRET not in str(raised.value)


def test_adapter_timeout_is_one_attempt_and_has_no_fallback() -> None:
    client = RecordingAdapterClient([TimeoutError("synthetic timeout")])

    with pytest.raises(ProviderUnavailableError, match="request failed"):
        asyncio.run(
            _provider(client).complete([{"role": "user", "content": "测试"}])
        )

    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        _completion_response(content=None),
        _completion_response(
            content="ok",
            usage={"inputTokens": 4, "outputTokens": 3, "totalTokens": 99},
        ),
        _completion_response(
            content="ok",
            tool_calls=[{"id": "", "name": "tool", "arguments": {}}],
        ),
        {"content": "ok", "toolCalls": "not-an-array", "usage": None},
    ],
)
def test_adapter_malformed_completion_json_or_dto_fails_without_repair(
    payload: object,
) -> None:
    client = RecordingAdapterClient([FakeInspectionResponse(payload)])

    with pytest.raises(ProviderResponseError):
        asyncio.run(
            _provider(client).complete([{"role": "user", "content": "测试"}])
        )

    assert len(client.calls) == 1


def test_adapter_malformed_json_body_fails_without_second_request() -> None:
    client = RecordingAdapterClient(
        [FakeInspectionResponse(ValueError("not JSON"))]
    )

    with pytest.raises(ProviderResponseError, match="not valid JSON"):
        asyncio.run(
            _provider(client).complete([{"role": "user", "content": "测试"}])
        )

    assert len(client.calls) == 1


def test_adapter_invalid_input_shape_fails_before_http_request() -> None:
    client = RecordingAdapterClient([])

    with pytest.raises(ProviderResponseError, match="invalid role"):
        asyncio.run(
            _provider(client).complete([{"role": "developer", "content": "测试"}])
        )

    assert client.calls == []
