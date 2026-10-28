"""Loyalty rules, FIFO coin ledger and partner enquiry API."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_FLOOR
import secrets

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, EmailStr, Field

from app.core.config import settings

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


def _connection():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Loyalty database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Loyalty database is unavailable") from exc


def _admin(request: Request):
    if getattr(request.state, "role", "") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Administrator access required")


class RuleUpdate(BaseModel):
    scope_type: str = Field(pattern=r"^(default|category|product)$")
    scope_id: int | None = Field(default=None, gt=0)
    coins_per_100: Decimal = Field(ge=0, le=100000)
    is_active: bool = True


class EarnCoins(BaseModel):
    customer_email: EmailStr
    order_reference: str = Field(min_length=1, max_length=120)
    eligible_amount: Decimal = Field(gt=0, le=1000000000)
    delivered_at: datetime
    description: str | None = Field(default=None, max_length=300)


class RedeemCoins(BaseModel):
    customer_email: EmailStr
    coins: int = Field(gt=0, le=10000000)
    order_reference: str = Field(min_length=1, max_length=120)


class PartnerEnquiry(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    business_name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=7, max_length=20)
    email: EmailStr
    partnership_type: str = Field(pattern=r"^(Seller|Brand|Supplier|Delivery / logistics|Other)$")
    message: str = Field(min_length=1, max_length=3000)


@router.get("/rules")
def get_rules():
    """Public storefront earning rules; most specific rules are applied first."""
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT scope_type, scope_id, coins_per_100, is_active FROM loyalty_rules "
                "WHERE is_active = TRUE ORDER BY CASE scope_type WHEN 'product' THEN 1 WHEN 'category' THEN 2 ELSE 3 END, scope_id"
            ).fetchall()
            default_rule = conn.execute(
                "SELECT coins_per_100 FROM loyalty_rules WHERE scope_type='default' AND scope_id IS NULL AND is_active=TRUE"
            ).fetchone()
        default_rate = str(default_rule["coins_per_100"]) if default_rule else "0"
        return {"items": rows, "default_coins_per_100": default_rate, "expiry_days": 365, "redemption_order": "FIFO"}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load loyalty rules") from exc


@router.get("/admin/rules")
def get_admin_rules(request: Request):
    """Administrator view of all earning rules, including inactive rules."""
    _admin(request)
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT id, scope_type, scope_id, coins_per_100, is_active, created_at, updated_at "
                "FROM loyalty_rules ORDER BY CASE scope_type WHEN 'default' THEN 1 WHEN 'category' THEN 2 ELSE 3 END, scope_id"
            ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load loyalty rules") from exc


@router.get("/customer/account")
def get_customer_loyalty_account(
    email: EmailStr = Query(),
    order_reference: str = Query(min_length=1, max_length=40),
):
    """Read a customer's loyalty card and ledger after verifying a prior order reference and email."""
    normalized_email = str(email).strip().lower()
    reference = order_reference.strip().upper()
    try:
        with _connection() as conn:
            verified_order = conn.execute(
                "SELECT id FROM orders WHERE upper(order_number)=%s AND lower(customer_email)=%s",
                (reference, normalized_email),
            ).fetchone()
            if verified_order is None:
                raise HTTPException(status_code=404, detail="We could not verify that order reference and email combination")
            account = conn.execute(
                "SELECT id, customer_email, card_number, created_at FROM loyalty_accounts WHERE customer_email=%s",
                (normalized_email,),
            ).fetchone()
            if account is None:
                return {
                    "account": None,
                    "available_coins": 0,
                    "items": [],
                    "message": "Your order is verified. A loyalty card and coins appear after an eligible order is marked delivered.",
                }
            balance = conn.execute(
                "SELECT COALESCE(SUM(GREATEST(e.coins - COALESCE(a.used,0),0)),0)::bigint AS available_coins "
                "FROM loyalty_transactions e "
                "LEFT JOIN LATERAL (SELECT SUM(x.coins)::bigint AS used FROM loyalty_redemption_allocations x "
                "WHERE x.earned_transaction_id=e.id) a ON TRUE "
                "WHERE e.account_id=%s AND e.transaction_type='earn' AND e.expires_at>now()",
                (account["id"],),
            ).fetchone()
            rows = conn.execute(
                "SELECT id, transaction_type, coins, order_reference, description, expires_at, created_at "
                "FROM loyalty_transactions WHERE account_id=%s ORDER BY created_at DESC, id DESC LIMIT 100",
                (account["id"],),
            ).fetchall()
        return {
            "account": account,
            "available_coins": int(balance["available_coins"] or 0),
            "items": rows,
            "message": "Loyalty account loaded.",
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load loyalty account") from exc


@router.get("/customer/me")
def get_my_loyalty_account(request: Request):
    """Return only the signed-in customer's own loyalty card and coin ledger."""
    email = str(getattr(request.state, "customer_email", "")).strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    try:
        with _connection() as conn:
            account = conn.execute(
                "SELECT id, customer_email, card_number, created_at FROM loyalty_accounts WHERE customer_email=%s",
                (email,),
            ).fetchone()
            if account is None:
                return {"account": None, "available_coins": 0, "items": [], "coin_value_in_rupees": 1}
            balance = conn.execute(
                "SELECT COALESCE(SUM(GREATEST(e.coins - COALESCE(a.used,0),0)),0)::bigint AS available_coins "
                "FROM loyalty_transactions e LEFT JOIN LATERAL ("
                "SELECT SUM(x.coins)::bigint AS used FROM loyalty_redemption_allocations x "
                "WHERE x.earned_transaction_id=e.id) a ON TRUE "
                "WHERE e.account_id=%s AND e.transaction_type='earn' AND e.expires_at>now()",
                (account["id"],),
            ).fetchone()
            rows = conn.execute(
                "SELECT id, transaction_type, coins, order_reference, description, expires_at, created_at "
                "FROM loyalty_transactions WHERE account_id=%s ORDER BY created_at DESC, id DESC LIMIT 100",
                (account["id"],),
            ).fetchall()
        return {
            "account": account,
            "available_coins": int(balance["available_coins"] or 0),
            "coin_value_in_rupees": 1,
            "items": rows,
        }
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load loyalty account") from exc


@router.get("/quote")
def quote_coins(amount: Decimal = Query(gt=0), product_id: int | None = Query(default=None, gt=0), category_id: int | None = Query(default=None, gt=0)):
    """Quote estimated coins from configured product/category/default rules."""
    try:
        with _connection() as conn:
            rule = None
            if product_id is not None:
                rule = conn.execute(
                    "SELECT coins_per_100 FROM loyalty_rules WHERE scope_type='product' AND scope_id=%s AND is_active=TRUE",
                    (product_id,),
                ).fetchone()
            if rule is None and category_id is not None:
                rule = conn.execute(
                    "SELECT coins_per_100 FROM loyalty_rules WHERE scope_type='category' AND scope_id=%s AND is_active=TRUE",
                    (category_id,),
                ).fetchone()
            if rule is None:
                rule = conn.execute(
                    "SELECT coins_per_100 FROM loyalty_rules WHERE scope_type='default' AND is_active=TRUE AND scope_id IS NULL"
                ).fetchone()
        rate = Decimal(str(rule["coins_per_100"])) if rule else Decimal("1")
        coins = int((amount / Decimal("100") * rate).to_integral_value(rounding=ROUND_FLOOR))
        return {"eligible_amount": str(amount), "coins": coins, "coins_per_100": str(rate)}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not calculate loyalty coins") from exc


@router.put("/rules")
def upsert_rule(payload: RuleUpdate, request: Request):
    _admin(request)
    if (payload.scope_type == "default") != (payload.scope_id is None):
        raise HTTPException(status_code=422, detail="Default rules must have no scope_id; product/category rules require scope_id")
    try:
        with _connection() as conn:
            row = conn.execute(
                "INSERT INTO loyalty_rules (scope_type, scope_id, coins_per_100, is_active) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (scope_type, (COALESCE(scope_id, 0))) DO UPDATE SET coins_per_100=EXCLUDED.coins_per_100, "
                "is_active=EXCLUDED.is_active, updated_at=now() "
                "RETURNING id, scope_type, scope_id, coins_per_100, is_active, updated_at",
                (payload.scope_type, payload.scope_id, payload.coins_per_100, payload.is_active),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not save loyalty rule") from exc


def _account(conn, email: str):
    normalized = email.strip().lower()
    row = conn.execute("SELECT id, customer_email, card_number FROM loyalty_accounts WHERE customer_email=%s FOR UPDATE", (normalized,)).fetchone()
    if row:
        return row
    card = "SB-" + secrets.token_hex(5).upper()
    return conn.execute(
        "INSERT INTO loyalty_accounts (customer_email, card_number) VALUES (%s,%s) RETURNING id, customer_email, card_number",
        (normalized, card),
    ).fetchone()


@router.post("/admin/earn")
def earn_coins(payload: EarnCoins, request: Request):
    """Admin-only, idempotent credit for a confirmed delivered order."""
    _admin(request)
    if payload.delivered_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="delivered_at must include a timezone")
    try:
        with _connection() as conn:
            account = _account(conn, str(payload.customer_email))
            rule = conn.execute(
                "SELECT coins_per_100 FROM loyalty_rules WHERE scope_type='default' AND scope_id IS NULL AND is_active=TRUE"
            ).fetchone()
            rate = Decimal(str(rule["coins_per_100"])) if rule else Decimal("1")
            coins = int((payload.eligible_amount / Decimal("100") * rate).to_integral_value(rounding=ROUND_FLOOR))
            if coins < 1:
                return {"credited": False, "coins": 0, "message": "Eligible order amount does not earn a whole coin at the configured rate"}
            key = "earn:" + payload.order_reference.strip()
            row = conn.execute(
                "INSERT INTO loyalty_transactions (account_id, transaction_type, coins, order_reference, description, expires_at, idempotency_key) "
                "VALUES (%s,'earn',%s,%s,%s,%s,%s) ON CONFLICT (idempotency_key) DO NOTHING "
                "RETURNING id, coins, expires_at, created_at",
                (account["id"], coins, payload.order_reference.strip(), payload.description or "Delivered order reward",
                 payload.delivered_at.astimezone(timezone.utc) + timedelta(days=365),
                 key),
            ).fetchone()
            if row is None:
                return {"credited": False, "duplicate": True, "message": "Coins for this order have already been processed"}
        return {"credited": True, "card_number": account["card_number"], "coins": coins, "expires_at": row["expires_at"]}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not credit loyalty coins") from exc


@router.post("/admin/redeem")
def redeem_coins(payload: RedeemCoins, request: Request):
    """Admin-only redemption allocated against oldest unexpired earn lots first."""
    _admin(request)
    try:
        with _connection() as conn:
            account = conn.execute(
                "SELECT id, customer_email, card_number FROM loyalty_accounts WHERE customer_email=%s FOR UPDATE",
                (str(payload.customer_email).strip().lower(),),
            ).fetchone()
            if account is None:
                raise HTTPException(status_code=404, detail="Loyalty account not found")
            prior = conn.execute(
                "SELECT id, coins FROM loyalty_transactions WHERE idempotency_key=%s",
                ("redeem:" + payload.order_reference.strip(),),
            ).fetchone()
            if prior:
                return {"redeemed": False, "duplicate": True, "message": "This redemption has already been processed"}
            lots = conn.execute(
                "SELECT e.id, e.coins - COALESCE(SUM(a.coins),0) AS remaining FROM loyalty_transactions e "
                "LEFT JOIN loyalty_redemption_allocations a ON a.earned_transaction_id=e.id "
                "WHERE e.account_id=%s AND e.transaction_type='earn' AND e.expires_at>now() "
                "GROUP BY e.id,e.coins,e.created_at HAVING e.coins-COALESCE(SUM(a.coins),0)>0 "
                "ORDER BY e.created_at ASC,e.id ASC FOR UPDATE OF e",
                (account["id"],),
            ).fetchall()
            available = sum(int(lot["remaining"]) for lot in lots)
            if available < payload.coins:
                raise HTTPException(status_code=422, detail="Insufficient unexpired Super Coins")
            redemption = conn.execute(
                "INSERT INTO loyalty_transactions (account_id, transaction_type, coins, order_reference, description, idempotency_key) "
                "VALUES (%s,'redeem',%s,%s,'Super Coins redemption',%s) RETURNING id",
                (account["id"], payload.coins, payload.order_reference.strip(), "redeem:" + payload.order_reference.strip()),
            ).fetchone()
            remaining = payload.coins
            for lot in lots:
                if remaining <= 0:
                    break
                take = min(remaining, int(lot["remaining"]))
                conn.execute(
                    "INSERT INTO loyalty_redemption_allocations (redemption_transaction_id, earned_transaction_id, coins) VALUES (%s,%s,%s)",
                    (redemption["id"], lot["id"], take),
                )
                remaining -= take
        return {"redeemed": True, "coins": payload.coins, "fifo": True}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not redeem loyalty coins") from exc


@router.get("/admin/accounts")
def list_loyalty_accounts(request: Request, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    """Admin-only account list with unexpired available balance."""
    _admin(request)
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT a.id, a.customer_email, a.card_number, a.created_at, "
                "COALESCE(SUM(CASE WHEN e.transaction_type='earn' AND e.expires_at>now() "
                "THEN e.coins - COALESCE(alloc.used,0) ELSE 0 END),0)::bigint AS available_coins "
                "FROM loyalty_accounts a LEFT JOIN loyalty_transactions e ON e.account_id=a.id "
                "LEFT JOIN LATERAL (SELECT SUM(x.coins)::bigint AS used FROM loyalty_redemption_allocations x "
                "WHERE x.earned_transaction_id=e.id) alloc ON TRUE "
                "GROUP BY a.id ORDER BY a.created_at DESC LIMIT %s OFFSET %s", (limit, offset)
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load loyalty accounts") from exc


@router.get("/admin/accounts/{account_id}/transactions")
def list_loyalty_transactions(account_id: int, request: Request, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    """Admin-only ledger history for a loyalty account."""
    _admin(request)
    try:
        with _connection() as conn:
            account = conn.execute(
                "SELECT id, customer_email, card_number, created_at FROM loyalty_accounts WHERE id=%s",
                (account_id,),
            ).fetchone()
            if account is None:
                raise HTTPException(status_code=404, detail="Loyalty account not found")
            rows = conn.execute(
                "SELECT id, transaction_type, coins, order_reference, description, expires_at, created_at "
                "FROM loyalty_transactions WHERE account_id=%s ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                (account_id, limit, offset),
            ).fetchall()
        return {"account": account, "items": rows, "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load loyalty transactions") from exc


@router.post("/partner-enquiries", status_code=201)
def create_partner_enquiry(payload: PartnerEnquiry):
    try:
        with _connection() as conn:
            row = conn.execute(
                "INSERT INTO partner_enquiries (name,business_name,phone,email,partnership_type,message) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, status, created_at",
                (payload.name.strip(), payload.business_name.strip(), payload.phone.strip(),
                 str(payload.email).lower(), payload.partnership_type, payload.message.strip()),
            ).fetchone()
        return {"id": row["id"], "status": row["status"], "message": "Thank you. Your partnership enquiry has been received."}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not save partnership enquiry") from exc


@router.get("/admin/partner-enquiries")
def list_partner_enquiries(request: Request, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    _admin(request)
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT id,name,business_name,phone,email,partnership_type,message,status,created_at,updated_at "
                "FROM partner_enquiries ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, offset)
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load partnership enquiries") from exc
