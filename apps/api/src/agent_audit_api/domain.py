"""Domain value objects used by the controlled demo target."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoActor:
    """A synthetic actor selectable in the demo UI."""

    id: str
    display_name: str
    role: str


@dataclass(frozen=True)
class KnowledgeDocument:
    """A synthetic knowledge document indexed by the RAG retriever."""

    id: str
    title: str
    content: str
    owner_id: str | None
    labels: tuple[str, ...]
    source_id: str
    source_type: str
    trust_level: str


@dataclass(frozen=True)
class RetrievedDocument:
    """A document and its query-specific TF-IDF/cosine score."""

    document: KnowledgeDocument
    score: float


@dataclass(frozen=True)
class CustomerRecord:
    """A synthetic customer record exposed by the Mock Customer Tool."""

    id: str
    name: str
    owner_id: str
    summary: str
