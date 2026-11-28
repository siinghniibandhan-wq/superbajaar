from decimal import Decimal

import pytest

from app.services.promotions import calculate_promotion_discount


def test_percent_promotion_rounds_to_paise_and_caps():
    assert calculate_promotion_discount(
        subtotal="999.99", discount_type="percent", discount_value="15",
        minimum_subtotal="500", maximum_discount="100",
    ) == Decimal("100.00")


def test_fixed_promotion_cannot_exceed_subtotal():
    assert calculate_promotion_discount(
        subtotal="45.00", discount_type="fixed", discount_value="100",
    ) == Decimal("45.00")


def test_promotion_rejects_minimum_subtotal_not_met():
    with pytest.raises(ValueError, match="minimum subtotal"):
        calculate_promotion_discount(
            subtotal="99", discount_type="fixed", discount_value="10", minimum_subtotal="100",
        )


@pytest.mark.parametrize("discount_type,value", [("percent", "0"), ("percent", "101"), ("fixed", "0"), ("unknown", "1")])
def test_promotion_rejects_invalid_discount(discount_type, value):
    with pytest.raises(ValueError):
        calculate_promotion_discount(subtotal="100", discount_type=discount_type, discount_value=value)


def test_percentage_discount_round_half_up():
    assert calculate_promotion_discount(
        subtotal="0.05", discount_type="percent", discount_value="10",
    ) == Decimal("0.01")
