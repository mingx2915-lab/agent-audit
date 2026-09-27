"""Materialize the pinned BGE release resources before freezing either platform."""
from pathlib import Path
import shutil
import json
import hashlib
from huggingface_hub import snapshot_download
from fastembed.common.utils import define_cache_dir

ROOT = Path(__file__).resolve().parents[3]
REVISION = "46fbe35fd4374a00fee7de77dfddaeb6dd6a2c59"
FILES = ["model_optimized.onnx", "tokenizer.json", "tokenizer_config.json",
         "special_tokens_map.json", "config.json"]
destination = ROOT / ".tools" / "embedding-model"
manifest_file = destination / "model-manifest.json"
if manifest_file.is_file():
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if manifest["revision"] != REVISION:
        raise RuntimeError("Prepared embedding model revision does not match release")
    for name in FILES:
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != manifest["files"][name]:
            raise RuntimeError(f"Prepared embedding resource does not match manifest: {name}")
    print(f"Verified pinned embedding resources: {destination}")
    raise SystemExit(0)
source = Path(snapshot_download(repo_id="Qdrant/bge-small-zh-v1.5", revision=REVISION,
                               cache_dir=str(define_cache_dir(None)), allow_patterns=FILES))
destination = ROOT / ".tools" / "embedding-model"
destination.mkdir(parents=True, exist_ok=True)
for name in FILES:
    shutil.copy2(source / name, destination / name)
manifest = {"model": "BAAI/bge-small-zh-v1.5", "repository": "Qdrant/bge-small-zh-v1.5",
            "revision": REVISION, "dimensions": 512,
            "files": {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in FILES}}
(destination / "model-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"Prepared pinned embedding resources: {destination}")
