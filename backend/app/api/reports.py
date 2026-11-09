"""Server-side, all-row reporting aggregates for the Admin Reports workspace."""
from datetime import date

import psycopg
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from app.core.config import settings

router = APIRouter(prefix="/reports", tags=["reports"])


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Reports database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Reports database is unavailable") from exc


def _db_error(exc: psycopg.Error):
    return HTTPException(status_code=503, detail="Reporting data is unavailable")


@router.get("/overview")
def reports_overview(from_date: date, to_date: date):
    """Aggregate all matching rows in PostgreSQL; list endpoints remain bounded detail views."""
    if from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must be on or before to_date")
    date_filter = "created_at >= (%s::date::timestamp AT TIME ZONE 'Asia/Kolkata') AND created_at < ((%s::date + 1)::timestamp AT TIME ZONE 'Asia/Kolkata')"
    try:
        with _connect() as conn:
            orders = conn.execute(
                f"""SELECT count(*) AS order_count,
                           count(*) FILTER (WHERE status NOT IN ('cancelled','draft')) AS active_order_count,
                           COALESCE(sum(total) FILTER (WHERE status NOT IN ('cancelled','draft')), 0) AS active_order_value
                    FROM orders WHERE {date_filter}""",
                (from_date, to_date),
            ).fetchone()
            order_statuses = conn.execute(
                f"""SELECT status, count(*) AS count FROM orders
                    WHERE {date_filter} GROUP BY status ORDER BY count DESC, status""",
                (from_date, to_date),
            ).fetchall()
            payments = conn.execute(
                f"""SELECT count(*) AS payment_count,
                           count(*) FILTER (WHERE status='captured') AS captured_count,
                           COALESCE(sum(amount) FILTER (WHERE status='captured'), 0) AS captured_amount,
                           count(*) FILTER (WHERE status IN ('pending','authorized')) AS pending_count,
                           COALESCE(sum(amount) FILTER (WHERE status IN ('pending','authorized')), 0) AS pending_amount
                    FROM payments WHERE {date_filter}""",
                (from_date, to_date),
            ).fetchone()
            payment_statuses = conn.execute(
                f"""SELECT status, count(*) AS count FROM payments
                    WHERE {date_filter} GROUP BY status ORDER BY count DESC, status""",
                (from_date, to_date),
            ).fetchall()
            inventory = conn.execute(
                """SELECT count(*) AS balance_rows,
                          COALESCE(sum(on_hand), 0) AS stock_units,
                          count(*) FILTER (WHERE on_hand > 0 AND on_hand <= 5) AS low_stock_rows,
                          count(*) FILTER (WHERE on_hand <= 0) AS out_of_stock_rows
                   FROM inventory_balances"""
            ).fetchone()
            catalogue = conn.execute(
                """SELECT
                     (SELECT count(*) FROM products WHERE status='active') AS active_products,
                     (SELECT count(*) FROM product_variants WHERE is_active=TRUE) AS active_variants"""
            ).fetchone()
        return {
            "source": "postgresql",
            "period": {"from_date": from_date, "to_date": to_date},
            "orders": orders,
            "order_statuses": order_statuses,
            "payments": payments,
            "payment_statuses": payment_statuses,
            "inventory": inventory,
            "catalogue": catalogue,
        }
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
