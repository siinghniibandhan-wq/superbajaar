"""Finance-approved accounting postings for Super Coins ledger events."""
from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException


COIN_VALUE_IN_RUPEES = Decimal("1.00")


def _approved_account(conn, *, event_type: str, line_role: str, expected_type: str | tuple[str, ...], event_date):
    rows = conn.execute(
        "SELECT m.account_id,a.account_type,a.is_active "
        "FROM accounting_event_account_mappings m "
        "JOIN accounting_accounts a ON a.id=m.account_id "
        "WHERE m.legal_entity_code='DEFAULT' AND m.source_module='loyalty' "
        "AND m.event_type=%s AND m.line_role=%s AND m.tax_component IS NULL "
        "AND m.status='approved' AND m.effective_from<=%s "
        "AND (m.effective_to IS NULL OR m.effective_to>=%s)",
        (event_type, line_role, event_date, event_date),
    ).fetchall()
    allowed_types = (expected_type,) if isinstance(expected_type, str) else expected_type
    if len(rows) != 1 or rows[0]["account_type"] not in allowed_types or not rows[0]["is_active"]:
        expected_label = " or ".join(allowed_types)
        raise HTTPException(
            409,
            f"Finance must approve exactly one active {expected_label} mapping for loyalty/{event_type}/{line_role}",
        )
    return int(rows[0]["account_id"])


def post_earning_accrual(conn, transaction_id: int) -> int | None:
    """Accrue an earned coin lot as expense and liability in the same transaction."""
    earned = conn.execute(
        "SELECT t.id,t.coins,t.created_at,t.idempotency_key,a.customer_email "
        "FROM loyalty_transactions t JOIN loyalty_accounts a ON a.id=t.account_id "
        "WHERE t.id=%s AND t.transaction_type='earn'",
        (transaction_id,),
    ).fetchone()
    if earned is None:
        raise HTTPException(404, "Earned Super Coins transaction not found")
    # Cancellation restoration reverses a redeemed balance; the cancellation
    # voucher reverses the original liability settlement, so do not accrue twice.
    if str(earned.get("idempotency_key") or "").startswith("restore:"):
        return None

    from app.api import accounting

    event_date = accounting._ist_date(earned["created_at"])
    expense_id = _approved_account(
        conn, event_type="points_earned", line_role="loyalty_reward_expense",
        expected_type="expense", event_date=event_date,
    )
    liability_id = _approved_account(
        conn, event_type="points_earned", line_role="loyalty_points_liability",
        expected_type="liability", event_date=event_date,
    )
    amount = (Decimal(int(earned["coins"])) * COIN_VALUE_IN_RUPEES).quantize(Decimal("0.01"))
    key = f"loyalty-earning:{transaction_id}"
    prior = conn.execute(
        "SELECT id FROM accounting_vouchers WHERE idempotency_key=%s", (key,)
    ).fetchone()
    if prior:
        return int(prior["id"])
    return accounting._post_voucher(
        conn,
        {
            "voucher_type": "journal",
            "voucher_date": event_date,
            "narration": f"Super Coins earned by {earned['customer_email']}",
            "reference": f"LOYALTY-EARN-{transaction_id}",
            "total_amount": amount,
            "source_type": "loyalty_earning",
            "source_id": str(transaction_id),
            "idempotency_key": key,
        },
        [
            {"account_id": expense_id, "debit": amount, "credit": 0,
             "narration": "Super Coins reward expense"},
            {"account_id": liability_id, "debit": 0, "credit": amount,
             "narration": "Super Coins outstanding liability"},
        ],
        (None, "system:loyalty"),
    )


def post_expiration_release(conn, transaction_id: int) -> int:
    """Release expired coin liability only under Finance-approved breakage mappings."""
    expired = conn.execute(
        "SELECT t.id,t.coins,t.created_at FROM loyalty_transactions t "
        "WHERE t.id=%s AND t.transaction_type='expire'",
        (transaction_id,),
    ).fetchone()
    if expired is None:
        raise HTTPException(404, "Expired Super Coins transaction not found")
    from app.api import accounting

    event_date = accounting._ist_date(expired["created_at"])
    liability_id = _approved_account(
        conn, event_type="points_expired", line_role="loyalty_points_liability",
        expected_type="liability", event_date=event_date,
    )
    breakage_id = _approved_account(
        conn, event_type="points_expired", line_role="loyalty_breakage_income",
        expected_type="income", event_date=event_date,
    )
    amount = (Decimal(int(expired["coins"])) * COIN_VALUE_IN_RUPEES).quantize(Decimal("0.01"))
    key = f"loyalty-expiry:{transaction_id}"
    prior = conn.execute(
        "SELECT id FROM accounting_vouchers WHERE idempotency_key=%s", (key,)
    ).fetchone()
    if prior:
        return int(prior["id"])
    return accounting._post_voucher(
        conn,
        {
            "voucher_type": "journal",
            "voucher_date": event_date,
            "narration": f"Super Coins expiry breakage for transaction {transaction_id}",
            "reference": f"LOYALTY-EXPIRY-{transaction_id}",
            "total_amount": amount,
            "source_type": "loyalty_expiry",
            "source_id": str(transaction_id),
            "idempotency_key": key,
        },
        [
            {"account_id": liability_id, "debit": amount, "credit": 0,
             "narration": "Release expired Super Coins liability"},
            {"account_id": breakage_id, "debit": 0, "credit": amount,
             "narration": "Expired Super Coins breakage income"},
        ],
        (None, "system:loyalty"),
    )


def post_debit_adjustment(conn, transaction_id: int) -> int:
    """Post admin debits with distinct accounting for manual redemption vs correction."""
    debit = conn.execute(
        "SELECT t.id,t.coins,t.created_at,t.transaction_type,a.customer_email "
        "FROM loyalty_transactions t JOIN loyalty_accounts a ON a.id=t.account_id "
        "WHERE t.id=%s AND t.transaction_type IN ('adjustment','redeem')",
        (transaction_id,),
    ).fetchone()
    if debit is None:
        raise HTTPException(404, "Super Coins debit transaction not found")
    from app.api import accounting

    event_date = accounting._ist_date(debit["created_at"])
    transaction_type = debit["transaction_type"]
    if transaction_type == "redeem":
        # A manually fulfilled redemption settles the liability against the
        # approved reward expense account. Website checkout redemptions are
        # settled in the sales voucher and do not pass through this function.
        event_type = "points_redeemed_admin"
        offset_role = "loyalty_reward_expense"
        narration = f"Manual Super Coins redemption for {debit['customer_email']}"
        reference = f"LOYALTY-MANUAL-REDEEM-{transaction_id}"
        source_type = "loyalty_manual_redemption"
        key = f"loyalty-manual-redemption:{transaction_id}"
        offset_narration = "Recognise manually redeemed Super Coins against reward expense"
    else:
        # An administrative correction removes an erroneous/unearned reward
        # and reverses the corresponding reward expense, not breakage income.
        event_type = "points_adjusted"
        offset_role = "loyalty_adjustment_offset"
        narration = f"Super Coins administrative correction for {debit['customer_email']}"
        reference = f"LOYALTY-ADJUST-{transaction_id}"
        source_type = "loyalty_adjustment"
        key = f"loyalty-adjustment:{transaction_id}"
        offset_narration = "Reverse reward expense for administrative correction"

    liability_id = _approved_account(
        conn, event_type=event_type, line_role="loyalty_points_liability",
        expected_type="liability", event_date=event_date,
    )
    offset_id = _approved_account(
        conn, event_type=event_type, line_role=offset_role,
        expected_type="expense", event_date=event_date,
    )
    amount = (Decimal(int(debit["coins"])) * COIN_VALUE_IN_RUPEES).quantize(Decimal("0.01"))
    prior = conn.execute(
        "SELECT id FROM accounting_vouchers WHERE idempotency_key=%s", (key,)
    ).fetchone()
    if prior:
        return int(prior["id"])
    return accounting._post_voucher(
        conn,
        {
            "voucher_type": "journal",
            "voucher_date": event_date,
            "narration": narration,
            "reference": reference,
            "total_amount": amount,
            "source_type": source_type,
            "source_id": str(transaction_id),
            "idempotency_key": key,
        },
        [
            {"account_id": liability_id, "debit": amount, "credit": 0,
             "narration": "Reduce Super Coins outstanding liability"},
            {"account_id": offset_id, "debit": 0, "credit": amount,
             "narration": offset_narration},
        ],
        (None, "system:loyalty"),
    )
