"""Shared runtime assembly for the fixed Ground Truth benchmark.

The CLI and HTTP benchmark endpoint must execute the same controlled demo
chain.  This module owns that assembly while leaving the benchmark runner's
deterministic execution and metric calculation in :mod:`benchmark`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .attack_cases import AttackCaseExecutor, load_target_profiles
from .benchmark import (
    BenchmarkResult,
    GroundTruthCase,
    GroundTruthRunner,
    load_ground_truth_cases,
)
from .demo_data import DemoData, load_demo_data
from .history import AuditRuntimeSnapshot
from .planning import AttackPlan, AttackPlanExecutor, ContractAttackPlanner
from .providers.base import LLMProvider, ProviderUsageTracker
from .red_team import provider_metadata
from .replay import ReplayExecutor
from .retrieval import EmbeddingRetriever, Retriever
from .security_contract import SecurityContract, load_security_contract
from .services.assistant import AssistantService
from .target import TargetProfile
from .tools import MockCustomerExportTool, MockCustomerTool, MockMailTool
from .workspace import AuditWorkspace


@dataclass(frozen=True)
class BenchmarkRuntime:
    """All dependencies required to run the repository-owned benchmark.

    ``cases`` is populated from the fixed repository catalog by default.  The
    optional internal override is used by the HTTP application's already
    loaded catalog so existing diagnostics remain tied to app construction;
    the CLI never receives case input and uses the default fixed catalog.
    """

    runner: GroundTruthRunner
    cases: tuple[GroundTruthCase, ...]
    contract: SecurityContract
    plans: tuple[AttackPlan, ...]
    provider: LLMProvider
    retriever: Retriever
    provider_usage_tracker: ProviderUsageTracker
    runtime_snapshot: AuditRuntimeSnapshot

    async def run(self) -> BenchmarkResult:
        """Execute the fixed cases once through the real benchmark runner."""

        return await self.runner.run(self.cases)


def _runtime_snapshot(
    provider: LLMProvider,
    retriever: Retriever,
) -> AuditRuntimeSnapshot:
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


def build_benchmark_runtime(
    provider: LLMProvider,
    *,
    contract: SecurityContract | None = None,
    retriever: Retriever | None = None,
    cases: Sequence[GroundTruthCase] | None = None,
    profiles: Sequence[TargetProfile] | None = None,
    plans: Sequence[AttackPlan] | None = None,
    demo_data: DemoData | None = None,
    data_dir: str | Path | None = None,
    workspace: AuditWorkspace | None = None,
) -> BenchmarkRuntime:
    """Build the shared four-profile, fixed 24-case benchmark runtime.

    ``provider`` and an optional already-created ``retriever`` are explicit so
    production configuration and HTTP app state are preserved.  A Desktop
    caller supplies one validated ``workspace`` so all assets come from that
    Workspace; omitted paths retain the repository development entrypoint.
    ``cases`` and ``profiles`` are internal app-state hooks and are not exposed
    by the CLI.
    """

    if workspace is not None and data_dir is not None:
        raise ValueError("workspace and data_dir cannot both be supplied")
    if workspace is not None:
        documents_dir = workspace.documents_path
        contract_dir = workspace.contract_path
        cases_dir = workspace.cases_path
    else:
        documents_dir = None
        contract_dir = None
        cases_dir = None

    app_demo_data = demo_data
    if app_demo_data is None:
        if documents_dir is not None:
            app_demo_data = load_demo_data(documents_dir)
        elif data_dir is not None:
            app_demo_data = load_demo_data(data_dir)
        else:
            app_demo_data = load_demo_data()

    if contract is not None:
        active_contract = contract
    elif contract_dir is not None:
        active_contract = load_security_contract(contract_dir)
    elif data_dir is not None:
        active_contract = load_security_contract(data_dir)
    else:
        active_contract = load_security_contract()
    shared_retriever = (
        retriever
        if retriever is not None
        else EmbeddingRetriever(app_demo_data.documents)
    )
    if cases is not None:
        ground_truth_cases = tuple(cases)
    elif cases_dir is not None:
        ground_truth_cases = load_ground_truth_cases(cases_dir)
    elif data_dir is not None:
        ground_truth_cases = load_ground_truth_cases(data_dir)
    else:
        ground_truth_cases = load_ground_truth_cases()
    if profiles is not None:
        target_profiles = tuple(profiles)
    elif cases_dir is not None:
        target_profiles = load_target_profiles(cases_dir)
    elif data_dir is not None:
        target_profiles = load_target_profiles(data_dir)
    else:
        target_profiles = load_target_profiles()
    customer_tool = MockCustomerTool(app_demo_data.customers)
    mail_tool = MockMailTool()
    export_tool = MockCustomerExportTool(app_demo_data.customers)
    usage_tracker = ProviderUsageTracker(provider)

    assistant_services = {
        profile.id: AssistantService(
            provider=usage_tracker,
            actors=app_demo_data.actors,
            retriever=shared_retriever,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
            contract=active_contract,
            target_profile=profile,
        )
        for profile in target_profiles
    }
    secure_service = assistant_services.get("secure")
    if secure_service is None:
        raise ValueError("secure target profile is unavailable")

    case_executor = AttackCaseExecutor(
        provider=usage_tracker,
        actors=app_demo_data.actors,
        retriever=shared_retriever,
        customer_tool=customer_tool,
        mail_tool=mail_tool,
        export_tool=export_tool,
        contract=active_contract,
        profiles=target_profiles,
    )
    plan_executor = AttackPlanExecutor(case_executor)
    benchmark_plans = (
        tuple(plan.model_copy(deep=True) for plan in plans)
        if plans is not None
        else ContractAttackPlanner(
            contract=active_contract,
            actors=app_demo_data.actors,
            documents=app_demo_data.documents,
            customers=app_demo_data.customers,
            customer_tool=customer_tool,
            mail_tool=mail_tool,
            export_tool=export_tool,
        ).plan()
    )
    replay_executor = ReplayExecutor(
        plan_executor=plan_executor,
        contract=active_contract,
    )
    runner = GroundTruthRunner(
        assistant_service=secure_service,
        assistant_services=assistant_services,
        plan_executor=plan_executor,
        replay_executor=replay_executor,
        contract=active_contract,
        plans=benchmark_plans,
        provider_usage_tracker=usage_tracker,
    )
    return BenchmarkRuntime(
        runner=runner,
        cases=ground_truth_cases,
        contract=active_contract,
        plans=benchmark_plans,
        provider=provider,
        retriever=shared_retriever,
        provider_usage_tracker=usage_tracker,
        runtime_snapshot=_runtime_snapshot(provider, shared_retriever),
    )


__all__ = ["BenchmarkRuntime", "build_benchmark_runtime"]
