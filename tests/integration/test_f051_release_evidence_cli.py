"""F-051 public CLI contract for offline release evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_audit_api import cli


def _manifest(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "tests.json").write_text('{"passed": 1}', encoding="utf-8")
    manifest = root / "input.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": "release-evidence-input.v1",
                "artifacts": [
                    {
                        "id": "tests",
                        "category": "test",
                        "path": "tests.json",
                        "status": "passed",
                        "provenance": "controlled_test",
                    },
                    {
                        "id": "linux",
                        "category": "desktop",
                        "status": "not_verified",
                        "provenance": "not_verified",
                    },
                ],
                "boundaries": ["No real model or Linux artifact was provided."],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_release_evidence_cli_succeeds_without_provider_or_workspace_assembly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_manifest = _manifest(tmp_path / "inputs")
    output = tmp_path / "output"

    def forbidden_provider() -> object:
        raise AssertionError("release-evidence must not create a Provider")

    def forbidden_runtime(*args: object, **kwargs: object) -> object:
        raise AssertionError("release-evidence must not assemble benchmark or Workspace runtime")

    monkeypatch.setattr(cli, "create_runtime_provider", forbidden_provider)
    monkeypatch.setattr(cli, "build_benchmark_runtime", forbidden_runtime)

    result = cli.main(
        [
            "release-evidence",
            "--input-manifest",
            str(input_manifest),
            "--output-dir",
            str(output),
            "--run-id",
            "cli-run",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "release-evidence: incomplete" in captured.out
    assert str((output / "cli-run").resolve()) in captured.out
    assert captured.err == ""
    assert json.loads((output / "cli-run" / "summary.json").read_text(encoding="utf-8"))[
        "status"
    ] == "incomplete"


def test_release_evidence_cli_returns_runtime_error_without_false_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.json"
    output = tmp_path / "output"

    result = cli.main(
        [
            "release-evidence",
            "--input-manifest",
            str(missing),
            "--output-dir",
            str(output),
            "--run-id",
            "failed-run",
        ]
    )

    captured = capsys.readouterr()
    assert result == cli.EXIT_RUNTIME_ERROR
    assert captured.out == ""
    assert "input manifest is unavailable" in captured.err
    assert not (output / "failed-run" / "summary.json").exists()


def test_release_evidence_cli_rejects_invalid_run_id_before_writing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_manifest = _manifest(tmp_path / "inputs")
    output = tmp_path / "output"

    result = cli.main(
        [
            "release-evidence",
            "--input-manifest",
            str(input_manifest),
            "--output-dir",
            str(output),
            "--run-id",
            "../escape",
        ]
    )

    captured = capsys.readouterr()
    assert result == cli.EXIT_RUNTIME_ERROR
    assert "run_id must use" in captured.err
    assert not output.exists()
