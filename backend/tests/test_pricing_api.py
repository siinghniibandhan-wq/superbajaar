from contextlib import contextmanager
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from app.api import pricing


class FakeConnection:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    @contextmanager
    def transaction(self):
        yield self


def test_pricing_overview_reports_source_metrics(monkeypatch):
    conn = FakeConnection({"variant_count": 12, "missing_price_count": 2, "invalid_mrp_count": 0,
                           "average_selling_price": 120, "sum_selling_prices": 1440})
    @contextmanager
    def connect():
        yield conn
    monkeypatch.setattr(pricing, "_connect", connect)
    result = pricing.pricing_overview()
    assert result["source"] == "postgresql"
    assert result["metrics"]["variant_count"] == 12
    assert "WHERE v.is_active = TRUE" in conn.queries[0][0]


def test_price_update_rejects_missing_variant(monkeypatch):
    conn = FakeConnection(None)
    @contextmanager
    def connect():
        yield conn
    monkeypatch.setattr(pricing, "_connect", connect)
    payload = pricing.PriceUpdate(selling_price=90, mrp=100, cost_price=50)
    try:
        pricing.update_price(999, payload)
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("missing variant must return 404")


def test_price_update_rejects_mrp_below_selling_price():
    with pytest.raises(ValidationError):
        pricing.PriceUpdate(selling_price=120, mrp=100, cost_price=60)
