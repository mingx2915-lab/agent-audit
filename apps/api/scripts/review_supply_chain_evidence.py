#!/usr/bin/env python3
"""Generate or validate an explicit supply-chain review register.

The register is a human-editable projection of one F-056 ``summary.json``;
this command never changes scanner decisions, lockfiles, or package metadata.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from agent_audit_api.supply_chain import (  # noqa: E402
    build_supply_chain_review_register,
    validate_supply_chain_review_register,
    write_supply_chain_review_register,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a pending supply-chain review register or validate an "
            "edited register against one explicit F-056 summary."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--summary",
        required=True,
        type=Path,
        help="explicit F-056 summary.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON register output (generation mode)",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        help="optional Markdown projection (generation mode)",
    )
    parser.add_argument(
        "--owner",
        help="explicit default owner for generated pending rows",
    )
    parser.add_argument(
        "--due-date",
        dest="due_date",
        help="explicit review due date (ISO date or timezone timestamp)",
    )
    parser.add_argument(
        "--register",
        "--reviews",
        "--input",
        dest="register",
        type=Path,
        help="edited JSON register (validation mode)",
    )
    parser.add_argument(
        "--check",
        "--validate",
        action="store_true",
        help="validate --register instead of generating a template",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow replacing explicitly selected output files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.check:
        if args.register is None:
            _parser().error("--check requires --register")
        if args.output is not None or args.markdown is not None:
            _parser().error("--check does not accept --output or --markdown")
        if args.owner is not None or args.due_date is not None:
            _parser().error("--check does not accept --owner or --due-date")
        try:
            register = validate_supply_chain_review_register(args.summary, args.register)
        except (OSError, TypeError, ValueError) as exc:
            print(f"supply-chain-review: invalid ({exc})", file=sys.stderr)
            return 1
        print(f"supply-chain-review: valid ({len(register.items)} items)")
        return 0

    if args.register is not None:
        _parser().error("--register requires --check")
    if args.output is None:
        _parser().error("generation mode requires --output")
    if (args.owner is None) != (args.due_date is None):
        _parser().error("--owner and --due-date must be provided together")
    markdown = args.markdown
    if markdown is None:
        markdown = args.output.with_suffix(".md")
    try:
        register = build_supply_chain_review_register(
            args.summary,
            owner=args.owner,
            due_date=args.due_date,
        )
        write_supply_chain_review_register(
            register,
            args.output,
            markdown_path=markdown,
            overwrite=args.overwrite,
        )
    except (OSError, TypeError, ValueError) as exc:
        print(f"supply-chain-review: failed ({exc})", file=sys.stderr)
        return 1
    print(
        f"supply-chain-review: generated ({len(register.items)} items) "
        f"{args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
