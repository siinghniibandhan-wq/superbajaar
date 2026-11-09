"""Transactional FIFO/FEFO inventory cost-layer primitives."""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def create_cost_layer(
    conn, *, movement_id: int, variant_id: int, location_id: int,
    quantity: Decimal, unit_cost: Decimal, purchase_order_line_id: int | None = None,
    goods_receipt_line_id: int | None = None, batch_code: str | None = None,
    expiry_date=None, manufacture_date=None, source_layer_id: int | None = None,
):
    """Create one cost layer for one receipt/opening/transfer-in movement."""
    return conn.execute(
        "INSERT INTO inventory_cost_layers "
        "(variant_id,location_id,receipt_movement_id,purchase_order_line_id,goods_receipt_line_id,source_layer_id,"
        "batch_code,manufacture_date,expiry_date,received_quantity,remaining_quantity,unit_cost) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "RETURNING id,variant_id,location_id,goods_receipt_line_id,batch_code,manufacture_date,expiry_date,"
        "received_quantity,remaining_quantity,unit_cost",
        (variant_id, location_id, movement_id, purchase_order_line_id, goods_receipt_line_id, source_layer_id,
         batch_code, manufacture_date, expiry_date, quantity, quantity, unit_cost),
    ).fetchone()


def allocate_cost_layers(conn, *, movement_id: int, variant_id: int, location_id: int,
                         quantity: Decimal, method: str = "fifo", allow_expired: bool = False,
                         minimum_remaining_shelf_life_days: int | None = None) -> dict:
    """Consume exact layer quantities under row locks; fail closed on unvalued stock."""
    if method not in {"fifo", "fefo"}:
        raise HTTPException(status_code=422, detail="Allocation method must be fifo or fefo")
    ordering = (
        "expiry_date ASC NULLS LAST, created_at ASC, id ASC"
        if method == "fefo" else "created_at ASC, id ASC"
    )
    expiry_filter = "" if allow_expired else "AND (expiry_date IS NULL OR expiry_date >= CURRENT_DATE) "
    expiry_params = ()
    if not allow_expired and minimum_remaining_shelf_life_days is not None:
        if isinstance(minimum_remaining_shelf_life_days, bool) or minimum_remaining_shelf_life_days < 0:
            raise HTTPException(status_code=422, detail="Minimum remaining shelf life must be a non-negative whole number of days")
        expiry_filter = "AND (expiry_date IS NULL OR expiry_date >= CURRENT_DATE + (%s * INTERVAL '1 day')) "
        expiry_params = (minimum_remaining_shelf_life_days,)
    layers = conn.execute(
        "SELECT id,remaining_quantity,unit_cost FROM inventory_cost_layers "
        "WHERE variant_id=%s AND location_id=%s AND remaining_quantity>0 "
        f"{expiry_filter}ORDER BY {ordering} FOR UPDATE",
        (variant_id, location_id, *expiry_params),
    ).fetchall()
    available = sum((row["remaining_quantity"] for row in layers), Decimal("0"))
    if available < quantity:
        raise HTTPException(
            status_code=409,
            detail=f"Insufficient {'valued' if not allow_expired else 'recorded'} stock: requested {quantity}, allocatable layer balance {available}. "
                   "Value opening stock with an approved opening layer before issuing it.",
        )
    remaining = quantity
    total_cost = Decimal("0.00")
    allocations = []
    for layer in layers:
        if remaining <= 0:
            break
        take = min(remaining, layer["remaining_quantity"])
        cost = money(take * layer["unit_cost"])
        conn.execute(
            "UPDATE inventory_cost_layers SET remaining_quantity=remaining_quantity-%s WHERE id=%s",
            (take, layer["id"]),
        )
        conn.execute(
            "INSERT INTO inventory_cost_allocations "
            "(issue_movement_id,cost_layer_id,quantity,unit_cost,total_cost,allocation_method) VALUES (%s,%s,%s,%s,%s,%s)",
            (movement_id, layer["id"], take, layer["unit_cost"], cost, method),
        )
        allocations.append({"cost_layer_id": layer["id"], "quantity": take,
                            "unit_cost": layer["unit_cost"], "total_cost": cost})
        total_cost += cost
        remaining -= take
    return {"quantity": quantity, "total_cost": money(total_cost), "method": method, "allocations": allocations}


def transfer_cost_layers(conn, *, source_movement_id: int, destination_movement_id: int,
                         variant_id: int, source_location_id: int, destination_location_id: int,
                         quantity: Decimal, minimum_remaining_shelf_life_days: int | None = None) -> list[dict]:
    """Move eligible lot quantities and original unit costs between locations."""
    expiry_filter = ""
    params = (variant_id, source_location_id)
    if minimum_remaining_shelf_life_days is not None:
        if isinstance(minimum_remaining_shelf_life_days, bool) or minimum_remaining_shelf_life_days < 0:
            raise HTTPException(status_code=422, detail="Minimum remaining shelf life must be a non-negative whole number of days")
        expiry_filter = "AND (expiry_date IS NULL OR expiry_date >= CURRENT_DATE + (%s * INTERVAL '1 day')) "
        params = (*params, minimum_remaining_shelf_life_days)
    source = conn.execute(
        "SELECT id,remaining_quantity,unit_cost,batch_code,manufacture_date,expiry_date,goods_receipt_line_id FROM inventory_cost_layers "
        "WHERE variant_id=%s AND location_id=%s AND remaining_quantity>0 "
        f"{expiry_filter}ORDER BY created_at,id FOR UPDATE",
        params,
    ).fetchall()
    available = sum((row["remaining_quantity"] for row in source), Decimal("0"))
    if available < quantity:
        raise HTTPException(status_code=409, detail="Insufficient valued stock for transfer")
    remaining = quantity
    moved = []
    for layer in source:
        if remaining <= 0:
            break
        take = min(remaining, layer["remaining_quantity"])
        conn.execute("UPDATE inventory_cost_layers SET remaining_quantity=remaining_quantity-%s WHERE id=%s",
                     (take, layer["id"]))
        conn.execute(
            "INSERT INTO inventory_cost_allocations "
            "(issue_movement_id,cost_layer_id,quantity,unit_cost,total_cost,allocation_method) VALUES (%s,%s,%s,%s,%s,%s)",
            (source_movement_id, layer["id"], take, layer["unit_cost"], money(take * layer["unit_cost"]), "fifo"),
        )
        created = create_cost_layer(
            conn, movement_id=destination_movement_id, variant_id=variant_id,
            location_id=destination_location_id, quantity=take, unit_cost=layer["unit_cost"],
            goods_receipt_line_id=layer["goods_receipt_line_id"], batch_code=layer["batch_code"],
            manufacture_date=layer["manufacture_date"], expiry_date=layer["expiry_date"], source_layer_id=layer["id"],
        )
        moved.append(created)
        remaining -= take
    return moved
