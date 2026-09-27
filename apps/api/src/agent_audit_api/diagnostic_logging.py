"""Bounded, body-free structured logging for local diagnostics."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

from .private_storage import ensure_private_directory, ensure_private_file


operation_id_var: ContextVar[str | None] = ContextVar(
    "agent_audit_operation_id", default=None
)
LOGGER_NAME = "agent_audit.runtime"
LOG_FILENAME = "agent-audit.jsonl"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "event": getattr(record, "event", "runtime_event"),
            "operationId": operation_id_var.get(),
            "component": getattr(record, "component", "api"),
            "status": getattr(record, "status", None),
            "errorType": getattr(record, "error_type", None),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class _PrivateRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        ensure_private_file(Path(self.baseFilename))
        return super()._open()


def configure_bounded_logging(
    logs_dir: Path, *, max_bytes: int = 1024 * 1024, backup_count: int = 3
) -> Path:
    if max_bytes <= 0 or backup_count < 0:
        raise ValueError("log rotation bounds are invalid")
    ensure_private_directory(logs_dir)
    path = logs_dir / LOG_FILENAME
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    for backup in logs_dir.glob(f"{LOG_FILENAME}.*"):
        if backup.name.removeprefix(f"{LOG_FILENAME}.").isdigit():
            ensure_private_file(backup)
    handler = _PrivateRotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    return path


def close_bounded_logging() -> None:
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def log_event(
    event: str,
    *,
    component: str = "api",
    status: str | None = None,
    error_type: str | None = None,
    level: Literal["info", "warning", "error"] = "info",
) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    logger.log(
        {"info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}[level],
        event,
        extra={
            "event": event,
            "component": component,
            "status": status,
            "error_type": error_type,
        },
    )


__all__ = [
    "LOG_FILENAME",
    "LOGGER_NAME",
    "configure_bounded_logging",
    "close_bounded_logging",
    "log_event",
    "operation_id_var",
]
