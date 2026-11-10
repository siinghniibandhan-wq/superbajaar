import importlib.util


def _load_service():
    spec = importlib.util.find_spec("app.services.inventory_overview")
    assert spec is not None, "Inventory overview must be backed by a server-side aggregate service"
    from app.services.inventory_overview import load_inventory_overview
    return load_inventory_overview


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        normalized = " ".join(query.split())
        if "SUM(on_hand)" in normalized:
            return FakeCursor([{"total_on_hand": 120, "total_reserved": 35, "total_available": 85, "low_stock_rows": 4, "out_of_stock_rows": 2}])
        if "FROM inventory_movements" in normalized and "GROUP BY" not in normalized:
            return FakeCursor([{"total_movements": 42}])
        if "FROM inventory_movements" in normalized and "GROUP BY" in normalized:
            return FakeCursor([{"movement_type": "receipt", "total": 30}, {"movement_type": "issue", "total": 12}])
        if "FROM stock_locations" in normalized:
            return FakeCursor([{"location_id": 1, "location_name": "Warehouse A", "on_hand": 120}])
        if "COUNT(*) AS total_approval_requests" in normalized:
            return FakeCursor([{"total_approval_requests": 7, "pending_approvals": 3}])
        if "COUNT(*) AS reconciliation_records" in normalized:
            return FakeCursor([{"reconciliation_records": 25, "mismatched_records": 2}])
        if "inventory_cost_layers" in normalized:
            return FakeCursor([{"active_cost_layers": 8}])
        raise AssertionError(f"Unexpected SQL: {normalized}")


def test_inventory_overview_uses_unbounded_database_aggregates():
    conn = FakeConnection()
    result = _load_service()(conn, actor_id=9, actor_role="manager")

    assert result["totals"] == {
        "on_hand": 120, "reserved": 35, "available": 85, "low_stock_rows": 4, "out_of_stock_rows": 2,
        "movements": 42, "pending_approvals": 3, "total_approval_requests": 7,
        "active_cost_layers": 8, "reconciliation_records": 25, "mismatched_records": 2,
    }
    assert result["movement_groups"] == [
        {"movement_type": "receipt", "total": 30},
        {"movement_type": "issue", "total": 12},
    ]
    assert result["stock_by_location"] == [
        {"location_id": 1, "location_name": "Warehouse A", "on_hand": 120},
    ]
    assert all("LIMIT" not in query.upper() for query, _ in conn.queries)
    approval_query = next((query, params) for query, params in conn.queries if "total_approval_requests" in query)
    assert approval_query[1] == ("manager", 9, 9, "manager")
    assert "hr_employee_statutory_profiles" in approval_query[0]
