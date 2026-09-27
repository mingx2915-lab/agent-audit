"""Command-line entrypoint for the fixed AgentAudit CI gate."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from .benchmark_runtime import build_benchmark_runtime
from .ci_gate import CIGateResult, build_ci_gate_result, write_ci_gate_artifacts
from .providers.runtime import create_runtime_provider
from .release_evidence import (
    DEFAULT_RELEASE_EVIDENCE_OUTPUT_DIR,
    ReleaseEvidenceRunner,
)
from .stability import (
    DEFAULT_ITERATIONS,
    DEFAULT_STABILITY_OUTPUT_DIR,
    MAX_ITERATIONS,
    MAX_LONG_SOAK_ITERATIONS,
    StabilityEvidence,
    run_stability_runner,
    write_stability_artifacts,
)


EXIT_GATE_FAILED = 1
EXIT_RUNTIME_ERROR = 2


def _iteration_count(value: str) -> int:
    """Parse the bounded explicit stability iteration count."""

    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("iterations must be an integer") from exc
    if not 1 <= parsed <= MAX_LONG_SOAK_ITERATIONS:
        raise argparse.ArgumentTypeError(
            f"iterations must be between 1 and {MAX_LONG_SOAK_ITERATIONS}"
        )
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-audit",
        description="Run an explicit AgentAudit benchmark or stability check.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    ci_gate_parser = subparsers.add_parser(
        "ci-gate",
        help="run the fixed 24-case benchmark and write CI gate artifacts",
        description="Run the fixed 24-case benchmark and write CI gate artifacts.",
        allow_abbrev=False,
    )
    ci_gate_parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="directory for ci-gate.json and ci-gate.md",
    )
    stability_parser = subparsers.add_parser(
        "stability",
        help="run the explicit deterministic F-036 workflow soak",
        description=(
            "Run the existing Guided Scan/Finding/Replay chain with the explicit "
            "deterministic Test Provider and write stability evidence."
        ),
        allow_abbrev=False,
    )
    stability_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_STABILITY_OUTPUT_DIR,
        help="directory for stability_<id>.json and stability_<id>.md",
    )
    stability_parser.add_argument(
        "--iterations",
        type=_iteration_count,
        default=DEFAULT_ITERATIONS,
        help=(
            f"explicit workflow iteration count (1-{MAX_ITERATIONS} by default; "
            f"up to {MAX_LONG_SOAK_ITERATIONS} with --long-soak)"
        ),
    )
    stability_parser.add_argument(
        "--long-soak",
        action="store_true",
        help=(
            f"explicitly permit {MAX_ITERATIONS + 1}-{MAX_LONG_SOAK_ITERATIONS} "
            "deterministic release-evidence iterations"
        ),
    )
    stability_parser.add_argument(
        "--max-rounds",
        type=int,
        choices=(2, 3),
        default=3,
        help="maximum bounded Red-Team rounds per iteration (default: 3)",
    )
    release_parser = subparsers.add_parser(
        "release-evidence",
        help="build one offline release-evidence bundle from an explicit manifest",
        description=(
            "Copy explicitly listed local artifacts into one immutable offline "
            "release-evidence bundle. This command does not run a Provider or read a Workspace."
        ),
        allow_abbrev=False,
    )
    release_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RELEASE_EVIDENCE_OUTPUT_DIR,
        help="parent directory for the versioned release-evidence run",
    )
    release_parser.add_argument(
        "--input-manifest",
        required=True,
        type=Path,
        help="explicit release-evidence-input.v1 JSON manifest",
    )
    release_parser.add_argument(
        "--run-id",
        help="optional safe run id; an id is generated when omitted",
    )
    return parser


async def _run_ci_gate(output_dir: Path) -> CIGateResult:
    provider = create_runtime_provider()
    runtime = build_benchmark_runtime(provider)
    benchmark = await runtime.run()
    result = build_ci_gate_result(
        benchmark,
        runtime.contract,
        runtime.runtime_snapshot,
    )
    write_ci_gate_artifacts(result, output_dir)
    return result


async def _run_stability(
    *,
    output_dir: Path,
    iterations: int,
    max_rounds: int,
    long_soak: bool,
) -> StabilityEvidence:
    """Run F-036 explicitly and persist only its two generated artifacts."""

    evidence = await run_stability_runner(
        iterations=iterations,
        max_rounds=max_rounds,  # type: ignore[arg-type]
        long_soak=long_soak,
    )
    write_stability_artifacts(evidence, output_dir)
    return evidence


def _print_result(result: CIGateResult) -> None:
    if result.status == "passed":
        print(
            "ci-gate: passed "
            f"({result.benchmark.metrics.matched_case_count}/"
            f"{result.benchmark.metrics.case_count} cases matched)"
        )
        return

    failed_check_ids = ", ".join(result.failed_check_ids) or "<unknown>"
    print(f"ci-gate: failed (failed checks: {failed_check_ids})")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its documented process exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    if (
        args.command == "stability"
        and args.iterations > MAX_ITERATIONS
        and not args.long_soak
    ):
        parser.error(
            f"iterations above {MAX_ITERATIONS} require explicit --long-soak"
        )

    try:
        if args.command == "ci-gate":
            result = asyncio.run(_run_ci_gate(args.output_dir))
        elif args.command == "stability":
            evidence = asyncio.run(
                _run_stability(
                    output_dir=args.output_dir,
                    iterations=args.iterations,
                    max_rounds=args.max_rounds,
                    long_soak=args.long_soak,
                )
            )
            print(
                "stability: "
                f"{evidence.status} "
                f"({evidence.observations.successful_workflows}/{evidence.checks[0].iterations} "
                "workflow iterations passed)"
            )
            return 0 if evidence.status == "passed" else EXIT_GATE_FAILED
        elif args.command == "release-evidence":
            runner = ReleaseEvidenceRunner(args.output_dir, run_id=args.run_id)
            summary = runner.run(args.input_manifest)
            print(
                "release-evidence: "
                f"{summary.status} ({(args.output_dir / summary.id).resolve()})"
            )
            return 0
        else:  # pragma: no cover - required subparser guards this
            return EXIT_RUNTIME_ERROR
    except Exception as exc:
        message = str(exc).strip() or type(exc).__name__
        print(f"agent-audit: {message}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    _print_result(result)
    return 0 if result.status == "passed" else EXIT_GATE_FAILED


if __name__ == "__main__":  # pragma: no cover - exercised by the module entrypoint
    raise SystemExit(main())


__all__ = ["EXIT_GATE_FAILED", "EXIT_RUNTIME_ERROR", "main"]
