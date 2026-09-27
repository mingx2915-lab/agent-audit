from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "apps" / "api" / "scripts" / "build_supply_chain_evidence.py"


def _module():
    spec = importlib.util.spec_from_file_location("f056_supply_chain_cli", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_is_offline_by_default_and_online_requires_explicit_flag(
    monkeypatch, tmp_path: Path
) -> None:
    module = _module()
    calls: list[dict[str, object]] = []

    class Summary:
        status = "incomplete"
        id = "cli-offline"

    class Runner:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def run(self, **kwargs):
            calls.append(kwargs)
            return Summary()

    monkeypatch.setattr(module, "SupplyChainEvidenceRunner", Runner)
    assert module.main(["--output-dir", str(tmp_path), "--run-id", "one"]) == 1
    assert calls[-1]["offline"] is True
    assert module.main(
        ["--output-dir", str(tmp_path), "--run-id", "two", "--online"]
    ) == 1
    assert calls[-1]["offline"] is False
