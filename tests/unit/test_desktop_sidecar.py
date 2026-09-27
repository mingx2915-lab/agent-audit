"""F-026 Sidecar lifecycle and local-only argument contract tests."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import agent_audit_api.desktop_sidecar as sidecar
from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.diagnostic_logging import LOGGER_NAME
from agent_audit_api.workspace import WorkspaceError, WorkspaceService


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SEED = REPOSITORY_ROOT / "data" / "demo"


def _uvicorn_double(run):
    """Adapt existing lifespan probes to Uvicorn's socket-owning Server API."""
    def config(app, **kwargs):
        return app, kwargs
    def server(configured):
        return SimpleNamespace(run=lambda sockets: run(configured[0], **configured[1]))
    return SimpleNamespace(Config=config, Server=server)


class _LifecycleApplication:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def on_event(self, event: str):
        def register(handler):
            self.handlers[event] = handler
            return handler

        return register


def _workspace(tmp_path: Path):
    return WorkspaceService().create(
        tmp_path / "workspace",
        "Sidecar test Workspace",
        seed_dir=DEMO_SEED,
    )


def _read_status(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_parser_accepts_only_locked_local_lifecycle_inputs(tmp_path: Path) -> None:
    args = sidecar.build_parser().parse_args(
        [
            "--host",
            sidecar.LOCAL_HOST,
            "--workspace",
            str(tmp_path / "workspace"),
            "--port",
            "43123",
            "--ready-file",
            str(tmp_path / "status.json"),
        ]
    )

    assert args.host == sidecar.LOCAL_HOST
    assert args.workspace == tmp_path / "workspace"
    assert args.port == 43123
    assert args.ready_file == tmp_path / "status.json"

    with pytest.raises(SystemExit):
        sidecar.build_parser().parse_args(
            [
                "--workspace",
                str(tmp_path / "workspace"),
                "--port",
                "43123",
                "--target",
                "arbitrary-endpoint",
            ]
        )


def test_resolve_seed_dir_has_explicit_source_and_bundled_modes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_root = tmp_path / "source"
    (source_root / "data" / "demo").mkdir(parents=True)
    assert sidecar.resolve_seed_dir(source_root=source_root) == (
        source_root / "data" / "demo"
    ).resolve()

    bundled_root = tmp_path / "bundle"
    (bundled_root / sidecar.BUNDLED_SEED_DIRECTORY).mkdir(parents=True)
    assert sidecar.resolve_seed_dir(bundled_root=bundled_root) == (
        bundled_root / sidecar.BUNDLED_SEED_DIRECTORY
    ).resolve()

    monkeypatch.setattr(sidecar.sys, "frozen", True, raising=False)
    extraction_root = tmp_path / "extracted"
    (extraction_root / sidecar.BUNDLED_SEED_DIRECTORY).mkdir(parents=True)
    monkeypatch.setattr(sidecar.sys, "_MEIPASS", str(extraction_root), raising=False)
    assert sidecar.resolve_seed_dir() == (
        extraction_root / sidecar.BUNDLED_SEED_DIRECTORY
    ).resolve()


def test_resolve_seed_dir_does_not_fallback_when_selected_seed_is_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(WorkspaceError, match="bundled Demo seed directory is unavailable"):
        sidecar.resolve_seed_dir(bundled_root=tmp_path / "missing-bundle")


def test_open_or_initialize_workspace_seeds_an_empty_directory_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    # ``WorkspaceService`` accepts a normal ``data/demo`` seed; use the
    # repository seed here and make the resolution explicit at the Sidecar
    # boundary so this test does not depend on frozen-process globals.
    monkeypatch.setattr(sidecar, "resolve_seed_dir", lambda **kwargs: DEMO_SEED)
    root.mkdir()

    first = sidecar._open_or_initialize_workspace(root)
    first_contract = first.security_contract_path.read_text(encoding="utf-8")
    first.security_contract_path.write_text("changed", encoding="utf-8")
    second = sidecar._open_or_initialize_workspace(root)

    assert second.root == first.root
    assert second.security_contract_path.read_text(encoding="utf-8") == "changed"
    assert first_contract != "changed"


def test_open_or_initialize_workspace_rejects_nonempty_root_without_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "unrelated.txt").write_text("do not overwrite", encoding="utf-8")
    monkeypatch.setattr(sidecar, "resolve_seed_dir", lambda **kwargs: DEMO_SEED)

    with pytest.raises(WorkspaceError, match="contains files but no valid manifest"):
        sidecar._open_or_initialize_workspace(root)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "localhost", "192.168.1.5"])
def test_non_loopback_host_is_rejected_before_app_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    host: str,
) -> None:
    called = False

    def unexpected_create_app(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("create_app must not run for a non-loopback host")

    monkeypatch.setattr(sidecar, "create_app", unexpected_create_app)
    workspace = _workspace(tmp_path)

    with pytest.raises(ValueError, match="127.0.0.1"):
        sidecar.run_sidecar(workspace, host=host, port=43123)

    assert called is False


@pytest.mark.parametrize("port", [0, -1, 65536, 70000])
def test_invalid_port_is_rejected_before_app_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    port: int,
) -> None:
    called = False

    def unexpected_create_app(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("create_app must not run for an invalid port")

    monkeypatch.setattr(sidecar, "create_app", unexpected_create_app)
    workspace = _workspace(tmp_path)

    with pytest.raises(ValueError, match="between 1 and 65535"):
        sidecar.run_sidecar(workspace, port=port)

    assert called is False


def test_run_sidecar_binds_uvicorn_to_loopback_and_records_ready_then_stopped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application = _LifecycleApplication()
    captured: dict[str, object] = {}
    ready_file = tmp_path / "status" / "sidecar.json"

    monkeypatch.setattr(sidecar, "create_app", lambda **kwargs: application)

    def fake_run(app, **kwargs) -> None:
        captured.update(kwargs)
        asyncio.run(app.handlers["startup"]())
        asyncio.run(app.handlers["shutdown"]())

    monkeypatch.setitem(sys.modules, "uvicorn", _uvicorn_double(fake_run))
    sidecar.run_sidecar(
        _workspace(tmp_path),
        host=sidecar.LOCAL_HOST,
        port=43123,
        ready_file=ready_file,
    )

    assert captured == {
        "host": sidecar.LOCAL_HOST,
        "port": 43123,
        "log_level": "warning",
        "access_log": False,
        "log_config": None,
    }
    assert _read_status(ready_file) == {
        "status": "stopped",
        "host": sidecar.LOCAL_HOST,
        "port": 43123,
        "detail": None,
    }


def test_real_create_app_lifespan_marks_ready_and_stopped_and_owns_diagnostic_logger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ready_file = tmp_path / "status" / "sidecar.json"
    app_paths = resolve_app_paths(tmp_path / "app-home")
    observed: list[tuple[str, str, bool]] = []

    def fake_run(application, **_kwargs) -> None:
        async def exercise_lifespan() -> None:
            async with application.router.lifespan_context(application):
                status = _read_status(ready_file)
                logger_active = bool(logging.getLogger(LOGGER_NAME).handlers)
                observed.append(("inside", status["status"], logger_active))

        asyncio.run(exercise_lifespan())
        status = _read_status(ready_file)
        logger_active = bool(logging.getLogger(LOGGER_NAME).handlers)
        observed.append(("after", status["status"], logger_active))

    monkeypatch.setitem(sys.modules, "uvicorn", _uvicorn_double(fake_run))
    sidecar.run_sidecar(
        _workspace(tmp_path),
        port=43123,
        ready_file=ready_file,
        app_paths=app_paths,
    )

    assert observed == [
        ("inside", "ready", True),
        ("after", "stopped", False),
    ]


def test_run_sidecar_surfaces_startup_error_as_failed_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application = _LifecycleApplication()
    ready_file = tmp_path / "status.json"
    monkeypatch.setattr(sidecar, "create_app", lambda **kwargs: application)

    def fail_run(app, **kwargs) -> None:
        raise OSError("address already in use")

    monkeypatch.setitem(sys.modules, "uvicorn", _uvicorn_double(fail_run))

    with pytest.raises(OSError, match="address already in use"):
        sidecar.run_sidecar(
            _workspace(tmp_path),
            port=43123,
            ready_file=ready_file,
        )

    assert _read_status(ready_file) == {
        "status": "failed",
        "host": sidecar.LOCAL_HOST,
        "port": 43123,
        "detail": "OSError: address already in use",
    }


def test_sidecar_startup_diagnostic_qualifies_exception_type_without_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ready_file = tmp_path / "status.json"
    monkeypatch.setattr(sidecar, "create_app", lambda **kwargs: _LifecycleApplication())

    def fail_run(_app, **_kwargs) -> None:
        raise KeyError(4)

    monkeypatch.setitem(sys.modules, "uvicorn", _uvicorn_double(fail_run))

    with pytest.raises(KeyError):
        sidecar.run_sidecar(
            _workspace(tmp_path),
            port=43123,
            ready_file=ready_file,
        )

    status = _read_status(ready_file)
    assert status["detail"] == "KeyError: 4"
    assert "Traceback" not in str(status["detail"])


def test_main_initializes_missing_workspace_before_starting_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ready_file = tmp_path / "status.json"
    workspace_root = tmp_path / "missing-workspace"
    captured: dict[str, object] = {}

    def fake_run_sidecar(workspace, **kwargs) -> None:
        captured["workspace"] = workspace
        captured.update(kwargs)

    monkeypatch.setattr(sidecar, "resolve_seed_dir", lambda **kwargs: DEMO_SEED)
    monkeypatch.setattr(sidecar, "run_sidecar", fake_run_sidecar)

    result = sidecar.main(
        [
            "--host",
            sidecar.LOCAL_HOST,
            "--workspace",
            str(workspace_root),
            "--port",
            "43123",
            "--ready-file",
            str(ready_file),
        ]
    )

    assert result == 0
    assert workspace_root.joinpath(sidecar.MANIFEST_FILENAME).is_file()
    assert captured["workspace"].root == workspace_root.resolve()
    assert captured["host"] == sidecar.LOCAL_HOST
    assert captured["port"] == 43123
    status = _read_status(ready_file)
    assert status["status"] == "starting"
    assert status["host"] == sidecar.LOCAL_HOST
    assert status["port"] == 43123
    assert status["detail"] is None


def test_main_rejects_non_loopback_host_with_diagnostic_status(tmp_path: Path) -> None:
    ready_file = tmp_path / "status.json"

    result = sidecar.main(
        [
            "--host",
            "0.0.0.0",
            "--workspace",
            str(tmp_path / "missing-workspace"),
            "--port",
            "43123",
            "--ready-file",
            str(ready_file),
        ]
    )

    assert result == 1
    status = _read_status(ready_file)
    assert status["status"] == "failed"
    assert status["host"] == sidecar.LOCAL_HOST
    assert "127.0.0.1" in str(status["detail"])
