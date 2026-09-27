"""Unit coverage for F-023 structured Contract and Planner previews."""

from __future__ import annotations

from copy import deepcopy
from agent_audit_api.demo_data import load_demo_data
from agent_audit_api.planning import (
    ContractAttackPlanner,
    _contract_field_changes,
    _plan_changes,
    build_security_contract_preview,
)
from agent_audit_api.security_contract import SecurityContract, load_security_contract
from agent_audit_api.tools import MockCustomerExportTool, MockCustomerTool, MockMailTool


def _planner(contract: SecurityContract) -> ContractAttackPlanner:
    data = load_demo_data()
    return ContractAttackPlanner(
        contract=contract,
        actors=data.actors,
        documents=data.documents,
        customers=data.customers,
        customer_tool=MockCustomerTool(data.customers),
        mail_tool=MockMailTool(),
        export_tool=MockCustomerExportTool(data.customers),
    )


def _candidate_with_collection_and_scalar_changes() -> SecurityContract:
    payload = load_security_contract().model_dump(mode="json", by_alias=True)
    payload["name"] = "候选 Contract"
    payload["roles"] = list(reversed(payload["roles"]))
    payload["resourceRules"] = [
        rule
        for rule in payload["resourceRules"]
        if rule["id"] != "resource_public_all"
    ]
    payload["resourceRules"].append(
        {
            "id": "resource_preview_added",
            "description": "F-023 预览新增规则",
            "matchLabels": ["public"],
            "allowedRoles": ["admin"],
            "requireOwnerMatch": False,
        }
    )
    payload["toolRules"] = [
        (
            {
                **rule,
                "allowedRoles": ["sales", "admin"],
            }
            if rule["id"] == "tool_customer_owner_read"
            else rule
        )
        for rule in payload["toolRules"]
    ]
    return SecurityContract.model_validate(payload)


def test_structured_contract_diff_is_id_stable_and_reports_all_change_kinds() -> None:
    active = load_security_contract()
    candidate = _candidate_with_collection_and_scalar_changes()

    changes = _contract_field_changes(active, candidate)

    assert [(change.path, change.kind) for change in changes] == [
        ("name", "changed"),
        ("resourceRules[resource_preview_added]", "added"),
        ("resourceRules[resource_public_all]", "removed"),
        ("toolRules[tool_customer_owner_read].allowedRoles", "changed"),
    ]
    by_path = {change.path: change for change in changes}
    assert by_path["name"].before_value == active.name
    assert by_path["name"].after_value == "候选 Contract"
    assert by_path["resourceRules[resource_preview_added]"].before_value is None
    assert by_path["resourceRules[resource_preview_added]"].after_value["id"] == (
        "resource_preview_added"
    )
    assert by_path["resourceRules[resource_public_all]"].after_value is None
    assert by_path["resourceRules[resource_public_all]"].before_value["id"] == (
        "resource_public_all"
    )
    assert by_path["toolRules[tool_customer_owner_read].allowedRoles"].before_value == [
        "sales"
    ]
    assert by_path["toolRules[tool_customer_owner_read].allowedRoles"].after_value == [
        "sales",
        "admin",
    ]


def test_reordering_roles_and_rules_does_not_create_structural_noise() -> None:
    active = load_security_contract()
    payload = active.model_dump(mode="json", by_alias=True)
    payload["roles"] = list(reversed(payload["roles"]))
    payload["resourceRules"] = list(reversed(payload["resourceRules"]))
    payload["toolRules"] = list(reversed(payload["toolRules"]))
    payload["sinkRules"] = list(reversed(payload["sinkRules"]))
    candidate = SecurityContract.model_validate(payload)

    assert _contract_field_changes(active, candidate) == []


def test_preview_plan_impact_comes_from_planner_outputs() -> None:
    active = load_security_contract()
    candidate = deepcopy(active.model_dump(mode="json", by_alias=True))
    owner_rule = next(
        rule
        for rule in candidate["resourceRules"]
        if rule["id"] == "resource_customer_owner"
    )
    owner_rule["requireOwnerMatch"] = False
    candidate_contract = SecurityContract.model_validate(candidate)

    current_plans = _planner(active).plan()
    candidate_plans = _planner(candidate_contract).plan()
    preview = build_security_contract_preview(
        active_contract=active,
        candidate_contract=candidate_contract,
        current_plans=current_plans,
        candidate_plans=candidate_plans,
    )

    assert preview.current_plans == list(current_plans)
    assert preview.candidate_plans == list(candidate_plans)
    assert [change.model_dump() for change in preview.plan_changes] == [
        {
            "plan_id": "plan_resource_customer_owner",
            "kind": "removed",
            "basis_type": "resource_owner_scope",
            "basis_rule_id": "resource_customer_owner",
        }
    ]
    assert _plan_changes(current_plans, candidate_plans) == preview.plan_changes


def test_plan_change_comparison_is_stable_by_plan_id() -> None:
    active = load_security_contract()
    current = list(_planner(active).plan())
    candidate = list(reversed(current))
    candidate[0] = candidate[0].model_copy(update={"message": "候选消息"})

    changes = _plan_changes(current, candidate)

    assert len(changes) == 1
    assert changes[0].plan_id == candidate[0].id
    assert changes[0].kind == "changed"
    assert changes[0].basis_type == candidate[0].basis_type
    assert changes[0].basis_rule_id == candidate[0].basis_rule_id
