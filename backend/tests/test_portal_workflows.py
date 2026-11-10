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
        source_document_uri="s3://private-bucket/vendor-invoices/1/abc.pdf",
        lines=[{"purchase_order_line_id": 1, "goods_receipt_line_id": 2, "quantity": "10", "unit_rate": "100", "taxable_value": "1000", "gst_rate": "18", "cgst_amount": "90", "sgst_amount": "90", "igst_amount": "0"}],
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
            source_document_uri="s3://private-bucket/vendor-invoices/1/abc.pdf",
        lines=[{"purchase_order_line_id": 1, "goods_receipt_line_id": 2, "quantity": "10", "unit_rate": "100", "taxable_value": "1000", "gst_rate": "18", "cgst_amount": "90", "sgst_amount": "90", "igst_amount": "0"}],
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
            source_document_uri="s3://private-bucket/vendor-invoices/1/abc.pdf",
        lines=[{"purchase_order_line_id": 1, "goods_receipt_line_id": 2, "quantity": "10", "unit_rate": "100", "taxable_value": "1000", "gst_rate": "18", "cgst_amount": "90", "sgst_amount": "90", "igst_amount": "0"}],
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


def test_vendor_document_signature_accepts_valid_pdf_jpeg_and_png():
    from app.api.vendor_portal import _matches_document_signature

    assert _matches_document_signature("application/pdf", b"%PDF-1.7")
    assert _matches_document_signature("image/jpeg", bytes((0xFF, 0xD8, 0xFF, 0xE0)))
    assert _matches_document_signature("image/png", bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)))


def test_vendor_document_signature_rejects_mismatched_or_unknown_content():
    from app.api.vendor_portal import _matches_document_signature

    assert not _matches_document_signature("image/jpeg", b"\\xff\\xd8\\xff")
    assert not _matches_document_signature("image/png", b"not a png")
    assert not _matches_document_signature("text/plain", b"hello")
