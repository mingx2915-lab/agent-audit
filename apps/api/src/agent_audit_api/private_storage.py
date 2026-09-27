"""Owner-only POSIX permissions for application-owned persistent files."""

from __future__ import annotations

import os
import stat
from pathlib import Path


def ensure_private_directory(path: Path) -> None:
    """Secure this application directory, without changing its ancestors."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        path.chmod(0o700)


def ensure_private_file(path: Path) -> None:
    """Create with 0600 or remove group/other access without adding owner rights."""
    if os.name != "posix":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        try:
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError:
            descriptor = os.open(path, os.O_RDONLY)
    try:
        current_mode = stat.S_IMODE(os.fstat(descriptor).st_mode)
        private_mode = current_mode & 0o600
        if current_mode != private_mode:
            os.fchmod(descriptor, private_mode)
    finally:
        os.close(descriptor)


def prepare_private_sqlite(path: Path) -> None:
    """Set the database mode before SQLite opens or creates auxiliary files."""
    ensure_private_file(path)
    if os.name == "posix":
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(path) + suffix)
            try:
                current_mode = stat.S_IMODE(sidecar.stat().st_mode)
                private_mode = current_mode & 0o600
                if current_mode != private_mode:
                    sidecar.chmod(private_mode)
            except FileNotFoundError:
                # SQLite removes auxiliary files when connections close.
                pass
