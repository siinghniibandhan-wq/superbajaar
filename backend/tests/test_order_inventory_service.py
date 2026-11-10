"""Focused tests for order inventory reservation and cost policy helpers."""

from app.services.order_inventory import cost_allocation_method, order_has_reservation


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row] if self.row is not None else []


class _Connection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        return _Result(self.row)


def test_expiry_managed_location_uses_fefo():
    conn = _Connection({"enabled": True})
    assert cost_allocation_method(conn, 12, 4) == "fefo"
    assert conn.calls[0][1] == (12, 4)
    assert "expiry_date IS NOT NULL" in conn.calls[0][0]


def test_non_expiry_managed_location_uses_fifo():
    conn = _Connection({"enabled": False})
    assert cost_allocation_method(conn, 12, 4) == "fifo"


def test_missing_cost_layer_result_fails_safe_to_fifo():
    conn = _Connection(None)
    assert cost_allocation_method(conn, 12, 4) == "fifo"


def test_order_has_reservation_reflects_query_result():
    conn = _Connection({"variant_id": 12, "location_id": 4, "outstanding": 2})
    assert order_has_reservation(conn, 55) is True
    assert conn.calls[0][1][3] == "55"
