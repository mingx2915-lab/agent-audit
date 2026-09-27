"""POSIX confidentiality of persistent history and rotating diagnostics."""
from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.diagnostic_logging import (
    close_bounded_logging, configure_bounded_logging, log_event,
)
from agent_audit_api.sqlite_schema import SQLiteSchemaManager
from agent_audit_api.workspace import WorkspaceService
from agent_audit_api.workspace_archive import WorkspaceArchiveService
from agent_audit_api.sqlite_schema import SQLiteSchemaError

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX permission bits')
ROOT = Path(__file__).resolve().parents[2]

def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)

def test_database_is_private_before_sqlite_first_opens_it(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / 'history' / 'agent_audit.sqlite3'
    original = sqlite3.connect
    def checked_connect(filename, *args, **kwargs):
        assert Path(filename).exists()
        assert mode(Path(filename)) == 0o600
        return original(filename, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', checked_connect)
    previous = os.umask(0)
    try:
        connection = SQLiteSchemaManager(path).connect()
        connection.close()
    finally:
        os.umask(previous)
    assert mode(path) == 0o600

def test_existing_database_is_restricted_without_losing_rows(tmp_path: Path) -> None:
    path = tmp_path / 'agent_audit.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE private_marker(value TEXT)')
        connection.execute("INSERT INTO private_marker VALUES ('synthetic retained record')")
    path.chmod(0o644)
    connection = SQLiteSchemaManager(path).connect()
    try:
        assert mode(path) == 0o600
        assert connection.execute('SELECT value FROM private_marker').fetchone()[0] == 'synthetic retained record'
    finally:
        connection.close()

@pytest.mark.parametrize('journal_mode,suffixes', [('WAL', ['-wal', '-shm']), ('PERSIST', ['-journal'])])
def test_sqlite_creates_private_auxiliary_files(tmp_path: Path, journal_mode: str, suffixes: list[str]) -> None:
    path = tmp_path / 'agent_audit.sqlite3'
    previous = os.umask(0)
    connection = None
    try:
        connection = SQLiteSchemaManager(path).connect()
        connection.execute(f'PRAGMA journal_mode={journal_mode}')
        connection.execute('CREATE TABLE private_marker(value TEXT)')
        connection.execute("INSERT INTO private_marker VALUES ('synthetic')")
        connection.commit()
        for suffix in suffixes:
            assert mode(Path(str(path) + suffix)) == 0o600
    finally:
        if connection is not None:
            connection.close()
        os.umask(previous)

def test_existing_live_wal_and_shm_are_restricted(tmp_path: Path) -> None:
    path = tmp_path / 'agent_audit.sqlite3'
    first = SQLiteSchemaManager(path).connect()
    second = None
    try:
        first.execute('PRAGMA journal_mode=WAL')
        first.execute('CREATE TABLE private_marker(value TEXT)')
        first.execute("INSERT INTO private_marker VALUES ('retained WAL record')")
        first.commit()
        files = [path, Path(str(path)+'-wal'), Path(str(path)+'-shm')]
        for file in files:
            file.chmod(0o644)
        second = SQLiteSchemaManager(path).connect()
        assert all(mode(file) == 0o600 for file in files)
        assert second.execute('SELECT value FROM private_marker').fetchone()[0] == 'retained WAL record'
    finally:
        if second is not None:
            second.close()
        first.close()

def test_workspace_open_repairs_history_permissions_and_retains_data(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path/'app')
    service = WorkspaceService(paths)
    workspace = service.create(paths.default_workspace_dir, '中文 Workspace', seed_dir=ROOT/'data/demo')
    assert mode(workspace.history_path) == 0o700
    connection = SQLiteSchemaManager(workspace.history_database_path).connect()
    connection.execute('CREATE TABLE private_marker(value TEXT)')
    connection.execute("INSERT INTO private_marker VALUES ('keep me')")
    connection.commit();connection.close()
    workspace.history_path.chmod(0o755)
    workspace.history_database_path.chmod(0o644)
    reopened = service.open(workspace.root)
    assert mode(reopened.history_path) == 0o700
    assert mode(reopened.history_database_path) == 0o600
    with sqlite3.connect(reopened.history_database_path) as connection:
        assert connection.execute('SELECT value FROM private_marker').fetchone()[0] == 'keep me'

def test_logs_and_rotations_remain_private(tmp_path: Path) -> None:
    logs = tmp_path/'logs'
    previous = os.umask(0)
    try:
        path = configure_bounded_logging(logs, max_bytes=300, backup_count=3)
        for _ in range(12):
            log_event('permission_test', status='ready')
        assert mode(logs) == 0o700
        files = list(logs.glob('agent-audit.jsonl*'))
        assert len(files) > 1
        assert all(mode(file) == 0o600 for file in files)
    finally:
        close_bounded_logging();os.umask(previous)

def test_existing_logs_are_restricted_without_rewriting_content(tmp_path: Path) -> None:
    logs = tmp_path/'logs';logs.mkdir(mode=0o755)
    files = [logs/'agent-audit.jsonl',logs/'agent-audit.jsonl.1',logs/'agent-audit.jsonl.4']
    for file in files:
        file.write_text('{"status":"synthetic"}\n', encoding='utf8');file.chmod(0o644)
    old = [file.read_bytes() for file in files]
    try:
        configure_bounded_logging(logs)
        assert mode(logs) == 0o700
        assert all(mode(file) == 0o600 for file in files)
        assert old == [file.read_bytes() for file in files]
    finally:
        close_bounded_logging()


def test_shared_parent_directory_is_not_modified(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)
    connection = SQLiteSchemaManager(tmp_path/'agent_audit.sqlite3').connect()
    connection.close()
    assert mode(tmp_path) == 0o755


def test_restored_workspace_is_private_before_activation(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path/'app')
    workspace = WorkspaceService(paths).create(paths.default_workspace_dir, 'Restore test', seed_dir=ROOT/'data/demo')
    connection = SQLiteSchemaManager(workspace.history_database_path).connect()
    connection.execute('CREATE TABLE private_marker(value TEXT)')
    connection.execute("INSERT INTO private_marker VALUES ('restored record')")
    connection.commit();connection.close()
    archives = WorkspaceArchiveService(workspace, app_paths=paths)
    result = archives.restore(archives.backup())
    restored = paths.default_workspace_dir.parent/result.workspace.relative_directory
    assert mode(restored/'history') == 0o700
    database = restored/'history/agent_audit.sqlite3'
    assert mode(database) == 0o600
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT value FROM private_marker').fetchone()[0] == 'restored record'


def test_permission_failure_does_not_open_database(tmp_path: Path, monkeypatch) -> None:
    def deny_permissions(*args):
        raise PermissionError('synthetic permission denial')
    def unexpected_sqlite_open(*args, **kwargs):
        pytest.fail('SQLite was opened despite failing to secure permissions')
    monkeypatch.setattr(os, 'fchmod', deny_permissions)
    monkeypatch.setattr(sqlite3, 'connect', unexpected_sqlite_open)
    with pytest.raises(SQLiteSchemaError, match='unable to initialize history schema'):
        SQLiteSchemaManager(tmp_path/'agent_audit.sqlite3').connect()
