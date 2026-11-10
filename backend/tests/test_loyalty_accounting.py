from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.services import loyalty_accounting


class FakeConnection:
    def __init__(self, *, mappings, prior=None):
        self.mappings = mappings
        self.prior = prior
        self.queries = []

    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        if "FROM loyalty_transactions t JOIN loyalty_accounts" in sql:
            return FakeResult({
                "id": 51, "coins": 25, "created_at": datetime(2026, 11, 3, tzinfo=timezone.utc),
                "idempotency_key": "earn:order:8", "customer_email": "customer@example.test",
            })
        if "FROM accounting_event_account_mappings" in sql:
            role = params[1]
            return FakeResult(self.mappings.get(role, []))
        if "FROM accounting_vouchers WHERE idempotency_key" in sql:
            return FakeResult(self.prior)
        raise AssertionError(f"Unexpected SQL: {sql}")


class FakeResult:
    def __init__(self, row_or_rows):
        self.value = row_or_rows

    def fetchone(self):
        return self.value if isinstance(self.value, dict) or self.value is None else None

    def fetchall(self):
        return self.value if isinstance(self.value, list) else []


def _mappings():
    return {
        "loyalty_reward_expense": [{"account_id": 700, "account_type": "expense", "is_active": True}],
        "loyalty_points_liability": [{"account_id": 800, "account_type": "liability", "is_active": True}],
    }


def test_earning_posts_balanced_expense_and_liability(monkeypatch):
    posted = {}
    monkeypatch.setattr(
        "app.api.accounting._ist_date",
        lambda value: date(2026, 11, 3),
    )
    monkeypatch.setattr(
        "app.api.accounting._post_voucher",
        lambda conn, header, lines, actor: posted.update(header=header, lines=lines, actor=actor) or 91,
    )
    conn = FakeConnection(mappings=_mappings())

    voucher_id = loyalty_accounting.post_earning_accrual(conn, 51)

    assert voucher_id == 91
    assert posted["header"]["idempotency_key"] == "loyalty-earning:51"
    assert posted["lines"][0]["account_id"] == 700
    assert posted["lines"][0]["debit"] == Decimal("25.00")
    assert posted["lines"][1]["account_id"] == 800
    assert posted["lines"][1]["credit"] == Decimal("25.00")
    assert posted["actor"] == (None, "system:loyalty")


def test_earning_fails_closed_without_exact_approved_expense_mapping(monkeypatch):
    monkeypatch.setattr("app.api.accounting._ist_date", lambda value: date(2026, 11, 3))
    conn = FakeConnection(mappings={
        "loyalty_reward_expense": [],
        "loyalty_points_liability": _mappings()["loyalty_points_liability"],
    })

    with pytest.raises(HTTPException) as error:
        loyalty_accounting.post_earning_accrual(conn, 51)

    assert error.value.status_code == 409
    assert "Finance must approve exactly one active expense mapping" in error.value.detail


def test_restoration_does_not_double_accrue_original_reward(monkeypatch):
    class RestoreConnection(FakeConnection):
        def execute(self, sql, params=()):
            if "FROM loyalty_transactions t JOIN loyalty_accounts" in sql:
                return FakeResult({
                    "id": 51, "coins": 25, "created_at": datetime(2026, 11, 3, tzinfo=timezone.utc),
                    "idempotency_key": "restore:order:8:earned:2", "customer_email": "customer@example.test",
                })
            return super().execute(sql, params)

    conn = RestoreConnection(mappings={})
    assert loyalty_accounting.post_earning_accrual(conn, 51) is None


class DebitConnection(FakeConnection):
    def __init__(self, *, transaction_type, mappings, prior=None):
        super().__init__(mappings=mappings, prior=prior)
        self.transaction_type = transaction_type

    def execute(self, sql, params=()):
        if "FROM loyalty_transactions t JOIN loyalty_accounts" in sql:
            self.queries.append((sql, params))
            return FakeResult({
                "id": 61, "coins": 12, "created_at": datetime(2026, 11, 3, tzinfo=timezone.utc),
                "transaction_type": self.transaction_type, "customer_email": "customer@example.test",
            })
        return super().execute(sql, params)


@pytest.mark.parametrize(
    ("transaction_type", "event_type", "offset_role", "key", "source_type"),
    [
        ("redeem", "points_redeemed_admin", "loyalty_reward_expense",
         "loyalty-manual-redemption:61", "loyalty_manual_redemption"),
        ("adjustment", "points_adjusted", "loyalty_adjustment_offset",
         "loyalty-adjustment:61", "loyalty_adjustment"),
    ],
)
def test_admin_debit_uses_distinct_finance_event_and_idempotency(
    monkeypatch, transaction_type, event_type, offset_role, key, source_type
):
    posted = {}
    monkeypatch.setattr("app.api.accounting._ist_date", lambda value: date(2026, 11, 3))
    monkeypatch.setattr(
        "app.api.accounting._post_voucher",
        lambda conn, header, lines, actor: posted.update(header=header, lines=lines) or 92,
    )
    mappings = {
        "loyalty_points_liability": [{"account_id": 2410, "account_type": "liability", "is_active": True}],
        offset_role: [{"account_id": 6110, "account_type": "expense", "is_active": True}],
    }
    conn = DebitConnection(transaction_type=transaction_type, mappings=mappings)

    voucher_id = loyalty_accounting.post_debit_adjustment(conn, 61)

    mapping_events = [params[0] for sql, params in conn.queries if "FROM accounting_event_account_mappings" in sql]
    mapping_roles = [params[1] for sql, params in conn.queries if "FROM accounting_event_account_mappings" in sql]
    assert voucher_id == 92
    assert mapping_events == [event_type, event_type]
    assert mapping_roles == ["loyalty_points_liability", offset_role]
    assert posted["header"]["idempotency_key"] == key
    assert posted["header"]["source_type"] == source_type
    assert posted["lines"][0]["account_id"] == 2410
    assert posted["lines"][0]["debit"] == Decimal("12.00")
    assert posted["lines"][1]["account_id"] == 6110
    assert posted["lines"][1]["credit"] == Decimal("12.00")


def test_super_coins_account_migration_is_additive_and_required():
    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    required = (root / "schema_required.txt").read_text()
    migration = (root / "schema" / "028_super_coins_checkout_redemption.sql").read_text().lower()

    assert "028_super_coins_checkout_redemption.sql" in required
    assert "'2410', 'super coins outstanding liability', 'liability'" in migration
    assert "'4210', 'super coins breakage income', 'income'" in migration
    assert "'6110', 'super coins reward expense', 'expense'" in migration
    assert "on conflict (code) do nothing" in migration
    assert "drop table" not in migration
    assert "drop column" not in migration
