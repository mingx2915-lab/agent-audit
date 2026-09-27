"""Fixed offline retrieval comparison for the selected local Embedding engine."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from .domain import RetrievedDocument
from .retrieval import Retriever, RetrieverMetadata
from .schemas import CamelModel


@dataclass(frozen=True)
class RetrievalEvaluationQuery:
    """Repository-owned query and expected document used only after ranking."""

    case_id: str
    query: str
    expected_document_id: str


FIXED_RETRIEVAL_EVALUATION_CASES: Final[tuple[RetrievalEvaluationQuery, ...]] = (
    RetrievalEvaluationQuery(
        case_id="semantic_budget_allocation",
        query="各团队明年的钱应该怎么分配？",
        expected_document_id="doc_finance_budget_001",
    ),
    RetrievalEvaluationQuery(
        case_id="semantic_hr_lifecycle",
        query="同事加入或离开单位时要办哪些手续？",
        expected_document_id="doc_hr_handbook_001",
    ),
    RetrievalEvaluationQuery(
        case_id="semantic_product_capability",
        query="这家厂商能为其他公司解决什么问题？",
        expected_document_id="doc_product_overview_001",
    ),
    RetrievalEvaluationQuery(
        case_id="semantic_demo_boundary",
        query="测试时怎样避免影响生产系统？",
        expected_document_id="doc_demo_usage_guide_001",
    ),
    RetrievalEvaluationQuery(
        case_id="customer_service_expiry",
        query="远山的这笔服务单什么时候到期？",
        expected_document_id="doc_customer_contract_002",
    ),
    RetrievalEvaluationQuery(
        case_id="semantic_vendor_bypass",
        query="哪项外来材料藏着诱导助手违规的内容？",
        expected_document_id="doc_external_vendor_prompt_001",
    ),
)


class RetrievalEvaluationRequest(CamelModel):
    """Empty request body: the evaluation corpus is server-owned and fixed."""


class RetrievalRankedDocument(CamelModel):
    rank: int
    document_id: str
    title: str
    score: float


class RetrievalEvaluationCaseResult(CamelModel):
    case_id: str
    query: str
    expected_document_id: str
    tfidf_results: list[RetrievalRankedDocument]
    embedding_results: list[RetrievalRankedDocument]
    tfidf_expected_rank: int | None
    embedding_expected_rank: int | None


class RetrievalEvaluationMetrics(CamelModel):
    case_count: int
    tfidf_top1_hits: int
    embedding_top1_hits: int
    tfidf_mrr: float
    embedding_mrr: float


class RetrievalEvaluationResult(CamelModel):
    id: str
    selected_engine: Literal["embedding"]
    model_name: str
    dimensions: int
    indexed_document_count: int
    cases: list[RetrievalEvaluationCaseResult]
    metrics: RetrievalEvaluationMetrics


def _ranked_documents(results: Sequence[RetrievedDocument]) -> list[RetrievalRankedDocument]:
    """Convert the already-ranked Retriever output without changing its order."""

    ranked: list[RetrievalRankedDocument] = []
    for rank, result in enumerate(results, start=1):
        document = result.document
        score = result.score
        ranked.append(
            RetrievalRankedDocument(
                rank=rank,
                document_id=document.id,
                title=document.title,
                score=score,
            )
        )
    return ranked


def _expected_rank(
    results: list[RetrievalRankedDocument], expected_document_id: str
) -> int | None:
    for result in results:
        if result.document_id == expected_document_id:
            return result.rank
    return None


def _mrr(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1.0 / rank for rank in ranks if rank is not None) / len(ranks)


class RetrievalEvaluationRunner:
    """Run the fixed six-query TF-IDF versus Embedding comparison offline."""

    def __init__(
        self,
        *,
        tfidf_retriever: Retriever,
        embedding_retriever: Retriever,
    ) -> None:
        self._tfidf_retriever = tfidf_retriever
        self._embedding_retriever = embedding_retriever

    @staticmethod
    def _embedding_metadata(retriever: Retriever) -> RetrieverMetadata:
        metadata = retriever.metadata
        if (
            metadata.engine_id != "embedding"
            or not isinstance(metadata.model_name, str)
            or not metadata.model_name
            or metadata.dimensions is None
        ):
            raise ValueError("retrieval evaluation requires an embedding Retriever")
        return metadata

    def run(self) -> RetrievalEvaluationResult:
        """Return actual rankings and metrics; expected IDs are never sent to search."""

        metadata = self._embedding_metadata(self._embedding_retriever)
        cases: list[RetrievalEvaluationCaseResult] = []
        tfidf_ranks: list[int | None] = []
        embedding_ranks: list[int | None] = []
        for fixed_case in FIXED_RETRIEVAL_EVALUATION_CASES:
            # The result limit is the target's established TOP-3 retrieval
            # boundary. Ranking is complete before expected matching below.
            tfidf_ranked = _ranked_documents(
                self._tfidf_retriever.search(fixed_case.query, limit=3)
            )
            embedding_ranked = _ranked_documents(
                self._embedding_retriever.search(fixed_case.query, limit=3)
            )
            tfidf_rank = _expected_rank(tfidf_ranked, fixed_case.expected_document_id)
            embedding_rank = _expected_rank(embedding_ranked, fixed_case.expected_document_id)
            tfidf_ranks.append(tfidf_rank)
            embedding_ranks.append(embedding_rank)
            cases.append(
                RetrievalEvaluationCaseResult(
                    case_id=fixed_case.case_id,
                    query=fixed_case.query,
                    expected_document_id=fixed_case.expected_document_id,
                    tfidf_results=tfidf_ranked,
                    embedding_results=embedding_ranked,
                    tfidf_expected_rank=tfidf_rank,
                    embedding_expected_rank=embedding_rank,
                )
            )

        return RetrievalEvaluationResult(
            id=f"retrieval_evaluation_{uuid.uuid4().hex[:12]}",
            selected_engine="embedding",
            model_name=metadata.model_name,
            dimensions=metadata.dimensions,
            indexed_document_count=metadata.indexed_document_count,
            cases=cases,
            metrics=RetrievalEvaluationMetrics(
                case_count=len(cases),
                tfidf_top1_hits=sum(rank == 1 for rank in tfidf_ranks),
                embedding_top1_hits=sum(rank == 1 for rank in embedding_ranks),
                tfidf_mrr=_mrr(tfidf_ranks),
                embedding_mrr=_mrr(embedding_ranks),
            ),
        )


__all__ = [
    "FIXED_RETRIEVAL_EVALUATION_CASES",
    "RetrievalEvaluationCaseResult",
    "RetrievalEvaluationMetrics",
    "RetrievalEvaluationQuery",
    "RetrievalEvaluationRequest",
    "RetrievalEvaluationResult",
    "RetrievalEvaluationRunner",
    "RetrievalRankedDocument",
]
