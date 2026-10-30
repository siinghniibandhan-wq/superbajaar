"""Order-linked stock reservation helpers using the existing inventory ledger.

This is an additive application-level use of inventory_balances and
inventory_movements. It does not alter inventory schema or legacy movement
semantics. Callers must use the same database transaction as the order change.
"""
from decimal import Decimal


ORDER_RESERVATION_REF = "order_reservation"
ORDER_FULFILMENT_REF = "order_fulfilment"


def reserve_order_stock(conn, order_id: int, delivery_pin: str | None, lines: list[tuple[int, int]]):
    """Reserve every line at one active PIN-matched location, or reserve none.

    Orders without a delivery PIN retain the legacy no-reservation behaviour.
    Existing balance rows are locked in a deterministic order to prevent
    overselling under concurrent checkouts.
    """
    if not delivery_pin:
        return None

    variant_ids = [variant_id for variant_id, _ in lines]
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

    raise ValueError("Insufficient stock at an active location serving this delivery PIN")


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
        conn.execute(
            "UPDATE inventory_balances SET reserved=reserved-%s, updated_at=now() "
            "WHERE variant_id=%s AND location_id=%s AND reserved >= %s",
            (quantity, row["variant_id"], row["location_id"], quantity),
        )
        conn.execute(
            "INSERT INTO inventory_movements "
            "(variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
            "VALUES (%s,%s,'release',%s,%s,%s,%s)",
            (row["variant_id"], row["location_id"], quantity, ORDER_RESERVATION_REF,
             str(order_id), f"Order reservation release {order_id}"),
        )
    return len(rows)


def dispatch_order_stock(conn, order_id: int):
    """Consume outstanding order reservations once, reducing on-hand and reserved."""
    rows = _outstanding_order_reservations(conn, order_id)
    for row in rows:
        quantity = Decimal(str(row["outstanding"]))
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
    return len(rows)
