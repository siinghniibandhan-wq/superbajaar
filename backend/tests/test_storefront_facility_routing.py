"""Regression tests for profile-driven storefront facility routing."""

from decimal import Decimal

from app.services.order_inventory import reserve_order_stock


class _Result:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, location_rows, balance_rows_by_location):
        self.location_rows = location_rows
        self.balance_rows_by_location = balance_rows_by_location
        self.calls = []
        self.updates = []
        self.movements = []

    def execute(self, query, params):
        self.calls.append((query, params))
        if "FROM stock_locations sl" in query:
            return _Result(rows=self.location_rows)
        if "FROM inventory_balances" in query:
            return _Result(rows=self.balance_rows_by_location.get(params[0], []))
        if query.startswith("UPDATE inventory_balances"):
            self.updates.append(params)
            return _Result(row={"variant_id": params[1]})
        if query.startswith("INSERT INTO inventory_movements"):
            self.movements.append(params)
            return _Result(row={"id": len(self.movements)})
        raise AssertionError(f"Unexpected SQL in routing test: {query}")


def test_storefront_reservation_queries_profile_service_pins_priority_and_hours():
    conn = _Connection(
        location_rows=[{"id": 22}, {"id": 11}],
        balance_rows_by_location={
            22: [{"variant_id": 7, "on_hand": Decimal("10"), "reserved": Decimal("0")}],
            11: [{"variant_id": 7, "on_hand": Decimal("10"), "reserved": Decimal("0")}],
        },
    )

    selected = reserve_order_stock(conn, 900, "800001", [(7, 2)], profile_routing=True)

    assert selected == 22
    query, params = conn.calls[0]
    assert "stock_location_profiles" in query
    assert "service_pin_codes" in query
    assert "routing_priority" in query
    assert "storefront_available" in query
    assert "operating_days" in query
    assert "Asia/Kolkata" in query
    assert params == ("800001",)
    assert len(conn.updates) == 1
    assert len(conn.movements) == 1


def test_storefront_reservation_skips_higher_priority_facility_without_all_stock():
    conn = _Connection(
        location_rows=[{"id": 22}, {"id": 11}],
        balance_rows_by_location={
            22: [{"variant_id": 7, "on_hand": Decimal("10"), "reserved": Decimal("0")}],
            11: [{"variant_id": 7, "on_hand": Decimal("1"), "reserved": Decimal("0")}],
        },
    )

    selected = reserve_order_stock(conn, 901, "800001", [(7, 2)], profile_routing=True)

    assert selected == 22
    assert len(conn.updates) == 1
    assert conn.updates[0][2] == 22


def test_storefront_reservation_never_splits_order_across_facilities():
    conn = _Connection(
        location_rows=[{"id": 22}, {"id": 11}],
        balance_rows_by_location={
            22: [{"variant_id": 7, "on_hand": Decimal("10"), "reserved": Decimal("0")}],
            11: [{"variant_id": 8, "on_hand": Decimal("10"), "reserved": Decimal("0")}],
        },
    )

    try:
        reserve_order_stock(conn, 902, "800001", [(7, 2), (8, 2)], profile_routing=True)
    except ValueError as exc:
        assert "no single active location" in str(exc)
    else:
        raise AssertionError("A split reservation must never be created")

    assert conn.updates == []
    assert conn.movements == []



def test_manual_order_keeps_legacy_pin_and_location_ordering():
    conn = _Connection(
        location_rows=[{"id": 4}],
        balance_rows_by_location={
            4: [{"variant_id": 7, "on_hand": Decimal("5"), "reserved": Decimal("0")}],
        },
    )

    selected = reserve_order_stock(conn, 903, "800001", [(7, 1)])

    assert selected == 4
    query, params = conn.calls[0]
    assert "stock_location_profiles" not in query
    assert "pin_code=%s ORDER BY id" in query
    assert params == ("800001",)
