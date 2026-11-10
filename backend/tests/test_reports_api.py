from contextlib import contextmanager
from datetime import date
import pytest
from fastapi import HTTPException
from app.api import reports


class FakeConnection:
    def __init__(self):
        self.one_rows = iter([
            {"order_count": 25, "active_order_count": 20, "active_order_value": 12500},
            {"payment_count": 22, "captured_count": 18, "captured_amount": 11200, "pending_count": 3, "pending_amount": 1000},
            {"balance_rows": 8, "stock_units": 120, "low_stock_rows": 2, "out_of_stock_rows": 1},
            {"active_products": 15, "active_variants": 28},
        ])
        self.many_rows = iter([
            [{"status": "placed", "count": 15}, {"status": "cancelled", "count": 10}],
            [{"status": "captured", "count": 18}, {"status": "pending", "count": 3}],
        ])
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        self.last_query = query
        return self

    def fetchone(self):
        return next(self.one_rows)

    def fetchall(self):
        return next(self.many_rows)


def test_reports_overview_returns_full_database_aggregates(monkeypatch):
    conn = FakeConnection()
    @contextmanager
    def connect():
        yield conn
    monkeypatch.setattr(reports, "_connect", connect)
    result = reports.reports_overview(date(2026, 11, 1), date(2026, 11, 6))
    assert result["orders"]["order_count"] == 25
    assert result["orders"]["active_order_value"] == 12500
    assert result["payments"]["captured_amount"] == 11200
    assert result["inventory"]["stock_units"] == 120
    assert result["catalogue"]["active_products"] == 15
    assert all(params == (date(2026, 11, 1), date(2026, 11, 6)) for query, params in conn.queries[:4])
    assert "Asia/Kolkata" in conn.queries[0][0]


def test_reports_overview_rejects_reversed_date_range():
    with pytest.raises(HTTPException) as exc:
        reports.reports_overview(date(2026, 11, 7), date(2026, 11, 6))
    assert exc.value.status_code == 422
