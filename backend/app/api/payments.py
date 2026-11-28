"""Payment records and verified Razorpay Standard Checkout integration."""
from decimal import Decimal
import uuid
import hashlib
import hmac
import json
import httpx

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.services.pos_tender import order_is_fully_paid
from app.services.order_inventory import consume_pos_order_stock

router = APIRouter(prefix="/payments", tags=["payments"])
razorpay_router = APIRouter(prefix="/razorpay", tags=["payments"])
PAYMENT_METHODS = {"upi", "card", "netbanking", "cod", "wallet", "bank_transfer", "other"}
PAYMENT_STATUSES = {"pending", "authorized", "captured", "failed", "cancelled", "refunded"}


def payment_payload_sha256(payload: dict) -> str:
    """Canonical hash used to reject key reuse with a different payment payload."""
    normalized = {
        key: (format(value, "f") if isinstance(value, Decimal) else value)
        for key, value in payload.items()
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _payment_idempotency_scope(actor_id: int, key: str) -> str:
    return hashlib.sha256(f"payment:{actor_id}:{key}".encode("utf-8")).hexdigest()


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


class PaymentRefundCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    note: str = Field(min_length=3, max_length=500)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A refund reason is required")
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


@router.post("/{payment_id}/refunds", status_code=201)
def create_payment_refund(
    payment_id: int,
    payload: PaymentRefundCreate,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
):
    """Create a verified Razorpay partial/full refund with a durable idempotency record."""
    role = getattr(request.state, "role", None)
    actor_id = getattr(request.state, "user_id", None)
    actor_email = getattr(request.state, "user_email", None)
    if role not in {"manager", "admin", "super_admin"} or not actor_id or not actor_email:
        raise HTTPException(status_code=403, detail="A manager or administrator session is required to refund a payment")
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Razorpay refunds are not configured")
    try:
        with _connect() as conn:
            conn.execute("SELECT pg_advisory_lock(hashtextextended(%s,0))", (lock_key,))
            conn.commit()
            try:
                with conn.transaction():
                    previous = conn.execute(
                        "SELECT id,payment_id,amount,status,provider_refund_id,note FROM payment_refunds WHERE idempotency_key=%s FOR UPDATE",
                        (idempotency_key,),
                    ).fetchone()
                    if previous:
                        if int(previous["payment_id"]) != payment_id or Decimal(str(previous["amount"])) != payload.amount or previous["note"] != payload.note:
                            raise HTTPException(status_code=409, detail="Refund idempotency key was reused with different details")
                        if previous["status"] == "processed":
                            return previous
                        raise HTTPException(status_code=409, detail="This refund attempt is pending provider reconciliation; do not retry it with a new key")
                    payment = conn.execute(
                        "SELECT id,order_id,amount,status,method,provider_reference FROM payments WHERE id=%s FOR UPDATE",
                        (payment_id,),
                    ).fetchone()
                    if payment is None:
                        raise HTTPException(status_code=404, detail="Payment not found")
                    if payment["status"] not in {"captured", "refunded"} or not payment["provider_reference"]:
                        raise HTTPException(status_code=409, detail="Only a captured Razorpay payment can be refunded through this endpoint")
                    refunded = conn.execute(
                        "SELECT COALESCE(sum(amount),0) AS amount FROM payment_refunds WHERE payment_id=%s AND status IN ('processed','pending')",
                        (payment_id,),
                    ).fetchone()["amount"]
                    remaining = Decimal(str(payment["amount"])) - Decimal(str(refunded))
                    if payload.amount > remaining:
                        raise HTTPException(status_code=422, detail=f"Refund exceeds the remaining refundable amount {remaining}")
                    refund = conn.execute(
                        """INSERT INTO payment_refunds(payment_id,order_id,amount,status,idempotency_key,note,created_by_user_id,created_by_email)
                           VALUES(%s,%s,%s,'pending',%s,%s,%s,%s)
                           RETURNING id,payment_id,order_id,amount,status,idempotency_key,note,created_at""",
                        (payment_id,payment["order_id"],payload.amount,shift_id,idempotency_key,payload.note,int(actor_id),str(actor_email)),
                    ).fetchone()
                    provider_payment_id = payment["provider_reference"]
                amount_paise = int((payload.amount * 100).quantize(Decimal("1")))
                try:
                    with httpx.Client(timeout=20.0) as client:
                        response = client.post(
                            f"https://api.razorpay.com/v1/payments/{provider_payment_id}/refund",
                            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
                            json={"amount": amount_paise, "notes": {"superbajaar_refund_id": str(refund["id"]), "reason": payload.note}},
                        )
                    response.raise_for_status()
                    provider_refund = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    # Keep the attempt pending: a timeout may have happened after the provider accepted it.
                    raise HTTPException(status_code=502, detail="Razorpay refund outcome is pending reconciliation; do not submit a new refund") from exc
                provider_status = provider_refund.get("status")
                if (not isinstance(provider_refund.get("id"), str) or not provider_refund.get("id")
                    or provider_refund.get("amount") != amount_paise
                    or provider_refund.get("payment_id") != provider_payment_id
                    or provider_status not in {"processed", "pending", "failed"}):
                    raise HTTPException(status_code=502, detail="Razorpay returned an invalid refund response; reconcile before retrying")
                local_status = provider_status
                with conn.transaction():
                    saved = conn.execute(
                        """UPDATE payment_refunds SET status=%s,provider_refund_id=%s,updated_at=now()
                           WHERE id=%s AND status='pending'
                           RETURNING id,payment_id,order_id,amount,status,provider_refund_id,idempotency_key,note,created_at""",
                        (local_status,provider_refund["id"],refund["id"]),
                    ).fetchone()
                    total_refunded = conn.execute(
                        "SELECT COALESCE(sum(amount),0) AS amount FROM payment_refunds WHERE payment_id=%s AND status='processed'",
                        (payment_id,),
                    ).fetchone()["amount"]
                    if Decimal(str(total_refunded)) >= Decimal(str(payment["amount"])):
                        conn.execute("UPDATE payments SET status='refunded',updated_at=now() WHERE id=%s", (payment_id,))
                return saved
            finally:
                conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (lock_key,))
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/{payment_id}/manual-refunds", status_code=201)
def create_manual_payment_refund(
    payment_id: int,
    payload: PaymentRefundCreate,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
):
    """Record manager-approved cash/terminal refunds; provider-managed payments must use the gateway refund route."""
    role = getattr(request.state, "role", None)
    actor_id = getattr(request.state, "user_id", None)
    actor_email = getattr(request.state, "user_email", None)
    if role not in {"manager", "admin", "super_admin"} or not actor_id or not actor_email:
        raise HTTPException(status_code=403, detail="A manager or administrator session is required to refund a payment")
    try:
        with _connect() as conn:
            with conn.transaction():
                lock_key = f"manual-payment-refund:{payment_id}:{idempotency_key}"
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (payload.order_id,))
                previous = conn.execute(
                    "SELECT id,payment_id,amount,status,provider,provider_refund_id,idempotency_key,note,created_at "
                    "FROM payment_refunds WHERE idempotency_key=%s FOR UPDATE",
                    (idempotency_key,),
                ).fetchone()
                if previous:
                    if int(previous["payment_id"]) != payment_id or Decimal(str(previous["amount"])) != payload.amount or previous["note"] != payload.note or previous["provider"] != "manual":
                        raise HTTPException(status_code=409, detail="Refund idempotency key was reused with different details")
                    return previous
                payment = conn.execute(
                    "SELECT p.id,p.order_id,p.amount,p.status,p.method,p.provider_reference,o.order_number,o.channel,o.pos_register_shift_id "
                    "FROM payments p JOIN orders o ON o.id=p.order_id WHERE p.id=%s FOR UPDATE OF p,o",
                    (payment_id,),
                ).fetchone()
                if payment is None:
                    raise HTTPException(status_code=404, detail="Payment not found")
                if payment["status"] not in {"captured", "refunded"}:
                    raise HTTPException(status_code=409, detail="Only captured payments can be refunded")
                if payment["provider_reference"]:
                    raise HTTPException(status_code=409, detail="This payment is provider-managed; use the gateway refund workflow")
                refunded = conn.execute(
                    "SELECT COALESCE(sum(amount),0) AS amount FROM payment_refunds WHERE payment_id=%s AND status IN ('processed','pending')",
                    (payment_id,),
                ).fetchone()["amount"]
                remaining = Decimal(str(payment["amount"])) - Decimal(str(refunded))
                if payload.amount > remaining:
                    raise HTTPException(status_code=422, detail=f"Refund exceeds the remaining refundable amount {remaining}")
                shift_id = None
                if payment["method"] == "cod" and payment["channel"] == "pos":
                    original_shift = conn.execute("SELECT register_id FROM pos_register_shifts WHERE id=%s", (payment["pos_register_shift_id"],)).fetchone()
                    open_shift = conn.execute(
                        "SELECT id,status FROM pos_register_shifts WHERE register_id=%s AND status='open' ORDER BY opened_at DESC LIMIT 1 FOR UPDATE",
                        (original_shift["register_id"] if original_shift else None,),
                    ).fetchone()
                    if not open_shift:
                        raise HTTPException(status_code=409, detail="Cash refunds against POS sales must be recorded during an open cashier shift at the original counter")
                    shift_id = open_shift["id"]
                refund = conn.execute(
                    "INSERT INTO payment_refunds(payment_id,order_id,amount,status,provider,pos_shift_id,idempotency_key,note,created_by_user_id,created_by_email) "
                    "VALUES(%s,%s,%s,'processed','manual',%s,%s,%s,%s,%s) "
                    "RETURNING id,payment_id,order_id,amount,status,provider,pos_shift_id,provider_refund_id,idempotency_key,note,created_at",
                    (payment_id,payment["order_id"],payload.amount,shift_id,idempotency_key,payload.note,int(actor_id),str(actor_email)),
                ).fetchone()
                total_refunded = Decimal(str(refunded)) + payload.amount
                if total_refunded >= Decimal(str(payment["amount"])):
                    conn.execute("UPDATE payments SET status='refunded',updated_at=now() WHERE id=%s", (payment_id,))
                if payment["method"] == "cod" and payment["channel"] == "pos":
                    conn.execute(
                        "INSERT INTO pos_cash_movements(shift_id,movement_type,amount,reason,reference,created_by) "
                        "VALUES(%s,'cash_out',%s,%s,%s,%s)",
                        (shift_id,payload.amount,"Refund: "+payment["order_number"],"payment-refund:"+str(refund["id"]),int(actor_id)),
                    )
                return refund
    except HTTPException:
        raise
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
                "SELECT COALESCE(sum(amount), 0) AS amount FROM payments WHERE status IN ('captured','refunded')"
            ).fetchone()["amount"]
            refunded = conn.execute(
                "SELECT COALESCE(sum(amount), 0) AS amount FROM payment_refunds WHERE status='processed'"
            ).fetchone()["amount"]
            pending_refunds = conn.execute(
                "SELECT count(*) AS count,COALESCE(sum(amount),0) AS amount FROM payment_refunds WHERE status='pending'"
            ).fetchone()
            refund_channels = conn.execute(
                "SELECT provider,count(*) AS count,COALESCE(sum(amount),0) AS amount FROM payment_refunds WHERE status='processed' GROUP BY provider ORDER BY provider"
            ).fetchall()
        by_status = {row["status"]: {"count": row["payment_count"], "amount": row["amount"]} for row in rows}
        return {
            "scope": "recorded_application_data_only",
            "gateway_or_bank_reconciled": False,
            "orders": {"count": order_rows["order_count"], "value": order_rows["order_value"]},
            "payments_by_status": by_status,
            "captured_amount_recorded": captured,
            "refunded_amount_recorded": refunded,
            "net_captured_amount_recorded": captured - refunded,
            "pending_refunds": pending_refunds,
            "refunds_by_provider": refund_channels,
            "note": "Amounts reflect application records only; provider settlement, fees, chargebacks and bank deposits are not verified.",
        }
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("", status_code=201)
def create_payment(
    payload: PaymentCreate,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=120),
):
    if not all(ch.isalnum() or ch in "-_." for ch in idempotency_key):
        raise HTTPException(status_code=422, detail="Idempotency-Key contains unsupported characters")
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id:
        raise HTTPException(status_code=403, detail="An authenticated staff account is required")
    payload_hash = payment_payload_sha256(payload.model_dump(mode="json"))
    scoped_key = _payment_idempotency_scope(int(actor_id), idempotency_key)
    try:
        with _connect() as conn:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (scoped_key,))
                prior = conn.execute(
                    "SELECT idempotency_payload_sha256, id, payment_reference, order_id, method, amount, status, provider_reference, note, created_at, updated_at "
                    "FROM payments WHERE idempotency_key=%s FOR UPDATE",
                    (scoped_key,),
                ).fetchone()
                if prior:
                    if prior["idempotency_payload_sha256"] != payload_hash:
                        raise HTTPException(status_code=409, detail="Idempotency-Key was already used with a different payment payload")
                    return {key: value for key, value in prior.items() if key != "idempotency_payload_sha256"}
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
                    "INSERT INTO payments (payment_reference, order_id, method, amount, status, provider_reference, note, idempotency_key, idempotency_payload_sha256) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id, payment_reference, order_id, method, amount, status, provider_reference, note, created_at, updated_at",
                    (reference, payload.order_id, payload.method, payload.amount, payload.status, payload.provider_reference, payload.note, scoped_key, payload_hash),
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
                    """SELECT p.id, p.order_id, p.amount, p.currency, p.status,
                              o.total AS order_total, o.status AS order_status, o.channel, o.order_number
                       FROM payments p JOIN orders o ON o.id=p.order_id
                       WHERE p.provider_order_id=%s
                       FOR UPDATE OF p, o""",
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
                    captured = conn.execute(
                        """SELECT COALESCE(sum(amount), 0) AS amount
                           FROM payments WHERE order_id=%s AND status='captured'""",
                        (payment["order_id"],),
                    ).fetchone()["amount"]
                    # Split tenders are settled only after every rupee is captured.
                    if payment["order_status"] == "placed" and order_is_fully_paid(payment["order_total"], captured):
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
                        if payment.get("channel") == "pos":
                            try:
                                consume_pos_order_stock(conn, int(payment["order_id"]))
                            except ValueError as exc:
                                raise HTTPException(status_code=409, detail=str(exc)) from exc
                            cost_row = conn.execute(
                                "SELECT COALESCE(sum(total_cost),0) AS total_cost FROM inventory_order_issues WHERE order_id=%s",
                                (payment["order_id"],),
                            ).fetchone()
                            total_cost = Decimal(str(cost_row["total_cost"] or 0))
                            if total_cost > 0:
                                from app.api import accounting
                                accounts = accounting._accounts_by_code(conn, ["1200", "5000"])
                                accounting._post_voucher(
                                    conn,
                                    {"voucher_type": "journal", "voucher_date": accounting._today(),
                                     "narration": f"Cost of goods sold for POS order {payment['order_number']}",
                                     "reference": payment["order_number"], "party_type": "customer",
                                     "party_name": "POS walk-in customer", "taxable_total": total_cost,
                                     "total_amount": total_cost, "source_type": "order_fulfilment",
                                     "source_id": str(payment["order_id"]),
                                     "idempotency_key": f"order-fulfilment-cogs:{payment['order_id']}"},
                                    [{"account_id": accounts["5000"]["id"], "debit": total_cost, "credit": 0,
                                      "narration": "Cost of goods sold"},
                                     {"account_id": accounts["1200"]["id"], "debit": 0, "credit": total_cost,
                                      "narration": "Inventory issued"}],
                                    (None, "razorpay-webhook"),
                                )
                            conn.execute(
                                "UPDATE orders SET status='delivered',updated_at=now() WHERE id=%s AND status='confirmed' AND channel='pos'",
                                (payment["order_id"],),
                            )
                            conn.execute(
                                """INSERT INTO order_status_history(order_id,from_status,to_status)
                                   SELECT %s,'confirmed','delivered'
                                   WHERE EXISTS (SELECT 1 FROM orders WHERE id=%s AND status='delivered')
                                     AND NOT EXISTS (SELECT 1 FROM order_status_history
                                                     WHERE order_id=%s AND from_status='confirmed' AND to_status='delivered')""",
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
    payment_id: int | None = Field(default=None, gt=0)


class RazorpayPaymentVerify(BaseModel):
    razorpay_order_id: str = Field(min_length=10, max_length=100, pattern=r"^order_[A-Za-z0-9]+$")
    razorpay_payment_id: str = Field(min_length=9, max_length=100, pattern=r"^pay_[A-Za-z0-9]+$")
    razorpay_signature: str = Field(min_length=64, max_length=64, pattern=r"^[a-fA-F0-9]{64}$")


@razorpay_router.post("/orders")
def create_razorpay_order(payload: RazorpayOrderCreate, request: Request):
    """Create or reuse a Razorpay order without holding a DB transaction over network I/O."""
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Razorpay payments are not configured")
    role = getattr(request.state, "role", None)
    actor_id = getattr(request.state, "user_id", None)
    if role != "customer" and not (role in {"staff", "manager", "admin", "super_admin"} and actor_id):
        raise HTTPException(status_code=403, detail="Customer or authenticated POS cashier session is required")

    lock_key = str(payload.order_id) + str(payload.payment_id)
    try:
        with _connect() as conn:
            # Session-level lock serializes provider-order creation for one local order.
            # Commit immediately: the lock survives the transaction while the provider is called.
            conn.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (lock_key,))
            conn.commit()
            try:
                with conn.transaction():
                    order = conn.execute(
                        """SELECT o.id, o.order_number, o.customer_email, o.total, o.status, o.channel,
                                  s.cashier_user_id
                           FROM orders o
                           LEFT JOIN pos_register_shifts s ON s.id=o.pos_register_shift_id
                           WHERE o.id=%s FOR UPDATE OF o""",
                        (payload.order_id,),
                    ).fetchone()
                    if order is None:
                        raise HTTPException(status_code=404, detail="Order not found")
                    if role == "customer":
                        if str(order["customer_email"] or "").lower() != str(request.state.customer_email).lower():
                            raise HTTPException(status_code=403, detail="Order does not belong to this customer")
                    elif order["channel"] != "pos" or int(order["cashier_user_id"] or 0) != int(actor_id):
                        raise HTTPException(status_code=403, detail="POS payment can only be initiated by the cashier assigned to this sale")
                    if order["status"] != "placed":
                        raise HTTPException(status_code=409, detail="Only newly placed orders can start payment")
                    if payload.payment_id:
                        existing = conn.execute(
                            "SELECT id,order_id,method,amount,status,provider_order_id FROM payments WHERE id=%s AND order_id=%s FOR UPDATE",
                            (payload.payment_id,payload.order_id),
                        ).fetchone()
                        if not existing or existing["method"] not in {"other","upi","card","wallet","netbanking"} or existing["status"] not in {"pending","authorized","failed"}:
                            raise HTTPException(status_code=409,detail="Selected online tender is not payable")
                        amount_paise = int((Decimal(str(existing["amount"])) * 100).quantize(Decimal("1")))
                    else:
                        amount_paise = int((Decimal(str(order["total"])) * 100).quantize(Decimal("1")))
                        existing = conn.execute(
                            """SELECT id, provider_order_id,method,amount,status FROM payments
                               WHERE order_id=%s AND method IN ('other','upi','card','wallet','netbanking')
                                 AND status IN ('pending','authorized')
                               ORDER BY id DESC LIMIT 1 FOR UPDATE""",
                            (payload.order_id,),
                        ).fetchone()
                    if amount_paise <= 0:
                        raise HTTPException(status_code=422, detail="Tender amount must be greater than zero")
                    if existing and existing["provider_order_id"] and existing["status"] in {"pending","authorized"}:
                        return {
                            "key_id": settings.razorpay_key_id,
                            "razorpay_order_id": existing["provider_order_id"],
                            "amount": amount_paise,
                            "currency": "INR",
                            "payment_id": existing["id"],
                            "order_number": order["order_number"],
                        }
                    order_snapshot = dict(order)
                    existing_payment_id = existing["id"] if existing else None

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
                                "notes": {"superbajaar_order_id": str(order_snapshot["id"]), "superbajaar_payment_id": str(existing_payment_id or "")},
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
                        """SELECT o.id, o.order_number, o.customer_email, o.total, o.status, o.channel,
                                  s.cashier_user_id
                           FROM orders o LEFT JOIN pos_register_shifts s ON s.id=o.pos_register_shift_id
                           WHERE o.id=%s FOR UPDATE OF o""",
                        (payload.order_id,),
                    ).fetchone()
                    if (current is None or current["status"] != "placed"
                        or Decimal(str(current["total"])) != Decimal(str(order_snapshot["total"]))
                        or (role == "customer" and str(current["customer_email"] or "").lower() != str(request.state.customer_email).lower())
                        or (role != "customer" and (current["channel"] != "pos" or int(current["cashier_user_id"] or 0) != int(actor_id)))):
                        raise HTTPException(status_code=409, detail="Order changed while payment was being initialised")
                    payment_reference = "PAY-" + uuid.uuid4().hex[:12].upper()
                    if existing_payment_id:
                        payment = conn.execute(
                            """UPDATE payments SET provider_order_id=%s,status='pending',currency='INR',
                                      note='Razorpay Standard Checkout',updated_at=now()
                               WHERE id=%s AND status IN ('pending','authorized','failed') RETURNING id""",
                            (provider_order_id, existing_payment_id),
                        ).fetchone()
                        if payment is None:
                            raise HTTPException(status_code=409, detail="POS tender changed while payment was being initialised")
                    else:
                        payment = conn.execute(
                            """INSERT INTO payments
                               (payment_reference, order_id, method, amount, status, provider_order_id, currency, note)
                               VALUES (%s,%s,%s,%s,'pending',%s,'INR','Razorpay Standard Checkout')
                               RETURNING id""",
                            (payment_reference, current["id"], existing["method"] if existing else "other", existing["amount"] if existing else current["total"], provider_order_id),
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
    role = getattr(request.state, "role", None)
    actor_id = getattr(request.state, "user_id", None)
    if role != "customer" and not (role in {"staff", "manager", "admin", "super_admin"} and actor_id):
        raise HTTPException(status_code=403, detail="Customer or authenticated POS cashier session is required")
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
                    """SELECT p.id, p.order_id, p.amount, p.currency, p.status, o.customer_email, o.order_number,
                              o.status AS order_status, o.channel, o.total AS order_total, s.cashier_user_id
                       FROM payments p JOIN orders o ON o.id=p.order_id
                       LEFT JOIN pos_register_shifts s ON s.id=o.pos_register_shift_id
                       WHERE p.provider_order_id=%s FOR UPDATE OF p, o""",
                    (payload.razorpay_order_id,),
                ).fetchone()
                if payment is None:
                    raise HTTPException(status_code=404, detail="Payment attempt not found")
                if role == "customer":
                    if str(payment["customer_email"] or "").lower() != str(request.state.customer_email).lower():
                        raise HTTPException(status_code=404, detail="Payment attempt not found")
                elif payment["channel"] != "pos" or int(payment["cashier_user_id"] or 0) != int(actor_id):
                    raise HTTPException(status_code=403, detail="POS payment can only be verified by the cashier assigned to this sale")
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
                captured_total = conn.execute(
                    "SELECT COALESCE(sum(amount),0) AS amount FROM payments WHERE order_id=%s AND status='captured'",
                    (payment["order_id"],),
                ).fetchone()["amount"]
                # A late capture is recorded but never resurrects a cancelled order.
                if payment["order_status"] == "placed" and order_is_fully_paid(payment["order_total"], captured_total):
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
                    if payment["channel"] == "pos":
                        try:
                            consume_pos_order_stock(conn, int(payment["order_id"]))
                        except ValueError as exc:
                            raise HTTPException(status_code=409, detail=str(exc)) from exc
                        cost_row = conn.execute(
                            "SELECT COALESCE(sum(total_cost),0) AS total_cost FROM inventory_order_issues WHERE order_id=%s",
                            (payment["order_id"],),
                        ).fetchone()
                        total_cost = Decimal(str(cost_row["total_cost"] or 0))
                        if total_cost > 0:
                            actor_email = getattr(request.state, "user_email", None)
                            if not actor_email:
                                raise HTTPException(status_code=401, detail="A valid cashier session is required to post POS cost of goods sold")
                            from app.api import accounting
                            accounts = accounting._accounts_by_code(conn, ["1200", "5000"])
                            accounting._post_voucher(
                                conn,
                                {"voucher_type": "journal", "voucher_date": accounting._today(),
                                 "narration": f"Cost of goods sold for POS order {payment['order_number']}",
                                 "reference": payment["order_number"], "party_type": "customer",
                                 "party_name": "POS walk-in customer", "taxable_total": total_cost,
                                 "total_amount": total_cost, "source_type": "order_fulfilment",
                                 "source_id": str(payment["order_id"]),
                                 "idempotency_key": f"order-fulfilment-cogs:{payment['order_id']}"},
                                [{"account_id": accounts["5000"]["id"], "debit": total_cost, "credit": 0,
                                  "narration": "Cost of goods sold"},
                                 {"account_id": accounts["1200"]["id"], "debit": 0, "credit": total_cost,
                                  "narration": "Inventory issued"}],
                                (actor_id, actor_email),
                            )
                        conn.execute(
                            "UPDATE orders SET status='delivered',updated_at=now() WHERE id=%s AND status='confirmed' AND channel='pos'",
                            (payment["order_id"],),
                        )
                        conn.execute(
                            """INSERT INTO order_status_history(order_id,from_status,to_status)
                               SELECT %s,'confirmed','delivered'
                               WHERE EXISTS (SELECT 1 FROM orders WHERE id=%s AND status='delivered')
                                 AND NOT EXISTS (SELECT 1 FROM order_status_history
                                                 WHERE order_id=%s AND from_status='confirmed' AND to_status='delivered')""",
                            (payment["order_id"], payment["order_id"], payment["order_id"]),
                        )
                final_order_status = conn.execute("SELECT status FROM orders WHERE id=%s", (payment["order_id"],)).fetchone()["status"]
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
