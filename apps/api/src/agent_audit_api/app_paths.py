"""Operating-system paths used by the desktop application.

The API is also used directly from the repository during development.  This
module keeps the desktop data root independent from the installed application
directory while allowing tests and the desktop launcher to provide an
explicit root.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_DIRECTORY_NAME = "AgentAudit"
LINUX_DIRECTORY_NAME = "agent-audit"
APP_HOME_ENV = "AGENT_AUDIT_HOME"


@dataclass(frozen=True)
class AppPaths:
    """Resolved local directories for one AgentAudit installation.

    Directories are returned as paths only; resolving them does not create
    files or directories.  Creation belongs to the operation that needs the
    directory and therefore remains observable to callers.
    """

    home_dir: Path
    config_dir: Path
    data_dir: Path
    runtime_dir: Path
    logs_dir: Path
    default_workspace_dir: Path


def _default_home() -> Path:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data and local_app_data.strip():
            return Path(local_app_data) / APP_DIRECTORY_NAME
        return Path.home() / "AppData" / "Local" / APP_DIRECTORY_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIRECTORY_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home and xdg_data_home.strip():
        return Path(xdg_data_home) / LINUX_DIRECTORY_NAME
    return Path.home() / ".local" / "share" / LINUX_DIRECTORY_NAME


def resolve_app_paths(home_override: Path | str | None = None) -> AppPaths:
    """Resolve application-owned paths without touching the filesystem.

    ``home_override`` is intended for tests and an explicitly configured
    desktop runtime.  Otherwise ``AGENT_AUDIT_HOME`` takes precedence, then
    the platform's ordinary per-user application-data location is used.
    """

    configured_home = home_override
    if configured_home is None:
        configured_home = os.environ.get(APP_HOME_ENV)
    if configured_home is not None:
        # Explicit application roots are test/launcher boundaries and retain
        # the F-026 layout on every platform.
        home_dir = Path(configured_home).expanduser()
        return AppPaths(
            home_dir=home_dir,
            config_dir=home_dir / "config",
            data_dir=home_dir / "data",
            runtime_dir=home_dir / "data",
            logs_dir=home_dir / "logs",
            default_workspace_dir=home_dir / "workspaces" / "default",
        )

    if sys.platform not in {"win32", "darwin"}:
        # Linux desktop follows XDG's split config/data/state boundaries.
        data_home = os.environ.get("XDG_DATA_HOME")
        config_home = os.environ.get("XDG_CONFIG_HOME")
        state_home = os.environ.get("XDG_STATE_HOME")
        data_dir = (
            Path(data_home) / LINUX_DIRECTORY_NAME
            if data_home and data_home.strip()
            else Path.home() / ".local" / "share" / LINUX_DIRECTORY_NAME
        )
        config_dir = (
            Path(config_home) / LINUX_DIRECTORY_NAME
            if config_home and config_home.strip()
            else Path.home() / ".config" / LINUX_DIRECTORY_NAME
        )
        logs_dir = (
            Path(state_home) / LINUX_DIRECTORY_NAME
            if state_home and state_home.strip()
            else Path.home() / ".local" / "state" / LINUX_DIRECTORY_NAME
        )
        return AppPaths(
            home_dir=data_dir,
            config_dir=config_dir,
            data_dir=data_dir,
            runtime_dir=logs_dir,
            logs_dir=logs_dir,
            default_workspace_dir=data_dir / "workspaces" / "default",
        )

    home_dir = _default_home().expanduser()
    return AppPaths(
        home_dir=home_dir,
        config_dir=home_dir / "config",
        data_dir=home_dir / "data",
        runtime_dir=home_dir / "data",
        logs_dir=home_dir / "logs",
        default_workspace_dir=home_dir / "workspaces" / "default",
    )


__all__ = [
    "APP_DIRECTORY_NAME",
    "APP_HOME_ENV",
    "AppPaths",
    "LINUX_DIRECTORY_NAME",
    "resolve_app_paths",
]
