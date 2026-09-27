"""Owner-only POSIX permissions for application-owned persistent files."""

from __future__ import annotations

import os
from pathlib import Path


def ensure_private_directory(path: Path) -> None:
    """Secure this application directory, without changing its ancestors."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix":
        path.chmod(0o700)


def ensure_private_file(path: Path) -> None:
    """Create with 0600 or restrict an existing file without truncating it."""
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def prepare_private_sqlite(path: Path) -> None:
    """Set the database mode before SQLite opens or creates auxiliary files."""
    ensure_private_file(path)
    if os.name == "posix":
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                Path(str(path) + suffix).chmod(0o600)
            except FileNotFoundError:
                # SQLite removes auxiliary files when connections close.
                pass
