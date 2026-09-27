"""Unit coverage for the F-017 permission-aware embedding retriever."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import pytest

from agent_audit_api.domain import KnowledgeDocument, RetrievedDocument
from agent_audit_api.retrieval import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    EmbeddingRetriever,
    Retriever,
    RetrieverInferenceError,
    RetrieverMetadata,
)
from agent_audit_api.retrieval_evaluation import (
    FIXED_RETRIEVAL_EVALUATION_CASES,
    RetrievalEvaluationRunner,
)


def _vector(*values: float) -> tuple[float, ...]:
    if len(values) > EMBEDDING_DIMENSIONS:
        raise ValueError("test vector is larger than the locked dimension")
    return tuple(values) + (0.0,) * (EMBEDDING_DIMENSIONS - len(values))


def _documents() -> tuple[KnowledgeDocument, ...]:
    return (
        KnowledgeDocument(
            id="doc_zeta",
            title="Zeta title",
            content="Zeta body",
            owner_id=None,
            labels=("public",),
            source_id="source_zeta",
            source_type="knowledge_base",
            trust_level="trusted",
        ),
        KnowledgeDocument(
            id="doc_alpha",
            title="Alpha title",
            content="Alpha body",
            owner_id=None,
            labels=("public",),
            source_id="source_alpha",
            source_type="knowledge_base",
            trust_level="trusted",
        ),
        KnowledgeDocument(
            id="doc_beta",
            title="Beta title",
            content="Beta body",
            owner_id=None,
            labels=("public",),
            source_id="source_beta",
            source_type="knowledge_base",
            trust_level="trusted",
        ),
    )


@dataclass
class FakeEmbedder:
    document_vectors: list[Sequence[float]]
    query_vectors: dict[str, list[Sequence[float]]]
    document_inputs: list[tuple[str, ...]] = field(default_factory=list)
    query_inputs: list[str] = field(default_factory=list)

    def embed(self, documents: Sequence[str]) -> Iterable[Sequence[float]]:
        self.document_inputs.append(tuple(documents))
        return tuple(self.document_vectors)

    def query_embed(self, query: str) -> Iterable[Sequence[float]]:
        self.query_inputs.append(query)
        return tuple(self.query_vectors[query])


def test_embedding_retriever_uses_title_and_content_and_stable_cosine_ties() -> None:
    documents = _documents()
    embedder = FakeEmbedder(
        document_vectors=[
            _vector(1.0, 0.0),
            _vector(1.0, 0.0),
            _vector(0.0, 1.0),
        ],
        query_vectors={"semantic query": [_vector(1.0, 0.0)]},
    )
    retriever = EmbeddingRetriever(documents, embedder=embedder)

    results = retriever.search("semantic query", limit=3)

    assert isinstance(retriever, Retriever)
    assert [item.document.id for item in results] == [
        "doc_alpha",
        "doc_zeta",
        "doc_beta",
    ]
    assert results[0].score == pytest.approx(1.0)
    assert results[1].score == pytest.approx(1.0)
    assert results[2].score == pytest.approx(0.0)
    assert embedder.document_inputs == [
        (
            "Zeta title\nZeta body",
            "Alpha title\nAlpha body",
            "Beta title\nBeta body",
        )
    ]
    assert embedder.query_inputs == ["semantic query"]
    assert retriever.metadata.engine_id == "embedding"
    assert retriever.metadata.model_name == EMBEDDING_MODEL_NAME
    assert retriever.metadata.dimensions == EMBEDDING_DIMENSIONS
    assert retriever.metadata.indexed_document_count == 3


def test_embedding_retriever_honors_limit_and_caches_document_index() -> None:
    documents = _documents()
    embedder = FakeEmbedder(
        document_vectors=[_vector(1.0), _vector(0.5), _vector(0.25)],
        query_vectors={
            "first": [_vector(1.0)],
            "second": [_vector(0.5)],
        },
    )
    retriever = EmbeddingRetriever(documents, embedder=embedder)

    assert retriever.search("first", limit=1)
    assert len(retriever.search("second", limit=2)) == 2
    assert retriever.search("second", limit=0) == []
    assert len(embedder.document_inputs) == 1
    assert embedder.query_inputs == ["first", "second"]


@pytest.mark.parametrize("query", ["", "   "])
def test_embedding_retriever_rejects_empty_query(query: str) -> None:
    embedder = FakeEmbedder(document_vectors=[], query_vectors={})
    retriever = EmbeddingRetriever(_documents(), embedder=embedder)

    with pytest.raises(ValueError, match="query must not be empty"):
        retriever.search(query)


def test_embedding_retriever_rejects_non_string_query() -> None:
    embedder = FakeEmbedder(document_vectors=[], query_vectors={})
    retriever = EmbeddingRetriever(_documents(), embedder=embedder)

    with pytest.raises(TypeError, match="query must be a string"):
        retriever.search(123)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "document_vectors",
    [
        [],
        [_vector(1.0), _vector(1.0)],
        [_vector(1.0), [0.0] * (EMBEDDING_DIMENSIONS - 1), _vector(1.0)],
        [
            _vector(1.0),
            _vector(float("nan")),
            _vector(1.0),
        ],
        [
            _vector(1.0),
            _vector(float("inf")),
            _vector(1.0),
        ],
    ],
)
def test_embedding_retriever_rejects_document_count_dimension_and_nonfinite_errors(
    document_vectors: list[Sequence[float]],
) -> None:
    embedder = FakeEmbedder(
        document_vectors=document_vectors,
        query_vectors={"query": [_vector(1.0)]},
    )
    retriever = EmbeddingRetriever(_documents(), embedder=embedder)

    with pytest.raises(RetrieverInferenceError):
        retriever.search("query")


@pytest.mark.parametrize(
    "query_vectors",
    [
        [],
        [_vector(1.0), _vector(1.0)],
        [[0.0] * (EMBEDDING_DIMENSIONS - 1)],
        [_vector(float("nan"))],
        [_vector(float("inf"))],
    ],
)
def test_embedding_retriever_rejects_query_count_dimension_and_nonfinite_errors(
    query_vectors: list[Sequence[float]],
) -> None:
    embedder = FakeEmbedder(
        document_vectors=[_vector(1.0)] * len(_documents()),
        query_vectors={"query": query_vectors},
    )
    retriever = EmbeddingRetriever(_documents(), embedder=embedder)

    with pytest.raises(RetrieverInferenceError):
        retriever.search("query")


def test_embedding_retriever_does_not_accept_boolean_vector_values() -> None:
    invalid = [True] + [0.0] * (EMBEDDING_DIMENSIONS - 1)
    embedder = FakeEmbedder(
        document_vectors=[invalid, _vector(1.0), _vector(1.0)],
        query_vectors={"query": [_vector(1.0)]},
    )
    retriever = EmbeddingRetriever(_documents(), embedder=embedder)

    with pytest.raises(RetrieverInferenceError, match="non-numeric"):
        retriever.search("query")


@dataclass
class RecordingEvaluationRetriever:
    """Retriever double that exposes the runner's query-only boundary."""

    engine_id: str
    calls: list[tuple[str, int]] = field(default_factory=list)

    @property
    def model_name(self) -> str | None:
        return EMBEDDING_MODEL_NAME if self.engine_id == "embedding" else None

    @property
    def dimensions(self) -> int | None:
        return EMBEDDING_DIMENSIONS if self.engine_id == "embedding" else None

    @property
    def indexed_document_count(self) -> int:
        return len(FIXED_RETRIEVAL_EVALUATION_CASES)

    @property
    def metadata(self) -> RetrieverMetadata:
        return RetrieverMetadata(
            engine_id=self.engine_id,  # type: ignore[arg-type]
            model_name=self.model_name,
            dimensions=self.dimensions,
            indexed_document_count=self.indexed_document_count,
        )

    def search(self, query: str, limit: int = 3) -> list[RetrievedDocument]:
        self.calls.append((query, limit))
        case = next(item for item in FIXED_RETRIEVAL_EVALUATION_CASES if item.query == query)
        expected = KnowledgeDocument(
            id=case.expected_document_id,
            title="Expected document",
            content="synthetic expected content",
            owner_id=None,
            labels=("public",),
            source_id=f"source_{case.expected_document_id}",
            source_type="knowledge_base",
            trust_level="trusted",
        )
        other = KnowledgeDocument(
            id=f"doc_other_{case.case_id}",
            title="Other document",
            content="synthetic other content",
            owner_id=None,
            labels=("public",),
            source_id=f"source_other_{case.case_id}",
            source_type="knowledge_base",
            trust_level="trusted",
        )
        return [
            RetrievedDocument(document=other, score=1.0),
            RetrievedDocument(document=expected, score=0.5),
        ][:limit]


def test_retrieval_evaluation_ranks_actual_results_without_passing_expected_to_search() -> None:
    tfidf = RecordingEvaluationRetriever(engine_id="tfidf")
    embedding = RecordingEvaluationRetriever(engine_id="embedding")

    result = RetrievalEvaluationRunner(
        tfidf_retriever=tfidf,  # type: ignore[arg-type]
        embedding_retriever=embedding,
    ).run()

    fixed_queries = [case.query for case in FIXED_RETRIEVAL_EVALUATION_CASES]
    assert tfidf.calls == [(query, 3) for query in fixed_queries]
    assert embedding.calls == [(query, 3) for query in fixed_queries]
    assert [case.embedding_expected_rank for case in result.cases] == [2] * 6
    assert [case.tfidf_expected_rank for case in result.cases] == [2] * 6
    assert result.metrics.model_dump(by_alias=True) == {
        "caseCount": 6,
        "tfidfTop1Hits": 0,
        "embeddingTop1Hits": 0,
        "tfidfMrr": pytest.approx(0.5),
        "embeddingMrr": pytest.approx(0.5),
    }
