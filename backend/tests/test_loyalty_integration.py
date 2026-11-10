"""Transactional Super Coins integration tests against disposable PostgreSQL only."""
import os
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from psycopg.rows import dict_row

from app.services.loyalty_redemption import (
    adjust_account, available_balance, expire_due_coins, redeem_for_order,
    restore_order_redemption,
)

TEST_DB = os.environ.get("SB_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="SB_TEST_DATABASE_URL is not set")
if TEST_DB and ("sb_app" in TEST_DB or "amazonaws" in TEST_DB):
    raise RuntimeError("Refusing to run Super Coins integration tests against a production-like database")


def test_checkout_redemption_restore_adjustment_and_expiry_are_ledger_safe():
    conn = psycopg.connect(TEST_DB, row_factory=dict_row)
    suffix = uuid4().hex
    email = f"coins-{suffix}@test.local"
    order_number = "COINS-" + suffix[:16].upper()
    try:
        account = conn.execute(
            "INSERT INTO loyalty_accounts(customer_email,card_number) VALUES(%s,%s) RETURNING id",
            (email, "SB-" + suffix[:10].upper()),
        ).fetchone()
        account_id = int(account["id"])
        liability = conn.execute(
            "SELECT id FROM accounting_accounts WHERE account_type='liability' AND is_active=TRUE ORDER BY id LIMIT 1"
        ).fetchone()
        expense = conn.execute(
            "SELECT id FROM accounting_accounts WHERE account_type='expense' AND is_active=TRUE ORDER BY id LIMIT 1"
        ).fetchone()
        income = conn.execute(
            "SELECT id FROM accounting_accounts WHERE account_type='income' AND is_active=TRUE ORDER BY id LIMIT 1"
        ).fetchone()
        assert liability and expense and income, "Disposable schema must include active liability, expense and income accounts"
        conn.execute(
            "INSERT INTO accounting_event_account_mappings "
            "(legal_entity_code,source_module,event_type,line_role,account_id,effective_from,status) "
            "VALUES('DEFAULT','loyalty','points_redemption','loyalty_points_liability',%s,%s,'approved')",
            (liability["id"], date.today()),
        )
        conn.execute(
            "INSERT INTO accounting_event_account_mappings "
            "(legal_entity_code,source_module,event_type,line_role,account_id,effective_from,status) "
            "VALUES('DEFAULT','loyalty','points_earned','loyalty_reward_expense',%s,%s,'approved')",
            (expense["id"], date.today()),
        )
        conn.execute(
            "INSERT INTO accounting_event_account_mappings "
            "(legal_entity_code,source_module,event_type,line_role,account_id,effective_from,status) "
            "VALUES('DEFAULT','loyalty','points_earned','loyalty_points_liability',%s,%s,'approved')",
            (liability["id"], date.today()),
        )
        conn.execute(
            "INSERT INTO accounting_event_account_mappings "
            "(legal_entity_code,source_module,event_type,line_role,account_id,effective_from,status) "
            "VALUES('DEFAULT','loyalty','points_expired','loyalty_points_liability',%s,%s,'approved')",
            (liability["id"], date.today()),
        )
        conn.execute(
            "INSERT INTO accounting_event_account_mappings "
            "(legal_entity_code,source_module,event_type,line_role,account_id,effective_from,status) "
            "VALUES('DEFAULT','loyalty','points_expired','loyalty_breakage_income',%s,%s,'approved')",
            (income["id"], date.today()),
        )
        conn.execute(
            "INSERT INTO accounting_event_account_mappings "
            "(legal_entity_code,source_module,event_type,line_role,account_id,effective_from,status) "
            "VALUES('DEFAULT','loyalty','points_adjusted','loyalty_points_liability',%s,%s,'approved')",
            (liability["id"], date.today()),
        )
        conn.execute(
            "INSERT INTO accounting_event_account_mappings "
            "(legal_entity_code,source_module,event_type,line_role,account_id,effective_from,status) "
            "VALUES('DEFAULT','loyalty','points_adjusted','loyalty_adjustment_offset',%s,%s,'approved')",
            (expense["id"], date.today()),
        )
        earn = conn.execute(
            "INSERT INTO loyalty_transactions(account_id,transaction_type,coins,order_reference,description,expires_at,idempotency_key) "
            "VALUES(%s,'earn',100,%s,'Integration-test earned lot',now()+interval '180 days',%s) RETURNING id,expires_at",
            (account_id, order_number, "test-earn:" + suffix),
        ).fetchone()
        order = conn.execute(
            "INSERT INTO orders(order_number,channel,customer_name,customer_email,status,subtotal,total) "
            "VALUES(%s,'website','Test Customer',%s,'placed',100,100) RETURNING id",
            (order_number, email),
        ).fetchone()
        order_id = int(order["id"])

        with conn.transaction():
            result = redeem_for_order(
                conn, customer_email=email, order_id=order_id, order_reference=order_number,
                payable_amount=Decimal("100.00"), requested_coins=70,
            )
        assert result["coins"] == 70
        assert result["discount_amount"] == Decimal("70.00")
        assert available_balance(conn, account_id) == 30

        with pytest.raises(HTTPException) as over_payable:
            redeem_for_order(
                conn, customer_email=email, order_id=order_id, order_reference=order_number,
                payable_amount=Decimal("100.00"), requested_coins=101,
            )
        assert over_payable.value.status_code == 422
        with pytest.raises(HTTPException) as wrong_customer:
            redeem_for_order(
                conn, customer_email=f"other-{suffix}@test.local", order_id=order_id,
                order_reference=order_number, payable_amount=Decimal("100.00"), requested_coins=1,
            )
        assert wrong_customer.value.status_code == 422
        with pytest.raises(HTTPException) as insufficient:
            redeem_for_order(
                conn, customer_email=email, order_id=order_id, order_reference=order_number,
                payable_amount=Decimal("100.00"), requested_coins=31,
            )
        assert insufficient.value.status_code == 422
        with pytest.raises(HTTPException) as duplicate:
            redeem_for_order(
                conn, customer_email=email, order_id=order_id, order_reference=order_number,
                payable_amount=Decimal("100.00"), requested_coins=10,
            )
        assert duplicate.value.status_code == 409

        with conn.transaction():
            restored = restore_order_redemption(conn, order_id=order_id)
        assert restored == {"restored": True, "coins": 70}
        assert available_balance(conn, account_id) == 100
        with conn.transaction():
            replay = restore_order_redemption(conn, order_id=order_id)
        assert replay["duplicate"] is True
        restoration = conn.execute(
            "SELECT t.coins,t.expires_at FROM loyalty_redemption_restorations r "
            "JOIN loyalty_transactions t ON t.id=r.restoration_transaction_id "
            "WHERE r.order_redemption_id=(SELECT id FROM loyalty_order_redemptions WHERE order_id=%s)",
            (order_id,),
        ).fetchone()
        assert restoration["coins"] == 70
        assert restoration["expires_at"] == earn["expires_at"]

        with conn.transaction():
            credit = adjust_account(
                conn, customer_email=email, direction="credit", coins=10,
                reason="Service recovery", idempotency_key="credit-" + suffix,
            )
            debit = adjust_account(
                conn, customer_email=email, direction="debit", coins=5,
                reason="Duplicate credit correction", idempotency_key="debit-" + suffix,
            )
        assert credit["adjusted"] and debit["adjusted"]
        adjustment_vouchers = conn.execute(
            "SELECT count(*) AS n FROM accounting_vouchers WHERE source_type='loyalty_adjustment'"
        ).fetchone()["n"]
        assert adjustment_vouchers == 1
        assert available_balance(conn, account_id) == 105

        conn.execute(
            "INSERT INTO loyalty_transactions(account_id,transaction_type,coins,order_reference,description,expires_at,idempotency_key) "
            "VALUES(%s,'earn',25,%s,'Expired test lot',now()-interval '1 day',%s)",
            (account_id, order_number, "expired-earn:" + suffix),
        )
        with conn.transaction():
            expired = expire_due_coins(conn, limit=10)
        assert expired["expired_coins"] == 25
        expiry_vouchers = conn.execute(
            "SELECT count(*) AS n FROM accounting_vouchers WHERE source_type='loyalty_expiry'"
        ).fetchone()["n"]
        assert expiry_vouchers == 1
        with conn.transaction():
            expiry_replay = expire_due_coins(conn, limit=10)
        assert expiry_replay["expired_coins"] == 0
        assert available_balance(conn, account_id) == 105
    finally:
        conn.rollback()
        conn.close()
