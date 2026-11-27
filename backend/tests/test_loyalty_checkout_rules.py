"""Super Coins checkout cap, non-expiring validity and accounting readiness."""
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import loyalty_accounting, loyalty_redemption as redemption

APP = Path(__file__).resolve().parents[1] / "app"


def _quote(monkeypatch, payable, available):
    monkeypatch.setattr(redemption, "_account", lambda conn, email, lock=False: {"id": 1})
    monkeypatch.setattr(redemption, "available_balance", lambda conn, account_id: available)
    monkeypatch.setattr(redemption, "loyalty_liability_account", lambda conn, event_date=None: 1)
    return redemption.quote_redemption(None, "a@test.local", Decimal(payable))


def test_coins_never_cover_the_whole_order(monkeypatch):
    assert _quote(monkeypatch, "100.00", 500)["maximum_redeemable_coins"] == 99
    assert _quote(monkeypatch, "99.50", 500)["maximum_redeemable_coins"] == 98
    assert _quote(monkeypatch, "100.00", 40)["maximum_redeemable_coins"] == 40


def test_tiny_orders_cannot_be_paid_with_coins(monkeypatch):
    assert _quote(monkeypatch, "1.00", 500)["maximum_redeemable_coins"] == 0
    assert _quote(monkeypatch, "0.50", 500)["maximum_redeemable_coins"] == 0


def test_server_rejects_coins_that_leave_nothing_to_pay():
    with pytest.raises(HTTPException) as error:
        redemption.redeem_for_order(
            None, customer_email="a@test.local", order_id=1, order_reference="SB-1",
            payable_amount=Decimal("100.00"), requested_coins=100,
        )
    assert error.value.status_code == 422
    assert "at least Rs 1" in error.value.detail


def test_coins_do_not_expire_and_no_code_path_uses_365_days():
    assert redemption.COIN_VALIDITY_DAYS >= 36500
    for relative in ("api/orders.py", "api/loyalty.py", "services/loyalty_redemption.py"):
        source = (APP / relative).read_text(encoding="utf-8")
        assert "365 days" not in source and "days=365" not in source, relative


def test_readiness_lists_only_missing_mappings(monkeypatch):
    def approved(conn, *, event_type, line_role, expected_type, event_date):
        if event_type == "points_redemption":
            raise HTTPException(409, "missing")
        return 1

    monkeypatch.setattr(loyalty_accounting, "_approved_account", approved)
    result = loyalty_accounting.mapping_readiness(None)
    assert result["ready"] is False
    assert [item["event_type"] for item in result["missing_required"]] == ["points_redemption"]
    assert result["missing_optional"] == []
