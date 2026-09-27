"""Contract tests for the now-persisted F-036 StabilityRunner boundary."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from agent_audit_api.cli import EXIT_RUNTIME_ERROR, main
from agent_audit_api.providers.base import ProviderUnavailableError
from agent_audit_api.stability import (
    DeterministicStabilityProvider,
    StabilityRunner,
    render_stability_markdown,
    run_stability_runner,
    write_stability_artifacts,
)


def test_stability_runner_executes_real_scan_replay_and_history_roundtrip(
    tmp_path: Path,
) -> None:
    evidence = asyncio.run(run_stability_runner(iterations=1, max_rounds=3))

    assert evidence.status == "passed"
    assert evidence.environment.deterministic is True
    assert evidence.environment.provider == "deterministic_test_provider"
    assert evidence.environment.workspace == "temporary"
    assert evidence.checks[0].id == "workflow_soak"
    assert evidence.checks[0].status == "passed"
    assert evidence.checks[0].completed_iterations == 1
    assert evidence.failures == []
    iteration = evidence.iterations[0]
    assert iteration.status == "passed"
    assert iteration.scan_id
    assert iteration.replay_id
    assert iteration.replay_result_id
    assert iteration.history_persisted is True
    assert iteration.history_count == 1
    assert iteration.source_sink_finding is True
    assert "external_sink_policy_violation" in iteration.finding_categories
    assert iteration.replay_status == "passed"
    assert iteration.replay_before_evaluation == "failed"
    assert iteration.replay_after_evaluation == "passed"
    assert iteration.replay_after_execution == "blocked"
    assert evidence.observations.history_count == 1
    assert evidence.observations.successful_workflows == 1
    assert evidence.observations.replay_pass_count == 1
    assert evidence.observations.finding_count >= 1

    json_path, markdown_path = write_stability_artifacts(evidence, tmp_path / "artifacts")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["id"] == evidence.id
    assert payload["status"] == evidence.status
    assert evidence.id in markdown
    assert evidence.status in markdown
    assert render_stability_markdown(evidence) == markdown


@dataclass
class _FailFirstDeterministicProvider(DeterministicStabilityProvider):
    fail_next: bool = True

    async def complete(self, messages, tools=None):
        if self.fail_next:
            self.fail_next = False
            raise ProviderUnavailableError("synthetic stability Provider outage")
        return await super().complete(messages, tools=tools)


def test_stability_runner_records_one_failed_iteration_then_continues(
    tmp_path: Path,
) -> None:
    provider = _FailFirstDeterministicProvider()
    evidence = asyncio.run(
        StabilityRunner(
            iterations=2,
            max_rounds=2,
            provider=provider,
            workspace_root=tmp_path / "workspace",
        ).run()
    )

    assert evidence.status == "failed"
    assert evidence.checks[0].status == "failed"
    assert evidence.checks[0].iterations == 2
    assert evidence.checks[0].completed_iterations == 1
    assert len(evidence.failures) == 1
    failure = evidence.failures[0]
    assert failure.iteration == 1
    assert failure.stage == "scan"
    assert failure.category == "provider_error"
    assert failure.error_type == "ProviderUnavailableError"
    assert failure.detail == "synthetic stability Provider outage"
    assert [item.status for item in evidence.iterations] == ["failed", "passed"]
    assert evidence.iterations[0].history_persisted is False
    assert evidence.iterations[0].history_count == 0
    assert evidence.iterations[1].history_persisted is True
    assert evidence.iterations[1].history_count == 1
    assert evidence.observations.successful_workflows == 1
    assert evidence.observations.history_count == 1
    assert provider.fail_next is False


def test_stability_runner_requires_explicitly_deterministic_provider() -> None:
    class NonDeterministicProvider:
        deterministic = False

    with pytest.raises(ValueError, match="explicitly marked deterministic"):
        StabilityRunner(provider=NonDeterministicProvider())


def test_default_stability_workspace_does_not_touch_configured_user_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_home = tmp_path / "user-home"
    monkeypatch.setenv("AGENT_AUDIT_HOME", str(user_home))

    evidence = asyncio.run(run_stability_runner(iterations=1, max_rounds=2))

    assert evidence.status == "passed"
    assert not user_home.exists()


@pytest.mark.parametrize("iterations", [0, 101, True, 1.0])
def test_stability_runner_rejects_iteration_counts_outside_contract(iterations) -> None:
    with pytest.raises(ValueError, match="iterations must be an integer between 1 and 100"):
        StabilityRunner(iterations=iterations)


def test_stability_runner_requires_explicit_long_soak_for_more_than_100_iterations() -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        StabilityRunner(iterations=101)

    runner = StabilityRunner(iterations=1_000, long_soak=True)
    assert runner.iterations == 1_000
    assert runner.long_soak is True


def test_stability_cli_writes_two_artifacts_and_returns_success(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "stability-artifacts"

    exit_code = main(
        [
            "stability",
            "--output-dir",
            str(output_dir),
            "--iterations",
            "1",
            "--max-rounds",
            "2",
        ]
    )

    assert exit_code == 0
    json_files = sorted(output_dir.glob("stability_*.json"))
    markdown_files = sorted(output_dir.glob("stability_*.md"))
    assert len(json_files) == 1
    assert len(markdown_files) == 1
    evidence = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert evidence["status"] == "passed"
    assert evidence["environment"]["deterministic"] is True
    assert json_files[0].stem == markdown_files[0].stem
    assert "stability: passed" in capsys.readouterr().out


def test_stability_cli_rejects_invalid_iteration_before_creating_output(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "not-created"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "stability",
                "--output-dir",
                str(output_dir),
                "--iterations",
                "0",
            ]
        )

    assert exc_info.value.code == 2
    assert not output_dir.exists()


def test_stability_cli_reports_output_directory_runtime_error(tmp_path: Path) -> None:
    output_path = tmp_path / "output-file"
    output_path.write_text("not a directory", encoding="utf-8")

    exit_code = main(
        [
            "stability",
            "--output-dir",
            str(output_path),
            "--iterations",
            "1",
            "--max-rounds",
            "2",
        ]
    )

    assert exit_code == EXIT_RUNTIME_ERROR
