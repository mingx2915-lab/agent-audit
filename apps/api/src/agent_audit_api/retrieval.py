"""Retriever implementations for the synthetic permission-aware RAG target."""

from __future__ import annotations

import math
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal, Protocol, runtime_checkable

from .domain import KnowledgeDocument, RetrievedDocument


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)*|[\u3400-\u4dbf\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    """Tokenize Latin words/numbers and individual CJK characters consistently."""

    return [token.lower() for token in _TOKEN_PATTERN.findall(text)]


RetrieverEngineId = Literal["tfidf", "embedding"]


@dataclass(frozen=True)
class RetrieverMetadata:
    """Stable metadata exposed by every Retriever implementation."""

    engine_id: RetrieverEngineId
    model_name: str | None
    dimensions: int | None
    indexed_document_count: int = 0


@runtime_checkable
class Retriever(Protocol):
    """Common retrieval contract shared by the target and audit paths."""

    @property
    def engine_id(self) -> RetrieverEngineId:
        """Stable engine identifier."""

    @property
    def model_name(self) -> str | None:
        """Model name, when the engine is model-backed."""

    @property
    def dimensions(self) -> int | None:
        """Embedding dimensions, when applicable."""

    @property
    def indexed_document_count(self) -> int:
        """Number of indexed synthetic documents."""

    @property
    def metadata(self) -> RetrieverMetadata:
        """Return engine metadata without performing a search."""

    def search(self, query: str, limit: int = 3) -> list[RetrievedDocument]:
        """Return documents in deterministic score order."""


@runtime_checkable
class TextEmbedder(Protocol):
    """Minimal text embedding interface implemented by FastEmbed and test doubles."""

    def embed(self, documents: Sequence[str]) -> Iterable[Sequence[float]]:
        """Return one vector for each input document, in input order."""

    def query_embed(self, query: str) -> Iterable[Sequence[float]]:
        """Return exactly one vector for a query."""


class RetrieverError(RuntimeError):
    """Base error for model initialization, embedding, and index failures."""


class RetrieverInitializationError(RetrieverError):
    """Raised when the embedding model cannot be initialized."""


class RetrieverInferenceError(RetrieverError):
    """Raised when embedding inference or its response validation fails."""


EMBEDDING_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIMENSIONS = 512


class FastEmbedTextEmbedder:
    """Lazy FastEmbed adapter for the locked local BGE model.

    The adapter deliberately materializes FastEmbed's generators at the model
    boundary so inference errors are reported as Retriever errors rather than
    escaping later during index construction or query ranking.
    """

    def __init__(
        self,
        *,
        model_name: str = EMBEDDING_MODEL_NAME,
        cache_dir: str | None = None,
        threads: int | None = None,
    ) -> None:
        self.model_name = model_name
        self._cache_dir = cache_dir
        self._threads = threads
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from fastembed import TextEmbedding

            kwargs: dict[str, Any] = {
                "model_name": self.model_name,
                "cache_dir": self._cache_dir,
                "cuda": False,
                "lazy_load": True,
            }
            if getattr(sys, "frozen", False):
                model_dir = Path(sys._MEIPASS) / "embedding-model"
                if not (model_dir / "model_optimized.onnx").is_file():
                    raise FileNotFoundError("bundled BGE embedding model is missing")
                kwargs["specific_model_path"] = str(model_dir)
                kwargs["local_files_only"] = True
            if self._threads is not None:
                kwargs["threads"] = self._threads
            self._model = TextEmbedding(**kwargs)
        except Exception as exc:
            raise RetrieverInitializationError(
                f"unable to initialize embedding model {self.model_name}"
            ) from exc
        return self._model

    def embed(self, documents: Sequence[str]) -> tuple[Sequence[float], ...]:
        model = self._load_model()
        try:
            return tuple(model.embed(documents))
        except Exception as exc:
            raise RetrieverInferenceError("embedding document inference failed") from exc

    def query_embed(self, query: str) -> tuple[Sequence[float], ...]:
        model = self._load_model()
        try:
            return tuple(model.query_embed(query))
        except Exception as exc:
            raise RetrieverInferenceError("embedding query inference failed") from exc


class TfidfRetriever:
    """Index documents once and rank a query by TF-IDF vector cosine similarity."""

    def __init__(self, documents: Sequence[KnowledgeDocument]) -> None:
        if not all(isinstance(document, KnowledgeDocument) for document in documents):
            raise TypeError("TfidfRetriever accepts KnowledgeDocument values")
        self._documents = tuple(documents)
        self._document_term_frequencies = tuple(
            Counter(_tokenize(document.content)) for document in self._documents
        )
        document_frequency: Counter[str] = Counter()
        for frequencies in self._document_term_frequencies:
            document_frequency.update(frequencies.keys())
        document_count = len(self._documents)
        self._idf = {
            token: math.log((1 + document_count) / (1 + frequency)) + 1.0
            for token, frequency in document_frequency.items()
        }
        self._document_vectors = tuple(
            self._weighted_vector(frequencies) for frequencies in self._document_term_frequencies
        )
        self._document_norms = tuple(self._vector_norm(vector) for vector in self._document_vectors)

    @property
    def metadata(self) -> RetrieverMetadata:
        return RetrieverMetadata(
            engine_id="tfidf",
            model_name=None,
            dimensions=None,
            indexed_document_count=len(self._documents),
        )

    @property
    def engine_id(self) -> RetrieverEngineId:
        return "tfidf"

    @property
    def model_name(self) -> str | None:
        return None

    @property
    def dimensions(self) -> int | None:
        return None

    @property
    def indexed_document_count(self) -> int:
        return len(self._documents)

    @staticmethod
    def _vector_norm(vector: dict[str, float]) -> float:
        return math.sqrt(sum(value * value for value in vector.values()))

    def _weighted_vector(self, frequencies: Counter[str]) -> dict[str, float]:
        total = sum(frequencies.values())
        if total == 0:
            return {}
        return {
            token: (count / total) * self._idf[token]
            for token, count in frequencies.items()
            if token in self._idf
        }

    def search(self, query: str, limit: int = 3) -> list[RetrievedDocument]:
        """Return up to ``limit`` positively matching documents in score order."""

        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            return []
        query_frequencies = Counter(_tokenize(query))
        query_vector = self._weighted_vector(query_frequencies)
        query_norm = self._vector_norm(query_vector)
        if query_norm == 0:
            return []

        ranked: list[RetrievedDocument] = []
        for document, vector, document_norm in zip(
            self._documents,
            self._document_vectors,
            self._document_norms,
        ):
            if document_norm == 0:
                continue
            dot_product = sum(query_vector.get(token, 0.0) * value for token, value in vector.items())
            if dot_product <= 0:
                continue
            score = dot_product / (query_norm * document_norm)
            ranked.append(RetrievedDocument(document=document, score=score))
        ranked.sort(key=lambda item: (-item.score, item.document.id))
        return ranked[:limit]


class EmbeddingRetriever:
    """In-process cosine retriever backed by the locked BGE embedding model."""

    def __init__(
        self,
        documents: Sequence[KnowledgeDocument],
        embedder: TextEmbedder | None = None,
    ) -> None:
        if not all(isinstance(document, KnowledgeDocument) for document in documents):
            raise TypeError("EmbeddingRetriever accepts KnowledgeDocument values")
        self._documents = tuple(documents)
        self._embedder = embedder if embedder is not None else FastEmbedTextEmbedder()
        self._document_vectors: tuple[tuple[float, ...], ...] | None = None
        self._metadata = RetrieverMetadata(
            engine_id="embedding",
            model_name=EMBEDDING_MODEL_NAME,
            dimensions=EMBEDDING_DIMENSIONS,
            indexed_document_count=len(self._documents),
        )

    @property
    def metadata(self) -> RetrieverMetadata:
        return self._metadata

    @property
    def engine_id(self) -> RetrieverEngineId:
        return self._metadata.engine_id

    @property
    def model_name(self) -> str | None:
        return self._metadata.model_name

    @property
    def dimensions(self) -> int | None:
        return self._metadata.dimensions

    @property
    def indexed_document_count(self) -> int:
        return self._metadata.indexed_document_count

    @staticmethod
    def _validated_vector(raw_vector: Sequence[float], *, label: str) -> tuple[float, ...]:
        if isinstance(raw_vector, (str, bytes)):
            raise RetrieverInferenceError(f"{label} embedding vector is invalid")
        try:
            values = tuple(raw_vector)
        except TypeError as exc:
            raise RetrieverInferenceError(f"{label} embedding vector is invalid") from exc
        if len(values) != EMBEDDING_DIMENSIONS:
            raise RetrieverInferenceError(
                f"{label} embedding dimension must be {EMBEDDING_DIMENSIONS}, got {len(values)}"
            )
        normalized: list[float] = []
        for value in values:
            if isinstance(value, (bool, str, bytes)):
                raise RetrieverInferenceError(f"{label} embedding vector contains non-numeric values")
            try:
                numeric = float(value)
            except (OverflowError, TypeError, ValueError) as exc:
                raise RetrieverInferenceError(
                    f"{label} embedding vector contains non-numeric values"
                ) from exc
            if not math.isfinite(numeric):
                raise RetrieverInferenceError(
                    f"{label} embedding vector contains non-finite values"
                )
            normalized.append(numeric)
        return tuple(normalized)

    def _build_index(self) -> tuple[tuple[float, ...], ...]:
        texts = tuple(f"{document.title}\n{document.content}" for document in self._documents)
        try:
            raw_vectors = tuple(self._embedder.embed(texts))
        except RetrieverError:
            raise
        except Exception as exc:
            raise RetrieverInferenceError("embedding document inference failed") from exc
        if len(raw_vectors) != len(self._documents):
            raise RetrieverInferenceError(
                "embedding document vector count does not match indexed documents"
            )
        return tuple(
            self._validated_vector(vector, label="document") for vector in raw_vectors
        )

    def _ensure_index(self) -> tuple[tuple[float, ...], ...]:
        if self._document_vectors is None:
            self._document_vectors = self._build_index()
        return self._document_vectors

    def prepare(self) -> None:
        """Build the document index before a caller publishes this Retriever."""

        self._ensure_index()

    def with_documents(
        self,
        documents: Sequence[KnowledgeDocument],
    ) -> "EmbeddingRetriever":
        """Create another index using this Retriever's configured embedder."""

        return EmbeddingRetriever(documents, embedder=self._embedder)

    def _query_vector(self, query: str) -> tuple[float, ...]:
        try:
            raw_vectors = tuple(self._embedder.query_embed(query))
        except RetrieverError:
            raise
        except Exception as exc:
            raise RetrieverInferenceError("embedding query inference failed") from exc
        if len(raw_vectors) != 1:
            raise RetrieverInferenceError(
                "embedding query inference must return exactly one vector"
            )
        return self._validated_vector(raw_vectors[0], label="query")

    @staticmethod
    def _vector_norm(vector: Sequence[float]) -> float:
        return math.sqrt(sum(value * value for value in vector))

    def search(self, query: str, limit: int = 3) -> list[RetrievedDocument]:
        """Return up to ``limit`` documents by cosine score and document ID tie-break."""

        if not isinstance(query, str):
            raise TypeError("query must be a string")
        if not query.strip():
            raise ValueError("query must not be empty")
        if limit <= 0:
            return []

        document_vectors = self._ensure_index()
        query_vector = self._query_vector(query)
        query_norm = self._vector_norm(query_vector)
        ranked: list[RetrievedDocument] = []
        for document, vector in zip(self._documents, document_vectors):
            document_norm = self._vector_norm(vector)
            if query_norm == 0.0 or document_norm == 0.0:
                score = 0.0
            else:
                dot_product = sum(left * right for left, right in zip(query_vector, vector))
                score = dot_product / (query_norm * document_norm)
            ranked.append(RetrievedDocument(document=document, score=score))
        ranked.sort(key=lambda item: (-item.score, item.document.id))
        return ranked[:limit]


class ReloadableRetriever:
    """Stable-identity Retriever slot for an in-process Workspace catalog.

    Existing Assistant/Scan/Replay services keep a reference to the object
    supplied during app construction.  Replacing the slot's current index
    therefore makes a committed catalog visible to every existing route
    without rebuilding the FastAPI application.  ``build_candidate`` creates
    and prepares a new index before ``replace`` is called by the import layer.
    """

    def __init__(
        self,
        current: Retriever,
        *,
        factory: Callable[[Sequence[KnowledgeDocument]], Retriever] | None = None,
    ) -> None:
        if not isinstance(current, Retriever):
            raise TypeError("ReloadableRetriever requires a Retriever")
        self._current = current
        self._factory = factory

    @property
    def current(self) -> Retriever:
        """Return the currently active concrete index."""

        return self._current

    @property
    def metadata(self) -> RetrieverMetadata:
        return self._current.metadata

    @property
    def engine_id(self) -> RetrieverEngineId:
        return self._current.engine_id

    @property
    def model_name(self) -> str | None:
        return self._current.model_name

    @property
    def dimensions(self) -> int | None:
        return self._current.dimensions

    @property
    def indexed_document_count(self) -> int:
        return self._current.indexed_document_count

    def search(self, query: str, limit: int = 3) -> list[RetrievedDocument]:
        return self._current.search(query, limit=limit)

    def build_candidate(
        self,
        documents: Sequence[KnowledgeDocument],
    ) -> Retriever:
        if self._factory is None:
            raise RetrieverError("no Retriever factory is configured")
        try:
            candidate = self._factory(tuple(documents))
        except RetrieverError:
            raise
        except Exception as exc:
            raise RetrieverError("unable to build replacement Retriever") from exc
        if not isinstance(candidate, Retriever):
            raise RetrieverError("Retriever factory returned an invalid value")
        prepare = getattr(candidate, "prepare", None)
        if callable(prepare):
            try:
                prepare()
            except RetrieverError:
                raise
            except Exception as exc:
                raise RetrieverError("unable to prepare replacement Retriever") from exc
        return candidate

    def replace(self, candidate: Retriever) -> None:
        if not isinstance(candidate, Retriever):
            raise TypeError("replacement must satisfy Retriever")
        self._current = candidate


__all__ = [
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_MODEL_NAME",
    "EmbeddingRetriever",
    "FastEmbedTextEmbedder",
    "Retriever",
    "RetrieverError",
    "RetrieverInitializationError",
    "RetrieverInferenceError",
    "RetrieverMetadata",
    "ReloadableRetriever",
    "TextEmbedder",
    "TfidfRetriever",
]
