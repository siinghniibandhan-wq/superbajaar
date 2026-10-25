"""Sales invoices: unique source-linked invoices, confirmation to bills, and payment tracking."""
import json
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from .auth import _db, _require
from .schema_guard import tolerate_missing_ddl_permission

router = APIRouter(prefix="/api/sales-invoices", tags=["sales-invoices"])


def _admin(auth: str | None) -> dict[str, Any]:
    return _require(auth, {"super_admin", "admin", "staff"})


@tolerate_missing_ddl_permission
def _ensure(conn: Any) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_sales_invoices (
        id BIGSERIAL PRIMARY KEY,
        invoice_number TEXT UNIQUE,
        source_type TEXT NOT NULL CHECK(source_type IN ('pos','website')),
        source_id BIGINT NOT NULL,
        customer_name TEXT NOT NULL,
        customer_email TEXT,
        customer_phone TEXT,
        subtotal NUMERIC(14,2) NOT NULL DEFAULT 0,
        tax_total NUMERIC(14,2) NOT NULL DEFAULT 0,
        total NUMERIC(14,2) NOT NULL DEFAULT 0,
        amount_received NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK(amount_received >= 0),
        status TEXT NOT NULL DEFAULT 'pending_confirmation'
          CHECK(status IN ('pending_confirmation','bill_created','void')),
        payment_status TEXT NOT NULL DEFAULT 'unpaid'
          CHECK(payment_status IN ('unpaid','partial','paid')),
        journal_id BIGINT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        confirmed_at TIMESTAMPTZ,
        UNIQUE(source_type, source_id)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_sales_invoice_lines (
        id BIGSERIAL PRIMARY KEY,
        invoice_id BIGINT NOT NULL REFERENCES sb_sales_invoices(id) ON DELETE CASCADE,
        description TEXT NOT NULL,
        variant_id BIGINT,
        quantity NUMERIC(14,3) NOT NULL DEFAULT 1,
        unit_price NUMERIC(14,2) NOT NULL DEFAULT 0,
        tax_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
        line_subtotal NUMERIC(14,2) NOT NULL DEFAULT 0,
        line_tax NUMERIC(14,2) NOT NULL DEFAULT 0,
        line_total NUMERIC(14,2) NOT NULL DEFAULT 0
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_sales_invoice_payments (
        id BIGSERIAL PRIMARY KEY,
        invoice_id BIGINT NOT NULL REFERENCES sb_sales_invoices(id),
        amount NUMERIC(14,2) NOT NULL CHECK(amount > 0),
        payment_method TEXT NOT NULL CHECK(payment_method IN ('cash','bank','upi','card','other')),
        reference TEXT,
        received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        received_by BIGINT,
        journal_id BIGINT
    )""")


def create_invoice(conn: Any, *, source_type: str, source_id: int, customer_name: str,
                   customer_email: str | None, customer_phone: str | None,
                   subtotal: Any, tax_total: Any, total: Any, lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Create one invoice per source inside the source transaction; safe to retry."""
    _ensure(conn)
    existing = conn.execute(
        "SELECT * FROM sb_sales_invoices WHERE source_type=%s AND source_id=%s",
        (source_type, source_id),
    ).fetchone()
    if existing:
        return existing
    row = conn.execute("""INSERT INTO sb_sales_invoices
        (source_type,source_id,customer_name,customer_email,customer_phone,subtotal,tax_total,total)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(source_type,source_id) DO NOTHING RETURNING *""",
        (source_type, source_id, customer_name or "Customer", customer_email, customer_phone,
         subtotal or 0, tax_total or 0, total or 0)).fetchone()
    if row is None:
        # Concurrent retries return the existing invoice and never duplicate its lines.
        return conn.execute("SELECT * FROM sb_sales_invoices WHERE source_type=%s AND source_id=%s",
                            (source_type, source_id)).fetchone()
    if row["invoice_number"] is None:
        number = f"SB-INV-{int(row['id']):08d}"
        row = conn.execute("UPDATE sb_sales_invoices SET invoice_number=%s WHERE id=%s RETURNING *",
                           (number, row["id"])).fetchone()
    for line in lines:
        conn.execute("""INSERT INTO sb_sales_invoice_lines
            (invoice_id,description,variant_id,quantity,unit_price,tax_rate,line_subtotal,line_tax,line_total)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (row["id"], str(line.get("description") or line.get("product_name") or "Sale item"),
             line.get("variant_id"), line.get("quantity") or 1, line.get("unit_price") or 0,
             line.get("tax_rate") or 0, line.get("line_subtotal", line.get("subtotal", 0)) or 0,
             line.get("line_tax", line.get("tax", 0)) or 0, line.get("line_total", 0) or 0))
    return row


class PaymentInput(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    payment_method: str = Field(pattern="^(cash|bank|upi|card|other)$")
    reference: str = Field(default="", max_length=160)


@router.get("")
def list_invoices(status: str = Query(default="", pattern="^(|pending_confirmation|bill_created|void)$"),
                  payment_status: str = Query(default="", pattern="^(|unpaid|partial|paid)$"),
                  authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            rows = conn.execute("""SELECT * FROM sb_sales_invoices
                WHERE (%s='' OR status=%s) AND (%s='' OR payment_status=%s)
                ORDER BY created_at DESC,id DESC LIMIT 500""",
                (status,status,payment_status,payment_status)).fetchall()
            for row in rows:
                row["lines"] = conn.execute("SELECT * FROM sb_sales_invoice_lines WHERE invoice_id=%s ORDER BY id",
                                            (row["id"],)).fetchall()
                row["payments"] = conn.execute("SELECT id,amount,payment_method,reference,received_at FROM sb_sales_invoice_payments WHERE invoice_id=%s ORDER BY id",
                                               (row["id"],)).fetchall()
            return {"items": rows}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Sales invoice register unavailable") from exc


@router.post("/{invoice_id}/confirm")
def confirm_invoice(invoice_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    actor = _require(authorization, {"super_admin", "admin", "staff"})
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            from .accounting import _ensure as ensure_accounting
            from .operations import _post_journal
            ensure_accounting(conn)
            with conn.transaction():
                inv = conn.execute("SELECT * FROM sb_sales_invoices WHERE id=%s FOR UPDATE", (invoice_id,)).fetchone()
                if not inv:
                    raise HTTPException(status_code=404, detail="Invoice not found")
                if inv["status"] == "bill_created":
                    return {"invoice": inv, "message": "Already confirmed; no duplicate bill was created."}
                if inv["status"] == "void":
                    raise HTTPException(status_code=409, detail="Voided invoice cannot be confirmed")
                if inv["source_type"] == "pos":
                    # POS already posts its tender, revenue and GST journal at checkout.
                    # Confirmation changes the invoice workflow only; never duplicate that journal.
                    posted = conn.execute("SELECT id FROM sb_journals WHERE source_module='pos' AND source_id=%s ORDER BY id DESC LIMIT 1",
                                          (str(inv["source_id"]),)).fetchone()
                    jid = posted["id"] if posted else None
                else:
                    total = Decimal(str(inv["total"]))
                    subtotal = Decimal(str(inv["subtotal"]))
                    tax = Decimal(str(inv["tax_total"]))
                    lines = [("accounts_receivable", total, Decimal("0")), ("sales", Decimal("0"), subtotal)]
                    if tax:
                        lines.append(("output_gst", Decimal("0"), tax))
                    jid = _post_journal(conn, date.today(), inv["invoice_number"],
                        "Sales invoice confirmed: " + inv["invoice_number"], "sales_invoice",
                        int(inv["id"]), lines, int(actor["id"]))
                updated = conn.execute("""UPDATE sb_sales_invoices SET status='bill_created',
                    confirmed_at=now(),journal_id=%s WHERE id=%s RETURNING *""", (jid, invoice_id)).fetchone()
                return {"invoice": updated, "message": "Invoice confirmed and bill posted to Accounting."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Invoice confirmation failed; no confirmation was recorded") from exc


@router.post("/{invoice_id}/payments", status_code=201)
def receive_payment(invoice_id: int, body: PaymentInput,
                    authorization: str | None = Header(default=None)) -> dict[str, Any]:
    actor = _require(authorization, {"super_admin", "admin", "staff"})
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            from .accounting import _ensure as ensure_accounting
            from .operations import _post_journal
            ensure_accounting(conn)
            with conn.transaction():
                inv = conn.execute("SELECT * FROM sb_sales_invoices WHERE id=%s FOR UPDATE", (invoice_id,)).fetchone()
                if not inv:
                    raise HTTPException(status_code=404, detail="Invoice not found")
                if inv["status"] != "bill_created":
                    raise HTTPException(status_code=409, detail="Confirm the invoice before recording payment")
                due = Decimal(str(inv["total"])) - Decimal(str(inv["amount_received"]))
                if body.amount > due:
                    raise HTTPException(status_code=422, detail=f"Payment exceeds outstanding balance {due}")
                payment = conn.execute("""INSERT INTO sb_sales_invoice_payments
                    (invoice_id,amount,payment_method,reference,received_by)
                    VALUES(%s,%s,%s,%s,%s) RETURNING *""",
                    (invoice_id, body.amount, body.payment_method, body.reference.strip() or None, actor["id"])).fetchone()
                cash_account = {"bank":"bank","upi":"bank","card":"bank","cash":"cash","other":"cash"}[body.payment_method]
                jid = _post_journal(conn, date.today(), inv["invoice_number"] + "-PAY-" + str(payment["id"]),
                    "Receipt against " + inv["invoice_number"], "invoice_payment", int(payment["id"]),
                    [(cash_account, body.amount, Decimal("0")), ("accounts_receivable", Decimal("0"), body.amount)],
                    int(actor["id"]))
                conn.execute("UPDATE sb_sales_invoice_payments SET journal_id=%s WHERE id=%s", (jid,payment["id"]))
                received = Decimal(str(inv["amount_received"])) + body.amount
                state = "paid" if received >= Decimal(str(inv["total"])) else "partial"
                updated = conn.execute("UPDATE sb_sales_invoices SET amount_received=%s,payment_status=%s WHERE id=%s RETURNING *",
                                       (received,state,invoice_id)).fetchone()
                return {"invoice": updated, "payment": payment, "message": "Payment recorded and posted to Accounting."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Payment could not be recorded") from exc
