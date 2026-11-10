"""Payment records and verified Razorpay Standard Checkout integration."""
from decimal import Decimal
import uuid
import hashlib
import hmac
import json
import httpx

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

router = APIRouter(prefix="/payments", tags=["payments"])
razorpay_router = APIRouter(prefix="/razorpay", tags=["payments"])
PAYMENT_METHODS = {"upi", "card", "netbanking", "cod", "wallet", "bank_transfer", "other"}
PAYMENT_STATUSES = {"pending", "authorized", "captured", "failed", "cancelled", "refunded"}


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Payments database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Payments database is unavailable") from exc


def _db_error(exc):
    if getattr(exc, "sqlstate", None) == "23503":
        return HTTPException(status_code=422, detail="Referenced order does not exist")
    if getattr(exc, "sqlstate", None) == "23505":
        return HTTPException(status_code=409, detail="Payment reference already exists")
    return HTTPException(status_code=503, detail="Payment storage is unavailable; verify the payments migration")


class PaymentCreate(BaseModel):
    order_id: int = Field(gt=0)
    method: str
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    status: str = "pending"
    provider_reference: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("method")
    @classmethod
    def method_allowed(cls, value):
        if value not in PAYMENT_METHODS:
            raise ValueError("Unsupported payment method")
        return value

    @field_validator("status")
    @classmethod
    def status_allowed(cls, value):
        if value != "pending":
            raise ValueError("New payment records must start as pending; provider confirmation is required")
        return value


class PaymentStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_allowed(cls, value):
        if value not in PAYMENT_STATUSES:
            raise ValueError("Unsupported payment status")
        if value in {"authorized", "captured", "refunded"}:
            raise ValueError("Authorized/captured/refunded status requires verified provider confirmation")
        return value


@router.get("")
def list_payments(
    status: str | None = Query(default=None),
    method: str | None = Query(default=None, pattern=r"^(upi|card|netbanking|cod|wallet|bank_transfer|other)$"),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if status and status not in PAYMENT_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported payment status")
    clauses, params = [], []
    if status:
        clauses.append("p.status=%s"); params.append(status)
    if method:
        clauses.append("p.method=%s"); params.append(method)
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(p.payment_reference ILIKE %s OR o.order_number ILIKE %s OR COALESCE(p.provider_reference,'') ILIKE %s)")
        params.extend([term, term, term])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    try:
        with _connect() as conn:
            items = conn.execute(
                "SELECT p.id, p.payment_reference, p.order_id, o.order_number, p.method, p.amount, p.status, "
                "p.provider_reference, p.note, p.created_at, p.updated_at FROM payments p "
                "JOIN orders o ON o.id=p.order_id" + where +
                " ORDER BY p.created_at DESC LIMIT %s OFFSET %s", (*params, limit, offset)
            ).fetchall()
            total = conn.execute("SELECT count(*) AS total FROM payments p JOIN orders o ON o.id=p.order_id" + where, params).fetchone()["total"]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/reconciliation")
def payment_reconciliation():
    """Summarise recorded payment states; this is not a bank or gateway settlement reconciliation."""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT status, count(*) AS payment_count, COALESCE(sum(amount), 0) AS amount "
                "FROM payments GROUP BY status ORDER BY status"
            ).fetchall()
            order_rows = conn.execute(
                "SELECT count(*) AS order_count, COALESCE(sum(total), 0) AS order_value "
                "FROM orders WHERE status <> 'cancelled'"
            ).fetchone()
            captured = conn.execute(
                "SELECT COALESCE(sum(amount), 0) AS amount FROM payments WHERE status='captured'"
            ).fetchone()["amount"]
            refunded = conn.execute(
                "SELECT COALESCE(sum(amount), 0) AS amount FROM payments WHERE status='refunded'"
            ).fetchone()["amount"]
        by_status = {row["status"]: {"count": row["payment_count"], "amount": row["amount"]} for row in rows}
        return {
            "scope": "recorded_application_data_only",
            "gateway_or_bank_reconciled": False,
            "orders": {"count": order_rows["order_count"], "value": order_rows["order_value"]},
            "payments_by_status": by_status,
            "captured_amount_recorded": captured,
            "refunded_amount_recorded": refunded,
            "net_captured_amount_recorded": captured - refunded,
            "note": "Amounts reflect application records only; provider settlement, fees, chargebacks and bank deposits are not verified.",
        }
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("", status_code=201)
def create_payment(payload: PaymentCreate):
    try:
        with _connect() as conn:
            with conn.transaction():
                order = conn.execute("SELECT id, total, status FROM orders WHERE id=%s FOR UPDATE", (payload.order_id,)).fetchone()
                if order is None:
                    raise HTTPException(status_code=404, detail="Order not found")
                if order["status"] == "cancelled":
                    raise HTTPException(status_code=409, detail="Cannot record payment for a cancelled order")
                already_recorded = conn.execute(
                    "SELECT COALESCE(sum(amount), 0) AS amount FROM payments "
                    "WHERE order_id=%s AND status IN ('pending','authorized','captured')",
                    (payload.order_id,),
                ).fetchone()["amount"]
                if Decimal(str(already_recorded)) + payload.amount > Decimal(str(order["total"])):
                    raise HTTPException(status_code=409, detail="Payment amount exceeds the remaining order balance")
                reference = "PAY-" + uuid.uuid4().hex[:12].upper()
                row = conn.execute(
                    "INSERT INTO payments (payment_reference, order_id, method, amount, status, provider_reference, note) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id, payment_reference, order_id, method, amount, status, provider_reference, note, created_at, updated_at",
                    (reference, payload.order_id, payload.method, payload.amount, payload.status, payload.provider_reference, payload.note),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/{payment_id}/status")
def update_payment_status(payment_id: int, payload: PaymentStatusUpdate):
    transitions = {
        "pending": {"authorized", "captured", "failed", "cancelled"},
        "authorized": {"captured", "failed", "cancelled"},
        "captured": {"refunded"},
        "failed": set(), "cancelled": set(), "refunded": set(),
    }
    try:
        with _connect() as conn:
            with conn.transaction():
                current = conn.execute("SELECT status FROM payments WHERE id=%s FOR UPDATE", (payment_id,)).fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Payment record not found")
                old = current["status"]
                if old == payload.status:
                    return {"id": payment_id, "status": old}
                if payload.status == "captured" or payload.status == "refunded":
                    raise HTTPException(status_code=409, detail="Captured/refunded status requires verified provider confirmation")
                if payload.status not in transitions[old]:
                    raise HTTPException(status_code=409, detail=f"Cannot change payment status from {old} to {payload.status}")
                row = conn.execute(
                    "UPDATE payments SET status=%s, updated_at=now() WHERE id=%s RETURNING id, payment_reference, status, updated_at",
                    (payload.status, payment_id),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@razorpay_router.post("/webhook", include_in_schema=False)
async def razorpay_webhook(request: Request):
    """Verify and durably process Razorpay payment lifecycle events."""
    secret = settings.razorpay_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Razorpay webhook is not configured")

    raw_body = await request.body()
    if len(raw_body) > 1_000_000:
        raise HTTPException(status_code=413, detail="Razorpay webhook payload is too large")
    signature = request.headers.get("x-razorpay-signature", "")
    event_id = request.headers.get("x-razorpay-event-id", "").strip()
    if not signature or not event_id or len(event_id) > 200:
        raise HTTPException(status_code=400, detail="Missing Razorpay signature or event id")

    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook signature")

    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook payload") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Razorpay webhook payload")
    event_type = payload.get("event")
    if not isinstance(event_type, str) or len(event_type) > 120:
        raise HTTPException(status_code=400, detail="Invalid Razorpay event type")

    event_payload = payload.get("payload")
    payment_payload = event_payload.get("payment") if isinstance(event_payload, dict) else None
    entity = payment_payload.get("entity") if isinstance(payment_payload, dict) else {}
    if not isinstance(entity, dict):
        entity = {}

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    try:
        with _connect() as conn:
            with conn.transaction():
                event = conn.execute(
                    """INSERT INTO payment_provider_events
                       (provider, provider_event_id, event_type, payload_sha256)
                       VALUES ('razorpay', %s, %s, %s)
                       ON CONFLICT (provider, provider_event_id) DO NOTHING
                       RETURNING id""",
                    (event_id, event_type, payload_hash),
                ).fetchone()
                if event is None:
                    previous = conn.execute(
                        """SELECT payload_sha256 FROM payment_provider_events
                           WHERE provider='razorpay' AND provider_event_id=%s""",
                        (event_id,),
                    ).fetchone()
                    if previous and previous["payload_sha256"] != payload_hash:
                        raise HTTPException(status_code=409, detail="Razorpay event id was reused with a different payload")
                    return Response(status_code=200)

                if event_type not in {"payment.authorized", "payment.captured", "payment.failed"}:
                    conn.execute(
                        "UPDATE payment_provider_events SET processing_status='ignored', processed_at=now() WHERE id=%s",
                        (event["id"],),
                    )
                    return Response(status_code=200)

                provider_order_id = entity.get("order_id")
                provider_payment_id = entity.get("id")
                amount = entity.get("amount")
                currency = entity.get("currency")
                if (not isinstance(provider_order_id, str) or not provider_order_id
                    or not isinstance(provider_payment_id, str) or not provider_payment_id
                    or not isinstance(amount, int) or amount <= 0
                    or currency != "INR"):
                    raise HTTPException(status_code=422, detail="Razorpay payment entity is incomplete or unsupported")

                payment = conn.execute(
                    """SELECT id, order_id, amount, currency, status
                       FROM payments WHERE provider_order_id=%s FOR UPDATE""",
                    (provider_order_id,),
                ).fetchone()
                if payment is None:
                    raise HTTPException(status_code=409, detail="No local payment attempt matches this Razorpay order")
                if (int(Decimal(str(payment["amount"])) * 100) != amount
                    or payment["currency"] != currency):
                    raise HTTPException(status_code=409, detail="Razorpay amount or currency does not match the local payment")

                if event_type == "payment.captured":
                    conn.execute(
                        """UPDATE payments SET status='captured', provider_reference=%s, updated_at=now()
                           WHERE id=%s AND status IN ('pending','authorized','failed','cancelled')""",
                        (provider_payment_id, payment["id"]),
                    )
                    conn.execute(
                        """UPDATE orders SET status='confirmed', updated_at=now()
                           WHERE id=%s AND status='placed'""",
                        (payment["order_id"],),
                    )
                    conn.execute(
                        """INSERT INTO order_status_history (order_id, from_status, to_status)
                           SELECT %s,'placed','confirmed'
                           WHERE EXISTS (SELECT 1 FROM orders WHERE id=%s AND status='confirmed')
                             AND NOT EXISTS (SELECT 1 FROM order_status_history
                                             WHERE order_id=%s AND from_status='placed' AND to_status='confirmed')""",
                        (payment["order_id"], payment["order_id"], payment["order_id"]),
                    )
                elif event_type == "payment.authorized":
                    conn.execute(
                        """UPDATE payments SET status='authorized', provider_reference=%s, updated_at=now()
                           WHERE id=%s AND status='pending'""",
                        (provider_payment_id, payment["id"]),
                    )
                else:
                    conn.execute(
                        """UPDATE payments SET status='failed', provider_reference=%s, updated_at=now()
                           WHERE id=%s AND status='pending'""",
                        (provider_payment_id, payment["id"]),
                    )

                conn.execute(
                    """UPDATE payment_provider_events
                       SET processing_status='processed', payment_id=%s, processed_at=now()
                       WHERE id=%s""",
                    (payment["id"], event["id"]),
                )
        return Response(status_code=200)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class RazorpayOrderCreate(BaseModel):
    order_id: int = Field(gt=0)


class RazorpayPaymentVerify(BaseModel):
    razorpay_order_id: str = Field(min_length=10, max_length=100, pattern=r"^order_[A-Za-z0-9]+$")
    razorpay_payment_id: str = Field(min_length=9, max_length=100, pattern=r"^pay_[A-Za-z0-9]+$")
    razorpay_signature: str = Field(min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")


@razorpay_router.post("/orders")
def create_razorpay_order(payload: RazorpayOrderCreate, request: Request):
    """Create or reuse a Razorpay order without holding a DB transaction over network I/O."""
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Razorpay payments are not configured")
    if getattr(request.state, "role", None) != "customer":
        raise HTTPException(status_code=403, detail="Customer checkout is required")

    lock_key = f"razorpay-order:{payload.order_id}"
    try:
        with _connect() as conn:
            # Session-level lock serializes provider-order creation for one local order.
            # Commit immediately: the lock survives the transaction while the provider is called.
            conn.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (lock_key,))
            conn.commit()
            try:
                with conn.transaction():
                    order = conn.execute(
                        """SELECT id, order_number, customer_email, total, status
                           FROM orders WHERE id=%s FOR UPDATE""",
                        (payload.order_id,),
                    ).fetchone()
                    if order is None:
                        raise HTTPException(status_code=404, detail="Order not found")
                    if str(order["customer_email"] or "").lower() != str(request.state.customer_email).lower():
                        raise HTTPException(status_code=403, detail="Order does not belong to this customer")
                    if order["status"] != "placed":
                        raise HTTPException(status_code=409, detail="Only newly placed orders can start payment")
                    amount_paise = int((Decimal(str(order["total"])) * 100).quantize(Decimal("1")))
                    if amount_paise <= 0:
                        raise HTTPException(status_code=422, detail="Order total must be greater than zero")
                    existing = conn.execute(
                        """SELECT id, provider_order_id FROM payments
                           WHERE order_id=%s AND method='other'
                             AND status IN ('pending','authorized')
                             AND provider_order_id IS NOT NULL
                           ORDER BY id DESC LIMIT 1 FOR UPDATE""",
                        (payload.order_id,),
                    ).fetchone()
                    if existing:
                        return {
                            "key_id": settings.razorpay_key_id,
                            "razorpay_order_id": existing["provider_order_id"],
                            "amount": amount_paise,
                            "currency": "INR",
                            "payment_id": existing["id"],
                            "order_number": order["order_number"],
                        }
                    order_snapshot = dict(order)

                # The provider request is deliberately outside a database transaction.
                receipt = str(order_snapshot["order_number"])[:40]
                try:
                    with httpx.Client(timeout=15.0) as client:
                        response = client.post(
                            "https://api.razorpay.com/v1/orders",
                            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                            json={
                                "amount": amount_paise,
                                "currency": "INR",
                                "receipt": receipt,
                                "notes": {"superbajaar_order_id": str(order_snapshot["id"])},
                            },
                        )
                    response.raise_for_status()
                    provider_order = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    raise HTTPException(status_code=502, detail="Razorpay could not create the payment order") from exc

                provider_order_id = provider_order.get("id")
                if (not isinstance(provider_order_id, str) or not provider_order_id
                    or provider_order.get("amount") != amount_paise
                    or provider_order.get("currency") != "INR"):
                    raise HTTPException(status_code=502, detail="Razorpay returned an invalid order response")

                with conn.transaction():
                    current = conn.execute(
                        "SELECT id, order_number, customer_email, total, status FROM orders WHERE id=%s FOR UPDATE",
                        (payload.order_id,),
                    ).fetchone()
                    if (current is None or current["status"] != "placed"
                        or str(current["customer_email"] or "").lower() != str(request.state.customer_email).lower()
                        or Decimal(str(current["total"])) != Decimal(str(order_snapshot["total"]))):
                        raise HTTPException(status_code=409, detail="Order changed while payment was being initialised")
                    payment_reference = "PAY-" + uuid.uuid4().hex[:12].upper()
                    payment = conn.execute(
                        """INSERT INTO payments
                           (payment_reference, order_id, method, amount, status, provider_order_id, currency, note)
                           VALUES (%s,%s,'other',%s,'pending',%s,'INR','Razorpay Standard Checkout')
                           RETURNING id""",
                        (payment_reference, current["id"], current["total"], provider_order_id),
                    ).fetchone()
                return {
                    "key_id": settings.razorpay_key_id,
                    "razorpay_order_id": provider_order_id,
                    "amount": amount_paise,
                    "currency": "INR",
                    "payment_id": payment["id"],
                    "order_number": order_snapshot["order_number"],
                }
            finally:
                conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (lock_key,))
                conn.commit()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc

@razorpay_router.post("/verify")
async def verify_razorpay_payment(payload: RazorpayPaymentVerify, request: Request):
    """Verify Checkout's HMAC response and confirm the payment with Razorpay's API."""
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Razorpay payments are not configured")
    if getattr(request.state, "role", None) != "customer":
        raise HTTPException(status_code=403, detail="Customer checkout is required")
    message = f"{payload.razorpay_order_id}|{payload.razorpay_payment_id}".encode("utf-8")
    expected = hmac.new(settings.razorpay_key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, payload.razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid Razorpay payment signature")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"https://api.razorpay.com/v1/payments/{payload.razorpay_payment_id}",
                auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            )
        response.raise_for_status()
        provider_payment = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Unable to verify payment with Razorpay") from exc

    if (provider_payment.get("id") != payload.razorpay_payment_id
        or provider_payment.get("order_id") != payload.razorpay_order_id
        or provider_payment.get("currency") != "INR"
        or provider_payment.get("status") != "captured"):
        raise HTTPException(status_code=409, detail="Razorpay has not confirmed a captured payment for this order")

    try:
        with _connect() as conn:
            with conn.transaction():
                payment = conn.execute(
                    """SELECT p.id, p.order_id, p.amount, p.currency, p.status, o.customer_email, o.order_number, o.status AS order_status
                       FROM payments p JOIN orders o ON o.id=p.order_id
                       WHERE p.provider_order_id=%s FOR UPDATE OF p, o""",
                    (payload.razorpay_order_id,),
                ).fetchone()
                if payment is None or str(payment["customer_email"] or "").lower() != str(request.state.customer_email).lower():
                    raise HTTPException(status_code=404, detail="Payment attempt not found")
                if payment["status"] == "refunded":
                    raise HTTPException(status_code=409, detail="This payment is already recorded as refunded; manual reconciliation is required")
                if (int(Decimal(str(payment["amount"])) * 100) != provider_payment.get("amount")
                    or payment["currency"] != provider_payment.get("currency")):
                    raise HTTPException(status_code=409, detail="Payment amount or currency does not match the order")
                conn.execute(
                    """UPDATE payments SET status='captured', provider_reference=%s, updated_at=now()
                       WHERE id=%s AND status <> 'refunded'""",
                    (payload.razorpay_payment_id, payment["id"]),
                )
                # A late capture must be recorded as money received, but it must
                # never resurrect an order that was already cancelled.
                if payment["order_status"] == "placed":
                    conn.execute(
                        """UPDATE orders SET status='confirmed', updated_at=now()
                           WHERE id=%s AND status='placed'""",
                        (payment["order_id"],),
                    )
                    conn.execute(
                        """INSERT INTO order_status_history (order_id, from_status, to_status)
                           SELECT %s,'placed','confirmed'
                           WHERE EXISTS (SELECT 1 FROM orders WHERE id=%s AND status='confirmed')
                             AND NOT EXISTS (SELECT 1 FROM order_status_history
                                             WHERE order_id=%s AND from_status='placed' AND to_status='confirmed')""",
                        (payment["order_id"], payment["order_id"], payment["order_id"]),
                    )
                final_order_status = "confirmed" if payment["order_status"] == "placed" else payment["order_status"]
        return {
            "status": "captured",
            "order_number": payment["order_number"],
            "order_status": final_order_status,
            "refund_required": final_order_status == "cancelled",
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
