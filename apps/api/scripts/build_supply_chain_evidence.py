#!/usr/bin/env python3
"""Build an explicit Python/npm/Cargo supply-chain evidence bundle."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from agent_audit_api.supply_chain import DEFAULT_OUTPUT_DIR, SupplyChainEvidenceRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-id")
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--pip-audit-python")
    parser.add_argument("--npm-tool", default=shutil.which("npm") or "npm")
    parser.add_argument("--cargo-tool", default="cargo")
    parser.add_argument("--cargo-audit-tool")
    parser.add_argument("--decisions", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = SupplyChainEvidenceRunner(
            ROOT, args.output_dir, run_id=args.run_id
    ).run(python_executable=args.python_executable,
          pip_audit_python=args.pip_audit_python,
          npm=args.npm_tool, cargo=args.cargo_tool,
          cargo_audit_tool=args.cargo_audit_tool,
          offline=not args.online, decisions=args.decisions)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"supply-chain-evidence: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"supply-chain-evidence: {summary.status} ({summary.id})")
    return 0 if summary.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
