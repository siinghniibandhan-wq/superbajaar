from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from app.api import pos


class FakeConnection:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


def test_pos_summary_separates_captured_and_pending(monkeypatch):
    conn = FakeConnection(rows=[
        {"order_count": 4, "active_order_count": 3, "order_value": 900, "today_order_count": 1, "today_order_value": 300},
        {"payment_count": 3, "captured_count": 1, "captured_amount": 200, "pending_count": 2, "pending_amount": 700},
    ])
    class Cursor:
        def __init__(self, row): self.row = row
        def fetchone(self): return self.row
    calls = iter(conn.rows)
    def execute(query, params=()):
        conn.queries.append((query, params))
        return Cursor(next(calls))
    conn.execute = execute
    @contextmanager
    def connect():
        yield conn
    monkeypatch.setattr(pos, "_connect", connect)
    result = pos.pos_summary()
    assert result["orders"]["order_value"] == 900
    assert result["payments"]["captured_amount"] == 200
    assert result["payments"]["pending_amount"] == 700
    assert "p.status='captured'" in conn.queries[1][0]
    assert "p.status IN ('pending','authorized')" in conn.queries[1][0]


def test_pos_sale_not_found_is_404(monkeypatch):
    conn = FakeConnection(row=None)

    @contextmanager
    def connect():
        yield conn

    monkeypatch.setattr(pos, "_connect", connect)
    with pytest.raises(HTTPException) as exc:
        pos.get_pos_sale(123)
    assert exc.value.status_code == 404


def test_pos_sales_aggregates_payments_before_joining_order_lines(monkeypatch):
    conn = FakeConnection(
        rows=[{"id": 7, "order_number": "POS-7", "captured_amount": 250, "line_count": 3}],
        row={"total": 1},
    )
    @contextmanager
    def connect():
        yield conn
    monkeypatch.setattr(pos, "_connect", connect)
    result = pos.list_pos_sales(limit=10, offset=0)
    assert result["total"] == 1
    assert result["items"][0]["captured_amount"] == 250
    query = conn.queries[0][0]
    assert "SELECT order_id, count(*) AS line_count" in query
    assert "SELECT order_id," in query and "sum(amount) FILTER (WHERE p.status='captured')" in query
    assert "FROM payments p GROUP BY order_id" in query
    assert "string_agg(DISTINCT p.status" in query



def test_pos_sales_supports_date_register_cashier_tender_and_search_filters(monkeypatch):
    from datetime import date
    conn = FakeConnection(
        rows=[{"id": 7, "order_number": "POS-7", "register_id": 2, "cashier_user_id": 9}],
        row={"total": 1},
    )

    @contextmanager
    def connect():
        yield conn

    monkeypatch.setattr(pos, "_connect", connect)
    result = pos.list_pos_sales(
        date_from=date(2026, 11, 1),
        date_to=date(2026, 11, 28),
        register_id=2,
        cashier_user_id=9,
        payment_method="upi",
        search="POS-7",
        limit=25,
        offset=0,
    )

    assert result["total"] == 1
    query, params = conn.queries[0]
    assert "pos_register_shifts s" in query
    assert "s.register_id=%s" in query
    assert "s.cashier_user_id=%s" in query
    assert "EXISTS (SELECT 1 FROM payments pm" in query
    assert "o.order_number ILIKE %s" in query
    assert params == [
        date(2026, 11, 1), date(2026, 11, 28), 2, 9, "upi",
        "%POS-7%", "%POS-7%", "%POS-7%", 25, 0,
    ]
    count_query, count_params = conn.queries[1]
    assert "LEFT JOIN pos_register_shifts" in count_query
    assert count_params == params[:-2]


def test_pos_sales_rejects_inverted_date_range():
    from datetime import date
    with pytest.raises(HTTPException) as exc:
        pos.list_pos_sales(date_from=date(2026, 11, 29), date_to=date(2026, 11, 1))
    assert exc.value.status_code == 422
