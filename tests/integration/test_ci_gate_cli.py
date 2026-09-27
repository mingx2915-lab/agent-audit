"""CLI, subprocess, and console-entry coverage for F-024."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

import agent_audit_api.cli as cli_module
from agent_audit_api.benchmark_runtime import build_benchmark_runtime
from agent_audit_api.ci_gate import CIGateResult
from agent_audit_api.providers.base import ProviderConfigurationError
from tests.benchmark_support import GroundTruthProvider
from tests.retriever_support import make_tfidf_retriever


REPO_ROOT = Path(__file__).resolve().parents[2]
API_SOURCE = REPO_ROOT / "apps" / "api" / "src"


def _pythonpath(*extra: Path) -> str:
    entries = [str(path) for path in extra]
    entries.extend([str(API_SOURCE), str(REPO_ROOT)])
    inherited = os.environ.get("PYTHONPATH")
    if inherited:
        entries.append(inherited)
    return os.pathsep.join(entries)


def _patch_deterministic_cli(monkeypatch) -> GroundTruthProvider:
    provider = GroundTruthProvider()
    real_builder = cli_module.build_benchmark_runtime

    monkeypatch.setattr(cli_module, "create_runtime_provider", lambda: provider)
    monkeypatch.setattr(
        cli_module,
        "build_benchmark_runtime",
        lambda provider_arg: real_builder(
            provider_arg,
            retriever=make_tfidf_retriever(),
        ),
    )
    return provider


def test_cli_success_writes_verifiable_json_and_markdown_with_real_runner(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    provider = _patch_deterministic_cli(monkeypatch)
    output_dir = tmp_path / "nested" / "ci-gate"
    unrelated = output_dir / "keep.txt"
    output_dir.mkdir(parents=True)
    unrelated.write_text("unrelated evidence", encoding="utf-8")

    exit_code = cli_module.main(["ci-gate", "--output-dir", str(output_dir)])

    assert exit_code == 0
    assert "ci-gate: passed (24/24 cases matched)" in capsys.readouterr().out
    json_path = output_dir / "ci-gate.json"
    markdown_path = output_dir / "ci-gate.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    result = CIGateResult.model_validate(payload)

    assert result.status == "passed"
    assert len(result.benchmark.cases) == 24
    assert result.failed_check_ids == []
    assert result.runtime_snapshot.provider == "injected:GroundTruthProvider"
    assert result.runtime_snapshot.retriever_engine == "tfidf"
    assert result.benchmark.metrics.provider_usage.call_count == len(provider.calls)
    assert result.benchmark.metrics.provider_usage.estimated_cost_usd is None
    assert "# 知盾 AgentAudit CI Gate" in markdown_path.read_text(encoding="utf-8")
    assert unrelated.read_text(encoding="utf-8") == "unrelated evidence"
    assert {path.name for path in output_dir.iterdir()} == {
        "keep.txt",
        "ci-gate.json",
        "ci-gate.md",
    }


def test_cli_returns_one_and_lists_exact_failed_check_when_benchmark_fails(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    provider = GroundTruthProvider()
    base_runtime = build_benchmark_runtime(
        provider,
        retriever=make_tfidf_retriever(),
    )
    benchmark = asyncio.run(base_runtime.run())
    bad_benchmark = benchmark.model_copy(
        update={
            "metrics": benchmark.metrics.model_copy(
                update={"replay_pass_rate": 0.5}
            )
        }
    )

    class StaticRuntime:
        contract = base_runtime.contract
        runtime_snapshot = base_runtime.runtime_snapshot

        async def run(self):
            return bad_benchmark

    monkeypatch.setattr(cli_module, "create_runtime_provider", lambda: provider)
    monkeypatch.setattr(cli_module, "build_benchmark_runtime", lambda _provider: StaticRuntime())
    output_dir = tmp_path / "failed"

    exit_code = cli_module.main(["ci-gate", "--output-dir", str(output_dir)])

    assert exit_code == cli_module.EXIT_GATE_FAILED
    assert "ci-gate: failed (failed checks: replay_pass_rate)" in capsys.readouterr().out
    result = CIGateResult.model_validate(
        json.loads((output_dir / "ci-gate.json").read_text(encoding="utf-8"))
    )
    assert result.status == "failed"
    assert result.failed_check_ids == ["replay_pass_rate"]


def test_cli_returns_two_for_provider_or_artifact_boundary_errors(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    def raise_provider_error():
        raise ProviderConfigurationError("deterministic provider configuration error")

    monkeypatch.setattr(cli_module, "create_runtime_provider", raise_provider_error)
    output_dir = tmp_path / "error"

    exit_code = cli_module.main(["ci-gate", "--output-dir", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == cli_module.EXIT_RUNTIME_ERROR
    assert "deterministic provider configuration error" in captured.err
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--url", "https://example.invalid/agent"],
        ["--case", "gt_normal_public_product_visitor"],
        ["--contract", "contract_nebula_default"],
        ["--threshold", "0.5"],
        ["https://example.invalid/agent"],
    ],
)
def test_cli_rejects_external_targets_case_contract_and_threshold_inputs(
    extra_args,
    tmp_path,
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli_module.main(
            ["ci-gate", "--output-dir", str(tmp_path / "rejected"), *extra_args]
        )

    assert raised.value.code == 2


def test_cli_accepts_only_ci_gate_command_and_requires_output_dir(tmp_path) -> None:
    with pytest.raises(SystemExit) as unknown_command:
        cli_module.main(["scan", "--output-dir", str(tmp_path / "rejected")])
    with pytest.raises(SystemExit) as missing_output:
        cli_module.main(["ci-gate"])

    assert unknown_command.value.code == 2
    assert missing_output.value.code == 2


def test_module_entrypoint_runs_in_subprocess_with_sitecustomize_injection(tmp_path) -> None:
    """Exercise ``python -m`` without loading FastEmbed or a real provider."""

    injection_dir = tmp_path / "injection"
    injection_dir.mkdir()
    (injection_dir / "sitecustomize.py").write_text(
        "\n".join(
            [
                "import agent_audit_api.benchmark_runtime as runtime_module",
                "import agent_audit_api.providers.runtime as provider_module",
                "from tests.benchmark_support import GroundTruthProvider",
                "from tests.retriever_support import make_tfidf_retriever",
                "provider = GroundTruthProvider()",
                "real_builder = runtime_module.build_benchmark_runtime",
                "provider_module.create_runtime_provider = lambda: provider",
                "runtime_module.build_benchmark_runtime = lambda provider_arg: real_builder(provider_arg, retriever=make_tfidf_retriever())",
                "",
            ]
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "module-output"
    environment = dict(os.environ)
    environment["PYTHONPATH"] = _pythonpath(injection_dir)
    environment["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_audit_api.cli",
            "ci-gate",
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "ci-gate: passed (24/24 cases matched)" in completed.stdout
    result = CIGateResult.model_validate(
        json.loads((output_dir / "ci-gate.json").read_text(encoding="utf-8"))
    )
    assert result.status == "passed"
    assert result.runtime_snapshot.provider == "injected:GroundTruthProvider"
    assert result.benchmark.metrics.case_count == 24


def test_console_script_registration_points_to_cli_main() -> None:
    package = tomllib.loads(
        (REPO_ROOT / "apps" / "api" / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert package["project"]["scripts"]["agent-audit"] == "agent_audit_api.cli:main"
