import pytest
from pydantic import ValidationError

from app.api.vendor_portal import InvoiceInput
from app.api.employee_portal import LeaveInput


def test_vendor_invoice_total_must_reconcile_to_taxable_value_and_tax():
    payload = InvoiceInput(
        purchase_order_id=7,
        invoice_number="INV-1001",
        invoice_date="2026-11-10",
        taxable_value="1000.00",
        cgst_amount="90.00",
        sgst_amount="90.00",
        invoice_total="1180.00",
    )
    assert payload.invoice_total == 1180


def test_vendor_invoice_rejects_mismatched_total():
    with pytest.raises(ValidationError, match="Invoice total must equal"):
        InvoiceInput(
            purchase_order_id=7,
            invoice_number="INV-1002",
            invoice_date="2026-11-10",
            taxable_value="1000.00",
            cgst_amount="90.00",
            sgst_amount="90.00",
            invoice_total="1100.00",
        )


def test_vendor_invoice_rejects_due_date_before_invoice_date():
    with pytest.raises(ValidationError, match="due date cannot precede"):
        InvoiceInput(
            purchase_order_id=7,
            invoice_number="INV-1003",
            invoice_date="2026-11-10",
            due_date="2026-11-09",
            taxable_value="1000.00",
            invoice_total="1000.00",
        )


def test_employee_leave_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError, match="Leave end date cannot precede"):
        LeaveInput(
            leave_type="annual",
            start_date="2026-11-12",
            end_date="2026-11-11",
            days="1",
            reason="Personal work",
        )
