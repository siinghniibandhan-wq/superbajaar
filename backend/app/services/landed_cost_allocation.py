"""Pure, preview-only landed-cost allocation primitives.

Persistence and accounting posting intentionally remain behind the approved
Database Owner schema contract. Callers must provide an explicit allocation basis.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Any

CENT = Decimal("0.01")
ZERO = Decimal("0")
SUPPORTED_BASES = {"line_value", "quantity"}


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be a valid decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def allocate_landed_cost(
    receipt_lines: Iterable[Mapping[str, Any]], *, amount: Decimal,
    basis: str | None, adjustment_type: str,
) -> dict:
    """Allocate a header charge/discount across accepted receipt lines.

    Supported bases are explicitly selected `line_value` and `quantity`.
    Rounding residual is assigned deterministically to the final line. This is
    a calculation only: it does not persist cost layers or create a voucher.
    """
    if basis not in SUPPORTED_BASES:
        raise ValueError("An explicit supported allocation basis is required")
    if adjustment_type not in {"charge", "discount"}:
        raise ValueError("adjustment_type must be charge or discount")
    total = _decimal(amount, "amount")
    if total < ZERO:
        raise ValueError("amount must be non-negative")

    normalized = []
    seen_line_ids = set()
    for line in receipt_lines:
        line_id = line.get("receipt_line_id")
        if line_id is None:
            raise ValueError("Every eligible receipt line requires receipt_line_id")
        if line_id in seen_line_ids:
            raise ValueError("receipt_line_id values must be unique")
        seen_line_ids.add(line_id)
        quantity = _decimal(line.get("quantity"), "quantity")
        unit_cost = _decimal(line.get("unit_cost"), "unit_cost")
        if quantity <= ZERO or unit_cost < ZERO:
            raise ValueError("Eligible receipt lines require positive quantity and non-negative unit cost")
        value = _money(quantity * unit_cost)
        weight = value if basis == "line_value" else quantity
        if weight <= ZERO:
            raise ValueError("Every eligible receipt line must have a positive allocation basis")
        normalized.append({"receipt_line_id": line_id, "quantity": quantity,
                           "unit_cost": unit_cost, "line_value": value, "weight": weight})

    if not normalized:
        if total == ZERO:
            return {"basis": basis, "adjustment_type": adjustment_type,
                    "total": ZERO.quantize(CENT), "allocations": []}
        raise ValueError("At least one eligible accepted receipt line is required")

    if adjustment_type == "discount" and total > sum((line["line_value"] for line in normalized), ZERO):
        raise ValueError("discount exceeds eligible received goods value")

    total_weight = sum((line["weight"] for line in normalized), ZERO)
    allocated_by_id = {}
    if adjustment_type == "charge":
        allocated_so_far = ZERO
        for index, line in enumerate(normalized):
            if index == len(normalized) - 1:
                allocated = _money(total - allocated_so_far)
            else:
                allocated = _money(total * line["weight"] / total_weight)
                allocated_so_far += allocated
            allocated_by_id[line["receipt_line_id"]] = allocated
    else:
        # Discounts are capped per receipt line at its goods value. If a
        # low-value line reaches zero cost, redistribute its excess over the
        # remaining eligible lines using the selected basis.
        remaining = total
        active = list(normalized)
        while active and remaining > ZERO:
            weight_sum = sum((line["weight"] for line in active), ZERO)
            round_left = remaining
            next_active = []
            for index, line in enumerate(active):
                prior = allocated_by_id.get(line["receipt_line_id"], ZERO)
                capacity = _money(line["line_value"] - prior)
                if index == len(active) - 1:
                    proposed = _money(round_left)
                else:
                    proposed = min(round_left, _money(remaining * line["weight"] / weight_sum))
                assigned = min(proposed, capacity)
                allocated_by_id[line["receipt_line_id"]] = prior + assigned
                round_left = _money(round_left - assigned)
                if assigned < capacity:
                    next_active.append(line)
            if round_left == remaining:
                raise ValueError("discount cannot be allocated to eligible receipt lines")
            remaining = round_left
            active = next_active
        if remaining != ZERO:
            raise ValueError("discount exceeds eligible received goods value")

    allocations = [{
        "receipt_line_id": line["receipt_line_id"],
        "basis_value": line["weight"],
        "allocated_amount": _money(allocated_by_id.get(line["receipt_line_id"], ZERO)),
    } for line in normalized]

    return {"basis": basis, "adjustment_type": adjustment_type,
            "total": _money(sum((row["allocated_amount"] for row in allocations), ZERO)),
            "allocations": allocations}


def split_layer_adjustment(*, allocated_amount: Decimal, received_quantity: Decimal,
                           consumed_quantity: Decimal) -> dict:
    """Split an adjustment into consumed COGS and remaining-stock portions."""
    amount = _decimal(allocated_amount, "allocated_amount")
    received = _decimal(received_quantity, "received_quantity")
    consumed = _decimal(consumed_quantity, "consumed_quantity")
    if amount < ZERO or received <= ZERO or consumed < ZERO or consumed > received:
        raise ValueError("Adjustment and quantities must be non-negative, with 0 <= consumed <= received")
    consumed_amount = _money(amount * consumed / received)
    if consumed == received:
        consumed_amount = _money(amount)
    remaining_amount = _money(amount - consumed_amount)
    return {"consumed_amount": consumed_amount, "remaining_amount": remaining_amount}
