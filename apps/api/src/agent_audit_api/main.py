"""FastAPI entrypoint for the controlled AgentAudit demo target."""

from __future__ import annotations

import json
import os
import sys
import uuid
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version as package_version
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .app_paths import AppPaths, resolve_app_paths
from .execution_outcomes import BlockedCaseExecution, BlockedPlanExecution
from .attack_cases import (
    AttackCase,
    AttackCaseExecutionError,
    AttackCaseExecutor,
    AttackExecutionResult,
    load_attack_cases,
    load_target_profiles,
)
from .acceptance import (
    AcceptanceConfigurationError,
    AcceptanceRun,
    AcceptanceRunComparison,
    AcceptanceRunSummary,
    AcceptanceRunner,
    EmptyAcceptanceRunRequest,
    build_acceptance_comparison,
    render_acceptance_markdown,
)
from .acceptance_history import (
    AcceptanceRunRepository,
    AcceptanceRunRepositoryError,
    SQLiteAcceptanceRunRepository,
)
from .benchmark import (
    BenchmarkResult,
    GroundTruthCase,
    load_ground_truth_cases,
)
from .benchmark_runtime import build_benchmark_runtime
from .demo_data import DemoData, load_demo_data
from .differential import (
    DifferentialAuditResult,
    DifferentialAuditRunner,
    DifferentialTask,
    StartDifferentialAuditRequest,
    build_differential_tasks,
)
from .diagnostic_logging import (
    close_bounded_logging,
    configure_bounded_logging,
    log_event,
    operation_id_var,
)
from .diagnostics import (
    DiagnosticBundleService,
    DiagnosticExportError,
    DiagnosticPreview,
)
from .provider_diagnostics import (
    ProviderDiagnosticStage,
    provider_error_diagnostic,
)
from .document_import import (
    DocumentImportCommitRequest,
    DocumentImportError,
    DocumentImportIndexError,
    DocumentImportPreview,
    DocumentImportPreviewRequest,
    DocumentImportResult,
    DocumentImportService,
    DocumentCatalog,
    DocumentImportStorageError,
    DocumentImportWorkspaceError,
)
from .evaluation import ContractChecker, HybridJudge, TraceEvaluationRequest, TraceEvaluationResult
from .history import (
    AuditRunDetail,
    AuditRunRepository,
    AuditRunRepositoryError,
    AuditRunSummary,
    AuditRuntimeSnapshot,
    EmptyReplayRequest,
    PersistedReplay,
    SQLiteAuditRunRepository,
    TargetProfileSnapshot,
)
from .providers.base import (
    LLMProvider,
    ProviderConfigurationError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from .providers.runtime import create_runtime_provider
from .provider_setup import (
    ProviderCandidateReadinessRequest,
    ProviderConnectionSettings,
    ProviderInspectionRequest,
    OllamaDiscoveryResult,
    OllamaDiscoveryRequest,
    ProviderSettingsError,
    ProviderSettingsStore,
    ProviderSetupState,
    ProtocolInspectionResult,
    PROVIDER_CREDENTIAL_ENV,
    SaveProviderSettingsRequest,
    discover_ollama_models,
    effective_auth_mode,
    inspect_provider_endpoint,
)
from .planning import (
    AttackPlan,
    SecurityContractPreview,
    AttackPlanExecutionResult,
    AttackPlanExecutor,
    ContractAttackPlanner,
    build_security_contract_preview,
)
from .replay import (
    ReplayExecutor,
    ReplayResult,
)
from .red_team import (
    LLMAttackVariantGenerator,
    RedTeamOrchestrator,
    RedTeamScan,
    StartScanRequest,
    provider_metadata,
)
from .readiness import (
    EmptyProviderReadinessRequest,
    ProviderReadinessResult,
    ProviderReadinessRunner,
)
from .reporting import AttackChainReport, build_attack_chain_report
from .retrieval import (
    EmbeddingRetriever,
    ReloadableRetriever,
    Retriever,
    RetrieverError,
    TextEmbedder,
    TfidfRetriever,
)
from .retrieval_evaluation import (
    RetrievalEvaluationRequest,
    RetrievalEvaluationResult,
    RetrievalEvaluationRunner,
)
from .schemas import (
    Actor,
    AssistantQueryRequest,
    AssistantQueryResult,
    CamelModel,
    DesktopRuntimeStatus,
)
from .security_contract import SecurityContract, load_security_contract
from .services.assistant import (
    AssistantService,
    EmptyMessageError,
    ToolAuthorizationError,
    UnknownActorError,
)
from .target import TargetProfile
from .tools import MockCustomerExportTool, MockCustomerTool, MockMailTool
from .workspace import AuditWorkspace, WorkspaceError, WorkspaceService
from .workspace import WORKSPACE_SCHEMA_VERSION
from .sqlite_schema import SQLITE_SCHEMA_VERSION
from .workspace_archive import (
    WorkspaceArchiveService,
    WorkspaceArchiveStorageError,
    WorkspaceArchiveValidationError,
    WorkspaceArchiveWorkspaceError,
    WorkspaceBackupPreview,
    WorkspaceRestoreResult,
    WorkspaceSummary,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _product_version() -> str:
    try:
        # Source execution has a repository root four parents above this
        # module.  A PyInstaller bundle may place the module at a shallower
        # `_MEIPASS/agent_audit_api` path, so resolving that optional source
        # metadata must remain inside the existing installed-package fallback.
        repository_root = Path(__file__).resolve().parents[4]
        payload = json.loads((repository_root / "package.json").read_text(encoding="utf-8"))
    except (IndexError, OSError, UnicodeError, json.JSONDecodeError):
        try:
            return package_version("agent-audit-api")
        except PackageNotFoundError as exc:
            raise RuntimeError("AgentAudit product version is unavailable") from exc
    value = payload.get("version") if isinstance(payload, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("AgentAudit product version is invalid")
    return value


def _default_history_path(app_paths: AppPaths | None = None) -> Path:
    configured_path = os.getenv("AGENT_AUDIT_DB_PATH")
    if configured_path and configured_path.strip():
        return Path(configured_path)
    paths = app_paths if app_paths is not None else resolve_app_paths()
    return paths.data_dir / "agent_audit.sqlite3"


def _coerce_workspace(
    workspace: AuditWorkspace | str | Path | None,
) -> AuditWorkspace | None:
    if workspace is None or isinstance(workspace, AuditWorkspace):
        return workspace
    return WorkspaceService().open(workspace)


def _target_profile_snapshot(profile: TargetProfile) -> TargetProfileSnapshot:
    return TargetProfileSnapshot(
        id=profile.id,
        name=profile.name,
        enforce_resource_authorization=profile.enforce_resource_authorization,
        enforce_tool_authorization=profile.enforce_tool_authorization,
        enforce_sink_authorization=profile.enforce_sink_authorization,
    )


def _target_profile(snapshot: TargetProfileSnapshot) -> TargetProfile:
    return TargetProfile(
        id=snapshot.id,
        name=snapshot.name,
        enforce_resource_authorization=snapshot.enforce_resource_authorization,
        enforce_tool_authorization=snapshot.enforce_tool_authorization,
        enforce_sink_authorization=snapshot.enforce_sink_authorization,
    )


def _runtime_snapshot(provider: object, retriever: Retriever) -> AuditRuntimeSnapshot:
    provider_name, model = provider_metadata(provider)
    metadata = retriever.metadata
    return AuditRuntimeSnapshot(
        provider=provider_name,
        model=model,
        retriever_engine=metadata.engine_id,
        retriever_model=metadata.model_name,
        retriever_dimensions=metadata.dimensions,
        indexed_document_count=metadata.indexed_document_count,
    )


def _same_provider_connection(
    current: ProviderConnectionSettings | None,
    candidate: ProviderConnectionSettings,
) -> bool:
    """Allow process-env credential reuse only for the same saved connection."""

    if current is None:
        return False
    return (
        current.kind == candidate.kind
        and current.base_url == candidate.base_url
        and effective_auth_mode(current) == effective_auth_mode(candidate)
    )


def _provider_failure_detail(
    error: BaseException,
    *,
    stage: ProviderDiagnosticStage,
    provider: object | None = None,
    provider_kind: str | None = None,
    probe_id: str | None = None,
) -> str:
    """Return a safe user diagnostic while retaining raw errors for logging."""

    resolved_kind = provider_kind
    if resolved_kind is None and provider is not None:
        resolved_kind, _ = provider_metadata(provider)
    return provider_error_diagnostic(
        error,
        stage=stage,
        provider_kind=resolved_kind,
        probe_id=probe_id,
    )


class WorkspaceActivationPreparationRequest(CamelModel):
    relative_directory: str


class WorkspaceActivationPreparation(CamelModel):
    prepared: bool = True
    relative_directory: str
    workspace_schema_version: int
    sqlite_schema_version: int


def _require_adapter_manifest(
    settings: ProviderConnectionSettings,
    *,
    credential: str | None,
    use_environment_credential: bool = False,
) -> None:
    """Require the fixed v1 bridge manifest before candidate Readiness.

    The manifest check is intentionally scoped to the explicitly selected
    adapter kind.  Other Providers retain their F-031 candidate flow and do
    not incur an extra network request.
    """

    if settings.kind != "agent_audit_adapter":
        return
    from .providers.agent_audit_adapter import (
        AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION,
    )

    # Match ``create_runtime_provider`` exactly: process environment reuse is
    # allowed only for an already-saved, same endpoint/kind/auth connection;
    # a new candidate never inherits a credential implicitly.
    resolved_credential = credential
    if (
        resolved_credential is None
        and use_environment_credential
        and effective_auth_mode(settings) != "none"
    ):
        resolved_credential = os.getenv(PROVIDER_CREDENTIAL_ENV)
    inspection = inspect_provider_endpoint(settings, credential=resolved_credential)
    if inspection.status != "available" or inspection.protocol != "agent_audit_adapter":
        raise HTTPException(
            status_code=422,
            detail=inspection.diagnostic or "企业 AI 适配协议不可用，请确认地址提供 AgentAudit adapter v1。",
        )
    if inspection.protocol_version != AGENT_AUDIT_ADAPTER_PROTOCOL_VERSION:
        raise HTTPException(
            status_code=422,
            detail="企业 AI 适配协议版本不受支持，请确认地址提供 AgentAudit adapter v1。",
        )
    capabilities = inspection.capabilities or {}
    # ``ProtocolInspectionResult.capabilities`` is already the public
    # camelCase DTO produced by the strict bridge manifest parser.  Keep one
    # shape at this trust boundary; accepting snake_case here would make an
    # unversioned alternate manifest representation silently valid.
    required = ("text", "toolCalling", "structuredOutput", "usage")
    if not all(capabilities.get(key) is True for key in required):
        raise HTTPException(
            status_code=422,
            detail=(
                "企业 AI 适配协议缺少必需能力（capabilities），请确认已支持文本、"
                "工具调用、结构化结果和用量信息。"
            ),
        )


class _ProviderSlot:
    """Small mutable holder for the app's current Target/Attack Provider pair.

    ``create_app`` historically exposed the concrete Providers through
    ``app.state.provider`` and ``app.state.attack_provider``.  The aliases are
    retained for test doubles and existing callers; the slot is the one place
    where an explicit Provider setup confirmation replaces both roles.
    """

    def __init__(
        self,
        provider: LLMProvider,
        attack_provider: LLMProvider,
    ) -> None:
        self.provider = provider
        self.attack_provider = attack_provider

    def replace(self, provider: LLMProvider) -> None:
        self.provider = provider
        self.attack_provider = provider


def create_app(
    provider: LLMProvider | None = None,
    contract: SecurityContract | None = None,
    attack_provider: LLMProvider | None = None,
    retriever: Retriever | None = None,
    embedder: TextEmbedder | None = None,
    history_repository: AuditRunRepository | None = None,
    acceptance_repository: AcceptanceRunRepository | None = None,
    workspace: AuditWorkspace | str | Path | None = None,
    data_dir: str | Path | None = None,
    history_path: str | Path | None = None,
    app_paths: AppPaths | None = None,
) -> FastAPI:
    """Create the API app with shared dependencies and optional test doubles.

    ``workspace`` is the production Desktop assembly boundary.  When omitted,
    the repository Demo seed remains available for development and tests.
    """

    active_workspace = _coerce_workspace(workspace)
    if active_workspace is not None and data_dir is not None:
        raise ValueError("workspace and data_dir cannot both be supplied")
    resolved_app_paths = app_paths if app_paths is not None else resolve_app_paths()
    provider_settings_store = ProviderSettingsStore(resolved_app_paths.config_dir)
    # Explicitly injected Providers are test/development seams and must remain
    # independent from a machine's persisted Desktop setup.  Production and
    # Desktop construction read the confirmed settings without creating files.
    confirmed_settings = (
        provider_settings_store.load() if provider is None else None
    )
    documents_data_dir = (
        active_workspace.documents_path
        if active_workspace is not None
        else data_dir
    )
    cases_data_dir = (
        active_workspace.cases_path
        if active_workspace is not None
        else data_dir
    )
    contract_data_dir = (
        active_workspace.contract_path
        if active_workspace is not None
        else data_dir
    )

    demo_data = (
        load_demo_data(documents_data_dir)
        if documents_data_dir is not None
        else load_demo_data()
    )
    if retriever is not None and embedder is not None:
        raise ValueError("retriever and embedder cannot both be supplied")
    initial_retriever = (
        retriever
        if retriever is not None
        else EmbeddingRetriever(demo_data.documents, embedder=embedder)
    )
    if retriever is None:
        retriever_factory = lambda documents: EmbeddingRetriever(
            documents,
            embedder=embedder,
        )
    elif isinstance(retriever, TfidfRetriever):
        retriever_factory = lambda documents: TfidfRetriever(documents)
    elif isinstance(retriever, EmbeddingRetriever):
        retriever_factory = retriever.with_documents
    else:
        retriever_factory = None
    # Production Workspace imports need a stable slot because existing route
    # closures retain their Retriever reference.  Keep the historic concrete
    # injection path unchanged for repository-only development/tests.
    shared_retriever = (
        ReloadableRetriever(initial_retriever, factory=retriever_factory)
        if active_workspace is not None
        else initial_retriever
    )
    tfidf_retriever = TfidfRetriever(demo_data.documents)
    customer_tool = MockCustomerTool(demo_data.customers)
    mail_tool = MockMailTool()
    export_tool = MockCustomerExportTool(demo_data.customers)
    active_contract = (
        contract
        if contract is not None
        else (
            load_security_contract(contract_data_dir)
            if contract_data_dir is not None
            else load_security_contract()
        )
    )
    attack_cases = (
        load_attack_cases(cases_data_dir)
        if cases_data_dir is not None
        else load_attack_cases()
    )
    target_profiles = (
        load_target_profiles(cases_data_dir)
        if cases_data_dir is not None
        else load_target_profiles()
    )
    ground_truth_cases = (
        load_ground_truth_cases(cases_data_dir)
        if cases_data_dir is not None
        else load_ground_truth_cases()
    )
    secure_profiles = [profile for profile in target_profiles if profile.id == "secure"]
    if len(secure_profiles) != 1:
        raise ValueError("F-007 requires one secure target profile")
    secure_profile = secure_profiles[0]
    @asynccontextmanager
    async def lifespan(_application: FastAPI):  # type: ignore[no-untyped-def]
        configure_bounded_logging(resolved_app_paths.logs_dir)
        try:
            yield
        finally:
            close_bounded_logging()

    application = FastAPI(
        title="知盾 AgentAudit API",
        version=_product_version(),
        lifespan=lifespan,
    )

    @application.exception_handler(RequestValidationError)
    async def redact_provider_validation_inputs(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Keep Provider validation errors useful without echoing credentials."""

        provider_paths = {
            "/api/provider-inspections",
            "/api/provider-candidates/readiness",
            "/api/provider-setup",
        }
        errors: list[dict[str, object]] = []
        for raw_error in exc.errors():
            error = dict(raw_error)
            if request.url.path in provider_paths:
                # A model-level validation error may locate at ``body`` or
                # ``settings`` while its input still contains a credential.
                # Redact every Provider request input at this boundary; the
                # stable location/message remains available for correction.
                error["input"] = "[已隐藏]"
            errors.append(error)
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(errors)},
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=(
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ),
        allow_origin_regex=r"^https?://(?:127\.0\.0\.1|localhost)(?::\d+)?$",
        allow_methods=("GET", "POST", "PUT", "OPTIONS"),
        allow_headers=("Accept", "Content-Type"),
        allow_credentials=False,
    )
    application.state.workspace = active_workspace
    application.state.app_paths = resolved_app_paths
    application.state.provider_settings_store = provider_settings_store
    application.state.provider_settings = confirmed_settings
    application.state.demo_data = demo_data
    application.state.retriever = shared_retriever
    application.state.tfidf_retriever = tfidf_retriever
    application.state.customer_tool = customer_tool
    application.state.mail_tool = mail_tool
    application.state.export_tool = export_tool
    # Provider construction is local and side-effect free; clients and API keys
    # remain lazy until a request actually needs model completion.
    configured_provider = (
        provider
        if provider is not None
        else (
            create_runtime_provider(
                settings=confirmed_settings,
                use_environment_credential=True,
            )
            if confirmed_settings is not None
            else create_runtime_provider()
        )
    )
    initial_attack_provider = (
        attack_provider if attack_provider is not None else configured_provider
    )
    provider_slot = _ProviderSlot(configured_provider, initial_attack_provider)
    application.state.provider_slot = provider_slot
    application.state.provider = provider_slot.provider
    application.state.attack_provider = provider_slot.attack_provider
    application.state.provider_credential_configured = bool(
        getattr(configured_provider, "credential_configured", False)
    )
    application.state.security_contract = active_contract
    application.state.attack_cases = attack_cases
    application.state.target_profiles = target_profiles
    application.state.secure_target_profile = secure_profile
    application.state.ground_truth_cases = ground_truth_cases
    history_store = (
        history_repository
        if history_repository is not None
        else SQLiteAuditRunRepository(
            Path(history_path)
            if history_path is not None
            else (
                active_workspace.history_db_path
                if active_workspace is not None
                else _default_history_path(resolved_app_paths)
            )
        )
    )
    application.state.history_repository = history_store
    configured_acceptance_repository = acceptance_repository
    if configured_acceptance_repository is None:
        history_path = getattr(
            history_store,
            "path",
            _default_history_path(resolved_app_paths),
        )
        configured_acceptance_repository = SQLiteAcceptanceRunRepository(history_path)
    application.state.acceptance_repository = configured_acceptance_repository

    def diagnostic_runtime() -> dict[str, Any]:
        settings = application.state.provider_settings
        provider_kind = getattr(settings, "kind", None) if settings is not None else None
        if hasattr(provider_kind, "value"):
            provider_kind = provider_kind.value
        return {
            "platform": sys.platform,
            "python": ".".join(str(part) for part in sys.version_info[:3]),
            "workspaceConfigured": active_workspace is not None,
            "providerKind": provider_kind,
            "retriever": str(shared_retriever.metadata.engine_id),
        }

    diagnostics = DiagnosticBundleService(
        resolved_app_paths,
        workspace=active_workspace,
        runtime_supplier=diagnostic_runtime,
        product_version=application.version,
    )
    application.state.diagnostics = diagnostics

    @application.middleware("http")
    async def operation_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        operation_id = uuid.uuid4().hex
        token = operation_id_var.set(operation_id)
        log_event("http_request_started", status="started")
        try:
            response = await call_next(request)
        except Exception as exc:
            log_event(
                "http_request_failed",
                status="failed",
                error_type=type(exc).__name__,
                level="error",
            )
            raise
        else:
            response.headers["X-AgentAudit-Operation-Id"] = operation_id
            log_event(
                "http_request_completed",
                status="passed" if response.status_code < 500 else "failed",
                error_type=(None if response.status_code < 500 else "HttpServerError"),
            )
            return response
        finally:
            operation_id_var.reset(token)

    @application.get(
        "/api/diagnostics/preview",
        response_model=DiagnosticPreview,
        response_model_by_alias=True,
    )
    def preview_diagnostics(request: Request) -> DiagnosticPreview:
        try:
            return request.app.state.diagnostics.preview()
        except DiagnosticExportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/diagnostics/export")
    def export_diagnostics(request: Request) -> Response:
        operation_id = operation_id_var.get()
        if operation_id is None:
            raise HTTPException(status_code=500, detail="operation ID is unavailable")
        try:
            payload = request.app.state.diagnostics.build(operation_id)
        except DiagnosticExportError as exc:
            log_event(
                "diagnostic_export_rejected",
                component="diagnostics",
                status="failed",
                error_type=type(exc).__name__,
                level="warning",
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        filename = request.app.state.diagnostics.preview().suggested_filename
        return Response(
            content=payload,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @application.get(
        "/api/runtime",
        response_model=AuditRuntimeSnapshot,
        response_model_by_alias=True,
    )
    def get_runtime(request: Request) -> AuditRuntimeSnapshot:
        return _runtime_snapshot(request.app.state.attack_provider, shared_retriever)

    @application.get(
        "/api/health",
        response_model=DesktopRuntimeStatus,
        response_model_by_alias=True,
    )
    async def get_health(request: Request) -> DesktopRuntimeStatus:
        """Return sidecar readiness without invoking a model or retriever."""

        return DesktopRuntimeStatus(
            status="ready", port=getattr(request.app.state, "sidecar_port", None)
        )

    def build_workspace_archive_service(request: Request) -> WorkspaceArchiveService:
        return WorkspaceArchiveService(
            workspace=request.app.state.workspace,
            app_paths=request.app.state.app_paths,
        )

    def read_workspace_archive_content_type(request: Request) -> None:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/zip":
            raise HTTPException(
                status_code=422,
                detail="Workspace backup requests must use Content-Type application/zip",
            )

    @application.get(
        "/api/workspace",
        response_model=WorkspaceSummary,
        response_model_by_alias=True,
    )
    async def get_workspace_summary(request: Request) -> WorkspaceSummary:
        try:
            return build_workspace_archive_service(request).summary()
        except WorkspaceArchiveWorkspaceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkspaceArchiveStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @application.get("/api/workspace/backups/current")
    async def download_current_workspace_backup(request: Request) -> Response:
        try:
            payload = build_workspace_archive_service(request).backup()
        except WorkspaceArchiveWorkspaceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkspaceArchiveStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return Response(
            content=payload,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="agent-audit-workspace.zip"'
            },
        )

    @application.post(
        "/api/workspace/backups/previews",
        response_model=WorkspaceBackupPreview,
        response_model_by_alias=True,
    )
    async def preview_workspace_backup(request: Request) -> WorkspaceBackupPreview:
        read_workspace_archive_content_type(request)
        try:
            return build_workspace_archive_service(request).preview(await request.body())
        except WorkspaceArchiveWorkspaceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkspaceArchiveValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except WorkspaceArchiveStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @application.post(
        "/api/workspace/restores",
        response_model=WorkspaceRestoreResult,
        response_model_by_alias=True,
    )
    async def restore_workspace_backup(request: Request) -> WorkspaceRestoreResult:
        read_workspace_archive_content_type(request)
        try:
            return build_workspace_archive_service(request).restore(await request.body())
        except WorkspaceArchiveWorkspaceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except WorkspaceArchiveValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except WorkspaceArchiveStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @application.post(
        "/api/workspace/activation-preparations",
        response_model=WorkspaceActivationPreparation,
        response_model_by_alias=True,
    )
    def prepare_workspace_activation(
        request: Request, payload: WorkspaceActivationPreparationRequest
    ) -> WorkspaceActivationPreparation:
        relative = payload.relative_directory.strip()
        if (
            not relative
            or Path(relative).name != relative
            or relative in {".", ".."}
            or "/" in relative
            or "\\" in relative
        ):
            raise HTTPException(
                status_code=422,
                detail="relativeDirectory must name one direct Workspace child",
            )
        root = request.app.state.app_paths.default_workspace_dir.parent / relative
        try:
            workspace = WorkspaceService(
                app_paths=request.app.state.app_paths
            ).open(root)
        except WorkspaceError as exc:
            detail = (
                "Workspace schema is newer than this application"
                if "newer" in str(exc)
                else "Workspace cannot be prepared for activation"
            )
            raise HTTPException(
                status_code=422,
                detail=detail,
            ) from exc
        database_version = WorkspaceService._database_version(
            workspace.history_database_path
        )
        return WorkspaceActivationPreparation(
            relative_directory=relative,
            workspace_schema_version=workspace.manifest.schema_version,
            sqlite_schema_version=database_version,
        )

    @application.get("/api/demo/actors", response_model=list[Actor], response_model_by_alias=True)
    async def list_demo_actors() -> list[Actor]:
        return [
            Actor(id=actor.id, display_name=actor.display_name, role=actor.role)  # type: ignore[arg-type]
            for actor in demo_data.actors
        ]

    def build_document_import_service(request: Request) -> DocumentImportService:
        current_data: DemoData = request.app.state.demo_data
        return DocumentImportService(
            workspace=request.app.state.workspace,
            actors=current_data.actors,
            documents=current_data.documents,
            contract=request.app.state.security_contract,
            retriever=request.app.state.retriever,
            customers=current_data.customers,
            customer_tool=request.app.state.customer_tool,
            mail_tool=request.app.state.mail_tool,
            export_tool=request.app.state.export_tool,
        )

    @application.get(
        "/api/workspace/documents",
        response_model=DocumentCatalog,
        response_model_by_alias=True,
    )
    async def get_workspace_documents(request: Request) -> DocumentCatalog:
        """Return safe document summaries and current index metadata."""

        return build_document_import_service(request).catalog()

    @application.post(
        "/api/document-imports/previews",
        response_model=DocumentImportPreview,
        response_model_by_alias=True,
    )
    async def preview_document_import(
        payload: DocumentImportPreviewRequest,
        request: Request,
    ) -> DocumentImportPreview:
        """Calculate import statuses and Contract authorization without writes."""

        try:
            return build_document_import_service(request).preview(payload)
        except DocumentImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post(
        "/api/document-imports",
        response_model=DocumentImportResult,
        response_model_by_alias=True,
    )
    async def commit_document_import(
        payload: DocumentImportCommitRequest,
        request: Request,
    ) -> DocumentImportResult:
        """Append confirmed documents to the Workspace and hot-swap its index."""

        nonlocal demo_data, tfidf_retriever, customer_tool, export_tool
        importer = build_document_import_service(request)
        try:
            result = importer.commit(payload)
        except DocumentImportWorkspaceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DocumentImportIndexError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except DocumentImportStorageError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except DocumentImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        # Keep every existing route closure on the newly committed catalog.
        # ``importer.documents`` is published only after atomic file replacement
        # and Retriever swap, so this assignment cannot expose a half-import.
        demo_data = DemoData(
            actors=demo_data.actors,
            documents=importer.documents,
            customers=demo_data.customers,
        )
        tfidf_retriever = TfidfRetriever(demo_data.documents)
        customer_tool = MockCustomerTool(demo_data.customers)
        export_tool = MockCustomerExportTool(demo_data.customers)
        request.app.state.demo_data = demo_data
        request.app.state.tfidf_retriever = tfidf_retriever
        request.app.state.customer_tool = customer_tool
        request.app.state.export_tool = export_tool
        return result

    @application.get(
        "/api/security-contract",
        response_model=SecurityContract,
        response_model_by_alias=True,
    )
    async def get_security_contract(request: Request) -> SecurityContract:
        return request.app.state.security_contract

    @application.put(
        "/api/security-contract",
        response_model=SecurityContract,
        response_model_by_alias=True,
    )
    async def update_security_contract(
        payload: SecurityContract,
        request: Request,
    ) -> SecurityContract:
        request.app.state.security_contract = payload
        return payload

    @application.post(
        "/api/security-contract/previews",
        response_model=SecurityContractPreview,
        response_model_by_alias=True,
    )
    async def preview_security_contract(
        payload: SecurityContract,
        request: Request,
    ) -> SecurityContractPreview:
        """Preview Contract and derived Plan changes without mutating app state."""

        active_contract = request.app.state.security_contract
        return build_security_contract_preview(
            active_contract=active_contract,
            candidate_contract=payload,
            current_plans=build_attack_plans(active_contract),
            candidate_plans=build_attack_plans(payload),
        )

    @application.get(
        "/api/attack-cases",
        response_model=list[AttackCase],
        response_model_by_alias=True,
    )
    async def list_attack_cases(request: Request) -> list[AttackCase]:
        return list(request.app.state.attack_cases)

    @application.post(
        "/api/attack-cases/{case_id}/execute",
        response_model=AttackExecutionResult | BlockedCaseExecution,
        response_model_by_alias=True,
    )
    async def execute_attack_case(
        case_id: str,
        request: Request,
    ) -> AttackExecutionResult | BlockedCaseExecution:
        cases_by_id = {case.id: case for case in request.app.state.attack_cases}
        case = cases_by_id.get(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="unknown attack case")

        active_provider = request.app.state.provider
        executor = AttackCaseExecutor(
            provider=active_provider,
            actors=demo_data.actors,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=request.app.state.security_contract,
            profiles=request.app.state.target_profiles,
        )
        try:
            return await executor.execute(case)
        except AttackCaseExecutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except UnknownActorError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EmptyMessageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolAuthorizationError as exc:
            return BlockedCaseExecution(
                case=case,
                blocked_reason=str(exc),
                trace_events=list(exc.trace_events),
                evaluation=await HybridJudge(None).evaluate(
                    contract=request.app.state.security_contract,
                    trace_events=exc.trace_events,
                    include_semantic_review=False,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def build_attack_plans(current_contract: SecurityContract) -> tuple[AttackPlan, ...]:
        return ContractAttackPlanner(
            contract=current_contract,
            actors=demo_data.actors,
            documents=demo_data.documents,
            customers=demo_data.customers,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
        ).plan()

    def build_acceptance_runner(request: Request) -> AcceptanceRunner:
        """Build one runner from app-owned dependencies and current snapshots."""

        return AcceptanceRunner(
            provider=request.app.state.provider,
            attack_provider=request.app.state.attack_provider,
            retriever=request.app.state.retriever,
            tfidf_retriever=request.app.state.tfidf_retriever,
            contract=request.app.state.security_contract,
            profiles=request.app.state.target_profiles,
            demo_data=demo_data,
            customer_tool=request.app.state.customer_tool,
            mail_tool=request.app.state.mail_tool,
            export_tool=request.app.state.export_tool,
            cases=request.app.state.ground_truth_cases,
        )

    @application.post(
        "/api/acceptance-runs",
        response_model=AcceptanceRun,
        response_model_by_alias=True,
    )
    async def create_acceptance_run(
        request: Request,
        _payload: EmptyAcceptanceRunRequest | None = Body(default=None),
    ) -> AcceptanceRun:
        """Execute and append one complete repository-owned Acceptance Run."""

        try:
            run = await build_acceptance_runner(request).run()
            request.app.state.acceptance_repository.save(run)
            return run
        except AcceptanceRunRepositoryError as exc:
            raise HTTPException(
                status_code=500,
                detail="unable to persist acceptance history",
            ) from exc
        except AcceptanceConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AttackCaseExecutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except UnknownActorError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EmptyMessageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get(
        "/api/acceptance-runs",
        response_model=list[AcceptanceRunSummary],
        response_model_by_alias=True,
    )
    def list_acceptance_runs(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[AcceptanceRunSummary]:
        try:
            return request.app.state.acceptance_repository.list(limit)
        except AcceptanceRunRepositoryError as exc:
            raise HTTPException(
                status_code=500,
                detail="unable to list acceptance history",
            ) from exc

    @application.get(
        "/api/acceptance-runs/{run_id}",
        response_model=AcceptanceRun,
        response_model_by_alias=True,
    )
    def get_acceptance_run(run_id: str, request: Request) -> AcceptanceRun:
        try:
            run = request.app.state.acceptance_repository.get(run_id)
        except AcceptanceRunRepositoryError as exc:
            raise HTTPException(
                status_code=500,
                detail="unable to read acceptance history",
            ) from exc
        if run is None:
            raise HTTPException(status_code=404, detail="unknown acceptance run")
        return run

    @application.get(
        "/api/acceptance-runs/{run_id}/comparison",
        response_model=AcceptanceRunComparison,
        response_model_by_alias=True,
    )
    def compare_acceptance_run(
        run_id: str,
        request: Request,
    ) -> AcceptanceRunComparison:
        repository = request.app.state.acceptance_repository
        try:
            current = repository.get(run_id)
            if current is None:
                raise HTTPException(status_code=404, detail="unknown acceptance run")
            previous = repository.previous(run_id)
            return build_acceptance_comparison(current, previous)
        except HTTPException:
            raise
        except AcceptanceRunRepositoryError as exc:
            raise HTTPException(
                status_code=500,
                detail="unable to compare acceptance history",
            ) from exc

    @application.get(
        "/api/acceptance-runs/{run_id}/evidence.json",
    )
    def export_acceptance_json(run_id: str, request: Request) -> Response:
        try:
            run = request.app.state.acceptance_repository.get(run_id)
        except AcceptanceRunRepositoryError as exc:
            raise HTTPException(
                status_code=500,
                detail="unable to read acceptance history",
            ) from exc
        if run is None:
            raise HTTPException(status_code=404, detail="unknown acceptance run")
        payload = json.dumps(
            run.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        return Response(
            content=payload + "\n",
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="acceptance-run-{run.id}.json"'
                )
            },
        )

    @application.get(
        "/api/acceptance-runs/{run_id}/evidence.md",
    )
    def export_acceptance_markdown(run_id: str, request: Request) -> Response:
        try:
            run = request.app.state.acceptance_repository.get(run_id)
        except AcceptanceRunRepositoryError as exc:
            raise HTTPException(
                status_code=500,
                detail="unable to read acceptance history",
            ) from exc
        if run is None:
            raise HTTPException(status_code=404, detail="unknown acceptance run")
        return Response(
            content=render_acceptance_markdown(run),
            media_type="text/markdown",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="acceptance-run-{run.id}.md"'
                )
            },
        )

    @application.get(
        "/api/provider-setup",
        response_model=ProviderSetupState,
        response_model_by_alias=True,
    )
    async def get_provider_setup(request: Request) -> ProviderSetupState:
        """Read confirmed non-secret setup and current runtime metadata only."""

        return ProviderSetupState(
            configured=request.app.state.provider_settings is not None,
            settings=request.app.state.provider_settings,
            credential_configured=bool(
                getattr(request.app.state, "provider_credential_configured", False)
            ),
            runtime_snapshot=_runtime_snapshot(
                request.app.state.provider,
                shared_retriever,
            ),
        )

    @application.post(
        "/api/provider-discoveries/ollama",
        response_model=OllamaDiscoveryResult,
        response_model_by_alias=True,
    )
    async def discover_local_ollama(
        _payload: OllamaDiscoveryRequest,
    ) -> OllamaDiscoveryResult:
        """Inspect only the fixed loopback Ollama tags endpoint."""

        return discover_ollama_models()

    @application.post(
        "/api/provider-inspections",
        response_model=ProtocolInspectionResult,
        response_model_by_alias=True,
    )
    async def inspect_provider_candidate(
        payload: ProviderInspectionRequest,
    ) -> ProtocolInspectionResult:
        """Inspect one user-supplied origin and no other endpoint/origin."""

        try:
            return inspect_provider_endpoint(
                payload,
                credential=payload.credential,
            )
        except ValueError as exc:
            # Do not surface transport/provider response bodies (which could
            # contain credentials); only deterministic input diagnostics are
            # returned here.
            raise HTTPException(
                status_code=422,
                detail=(
                    "AI 服务地址格式无效，请填写 http 或 https 地址，"
                    "不要包含账号、密码、查询参数或片段。"
                ),
            ) from exc

    @application.post(
        "/api/provider-candidates/readiness",
        response_model=ProviderReadinessResult,
        response_model_by_alias=True,
    )
    async def run_provider_candidate_readiness(
        payload: ProviderCandidateReadinessRequest,
        request: Request,
    ) -> ProviderReadinessResult:
        """Probe one explicit candidate without mutating app state or storage."""

        reuse_environment_credential = _same_provider_connection(
            request.app.state.provider_settings,
            payload.settings,
        )
        _require_adapter_manifest(
            payload.settings,
            credential=payload.credential,
            use_environment_credential=reuse_environment_credential,
        )
        candidate = create_runtime_provider(
            settings=payload.settings,
            credential=payload.credential,
            use_environment_credential=reuse_environment_credential,
        )
        runner = ProviderReadinessRunner(
            target_provider=candidate,
            attack_provider=candidate,
            plans=build_attack_plans(request.app.state.security_contract),
        )
        try:
            return await runner.run()
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="readiness",
                    provider=candidate,
                ),
            ) from exc
        except (ProviderResponseError, ProviderUnavailableError) as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="readiness",
                    provider=candidate,
                ),
            ) from exc

    @application.put(
        "/api/provider-setup",
        response_model=ProviderSetupState,
        response_model_by_alias=True,
    )
    async def save_provider_setup(
        payload: SaveProviderSettingsRequest,
        request: Request,
    ) -> ProviderSetupState:
        """Persist confirmed public settings and replace both runtime roles."""

        reuse_environment_credential = _same_provider_connection(
            request.app.state.provider_settings,
            payload.settings,
        )
        _require_adapter_manifest(
            payload.settings,
            credential=payload.credential,
            use_environment_credential=reuse_environment_credential,
        )
        candidate = create_runtime_provider(
            settings=payload.settings,
            credential=payload.credential,
            use_environment_credential=reuse_environment_credential,
        )
        auth_mode = effective_auth_mode(payload.settings)
        if auth_mode != "none" and not getattr(
            candidate,
            "credential_configured",
            False,
        ):
            # The API has no keyring by design. Desktop must provide the
            # transient value now, or the active same-connection process env
            # value must already be available from the Desktop boundary.
            detail = (
                "认证失败：此连接需要 x-api-key 凭据（credential），请重新输入凭据。"
                if auth_mode == "x_api_key"
                else "认证失败：此连接需要 Bearer 凭据（credential），请重新输入凭据。"
            )
            raise HTTPException(
                status_code=422,
                detail=detail,
            )

        try:
            request.app.state.provider_settings_store.save(payload.settings)
        except ProviderSettingsError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        provider_slot: _ProviderSlot = request.app.state.provider_slot
        provider_slot.replace(candidate)
        # Preserve the long-standing concrete aliases used throughout the API
        # and by injected test doubles.
        request.app.state.provider = provider_slot.provider
        request.app.state.attack_provider = provider_slot.attack_provider
        request.app.state.provider_settings = payload.settings
        request.app.state.provider_credential_configured = bool(
            getattr(candidate, "credential_configured", False)
        )
        return ProviderSetupState(
            configured=True,
            settings=payload.settings,
            credential_configured=request.app.state.provider_credential_configured,
            runtime_snapshot=_runtime_snapshot(
                request.app.state.provider,
                shared_retriever,
            ),
        )

    @application.post(
        "/api/provider-readiness",
        response_model=ProviderReadinessResult,
        response_model_by_alias=True,
    )
    async def run_provider_readiness(
        _payload: EmptyProviderReadinessRequest,
        request: Request,
    ) -> ProviderReadinessResult:
        """Run explicit Target/Attack Provider probes without persistence."""

        runner = ProviderReadinessRunner(
            target_provider=request.app.state.provider,
            attack_provider=request.app.state.attack_provider,
            plans=build_attack_plans(request.app.state.security_contract),
        )
        return await runner.run()

    @application.get(
        "/api/attack-plans",
        response_model=list[AttackPlan],
        response_model_by_alias=True,
    )
    async def list_attack_plans(request: Request) -> list[AttackPlan]:
        return list(build_attack_plans(request.app.state.security_contract))

    @application.post(
        "/api/scans",
        response_model=RedTeamScan,
        response_model_by_alias=True,
    )
    async def create_scan(
        payload: StartScanRequest,
        request: Request,
    ) -> RedTeamScan:
        active_contract = request.app.state.security_contract
        plans_by_id = {
            plan.id: plan
            for plan in build_attack_plans(active_contract)
        }
        plan = plans_by_id.get(payload.plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="unknown attack plan")

        profiles_by_id = {profile.id: profile for profile in request.app.state.target_profiles}
        target_profile = profiles_by_id.get(plan.target_profile_id)
        if target_profile is None:
            raise HTTPException(status_code=500, detail="target profile is unavailable")

        active_provider = request.app.state.provider
        attack_provider = request.app.state.attack_provider
        case_executor = AttackCaseExecutor(
            provider=active_provider,
            actors=demo_data.actors,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=active_contract,
            profiles=request.app.state.target_profiles,
        )
        orchestrator = RedTeamOrchestrator(
            plan_executor=AttackPlanExecutor(case_executor),
            variant_generator=LLMAttackVariantGenerator(attack_provider),
            contract=active_contract,
            provider=attack_provider,
        )
        try:
            scan = await orchestrator.run(plan, max_rounds=payload.max_rounds)
            detail = AuditRunDetail(
                scan=scan,
                plan_snapshot=plan,
                contract_snapshot=active_contract,
                target_profile_snapshot=_target_profile_snapshot(target_profile),
                runtime_snapshot=_runtime_snapshot(attack_provider, shared_retriever),
                replays=[],
            )
            request.app.state.history_repository.save(detail)
            return scan
        except AuditRunRepositoryError as exc:
            raise HTTPException(status_code=500, detail="unable to persist audit scan") from exc
        except AttackCaseExecutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except UnknownActorError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EmptyMessageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get(
        "/api/scans",
        response_model=list[AuditRunSummary],
        response_model_by_alias=True,
    )
    def list_scans(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> list[AuditRunSummary]:
        try:
            return request.app.state.history_repository.list(limit)
        except AuditRunRepositoryError as exc:
            raise HTTPException(status_code=500, detail="unable to list audit history") from exc

    @application.get(
        "/api/scans/{scan_id}",
        response_model=AuditRunDetail,
        response_model_by_alias=True,
    )
    def get_scan(scan_id: str, request: Request) -> AuditRunDetail:
        try:
            detail = request.app.state.history_repository.get(scan_id)
        except AuditRunRepositoryError as exc:
            raise HTTPException(status_code=500, detail="unable to read audit history") from exc
        if detail is None:
            raise HTTPException(status_code=404, detail="unknown scan")
        return detail

    @application.post(
        "/api/scans/{scan_id}/replays",
        response_model=PersistedReplay,
        response_model_by_alias=True,
    )
    async def replay_persisted_scan(
        scan_id: str,
        _payload: EmptyReplayRequest,
        request: Request,
    ) -> PersistedReplay:
        try:
            detail = request.app.state.history_repository.get(scan_id)
        except AuditRunRepositoryError as exc:
            raise HTTPException(status_code=500, detail="unable to read audit history") from exc
        if detail is None:
            raise HTTPException(status_code=404, detail="unknown scan")

        saved_target_profile = _target_profile(detail.target_profile_snapshot)
        replay_profiles = {
            profile.id: profile for profile in request.app.state.target_profiles
        }
        replay_profiles[saved_target_profile.id] = saved_target_profile
        replay_profiles[request.app.state.secure_target_profile.id] = (
            request.app.state.secure_target_profile
        )
        case_executor = AttackCaseExecutor(
            provider=request.app.state.provider,
            actors=demo_data.actors,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=detail.contract_snapshot,
            profiles=tuple(replay_profiles.values()),
        )
        try:
            replay = await ReplayExecutor(
                plan_executor=AttackPlanExecutor(case_executor),
                contract=detail.contract_snapshot,
            ).replay(detail.plan_snapshot)
            persisted = PersistedReplay(
                id=f"persisted_replay_{uuid.uuid4().hex}",
                created_at=_utc_now(),
                replay=replay,
            )
            request.app.state.history_repository.append_replay(scan_id, persisted)
            return persisted
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown scan") from exc
        except AuditRunRepositoryError as exc:
            raise HTTPException(status_code=500, detail="unable to append audit replay") from exc
        except UnknownActorError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EmptyMessageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.get(
        "/api/ground-truth-cases",
        response_model=list[GroundTruthCase],
        response_model_by_alias=True,
    )
    async def list_ground_truth_cases(request: Request) -> list[GroundTruthCase]:
        return list(request.app.state.ground_truth_cases)

    @application.get(
        "/api/differential-tasks",
        response_model=list[DifferentialTask],
        response_model_by_alias=True,
    )
    async def list_differential_tasks() -> list[DifferentialTask]:
        return list(
            build_differential_tasks(
                actors=demo_data.actors,
                documents=demo_data.documents,
                customers=demo_data.customers,
                customer_tool=customer_tool,
            )
        )

    @application.post(
        "/api/differential-audits",
        response_model=DifferentialAuditResult,
        response_model_by_alias=True,
    )
    async def run_differential_audit(
        payload: StartDifferentialAuditRequest,
        request: Request,
    ) -> DifferentialAuditResult:
        tasks_by_id = {
            task.id: task
            for task in build_differential_tasks(
                actors=demo_data.actors,
                documents=demo_data.documents,
                customers=demo_data.customers,
                customer_tool=customer_tool,
            )
        }
        task = tasks_by_id.get(payload.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="unknown differential task")
        if payload.target_profile_id not in task.supported_target_profile_ids:
            raise HTTPException(
                status_code=422,
                detail="target profile is not supported by differential task",
            )
        runner = DifferentialAuditRunner(
            provider=request.app.state.provider,
            actors=demo_data.actors,
            documents=demo_data.documents,
            customers=demo_data.customers,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=request.app.state.security_contract,
            profiles=request.app.state.target_profiles,
        )
        try:
            return await runner.run(task, payload.target_profile_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.post(
        "/api/retrieval-evaluations",
        response_model=RetrievalEvaluationResult,
        response_model_by_alias=True,
    )
    async def run_retrieval_evaluation(
        request: Request,
        _payload: RetrievalEvaluationRequest | None = None,
    ) -> RetrievalEvaluationResult:
        """Compare the fixed offline queries without invoking an LLM."""

        runner = RetrievalEvaluationRunner(
            tfidf_retriever=request.app.state.tfidf_retriever,
            embedding_retriever=request.app.state.retriever,
        )
        try:
            return runner.run()
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post(
        "/api/attack-plans/{plan_id}/execute",
        response_model=AttackPlanExecutionResult | BlockedPlanExecution,
        response_model_by_alias=True,
    )
    async def execute_attack_plan(
        plan_id: str,
        request: Request,
    ) -> AttackPlanExecutionResult | BlockedPlanExecution:
        plans_by_id = {
            plan.id: plan
            for plan in build_attack_plans(request.app.state.security_contract)
        }
        plan = plans_by_id.get(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="unknown attack plan")

        active_provider = request.app.state.provider
        case_executor = AttackCaseExecutor(
            provider=active_provider,
            actors=demo_data.actors,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=request.app.state.security_contract,
            profiles=request.app.state.target_profiles,
        )
        try:
            return await AttackPlanExecutor(case_executor).execute(plan)
        except AttackCaseExecutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except UnknownActorError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EmptyMessageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolAuthorizationError as exc:
            return BlockedPlanExecution(
                plan=plan,
                blocked_reason=str(exc),
                trace_events=list(exc.trace_events),
                evaluation=await HybridJudge(None).evaluate(
                    contract=request.app.state.security_contract,
                    trace_events=exc.trace_events,
                    include_semantic_review=False,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.post(
        "/api/benchmarks/run",
        response_model=BenchmarkResult,
        response_model_by_alias=True,
    )
    async def run_benchmark(request: Request) -> BenchmarkResult:
        try:
            benchmark_kwargs = {
                "contract": request.app.state.security_contract,
                "retriever": request.app.state.retriever,
                # Reuse the app-owned catalog so malformed test/configuration
                # data retains the existing diagnostic response boundary.
                "cases": request.app.state.ground_truth_cases,
            }
            if active_workspace is not None or data_dir is not None:
                benchmark_kwargs.update(
                    {
                        "demo_data": request.app.state.demo_data,
                        "profiles": request.app.state.target_profiles,
                        "workspace": active_workspace,
                        "data_dir": data_dir,
                    }
                )
            runtime = build_benchmark_runtime(
                request.app.state.provider,
                **benchmark_kwargs,
            )
            return await runtime.run()
        except UnknownActorError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except AttackCaseExecutionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except EmptyMessageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=request.app.state.provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.post(
        "/api/attack-plans/{plan_id}/replay",
        response_model=ReplayResult,
        response_model_by_alias=True,
    )
    async def replay_attack_plan(
        plan_id: str,
        request: Request,
    ) -> ReplayResult:
        plans_by_id = {
            plan.id: plan
            for plan in build_attack_plans(request.app.state.security_contract)
        }
        plan = plans_by_id.get(plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="unknown attack plan")

        active_provider = request.app.state.provider
        case_executor = AttackCaseExecutor(
            provider=active_provider,
            actors=demo_data.actors,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=request.app.state.security_contract,
            profiles=request.app.state.target_profiles,
        )
        try:
            return await ReplayExecutor(
                plan_executor=AttackPlanExecutor(case_executor),
                contract=request.app.state.security_contract,
            ).replay(plan)
        except UnknownActorError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EmptyMessageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @application.post(
        "/api/attack-chain-reports",
        response_model=AttackChainReport,
        response_model_by_alias=True,
    )
    def create_attack_chain_report(payload: ReplayResult) -> AttackChainReport:
        return build_attack_chain_report(payload)

    @application.post(
        "/api/evaluations",
        response_model=TraceEvaluationResult,
        response_model_by_alias=True,
    )
    async def evaluate_trace(
        payload: TraceEvaluationRequest,
        request: Request,
    ) -> TraceEvaluationResult:
        deterministic_findings = ContractChecker().check(payload.trace_events)
        active_provider = request.app.state.provider
        judge = HybridJudge(active_provider)
        try:
            return await judge.evaluate(
                contract=request.app.state.security_contract,
                trace_events=payload.trace_events,
                include_semantic_review=payload.include_semantic_review,
            )
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc

    @application.post(
        "/api/assistant/queries",
        response_model=AssistantQueryResult,
        response_model_by_alias=True,
    )
    async def assistant_query(
        payload: AssistantQueryRequest,
        request: Request,
    ) -> AssistantQueryResult:
        active_provider = request.app.state.provider
        service = AssistantService(
            provider=active_provider,
            actors=demo_data.actors,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=request.app.state.security_contract,
            target_profile=request.app.state.secure_target_profile,
        )
        try:
            return await service.answer(payload.actor_id, payload.message)
        except UnknownActorError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except EmptyMessageError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ToolAuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            # Includes invalid Mock Customer Tool arguments at the trust boundary.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ProviderConfigurationError as exc:
            raise HTTPException(
                status_code=503,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderResponseError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except ProviderUnavailableError as exc:
            raise HTTPException(
                status_code=502,
                detail=_provider_failure_detail(
                    exc,
                    stage="execution",
                    provider=active_provider,
                ),
            ) from exc
        except RetrieverError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return application


# The packaged Sidecar imports ``create_app`` and supplies its Workspace only
# after validating the fixed lifecycle arguments.  Constructing the ordinary
# development app in a frozen process would eagerly look for repository seed
# data before the bundled ``demo-seed`` is resolved.
app = None if getattr(sys, "frozen", False) else create_app()

__all__ = ["app", "create_app"]
