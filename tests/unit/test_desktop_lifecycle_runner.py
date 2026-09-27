"""High-value contract tests for the explicit Desktop lifecycle runner.

The runner is imported as a script because it is intentionally not a Python
package entrypoint.  These tests exercise only validation, Workspace/SQLite
observation, artifact projection, and the process-identity cleanup helper;
they never launch a Desktop or Sidecar artifact.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from agent_audit_api.workspace import WorkspaceService
from agent_audit_api.history import SQLiteAuditRunRepository
from tests.unit.test_history_repository import _detail as make_scan_detail


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY_ROOT / "apps" / "desktop" / "scripts" / "desktop_lifecycle_runner.py"
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"
RUNNER_MODULE_NAME = "agent_audit_desktop_lifecycle_runner_f036"


@pytest.fixture(scope="module")
def runner_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(RUNNER_MODULE_NAME, RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load Desktop runner from {RUNNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[RUNNER_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def _required_args(tmp_path: Path) -> list[str]:
    return [
        "--iterations",
        "1",
        "--output-dir",
        str(tmp_path / "output"),
        "--agent-audit-home",
        str(tmp_path / "home"),
    ]


def test_runner_bounds_iterations_at_one_hundred_and_requires_artifact_kind(
    runner_module: ModuleType,
    tmp_path: Path,
) -> None:
    parser = runner_module._parser()
    assert runner_module.MAX_ITERATIONS == 100

    for kind in ("desktop", "sidecar"):
        args = parser.parse_args(
            [*_required_args(tmp_path), "--artifact-kind", kind]
        )
        assert args.iterations == 1
        assert args.artifact_kind == kind

    with pytest.raises(SystemExit) as missing_kind:
        parser.parse_args(_required_args(tmp_path))
    assert missing_kind.value.code == 2

    with pytest.raises(SystemExit) as invalid_kind:
        parser.parse_args(
            [*_required_args(tmp_path), "--artifact-kind", "unknown"]
        )
    assert invalid_kind.value.code == 2

    # argparse accepts the integer; main() owns the bounded-value check so it
    # can keep setup side effects out of the failure path.
    over_limit = parser.parse_args(
        [
            "--artifact-kind",
            "sidecar",
            "--iterations",
            str(runner_module.MAX_ITERATIONS + 1),
            "--output-dir",
            str(tmp_path / "output"),
            "--agent-audit-home",
            str(tmp_path / "home"),
        ]
    )
    assert over_limit.iterations == runner_module.MAX_ITERATIONS + 1


def test_runner_main_rejects_over_limit_without_creating_run_directory(
    runner_module: ModuleType,
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    home = tmp_path / "home"

    with pytest.raises(SystemExit) as exc_info:
        runner_module.main(
            [
                "--artifact-kind",
                "sidecar",
                "--iterations",
                str(runner_module.MAX_ITERATIONS + 1),
                "--output-dir",
                str(output),
                "--agent-audit-home",
                str(home),
            ]
        )

    assert exc_info.value.code == 2
    assert not output.exists()
    assert not home.exists()


def test_workspace_observation_reads_real_history_sqlite(tmp_path: Path, runner_module: ModuleType) -> None:
    home = tmp_path / "app-home"
    workspace = WorkspaceService().create(
        home / "workspaces" / "default",
        "F-036 lifecycle observation",
        seed_dir=DEMO_SEED,
    )
    repository = SQLiteAuditRunRepository(workspace.history_db_path)
    repository.save(make_scan_detail(scan_id="f036_desktop_observation"))

    observation = runner_module._workspace(home)

    assert observation["rootPresent"] is True
    assert observation["manifest"] == {
        "status": "readable",
        "readable": True,
        "requiredDirectories": [
            {"name": name, "present": True}
            for name in (
                "documentsDir",
                "contractDir",
                "casesDir",
                "historyDir",
                "exportsDir",
            )
        ],
        "error": None,
    }
    assert observation["sqlite"]["status"] == "readable"
    assert observation["sqlite"]["readable"] is True
    assert observation["sqlite"]["integrity"] == "ok"
    # audit_runs has one saved row and audit_replays is empty.  The runner
    # counts actual SQLite rows, not the mere presence of the database file.
    assert observation["sqlite"]["rowCount"] == 1
    assert observation["sqlite"]["error"] is None

    with sqlite3.connect(workspace.history_db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM audit_runs").fetchone() == (1,)


def test_setup_failure_reports_without_unbound_run_directory(
    runner_module: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_file = tmp_path / "output-file"
    output_file.write_text("reserved output path", encoding="utf-8")
    home = tmp_path / "home"

    exit_code = runner_module.main(
        [
            "--artifact-kind",
            "desktop",
            "--iterations",
            "1",
            "--output-dir",
            str(output_file),
            "--agent-audit-home",
            str(home),
        ]
    )

    assert exit_code == 2
    error_lines = [line for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert error_lines
    payload = json.loads(error_lines[-1])
    assert payload["status"] == "failed"
    assert payload["check"] == "runner_setup"
    assert payload["artifactPathProvided"] is False
    assert "directory" not in payload
    assert not home.exists()
    assert output_file.read_text(encoding="utf-8") == "reserved output path"


def test_skip_writes_json_and_markdown_from_one_run_directory(
    runner_module: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "output"
    home = tmp_path / "home"

    exit_code = runner_module.main(
        [
            "--artifact-kind",
            "sidecar",
            "--iterations",
            "1",
            "--output-dir",
            str(output),
            "--agent-audit-home",
            str(home),
        ]
    )

    assert exit_code == 0
    stdout = json.loads(capsys.readouterr().out.strip())
    run_dirs = [path for path in output.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    assert stdout["status"] == "skipped"
    assert stdout["directory"] == run_dirs[0].name

    json_path = run_dirs[0] / "desktop-lifecycle.json"
    markdown_path = run_dirs[0] / "desktop-lifecycle.md"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["status"] == "skipped"
    assert payload["environment"]["artifact"] is None
    assert payload["environment"]["artifactPathProvided"] is False
    assert payload["checks"]
    assert all(check["status"] == "skipped" for check in payload["checks"])
    assert payload["artifacts"] == {
        "json": "desktop-lifecycle.json",
        "markdown": "desktop-lifecycle.md",
        "directory": run_dirs[0].name,
    }
    assert f"状态：`{payload['status']}`" in markdown
    assert f"Run ID：`{payload['id']}`" in markdown
    assert "本 Markdown 由同目录 `desktop-lifecycle.json` 投影生成" in markdown
    assert all(limitation in markdown for limitation in payload["limitations"])


def test_powershell_path_uses_system_root_without_windows_literal_fallback(
    runner_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SystemRoot", raising=False)
    assert runner_module._powershell() is None

    explicit_root = tmp_path / "synthetic-system-root"
    explicit_root.mkdir()
    monkeypatch.setenv("SystemRoot", str(explicit_root))
    assert runner_module._powershell() is None


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.returncode: int | None = None

    def poll(self) -> None:
        return self.returncode

    def kill(self) -> None:
        self.returncode = 137

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = self.returncode if self.returncode is not None else 137
        return self.returncode


def test_crash_root_query_loss_cleans_only_verified_known_descendant_tree(
    runner_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "owned-sidecar.exe"
    artifact.write_bytes(b"synthetic artifact placeholder")
    process = _FakeProcess(100)
    root = runner_module.ProcessInfo(
        pid=100,
        parent_pid=None,
        path=str(artifact),
        created="root-created",
        working_set=1,
    )
    child = runner_module.ProcessInfo(
        pid=101,
        parent_pid=100,
        path=str(artifact),
        created="child-created",
        working_set=2,
    )
    grandchild = runner_module.ProcessInfo(
        pid=102,
        parent_pid=101,
        path=str(artifact),
        created="grandchild-created",
        working_set=3,
    )
    observed = [root, child, grandchild]
    actions: list[tuple[int, str]] = []

    def process_query(pid: int, tree: bool = False):
        assert tree is False
        if pid == root.pid:
            return [], "root_query_failed"
        current = {child.pid: child, grandchild.pid: grandchild}.get(pid)
        return ([] if current is None else [current]), None

    def taskkill(pid: int, method: str) -> dict[str, Any]:
        actions.append((pid, method))
        return {
            "status": "forced_owned_tree_termination",
            "method": method,
            "identityVerified": True,
        }

    monkeypatch.setattr(runner_module, "_process", process_query)
    monkeypatch.setattr(runner_module, "_taskkill_tree", taskkill)
    monkeypatch.setattr(
        runner_module,
        "_wait_identity_gone",
        lambda current, timeout: ("gone", None),
    )

    result = runner_module._terminate(
        process,
        artifact,
        "sidecar",
        True,
        1.0,
        observed,
    )

    cleanup = result["exactDescendantCleanup"]
    # Root identity was unavailable, so the aggregate remains conservative;
    # the exact descendant helper still records its own verified action below.
    assert result["method"] == "popen_exact_handle"
    assert result["terminationNote"].startswith("precise crash-recovery")
    assert cleanup["rootObserved"] is True
    assert cleanup["candidatePids"] == [child.pid]
    assert [item["pid"] for item in cleanup["verifiedDescendants"]] == [child.pid]
    assert cleanup["queryErrors"] == ["root_query_failed"]
    assert cleanup["actions"][0]["pid"] == child.pid
    assert cleanup["actions"][0]["postTermination"] == "gone"
    assert actions == [(child.pid, "taskkill_tree_exact_descendant")]
