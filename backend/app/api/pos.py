"""POS reporting/read APIs backed by the existing order and payment ledger."""
import psycopg
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
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    clauses = ["o.channel='pos'"]
    params = []
    if status:
        clauses.append("o.status=%s")
        params.append(status)
    where = " AND ".join(clauses)
    try:
        with _connect() as conn:
            items = conn.execute(
                f"""SELECT o.id, o.order_number, o.customer_name, o.customer_phone, o.status,
                           o.subtotal, o.total, o.created_at,
                           COALESCE(l.line_count, 0) AS line_count,
                           COALESCE(p.captured_amount, 0) AS captured_amount,
                           COALESCE(p.pending_amount, 0) AS pending_amount,
                           COALESCE(p.payment_statuses, '') AS payment_statuses
                    FROM orders o
                    LEFT JOIN (
                      SELECT order_id, count(*) AS line_count
                      FROM order_lines GROUP BY order_id
                    ) l ON l.order_id=o.id
                    LEFT JOIN (
                      SELECT order_id,
                             sum(amount) FILTER (WHERE p.status='captured') AS captured_amount,
                             sum(amount) FILTER (WHERE p.status IN ('pending','authorized')) AS pending_amount,
                             string_agg(DISTINCT status, ', ') AS payment_statuses
                      FROM payments GROUP BY order_id
                    ) p ON p.order_id=o.id
                    WHERE {where}
                    ORDER BY o.created_at DESC
                    LIMIT %s OFFSET %s""",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute(f"SELECT count(*) AS total FROM orders o WHERE {where}", params).fetchone()["total"]
        return {"items": items, "total": total, "limit": limit, "offset": offset, "source": "postgresql"}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/sales/{order_id}")
def get_pos_sale(order_id: int):
    try:
        with _connect() as conn:
            order = conn.execute(
                """SELECT id, order_number, customer_name, customer_phone, status,
                          subtotal, total, notes, created_at, updated_at
                   FROM orders WHERE id=%s AND channel='pos'""",
                (order_id,),
            ).fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="POS sale not found")
            lines = conn.execute(
                """SELECT l.id, l.variant_id, v.sku, p.name AS product_name,
                          l.quantity, l.unit_price, l.line_total
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
        return {**order, "lines": lines, "payments": payments, "source": "postgresql"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
