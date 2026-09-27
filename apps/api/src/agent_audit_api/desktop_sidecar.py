"""Fixed-lifecycle local API Sidecar entrypoint for the Desktop shell."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from .app_paths import AppPaths, resolve_app_paths
from .main import create_app
from .schemas import DesktopRuntimeStatus
from .workspace import (
    MANIFEST_FILENAME,
    AuditWorkspace,
    WorkspaceError,
    WorkspaceService,
)


LOCAL_HOST = "127.0.0.1"
BUNDLED_SEED_DIRECTORY = "demo-seed"


def build_parser() -> argparse.ArgumentParser:
    """Build the deliberately small Desktop lifecycle argument surface."""

    parser = argparse.ArgumentParser(
        prog="agent-audit-sidecar",
        description="Run the local AgentAudit API for the Desktop shell.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--host",
        default=LOCAL_HOST,
        help="local host; only 127.0.0.1 is supported",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        type=Path,
        help="validated Audit Workspace directory",
    )
    parser.add_argument(
        "--port",
        required=True,
        type=int,
        help="local loopback port selected by the Desktop shell",
    )
    parser.add_argument(
        "--ready-file",
        type=Path,
        default=None,
        help="optional local status file written during Sidecar lifecycle",
    )
    return parser


def _write_status(path: Path | None, status: DesktopRuntimeStatus) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                status.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise RuntimeError("unable to write Desktop Sidecar status") from exc


def _validate_port(port: int) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("Sidecar port must be between 1 and 65535")


def _validate_host(host: str) -> None:
    if host != LOCAL_HOST:
        raise ValueError("Desktop Sidecar host must be 127.0.0.1")


def _exception_detail(exc: BaseException) -> str:
    """Return a bounded type-qualified startup diagnostic without a traceback.

    Provider and Workspace boundaries already expose only user-safe messages.
    The Sidecar status is also consumed by the local Desktop shell, so keep the
    diagnostic to the exception type and its first-line message; never include
    a traceback, exception repr, environment, or chained exception details.
    """

    type_name = type(exc).__name__
    message = " ".join(str(exc).split())
    if not message:
        return type_name
    return f"{type_name}: {message}"[:500]


def resolve_seed_dir(
    *,
    source_root: str | Path | None = None,
    bundled_root: str | Path | None = None,
) -> Path:
    """Resolve the fixed Demo seed location for source or frozen execution.

    Source execution uses the repository's module-relative ``data/demo``.
    PyInstaller execution uses the bundle's ``demo-seed`` resource.  A caller
    can provide either root explicitly for packaging tests; a missing seed is
    an error and never switches to the other execution mode.
    """

    is_frozen = bool(getattr(sys, "frozen", False))
    if bundled_root is not None:
        seed_dir = Path(bundled_root).expanduser().resolve() / BUNDLED_SEED_DIRECTORY
    elif is_frozen:
        extraction_root = getattr(sys, "_MEIPASS", None)
        if extraction_root is None:
            extraction_root = Path(sys.executable).resolve().parent
        seed_dir = Path(extraction_root).expanduser().resolve() / BUNDLED_SEED_DIRECTORY
    elif source_root is not None:
        seed_dir = Path(source_root).expanduser().resolve() / "data" / "demo"
    else:
        seed_dir = Path(__file__).resolve().parents[4] / "data" / "demo"

    if not seed_dir.is_dir():
        mode = "bundled" if is_frozen or bundled_root is not None else "source"
        raise WorkspaceError(
            f"{mode} Demo seed directory is unavailable: {seed_dir}"
        )
    return seed_dir


def _open_or_initialize_workspace(
    root: Path,
    *,
    app_paths: AppPaths | None = None,
) -> AuditWorkspace:
    service = WorkspaceService(app_paths=app_paths)
    workspace_root = root.expanduser().resolve()
    if (workspace_root / MANIFEST_FILENAME).is_file():
        return service.open(workspace_root)
    seed_dir = resolve_seed_dir()
    return service.ensure_default(seed_dir, root=workspace_root)


def _install_lifecycle_status(
    application,
    *,
    ready_file: Path | None,
    port: int,
) -> None:
    existing_lifespan = application.router.lifespan_context
    application.state.sidecar_port = port

    @asynccontextmanager
    async def sidecar_lifespan(app):  # type: ignore[no-untyped-def]
        async with existing_lifespan(app):
            _write_status(
                ready_file,
                DesktopRuntimeStatus(status="ready", host=LOCAL_HOST, port=port),
            )
            try:
                yield
            finally:
                _write_status(
                    ready_file,
                    DesktopRuntimeStatus(
                        status="stopped", host=LOCAL_HOST, port=port
                    ),
                )

    application.router.lifespan_context = sidecar_lifespan


def _install_legacy_lifecycle_status(
    application,
    *,
    ready_file: Path | None,
    port: int,
) -> None:
    """Compatibility boundary for deliberately tiny application test doubles."""

    @application.on_event("startup")
    async def _mark_ready() -> None:
        _write_status(
            ready_file,
            DesktopRuntimeStatus(status="ready", host=LOCAL_HOST, port=port),
        )

    @application.on_event("shutdown")
    async def _mark_stopped() -> None:
        _write_status(
            ready_file,
            DesktopRuntimeStatus(status="stopped", host=LOCAL_HOST, port=port),
        )


def run_sidecar(
    workspace: AuditWorkspace,
    *,
    port: int,
    host: str = LOCAL_HOST,
    ready_file: Path | None = None,
    app_paths: AppPaths | None = None,
) -> None:
    """Run one Workspace-bound API process on loopback until Desktop closes it."""

    _validate_host(host)
    _validate_port(port)
    application = create_app(
        workspace=workspace,
        app_paths=app_paths if app_paths is not None else resolve_app_paths(),
    )
    if hasattr(application, "router") and hasattr(
        application.router, "lifespan_context"
    ):
        _install_lifecycle_status(application, ready_file=ready_file, port=port)
    else:
        _install_legacy_lifecycle_status(
            application, ready_file=ready_file, port=port
        )

    try:
        import uvicorn

        # Bind before entering the application lifespan: readiness means the
        # endpoint is owned, and a bind error retains its original OSError.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            if sys.platform != "win32":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((LOCAL_HOST, port))
            config = uvicorn.Config(
                application,
                host=LOCAL_HOST,
                port=port,
                log_level="warning",
                access_log=False,
                log_config=None,
            )
            uvicorn.Server(config).run(sockets=[listener])
    except (Exception, SystemExit) as exc:
        _write_status(
            ready_file,
            DesktopRuntimeStatus(
                status="failed",
                host=LOCAL_HOST,
                port=port,
                detail=_exception_detail(exc),
            ),
        )
        raise


def main(argv: Sequence[str] | None = None) -> int:
    """Validate fixed lifecycle inputs and start the Desktop Sidecar."""

    args = build_parser().parse_args(argv)
    try:
        _validate_host(args.host)
        _validate_port(args.port)
        app_paths = resolve_app_paths()
        workspace = _open_or_initialize_workspace(
            args.workspace,
            app_paths=app_paths,
        )
        _write_status(
            args.ready_file,
            DesktopRuntimeStatus(status="starting", host=LOCAL_HOST, port=args.port),
        )
        run_sidecar(
            workspace,
            host=args.host,
            port=args.port,
            ready_file=args.ready_file,
            app_paths=app_paths,
        )
    except Exception as exc:
        detail = _exception_detail(exc)
        try:
            _write_status(
                args.ready_file,
                DesktopRuntimeStatus(
                    status="failed",
                    host=LOCAL_HOST,
                    port=args.port,
                    detail=detail,
                ),
            )
        except RuntimeError:
            pass
        print(f"agent-audit-sidecar: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by packaged entrypoint
    raise SystemExit(main())


__all__ = [
    "LOCAL_HOST",
    "BUNDLED_SEED_DIRECTORY",
    "build_parser",
    "main",
    "resolve_seed_dir",
    "run_sidecar",
]
