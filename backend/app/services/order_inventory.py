"""Order-linked stock reservation helpers using the existing inventory ledger.

This is an additive application-level use of inventory_balances and
inventory_movements. It does not alter inventory schema or legacy movement
semantics. Callers must use the same database transaction as the order change.
"""
from decimal import Decimal


ORDER_RESERVATION_REF = "order_reservation"
ORDER_FULFILMENT_REF = "order_fulfilment"


def reserve_order_stock(conn, order_id: int, delivery_pin: str | None, lines: list[tuple[int, int]], location_id: int | None = None):
    """Reserve every line at one eligible location, or reserve none.

    Website/manual orders with a delivery PIN select a matching location.
    POS orders pass the staff-selected location; a PIN, when supplied, must
    also match that location. Orders with neither PIN nor location retain the
    legacy no-reservation behaviour.
    """
    if not delivery_pin and location_id is None:
        return None

    variant_ids = [variant_id for variant_id, _ in lines]
    if location_id is not None:
        if delivery_pin:
            locations = conn.execute(
                "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE AND pin_code=%s FOR UPDATE",
                (location_id, delivery_pin),
            ).fetchall()
        else:
            locations = conn.execute(
                "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR UPDATE",
                (location_id,),
            ).fetchall()
    else:
        locations = conn.execute(
            "SELECT id FROM stock_locations WHERE is_active=TRUE AND pin_code=%s ORDER BY id FOR UPDATE",
            (delivery_pin,),
        ).fetchall()

    for location in locations:
        balances = conn.execute(
            "SELECT variant_id, on_hand, reserved FROM inventory_balances "
            "WHERE location_id=%s AND variant_id=ANY(%s) ORDER BY variant_id FOR UPDATE",
            (location["id"], variant_ids),
        ).fetchall()
        by_variant = {int(row["variant_id"]): row for row in balances}
        if any(variant_id not in by_variant for variant_id in variant_ids):
            continue
        if any(
            Decimal(str(by_variant[variant_id]["on_hand"])) -
            Decimal(str(by_variant[variant_id]["reserved"])) < quantity
            for variant_id, quantity in lines
        ):
            continue

        for variant_id, quantity in lines:
            conn.execute(
                "UPDATE inventory_balances SET reserved=reserved+%s, updated_at=now() "
                "WHERE variant_id=%s AND location_id=%s",
                (quantity, variant_id, location["id"]),
            )
            conn.execute(
                "INSERT INTO inventory_movements "
                "(variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
                "VALUES (%s,%s,'reservation',%s,%s,%s,%s)",
                (variant_id, location["id"], quantity, ORDER_RESERVATION_REF, str(order_id),
                 f"Order reservation {order_id}"),
            )
        return int(location["id"])

    if location_id is not None:
        raise ValueError("Selected stock location is inactive or does not serve the delivery PIN")
    raise ValueError("Insufficient stock: no single active location serving this delivery PIN can fulfil the complete order")

def _outstanding_order_reservations(conn, order_id: int):
    rows = conn.execute(
        "SELECT variant_id, location_id, "
        "SUM(CASE WHEN movement_type='reservation' AND reference_type=%s THEN quantity "
        "WHEN movement_type='release' AND reference_type=%s THEN -quantity "
        "WHEN movement_type='sale' AND reference_type=%s THEN -quantity ELSE 0 END) AS outstanding "
        "FROM inventory_movements WHERE reference_id=%s AND reference_type IN (%s,%s) "
        "GROUP BY variant_id, location_id HAVING SUM(CASE "
        "WHEN movement_type='reservation' AND reference_type=%s THEN quantity "
        "WHEN movement_type='release' AND reference_type=%s THEN -quantity "
        "WHEN movement_type='sale' AND reference_type=%s THEN -quantity ELSE 0 END) > 0 "
        "ORDER BY location_id, variant_id",
        (ORDER_RESERVATION_REF, ORDER_RESERVATION_REF, ORDER_FULFILMENT_REF,
         str(order_id), ORDER_RESERVATION_REF, ORDER_FULFILMENT_REF,
         ORDER_RESERVATION_REF, ORDER_RESERVATION_REF, ORDER_FULFILMENT_REF),
    ).fetchall()
    return rows


def release_order_stock(conn, order_id: int):
    """Release only the still-outstanding reservation quantity; safe to retry."""
    rows = _outstanding_order_reservations(conn, order_id)
    for row in rows:
        quantity = Decimal(str(row["outstanding"]))
        updated = conn.execute(
            "UPDATE inventory_balances SET reserved=reserved-%s, updated_at=now() "
            "WHERE variant_id=%s AND location_id=%s AND reserved >= %s RETURNING variant_id",
            (quantity, row["variant_id"], row["location_id"], quantity),
        ).fetchone()
        if updated is None:
            raise ValueError("Reserved inventory changed before cancellation; reservation was not released")
        conn.execute(
            "INSERT INTO inventory_movements "
            "(variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
            "VALUES (%s,%s,'release',%s,%s,%s,%s)",
            (row["variant_id"], row["location_id"], quantity, ORDER_RESERVATION_REF,
             str(order_id), f"Order reservation release {order_id}"),
        )
    return len(rows)


def dispatch_order_stock(conn, order_id: int, requested_quantities: dict[int, int] | None = None):
    """Consume all or selected outstanding quantities, supporting partial dispatch."""
    rows = _outstanding_order_reservations(conn, order_id)
    available_by_variant = {}
    for row in rows:
        variant_id = int(row["variant_id"])
        available_by_variant[variant_id] = available_by_variant.get(variant_id, Decimal("0")) + Decimal(str(row["outstanding"]))
    if requested_quantities is not None:
        if not requested_quantities or any(qty <= 0 for qty in requested_quantities.values()):
            raise ValueError("Partial dispatch quantities must be positive")
        for variant_id, quantity in requested_quantities.items():
            if Decimal(str(quantity)) > available_by_variant.get(int(variant_id), Decimal("0")):
                raise ValueError(f"Dispatch quantity exceeds the outstanding reservation for variant {variant_id}")
    remaining_to_dispatch = {int(k): Decimal(str(v)) for k, v in requested_quantities.items()} if requested_quantities is not None else None
    dispatched_rows = 0
    for row in rows:
        variant_id = int(row["variant_id"])
        outstanding = Decimal(str(row["outstanding"]))
        quantity = outstanding if remaining_to_dispatch is None else min(outstanding, remaining_to_dispatch.get(variant_id, Decimal("0")))
        if quantity <= 0:
            continue
        updated = conn.execute(
            "UPDATE inventory_balances SET on_hand=on_hand-%s, reserved=reserved-%s, updated_at=now() "
            "WHERE variant_id=%s AND location_id=%s AND on_hand >= %s AND reserved >= %s "
            "RETURNING variant_id",
            (quantity, quantity, row["variant_id"], row["location_id"], quantity, quantity),
        ).fetchone()
        if updated is None:
            raise ValueError("Reserved inventory changed before order dispatch; stock was not dispatched")
        conn.execute(
            "INSERT INTO inventory_movements "
            "(variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
            "VALUES (%s,%s,'sale',%s,%s,%s,%s)",
            (row["variant_id"], row["location_id"], quantity, ORDER_FULFILMENT_REF,
             str(order_id), f"Order dispatch {order_id}"),
        )
        dispatched_rows += 1
        if remaining_to_dispatch is not None:
            remaining_to_dispatch[variant_id] -= quantity
    if remaining_to_dispatch is not None and any(value > 0 for value in remaining_to_dispatch.values()):
        raise ValueError("Not all requested dispatch quantities could be allocated")
    return dispatched_rows


def order_reservation_locations(conn, order_id: int):
    """Return only locations with a positive, still-outstanding reservation."""
    rows = _outstanding_order_reservations(conn, order_id)
    return sorted({int(row["location_id"]) for row in rows})


def order_has_reservation(conn, order_id: int) -> bool:
    return bool(_outstanding_order_reservations(conn, order_id))


def ensure_order_can_be_cancelled(conn, order_id: int):
    """Prevent cancellation after any quantity has physically been dispatched."""
    if order_fulfilment_started(conn, order_id):
        raise ValueError("Order cannot be cancelled after any quantity has been dispatched")


def order_fulfilment_started(conn, order_id: int) -> bool:
    """Whether any quantity has already been consumed for this order."""
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM inventory_movements "
        "WHERE movement_type='sale' AND reference_type=%s AND reference_id=%s) AS started",
        (ORDER_FULFILMENT_REF, str(order_id)),
    ).fetchone()
    return bool(row["started"])
