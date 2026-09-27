"""Enterprise document import and Workspace catalog support.

The import boundary deliberately accepts text that has already been selected
by the native shell.  It never receives or persists an absolute filesystem
path.  Preview is a pure calculation; commit validates the same payload again,
builds the replacement index before changing the Workspace, and writes one
atomic catalog snapshot.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from collections.abc import Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import Field, field_validator

from .domain import CustomerRecord, DemoActor, KnowledgeDocument
from .planning import AttackPlan, ContractAttackPlanner
from .retrieval import ReloadableRetriever, Retriever, RetrieverError
from .schemas import ActorRole, CamelModel
from .security_contract import ContractEvaluator, SecurityContract
from .tools import MockCustomerExportTool, MockCustomerTool, MockMailTool
from .workspace import AuditWorkspace, WorkspaceError


SUPPORTED_EXTENSIONS = frozenset({".txt", ".md", ".pdf", ".docx"})
# The picker bounds the original selected file separately from the normalized
# UTF-8 text sent to this API.  Binary PDF/DOCX files can be larger than their
# extracted text while the persisted/indexed representation remains bounded.
MAX_SOURCE_SIZE_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_SIZE_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ITEMS = 50
CONTENT_PREVIEW_LENGTH = 320

DocumentImportStatus = Literal["ready", "unsupported", "invalid"]
DocumentImportDiagnosticCode = Literal[
    "unsupported_format",
    "invalid_utf8",
    "parse_failed",
    "encrypted",
    "no_text",
    "too_large",
    "read_failed",
]
DocumentSensitivity = Literal["public", "confidential"]
DocumentBusinessScope = Literal["general", "customer", "finance", "hr"]
DocumentTrustLevel = Literal["trusted", "untrusted"]


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_relative_path(value: str) -> str:
    value = _non_empty(value, "relativePath")
    if "\\" in value:
        raise ValueError("relativePath must use portable forward slashes")
    path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    raw_parts = value.split("/")
    if (
        path.is_absolute()
        or path.anchor
        or windows_path.is_absolute()
        or windows_path.anchor
        or any(part in ("", ".", "..") for part in raw_parts)
    ):
        raise ValueError("relativePath must be a safe relative path")
    return value


def _validate_display_name(value: str) -> str:
    value = _non_empty(value, "displayName")
    if (
        "/" in value
        or "\\" in value
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or PureWindowsPath(value).anchor
    ):
        raise ValueError("displayName must be a file name, not an absolute path")
    return value


def _validate_source_id(value: str) -> str:
    value = _non_empty(value, "sourceId")
    if any(character in value for character in ("/", "\\", ":")):
        raise ValueError("sourceId must be a portable identifier")
    return value


class DocumentImportError(ValueError):
    """Base error for import validation and Workspace operations."""


class DocumentImportWorkspaceError(DocumentImportError):
    """Raised when a commit is requested without a valid Workspace."""


class DocumentImportIndexError(DocumentImportError):
    """Raised when the replacement Retriever cannot be built or prepared."""


class DocumentImportStorageError(RuntimeError):
    """Raised when the Workspace catalog cannot be atomically replaced."""


class DocumentImportSource(CamelModel):
    source_id: str
    display_name: str
    relative_path: str
    extension: str
    size_bytes: int = Field(ge=0)
    content: str | None = None
    diagnostic: str | None = None
    # The native picker may provide these as a display hint.  The API never
    # trusts the hint and recomputes the status from the payload below.
    status: DocumentImportStatus | None = None
    diagnostic_code: DocumentImportDiagnosticCode | None = None

    _validate_source_id_value = field_validator("source_id")(_validate_source_id)
    _validate_display_name_value = field_validator("display_name")(_validate_display_name)
    _validate_relative_path_value = field_validator("relative_path")(_validate_relative_path)

    @field_validator("extension")
    @classmethod
    def _normalize_extension(cls, value: str) -> str:
        value = _non_empty(value, "extension").lower()
        if not value.startswith("."):
            value = "." + value
        return value

    @field_validator("diagnostic")
    @classmethod
    def _normalize_diagnostic(cls, value: str | None) -> str | None:
        return None if value is None else _non_empty(value, "diagnostic")


class DocumentImportMetadata(CamelModel):
    title: str
    sensitivity: DocumentSensitivity
    business_scope: DocumentBusinessScope
    owner_id: str | None = None
    trust_level: DocumentTrustLevel

    _validate_title = field_validator("title")(
        lambda value: _non_empty(value, "title")
    )
    @field_validator("owner_id")
    @classmethod
    def _normalize_owner(cls, value: str | None) -> str | None:
        return None if value is None else _non_empty(value, "ownerId")


class DocumentImportDraft(CamelModel):
    source: DocumentImportSource
    metadata: DocumentImportMetadata


class DocumentAuthorizationPreview(CamelModel):
    actor_id: str
    role: ActorRole
    allowed: bool
    rule_id: str | None = None


class DocumentImportPlanSummary(CamelModel):
    """Safe projection of one real Contract-derived executable AttackPlan."""

    id: str
    name: str
    description: str
    basis_type: Literal[
        "resource_owner_scope",
        "tool_owner_scope",
        "source_sink",
        "tool_record_limit",
    ]
    basis_rule_id: str
    attacker_type: Literal["outside_in", "inside_out"]
    actor_id: str
    target_kind: Literal[
        "knowledge_document",
        "customer_record",
        "external_sink",
        "customer_export",
    ]
    target_id: str
    target_profile_id: str


class DocumentImportPreviewItem(CamelModel):
    source_id: str
    display_name: str
    relative_path: str
    status: DocumentImportStatus
    title_suggestion: str
    content_preview: str | None = None
    diagnostic: str | None = None
    diagnostic_code: DocumentImportDiagnosticCode | None = None
    metadata: DocumentImportMetadata
    authorization: list[DocumentAuthorizationPreview]


class DocumentImportPreviewRequest(CamelModel):
    documents: list[DocumentImportDraft] = Field(
        min_length=1,
        max_length=MAX_IMPORT_ITEMS,
    )


class DocumentImportPreview(CamelModel):
    contract_id: str
    contract_version: int
    items: list[DocumentImportPreviewItem]
    ready_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    executable_plans: list["DocumentImportPlanSummary"] = Field(default_factory=list)
    plan_diagnostic: str | None = None


class WorkspaceDocumentSummary(CamelModel):
    id: str
    title: str
    owner_id: str | None
    labels: list[str]
    source_type: str
    trust_level: str


class DocumentIndexMetadata(CamelModel):
    engine_id: Literal["tfidf", "embedding"]
    model_name: str | None
    dimensions: int | None
    indexed_document_count: int = Field(ge=0)


class DocumentCatalog(CamelModel):
    workspace_name: str | None
    documents: list[WorkspaceDocumentSummary]
    retriever: DocumentIndexMetadata


class DocumentImportCommitRequest(CamelModel):
    documents: list[DocumentImportDraft] = Field(
        min_length=1,
        max_length=MAX_IMPORT_ITEMS,
    )


class DocumentImportSkippedItem(CamelModel):
    source_id: str
    display_name: str
    status: Literal["unsupported", "invalid"]
    diagnostic: str
    diagnostic_code: DocumentImportDiagnosticCode | None = None


class DocumentImportResult(CamelModel):
    imported: list[WorkspaceDocumentSummary]
    skipped: list[DocumentImportSkippedItem]
    retriever: DocumentIndexMetadata
    executable_plans: list[DocumentImportPlanSummary] = Field(default_factory=list)
    plan_diagnostic: str | None = None


def _labels_for_metadata(metadata: DocumentImportMetadata) -> tuple[str, ...]:
    labels = [metadata.sensitivity]
    if metadata.business_scope != "general":
        labels.append(metadata.business_scope)
    return tuple(labels)


def _document_summary(document: KnowledgeDocument) -> WorkspaceDocumentSummary:
    return WorkspaceDocumentSummary(
        id=document.id,
        title=document.title,
        owner_id=document.owner_id,
        labels=list(document.labels),
        source_type=document.source_type,
        trust_level=document.trust_level,
    )


def _index_metadata(retriever: Retriever) -> DocumentIndexMetadata:
    metadata = retriever.metadata
    return DocumentIndexMetadata(
        engine_id=metadata.engine_id,
        model_name=metadata.model_name,
        dimensions=metadata.dimensions,
        indexed_document_count=metadata.indexed_document_count,
    )


_DIAGNOSTIC_MESSAGES: dict[DocumentImportDiagnosticCode, str] = {
    "unsupported_format": "当前版本不支持此文件格式",
    "invalid_utf8": "文件不是有效的 UTF-8 文本",
    "parse_failed": "文档解析失败，请确认文件内容完整",
    "encrypted": "文档已加密，当前版本无法读取",
    "no_text": "文档不包含可提取文本",
    "too_large": (
        "原始文件不能超过 "
        f"{MAX_SOURCE_SIZE_BYTES // (1024 * 1024)} MiB，标准化文本不能超过 "
        f"{MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)} MiB"
    ),
    "read_failed": "无法读取文件，请检查文件权限",
}


def _diagnostic_message(
    code: DocumentImportDiagnosticCode,
    diagnostic: str | None = None,
) -> str:
    """Return a readable diagnostic without echoing an absolute source path."""

    # Native code supplies the human-readable reason.  A stable code is still
    # available for clients that need to render a localized label.  Do not
    # include the source path in generated diagnostics.
    if diagnostic and _contains_absolute_path(diagnostic):
        return _DIAGNOSTIC_MESSAGES[code]
    return (
        diagnostic.strip()
        if diagnostic and diagnostic.strip()
        else _DIAGNOSTIC_MESSAGES[code]
    )


def _contains_absolute_path(value: str) -> bool:
    """Detect path syntax at the diagnostic trust boundary.

    ``displayName``/``relativePath`` are validated structurally.  Diagnostics
    are free-form native text, so only absolute path tokens are suppressed;
    ordinary readable error details remain intact.
    """

    for token in re.split(r"\s+", value):
        candidate = token.strip("`'\".,;:()[]{}")
        if (
            candidate.startswith("\\\\")
            or PurePosixPath(candidate).is_absolute()
            or PureWindowsPath(candidate).is_absolute()
        ):
            return True
    return False


def _source_status(
    source: DocumentImportSource,
) -> tuple[
    DocumentImportStatus,
    DocumentImportDiagnosticCode | None,
    str | None,
]:
    """Recompute import state at the API trust boundary.

    ``status`` from the native picker is intentionally ignored.  PDF/DOCX
    sources carry text already normalized by the local shell; their binary
    size therefore cannot be compared with the UTF-8 size of ``content``.
    Plain text sources remain byte-for-byte checked.
    """

    if source.extension not in SUPPORTED_EXTENSIONS:
        code: DocumentImportDiagnosticCode = "unsupported_format"
        return "unsupported", code, _diagnostic_message(code, source.diagnostic)
    if source.size_bytes > MAX_SOURCE_SIZE_BYTES or (
        source.extension in {".txt", ".md"}
        and source.size_bytes > MAX_DOCUMENT_SIZE_BYTES
    ):
        code = "too_large"
        return "invalid", code, _diagnostic_message(code, source.diagnostic)
    if source.diagnostic_code is not None:
        code = source.diagnostic_code
        # A picker diagnostic always describes a failed read/parse, even if a
        # stale native status hint says ``ready``.
        return "invalid", code, _diagnostic_message(code, source.diagnostic)
    if source.diagnostic:
        code = "parse_failed"
        return "invalid", code, _diagnostic_message(code, source.diagnostic)
    if source.content is None:
        code = "parse_failed"
        return "invalid", code, _diagnostic_message(code)
    if not source.content.strip():
        code = "no_text"
        return "invalid", code, _diagnostic_message(code)

    actual_size = len(source.content.encode("utf-8"))
    if source.extension in {".txt", ".md"} and actual_size != source.size_bytes:
        code = "invalid_utf8"
        return "invalid", code, "文件大小与文本内容不一致"
    # A normalized PDF/DOCX payload may be smaller or larger than the source
    # archive, but the resulting text must remain within the same bounded
    # import envelope before it is copied into Workspace and indexed.
    if actual_size > MAX_DOCUMENT_SIZE_BYTES:
        code = "too_large"
        return "invalid", code, _diagnostic_message(code)
    return "ready", None, None


def _title_suggestion(source: DocumentImportSource) -> str:
    name = source.display_name
    extension = source.extension
    if name.lower().endswith(extension):
        name = name[: -len(extension)]
    return name.strip() or source.relative_path


def _as_document(
    draft: DocumentImportDraft,
    *,
    document_id: str | None = None,
) -> KnowledgeDocument:
    metadata = draft.metadata
    source = draft.source
    if source.content is None:
        raise DocumentImportError("ready document is missing content")
    return KnowledgeDocument(
        id=document_id or f"doc_import_{uuid.uuid4().hex}",
        title=metadata.title,
        content=source.content,
        owner_id=metadata.owner_id,
        labels=_labels_for_metadata(metadata),
        source_id=f"source_import_{uuid.uuid4().hex}",
        source_type=(
            "knowledge_base" if metadata.trust_level == "trusted" else "external_document"
        ),
        trust_level=metadata.trust_level,
    )


def _plan_summary(plan: AttackPlan) -> DocumentImportPlanSummary:
    """Project a planner result without exposing its generated attack message."""

    return DocumentImportPlanSummary(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        basis_type=plan.basis_type,
        basis_rule_id=plan.basis_rule_id,
        attacker_type=plan.attacker_type,
        actor_id=plan.actor_id,
        target_kind=plan.target_kind,
        target_id=plan.target_id,
        target_profile_id=plan.target_profile_id,
    )


def _atomic_write_documents(path: Path, documents: Sequence[KnowledgeDocument]) -> None:
    payload = [
        {
            "id": document.id,
            "title": document.title,
            "content": document.content,
            "ownerId": document.owner_id,
            "labels": list(document.labels),
            "sourceId": document.source_id,
            "sourceType": document.source_type,
            "trustLevel": document.trust_level,
        }
        for document in documents
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise DocumentImportStorageError(
            "unable to write Workspace document catalog"
        ) from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


class DocumentImportService:
    """Preview and commit explicit text documents into one Workspace."""

    def __init__(
        self,
        *,
        workspace: AuditWorkspace | None,
        actors: Sequence[DemoActor],
        documents: Sequence[KnowledgeDocument],
        contract: SecurityContract,
        retriever: ReloadableRetriever | Retriever,
        customers: Sequence[CustomerRecord] = (),
        customer_tool: MockCustomerTool | None = None,
        mail_tool: MockMailTool | None = None,
        export_tool: MockCustomerExportTool | None = None,
    ) -> None:
        self.workspace = workspace
        self.actors = tuple(actors)
        self.documents = tuple(documents)
        self.contract = contract
        self.retriever = retriever
        self.customers = tuple(customers)
        self.customer_tool = customer_tool
        self.mail_tool = mail_tool
        self.export_tool = export_tool

    def _validate_metadata(self, metadata: DocumentImportMetadata) -> None:
        if metadata.owner_id is None:
            return
        if metadata.owner_id not in {actor.id for actor in self.actors}:
            raise DocumentImportError(f"unknown ownerId: {metadata.owner_id}")

    def _authorization(
        self,
        document: KnowledgeDocument,
    ) -> list[DocumentAuthorizationPreview]:
        evaluator = ContractEvaluator(self.contract)
        previews: list[DocumentAuthorizationPreview] = []
        for actor in self.actors:
            decision = evaluator.authorize_resource(
                actor_role=actor.role,
                actor_id=actor.id,
                resource_labels=document.labels,
                resource_owner_id=document.owner_id,
            )
            rule_id = decision.rule_id
            if rule_id is None:
                matching_rules = sorted(
                    (
                        rule
                        for rule in self.contract.resource_rules
                        if all(label in set(document.labels) for label in rule.match_labels)
                    ),
                    key=lambda rule: (-len(rule.match_labels), rule.id),
                )
                rule_id = matching_rules[0].id if matching_rules else None
            previews.append(
                DocumentAuthorizationPreview(
                    actor_id=actor.id,
                    role=actor.role,  # type: ignore[arg-type]
                    allowed=decision.allowed,
                    rule_id=rule_id,
                )
            )
        return previews

    def _plans(
        self,
        documents: Sequence[KnowledgeDocument],
    ) -> tuple[list[DocumentImportPlanSummary], str | None]:
        """Project only plans returned by the active ContractAttackPlanner."""

        if self.customer_tool is None:
            return [], "当前接入状态缺少可执行 Plan 所需的企业工具配置"
        plans = ContractAttackPlanner(
            contract=self.contract,
            actors=self.actors,
            documents=documents,
            customers=self.customers,
            customer_tool=self.customer_tool,
            mail_tool=self.mail_tool,
            export_tool=self.export_tool,
        ).plan()
        summaries = [_plan_summary(plan) for plan in plans]
        if summaries:
            return summaries, None

        owner_resource_rules = [
            rule.id
            for rule in self.contract.resource_rules
            if rule.require_owner_match
        ]
        owner_tool_rules = [
            rule.id for rule in self.contract.tool_rules if rule.require_owner_match
        ]
        if not owner_resource_rules and not owner_tool_rules and not self.contract.sink_rules:
            return [], "当前 active Contract 没有可执行的 Resource、Tool 或 Sink Rule"
        if not self.actors or (not documents and not self.customers):
            return [], "当前 Workspace 缺少派生 Plan 所需的角色、资料或客户对象"
        candidate_rule_ids = [*owner_resource_rules, *owner_tool_rules]
        if self.contract.sink_rules:
            candidate_rule_ids.extend(rule.id for rule in self.contract.sink_rules)
        rules = "、".join(candidate_rule_ids)
        return (
            [],
            "active Contract 暂未从现有角色、资料和工具派生可执行 Plan"
            + (f"（候选规则：{rules}）" if rules else ""),
        )

    def preview(self, request: DocumentImportPreviewRequest) -> DocumentImportPreview:
        items: list[DocumentImportPreviewItem] = []
        for draft in request.documents:
            self._validate_metadata(draft.metadata)
            status, diagnostic_code, diagnostic = _source_status(draft.source)
            candidate = _as_document(
                draft,
                document_id=f"preview_{draft.source.source_id}",
            ) if status == "ready" else None
            title_suggestion = _title_suggestion(draft.source)
            items.append(
                DocumentImportPreviewItem(
                    source_id=draft.source.source_id,
                    display_name=draft.source.display_name,
                    relative_path=draft.source.relative_path,
                    status=status,
                    title_suggestion=title_suggestion,
                    content_preview=(
                        draft.source.content[:CONTENT_PREVIEW_LENGTH]
                        if status == "ready" and draft.source.content is not None
                        else None
                    ),
                    diagnostic=diagnostic,
                    diagnostic_code=diagnostic_code,
                    metadata=draft.metadata,
                    authorization=self._authorization(candidate) if candidate else [],
                )
            )
        ready_count = sum(item.status == "ready" for item in items)
        # Candidate IDs only exist for the side-effect-free preview.  Returning
        # plans that target those temporary IDs would produce a plan that
        # cannot be executed after commit, so preview exposes only plans backed
        # by the current committed catalog.  Commit returns the post-import
        # plans with their real document IDs.
        executable_plans, plan_diagnostic = self._plans(self.documents)
        return DocumentImportPreview(
            contract_id=self.contract.id,
            contract_version=self.contract.version,
            items=items,
            ready_count=ready_count,
            skipped_count=len(items) - ready_count,
            executable_plans=executable_plans,
            plan_diagnostic=plan_diagnostic,
        )

    def catalog(self) -> DocumentCatalog:
        workspace_name = self.workspace.manifest.name if self.workspace else None
        return DocumentCatalog(
            workspace_name=workspace_name,
            documents=[_document_summary(document) for document in self.documents],
            retriever=_index_metadata(self.retriever),
        )

    def commit(self, request: DocumentImportCommitRequest) -> DocumentImportResult:
        if self.workspace is None:
            raise DocumentImportWorkspaceError(
                "document import requires an active Workspace"
            )
        try:
            self.workspace.documents_file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DocumentImportWorkspaceError(
                "Workspace documents directory is not writable"
            ) from exc

        imported_drafts: list[DocumentImportDraft] = []
        skipped: list[DocumentImportSkippedItem] = []
        for draft in request.documents:
            self._validate_metadata(draft.metadata)
            status, diagnostic_code, diagnostic = _source_status(draft.source)
            if status == "ready":
                imported_drafts.append(draft)
            else:
                skipped.append(
                    DocumentImportSkippedItem(
                        source_id=draft.source.source_id,
                        display_name=draft.source.display_name,
                        status=status,
                        diagnostic=diagnostic or "document is not importable",
                        diagnostic_code=diagnostic_code,
                    )
                )
        if not imported_drafts:
            raise DocumentImportError(
                "没有可导入的 PDF、DOCX、UTF-8 .txt 或 .md 文档"
            )

        imported_documents = tuple(_as_document(draft) for draft in imported_drafts)
        new_documents = tuple([*self.documents, *imported_documents])
        try:
            if isinstance(self.retriever, ReloadableRetriever):
                candidate_retriever = self.retriever.build_candidate(new_documents)
            else:
                raise RetrieverError("document import requires a reloadable Retriever")
            _atomic_write_documents(self.workspace.documents_file_path, new_documents)
            self.retriever.replace(candidate_retriever)
        except DocumentImportError:
            raise
        except RetrieverError as exc:
            raise DocumentImportIndexError(
                "unable to rebuild document Retriever"
            ) from exc
        except WorkspaceError:
            raise

        # Publish the new in-memory catalog only after both the candidate index
        # and atomic Workspace snapshot have succeeded.  A subsequent import
        # therefore appends to this exact tuple instead of the startup tuple.
        self.documents = new_documents
        executable_plans, plan_diagnostic = self._plans(new_documents)

        return DocumentImportResult(
            imported=[_document_summary(document) for document in imported_documents],
            skipped=skipped,
            retriever=_index_metadata(self.retriever),
            executable_plans=executable_plans,
            plan_diagnostic=plan_diagnostic,
        )


# Friendly aliases for callers that prefer the shorter noun.
DocumentImporter = DocumentImportService


__all__ = [
    "CONTENT_PREVIEW_LENGTH",
    "DocumentAuthorizationPreview",
    "DocumentBusinessScope",
    "DocumentCatalog",
    "DocumentImportCommitRequest",
    "DocumentImportDiagnosticCode",
    "DocumentImportDraft",
    "DocumentImportError",
    "DocumentImportIndexError",
    "DocumentImportMetadata",
    "DocumentImportPreview",
    "DocumentImportPreviewItem",
    "DocumentImportPreviewRequest",
    "DocumentImportPlanSummary",
    "DocumentImportResult",
    "DocumentImportService",
    "DocumentImportSkippedItem",
    "DocumentImportSource",
    "DocumentImportStatus",
    "DocumentImportWorkspaceError",
    "DocumentImportStorageError",
    "DocumentImporter",
    "DocumentIndexMetadata",
    "DocumentSensitivity",
    "DocumentTrustLevel",
    "MAX_DOCUMENT_SIZE_BYTES",
    "MAX_IMPORT_ITEMS",
    "MAX_SOURCE_SIZE_BYTES",
    "SUPPORTED_EXTENSIONS",
    "WorkspaceDocumentSummary",
]
