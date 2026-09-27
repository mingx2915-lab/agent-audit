"""Deterministic Test-only API server for the browser E2E suite.

The browser still exercises the production ``create_app`` wiring and all Scan,
Trace, Finding, SQLite, and persisted Replay code paths. Only the two model
boundaries are replaced with explicit, local providers; the primary Retriever
is a deterministic local embedding double while the production Acceptance
Runner keeps its existing TF-IDF comparison Retriever.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from types import SimpleNamespace


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_API_SOURCE_ROOT = _REPOSITORY_ROOT / "apps" / "api" / "src"
if str(_API_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_SOURCE_ROOT))

from agent_audit_api.history import SQLiteAuditRunRepository  # noqa: E402
from agent_audit_api.main import create_app  # noqa: E402
from agent_audit_api.app_paths import resolve_app_paths  # noqa: E402
from agent_audit_api import provider_setup as provider_setup_module  # noqa: E402
from agent_audit_api.providers.base import (  # noqa: E402
    LLMResponse,
    ToolCall,
    ProviderUnavailableError,
)
from agent_audit_api.providers.ollama import OllamaProvider  # noqa: E402
from agent_audit_api.providers.openai_compatible import OpenAICompatibleProvider  # noqa: E402
from agent_audit_api.readiness import (  # noqa: E402
    _READINESS_NONCE,
    _READINESS_TOOL_NAME,
)
from agent_audit_api.workspace import WorkspaceService  # noqa: E402
from tests.acceptance_support import (  # noqa: E402
    AcceptanceProvider,
    make_acceptance_embedding_retriever,
)


@dataclass
class E2EScanVariantProvider:
    """Generate one deterministic JSON variant from the real scan baseline."""

    model: str = "test-e2e-variant-generator"
    calls: list[tuple[Any, Any]] = field(default_factory=list)

    async def complete(self, messages, tools=None) -> LLMResponse:
        self.calls.append((messages, tools))
        if not messages:
            raise AssertionError("E2E variant provider received no messages")
        probe_content = " ".join(
            message.get("content") or ""
            for message in messages
            if isinstance(message, dict)
        )
        if "Connectivity probe" in probe_content:
            return LLMResponse(content="固定浏览器 E2E connectivity 响应")
        if "strict JSON readiness probe" in probe_content:
            return LLMResponse(
                content=json.dumps(
                    {"status": "ready", "nonce": "agent-audit-readiness"},
                    separators=(",", ":"),
                )
            )
        baseline_payload = json.loads(messages[-1]["content"])
        baseline = baseline_payload["baseline"]
        return LLMResponse(
            content=json.dumps(
                {
                    "message": f"{baseline['message']}（浏览器 E2E 固定变体）",
                    "mutationReason": "依据上一轮真实 Trace 生成固定浏览器测试变体",
                },
                ensure_ascii=False,
            )
        )


@dataclass
class E2EScanTargetProvider(AcceptanceProvider):
    """Reuse the fixed benchmark Provider while retaining the old 502 case."""

    async def complete(self, messages, tools=None) -> LLMResponse:
        user_messages = [
            message.get("content") or ""
            for message in messages
            if isinstance(message, dict) and message.get("role") == "user"
        ]
        # The legacy browser regression intentionally selects the vulnerable
        # customer-tool Scan Plan.  Its real Red-Team variant has this marker;
        # fixed Acceptance benchmark cases use the unmodified repository
        # message and therefore still exercise the full deterministic Provider.
        if any(
            "mock_customer_lookup" in content
            and "浏览器 E2E 固定变体" in content
            for content in user_messages
        ):
            raise ProviderUnavailableError("synthetic E2E target provider unavailable")
        return await super().complete(messages, tools=tools)


@dataclass
class _E2ETagsResponse:
    """Response object for the local-only discovery test transport."""

    payload: dict[str, object]
    closed: bool = False

    status: int = 200

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")

    def close(self) -> None:
        self.closed = True


@dataclass
class E2EDiscoveryTransport:
    """Return synthetic local models, then a deterministic failure.

    This is installed only in the Playwright support process.  The production
    route remains responsible for constructing the fixed loopback request and
    parsing its response; no browser route is fulfilled with fake business
    results.
    """

    calls: list[tuple[str, int]] = field(default_factory=list)

    def open(self, request, *, timeout: int) -> _E2ETagsResponse:
        self.calls.append((request.full_url, timeout))
        if request.full_url.rstrip("/").endswith("/api/tags"):
            local_discovery_calls = sum(
                url.rstrip("/").endswith("/api/tags")
                for url, _ in self.calls
            )
            if local_discovery_calls <= 2:
                return _E2ETagsResponse(
                    {
                        "models": [
                            {
                                "name": "qwen3:8b",
                                "size": 8_000,
                                "modified_at": "2026-08-28T00:00:00Z",
                            },
                            {
                                "name": "llama3.2:3b",
                                "size": 3_000,
                                "modified_at": "2026-08-28T00:00:00Z",
                            },
                        ]
                    }
                )
            raise OSError("synthetic E2E Ollama discovery unavailable")

        if request.full_url.rstrip("/").endswith("/models"):
            if "manual.runtime.intra.example" in request.full_url:
                return _E2ETagsResponse(
                    {
                        "object": "list",
                        "data": [],
                    }
                )
            return _E2ETagsResponse(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": "enterprise-model",
                            "object": "model",
                            "created": 1_725_000_000,
                            "owned_by": "platform-team",
                        }
                    ],
                }
            )

        raise OSError("synthetic E2E provider endpoint unavailable")


def _raw_ollama_response(
    *,
    content: str | None = None,
    tool_calls: tuple[ToolCall, ...] = (),
) -> object:
    raw_calls = [
        SimpleNamespace(
            id=call.id,
            function=SimpleNamespace(
                name=call.name,
                arguments=json.dumps(dict(call.arguments), separators=(",", ":")),
            ),
        )
        for call in tool_calls
    ]
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=raw_calls),
            )
        ]
    )


@dataclass
class E2EOllamaCompletions:
    """OpenAI-compatible local double used after the setup flow confirms."""

    calls: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def _user_text(messages: Any) -> str:
        return "\n".join(
            str(message.get("content") or "")
            for message in messages or ()
            if isinstance(message, dict) and message.get("role") == "user"
        )

    @staticmethod
    def _tool_names(tools: Any) -> set[str]:
        names: set[str] = set()
        for tool in tools or ():
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                names.add(function["name"])
        return names

    async def create(self, **request: Any) -> object:
        self.calls.append(request)
        messages = request.get("messages", [])
        tools = request.get("tools", [])
        tool_names = self._tool_names(tools)
        user_text = self._user_text(messages)
        all_text = "\n".join(
            str(message.get("content") or "")
            for message in messages or ()
            if isinstance(message, dict)
        )

        if _READINESS_TOOL_NAME in tool_names:
            return _raw_ollama_response(
                tool_calls=(
                    ToolCall(
                        id=f"e2e-readiness-{len(self.calls)}",
                        name=_READINESS_TOOL_NAME,
                        arguments={"nonce": _READINESS_NONCE},
                    ),
                )
            )
        if "strict JSON readiness probe" in all_text:
            return _raw_ollama_response(
                content=json.dumps(
                    {"status": "ready", "nonce": _READINESS_NONCE},
                    separators=(",", ":"),
                )
            )
        if "Connectivity probe" in user_text:
            return _raw_ollama_response(content="固定浏览器 E2E connectivity 响应")

        # The real bounded variant generator sends a JSON baseline and only
        # expects a structured message/mutation response.
        if messages and isinstance(messages[-1], dict):
            candidate = messages[-1].get("content")
            if isinstance(candidate, str):
                try:
                    payload = json.loads(candidate)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict) and isinstance(payload.get("baseline"), dict):
                    baseline = payload["baseline"]
                    return _raw_ollama_response(
                        content=json.dumps(
                            {
                                "message": f"{baseline['message']}（浏览器 E2E 固定变体）",
                                "mutationReason": "依据上一轮真实 Trace 生成固定浏览器测试变体",
                            },
                            ensure_ascii=False,
                        )
                    )

        if "mock_mail_send" in tool_names and "mock_mail_send" in user_text:
            return _raw_ollama_response(
                tool_calls=(
                    ToolCall(
                        id=f"e2e-mail-{len(self.calls)}",
                        name="mock_mail_send",
                        arguments={
                            "to": "audit@external-sink.demo.local",
                            "subject": "合成审计摘要",
                            "body": "浏览器 E2E synthetic summary",
                            "resourceIds": [
                                "doc_external_vendor_prompt_001",
                                "doc_finance_budget_001",
                            ],
                            "approved": False,
                        },
                    ),
                )
            )
        return _raw_ollama_response(content="固定浏览器 E2E Ollama 响应")


@dataclass
class E2EOllamaClient:
    completions: E2EOllamaCompletions = field(default_factory=E2EOllamaCompletions)

    def __post_init__(self) -> None:
        self.chat = type("Chat", (), {"completions": self.completions})()


def _e2e_ollama_client(provider: OllamaProvider) -> E2EOllamaClient:
    """Explicit test-only replacement for the SDK/network boundary."""

    return _E2E_OLLAMA_CLIENT


def _e2e_openai_compatible_client(
    provider: OpenAICompatibleProvider,
) -> E2EOllamaClient:
    """Use the same explicit local completion double for enterprise candidates."""

    return _E2E_OLLAMA_CLIENT


_E2E_DISCOVERY_TRANSPORT = E2EDiscoveryTransport()
_E2E_OLLAMA_CLIENT = E2EOllamaClient()
provider_setup_module._NO_REDIRECT_OPENER = _E2E_DISCOVERY_TRANSPORT
OllamaProvider._create_client = _e2e_ollama_client  # type: ignore[method-assign]
OpenAICompatibleProvider._create_client = _e2e_openai_compatible_client  # type: ignore[method-assign]


def e2e_history_path() -> Path:
    """Resolve a temporary history path without touching the repository data tree."""

    configured_path = os.environ.get("AGENT_AUDIT_E2E_DB_PATH", "").strip()
    if configured_path:
        return Path(configured_path)
    temporary_directory = Path(tempfile.mkdtemp(prefix="agent-audit-e2e-"))
    return temporary_directory / "history.sqlite3"


def create_e2e_app(history_path: Path | None = None):
    """Build the real API application with only explicit deterministic doubles."""

    target_provider = E2EScanTargetProvider()
    variant_provider = E2EScanVariantProvider()
    repository = SQLiteAuditRunRepository(history_path or e2e_history_path())
    app_paths = resolve_app_paths(repository.path.parent / "app-home")
    # Document import is a production Workspace route.  Give the browser suite
    # an isolated, seed-backed Workspace so the E2E path exercises the same
    # active catalog, Contract and hot Retriever slot as Desktop/runtime use.
    workspace_root = Path(tempfile.mkdtemp(prefix="agent-audit-e2e-workspace-"))
    workspace = WorkspaceService(app_paths).create(
        workspace_root,
        "E2E Workspace",
        seed_dir=_REPOSITORY_ROOT / "data" / "demo",
    )
    return create_app(
        provider=target_provider,
        attack_provider=variant_provider,
        retriever=make_acceptance_embedding_retriever(),
        history_repository=repository,
        app_paths=app_paths,
        workspace=workspace,
    )


app = create_e2e_app()


if __name__ == "__main__":  # pragma: no cover - exercised by Playwright webServer
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("AGENT_AUDIT_E2E_HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENT_AUDIT_E2E_PORT", "8000")),
        log_level="warning",
    )

__all__ = [
    "E2EScanTargetProvider",
    "E2EScanVariantProvider",
    "app",
    "create_e2e_app",
    "e2e_history_path",
]
