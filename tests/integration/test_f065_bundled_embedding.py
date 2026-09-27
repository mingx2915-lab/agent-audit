"""Release inference must use packaged resources without cache/network."""
from pathlib import Path
import sys
import pytest
from agent_audit_api.retrieval import FastEmbedTextEmbedder


def test_frozen_embedding_runs_offline_with_empty_cache(monkeypatch, tmp_path):
    import fastembed  # Import dependency before simulating frozen resources.
    bundle = Path(__file__).resolve().parents[2] / ".tools"
    if not (bundle / "embedding-model/model_optimized.onnx").is_file():
        pytest.skip("Run prepare_embedding_model.py before release inference checks")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    embedder = FastEmbedTextEmbedder(cache_dir=str(tmp_path / "empty-cache"), threads=2)
    vectors = embedder.embed(["企业财务预算", "客户合同资料"])
    query = embedder.query_embed("财务预算")
    assert len(vectors) == 2 and len(query) == 1
    assert len(query[0]) == 512
    assert float(vectors[0] @ query[0]) > float(vectors[1] @ query[0])
