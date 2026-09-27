from __future__ import annotations

import asyncio
import ast
import io
import json
import logging
import re
import zipfile
from pathlib import Path

import pytest

from agent_audit_api.app_paths import resolve_app_paths
from agent_audit_api.diagnostic_logging import (
    LOGGER_NAME,
    close_bounded_logging,
    configure_bounded_logging,
    log_event,
    operation_id_var,
)
from agent_audit_api.diagnostics import DiagnosticBundleService, DiagnosticExportError
from agent_audit_api.providers.deepseek import DeepSeekProvider
from agent_audit_api.providers.ollama import OllamaProvider


OPERATION_ID = "a" * 32


def _archive(payload: bytes) -> tuple[list[str], dict[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        return names, {name: archive.read(name) for name in names}


def test_bounded_json_logging_has_fixed_fields_and_rotates(tmp_path: Path) -> None:
    path = configure_bounded_logging(tmp_path, max_bytes=512, backup_count=3)
    token = operation_id_var.set("b" * 32)
    try:
        for _ in range(20):
            log_event(
                "provider_request_failed",
                component="provider",
                status="failed",
                error_type="TimeoutError",
                level="warning",
            )
    finally:
        operation_id_var.reset(token)
        for handler in logging.getLogger(LOGGER_NAME).handlers:
            handler.flush()

    files = sorted(tmp_path.glob("agent-audit.jsonl*"))
    assert path in files
    assert len(files) <= 4
    assert all(file.stat().st_size <= 512 for file in files)
    for file in files:
        for line in file.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            assert set(payload) == {
                "timestamp",
                "level",
                "event",
                "operationId",
                "component",
                "status",
                "errorType",
            }
            assert payload["operationId"] == "b" * 32
            assert "request" not in payload and "response" not in payload


def test_default_log_rotation_contract_is_one_mib_and_three_backups(
    tmp_path: Path,
) -> None:
    configure_bounded_logging(tmp_path)
    handlers = logging.getLogger(LOGGER_NAME).handlers
    assert len(handlers) == 1
    handler = handlers[0]
    assert getattr(handler, "maxBytes") == 1024 * 1024
    assert getattr(handler, "backupCount") == 3


class _ProviderCompletions:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure

    async def create(self, **_request):
        if self.failure is not None:
            raise self.failure
        return {
            "choices": [{"message": {"content": "provider-private-response", "tool_calls": []}}]
        }


def _provider_client(*, failure: Exception | None = None):
    from types import SimpleNamespace

    return SimpleNamespace(
        chat=SimpleNamespace(completions=_ProviderCompletions(failure=failure))
    )


def _read_log(path: Path) -> list[dict[str, object]]:
    close_bounded_logging()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_provider_success_logs_started_then_completed_without_request_material(tmp_path: Path) -> None:
    path = configure_bounded_logging(tmp_path / "logs")
    operation_id = "1" * 32
    token = operation_id_var.set(operation_id)
    try:
        response = asyncio.run(
            DeepSeekProvider(client=_provider_client()).complete(
                [{"role": "user", "content": "private-prompt-body"}]
            )
        )
    finally:
        operation_id_var.reset(token)
    assert response.content == "provider-private-response"
    events = _read_log(path)
    assert [event["event"] for event in events] == [
        "provider_call_started",
        "provider_call_completed",
    ]
    assert {event["operationId"] for event in events} == {operation_id}
    assert {event["status"] for event in events} == {"started", "passed"}
    assert all(len(event) == 7 and event["component"] == "provider" for event in events)
    serialized = json.dumps(events, ensure_ascii=False)
    for forbidden in (
        "private-prompt-body",
        "provider-private-response",
        DeepSeekProvider.MODEL,
        DeepSeekProvider.BASE_URL,
    ):
        assert forbidden not in serialized


def test_provider_failure_logs_started_then_failed_without_exception_or_secret(tmp_path: Path) -> None:
    path = configure_bounded_logging(tmp_path / "logs")
    operation_id = "2" * 32
    secret = "enterprise-secret-value"
    failure_text = "timeout contacting http://private.enterprise.example/v1 with " + secret
    token = operation_id_var.set(operation_id)
    try:
        with pytest.raises(Exception, match="Ollama provider request failed"):
            asyncio.run(
                OllamaProvider(
                    client=_provider_client(failure=TimeoutError(failure_text)),
                    base_url="http://private.enterprise.example/v1",
                    model="private-enterprise-model",
                    auth_mode="bearer",
                    credential=secret,
                ).complete([{"role": "user", "content": "private-prompt-body"}])
            )
    finally:
        operation_id_var.reset(token)
    events = _read_log(path)
    assert [event["event"] for event in events] == [
        "provider_call_started",
        "provider_call_failed",
    ]
    assert {event["operationId"] for event in events} == {operation_id}
    assert events[-1]["status"] == "failed"
    assert events[-1]["errorType"] == "TimeoutError"
    assert all(len(event) == 7 and event["component"] == "provider" for event in events)
    serialized = json.dumps(events, ensure_ascii=False)
    for forbidden in (
        secret,
        failure_text,
        "private.enterprise.example",
        "private-enterprise-model",
        "private-prompt-body",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "provider_file",
    [
        "deepseek.py",
        "ollama.py",
        "openai_compatible.py",
        "anthropic.py",
        "agent_audit_adapter.py",
    ],
)
def test_all_production_provider_adapters_emit_the_fixed_operation_lifecycle(provider_file: str) -> None:
    source = (
        Path(__file__).parents[2]
        / "apps"
        / "api"
        / "src"
        / "agent_audit_api"
        / "providers"
        / provider_file
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    lifecycle_calls: set[tuple[str, str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "log_event" or not node.args:
            continue
        event_arg = node.args[0]
        if not isinstance(event_arg, ast.Constant) or not isinstance(event_arg.value, str):
            continue
        keywords = {
            keyword.arg: keyword.value
            for keyword in node.keywords
            if keyword.arg is not None
        }
        component = keywords.get("component")
        status = keywords.get("status")
        if (
            isinstance(component, ast.Constant)
            and isinstance(component.value, str)
            and isinstance(status, ast.Constant)
            and isinstance(status.value, str)
        ):
            lifecycle_calls.add((event_arg.value, component.value, status.value))
    for event, status in (
        ("provider_call_started", "started"),
        ("provider_call_completed", "passed"),
        ("provider_call_failed", "failed"),
    ):
        assert (event, "provider", status) in lifecycle_calls


def test_bundle_has_strict_relative_unique_allowlist_and_same_source_readme(
    tmp_path: Path,
) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    paths.logs_dir.mkdir(parents=True)
    (paths.logs_dir / "agent-audit.jsonl").write_text(
        '{"event":"startup","operationId":null}\n', encoding="utf-8"
    )
    service = DiagnosticBundleService(
        paths,
        runtime_supplier=lambda: {
            "platform": "win32",
            "providerKind": "ollama",
            "workspaceConfigured": False,
        },
        product_version="1.2.3",
    )
    names, members = _archive(service.build(OPERATION_ID))
    assert len(names) == len(set(names))
    assert set(names) == {
        "README.md",
        "logs/runtime-1.jsonl",
        "manifest.json",
        "runtime.json",
    }
    assert all(not name.startswith(("/", "\\")) and ".." not in name.split("/") for name in names)
    manifest = json.loads(members["manifest.json"])
    readme = members["README.md"].decode("utf-8")
    assert manifest["operationId"] == OPERATION_ID
    assert manifest["productVersion"] == "1.2.3"
    assert manifest["disclaimer"] in readme
    assert OPERATION_ID in readme
    assert "本地生成" in readme
    assert "未上传" in readme
    assert "仅供" in readme and "排障" in readme
    assert "不构成根因" in readme
    assert [item["path"] for item in manifest["files"]] == [
        "logs/runtime-1.jsonl",
        "runtime.json",
    ]
    assert all(item["path"] in members for item in manifest["files"])


def test_no_workspace_and_no_logs_export_is_honest(tmp_path: Path) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    service = DiagnosticBundleService(
        paths, workspace=None, runtime_supplier=lambda: {"platform": "linux"}, product_version="1.2.3"
    )
    preview = service.preview().model_dump(by_alias=True)
    by_id = {item["id"]: item for item in preview["included"]}
    assert by_id["logs"] == {
        "id": "logs",
        "label": "有界结构化日志",
        "available": False,
        "count": 0,
    }
    assert by_id["workspace"]["available"] is False
    names, members = _archive(service.build(OPERATION_ID))
    assert set(names) == {"README.md", "manifest.json", "runtime.json"}
    manifest = json.loads(members["manifest.json"])
    assert manifest["workspace"] is None and manifest["sidecar"] is None


@pytest.mark.parametrize(
    "secret",
    [
        "Authorization: Bearer top-secret-token",
        "x-api-key: enterprise-secret-value",
        "api_key=provider-secret-value",
        "sk-abcdefghijklmnopqrstuvwxyz012345",
    ],
)
def test_credential_shapes_fail_closed_without_echoing_secret(
    tmp_path: Path, secret: str
) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    service = DiagnosticBundleService(
        paths, runtime_supplier=lambda: {"platform": "linux", "unsafe": secret}, product_version="1.2.3"
    )
    with pytest.raises(DiagnosticExportError) as captured:
        service.build(OPERATION_ID)
    assert secret not in str(captured.value)
    assert "credential" in str(captured.value)


@pytest.mark.parametrize(
    "home",
    [r"C:\\Users\\Alice", r"\\server\\Users\\Alice", "/home/alice", "/Users/alice"],
)
def test_any_platform_user_home_path_fails_closed(tmp_path: Path, home: str) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    service = DiagnosticBundleService(
        paths, runtime_supplier=lambda: {"diagnosticPath": f"{home}/private/file.txt"}, product_version="1.2.3"
    )
    with pytest.raises(DiagnosticExportError) as captured:
        service.build(OPERATION_ID)
    assert home not in str(captured.value)


def test_prompt_document_sqlite_and_provider_settings_are_never_zip_members(
    tmp_path: Path,
) -> None:
    paths = resolve_app_paths(tmp_path / "app")
    paths.config_dir.mkdir(parents=True)
    paths.runtime_dir.mkdir(parents=True)
    paths.default_workspace_dir.mkdir(parents=True)
    (paths.config_dir / "provider-settings.json").write_text(
        '{"credential":"do-not-export"}', encoding="utf-8"
    )
    (paths.default_workspace_dir / "agent_audit.sqlite3").write_bytes(b"SQLite format 3")
    (paths.default_workspace_dir / "prompt.txt").write_text(
        "full confidential prompt", encoding="utf-8"
    )
    (paths.default_workspace_dir / "document.md").write_text(
        "complete business document", encoding="utf-8"
    )
    names, members = _archive(
        DiagnosticBundleService(paths, runtime_supplier=lambda: {"platform": "linux"}, product_version="1.2.3").build(
            OPERATION_ID
        )
    )
    combined = b"\n".join(members.values())
    assert all(
        forbidden not in names
        for forbidden in (
            "provider-settings.json",
            "agent_audit.sqlite3",
            "prompt.txt",
            "document.md",
        )
    )
    for raw in (
        b"do-not-export",
        b"SQLite format 3",
        b"full confidential prompt",
        b"complete business document",
    ):
        assert raw not in combined
