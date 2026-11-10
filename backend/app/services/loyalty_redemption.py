"""Transactional Super Coins ledger operations shared by checkout and administration."""
from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR

from fastapi import HTTPException


COIN_VALUE_IN_RUPEES = Decimal("1")


def _account(conn, email: str, *, lock: bool = False):
    suffix = " FOR UPDATE" if lock else ""
    return conn.execute(
        "SELECT id, customer_email, card_number FROM loyalty_accounts WHERE lower(customer_email)=%s" + suffix,
        (email.strip().lower(),),
    ).fetchone()


def _lot_query(where: str, *, lock: bool = False) -> str:
    sql = (
        "SELECT e.id, e.coins, e.expires_at, e.created_at, "
        "GREATEST(e.coins-COALESCE(r.used,0)-COALESCE(x.expired,0),0)::bigint AS remaining "
        "FROM loyalty_transactions e "
        "LEFT JOIN LATERAL (SELECT SUM(a.coins)::bigint AS used FROM loyalty_redemption_allocations a "
        "WHERE a.earned_transaction_id=e.id) r ON TRUE "
        "LEFT JOIN LATERAL (SELECT SUM(a.coins)::bigint AS expired FROM loyalty_expiration_allocations a "
        "WHERE a.earned_transaction_id=e.id) x ON TRUE "
        "WHERE e.transaction_type='earn' AND " + where +
        " ORDER BY e.created_at ASC,e.id ASC"
    )
    return sql + (" FOR UPDATE OF e" if lock else "")


def available_balance(conn, account_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(GREATEST(e.coins-COALESCE(r.used,0)-COALESCE(x.expired,0),0)),0)::bigint AS balance "
        "FROM loyalty_transactions e "
        "LEFT JOIN LATERAL (SELECT SUM(a.coins)::bigint AS used FROM loyalty_redemption_allocations a "
        "WHERE a.earned_transaction_id=e.id) r ON TRUE "
        "LEFT JOIN LATERAL (SELECT SUM(a.coins)::bigint AS expired FROM loyalty_expiration_allocations a "
        "WHERE a.earned_transaction_id=e.id) x ON TRUE "
        "WHERE e.account_id=%s AND e.transaction_type='earn' AND e.expires_at>now()",
        (account_id,),
    ).fetchone()
    return int(row["balance"] or 0)


def available_lots(conn, account_id: int, *, lock: bool = True) -> list[dict]:
    return conn.execute(
        _lot_query("e.account_id=%s AND e.expires_at>now() AND "
                   "GREATEST(e.coins-COALESCE(r.used,0)-COALESCE(x.expired,0),0)>0", lock=lock),
        (account_id,),
    ).fetchall()


def loyalty_liability_account(conn, event_date=None) -> int:
    """Require exactly one Finance-approved liability mapping for Super Coins redemption."""
    from datetime import date
    day = event_date or date.today()
    try:
        rows = conn.execute(
            "SELECT m.account_id,a.account_type,a.is_active FROM accounting_event_account_mappings m "
            "JOIN accounting_accounts a ON a.id=m.account_id "
            "WHERE m.legal_entity_code='DEFAULT' AND m.source_module='loyalty' "
            "AND m.event_type='points_redemption' AND m.line_role='loyalty_points_liability' "
            "AND m.tax_component IS NULL AND m.status='approved' "
            "AND m.effective_from<=%s AND (m.effective_to IS NULL OR m.effective_to>=%s)",
            (day, day),
        ).fetchall()
    except Exception as exc:
        if getattr(exc, "sqlstate", None) in {"42P01", "42703"}:
            raise HTTPException(409, "Accounting mapping registry is not ready for Super Coins redemption") from exc
        raise
    if len(rows) != 1 or rows[0]["account_type"] != "liability" or not rows[0]["is_active"]:
        raise HTTPException(409, "Finance must approve exactly one active loyalty_points_liability mapping before Super Coins checkout redemption can be used")
    return int(rows[0]["account_id"])


def quote_redemption(conn, email: str, payable_amount: Decimal) -> dict:
    account = _account(conn, email)
    available = available_balance(conn, int(account["id"])) if account else 0
    payable_coins = max(0, int(Decimal(payable_amount).to_integral_value(rounding=ROUND_FLOOR)))
    enabled = False
    reason = None
    if available and payable_coins:
        try:
            loyalty_liability_account(conn)
            enabled = True
        except HTTPException as exc:
            reason = exc.detail
    return {"available_coins": available,
            "maximum_redeemable_coins": min(available, payable_coins) if enabled else 0,
            "coin_value_in_rupees": 1, "redemption_enabled": enabled, "reason": reason}


def redeem_for_order(conn, *, customer_email: str, order_id: int, order_reference: str,
                     payable_amount: Decimal, requested_coins: int) -> dict:
    """Debit earned lots FIFO; caller owns the transaction and order insert."""
    if requested_coins <= 0:
        return {"coins": 0, "discount_amount": Decimal("0.00"), "account_id": None}
    if Decimal(requested_coins) > Decimal(payable_amount):
        raise HTTPException(422, "Requested Super Coins exceed the payable order amount")
    loyalty_liability_account(conn)
    account = _account(conn, customer_email, lock=True)
    if account is None:
        raise HTTPException(422, "No Super Coins balance is available for this customer")
    lots = available_lots(conn, int(account["id"]), lock=True)
    if sum(int(lot["remaining"]) for lot in lots) < requested_coins:
        raise HTTPException(422, "Insufficient unexpired Super Coins")
    key = f"redeem:order:{order_id}"
    if conn.execute("SELECT id FROM loyalty_transactions WHERE idempotency_key=%s", (key,)).fetchone():
        raise HTTPException(409, "Super Coins have already been applied to this order")
    redemption = conn.execute(
        "INSERT INTO loyalty_transactions (account_id,transaction_type,coins,order_reference,description,idempotency_key) "
        "VALUES (%s,'redeem',%s,%s,'Super Coins redeemed at checkout',%s) RETURNING id",
        (account["id"], requested_coins, order_reference, key),
    ).fetchone()
    remaining = requested_coins
    for lot in lots:
        if remaining <= 0:
            break
        take = min(remaining, int(lot["remaining"]))
        conn.execute(
            "INSERT INTO loyalty_redemption_allocations (redemption_transaction_id,earned_transaction_id,coins) VALUES (%s,%s,%s)",
            (redemption["id"], lot["id"], take),
        )
        remaining -= take
    discount = Decimal(requested_coins).quantize(Decimal("0.01"))
    conn.execute(
        "INSERT INTO loyalty_order_redemptions (order_id,account_id,redemption_transaction_id,coins,discount_amount) VALUES (%s,%s,%s,%s,%s)",
        (order_id, account["id"], redemption["id"], requested_coins, discount),
    )
    return {"coins": requested_coins, "discount_amount": discount, "account_id": int(account["id"])}


def restore_order_redemption(conn, *, order_id: int, reason: str = "Eligible order cancellation") -> dict:
    """Restore exact original lots, retaining their original expiry dates."""
    redemption = conn.execute(
        "SELECT r.id,r.account_id,r.redemption_transaction_id,r.status,o.order_number "
        "FROM loyalty_order_redemptions r JOIN orders o ON o.id=r.order_id WHERE r.order_id=%s FOR UPDATE OF r",
        (order_id,),
    ).fetchone()
    if redemption is None:
        return {"restored": False, "coins": 0}
    if redemption.get("status") == "restored":
        return {"restored": False, "duplicate": True, "coins": 0}
    allocations = conn.execute(
        "SELECT a.earned_transaction_id,a.coins,e.expires_at FROM loyalty_redemption_allocations a "
        "JOIN loyalty_transactions e ON e.id=a.earned_transaction_id WHERE a.redemption_transaction_id=%s ORDER BY e.created_at,e.id",
        (redemption["redemption_transaction_id"],),
    ).fetchall()
    restored = 0
    for allocation in allocations:
        key = f"restore:order:{order_id}:earned:{allocation['earned_transaction_id']}"
        row = conn.execute(
            "INSERT INTO loyalty_transactions (account_id,transaction_type,coins,order_reference,description,expires_at,idempotency_key) "
            "VALUES (%s,'earn',%s,%s,%s,%s,%s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
            (redemption["account_id"], allocation["coins"], redemption["order_number"], reason, allocation["expires_at"], key),
        ).fetchone()
        if row is None:
            row = conn.execute("SELECT id FROM loyalty_transactions WHERE idempotency_key=%s", (key,)).fetchone()
        conn.execute(
            "INSERT INTO loyalty_redemption_restorations (order_redemption_id,earned_transaction_id,restoration_transaction_id,coins) "
            "VALUES (%s,%s,%s,%s) ON CONFLICT (order_redemption_id,earned_transaction_id) DO NOTHING",
            (redemption["id"], allocation["earned_transaction_id"], row["id"], allocation["coins"]),
        )
        restored += int(allocation["coins"])
    conn.execute("UPDATE loyalty_order_redemptions SET status='restored',restored_at=now() WHERE id=%s AND status='redeemed'", (redemption["id"],))
    return {"restored": True, "coins": restored}


def adjust_account(conn, *, customer_email: str, direction: str, coins: int, reason: str, idempotency_key: str) -> dict:
    account = _account(conn, customer_email, lock=True)
    if account is None:
        raise HTTPException(404, "Loyalty account not found")
    key = "admin-adjust:" + idempotency_key.strip()
    prior = conn.execute("SELECT id FROM loyalty_transactions WHERE idempotency_key=%s", (key,)).fetchone()
    if prior:
        return {"adjusted": False, "duplicate": True, "transaction_id": prior["id"]}
    if direction == "credit":
        row = conn.execute(
            "INSERT INTO loyalty_transactions (account_id,transaction_type,coins,description,expires_at,idempotency_key) VALUES (%s,'earn',%s,%s,now()+interval '365 days',%s) RETURNING id",
            (account["id"], coins, "Administrative credit: " + reason.strip(), key),
        ).fetchone()
        from app.services.loyalty_accounting import post_earning_accrual
        post_earning_accrual(conn, int(row["id"]))
        return {"adjusted": True, "direction": direction, "coins": coins, "transaction_id": row["id"]}
    lots = available_lots(conn, int(account["id"]), lock=True)
    if sum(int(lot["remaining"]) for lot in lots) < coins:
        raise HTTPException(422, "Administrative debit exceeds the customer's available unexpired balance")
    row = conn.execute(
        "INSERT INTO loyalty_transactions (account_id,transaction_type,coins,description,idempotency_key) VALUES (%s,'adjustment',%s,%s,%s) RETURNING id",
        (account["id"], coins, "Administrative debit: " + reason.strip(), key),
    ).fetchone()
    remaining = coins
    for lot in lots:
        if remaining <= 0:
            break
        take = min(remaining, int(lot["remaining"]))
        conn.execute("INSERT INTO loyalty_redemption_allocations (redemption_transaction_id,earned_transaction_id,coins) VALUES (%s,%s,%s)",
                     (row["id"], lot["id"], take))
        remaining -= take
    from app.services.loyalty_accounting import post_debit_adjustment
    post_debit_adjustment(conn, int(row["id"]))
    return {"adjusted": True, "direction": direction, "coins": coins, "transaction_id": row["id"]}


def expire_due_coins(conn, *, limit: int = 200) -> dict:
    account_ids = conn.execute(
        "SELECT a.id FROM loyalty_accounts a WHERE EXISTS (SELECT 1 FROM loyalty_transactions e "
        "WHERE e.account_id=a.id AND e.transaction_type='earn' AND e.expires_at<=now()) ORDER BY a.id LIMIT %s",
        (limit,),
    ).fetchall()
    expired_total = 0
    expired_lots = 0
    for item in account_ids:
        account_id = int(item["id"])
        conn.execute("SELECT id FROM loyalty_accounts WHERE id=%s FOR UPDATE", (account_id,))
        lots = conn.execute(
            _lot_query("e.account_id=%s AND e.expires_at<=now() AND GREATEST(e.coins-COALESCE(r.used,0)-COALESCE(x.expired,0),0)>0", lock=True),
            (account_id,),
        ).fetchall()
        for lot in lots:
            coins = int(lot["remaining"])
            key = f"expire:earned:{lot['id']}"
            row = conn.execute(
                "INSERT INTO loyalty_transactions (account_id,transaction_type,coins,order_reference,description,idempotency_key) "
                "VALUES (%s,'expire',%s,NULL,'Expired unspent Super Coins',%s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
                (account_id, coins, key),
            ).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO loyalty_expiration_allocations (expiration_transaction_id,earned_transaction_id,coins) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (row["id"], lot["id"], coins),
                )
                from app.services.loyalty_accounting import post_expiration_release
                post_expiration_release(conn, int(row["id"]))
                expired_total += coins
                expired_lots += 1
    return {"expired_coins": expired_total, "expired_lots": expired_lots}
