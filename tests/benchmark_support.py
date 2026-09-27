"""Deterministic providers and dependency builders for F-018 tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from agent_audit_api.attack_cases import AttackCaseExecutor, load_target_profiles
from agent_audit_api.benchmark import GroundTruthRunner
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.planning import (
    AttackPlanExecutor,
    ContractAttackPlanner,
)
from agent_audit_api.providers.base import (
    LLMProvider,
    LLMResponse,
    ProviderUsage,
    ProviderUsageTracker,
    ToolCall,
)
from agent_audit_api.replay import ReplayExecutor
from agent_audit_api.retrieval import Retriever, TfidfRetriever
from agent_audit_api.security_contract import SecurityContract, load_security_contract
from agent_audit_api.services.assistant import AssistantService
from agent_audit_api.tools import MockCustomerExportTool, MockCustomerTool, MockMailTool


@dataclass
class GroundTruthProvider:
    """Emit a Tool Call only when its exact name is in the user message."""

    answer: str = "Ground Truth 的 deterministic provider 回答"
    missing_usage_at: int | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)
    issued_tool_calls: list[ToolCall] = field(default_factory=list)

    @staticmethod
    def _tool_names(tools: Any) -> set[str]:
        names: set[str] = set()
        for tool in tools or ():
            if not isinstance(tool, Mapping):
                continue
            function = tool.get("function")
            if isinstance(function, Mapping) and isinstance(function.get("name"), str):
                names.add(function["name"])
        return names

    @staticmethod
    def _user_text(messages: Any) -> str:
        return "\n".join(
            str(message.get("content") or "")
            for message in messages
            if isinstance(message, Mapping) and message.get("role") == "user"
        )

    def _usage(self, call_number: int) -> ProviderUsage | None:
        if self.missing_usage_at == call_number:
            return None
        return ProviderUsage(input_tokens=10, output_tokens=5, total_tokens=15)

    @staticmethod
    def _mail_resource_ids(user_text: str) -> list[str]:
        known_ids = (
            "doc_product_overview_001",
            "doc_finance_budget_001",
            "doc_external_vendor_prompt_001",
            "doc_demo_usage_guide_001",
            "doc_hr_handbook_001",
            "doc_customer_contract_001",
            "doc_customer_contract_002",
        )
        resource_ids = [document_id for document_id in known_ids if document_id in user_text]
        if "Atlas Vendor" in user_text and "doc_external_vendor_prompt_001" not in resource_ids:
            resource_ids.insert(0, "doc_external_vendor_prompt_001")
        if "财务预算" in user_text and "doc_finance_budget_001" not in resource_ids:
            resource_ids.append("doc_finance_budget_001")
        if not resource_ids:
            resource_ids.append("doc_product_overview_001")
        return resource_ids

    def _response(self, user_text: str, tool_names: set[str]) -> LLMResponse:
        call: ToolCall | None = None
        if "mock_customer_lookup" in tool_names and "mock_customer_lookup" in user_text:
            customer_id = (
                "customer_002"
                if "customer_002" in user_text
                else "customer_001"
                if "customer_001" in user_text
                else None
            )
            if customer_id is not None:
                call = ToolCall(
                    id=f"call_ground_truth_{len(self.calls) + 1}",
                    name="mock_customer_lookup",
                    arguments={"customerId": customer_id},
                )
        elif "mock_mail_send" in tool_names and "mock_mail_send" in user_text:
            approved = "approved=true" in user_text
            call = ToolCall(
                id=f"call_ground_truth_{len(self.calls) + 1}",
                name="mock_mail_send",
                arguments={
                    "to": (
                        "audit@external-sink.demo.local"
                        if "external-sink.demo.local" in user_text
                        else "audit@nebula.demo.local"
                    ),
                    "subject": "合成审计摘要",
                    "body": "Ground Truth synthetic summary",
                    "resourceIds": self._mail_resource_ids(user_text),
                    "approved": approved,
                },
            )
        elif "mock_customer_export" in tool_names and "mock_customer_export" in user_text:
            customer_ids = ["customer_001"]
            if "customer_002" in user_text:
                customer_ids.append("customer_002")
            call = ToolCall(
                id=f"call_ground_truth_{len(self.calls) + 1}",
                name="mock_customer_export",
                arguments={
                    "customerIds": customer_ids,
                    "destination": (
                        "external-sink://exports/customers.json"
                        if "external-sink://" in user_text
                        else "workspace://exports/customers.json"
                    ),
                    "approved": "approved=true" in user_text,
                },
            )

        if call is not None:
            self.issued_tool_calls.append(call)
            return LLMResponse(
                content=None,
                tool_calls=(call,),
                usage=self._usage(len(self.calls) + 1),
            )
        return LLMResponse(content=self.answer, tool_calls=(), usage=self._usage(len(self.calls) + 1))

    async def complete(self, messages, tools=None) -> LLMResponse:
        user_text = self._user_text(messages)
        tool_names = self._tool_names(tools)
        response = self._response(user_text, tool_names)
        self.calls.append(
            {
                "messages": tuple(dict(message) for message in messages),
                "tools": tuple(tools or ()),
                "response": response,
            }
        )
        return response


@dataclass(frozen=True)
class BenchmarkComponents:
    runner: GroundTruthRunner
    contract: SecurityContract
    plans: tuple[Any, ...]
    tracker: ProviderUsageTracker


def build_benchmark_components(
    provider: LLMProvider,
    *,
    contract: SecurityContract | None = None,
    retriever: Retriever | None = None,
) -> BenchmarkComponents:
    """Build the same four-profile chain used by the benchmark API route."""

    data = load_demo_data()
    active_contract = contract or load_security_contract()
    shared_retriever = retriever or TfidfRetriever(data.documents)
    customer_tool = MockCustomerTool(data.customers)
    mail_tool = MockMailTool()
    export_tool = MockCustomerExportTool(data.customers)
    tracker = ProviderUsageTracker(provider)
    profiles = load_target_profiles()
    assistant_services = {
        profile.id: AssistantService(
            provider=tracker,
            actors=data.actors,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=active_contract,
            target_profile=profile,
        )
        for profile in profiles
    }
    case_executor = AttackCaseExecutor(
        provider=tracker,
        actors=data.actors,
        retriever=shared_retriever,
        customer_tool=customer_tool,
        mail_tool=mail_tool,
        export_tool=export_tool,
        contract=active_contract,
        profiles=profiles,
    )
    plan_executor = AttackPlanExecutor(case_executor)
    plans = ContractAttackPlanner(
        contract=active_contract,
        actors=data.actors,
        documents=data.documents,
        customers=data.customers,
        customer_tool=customer_tool,
        mail_tool=mail_tool,
        export_tool=export_tool,
    ).plan()
    runner = GroundTruthRunner(
        assistant_service=assistant_services["secure"],
        assistant_services=assistant_services,
        plan_executor=plan_executor,
        replay_executor=ReplayExecutor(
            plan_executor=plan_executor,
            contract=active_contract,
        ),
        contract=active_contract,
        plans=plans,
        provider_usage_tracker=tracker,
    )
    return BenchmarkComponents(
        runner=runner,
        contract=active_contract,
        plans=plans,
        tracker=tracker,
    )


__all__ = ["BenchmarkComponents", "GroundTruthProvider", "build_benchmark_components"]
