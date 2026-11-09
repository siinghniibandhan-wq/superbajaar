"""Unbounded, database-side Inventory overview aggregates."""


def load_inventory_overview(conn, *, actor_id: int, actor_role: str):
    """Return full-dataset Inventory KPIs and chart series without page limits.

    Operational list endpoints remain paginated; dashboard totals must never be
    derived from those bounded result sets.
    """
    balance_totals = conn.execute(
        "SELECT COALESCE(SUM(on_hand),0) AS total_on_hand, "
        "COALESCE(SUM(reserved),0) AS total_reserved, "
        "COALESCE(SUM(on_hand-reserved),0) AS total_available, "
        "COUNT(*) FILTER (WHERE on_hand>0 AND on_hand<=5) AS low_stock_rows, "
        "COUNT(*) FILTER (WHERE on_hand<=0) AS out_of_stock_rows "
        "FROM inventory_balances"
    ).fetchone() or {}
    movement_total = conn.execute(
        "SELECT COUNT(*) AS total_movements FROM inventory_movements"
    ).fetchone() or {}
    movement_groups = conn.execute(
        "SELECT movement_type,COUNT(*) AS total FROM inventory_movements "
        "GROUP BY movement_type ORDER BY total DESC,movement_type"
    ).fetchall()
    stock_by_location = conn.execute(
        "SELECT sl.id AS location_id,sl.name AS location_name, "
        "COALESCE(SUM(ib.on_hand),0) AS on_hand "
        "FROM stock_locations sl LEFT JOIN inventory_balances ib ON ib.location_id=sl.id "
        "GROUP BY sl.id,sl.name ORDER BY on_hand DESC,sl.name"
    ).fetchall()
    approval_totals = conn.execute(
        "SELECT COUNT(*) AS total_approval_requests, "
        "COUNT(*) FILTER (WHERE r.status='pending') AS pending_approvals "
        "FROM inventory_event_approval_requests r "
        "JOIN organisation_policy_versions p ON p.id=r.policy_version_id "
        "WHERE (%s IN ('owner','admin') OR r.created_by_user_id=%s OR ("
        "r.establishment_id IN (SELECT esp.establishment_id FROM hr_employees he "
        "JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id WHERE he.user_id=%s) "
        "AND EXISTS (SELECT 1 FROM jsonb_array_elements("
        "p.policy_config->'event_policies'->r.event_type->'stages') st "
        "WHERE st->'approver_roles' ? %s)))",
        (actor_role, actor_id, actor_id, actor_role),
    ).fetchone() or {}
    reconciliation_totals = conn.execute(
        "SELECT COUNT(*) AS reconciliation_records, "
        "COUNT(*) FILTER (WHERE ib.on_hand <> COALESCE(cl.valued_quantity,0)) AS mismatched_records "
        "FROM inventory_balances ib LEFT JOIN ("
        "SELECT variant_id,location_id,SUM(remaining_quantity) AS valued_quantity "
        "FROM inventory_cost_layers GROUP BY variant_id,location_id"
        ") cl ON cl.variant_id=ib.variant_id AND cl.location_id=ib.location_id"
    ).fetchone() or {}
    active_layers = conn.execute(
        "SELECT COUNT(*) AS active_cost_layers FROM inventory_cost_layers "
        "WHERE remaining_quantity>0"
    ).fetchone() or {}

    return {
        "totals": {
            "on_hand": balance_totals.get("total_on_hand", 0),
            "reserved": balance_totals.get("total_reserved", 0),
            "available": balance_totals.get("total_available", 0),
            "low_stock_rows": balance_totals.get("low_stock_rows", 0),
            "out_of_stock_rows": balance_totals.get("out_of_stock_rows", 0),
            "movements": movement_total.get("total_movements", 0),
            "pending_approvals": approval_totals.get("pending_approvals", 0),
            "total_approval_requests": approval_totals.get("total_approval_requests", 0),
            "active_cost_layers": active_layers.get("active_cost_layers", 0),
            "reconciliation_records": reconciliation_totals.get("reconciliation_records", 0),
            "mismatched_records": reconciliation_totals.get("mismatched_records", 0),
        },
        "movement_groups": movement_groups,
        "stock_by_location": stock_by_location,
    }
