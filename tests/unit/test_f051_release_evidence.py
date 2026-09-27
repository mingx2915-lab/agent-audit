"""F-051 offline release-evidence bundle trust-boundary coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agent_audit_api.release_evidence import (
    ReleaseEvidenceError,
    ReleaseEvidenceInputArtifact,
    ReleaseEvidenceRunner,
)
from pydantic import ValidationError


def _write_manifest(
    root: Path,
    artifacts: list[dict[str, object]],
    *,
    boundaries: list[str] | None = None,
) -> Path:
    path = root / "input.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": "release-evidence-input.v1",
                "productVersion": "0.1.0",
                "gitRevision": "abc123",
                "dirtyWorktree": False,
                "platform": "Windows test fixture",
                "pythonVersion": "3.12-test",
                "artifacts": artifacts,
                "boundaries": boundaries or ["受控 Test-only 证据，不代表真实企业 Gateway。"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_runner_writes_one_summary_projection_relative_manifest_and_recomputable_checksums(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "pytest.json").write_text(
        json.dumps({"passed": 692, "skipped": 6}),
        encoding="utf-8",
    )
    (inputs / "finding.json").write_text(
        json.dumps({"findingId": "finding_fixture", "severity": "critical"}),
        encoding="utf-8",
    )
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "python-tests",
                "category": "test",
                "path": "pytest.json",
                "status": "passed",
                "provenance": "controlled_test",
                "label": "Python tests",
            },
            {
                "id": "finding",
                "category": "finding",
                "path": "finding.json",
                "status": "passed",
                "provenance": "controlled_test",
            },
            {
                "id": "linux-artifact",
                "category": "desktop",
                "status": "not_verified",
                "provenance": "not_verified",
            },
            {
                "id": "enterprise-gateway",
                "category": "test",
                "status": "not_provided",
                "provenance": "not_provided",
            },
        ],
    )

    output = tmp_path / "output"
    summary = ReleaseEvidenceRunner(output, run_id="release-test-001").run(manifest)
    run_dir = output / summary.id
    summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (run_dir / "summary.md").read_text(encoding="utf-8")
    html = (run_dir / "summary.html").read_text(encoding="utf-8")
    output_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert summary_payload == summary.model_dump(mode="json", by_alias=True)
    assert summary_payload["status"] == "incomplete"
    assert summary_payload["counts"] == {
        "total": 4,
        "passed": 2,
        "failed": 0,
        "notRun": 0,
        "notProvided": 1,
        "notVerified": 1,
    }
    for artifact in summary_payload["artifacts"]:
        assert artifact["status"] in markdown
        assert artifact["provenance"] in markdown
        assert artifact["status"] in html
        assert artifact["provenance"] in html
    assert "Status: `incomplete`" in markdown
    assert "Status <strong>incomplete</strong>" in html
    assert output_manifest["runId"] == "release-test-001"
    assert output_manifest["artifacts"] == [
        "tests/python-tests.json",
        "findings/finding.json",
    ]
    for value in output_manifest.values():
        if isinstance(value, str):
            assert not Path(value).is_absolute()
        elif isinstance(value, list):
            assert all(not Path(item).is_absolute() for item in value)

    checksum_lines = (run_dir / "checksums.txt").read_text(encoding="utf-8").splitlines()
    checksums = dict(line.split("  ", 1)[::-1] for line in checksum_lines)
    assert "checksums.txt" not in checksums
    expected_files = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file() and path.name != "checksums.txt"
    }
    assert set(checksums) == expected_files
    assert all(checksums[relative] == _sha256(run_dir / relative) for relative in checksums)


@pytest.mark.parametrize(
    ("status", "provenance"),
    [
        ("not_run", "controlled_test"),
        ("not_provided", "not_provided"),
        ("not_verified", "not_verified"),
    ],
)
def test_missing_evidence_never_creates_an_artifact_or_passes(
    tmp_path: Path,
    status: str,
    provenance: str,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "missing",
                "category": "desktop",
                "status": status,
                "provenance": provenance,
            }
        ],
    )

    summary = ReleaseEvidenceRunner(tmp_path / "output", run_id="missing-run").run(manifest)

    assert summary.status == "incomplete"
    assert summary.counts.passed == 0
    assert summary.artifacts[0].path is None
    assert summary.artifacts[0].sha256 is None
    assert summary.artifacts[0].size_bytes is None


def test_runner_rejects_nonempty_run_before_copying_artifacts(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "result.json").write_text("{}", encoding="utf-8")
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "result",
                "category": "test",
                "path": "result.json",
                "status": "passed",
                "provenance": "controlled_test",
            }
        ],
    )
    run_dir = tmp_path / "output" / "existing-run"
    run_dir.mkdir(parents=True)
    sentinel = run_dir / "owned-by-user.txt"
    sentinel.write_text("keep", encoding="utf-8")

    with pytest.raises(ReleaseEvidenceError, match="not empty"):
        ReleaseEvidenceRunner(tmp_path / "output", run_id="existing-run").run(manifest)

    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert list(run_dir.iterdir()) == [sentinel]


@pytest.mark.parametrize(
    "artifact_path",
    ["../outside.json", "/tmp/outside.json", "C:\\Users\\person\\outside.json"],
)
def test_runner_rejects_artifacts_outside_manifest_directory(
    tmp_path: Path,
    artifact_path: str,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "escape",
                "category": "test",
                "path": artifact_path,
                "status": "passed",
                "provenance": "controlled_test",
            }
        ],
    )

    with pytest.raises(ReleaseEvidenceError, match="relative|within"):
        ReleaseEvidenceRunner(tmp_path / "output", run_id="escape-run").run(manifest)

    assert not (tmp_path / "output" / "escape-run").exists()


@pytest.mark.parametrize(
    "content",
    [
        '{"authorization": "Bearer secret-value-123"}',
        '{"x-api-key": "secret-value-123"}',
        "Authorization: Bearer secret-value-123",
        "password=secret-value-123",
    ],
)
def test_runner_rejects_secret_or_authentication_material(
    tmp_path: Path,
    content: str,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "unsafe.json").write_text(content, encoding="utf-8")
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "unsafe",
                "category": "test",
                "path": "unsafe.json",
                "status": "failed",
                "provenance": "real",
            }
        ],
    )

    with pytest.raises(ReleaseEvidenceError, match="secret|sensitive"):
        ReleaseEvidenceRunner(tmp_path / "output", run_id="unsafe-run").run(manifest)

    assert not (tmp_path / "output" / "unsafe-run").exists()


def test_runner_rejects_user_home_in_manifest_or_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_home = tmp_path / "private-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "unsafe.txt").write_text(
        f"source path: {fake_home / 'documents' / 'internal.txt'}",
        encoding="utf-8",
    )
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "unsafe-home",
                "category": "test",
                "path": "unsafe.txt",
                "status": "failed",
                "provenance": "real",
            }
        ],
    )

    with pytest.raises(ReleaseEvidenceError, match="user home"):
        ReleaseEvidenceRunner(tmp_path / "output", run_id="home-run").run(manifest)

    assert not (tmp_path / "output" / "home-run").exists()


def test_runner_does_not_read_or_modify_default_app_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_home = tmp_path / "default-user-app-home"
    app_home.mkdir()
    sentinel = app_home / "workspace-sentinel.bin"
    original = b"user workspace must stay byte-for-byte unchanged"
    sentinel.write_bytes(original)
    monkeypatch.setenv("AGENT_AUDIT_HOME", str(app_home))
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "result.json").write_text('{"passed": true}', encoding="utf-8")
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "result",
                "category": "test",
                "path": "result.json",
                "status": "passed",
                "provenance": "controlled_test",
            }
        ],
    )

    ReleaseEvidenceRunner(tmp_path / "output", run_id="isolated-run").run(manifest)

    assert sentinel.read_bytes() == original
    assert sorted(path.relative_to(app_home) for path in app_home.rglob("*")) == [
        Path("workspace-sentinel.bin")
    ]


@pytest.mark.parametrize(
    ("status", "provenance"),
    [
        ("passed", "not_provided"),
        ("failed", "not_verified"),
        ("not_provided", "real"),
        ("not_verified", "controlled_test"),
        ("not_run", "real"),
        ("not_run", "not_provided"),
    ],
)
def test_artifact_status_and_provenance_must_be_honestly_consistent(
    status: str,
    provenance: str,
) -> None:
    with pytest.raises(ValidationError, match="provenance"):
        ReleaseEvidenceInputArtifact.model_validate(
            {
                "id": "dishonest",
                "category": "test",
                "path": "evidence.json" if status in {"passed", "failed"} else None,
                "status": status,
                "provenance": provenance,
            }
        )


def test_failed_real_evidence_makes_bundle_failed_not_incomplete(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "failure.json").write_text('{"status": "failed"}', encoding="utf-8")
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "failure",
                "category": "test",
                "path": "failure.json",
                "status": "failed",
                "provenance": "real",
            },
            {
                "id": "missing",
                "category": "desktop",
                "status": "not_verified",
                "provenance": "not_verified",
            },
        ],
    )

    summary = ReleaseEvidenceRunner(tmp_path / "output", run_id="failed-run").run(manifest)

    assert summary.status == "failed"
    assert summary.counts.failed == 1
    assert summary.counts.not_verified == 1


def test_manifest_itself_must_not_contain_authentication_material(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    manifest = _write_manifest(inputs, [])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["boundaries"] = ["Authorization: Bearer secret-value-123"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReleaseEvidenceError, match="authentication secret"):
        ReleaseEvidenceRunner(tmp_path / "output", run_id="manifest-secret").run(manifest)

    assert not (tmp_path / "output" / "manifest-secret").exists()


def test_runner_rejects_symlinked_artifact_when_supported(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    target = inputs / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = inputs / "linked.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("current environment cannot create a symlink without elevation")
    manifest = _write_manifest(
        inputs,
        [
            {
                "id": "linked",
                "category": "test",
                "path": "linked.json",
                "status": "passed",
                "provenance": "controlled_test",
            }
        ],
    )

    with pytest.raises(ReleaseEvidenceError, match="symlink|reparse"):
        ReleaseEvidenceRunner(tmp_path / "output", run_id="symlink-run").run(manifest)

    assert not (tmp_path / "output" / "symlink-run").exists()
