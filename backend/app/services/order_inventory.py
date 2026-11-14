"""Order-linked stock reservation helpers using the existing inventory ledger.

This is an additive application-level use of inventory_balances and
inventory_movements. It does not alter inventory schema or legacy movement
semantics. Callers must use the same database transaction as the order change.
"""
from decimal import Decimal

from app.services.inventory_costing import allocate_cost_layers
from app.services.organisation_policy import validate_inventory_policy, resolve_minimum_remaining_shelf_life_days


ORDER_RESERVATION_REF = "order_reservation"
ORDER_FULFILMENT_REF = "order_fulfilment"


def reserve_order_stock(conn, order_id: int, delivery_pin: str | None, lines: list[tuple[int, int]], location_id: int | None = None, profile_routing: bool = False):
    """Reserve every line at one eligible location, or reserve none."""
    if not delivery_pin and location_id is None:
        raise ValueError("A verified delivery PIN or staff-selected stock location is required before reserving order stock")
    variant_ids = [variant_id for variant_id, _ in lines]
    if location_id is not None:
        if delivery_pin:
            locations = conn.execute(
                "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE AND is_fulfillable=TRUE AND pin_code=%s FOR UPDATE",
                (location_id, delivery_pin),
            ).fetchall()
        else:
            locations = conn.execute(
                "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE AND is_fulfillable=TRUE FOR UPDATE",
                (location_id,),
            ).fetchall()
    elif profile_routing:
        locations = conn.execute(
            "SELECT sl.id FROM stock_locations sl "
            "LEFT JOIN stock_location_profiles p ON p.location_id=sl.id "
            "WHERE sl.is_active=TRUE AND sl.is_fulfillable=TRUE "
            "AND COALESCE((p.profile_data->>'storefront_available')::boolean, TRUE)=TRUE "
            "AND COALESCE(p.profile_data->'service_pin_codes', "
            "CASE WHEN sl.pin_code IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(sl.pin_code) END) "
            "@> jsonb_build_array(%s::text) "
            "AND (COALESCE(jsonb_array_length(p.profile_data->'operating_days'),0)=0 "
            "OR p.profile_data->'operating_days' ? lower(to_char(now() AT TIME ZONE 'Asia/Kolkata','Dy'))) "
            "AND (p.profile_data->>'opening_time' IS NULL OR "
            "to_char(now() AT TIME ZONE 'Asia/Kolkata','HH24:MI') >= p.profile_data->>'opening_time') "
            "AND (p.profile_data->>'closing_time' IS NULL OR "
            "to_char(now() AT TIME ZONE 'Asia/Kolkata','HH24:MI') <= p.profile_data->>'closing_time') "
            "ORDER BY COALESCE((p.profile_data->>'routing_priority')::integer,100), sl.id FOR UPDATE OF sl",
            (delivery_pin,),
        ).fetchall()
    else:
        locations = conn.execute(
            "SELECT id FROM stock_locations WHERE is_active=TRUE AND is_fulfillable=TRUE AND pin_code=%s ORDER BY id FOR UPDATE",
            (delivery_pin,),
        ).fetchall()
    if location_id is not None and not locations:
        raise ValueError("Selected stock location is inactive or does not serve the delivery PIN")
    for location in locations:
        balances = conn.execute(
            "SELECT variant_id, on_hand, reserved FROM inventory_balances WHERE location_id=%s AND variant_id=ANY(%s) ORDER BY variant_id FOR UPDATE",
            (location["id"], variant_ids),
        ).fetchall()
        by_variant = {int(row["variant_id"]): row for row in balances}
        if any(variant_id not in by_variant for variant_id in variant_ids):
            continue
        if any(Decimal(str(by_variant[variant_id]["on_hand"])) - Decimal(str(by_variant[variant_id]["reserved"])) < quantity for variant_id, quantity in lines):
            continue
        for variant_id, quantity in lines:
            conn.execute("UPDATE inventory_balances SET reserved=reserved+%s, updated_at=now() WHERE variant_id=%s AND location_id=%s",
                         (quantity, variant_id, location["id"]))
            conn.execute(
                "INSERT INTO inventory_movements (variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
                "VALUES (%s,%s,'reservation',%s,%s,%s,%s)",
                (variant_id, location["id"], quantity, ORDER_RESERVATION_REF, str(order_id), f"Order reservation {order_id}"),
            )
        return int(location["id"])
    if location_id is not None:
        raise ValueError("Insufficient stock at the selected stock location to fulfil the complete order")
    raise ValueError("Insufficient stock: no single active location serving this delivery PIN can fulfil the complete order")


def _outstanding_order_reservations(conn, order_id: int):
    return conn.execute(
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
            "INSERT INTO inventory_movements (variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
            "VALUES (%s,%s,'release',%s,%s,%s,%s)",
            (row["variant_id"], row["location_id"], quantity, ORDER_RESERVATION_REF, str(order_id), f"Order reservation release {order_id}"),
        )
    return len(rows)


def cost_allocation_method(conn, variant_id: int, location_id: int) -> str:
    """Use FEFO when the location has expiry-managed layers; otherwise use FIFO."""
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM inventory_cost_layers WHERE variant_id=%s AND location_id=%s AND remaining_quantity>0 AND expiry_date IS NOT NULL) AS enabled",
        (variant_id, location_id),
    ).fetchone()
    return "fefo" if row and row["enabled"] else "fifo"


def _dispatch_shelf_life_policy(conn, location_id: int, variant_id: int) -> int | None:
    location = conn.execute("SELECT establishment_id FROM stock_locations WHERE id=%s FOR SHARE", (location_id,)).fetchone()
    if not location or location["establishment_id"] is None:
        raise ValueError("Assign the fulfilment stock location to an active establishment with an Inventory policy before dispatch")
    policy_rows = conn.execute(
        "SELECT * FROM organisation_policy_versions WHERE establishment_id=%s AND domain='inventory' "
        "AND status='active' AND effective_from<=CURRENT_DATE AND (effective_to IS NULL OR effective_to>=CURRENT_DATE) ORDER BY id FOR SHARE",
        (location["establishment_id"],),
    ).fetchall()
    if len(policy_rows) != 1:
        raise ValueError("No unique active Inventory policy applies to this dispatch location")
    config = policy_rows[0]["policy_config"]
    try:
        validate_inventory_policy(config)
    except ValueError as exc:
        raise ValueError(f"Inventory policy configuration is invalid: {exc}") from exc
    dispatch_policy = config["event_policies"].get("dispatch")
    if not isinstance(dispatch_policy, dict) or dispatch_policy.get("approval_required") is not False:
        raise ValueError("The active Inventory policy must explicitly permit direct dispatch; approval-required dispatch is not supported by this route")
    product = conn.execute("SELECT p.id,p.category_id FROM product_variants v JOIN products p ON p.id=v.product_id WHERE v.id=%s", (variant_id,)).fetchone()
    if product is None:
        raise ValueError("Product for dispatch variant was not found")
    return resolve_minimum_remaining_shelf_life_days(
        config, location_id=location_id, product_id=int(product["id"]),
        category_id=int(product["category_id"]) if product["category_id"] is not None else None,
    )


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
            "WHERE variant_id=%s AND location_id=%s AND on_hand >= %s AND reserved >= %s RETURNING variant_id",
            (quantity, quantity, row["variant_id"], row["location_id"], quantity, quantity),
        ).fetchone()
        if updated is None:
            raise ValueError("Reserved inventory changed before order dispatch; stock was not dispatched")
        movement = conn.execute(
            "INSERT INTO inventory_movements (variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
            "VALUES (%s,%s,'sale',%s,%s,%s,%s) RETURNING id",
            (row["variant_id"], row["location_id"], quantity, ORDER_FULFILMENT_REF, str(order_id), f"Order dispatch {order_id}"),
        ).fetchone()
        order_line = conn.execute("SELECT id FROM order_lines WHERE order_id=%s AND variant_id=%s FOR UPDATE", (order_id, row["variant_id"])).fetchone()
        if order_line is None:
            raise ValueError(f"Order line not found for dispatched variant {variant_id}")
        minimum_shelf_life_days = _dispatch_shelf_life_policy(conn, int(row["location_id"]), int(row["variant_id"]))
        allocation_method = cost_allocation_method(conn, int(row["variant_id"]), int(row["location_id"]))
        costing = allocate_cost_layers(conn, movement_id=movement["id"], variant_id=int(row["variant_id"]),
                                       location_id=int(row["location_id"]), quantity=quantity, method=allocation_method,
                                       allow_expired=False, minimum_remaining_shelf_life_days=minimum_shelf_life_days)
        conn.execute(
            "INSERT INTO inventory_order_issues (order_id,order_line_id,movement_id,location_id,fulfilment_reference,quantity,total_cost,allocation_method) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (order_id, order_line["id"], movement["id"], row["location_id"],
             f"order:{order_id}:movement:{movement['id']}", quantity, costing["total_cost"], costing["method"]),
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
        "SELECT EXISTS (SELECT 1 FROM inventory_movements WHERE movement_type='sale' AND reference_type=%s AND reference_id=%s) AS started",
        (ORDER_FULFILMENT_REF, str(order_id)),
    ).fetchone()
    return bool(row["started"])
