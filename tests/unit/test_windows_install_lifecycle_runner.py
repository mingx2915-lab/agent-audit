from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = ROOT / "apps" / "desktop" / "scripts" / "windows_install_lifecycle_runner.py"
WINDOWS_CONFIG = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.windows.conf.json"
INSTALLER_HOOKS = ROOT / "apps" / "desktop" / "src-tauri" / "windows" / "installer-hooks.nsh"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "windows_install_lifecycle_runner_for_tests", RUNNER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runner() -> ModuleType:
    return _load_runner()


def _installer(path: Path, content: bytes = b"nsis") -> Path:
    path.write_bytes(content)
    return path


def _args(runner: ModuleType, baseline: Path, upgrade: Path, sandbox: Path, *, upgrade_version: str = "1.1.0"):
    return runner._parser().parse_args(
        [
            "--baseline-installer",
            str(baseline),
            "--baseline-version",
            "1.0.0",
            "--upgrade-installer",
            str(upgrade),
            "--upgrade-version",
            upgrade_version,
            "--sandbox-root",
            str(sandbox),
        ]
    )


def test_preflight_rejects_same_artifact_and_non_upgrade_version(
    runner: ModuleType, tmp_path: Path
) -> None:
    baseline = _installer(tmp_path / "baseline.exe", b"baseline")
    upgrade = _installer(tmp_path / "upgrade.exe", b"upgrade")
    same_artifact = _args(runner, baseline, baseline, tmp_path / "sandbox-a")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(runner, "_assert_no_existing_installation", lambda: None)
    with pytest.raises(runner.RunnerError, match="两个不同工件"):
        runner._preflight(same_artifact, tmp_path / "run-a", tmp_path / "install-a")

    same_version = _args(
        runner, baseline, upgrade, tmp_path / "sandbox-b", upgrade_version="1.0.0"
    )
    with pytest.raises(runner.RunnerError, match="严格高于"):
        runner._preflight(same_version, tmp_path / "run-b", tmp_path / "install-b")
    monkeypatch.undo()


def test_prepare_directories_requires_new_isolated_absolute_paths(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "_protected_roots", lambda: ())
    with pytest.raises(runner.RunnerError, match="绝对路径"):
        runner._prepare_directories("relative-sandbox")

    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(runner.RunnerError, match="运行前不存在"):
        runner._prepare_directories(str(existing))

    with pytest.raises(runner.RunnerError, match="不能含空格"):
        runner._prepare_directories(str(tmp_path / "has space"))

    protected = tmp_path / "protected"
    monkeypatch.setattr(runner, "_protected_roots", lambda: (protected,))
    for candidate in (protected, protected / "child", tmp_path):
        with pytest.raises(runner.RunnerError, match="受保护目录"):
            runner._prepare_directories(str(candidate))

    monkeypatch.setattr(runner, "_protected_roots", lambda: ())
    sandbox = tmp_path / "sandbox"
    install_root, home, run_dir, returned = runner._prepare_directories(str(sandbox))
    assert returned == sandbox.resolve()
    assert install_root == sandbox / "install" and not install_root.exists()
    assert home == sandbox / "home" and list(home.iterdir()) == []
    assert run_dir.parent == sandbox / "evidence"


def test_preflight_refuses_any_existing_current_user_product(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = _installer(tmp_path / "baseline.exe", b"baseline")
    upgrade = _installer(tmp_path / "upgrade.exe", b"upgrade")
    args = _args(runner, baseline, upgrade, tmp_path / "sandbox")
    monkeypatch.setattr(
        runner,
        "_registry_entries",
        lambda: ([{"displayName": runner.PRODUCT_NAME, "installLocation": r"C:\existing"}], None),
    )
    monkeypatch.setattr(runner, "_manufacturer_install_location", lambda: (None, None))
    with pytest.raises(runner.RunnerError, match="拒绝覆盖"):
        runner._preflight(args, tmp_path / "run", tmp_path / "install")

    monkeypatch.setattr(runner, "_registry_entries", lambda: ([], None))
    monkeypatch.setattr(
        runner, "_manufacturer_install_location", lambda: (r"C:\existing", None)
    )
    with pytest.raises(runner.RunnerError, match="拒绝覆盖"):
        runner._preflight(args, tmp_path / "run", tmp_path / "install")


def test_nsis_install_uses_raw_final_unquoted_destination(
    runner: ModuleType, tmp_path: Path
) -> None:
    installer = _installer(tmp_path / "setup.exe")
    install_root = tmp_path / "sandbox" / "install"
    executable, raw = runner._nsis_install_command(installer, install_root)
    assert executable == installer
    assert raw == f"/S /D={install_root}"
    assert '"' not in raw

    with pytest.raises(runner.RunnerError, match="空格"):
        runner._nsis_install_command(installer, tmp_path / "has space" / "install")


def test_uninstall_invokes_only_the_exact_verified_executable_with_silent_flag(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_root = tmp_path / "install"
    install_root.mkdir()
    uninstaller = _installer(install_root / "uninstall.exe")
    calls: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        runner,
        "_verified_uninstall_entry",
        lambda root, version: (
            {"displayVersion": version, "installLocation": str(root)},
            uninstaller,
            ["ignored-registry-argument"],
        ),
    )

    def fake_run(executable, raw_arguments, *, timeout, environment=None):
        calls.append((executable, raw_arguments))
        uninstaller.unlink()
        install_root.rmdir()
        return {"exitCode": 0, "completed": True}

    monkeypatch.setattr(runner, "_run_raw", fake_run)
    monkeypatch.setattr(runner, "_registry_entries", lambda: ([], None))
    monkeypatch.setattr(runner, "_manufacturer_install_location", lambda: (None, None))
    result = runner._uninstall(install_root, "1.1.0", 2.0)
    assert result == {"uninstallerExitCode": 0, "installRootRemoved": True}
    assert calls == [(uninstaller, "/S")]
    assert "_?=" not in calls[0][1]


def test_uninstall_polls_root_and_both_registry_views_until_all_converge(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_root = tmp_path / "install"
    install_root.mkdir()
    uninstaller = _installer(install_root / "uninstall.exe")
    monkeypatch.setattr(
        runner,
        "_verified_uninstall_entry",
        lambda root, version: ({"displayVersion": version}, uninstaller, []),
    )
    monkeypatch.setattr(
        runner,
        "_run_raw",
        lambda *args, **kwargs: {"exitCode": 0, "completed": True},
    )
    clock = [0.0]
    sleeps: list[float] = []
    registry_calls = 0
    manufacturer_calls = 0

    def monotonic() -> float:
        return clock[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    def registry_entries():
        nonlocal registry_calls
        registry_calls += 1
        if registry_calls == 1:
            uninstaller.unlink()
            install_root.rmdir()
        return (
            ([{"displayName": runner.PRODUCT_NAME}] if registry_calls < 3 else []),
            None,
        )

    def manufacturer_location():
        nonlocal manufacturer_calls
        manufacturer_calls += 1
        return (r"C:\stale" if manufacturer_calls < 3 else None, None)

    monkeypatch.setattr(runner.time, "monotonic", monotonic)
    monkeypatch.setattr(runner.time, "sleep", sleep)
    monkeypatch.setattr(runner, "_registry_entries", registry_entries)
    monkeypatch.setattr(runner, "_manufacturer_install_location", manufacturer_location)
    result = runner._uninstall(install_root, "1.1.0", 2.0)
    assert result["installRootRemoved"] is True
    assert registry_calls == 3
    assert manufacturer_calls == 3
    assert sleeps == [0.1, 0.1]


def test_uninstall_registry_query_error_never_passes(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_root = tmp_path / "install"
    install_root.mkdir()
    uninstaller = _installer(install_root / "uninstall.exe")
    monkeypatch.setattr(
        runner,
        "_verified_uninstall_entry",
        lambda root, version: ({}, uninstaller, []),
    )

    def run_and_remove(*args, **kwargs):
        uninstaller.unlink()
        install_root.rmdir()
        return {"exitCode": 0, "completed": True}

    monkeypatch.setattr(runner, "_run_raw", run_and_remove)
    monkeypatch.setattr(runner, "_registry_entries", lambda: ([], "query_failed"))
    monkeypatch.setattr(runner, "_manufacturer_install_location", lambda: (None, None))
    with pytest.raises(runner.RunnerError, match="无法复核"):
        runner._uninstall(install_root, "1.1.0", 0.2)


def test_verified_uninstall_entry_requires_unique_exact_hkcu_match_and_local_exe(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_root = tmp_path / "AgentAudit"
    install_root.mkdir()
    uninstaller = _installer(install_root / "uninstall.exe")
    matching = {
        "displayName": runner.PRODUCT_NAME,
        "displayVersion": "1.1.0",
        "installLocation": str(install_root),
        "uninstallString": f'"{uninstaller}" /S',
        "quietUninstallString": "",
    }
    monkeypatch.setattr(runner, "_registry_entries", lambda: ([matching], None))
    entry, executable, arguments = runner._verified_uninstall_entry(
        install_root, "1.1.0"
    )
    assert entry is matching
    assert executable == uninstaller.resolve()
    assert arguments == ["/S"]

    monkeypatch.setattr(runner, "_registry_entries", lambda: ([matching, matching], None))
    with pytest.raises(runner.RunnerError, match="必须只有一个"):
        runner._verified_uninstall_entry(install_root, "1.1.0")

    outside = _installer(tmp_path / "outside.exe")
    outside_entry = {**matching, "uninstallString": f'"{outside}" /S'}
    monkeypatch.setattr(runner, "_registry_entries", lambda: ([outside_entry], None))
    with pytest.raises(runner.RunnerError, match="不在已验证的安装根目录"):
        runner._verified_uninstall_entry(install_root, "1.1.0")


def test_registry_install_location_accepts_only_one_balanced_outer_quote_pair(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_root = tmp_path / "AgentAudit"
    install_root.mkdir()
    uninstaller = _installer(install_root / "uninstall.exe")
    base = {
        "displayName": runner.PRODUCT_NAME,
        "displayVersion": "1.1.0",
        "uninstallString": f'"{uninstaller}" /S',
        "quietUninstallString": "",
    }

    quoted = {**base, "installLocation": f'"{install_root}"'}
    monkeypatch.setattr(runner, "_registry_entries", lambda: ([quoted], None))
    entry, _, _ = runner._verified_uninstall_entry(install_root, "1.1.0")
    assert entry["installLocation"] == f'"{install_root}"'
    assert runner._same_path(f'"{install_root}"', install_root)

    invalid_values = (
        f'"{install_root}',
        f'{install_root}"',
        f'"{install_root}" /S',
        f'prefix "{install_root}"',
        f'""{install_root}""',
    )
    for value in invalid_values:
        assert not runner._same_path(value, install_root), value
        monkeypatch.setattr(
            runner,
            "_registry_entries",
            lambda value=value: ([{**base, "installLocation": value}], None),
        )
        with pytest.raises(runner.RunnerError, match="必须只有一个"):
            runner._verified_uninstall_entry(install_root, "1.1.0")


def test_process_tree_query_is_rooted_at_exact_pid_and_returns_identity(
    runner: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def fake_ps(script: str):
        captured.append(script)
        return (
            [
                {
                    "ProcessId": 4120,
                    "ParentProcessId": 4000,
                    "ExecutablePath": r"C:\isolated\AgentAudit.exe",
                    "CreationDate": "20260830120000.000000+480",
                },
                {
                    "ProcessId": 4121,
                    "ParentProcessId": 4120,
                    "ExecutablePath": r"C:\isolated\sidecar.exe",
                    "CreationDate": "20260830120001.000000+480",
                },
            ],
            None,
        )

    monkeypatch.setattr(runner, "_ps_json", fake_ps)
    rows, error = runner._process_tree(4120)
    assert error is None
    assert [(row.pid, row.parent_pid) for row in rows] == [(4120, 4000), (4121, 4120)]
    assert all(row.path and row.created for row in rows)
    assert "Find-Tree 4120" in captured[0]
    assert "Get-Process -Name" not in captured[0]


def test_markdown_is_a_projection_of_the_json_evidence(
    runner: ModuleType, tmp_path: Path
) -> None:
    result = {
        "status": "failed",
        "id": "windows_install_test",
        "startedAt": "2026-08-30T00:00:00.000Z",
        "completedAt": "2026-08-30T00:00:01.000Z",
        "inputs": {
            "baseline": {
                "version": "1.0.0",
                "name": "baseline.exe",
                "sha256": "a" * 64,
            },
            "upgrade": {
                "version": "1.1.0",
                "name": "upgrade.exe",
                "sha256": "b" * 64,
            },
        },
        "checks": [{"id": "upgrade_preserved_data", "status": "failed", "detail": "mismatch"}],
        "phases": [{"id": "upgrade", "status": "failed"}],
        "limitations": ["isolated current-user run"],
    }
    runner._write(result, tmp_path)
    persisted = json.loads((tmp_path / "windows-install-lifecycle.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "windows-install-lifecycle.md").read_text(encoding="utf-8")
    assert markdown == runner._markdown(persisted)
    assert "`upgrade_preserved_data` | `failed` | mismatch" in markdown


def test_database_snapshot_records_explicit_ids_counts_and_integrity(
    runner: ModuleType, tmp_path: Path
) -> None:
    database = tmp_path / "agent_audit.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE audit_runs (scan_id TEXT PRIMARY KEY);
        CREATE TABLE acceptance_runs (run_id TEXT PRIMARY KEY);
        INSERT INTO audit_runs VALUES ('scan_baseline_001');
        INSERT INTO audit_runs VALUES ('scan_baseline_002');
        INSERT INTO acceptance_runs VALUES ('acceptance_baseline_001');
        """
    )
    connection.commit()
    connection.close()

    snapshot = runner._database_snapshot(database)
    assert snapshot == {
        "integrity": "ok",
        "auditRunCount": 2,
        "auditRunIds": ["scan_baseline_001", "scan_baseline_002"],
        "acceptanceRunCount": 1,
        "acceptanceRunIds": ["acceptance_baseline_001"],
    }


def test_controlled_history_records_non_empty_acceptance_ids(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = type(
        "ControlledWorkflow",
        (),
        {
            "provider_id": "deterministic_test_provider",
            "retriever_id": "tfidf_test_retriever",
            "scan_id": "scan_controlled_001",
            "acceptance_id": "acceptance_controlled_001",
        },
    )()
    import agent_audit_api.controlled_release_workflow as controlled_workflow

    async def fake_workflow(root: Path):
        return workflow

    monkeypatch.setattr(controlled_workflow, "build_controlled_release_workflow", fake_workflow)

    result = runner._create_controlled_history(tmp_path / "workspace")

    assert result["scanIds"] == ["scan_controlled_001"]
    assert result["acceptanceIds"] == ["acceptance_controlled_001"]
    assert all(result["acceptanceIds"])


@pytest.mark.parametrize("missing", ["scan_id", "acceptance_id"])
def test_controlled_history_rejects_empty_history_ids(
    runner: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    import agent_audit_api.controlled_release_workflow as controlled_workflow

    workflow = type(
        "ControlledWorkflow",
        (),
        {
            "scan_id": "" if missing == "scan_id" else "scan_controlled_001",
            "acceptance_id": "" if missing == "acceptance_id" else "acceptance_controlled_001",
        },
    )()

    async def fake_workflow(_root: Path) -> object:
        return workflow

    monkeypatch.setattr(controlled_workflow, "build_controlled_release_workflow", fake_workflow)

    with pytest.raises(runner.RunnerError, match="非空 Scan/Acceptance History"):
        runner._create_controlled_history(tmp_path / "workspace")


def test_controlled_history_failure_is_a_runner_error(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agent_audit_api.controlled_release_workflow as controlled_workflow

    async def broken_workflow(_root: Path) -> object:
        raise RuntimeError("controlled workflow failed")

    monkeypatch.setattr(controlled_workflow, "build_controlled_release_workflow", broken_workflow)

    with pytest.raises(runner.RunnerError, match="controlled workflow failed"):
        runner._create_controlled_history(tmp_path / "workspace")


def test_execute_lifecycle_uses_two_versions_and_preserves_exact_snapshot(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_path = _installer(tmp_path / "baseline.exe", b"baseline")
    upgrade_path = _installer(tmp_path / "upgrade.exe", b"upgrade")
    baseline = runner._installer(str(baseline_path), "1.0.0", "baseline")
    upgrade = runner._installer(str(upgrade_path), "1.1.0", "upgrade")
    args = _args(runner, baseline_path, upgrade_path, tmp_path / "sandbox")
    result = runner._base_result(args, tmp_path / "run", baseline, upgrade)
    install_root = tmp_path / "install"
    home = tmp_path / "home"
    home.mkdir()
    workspace = home / "workspaces" / "default"
    workspace.mkdir(parents=True)

    operations: list[str] = []
    monkeypatch.setattr(
        runner,
        "_install",
        lambda item, root, timeout, *, installed_version=None: operations.append(
            f"install:{item.version}:from:{installed_version}"
        )
        or {"installerVersion": item.version},
    )
    monkeypatch.setattr(runner, "_installed_desktop", lambda root: root / "agent-audit-desktop.exe")

    session_count = 0

    def fake_session(artifact, session_home, ready_timeout, exit_timeout, action=None):
        nonlocal session_count
        session_count += 1
        operations.append(f"launch:{session_count}")
        if action is not None:
            action(60123)
        return {"status": "passed"}

    monkeypatch.setattr(runner, "_desktop_session", fake_session)
    monkeypatch.setattr(runner, "_write_marker", lambda port: "doc_marker_001")
    monkeypatch.setattr(
        runner,
        "_create_controlled_history",
        lambda root: {
            "provider": "deterministic_test_provider",
            "retriever": "tfidf_test_retriever",
            "scanIds": ["scan_001"],
            "acceptanceIds": ["acceptance_001"],
        },
    )
    snapshot = {
        "manifestId": "workspace_default",
        "markerDocumentId": "doc_marker_001",
        "markerPresent": True,
        "hashes": {"manifest": "a" * 64, "contract": "b" * 64, "documents": "c" * 64},
        "database": {
            "integrity": "ok",
            "auditRunCount": 1,
            "auditRunIds": ["scan_001"],
            "acceptanceRunCount": 1,
            "acceptanceRunIds": ["acceptance_001"],
        },
    }
    monkeypatch.setattr(runner, "_workspace_paths", lambda value: (workspace, workspace / "history" / runner.HISTORY_NAME))
    monkeypatch.setattr(runner, "_workspace_snapshot", lambda value, marker: dict(snapshot))
    monkeypatch.setattr(
        runner,
        "_uninstall",
        lambda root, version, timeout: operations.append(f"uninstall:{version}")
        or {"installRootRemoved": True},
    )

    completed = runner._execute_lifecycle(
        args, result, baseline, upgrade, install_root, home
    )
    assert completed["status"] == "passed"
    assert completed["phases"][2]["detail"]["acceptanceIds"] == [
        "acceptance_001"
    ]
    snapshot_phases = {
        phase["id"]: phase["detail"]
        for phase in completed["phases"]
        if phase["id"] in {
            "baseline_snapshot",
            "upgrade_data_preserved",
            "uninstall_user_data_preserved",
        }
    }
    assert set(snapshot_phases) == {
        "baseline_snapshot",
        "upgrade_data_preserved",
        "uninstall_user_data_preserved",
    }
    for detail in snapshot_phases.values():
        assert detail["database"]["acceptanceRunCount"] == 1
        assert detail["database"]["acceptanceRunIds"] == ["acceptance_001"]
    assert operations == [
        "install:1.0.0:from:None",
        "launch:1",
        "install:1.1.0:from:1.0.0",
        "launch:2",
        "uninstall:1.1.0",
    ]
    assert [phase["id"] for phase in completed["phases"]] == [
        "baseline_install",
        "baseline_launch_and_marker",
        "controlled_history",
        "baseline_snapshot",
        "upgrade_install",
        "upgraded_launch",
        "upgrade_data_preserved",
        "uninstall",
        "uninstall_user_data_preserved",
    ]
    assert completed["checks"][-1]["id"] == "complete_install_upgrade_uninstall"


def test_lifecycle_failure_stops_without_running_later_cleanup(
    runner: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline_path = _installer(tmp_path / "baseline.exe", b"baseline")
    upgrade_path = _installer(tmp_path / "upgrade.exe", b"upgrade")
    baseline = runner._installer(str(baseline_path), "1.0.0", "baseline")
    upgrade = runner._installer(str(upgrade_path), "1.1.0", "upgrade")
    args = _args(runner, baseline_path, upgrade_path, tmp_path / "sandbox")
    result = runner._base_result(args, tmp_path / "run", baseline, upgrade)
    calls: list[str] = []

    def fail_baseline(item, root, timeout, *, installed_version=None):
        assert installed_version is None
        calls.append("baseline")
        raise runner.RunnerError("baseline failed")

    monkeypatch.setattr(runner, "_install", fail_baseline)
    monkeypatch.setattr(
        runner,
        "_uninstall",
        lambda *values: calls.append("uninstall"),
    )
    with pytest.raises(runner.RunnerError, match="baseline failed"):
        runner._execute_lifecycle(
            args, result, baseline, upgrade, tmp_path / "install", tmp_path / "home"
        )
    assert calls == ["baseline"]
    assert result["phases"] == [
        {
            "id": "baseline_install",
            "status": "failed",
            "durationMs": result["phases"][0]["durationMs"],
            "detail": "baseline failed",
        }
    ]


def test_runner_source_has_no_name_based_or_recursive_directory_cleanup() -> None:
    source = RUNNER_PATH.read_text(encoding="utf-8")
    assert "taskkill" not in source.casefold()
    assert "get-process -name" not in source.casefold()
    assert "stop-process -name" not in source.casefold()
    assert "rmtree(" not in source
    assert "shutil.rmtree" not in source
    assert 'f"/S _?=' not in source
    assert '"/S _?=' not in source


def test_windows_nsis_config_uses_current_user_preserving_installer_hook() -> None:
    config = json.loads(WINDOWS_CONFIG.read_text(encoding="utf-8"))
    assert config["bundle"]["targets"] == ["nsis"]
    nsis = config["bundle"]["windows"]["nsis"]
    assert nsis == {
        "installMode": "currentUser",
        "installerHooks": "windows/installer-hooks.nsh",
    }
    assert (WINDOWS_CONFIG.parent / nsis["installerHooks"]).resolve() == INSTALLER_HOOKS.resolve()
    assert INSTALLER_HOOKS.is_file()


def test_uninstall_hook_only_removes_installer_owned_registry_keys() -> None:
    source = INSTALLER_HOOKS.read_text(encoding="utf-8")
    executable_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip() and not line.lstrip().startswith(";")
    ]
    assert executable_lines == [
        "!macro NSIS_HOOK_POSTUNINSTALL",
        'DeleteRegKey SHCTX "${MANUPRODUCTKEY}"',
        'DeleteRegKey /ifempty SHCTX "${MANUKEY}"',
        "!macroend",
    ]
    forbidden = (
        "$appdata",
        "$localappdata",
        "workspace",
        "agent_audit_home",
        "rmdir",
        "delete ",
        "delfile",
        "rmfile",
    )
    lowered = source.casefold()
    assert all(token not in lowered for token in forbidden)
