"""POS reporting/read APIs backed by the existing order and payment ledger."""
import psycopg
from datetime import date
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from app.core.config import settings

router = APIRouter(prefix="/pos", tags=["pos"])


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="POS database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="POS database is unavailable") from exc


def _db_error(exc: psycopg.Error):
    return HTTPException(status_code=503, detail="POS records are unavailable")


@router.get("/summary")
def pos_summary():
    """Return POS-only sales and payment metrics; pending records are never counted as collected."""
    try:
        with _connect() as conn:
            orders = conn.execute(
                """SELECT count(*) AS order_count,
                          count(*) FILTER (WHERE status <> 'cancelled') AS active_order_count,
                          COALESCE(sum(total) FILTER (WHERE status <> 'cancelled'), 0) AS order_value,
                          count(*) FILTER (WHERE (created_at AT TIME ZONE 'Asia/Kolkata')::date = (now() AT TIME ZONE 'Asia/Kolkata')::date) AS today_order_count,
                          COALESCE(sum(total) FILTER (WHERE (created_at AT TIME ZONE 'Asia/Kolkata')::date = (now() AT TIME ZONE 'Asia/Kolkata')::date AND status <> 'cancelled'), 0) AS today_order_value
                   FROM orders WHERE channel='pos'"""
            ).fetchone()
            payments = conn.execute(
                """SELECT count(*) AS payment_count,
                          count(*) FILTER (WHERE p.status='captured') AS captured_count,
                          COALESCE(sum(amount) FILTER (WHERE p.status='captured'), 0) AS captured_amount,
                          count(*) FILTER (WHERE p.status IN ('pending','authorized')) AS pending_count,
                          COALESCE(sum(amount) FILTER (WHERE p.status IN ('pending','authorized')), 0) AS pending_amount
                   FROM payments p JOIN orders o ON o.id=p.order_id WHERE o.channel='pos'"""
            ).fetchone()
        return {"source": "postgresql", "orders": orders, "payments": payments}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/sales")
def list_pos_sales(
    status: Annotated[str | None, Query(max_length=40)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    register_id: Annotated[int | None, Query(gt=0)] = None,
    cashier_user_id: Annotated[int | None, Query(gt=0)] = None,
    payment_method: Annotated[str | None, Query(pattern=r"^(upi|card|netbanking|cod|wallet|bank_transfer|other)$")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from cannot be after date_to")
    clauses = ["o.channel='pos'"]
    params = []
    if status:
        clauses.append("o.status=%s")
        params.append(status)
    if date_from:
        clauses.append("(o.created_at AT TIME ZONE 'Asia/Kolkata')::date >= %s")
        params.append(date_from)
    if date_to:
        clauses.append("(o.created_at AT TIME ZONE 'Asia/Kolkata')::date <= %s")
        params.append(date_to)
    if register_id:
        clauses.append("s.register_id=%s")
        params.append(register_id)
    if cashier_user_id:
        clauses.append("s.cashier_user_id=%s")
        params.append(cashier_user_id)
    if payment_method:
        clauses.append("EXISTS (SELECT 1 FROM payments pm WHERE pm.order_id=o.id AND pm.method=%s)")
        params.append(payment_method)
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(o.order_number ILIKE %s OR o.customer_name ILIKE %s OR COALESCE(o.customer_phone,'') ILIKE %s)")
        params.extend([term, term, term])
    where = " AND ".join(clauses)
    try:
        with _connect() as conn:
            items = conn.execute(
                f"""SELECT o.id, o.order_number, o.customer_name, o.customer_phone, o.status,
                           o.subtotal, o.total, o.created_at, s.register_id, s.cashier_user_id,
                           COALESCE(l.line_count, 0) AS line_count,
                           COALESCE(p.captured_amount, 0) AS captured_amount,
                           COALESCE(p.pending_amount, 0) AS pending_amount,
                           COALESCE(r.refunded_amount, 0) AS refunded_amount,
                           COALESCE(p.payment_statuses, '') AS payment_statuses
                    FROM orders o
                    LEFT JOIN pos_register_shifts s ON s.id=o.pos_register_shift_id
                    LEFT JOIN (
                      SELECT order_id, count(*) AS line_count
                      FROM order_lines GROUP BY order_id
                    ) l ON l.order_id=o.id
                    LEFT JOIN (
                      SELECT order_id,
                             sum(amount) FILTER (WHERE p.status='captured') AS captured_amount,
                             sum(amount) FILTER (WHERE p.status IN ('pending','authorized')) AS pending_amount,
                             string_agg(DISTINCT p.status, ', ') AS payment_statuses
                      FROM payments p GROUP BY order_id
                    ) p ON p.order_id=o.id
                    LEFT JOIN (
                      SELECT order_id,COALESCE(sum(amount) FILTER (WHERE status='processed'),0) AS refunded_amount
                      FROM payment_refunds GROUP BY order_id
                    ) r ON r.order_id=o.id
                    WHERE {where}
                    ORDER BY o.created_at DESC
                    LIMIT %s OFFSET %s""",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute(
                f"SELECT count(*) AS total FROM orders o LEFT JOIN pos_register_shifts s ON s.id=o.pos_register_shift_id WHERE {where}",
                params,
            ).fetchone()["total"]
        return {"items": items, "total": total, "limit": limit, "offset": offset, "source": "postgresql"}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/sales/{order_id}")
def get_pos_sale(order_id: int):
    try:
        with _connect() as conn:
            order = conn.execute(
                """SELECT o.id, o.order_number, o.customer_name, o.customer_phone, o.status,
                          o.subtotal, o.total, o.discount_total, o.promotion_code, o.tax_total, o.place_of_supply_state, o.notes, o.created_at, o.updated_at,
                          s.id AS shift_id, s.register_id, r.register_code, r.name AS register_name,
                          s.cashier_user_id
                   FROM orders o
                   LEFT JOIN pos_register_shifts s ON s.id=o.pos_register_shift_id
                   LEFT JOIN pos_registers r ON r.id=s.register_id
                   WHERE o.id=%s AND o.channel='pos'""",
                (order_id,),
            ).fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="POS sale not found")
            lines = conn.execute(
                """SELECT l.id, l.variant_id, v.sku, p.name AS product_name,
                          l.quantity, l.unit_price, l.line_total, l.hsn_code, l.gst_rule_id, l.gst_rate, l.taxable_value,
                          l.cgst_amount, l.sgst_amount, l.igst_amount, l.tax_total
                   FROM order_lines l JOIN product_variants v ON v.id=l.variant_id
                   JOIN products p ON p.id=v.product_id
                   WHERE l.order_id=%s ORDER BY l.id""",
                (order_id,),
            ).fetchall()
            payments = conn.execute(
                """SELECT id, payment_reference, method, amount, status, provider_reference, created_at
                   FROM payments WHERE order_id=%s ORDER BY created_at""",
                (order_id,),
            ).fetchall()
            refunds = conn.execute(
                "SELECT id,payment_id,amount,status,provider,provider_refund_id,idempotency_key,note,created_at FROM payment_refunds WHERE order_id=%s ORDER BY created_at,id",
                (order_id,),
            ).fetchall()
        return {**order, "lines": lines, "payments": payments, "refunds": refunds, "source": "postgresql"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
