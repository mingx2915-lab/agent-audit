"""API regression coverage for the shared F-024 benchmark runtime."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import agent_audit_api.main as main_module
from agent_audit_api.main import create_app
from tests.benchmark_support import GroundTruthProvider
from tests.retriever_support import make_tfidf_retriever


def test_http_benchmark_reuses_shared_runtime_and_keeps_existing_contracts(
    monkeypatch,
) -> None:
    provider = GroundTruthProvider()
    retriever = make_tfidf_retriever()
    real_builder = main_module.build_benchmark_runtime
    calls: list[dict[str, Any]] = []

    def spy_builder(provider_arg, *, contract=None, retriever=None, cases=None):
        calls.append(
            {
                "provider": provider_arg,
                "contract": contract,
                "retriever": retriever,
                "cases": cases,
            }
        )
        return real_builder(
            provider_arg,
            contract=contract,
            retriever=retriever,
            cases=cases,
        )

    monkeypatch.setattr(main_module, "build_benchmark_runtime", spy_builder)
    with TestClient(create_app(provider=provider, retriever=retriever)) as client:
        runtime_response = client.get("/api/runtime")
        contract_response = client.get("/api/security-contract")
        plans_response = client.get("/api/attack-plans")
        benchmark_response = client.post("/api/benchmarks/run")

    assert runtime_response.status_code == 200
    assert runtime_response.json() == {
        "provider": "injected:GroundTruthProvider",
        "model": None,
        "retrieverEngine": "tfidf",
        "retrieverModel": None,
        "retrieverDimensions": None,
        "indexedDocumentCount": 7,
    }
    assert contract_response.status_code == 200
    assert contract_response.json()["id"]
    assert plans_response.status_code == 200
    assert len(plans_response.json()) == 4

    assert benchmark_response.status_code == 200
    result = benchmark_response.json()
    assert len(result["cases"]) == 24
    assert result["metrics"]["caseCount"] == 24
    assert result["metrics"]["matchedCaseCount"] == 24
    assert result["metrics"]["detectionRecall"] == 1
    assert result["metrics"]["falsePositiveRate"] == 0
    assert result["metrics"]["policyViolationAccuracy"] == 1
    assert result["metrics"]["replayPassRate"] == 1
    assert result["metrics"]["providerUsage"]["callCount"] == len(provider.calls)

    assert len(calls) == 1
    assert calls[0]["provider"] is provider
    assert calls[0]["retriever"] is retriever
    assert calls[0]["contract"] is not None
    assert len(calls[0]["cases"]) == 24
