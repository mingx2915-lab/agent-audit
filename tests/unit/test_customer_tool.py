import pytest

from agent_audit_api.domain import CustomerRecord
from agent_audit_api.tools import MockCustomerTool


@pytest.fixture
def customer_tool() -> MockCustomerTool:
    return MockCustomerTool(
        [
            CustomerRecord(
                id="customer_001",
                name="星河制造",
                owner_id="sales_001",
                summary="续约客户，合同将在本季度复审。",
            )
        ]
    )


def test_mock_customer_tool_returns_synthetic_customer_record(
    customer_tool: MockCustomerTool,
) -> None:
    result = customer_tool.execute({"customerId": "customer_001"})

    assert result.success is True
    assert result.tool_name == "mock_customer_lookup"
    assert result.data == {
        "customerId": "customer_001",
        "name": "星河制造",
        "ownerId": "sales_001",
        "summary": "续约客户，合同将在本季度复审。",
    }
    assert result.summary


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"customerId": "customer_missing"},
        {"customerId": 1},
    ],
)
def test_mock_customer_tool_rejects_invalid_arguments(
    customer_tool: MockCustomerTool,
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        customer_tool.execute(arguments)
