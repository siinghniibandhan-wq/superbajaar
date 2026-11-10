from decimal import Decimal
import pytest

from app.services.landed_cost_allocation import allocate_landed_cost, split_layer_adjustment


def test_allocates_freight_by_explicit_line_value_and_reconciles_rounding():
    lines = [
        {"receipt_line_id": 11, "quantity": Decimal("2"), "unit_cost": Decimal("10.00")},
        {"receipt_line_id": 12, "quantity": Decimal("1"), "unit_cost": Decimal("10.00")},
    ]

    result = allocate_landed_cost(lines, amount=Decimal("1.00"), basis="line_value", adjustment_type="charge")

    assert result["total"] == Decimal("1.00")
    assert [row["allocated_amount"] for row in result["allocations"]] == [Decimal("0.67"), Decimal("0.33")]


def test_requires_explicit_supported_basis_and_never_defaults():
    with pytest.raises(ValueError, match="basis"):
        allocate_landed_cost([], amount=Decimal("1.00"), basis=None, adjustment_type="charge")
    with pytest.raises(ValueError, match="basis"):
        allocate_landed_cost([], amount=Decimal("1.00"), basis="weight", adjustment_type="charge")


def test_rejects_negative_or_ineligible_receipt_lines():
    with pytest.raises(ValueError, match="positive"):
        allocate_landed_cost([{"receipt_line_id": 1, "quantity": Decimal("0"), "unit_cost": Decimal("10")}], amount=Decimal("1"), basis="quantity", adjustment_type="charge")
    with pytest.raises(ValueError, match="non-negative"):
        allocate_landed_cost([{"receipt_line_id": 1, "quantity": Decimal("1"), "unit_cost": Decimal("10")}], amount=Decimal("-1"), basis="quantity", adjustment_type="charge")


def test_discount_cannot_reduce_a_receipt_line_below_zero_cost():
    lines = [{"receipt_line_id": 1, "quantity": Decimal("1"), "unit_cost": Decimal("2.00")}]
    with pytest.raises(ValueError, match="exceeds"):
        allocate_landed_cost(lines, amount=Decimal("2.01"), basis="line_value", adjustment_type="discount")


def test_splits_adjustment_between_remaining_and_consumed_quantity():
    split = split_layer_adjustment(
        allocated_amount=Decimal("1.00"), received_quantity=Decimal("3"),
        consumed_quantity=Decimal("1"),
    )
    assert split == {"consumed_amount": Decimal("0.33"), "remaining_amount": Decimal("0.67")}


def test_quantity_basis_discount_redistributes_amount_capped_by_low_value_line():
    lines = [
        {"receipt_line_id": 21, "quantity": Decimal("1"), "unit_cost": Decimal("1.00")},
        {"receipt_line_id": 22, "quantity": Decimal("1"), "unit_cost": Decimal("9.00")},
    ]
    result = allocate_landed_cost(
        lines, amount=Decimal("4.00"), basis="quantity", adjustment_type="discount"
    )
    assert [row["allocated_amount"] for row in result["allocations"]] == [
        Decimal("1.00"), Decimal("3.00")
    ]
    assert result["total"] == Decimal("4.00")


def test_rejects_duplicate_receipt_line_ids_to_prevent_overwritten_allocations():
    duplicate_lines = [
        {"receipt_line_id": 7, "quantity": Decimal("1"), "unit_cost": Decimal("2")},
        {"receipt_line_id": 7, "quantity": Decimal("1"), "unit_cost": Decimal("3")},
    ]
    with pytest.raises(ValueError, match="unique"):
        allocate_landed_cost(
            duplicate_lines, amount=Decimal("1"), basis="line_value", adjustment_type="charge"
        )
