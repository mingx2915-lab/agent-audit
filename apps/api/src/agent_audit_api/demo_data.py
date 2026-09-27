"""Load the repository's synthetic demo data without external services."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .domain import CustomerRecord, DemoActor, KnowledgeDocument


class DemoDataError(ValueError):
    """Raised when a required synthetic demo data file is malformed."""


@dataclass(frozen=True)
class DemoData:
    actors: tuple[DemoActor, ...]
    documents: tuple[KnowledgeDocument, ...]
    customers: tuple[CustomerRecord, ...]


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoDataError(f"unable to load demo data: {path.name}") from exc


def _required_string(record: dict[str, Any], key: str, source: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DemoDataError(f"{source} requires a non-empty {key}")
    return value


def _string_tuple(record: dict[str, Any], key: str, source: str) -> tuple[str, ...]:
    value = record.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DemoDataError(f"{source} requires a string list for {key}")
    return tuple(value)


def _repo_root() -> Path:
    # data.py lives at <repo>/apps/api/src/agent_audit_api/demo_data.py.
    return Path(__file__).resolve().parents[4]


def load_demo_data(data_dir: str | Path | None = None) -> DemoData:
    """Load actors, knowledge documents, and customer records from one data root.

    The default remains the repository Demo seed for development and tests.
    Desktop production passes the Workspace ``documents`` directory explicitly.
    """

    directory = Path(data_dir) if data_dir is not None else _repo_root() / "data" / "demo"
    actors_raw = _read_json(directory / "actors.json")
    documents_raw = _read_json(directory / "knowledge_documents.json")
    customers_raw = _read_json(directory / "customers.json")

    if not isinstance(actors_raw, list):
        raise DemoDataError("actors.json must contain an array")
    if not isinstance(documents_raw, list):
        raise DemoDataError("knowledge_documents.json must contain an array")
    if not isinstance(customers_raw, list):
        raise DemoDataError("customers.json must contain an array")

    actors: list[DemoActor] = []
    for index, raw in enumerate(actors_raw):
        if not isinstance(raw, dict):
            raise DemoDataError(f"actors.json item {index} must be an object")
        actors.append(
            DemoActor(
                id=_required_string(raw, "id", "actor"),
                display_name=_required_string(raw, "displayName", "actor"),
                role=_required_string(raw, "role", "actor"),
            )
        )

    documents: list[KnowledgeDocument] = []
    for index, raw in enumerate(documents_raw):
        if not isinstance(raw, dict):
            raise DemoDataError(f"knowledge_documents.json item {index} must be an object")
        documents.append(
            KnowledgeDocument(
                id=_required_string(raw, "id", "document"),
                title=_required_string(raw, "title", "document"),
                content=_required_string(raw, "content", "document"),
                owner_id=raw.get("ownerId") if raw.get("ownerId") is not None else None,
                labels=_string_tuple(raw, "labels", "document"),
                source_id=_required_string(raw, "sourceId", "document"),
                source_type=_required_string(raw, "sourceType", "document"),
                trust_level=_required_string(raw, "trustLevel", "document"),
            )
        )

    customers: list[CustomerRecord] = []
    for index, raw in enumerate(customers_raw):
        if not isinstance(raw, dict):
            raise DemoDataError(f"customers.json item {index} must be an object")
        customers.append(
            CustomerRecord(
                id=_required_string(raw, "id", "customer"),
                name=_required_string(raw, "name", "customer"),
                owner_id=_required_string(raw, "ownerId", "customer"),
                summary=_required_string(raw, "summary", "customer"),
            )
        )

    return DemoData(tuple(actors), tuple(documents), tuple(customers))
