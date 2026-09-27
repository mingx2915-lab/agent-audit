import pytest
from pydantic import ValidationError

from agent_audit_api.security_contract import (
    ContractEvaluator,
    ContractRole,
    ResourceRule,
    SecurityContract,
    ToolRule,
)


def _contract(
    *,
    resource_rules: list[ResourceRule] | None = None,
    tool_rules: list[ToolRule] | None = None,
) -> SecurityContract:
    return SecurityContract(
        id="contract_test",
        name="测试 Security Contract",
        version=1,
        roles=[
            ContractRole(id="sales", display_name="销售"),
            ContractRole(id="employee", display_name="员工"),
            ContractRole(id="admin", display_name="管理员"),
        ],
        resource_rules=resource_rules or [],
        tool_rules=tool_rules or [],
    )


def test_resource_rule_requires_all_labels_role_and_matching_owner() -> None:
    evaluator = ContractEvaluator(
        _contract(
            resource_rules=[
                ResourceRule(
                    id="resource_customer_owner",
                    description="销售只能读取本人客户资料",
                    match_labels=["customer", "confidential"],
                    allowed_roles=["sales"],
                    require_owner_match=True,
                )
            ]
        )
    )

    allowed = evaluator.authorize_resource(
        actor_role="sales",
        actor_id="sales_001",
        resource_labels=["SYNTHETIC", "customer", "confidential"],
        resource_owner_id="sales_001",
    )
    missing_label = evaluator.authorize_resource(
        actor_role="sales",
        actor_id="sales_001",
        resource_labels=["customer"],
        resource_owner_id="sales_001",
    )
    wrong_role = evaluator.authorize_resource(
        actor_role="employee",
        actor_id="employee_001",
        resource_labels=["customer", "confidential"],
        resource_owner_id="sales_001",
    )
    wrong_owner = evaluator.authorize_resource(
        actor_role="sales",
        actor_id="sales_002",
        resource_labels=["customer", "confidential"],
        resource_owner_id="sales_001",
    )

    assert allowed.allowed is True
    assert allowed.rule_id == "resource_customer_owner"
    assert missing_label.allowed is False
    assert wrong_role.allowed is False
    assert wrong_owner.allowed is False


def test_resource_authorization_uses_contract_attributes_not_document_roles() -> None:
    evaluator = ContractEvaluator(
        _contract(
            resource_rules=[
                ResourceRule(
                    id="resource_employee_public",
                    description="员工可读带有 handbook 标签的资源",
                    match_labels=["handbook"],
                    allowed_roles=["employee"],
                    require_owner_match=False,
                )
            ]
        )
    )

    # The evaluator receives only normalized labels/owner metadata.  No
    # document.allowed_roles value participates in this decision.
    decision = evaluator.authorize_resource(
        actor_role="employee",
        actor_id="employee_001",
        resource_labels=["handbook", "confidential"],
        resource_owner_id="sales_001",
    )

    assert decision.allowed is True
    assert decision.rule_id == "resource_employee_public"


def test_multiple_resource_rules_allow_when_any_one_is_complete() -> None:
    evaluator = ContractEvaluator(
        _contract(
            resource_rules=[
                ResourceRule(
                    id="resource_sales_owner",
                    description="销售本人客户资料",
                    match_labels=["customer", "confidential"],
                    allowed_roles=["sales"],
                    require_owner_match=True,
                ),
                ResourceRule(
                    id="resource_employee_customer",
                    description="员工公共客户资料",
                    match_labels=["customer", "public"],
                    allowed_roles=["employee"],
                    require_owner_match=False,
                ),
            ]
        )
    )

    decision = evaluator.authorize_resource(
        actor_role="employee",
        actor_id="employee_001",
        resource_labels=["customer", "public"],
        resource_owner_id="sales_001",
    )

    assert decision.allowed is True
    assert decision.rule_id == "resource_employee_customer"


def test_resource_without_complete_matching_rule_is_denied() -> None:
    evaluator = ContractEvaluator(
        _contract(
            resource_rules=[
                ResourceRule(
                    id="resource_finance_manager",
                    description="财务经理预算资料",
                    match_labels=["finance", "confidential"],
                    allowed_roles=["admin"],
                    require_owner_match=False,
                )
            ]
        )
    )

    decision = evaluator.authorize_resource(
        actor_role="sales",
        actor_id="sales_001",
        resource_labels=["customer", "confidential"],
        resource_owner_id=None,
    )

    assert decision.allowed is False
    assert decision.rule_id is None


def test_tool_rule_requires_tool_name_action_role_and_owner() -> None:
    evaluator = ContractEvaluator(
        _contract(
            tool_rules=[
                ToolRule(
                    id="tool_customer_owner_read",
                    description="销售只能读取本人客户记录",
                    tool_name="mock_customer_lookup",
                    action="read",
                    allowed_roles=["sales"],
                    require_owner_match=True,
                )
            ]
        )
    )

    allowed = evaluator.authorize_tool(
        actor_role="sales",
        actor_id="sales_001",
        tool_name="mock_customer_lookup",
        action="read",
        resource_owner_id="sales_001",
    )
    wrong_tool = evaluator.authorize_tool(
        actor_role="sales",
        actor_id="sales_001",
        tool_name="other_tool",
        action="read",
        resource_owner_id="sales_001",
    )
    wrong_action = evaluator.authorize_tool(
        actor_role="sales",
        actor_id="sales_001",
        tool_name="mock_customer_lookup",
        action="export",
        resource_owner_id="sales_001",
    )
    wrong_role = evaluator.authorize_tool(
        actor_role="employee",
        actor_id="employee_001",
        tool_name="mock_customer_lookup",
        action="read",
        resource_owner_id="sales_001",
    )
    wrong_owner = evaluator.authorize_tool(
        actor_role="sales",
        actor_id="sales_002",
        tool_name="mock_customer_lookup",
        action="read",
        resource_owner_id="sales_001",
    )

    assert allowed.allowed is True
    assert allowed.rule_id == "tool_customer_owner_read"
    assert wrong_tool.allowed is False
    assert wrong_action.allowed is False
    assert wrong_role.allowed is False
    assert wrong_owner.allowed is False


def test_multiple_tool_rules_allow_when_any_one_is_complete() -> None:
    evaluator = ContractEvaluator(
        _contract(
            tool_rules=[
                ToolRule(
                    id="tool_sales_owner_read",
                    description="销售读取本人客户",
                    tool_name="mock_customer_lookup",
                    action="read",
                    allowed_roles=["sales"],
                    require_owner_match=True,
                ),
                ToolRule(
                    id="tool_admin_any_read",
                    description="管理员读取客户",
                    tool_name="mock_customer_lookup",
                    action="read",
                    allowed_roles=["admin"],
                    require_owner_match=False,
                ),
            ]
        )
    )

    decision = evaluator.authorize_tool(
        actor_role="admin",
        actor_id="admin_001",
        tool_name="mock_customer_lookup",
        action="read",
        resource_owner_id="sales_001",
    )

    assert decision.allowed is True
    assert decision.rule_id == "tool_admin_any_read"


@pytest.mark.parametrize(
    "bad_update",
    [
        {
            "id": "contract_bad",
            "name": "重复资源规则",
            "version": 1,
            "roles": [{"id": "sales", "displayName": "销售"}],
            "resourceRules": [
                {
                    "id": "duplicate",
                    "description": "A",
                    "matchLabels": ["customer"],
                    "allowedRoles": ["sales"],
                    "requireOwnerMatch": False,
                },
                {
                    "id": "duplicate",
                    "description": "B",
                    "matchLabels": ["contract"],
                    "allowedRoles": ["sales"],
                    "requireOwnerMatch": False,
                },
            ],
            "toolRules": [],
        },
        {
            "id": "contract_bad",
            "name": "未知角色引用",
            "version": 1,
            "roles": [{"id": "sales", "displayName": "销售"}],
            "resourceRules": [
                {
                    "id": "unknown_role",
                    "description": "引用未声明角色",
                    "matchLabels": ["customer"],
                    "allowedRoles": ["hr"],
                    "requireOwnerMatch": False,
                }
            ],
            "toolRules": [],
        },
    ],
)
def test_contract_model_rejects_duplicate_rule_ids_and_unknown_roles(
    bad_update: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SecurityContract.model_validate(bad_update)
