from decimal import Decimal

import pytest

from app.services.order_inventory import (
    dispatch_order_stock,
    ensure_order_can_be_cancelled,
    release_order_stock,
    reserve_order_stock,
)


class Result:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, locations=None, balances=None, outstanding=None):
        self.locations = locations or []
        self.balances = balances or []
        self.outstanding = outstanding or []
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "FROM stock_locations" in sql:
            return Result(rows=self.locations)
        if "FROM inventory_balances" in sql and "SELECT variant_id" in sql:
            return Result(rows=self.balances)
        if "FROM inventory_movements" in sql and "GROUP BY variant_id" in sql:
            return Result(rows=self.outstanding)
        if "UPDATE inventory_balances" in sql:
            return Result(row={"variant_id": params[2] if len(params) > 2 else 1})
        return Result()


def test_order_without_pin_keeps_legacy_no_reservation_behaviour():
    conn = FakeConnection()
    assert reserve_order_stock(conn, 101, None, [(7, 2)]) is None
    assert conn.calls == []


def test_reservation_uses_one_pin_location_and_records_each_line():
    conn = FakeConnection(
        locations=[{"id": 4}],
        balances=[
            {"variant_id": 7, "on_hand": Decimal("5"), "reserved": Decimal("1")},
            {"variant_id": 8, "on_hand": Decimal("3"), "reserved": Decimal("0")},
        ],
    )
    location_id = reserve_order_stock(conn, 101, "560035", [(7, 2), (8, 3)])
    assert location_id == 4
    updates = [call for call in conn.calls if "UPDATE inventory_balances" in call[0]]
    movements = [call for call in conn.calls if "INSERT INTO inventory_movements" in call[0]]
    assert len(updates) == 2
    assert len(movements) == 2
    assert all(params[4] == "101" for _, params in movements)


def test_reservation_fails_without_mutating_stock_when_pin_location_is_insufficient():
    conn = FakeConnection(
        locations=[{"id": 4}],
        balances=[{"variant_id": 7, "on_hand": Decimal("2"), "reserved": Decimal("1")}],
    )
    with pytest.raises(ValueError, match="Insufficient stock"):
        reserve_order_stock(conn, 101, "560035", [(7, 2)])
    assert not any("UPDATE inventory_balances" in sql for sql, _ in conn.calls)
    assert not any("INSERT INTO inventory_movements" in sql for sql, _ in conn.calls)


def test_release_and_dispatch_are_noops_when_no_reservation_is_outstanding():
    conn = FakeConnection(outstanding=[])
    assert release_order_stock(conn, 101) == 0
    assert dispatch_order_stock(conn, 101) == 0
    assert not any("UPDATE inventory_balances" in sql for sql, _ in conn.calls)


def test_dispatch_consumes_only_outstanding_reserved_quantity():
    conn = FakeConnection(outstanding=[{
        "variant_id": 7,
        "location_id": 4,
        "outstanding": Decimal("2"),
    }])
    assert dispatch_order_stock(conn, 101) == 1
    update = next(call for call in conn.calls if "UPDATE inventory_balances" in call[0])
    assert "on_hand=on_hand-%s, reserved=reserved-%s" in update[0]
    movement = next(call for call in conn.calls if "INSERT INTO inventory_movements" in call[0])
    assert "'sale'" in movement[0]
    assert movement[1][4] == "101"


def test_release_records_a_release_movement_for_outstanding_quantity():
    conn = FakeConnection(outstanding=[{
        "variant_id": 7,
        "location_id": 4,
        "outstanding": Decimal("2"),
    }])
    assert release_order_stock(conn, 101) == 1
    movement = next(call for call in conn.calls if "INSERT INTO inventory_movements" in call[0])
    assert "'release'" in movement[0]
    assert movement[1][4] == "101"



def test_partial_dispatch_consumes_only_requested_quantity():
    conn = FakeConnection(outstanding=[{
        "variant_id": 7,
        "location_id": 4,
        "outstanding": Decimal("5"),
    }])
    assert dispatch_order_stock(conn, 101, {7: 2}) == 1
    update = next(call for call in conn.calls if "UPDATE inventory_balances" in call[0])
    assert update[1][0] == Decimal("2")
    assert update[1][1] == Decimal("2")
    movement = next(call for call in conn.calls if "INSERT INTO inventory_movements" in call[0])
    assert movement[1][2] == Decimal("2")


def test_partial_dispatch_rejects_quantity_above_reservation_before_mutation():
    conn = FakeConnection(outstanding=[{
        "variant_id": 7,
        "location_id": 4,
        "outstanding": Decimal("3"),
    }])
    with pytest.raises(ValueError, match="exceeds the outstanding reservation"):
        dispatch_order_stock(conn, 101, {7: 4})
    assert not any("UPDATE inventory_balances" in sql for sql, _ in conn.calls)
    assert not any("INSERT INTO inventory_movements" in sql for sql, _ in conn.calls)


def test_partial_dispatch_rejects_empty_quantity_map():
    conn = FakeConnection(outstanding=[{
        "variant_id": 7,
        "location_id": 4,
        "outstanding": Decimal("3"),
    }])
    with pytest.raises(ValueError, match="must be positive"):
        dispatch_order_stock(conn, 101, {})
    assert not any("UPDATE inventory_balances" in sql for sql, _ in conn.calls)



def test_pos_reservation_uses_staff_selected_location_without_delivery_pin():
    conn = FakeConnection(
        locations=[{"id": 9}],
        balances=[{"variant_id": 7, "on_hand": Decimal("4"), "reserved": Decimal("1")}],
    )
    location_id = reserve_order_stock(conn, 102, None, [(7, 2)], location_id=9)
    assert location_id == 9
    location_query = next(call for call in conn.calls if "FROM stock_locations" in call[0])
    assert "id=%s AND is_active=TRUE" in location_query[0]
    assert location_query[1] == (9,)


def test_pos_reservation_rejects_inactive_or_unmatched_selected_location():
    conn = FakeConnection(locations=[])
    with pytest.raises(ValueError, match="Selected stock location"):
        reserve_order_stock(conn, 102, None, [(7, 1)], location_id=9)


def test_order_cancellation_is_blocked_after_any_dispatch():
    class StartedConnection:
        def execute(self, sql, params=()):
            return Result(row={"started": True})
    with pytest.raises(ValueError, match="cannot be cancelled"):
        ensure_order_can_be_cancelled(StartedConnection(), 101)


def test_order_cancellation_remains_allowed_before_dispatch():
    class NotStartedConnection:
        def execute(self, sql, params=()):
            return Result(row={"started": False})
    assert ensure_order_can_be_cancelled(NotStartedConnection(), 101) is None
