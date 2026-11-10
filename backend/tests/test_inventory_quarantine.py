from decimal import Decimal

import pytest

from app.services.inventory_quarantine import calculate_quarantine_release


def test_quarantine_release_moves_only_the_requested_quantity_to_accepted():
    result = calculate_quarantine_release(Decimal("8.500"), Decimal("3.250"))
    assert result == {
        "remaining_quarantined": Decimal("5.250"),
        "accepted_quantity": Decimal("3.250"),
    }


def test_quarantine_release_rejects_quantity_above_quarantined_balance():
    with pytest.raises(ValueError, match="exceeds the quarantined quantity"):
        calculate_quarantine_release(Decimal("2.000"), Decimal("2.001"))


def test_quarantine_release_rejects_zero_or_negative_quantities():
    with pytest.raises(ValueError, match="must be greater than zero"):
        calculate_quarantine_release(Decimal("2.000"), Decimal("0"))


def test_expired_stock_transfer_allocates_oldest_layers_first_and_respects_partial_quantity():
    from app.services.inventory_quarantine import plan_quarantine_transfer
    layers = [
        {"id": 10, "remaining_quantity": "2.000"},
        {"id": 11, "remaining_quantity": "3.000"},
    ]
    assert plan_quarantine_transfer(layers, Decimal("3.500")) == [
        {"layer_id": 10, "quantity": Decimal("2.000")},
        {"layer_id": 11, "quantity": Decimal("1.500")},
    ]


def test_expired_stock_transfer_rejects_request_above_available_expired_layers():
    from app.services.inventory_quarantine import plan_quarantine_transfer
    with pytest.raises(ValueError, match="exceeds available expired stock"):
        plan_quarantine_transfer([{"id": 10, "remaining_quantity": "1.000"}], Decimal("1.001"))


def test_expired_stock_transfer_rejects_empty_expired_layer_set():
    from app.services.inventory_quarantine import plan_quarantine_transfer
    with pytest.raises(ValueError, match="No expired stock remains"):
        plan_quarantine_transfer([], None)


def test_customer_return_quarantine_release_excludes_expired_layers():
    from app.services.inventory_quarantine import split_releasable_layers
    layers = [
        {"id": 1, "remaining_quantity": "2.000", "is_releasable": True},
        {"id": 2, "remaining_quantity": "1.500", "is_releasable": False},
    ]
    releasable, expired_quantity = split_releasable_layers(layers)
    assert [row["id"] for row in releasable] == [1]
    assert expired_quantity == Decimal("1.500")


def test_customer_return_quarantine_release_fails_when_all_remaining_layers_are_expired():
    from app.services.inventory_quarantine import split_releasable_layers
    releasable, expired_quantity = split_releasable_layers([
        {"id": 2, "remaining_quantity": "1.500", "is_releasable": False},
    ])
    assert releasable == []
    assert expired_quantity == Decimal("1.500")
}
