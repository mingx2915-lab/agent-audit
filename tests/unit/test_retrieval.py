from agent_audit_api.domain import KnowledgeDocument
from agent_audit_api.retrieval import TfidfRetriever


def _documents() -> list[KnowledgeDocument]:
    return [
        KnowledgeDocument(
            id="doc-contract",
            title="Customer contract",
            content="customer contract renewal terms and customer contract owner",
            owner_id="sales_001",
            labels=("customer", "confidential"),
            source_id="crm://contracts/customer_001",
            source_type="crm_record",
            trust_level="trusted",
        ),
        KnowledgeDocument(
            id="doc-handbook",
            title="Employee handbook",
            content="employee handbook leave and workplace policies",
            owner_id=None,
            labels=("internal",),
            source_id="wiki://employee-handbook",
            source_type="internal_wiki",
            trust_level="trusted",
        ),
        KnowledgeDocument(
            id="doc-directory",
            title="Customer directory",
            content="customer directory account contacts and regions",
            owner_id=None,
            labels=("customer", "internal"),
            source_id="crm://directory",
            source_type="crm_directory",
            trust_level="trusted",
        ),
    ]


def test_tfidf_retriever_ranks_documents_for_each_query() -> None:
    retriever = TfidfRetriever(_documents())

    contract_results = retriever.search("customer contract", limit=3)
    handbook_results = retriever.search("employee handbook", limit=3)

    assert contract_results
    assert handbook_results
    assert contract_results[0].document.id == "doc-contract"
    assert handbook_results[0].document.id == "doc-handbook"
    assert all(
        left.score >= right.score
        for left, right in zip(contract_results, contract_results[1:])
    )
    assert all(
        left.score >= right.score
        for left, right in zip(handbook_results, handbook_results[1:])
    )


def test_tfidf_retriever_honors_result_limit() -> None:
    retriever = TfidfRetriever(_documents())

    results = retriever.search("customer", limit=1)

    assert len(results) == 1
    assert results[0].score > 0
