"""Accounting API tests that need no database: validation, access and posting maths."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import accounting
from app.main import app

client = TestClient(app)
D = Decimal


def _codes():
    codes = [accounting.A_AR, accounting.A_AP, accounting.A_GRNI, accounting.A_INVENTORY, accounting.A_SALES,
             accounting.A_SALES_RETURN, accounting.A_ROUND_OFF, accounting.A_IN_CGST, accounting.A_IN_SGST,
             accounting.A_IN_IGST, accounting.A_OUT_CGST, accounting.A_OUT_SGST, accounting.A_OUT_IGST,
             accounting.A_OTHER_CHARGES, accounting.A_DISCOUNT, accounting.A_COGS, *accounting.SETTLEMENT_ACCOUNTS.values()]
    return {code: {"id": index + 1, "code": code} for index, code in enumerate(dict.fromkeys(codes))}


def _balanced(lines):
    debit = sum((D(str(l.get("debit", 0))) for l in lines), D("0"))
    credit = sum((D(str(l.get("credit", 0))) for l in lines), D("0"))
    return debit, credit


def test_accounting_requires_database_configuration(monkeypatch):
    monkeypatch.setattr(accounting.settings, "database_url", "")
    response = client.get("/api/accounting/reports/summary")
    assert response.status_code == 503
    assert response.json()["detail"] == "Accounting database is not configured"


def test_reader_dependency_blocks_staff_and_viewer(monkeypatch):
    monkeypatch.setattr(accounting.settings, "database_url", "postgresql://example.invalid/db")
    for role in ("staff", "viewer", "customer", None):
        with pytest.raises(HTTPException) as caught:
            accounting.require_accounting_reader(SimpleNamespace(state=SimpleNamespace(role=role)), None)
        assert caught.value.status_code == 403
    for role in ("owner", "admin", "manager"):
        accounting.require_accounting_reader(SimpleNamespace(state=SimpleNamespace(role=role)), None)


def test_manager_cannot_write_accounting_through_middleware():
    from app.core.auth_middleware import _role_can_write

    assert not _role_can_write("manager", "/api/accounting/vouchers")
    assert not _role_can_write("staff", "/api/accounting/vouchers")
    assert _role_can_write("admin", "/api/accounting/vouchers")


def test_unbalanced_voucher_is_rejected_before_database_access():
    response = client.post("/api/accounting/vouchers", json={
        "voucher_type": "journal", "voucher_date": "2026-10-31",
        "lines": [{"account_id": 1, "debit": "100"}, {"account_id": 2, "credit": "90"}],
    })
    assert response.status_code == 422


def test_voucher_line_cannot_have_both_debit_and_credit():
    response = client.post("/api/accounting/vouchers", json={
        "voucher_type": "journal", "voucher_date": "2026-10-31",
        "lines": [{"account_id": 1, "debit": "100", "credit": "100"}, {"account_id": 2, "credit": "100"}],
    })
    assert response.status_code == 422


def test_invoice_types_are_not_accepted_on_generic_voucher_endpoint():
    response = client.post("/api/accounting/vouchers", json={
        "voucher_type": "sales", "voucher_date": "2026-10-31",
        "lines": [{"account_id": 1, "debit": "100"}, {"account_id": 2, "credit": "100"}],
    })
    assert response.status_code == 422


def test_invoice_rejects_unsupported_gst_rate_and_bad_gstin():
    base = {"invoice_type": "sales", "voucher_date": "2026-10-31", "party_name": "A customer",
            "lines": [{"description": "Rice", "rate": "100", "gst_rate": "18"}]}
    assert client.post("/api/accounting/invoices", json={**base, "lines": [{"description": "Rice", "rate": "100", "gst_rate": "17"}]}).status_code == 422
    assert client.post("/api/accounting/invoices", json={**base, "party_gstin": "BADGSTIN"}).status_code == 422
    assert client.post("/api/accounting/invoices", json={**base, "lines": []}).status_code == 422
    assert client.post("/api/accounting/invoices", json={**base, "against_receipt": True}).status_code == 422


def test_reverse_requires_reason():
    response = client.post("/api/accounting/vouchers/1/reverse", json={"reason": "  "})
    assert response.status_code == 422


def test_settings_reject_gstin_state_mismatch():
    response = client.put("/api/accounting/settings", json={
        "business_name": "Super Bajaar", "gstin": "10ABCDE1234F1Z5", "state_code": "09",
    })
    assert response.status_code == 422


def test_fiscal_year_follows_indian_april_to_march_year():
    assert accounting.fiscal_year(date(2026, 3, 31)) == "2025-26"
    assert accounting.fiscal_year(date(2026, 4, 1)) == "2026-27"
    assert accounting.fiscal_year_start(date(2027, 1, 15)) == date(2026, 4, 1)


def test_gst_split_intra_and_inter_state():
    assert accounting.split_gst(D("1000.00"), D("18"), "intra") == {"cgst": D("90.00"), "sgst": D("90.00")}
    assert accounting.split_gst(D("1000.00"), D("18"), "inter") == {"igst": D("180.00")}
    odd = accounting.split_gst(D("10.10"), D("5"), "intra")
    assert odd["cgst"] + odd["sgst"] == D("0.51")


def test_inclusive_split_reconstructs_gross():
    taxable, tax = accounting.inclusive_split(D("118.00"), D("18"))
    assert (taxable, tax) == (D("100.00"), D("18.00"))
    taxable, tax = accounting.inclusive_split(D("99.99"), D("12"))
    assert taxable + tax == D("99.99")
    assert accounting.inclusive_split(D("50"), D("0")) == (D("50.00"), D("0.00"))


def test_sales_invoice_lines_balance_with_round_off():
    payload = accounting.InvoiceCreate(
        invoice_type="sales", voucher_date=date(2026, 10, 31), party_name="Ravi Traders",
        lines=[
            {"description": "Basmati rice 5kg", "quantity": "3", "rate": "333.33", "gst_rate": "5"},
            {"description": "Steel bottle", "quantity": "1", "rate": "499", "discount": "20", "gst_rate": "18"},
        ],
    )
    lines, taxable, tax = accounting.build_invoice_lines(payload, _codes(), {})
    debit, credit = _balanced(lines)
    assert debit == credit
    assert taxable == D("999.99") + D("479.00")
    assert tax == D("50.00") + D("86.22")
    assert lines[0]["debit"] == D("1615")  # 1615.21 rounded to the nearest rupee
    assert any(l.get("narration") == "Round off" for l in lines)


def test_purchase_bill_against_receipt_clears_grni_with_igst():
    payload = accounting.InvoiceCreate(
        invoice_type="purchase", voucher_date=date(2026, 10, 31), party_name="Supplier", place_of_supply="inter",
        against_receipt=True, round_off=False, lines=[{"description": "Stock", "quantity": "10", "rate": "50", "gst_rate": "12"}],
    )
    codes = _codes()
    lines, taxable, tax = accounting.build_invoice_lines(payload, codes, {})
    assert _balanced(lines) == (D("560.00"), D("560.00"))
    assert lines[0]["account_id"] == codes[accounting.A_AP]["id"] and lines[0]["credit"] == D("560.00")
    assert any(l["account_id"] == codes[accounting.A_GRNI]["id"] and l["debit"] == D("500.00") for l in lines)
    assert any(l.get("tax_component") == "igst" and l["debit"] == D("60.00") for l in lines)


def test_credit_note_reverses_sales_sides_and_cash_settlement():
    payload = accounting.InvoiceCreate(
        invoice_type="credit_note", voucher_date=date(2026, 10, 31), party_name="Walk-in", settlement="cash",
        round_off=False, lines=[{"description": "Return", "rate": "100", "gst_rate": "18"}],
    )
    codes = _codes()
    lines, _, _ = accounting.build_invoice_lines(payload, codes, {})
    assert lines[0]["account_id"] == codes[accounting.A_CASH]["id"] and lines[0]["credit"] == D("118.00")
    assert any(l["account_id"] == codes[accounting.A_SALES_RETURN]["id"] and l["debit"] == D("100.00") for l in lines)


def test_order_posting_handles_inclusive_tax_charges_and_cogs():
    codes = _codes()
    order = {"total": D("1218.00"), "customer_name": "Asha"}
    items = [
        {"line_total": D("1180.00"), "tax_rate": D("18"), "cost_price": D("400"), "quantity": 2},
        {"line_total": D("0.00"), "tax_rate": None, "cost_price": None, "quantity": 1},
    ]
    lines, taxable, tax = accounting.build_order_lines(order, items, codes, "intra")
    debit, credit = _balanced(lines)
    assert debit == credit
    assert (taxable, tax) == (D("1000.00"), D("180.00"))
    assert any(l["account_id"] == codes[accounting.A_OTHER_CHARGES]["id"] and l["credit"] == D("38.00") for l in lines)
    assert any(l["account_id"] == codes[accounting.A_COGS]["id"] and l["debit"] == D("800.00") for l in lines)


def test_order_discount_is_posted_when_total_is_below_line_sum():
    codes = _codes()
    lines, _, _ = accounting.build_order_lines({"total": D("90"), "customer_name": "B"},
                                               [{"line_total": D("100"), "tax_rate": D("0"), "cost_price": None, "quantity": 1}],
                                               codes, "intra")
    assert _balanced(lines) == (D("100.00"), D("100.00"))
    assert any(l["account_id"] == codes[accounting.A_DISCOUNT]["id"] and l["debit"] == D("10") for l in lines)


def test_aging_allocates_outstanding_to_newest_entries():
    entries = [{"date": date(2026, 6, 1), "amount": D("500")}, {"date": date(2026, 10, 20), "amount": D("300")}]
    buckets = accounting.age_outstanding(entries, D("600"), date(2026, 10, 31))
    assert buckets == {"current": D("300"), "d31_60": D("0.00"), "d61_90": D("0.00"), "d90_plus": D("300")}


def test_profit_and_loss_sections():
    rows = [
        {"id": 1, "code": "4000", "name": "Sales", "account_type": "income", "sub_type": "sales", "debit": 0, "credit": 1000},
        {"id": 2, "code": "4010", "name": "Returns", "account_type": "income", "sub_type": "sales_return", "debit": 100, "credit": 0},
        {"id": 3, "code": "5000", "name": "COGS", "account_type": "expense", "sub_type": "cogs", "debit": 500, "credit": 0},
        {"id": 4, "code": "4200", "name": "Other", "account_type": "income", "sub_type": "other_income", "debit": 0, "credit": 50},
        {"id": 5, "code": "6000", "name": "Rent", "account_type": "expense", "sub_type": "operating", "debit": 200, "credit": 0},
    ]
    pl = accounting.profit_and_loss_from_rows(rows)
    assert pl["gross_profit"] == D("400.00")
    assert pl["net_profit"] == D("250.00")
