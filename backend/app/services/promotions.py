"""Coupon/promotion validation and deterministic discount calculation."""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def calculate_promotion_discount(*, subtotal, discount_type, discount_value, minimum_subtotal=0, maximum_discount=None):
    subtotal = Decimal(str(subtotal)).quantize(CENT, rounding=ROUND_HALF_UP)
    value = Decimal(str(discount_value))
    minimum = Decimal(str(minimum_subtotal or 0))
    if subtotal < minimum:
        raise ValueError(f"Promotion requires a minimum subtotal of ₹{minimum:.2f}")
    if discount_type == "percent":
        if value <= 0 or value > 100:
            raise ValueError("Percentage discount must be between 0 and 100")
        discount = (subtotal * value / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        if maximum_discount is not None:
            discount = min(discount, Decimal(str(maximum_discount)))
    elif discount_type == "fixed":
        if value <= 0:
            raise ValueError("Fixed discount must be greater than zero")
        discount = value.quantize(CENT, rounding=ROUND_HALF_UP)
    else:
        raise ValueError("Unsupported promotion type")
    return min(max(discount, Decimal("0.00")), subtotal).quantize(CENT, rounding=ROUND_HALF_UP)
