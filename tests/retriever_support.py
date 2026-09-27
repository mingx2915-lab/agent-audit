"""Explicit deterministic Retriever injection for API regression tests."""

from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.retrieval import TfidfRetriever


def make_tfidf_retriever() -> TfidfRetriever:
    """Preserve the pre-F-017 lexical test fixture without loading a model."""

    return TfidfRetriever(load_demo_data().documents)
