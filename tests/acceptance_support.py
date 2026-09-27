"""Deterministic dependencies shared by the F-025 Acceptance tests.

The Acceptance Runner deliberately receives the same repository-owned tools,
plans, Ground Truth catalog, and test Provider chain used by the existing
benchmark tests.  The only additional test boundary is a small explicit
readiness/variant response in the Provider and a deterministic in-memory
Embedding index so no external model is loaded during pytest or Playwright.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from agent_audit_api.providers.base import LLMResponse, ToolCall
from agent_audit_api.retrieval import EmbeddingRetriever
from tests.benchmark_support import GroundTruthProvider
from agent_audit_api.demo_data import load_demo_data


READINESS_TOOL_NAME = "agent_audit_readiness_probe"
READINESS_NONCE = "agent-audit-readiness"


@dataclass
class AcceptanceProvider(GroundTruthProvider):
    """Existing deterministic benchmark Provider plus F-025 probes/variants."""

    # ``provider_metadata`` intentionally reads this class attribute for an
    # injected test double; no credential or external model is involved.
    model: str = "test-acceptance-provider"

    def _record(self, messages: Any, tools: Any, response: LLMResponse) -> LLMResponse:
        self.calls.append(
            {
                "messages": tuple(dict(message) for message in messages),
                "tools": tuple(tools or ()),
                "response": response,
            }
        )
        return response

    @staticmethod
    def _contains(messages: Any, phrase: str) -> bool:
        return any(
            phrase in str(message.get("content") or "")
            for message in messages
            if isinstance(message, Mapping)
        )

    @staticmethod
    def _tool_names(tools: Any) -> set[str]:
        names: set[str] = set()
        for tool in tools or ():
            if not isinstance(tool, Mapping):
                continue
            function = tool.get("function")
            if isinstance(function, Mapping) and isinstance(function.get("name"), str):
                names.add(function["name"])
        return names

    async def complete(self, messages, tools=None) -> LLMResponse:
        call_number = len(self.calls) + 1
        tool_names = self._tool_names(tools)

        if READINESS_TOOL_NAME in tool_names:
            return self._record(
                messages,
                tools,
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id=f"acceptance_readiness_call_{call_number}",
                            name=READINESS_TOOL_NAME,
                            arguments={"nonce": READINESS_NONCE},
                        ),
                    ),
                    usage=self._usage(call_number),
                ),
            )

        if self._contains(messages, "strict JSON readiness probe"):
            return self._record(
                messages,
                tools,
                LLMResponse(
                    content=json.dumps(
                        {"status": "ready", "nonce": READINESS_NONCE},
                        separators=(",", ":"),
                    ),
                    usage=self._usage(call_number),
                ),
            )

        if self._contains(messages, "Connectivity probe"):
            return self._record(
                messages,
                tools,
                LLMResponse(
                    content="固定 Acceptance connectivity 响应",
                    usage=self._usage(call_number),
                ),
            )

        # The Attack Provider receives the baseline JSON from the existing
        # bounded Red-Team generator.  Keep its target metadata untouched and
        # vary only the allowed message/reason fields.
        if messages:
            candidate = messages[-1].get("content") if isinstance(messages[-1], Mapping) else None
            if isinstance(candidate, str):
                try:
                    payload = json.loads(candidate)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, Mapping) and isinstance(payload.get("baseline"), Mapping):
                    baseline = payload["baseline"]
                    return self._record(
                        messages,
                        tools,
                        LLMResponse(
                            content=json.dumps(
                                {
                                    "message": f"{baseline['message']}（固定 Acceptance 变体）",
                                    "mutationReason": "依据上一轮真实 Trace 生成固定 Acceptance 变体",
                                },
                                ensure_ascii=False,
                            ),
                            usage=self._usage(call_number),
                        ),
                    )

        return await super().complete(messages, tools=tools)


@dataclass
class DeterministicAcceptanceEmbedder:
    """A local, explicit 512-dimensional embedder for fixed retrieval cases."""

    document_inputs: list[tuple[str, ...]] = field(default_factory=list)
    query_inputs: list[str] = field(default_factory=list)

    @staticmethod
    def _unit(index: int) -> tuple[float, ...]:
        values = [0.0] * 512
        values[index % 512] = 1.0
        return tuple(values)

    def embed(self, documents: Sequence[str]) -> Iterable[Sequence[float]]:
        self.document_inputs.append(tuple(documents))
        return tuple(self._unit(index) for index, _ in enumerate(documents))

    def query_embed(self, query: str) -> Iterable[Sequence[float]]:
        self.query_inputs.append(query)
        expected_by_query = {
            "各团队明年的钱应该怎么分配？": "doc_finance_budget_001",
            "同事加入或离开单位时要办哪些手续？": "doc_hr_handbook_001",
            "这家厂商能为其他公司解决什么问题？": "doc_product_overview_001",
            "测试时怎样避免影响生产系统？": "doc_demo_usage_guide_001",
            "远山的这笔服务单什么时候到期？": "doc_customer_contract_002",
            "哪项外来材料藏着诱导助手违规的内容？": "doc_external_vendor_prompt_001",
        }
        documents = load_demo_data().documents
        document_positions = {
            document.id: position for position, document in enumerate(documents)
        }
        # Target requests may mention both an untrusted source and the
        # confidential resource it is trying to reach.  Give each explicitly
        # named document a positive coordinate so the normal top-3 boundary
        # preserves both real candidates for Contract authorization.
        indices = [
            position
            for document_id, position in document_positions.items()
            if document_id in query
        ]
        if "Atlas Vendor" in query:
            indices.extend(
                position
                for document_id, position in document_positions.items()
                if document_id in {
                    "doc_external_vendor_prompt_001",
                    "doc_finance_budget_001",
                }
            )
        if "财务预算" in query or "预算摘要" in query:
            indices.append(document_positions["doc_finance_budget_001"])
        indices = list(dict.fromkeys(indices))
        if not indices:
            expected_document_id = expected_by_query.get(query)
            indices = [document_positions.get(expected_document_id, 0)]
        values = [0.0] * 512
        for index in indices:
            values[index % 512] = 1.0
        return (tuple(values),)


def make_acceptance_embedding_retriever() -> EmbeddingRetriever:
    """Construct an explicit no-network embedding Retriever for F-025 tests."""

    return EmbeddingRetriever(
        load_demo_data().documents,
        embedder=DeterministicAcceptanceEmbedder(),
    )


__all__ = [
    "AcceptanceProvider",
    "DeterministicAcceptanceEmbedder",
    "READINESS_NONCE",
    "READINESS_TOOL_NAME",
    "make_acceptance_embedding_retriever",
]
