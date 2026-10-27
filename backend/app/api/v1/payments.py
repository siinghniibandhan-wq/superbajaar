"""Payment record management API; this does not initiate external gateway charges."""
from decimal import Decimal
import uuid

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

router = APIRouter(prefix="/payments", tags=["payments"])
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
            raise ValueError("New payment records must start as pending; gateway confirmation is not configured")
        return value


class PaymentStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_allowed(cls, value):
        if value not in PAYMENT_STATUSES:
            raise ValueError("Unsupported payment status")
        if value == "captured" or value == "refunded":
            raise ValueError("Captured/refunded status requires verified provider confirmation; gateway integration is not configured")
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


@router.post("", status_code=201)
def create_payment(payload: PaymentCreate):
    try:
        with _connect() as conn:
            with conn.transaction():
                order = conn.execute("SELECT id, total, status FROM orders WHERE id=%s FOR SHARE", (payload.order_id,)).fetchone()
                if order is None:
                    raise HTTPException(status_code=404, detail="Order not found")
                if order["status"] == "cancelled":
                    raise HTTPException(status_code=409, detail="Cannot record payment for a cancelled order")
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
                    raise HTTPException(status_code=409, detail="Captured/refunded status requires verified provider confirmation; gateway integration is not configured")
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
