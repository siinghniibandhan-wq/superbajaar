"""End-to-end accounting tests against a disposable PostgreSQL database.

Skipped unless SB_TEST_DATABASE_URL points at a throw-away database that already has
every backend/schema/*.sql file applied. Never point this at production: the test
writes orders, payments, purchase receipts and vouchers.
"""
import os
from decimal import Decimal
from datetime import date, timedelta

import psycopg
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.api import accounting
from app.core.auth_middleware import require_active_session
from app.main import app

TEST_DB = os.environ.get("SB_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="SB_TEST_DATABASE_URL is not set")
if TEST_DB and ("sb_app" in TEST_DB or "amazonaws" in TEST_DB):
    raise RuntimeError("Refusing to run accounting integration tests against a production-like database")

TODAY = accounting._today()


@pytest.fixture()
def api(monkeypatch):
    role = {"value": "owner"}

    async def fake_session(request: Request):
        request.state.role = role["value"]
        request.state.user_id = 1
        request.state.user_email = f"{role['value']}@test.local"

    monkeypatch.setattr(accounting.settings, "database_url", TEST_DB)
    app.dependency_overrides[require_active_session] = fake_session
    with psycopg.connect(TEST_DB) as conn:
        conn.execute("ALTER TABLE accounting_vouchers DISABLE TRIGGER accounting_vouchers_protect_trg")
        conn.execute("ALTER TABLE accounting_voucher_lines DISABLE TRIGGER accounting_voucher_lines_protect_trg")
        conn.execute("TRUNCATE accounting_voucher_lines, accounting_vouchers, accounting_voucher_sequences RESTART IDENTITY CASCADE")
        conn.execute("ALTER TABLE accounting_vouchers ENABLE TRIGGER accounting_vouchers_protect_trg")
        conn.execute("ALTER TABLE accounting_voucher_lines ENABLE TRIGGER accounting_voucher_lines_protect_trg")
        conn.execute("DELETE FROM accounting_accounts WHERE code = '6110'")
        conn.execute("UPDATE accounting_settings SET lock_date=NULL, default_supply='intra' WHERE id=1")
    client = TestClient(app)
    client.role = role
    yield client
    app.dependency_overrides.pop(require_active_session, None)


def acct(client, code):
    items = client.get("/api/accounting/accounts").json()["items"]
    return next(item["id"] for item in items if item["code"] == code)


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def test_full_accounting_cycle(api):
    cash, bank, capital, rent, ar = (acct(api, c) for c in ("1000", "1010", "3000", "6000", "1100"))
    day = TODAY - timedelta(days=5)

    opening = ok(api.post("/api/accounting/vouchers", json={
        "voucher_type": "opening", "voucher_date": str(day), "narration": "Opening balances",
        "lines": [{"account_id": cash, "debit": "10000"}, {"account_id": bank, "debit": "50000"},
                  {"account_id": capital, "credit": "60000"}],
    }), 201)
    assert opening["voucher_number"].startswith("OB/" + accounting.fiscal_year(day) + "/")

    sale = ok(api.post("/api/accounting/invoices", json={
        "invoice_type": "sales", "voucher_date": str(day), "party_name": "Ravi Traders", "party_gstin": "10ABCDE1234F1Z5",
        "due_date": str(day + timedelta(days=15)), "idempotency_key": "sale-test-0001",
        "lines": [{"description": "Rice", "hsn_sac": "1006", "quantity": "10", "rate": "100", "gst_rate": "5"},
                  {"description": "Bottle", "quantity": "2", "rate": "500", "gst_rate": "18"}],
    }), 201)
    assert sale["total_amount"] in ("2230.00", 2230.0, "2230")
    replay = ok(api.post("/api/accounting/invoices", json={
        "invoice_type": "sales", "voucher_date": str(day), "party_name": "Ravi Traders", "idempotency_key": "sale-test-0001",
        "lines": [{"description": "Rice", "rate": "1", "gst_rate": "0"}],
    }), 201)
    assert replay["id"] == sale["id"] and replay["idempotent_replay"] is True

    ok(api.post("/api/accounting/invoices", json={
        "invoice_type": "purchase", "voucher_date": str(day), "party_name": "Delhi Supplier", "place_of_supply": "inter",
        "reference": "BILL-77", "lines": [{"description": "Stock", "quantity": "20", "rate": "40", "gst_rate": "12"}],
    }), 201)
    ok(api.post("/api/accounting/vouchers", json={
        "voucher_type": "receipt", "voucher_date": str(day + timedelta(days=1)), "party_type": "customer", "party_name": "Ravi Traders",
        "lines": [{"account_id": bank, "debit": "1000"}, {"account_id": ar, "credit": "1000"}],
    }), 201)
    expense = ok(api.post("/api/accounting/vouchers", json={
        "voucher_type": "expense", "voucher_date": str(day + timedelta(days=1)), "narration": "Shop rent",
        "lines": [{"account_id": rent, "debit": "5000"}, {"account_id": cash, "credit": "5000"}],
    }), 201)

    bad_contra = api.post("/api/accounting/vouchers", json={
        "voucher_type": "contra", "voucher_date": str(day),
        "lines": [{"account_id": rent, "debit": "10"}, {"account_id": cash, "credit": "10"}],
    })
    assert bad_contra.status_code == 422

    tb = ok(api.get("/api/accounting/reports/trial-balance"))
    assert tb["balanced"] is True
    bs = ok(api.get("/api/accounting/reports/balance-sheet"))
    assert bs["balanced"] is True
    pl = ok(api.get("/api/accounting/reports/profit-loss", params={"from_date": str(day - timedelta(days=1))}))
    assert float(pl["totals"]["revenue"]) == 2000.0
    assert float(pl["net_profit"]) == 2000.0 - 5000.0 + float(pl["totals"]["other_income"])

    gst = ok(api.get("/api/accounting/reports/gst-summary", params={"from_date": str(day - timedelta(days=1))}))
    assert float(gst["output_tax"]["cgst"]) == 115.0 and float(gst["output_tax"]["sgst"]) == 115.0
    assert float(gst["input_tax"]["igst"]) == 96.0
    assert float(gst["total_net_payable"]) == 230.0 - 96.0
    assert {b["rate"] for b in gst["by_rate"]} >= {"5", "18", "12"}

    ledger = ok(api.get(f"/api/accounting/reports/ledger/{cash}", params={"from_date": str(day - timedelta(days=1))}))
    assert float(ledger["closing_balance"]) == 5000.0

    parties = ok(api.get("/api/accounting/reports/parties", params={"kind": "receivable"}))
    ravi = next(p for p in parties["items"] if p["party_name"] == "Ravi Traders")
    assert float(ravi["outstanding"]) == 1230.0
    payables = ok(api.get("/api/accounting/reports/parties", params={"kind": "payable"}))
    assert float(next(p for p in payables["items"] if p["party_name"] == "Delhi Supplier")["outstanding"]) == 896.0

    summary = ok(api.get("/api/accounting/reports/summary", params={"from_date": str(day - timedelta(days=1))}))
    assert float(summary["cash_balance"]) == 5000.0 and float(summary["bank_balance"]) == 51000.0
    assert summary["voucher_count"] == 5

    reversal = ok(api.post(f"/api/accounting/vouchers/{expense['id']}/reverse", json={"reason": "Entered twice by mistake"}), 201)
    assert reversal["voucher_type"] == "reversal"
    assert api.post(f"/api/accounting/vouchers/{expense['id']}/reverse", json={"reason": "Again please"}).status_code == 409
    assert api.post(f"/api/accounting/vouchers/{reversal['id']}/reverse", json={"reason": "Undo the undo"}).status_code == 409
    assert float(ok(api.get(f"/api/accounting/reports/ledger/{cash}"))["closing_balance"]) == 10000.0

    bank_view = ok(api.get("/api/accounting/bank-reconciliation", params={"account_id": bank}))
    assert float(bank_view["book_balance"]) == 51000.0 and float(bank_view["cleared_balance"]) == 0.0
    line = bank_view["items"][0]
    ok(api.patch(f"/api/accounting/lines/{line['line_id']}/reconcile", json={"reconciled_on": str(TODAY), "bank_reference": "STMT-1"}))
    assert float(ok(api.get("/api/accounting/bank-reconciliation", params={"account_id": bank}))["cleared_balance"]) == float(line["debit"])
    assert api.patch(f"/api/accounting/lines/{opening['lines'][2]['id']}/reconcile", json={"reconciled_on": str(TODAY)}).status_code == 422

    day_book = ok(api.get("/api/accounting/reports/day-book", params={"from_date": str(day), "to_date": str(TODAY)}))
    assert len(day_book["items"]) == 6 and all(len(v["lines"]) >= 2 for v in day_book["items"])

    with psycopg.connect(TEST_DB) as conn:
        with pytest.raises(psycopg.Error):
            conn.execute("DELETE FROM accounting_vouchers WHERE id=%s", (opening["id"],))
        conn.rollback()
        with pytest.raises(psycopg.Error):
            conn.execute("UPDATE accounting_voucher_lines SET debit=debit+1 WHERE voucher_id=%s AND line_no=1", (opening["id"],))


def test_lock_date_and_owner_only_lock(api):
    cash, capital = acct(api, "1000"), acct(api, "3000")
    settings = ok(api.get("/api/accounting/settings"))
    body = {"business_name": settings["business_name"], "default_supply": "intra", "lock_date": str(TODAY - timedelta(days=2))}
    api.role["value"] = "admin"
    assert api.put("/api/accounting/settings", json=body).status_code == 403
    api.role["value"] = "owner"
    ok(api.put("/api/accounting/settings", json=body))
    locked = api.post("/api/accounting/vouchers", json={
        "voucher_type": "journal", "voucher_date": str(TODAY - timedelta(days=3)),
        "lines": [{"account_id": cash, "debit": "1"}, {"account_id": capital, "credit": "1"}],
    })
    assert locked.status_code == 409
    ok(api.post("/api/accounting/vouchers", json={
        "voucher_type": "journal", "voucher_date": str(TODAY),
        "lines": [{"account_id": cash, "debit": "1"}, {"account_id": capital, "credit": "1"}],
    }), 201)
    api.role["value"] = "staff"
    assert api.get("/api/accounting/reports/summary").status_code == 403
    api.role["value"] = "manager"
    ok(api.get("/api/accounting/reports/summary"))


def test_accounts_create_and_system_protection(api):
    created = ok(api.post("/api/accounting/accounts", json={
        "code": "6110", "name": "Software subscriptions", "account_type": "expense", "sub_type": "operating"}), 201)
    assert api.post("/api/accounting/accounts", json={
        "code": "6110", "name": "Duplicate", "account_type": "expense", "sub_type": "operating"}).status_code == 409
    assert api.post("/api/accounting/accounts", json={
        "code": "6120", "name": "Bad", "account_type": "expense", "sub_type": "bank"}).status_code == 422
    ok(api.patch(f"/api/accounting/accounts/{created['id']}", json={"is_active": False}))
    assert api.patch(f"/api/accounting/accounts/{acct(api, '1000')}", json={"is_active": False}).status_code == 409


def test_operational_sync_is_idempotent_and_balanced(api):
    with psycopg.connect(TEST_DB) as conn:
        suffix = str(os.getpid()) + str(abs(hash(str(TODAY))) % 10000)
        cat = conn.execute("INSERT INTO categories(name,slug) VALUES('Acc test',%s) RETURNING id", ("acc-" + suffix,)).fetchone()[0]
        prod = conn.execute("INSERT INTO products(category_id,name,slug,status,tax_rate) VALUES(%s,'Acc product',%s,'active',18) RETURNING id",
                            (cat, "acc-prod-" + suffix)).fetchone()[0]
        var = conn.execute("INSERT INTO product_variants(product_id,sku,selling_price,cost_price) VALUES(%s,%s,590,300) RETURNING id",
                           (prod, "ACC-" + suffix)).fetchone()[0]
        order = conn.execute("INSERT INTO orders(order_number,channel,customer_name,status,subtotal,total) VALUES(%s,'pos','Walk-in','placed',1180,1180) RETURNING id",
                             ("ACC-ORD-" + suffix,)).fetchone()[0]
        conn.execute("INSERT INTO order_lines(order_id,variant_id,quantity,unit_price,line_total) VALUES(%s,%s,2,590,1180)", (order, var))
        conn.execute("INSERT INTO payments(payment_reference,order_id,method,amount,status) VALUES(%s,%s,'upi',1180,'captured')",
                     ("ACC-PAY-" + suffix, order))
        sup = conn.execute("INSERT INTO suppliers(name) VALUES('Acc supplier') RETURNING id").fetchone()[0]
        loc = conn.execute("INSERT INTO stock_locations(name,location_type) VALUES(%s,'store') RETURNING id", ("Acc store " + suffix,)).fetchone()[0]
        po = conn.execute("INSERT INTO purchase_orders(purchase_number,supplier_id,location_id,status,subtotal) VALUES(%s,%s,%s,'ordered',3000) RETURNING id",
                          ("ACC-PO-" + suffix, sup, loc)).fetchone()[0]
        conn.execute("INSERT INTO purchase_order_lines(purchase_order_id,variant_id,quantity_ordered,unit_cost) VALUES(%s,%s,10,300)", (po, var))
        conn.execute("INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id) VALUES(%s,%s,'receipt',10,'purchase_order',%s)",
                     (var, loc, str(po)))

    status = ok(api.get("/api/accounting/sync/status"))
    assert status["orders"] >= 1 and status["payments"] >= 1 and status["goods_receipts"] >= 1
    first = ok(api.post("/api/accounting/sync"))
    assert first["errors"] == [] and first["orders"] >= 1 and first["payments"] >= 1 and first["goods_receipts"] >= 1
    second = ok(api.post("/api/accounting/sync"))
    assert second["orders"] == second["payments"] == second["goods_receipts"] == 0
    assert second["pending"]["pending_total"] == 0

    gst = ok(api.get("/api/accounting/reports/gst-summary"))
    assert float(gst["output_tax"]["cgst"]) >= 90.0

    with psycopg.connect(TEST_DB) as conn:
        conn.execute("UPDATE orders SET status='cancelled', updated_at=now() WHERE id=%s", (order,))
        conn.execute("UPDATE payments SET status='refunded', updated_at=now() WHERE order_id=%s", (order,))
    third = ok(api.post("/api/accounting/sync"))
    assert third["order_cancellations"] == 1 and third["refunds"] == 1
    assert ok(api.get("/api/accounting/reports/trial-balance"))["balanced"] is True
    assert ok(api.get("/api/accounting/reports/balance-sheet"))["balanced"] is True
    receivable = ok(api.get("/api/accounting/reports/parties", params={"kind": "receivable"}))
    assert all(p["party_name"] != "Walk-in" for p in receivable["items"])


def test_rounded_down_invoice_total_is_billed_amount(api):
    # 45 + 18% GST = 53.10 -> rounded to 53.00; total debits are 53.10 (round-off is a debit),
    # but the voucher total must show the billed 53.00, and a reversal keeps that value.
    invoice = ok(api.post("/api/accounting/invoices", json={
        "invoice_type": "sales", "voucher_date": "2026-10-01", "party_name": "Round Down Buyer",
        "lines": [{"description": "Sugar", "quantity": "1", "rate": "45", "gst_rate": "18"}],
    }), 201)
    assert Decimal(str(invoice["total_amount"])) == Decimal("53.00")
    debits = sum(Decimal(str(line["debit"])) for line in invoice["lines"])
    credits = sum(Decimal(str(line["credit"])) for line in invoice["lines"])
    assert debits == credits == Decimal("53.10")
    reversal = ok(api.post(f"/api/accounting/vouchers/{invoice['id']}/reverse",
                           json={"reason": "Rounding test", "reversal_date": "2026-10-02"}), 201)
    assert Decimal(str(reversal["total_amount"])) == Decimal("53.00")
