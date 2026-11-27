from decimal import Decimal
from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from app.api import pos_registers


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows or []
    def fetchone(self): return self.row
    def fetchall(self): return self.rows


class FakeConnection:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.queries = []
    def execute(self, query, params=()):
        self.queries.append((query, params))
        return next(self.responses)


def test_register_code_is_normalized_and_required():
    payload = pos_registers.RegisterCreate(location_id=1, register_code=" till 01 ", name=" Main Counter ")
    assert payload.register_code == "till 01"
    assert payload.name == "Main Counter"


def test_cash_movement_rejects_invalid_direction():
    with pytest.raises(ValueError):
        pos_registers.CashMovement(movement_type="transfer", amount=Decimal("10"), reason="Float top-up")


def test_cash_movement_requires_reason():
    with pytest.raises(ValueError):
        pos_registers.CashMovement(movement_type="cash_out", amount=Decimal("10"), reason="  ")


def test_shift_cash_expected_formula(monkeypatch):
    conn = FakeConnection([
        Cursor({"cash_sales": Decimal("500"), "cash_refunds": Decimal("20")}),
        Cursor({"cash_in": Decimal("100"), "cash_out": Decimal("30")}),
    ])
    monkeypatch.setattr(pos_registers, "_connect", lambda: conn)
    result = pos_registers._shift_cash_totals(conn, 42)
    assert result == {
        "cash_sales": Decimal("500"), "cash_refunds": Decimal("20"),
        "cash_in": Decimal("100"), "cash_out": Decimal("30"),
    }


def test_close_shift_expected_cash_uses_float_sales_refunds_and_drawer_movements():
    opening_float = Decimal("1000")
    cash_sales = Decimal("500")
    cash_refunds = Decimal("20")
    cash_in = Decimal("100")
    cash_out = Decimal("30")
    expected = opening_float + cash_sales - cash_refunds + cash_in - cash_out
    assert expected == Decimal("1550")
