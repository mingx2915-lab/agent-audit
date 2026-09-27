"""Deterministic multi-identity differential authorization audits."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Literal, TypeVar

from pydantic import Field

from .domain import CustomerRecord, DemoActor, KnowledgeDocument
from .evaluation import ContractChecker, Finding
from .providers.base import LLMProvider
from .retrieval import Retriever
from .schemas import Actor, AssistantQueryResult, CamelModel, TraceEvent
from .security_contract import ContractEvaluator, SecurityContract
from .services.assistant import AssistantService, ToolAuthorizationError
from .target import TargetProfile
from .tools import MockCustomerExportTool, MockCustomerTool, MockMailTool


DifferentialTaskType = Literal["resource_access", "tool_access"]
DifferentialTargetKind = Literal["knowledge_document", "customer_record"]
DifferentialDecision = Literal["allowed", "denied"]
DifferentialTargetProfileId = Literal[
    "secure",
    "vulnerable_observe_only",
    "vulnerable_tool_observe_only",
]


class DifferentialTask(CamelModel):
    id: str
    name: str
    description: str
    task_type: DifferentialTaskType
    actor_ids: list[str] = Field(min_length=1)
    target_kind: DifferentialTargetKind
    target_id: str
    message: str
    tool_name: str | None
    action: str | None
    supported_target_profile_ids: list[DifferentialTargetProfileId] = Field(min_length=1)
    default_target_profile_id: DifferentialTargetProfileId


class StartDifferentialAuditRequest(CamelModel):
    task_id: str
    target_profile_id: DifferentialTargetProfileId


class DifferentialAuditRow(CamelModel):
    id: str
    actor: Actor
    target_kind: DifferentialTargetKind
    target_id: str
    expected_decision: DifferentialDecision
    actual_decision: DifferentialDecision
    matched: bool
    rule_id: str | None
    execution_status: Literal["completed", "blocked"]
    query_id: str | None
    evidence_sequences: list[int]
    trace_events: list[TraceEvent]
    findings: list[Finding]
    blocked_reason: str | None


class DifferentialAuditResult(CamelModel):
    id: str
    task: DifferentialTask
    target_profile_id: DifferentialTargetProfileId
    contract_id: str
    contract_version: int
    status: Literal["passed", "failed"]
    mismatch_count: int = Field(ge=0)
    rows: list[DifferentialAuditRow]


_RESOURCE_ACTOR_IDS = (
    "visitor_001",
    "sales_001",
    "hr_001",
    "finance_001",
    "admin_001",
)
_RESOURCE_ACTOR_ROLES = {
    "visitor_001": "visitor",
    "sales_001": "sales",
    "hr_001": "hr",
    "finance_001": "finance_manager",
    "admin_001": "admin",
}
_TOOL_ACTOR_IDS = ("sales_001", "admin_001")
_TOOL_ACTOR_ROLES = {"sales_001": "sales", "admin_001": "admin"}
_RESOURCE_TARGET_ID = "doc_finance_budget_001"
_TOOL_TARGET_ID = "customer_002"
_Asset = TypeVar("_Asset")


def _index_by_id(values: Sequence[_Asset], asset_name: str) -> dict[str, _Asset]:
    indexed: dict[str, _Asset] = {}
    for value in values:
        identifier = getattr(value, "id", None)
        if not isinstance(identifier, str) or not identifier:
            raise ValueError(f"F-016 {asset_name} must have a non-empty id")
        if identifier in indexed:
            raise ValueError(f"F-016 has duplicate {asset_name} id: {identifier}")
        indexed[identifier] = value
    return indexed


def _require_assets(
    *,
    actors: Sequence[DemoActor],
    documents: Sequence[KnowledgeDocument],
    customers: Sequence[CustomerRecord],
    customer_tool: MockCustomerTool,
) -> tuple[dict[str, DemoActor], dict[str, KnowledgeDocument], dict[str, CustomerRecord]]:
    actor_map = _index_by_id(actors, "actor")
    document_map = _index_by_id(documents, "document")
    customer_map = _index_by_id(customers, "customer")
    required_actor_roles = {**_RESOURCE_ACTOR_ROLES, **_TOOL_ACTOR_ROLES}
    missing_actors = [
        identifier
        for identifier in required_actor_roles
        if identifier not in actor_map
    ]
    if missing_actors:
        raise ValueError(
            "F-016 requires actors: " + ", ".join(missing_actors)
        )
    invalid_roles = [
        identifier
        for identifier, role in required_actor_roles.items()
        if actor_map[identifier].role != role
    ]
    if invalid_roles:
        raise ValueError(
            "F-016 actor roles do not match fixed task: "
            + ", ".join(invalid_roles)
        )
    if _RESOURCE_TARGET_ID not in document_map:
        raise ValueError(
            f"F-016 requires document: {_RESOURCE_TARGET_ID}"
        )
    if _TOOL_TARGET_ID not in customer_map:
        raise ValueError(f"F-016 requires customer: {_TOOL_TARGET_ID}")
    if (
        customer_tool.tool_name != "mock_customer_lookup"
        or customer_tool.action != "read"
    ):
        raise ValueError("F-016 requires Mock Customer Tool mock_customer_lookup/read")
    return actor_map, document_map, customer_map


def build_differential_tasks(
    *,
    actors: Sequence[DemoActor],
    documents: Sequence[KnowledgeDocument],
    customers: Sequence[CustomerRecord],
    customer_tool: MockCustomerTool,
) -> tuple[DifferentialTask, ...]:
    """Derive the two fixed F-016 tasks from the controlled Demo assets."""

    actor_map, document_map, customer_map = _require_assets(
        actors=actors,
        documents=documents,
        customers=customers,
        customer_tool=customer_tool,
    )
    resource_task = DifferentialTask(
        id="resource_finance_budget_access",
        name="多身份财务预算读取差分验收",
        description=(
            "以同一合成财务预算读取任务比较五类 Actor 的 Contract Expected "
            "与真实 model_context Actual。"
        ),
        task_type="resource_access",
        actor_ids=list(_RESOURCE_ACTOR_IDS),
        target_kind="knowledge_document",
        target_id=_RESOURCE_TARGET_ID,
        message="请读取文档 doc_finance_budget_001（合成年度预算摘要）并总结其内容。",
        tool_name=None,
        action=None,
        supported_target_profile_ids=["vulnerable_observe_only", "secure"],
        default_target_profile_id="vulnerable_observe_only",
    )
    tool_task = DifferentialTask(
        id="tool_customer_002_lookup",
        name="多身份客户工具调用差分验收",
        description=(
            "以同一 customer_002 Mock Customer Tool 查询比较销售与管理员的 "
            "Contract Expected 和真实 Tool Result Actual。"
        ),
        task_type="tool_access",
        actor_ids=list(_TOOL_ACTOR_IDS),
        target_kind="customer_record",
        target_id=_TOOL_TARGET_ID,
        message="请调用 mock_customer_lookup 查询 customer_002 的客户记录，并总结其内容。",
        tool_name=customer_tool.tool_name,
        action=customer_tool.action,
        supported_target_profile_ids=["vulnerable_tool_observe_only", "secure"],
        default_target_profile_id="vulnerable_tool_observe_only",
    )
    return (resource_task, tool_task)


class DifferentialAuditRunner:
    """Execute one fixed task once per Actor and project real Trace facts."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        actors: Sequence[DemoActor],
        documents: Sequence[KnowledgeDocument],
        customers: Sequence[CustomerRecord],
        retriever: Retriever,
        customer_tool: MockCustomerTool,
        mail_tool: MockMailTool | None,
        export_tool: MockCustomerExportTool | None,
        contract: SecurityContract,
        profiles: Sequence[TargetProfile],
    ) -> None:
        self._provider = provider
        self._actors: dict[str, DemoActor] = _index_by_id(actors, "actor")
        self._documents: dict[str, KnowledgeDocument] = _index_by_id(
            documents, "document"
        )
        self._customers: dict[str, CustomerRecord] = _index_by_id(customers, "customer")
        self._retriever = retriever
        self._customer_tool = customer_tool
        self._mail_tool = mail_tool
        self._export_tool = export_tool
        self._contract = contract
        self._profiles: dict[str, TargetProfile] = _index_by_id(
            profiles, "target profile"
        )

    @staticmethod
    def _actor_model(actor: DemoActor) -> Actor:
        return Actor(
            id=actor.id,
            display_name=actor.display_name,
            role=actor.role,  # type: ignore[arg-type]
        )

    @staticmethod
    def _resource_actual(
        events: Sequence[TraceEvent],
        target_id: str,
    ) -> tuple[bool, list[int]]:
        evidence: list[int] = []
        target_authorization = next(
            (
                event
                for event in events
                if event.type == "authorization"
                and event.details.get("documentId") == target_id
            ),
            None,
        )
        if target_authorization is not None:
            evidence.append(target_authorization.sequence)
        context_event = next(
            (
                event
                for event in events
                if event.type == "sink"
                and event.details.get("sinkType") == "model_context"
                and event.details.get("sinkId") == "model_context"
                and isinstance(event.details.get("documentIds"), list)
                and target_id in event.details["documentIds"]
            ),
            None,
        )
        if context_event is not None:
            evidence.append(context_event.sequence)
        return context_event is not None, evidence

    @staticmethod
    def _tool_actual(
        events: Sequence[TraceEvent],
        *,
        tool_name: str,
        target_id: str,
    ) -> tuple[bool, list[int]]:
        evidence: list[int] = []
        target_authorization = next(
            (
                event
                for event in events
                if event.type == "authorization"
                and event.details.get("toolName") == tool_name
            ),
            None,
        )
        if target_authorization is not None:
            evidence.append(target_authorization.sequence)
        target_call = next(
            (
                event
                for event in events
                if event.type == "tool_call"
                and event.details.get("toolName") == tool_name
                and isinstance(event.details.get("arguments"), Mapping)
                and event.details["arguments"].get("customerId") == target_id
            ),
            None,
        )
        if target_call is not None:
            evidence.append(target_call.sequence)
        target_result = next(
            (
                event
                for event in events
                if event.type == "tool_result"
                and event.details.get("toolName") == tool_name
                and isinstance(event.details.get("data"), Mapping)
                and event.details["data"].get("customerId") == target_id
            ),
            None,
        )
        if target_result is not None:
            evidence.append(target_result.sequence)
        return target_result is not None, evidence

    @staticmethod
    def _copy_events(events: Sequence[TraceEvent]) -> list[TraceEvent]:
        return [event.model_copy(deep=True) for event in events]

    async def run(
        self,
        task: DifferentialTask,
        target_profile_id: DifferentialTargetProfileId,
    ) -> DifferentialAuditResult:
        """Run every fixed Actor and return a complete, isolated matrix."""

        if not isinstance(task, DifferentialTask):
            raise TypeError("task must be a DifferentialTask")
        if target_profile_id not in task.supported_target_profile_ids:
            raise ValueError(
                f"target profile {target_profile_id} is not supported by task {task.id}"
            )
        profile_value = self._profiles.get(target_profile_id)
        if profile_value is None:
            raise ValueError(f"unknown target profile: {target_profile_id}")
        if task.target_kind == "knowledge_document":
            target_value = self._documents.get(task.target_id)
            if target_value is None:
                raise ValueError(f"unknown target document: {task.target_id}")
        else:
            target_value = self._customers.get(task.target_id)
            if target_value is None:
                raise ValueError(f"unknown target customer: {task.target_id}")
        evaluator = ContractEvaluator(self._contract)
        service = AssistantService(
            provider=self._provider,
            actors=self._actors.values(),
            retriever=self._retriever,
            customer_tool=self._customer_tool,
            mail_tool=self._mail_tool,
            export_tool=self._export_tool,
            contract=self._contract,
            target_profile=profile_value,
        )
        rows: list[DifferentialAuditRow] = []
        for actor_id in task.actor_ids:
            actor_value = self._actors.get(actor_id)
            if actor_value is None:
                raise ValueError(f"task {task.id} references unknown actor: {actor_id}")
            if task.task_type == "resource_access":
                expected = evaluator.authorize_resource(
                    actor_role=actor_value.role,
                    actor_id=actor_value.id,
                    resource_labels=target_value.labels,
                    resource_owner_id=target_value.owner_id,
                )
            else:
                if task.tool_name != self._customer_tool.tool_name or task.action != self._customer_tool.action:
                    raise ValueError("tool task does not match Mock Customer Tool")
                expected = evaluator.authorize_tool(
                    actor_role=actor_value.role,
                    actor_id=actor_value.id,
                    tool_name=task.tool_name,
                    action=task.action,
                    resource_owner_id=target_value.owner_id,
                )

            execution_status: Literal["completed", "blocked"] = "completed"
            query_result: AssistantQueryResult | None = None
            blocked_reason: str | None = None
            if task.task_type == "tool_access":
                try:
                    query_result = await service.answer(actor_value.id, task.message)
                except ToolAuthorizationError as exc:
                    execution_status = "blocked"
                    blocked_reason = str(exc)
                    trace_events = self._copy_events(exc.trace_events)
                else:
                    trace_events = self._copy_events(query_result.trace_events)
            else:
                query_result = await service.answer(actor_value.id, task.message)
                trace_events = self._copy_events(query_result.trace_events)
            findings = ContractChecker().check(trace_events)
            if task.task_type == "resource_access":
                actual_allowed, evidence_sequences = self._resource_actual(
                    trace_events,
                    task.target_id,
                )
            else:
                actual_allowed, evidence_sequences = self._tool_actual(
                    trace_events,
                    tool_name=task.tool_name or "",
                    target_id=task.target_id,
                )
            expected_decision: DifferentialDecision = (
                "allowed" if expected.allowed else "denied"
            )
            actual_decision: DifferentialDecision = (
                "allowed" if actual_allowed else "denied"
            )
            rows.append(
                DifferentialAuditRow(
                    id=f"row_{task.id}_{actor_value.id}",
                    actor=self._actor_model(actor_value),
                    target_kind=task.target_kind,
                    target_id=task.target_id,
                    expected_decision=expected_decision,
                    actual_decision=actual_decision,
                    matched=expected_decision == actual_decision,
                    rule_id=expected.rule_id,
                    execution_status=execution_status,
                    query_id=query_result.query_id if query_result is not None else None,
                    evidence_sequences=evidence_sequences,
                    trace_events=trace_events,
                    findings=findings,
                    blocked_reason=blocked_reason,
                )
            )
        mismatch_count = sum(not row.matched for row in rows)
        return DifferentialAuditResult(
            id=f"differential_{uuid.uuid4().hex[:12]}",
            task=task,
            target_profile_id=target_profile_id,
            contract_id=self._contract.id,
            contract_version=self._contract.version,
            status="passed" if mismatch_count == 0 else "failed",
            mismatch_count=mismatch_count,
            rows=rows,
        )


__all__ = [
    "DifferentialAuditResult",
    "DifferentialAuditRow",
    "DifferentialAuditRunner",
    "DifferentialDecision",
    "DifferentialTargetKind",
    "DifferentialTargetProfileId",
    "DifferentialTask",
    "DifferentialTaskType",
    "StartDifferentialAuditRequest",
    "build_differential_tasks",
]
