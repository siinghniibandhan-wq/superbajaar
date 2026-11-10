from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.purchasing_lifecycle import (
    SupplierInvoiceReviewReason,
    SupplierInvoiceLineInput,
    build_supplier_invoice_voucher_lines,
    supplier_invoice_grni_matches,
    supplier_invoice_grn_is_accepted,
    supplier_return_ap_debit_matches,
    supplier_return_gst_reversal_matches,
    validate_supplier_invoice_tax_mode,
)


def _codes():
    return {code: {"id": index} for index, code in enumerate(("2050", "1300", "1301", "1302", "2000"), start=1)}


def test_supplier_invoice_approval_voucher_balances_when_grni_matches_received_value():
    invoice = {
        "taxable_value": Decimal("1000.00"),
        "freight_amount": Decimal("50.00"),
        "discount_amount": Decimal("10.00"),
        "cgst_amount": Decimal("93.60"),
        "sgst_amount": Decimal("93.60"),
        "igst_amount": Decimal("0.00"),
        "cess_amount": Decimal("0.00"),
        "invoice_total": Decimal("1227.20"),
    }

    lines = build_supplier_invoice_voucher_lines(invoice, _codes())

    assert lines[0]["account_id"] == _codes()["2050"]["id"]
    assert lines[0]["debit"] == Decimal("1040.00")
    assert [line["account_id"] for line in lines[1:3]] == [
        _codes()["1300"]["id"], _codes()["1301"]["id"]
    ]
    assert lines[-1]["account_id"] == _codes()["2000"]["id"]
    assert lines[-1]["credit"] == Decimal("1227.20")
    assert sum((line.get("debit", Decimal("0")) for line in lines), Decimal("0")) == sum(
        (line.get("credit", Decimal("0")) for line in lines), Decimal("0")
    )
    assert supplier_invoice_grni_matches(invoice, Decimal("1040.00"))
    assert not supplier_invoice_grni_matches(invoice, Decimal("1000.00"))


def test_supplier_invoice_approval_blocks_unconfigured_cess_ledger():
    invoice = {
        "taxable_value": Decimal("100.00"), "freight_amount": Decimal("0.00"),
        "discount_amount": Decimal("0.00"), "cgst_amount": Decimal("0.00"),
        "sgst_amount": Decimal("0.00"), "igst_amount": Decimal("0.00"),
        "cess_amount": Decimal("1.00"), "invoice_total": Decimal("101.00"),
    }

    with pytest.raises(HTTPException, match="cess requires a configured"):
        build_supplier_invoice_voucher_lines(invoice, _codes())


def test_supplier_invoice_approval_rejects_non_positive_net_grni():
    invoice = {
        "taxable_value": Decimal("100.00"), "freight_amount": Decimal("0.00"),
        "discount_amount": Decimal("100.00"), "cgst_amount": Decimal("0.00"),
        "sgst_amount": Decimal("0.00"), "igst_amount": Decimal("0.00"),
        "cess_amount": Decimal("0.00"), "invoice_total": Decimal("0.00"),
    }

    with pytest.raises(HTTPException, match="Net GRNI amount"):
        build_supplier_invoice_voucher_lines(invoice, _codes())


from app.api.purchasing_lifecycle import supplier_return_valuation_matches


def test_supplier_return_debit_note_must_match_dispatched_inventory_valuation():
    assert supplier_return_valuation_matches(Decimal("247.35"), Decimal("247.35"))
    assert supplier_return_valuation_matches(Decimal("247.354"), Decimal("247.35"))
    assert not supplier_return_valuation_matches(Decimal("247.35"), Decimal("277.35"))


def test_supplier_invoice_line_tax_matches_rate_and_intrastate_components():
    line = SupplierInvoiceLineInput(
        purchase_order_line_id=1, goods_receipt_line_id=1, quantity=1, unit_rate=100,
        taxable_value=100, gst_rate=18, cgst_amount=9, sgst_amount=9, igst_amount=0,
    )
    assert line.cgst_amount + line.sgst_amount == Decimal("18")


def test_supplier_invoice_line_tax_matches_rate_and_interstate_component():
    line = SupplierInvoiceLineInput(
        purchase_order_line_id=1, goods_receipt_line_id=1, quantity=1, unit_rate=100,
        taxable_value=100, gst_rate=18, cgst_amount=0, sgst_amount=0, igst_amount=18,
    )
    assert line.igst_amount == Decimal("18")


def test_supplier_invoice_line_rejects_tax_that_does_not_match_rate():
    with pytest.raises(ValueError, match="multiplied by GST rate"):
        SupplierInvoiceLineInput(
            purchase_order_line_id=1, goods_receipt_line_id=1, quantity=1, unit_rate=100,
            taxable_value=100, gst_rate=18, cgst_amount=10, sgst_amount=10, igst_amount=0,
        )


def test_supplier_invoice_line_rejects_mixed_gst_components():
    with pytest.raises(ValueError, match="not both"):
        SupplierInvoiceLineInput(
            purchase_order_line_id=1, goods_receipt_line_id=1, quantity=1, unit_rate=100,
            taxable_value=100, gst_rate=18, cgst_amount=9, sgst_amount=0, igst_amount=9,
        )


def test_supplier_invoice_line_requires_rate_for_nonzero_tax():
    with pytest.raises(ValueError, match="GST rate is required"):
        SupplierInvoiceLineInput(
            purchase_order_line_id=1, goods_receipt_line_id=1, quantity=1, unit_rate=100,
            taxable_value=100, cgst_amount=9, sgst_amount=9,
        )


def test_supplier_invoice_rejects_mixing_interstate_and_intrastate_lines():
    lines = [
        SupplierInvoiceLineInput(
            purchase_order_line_id=1, goods_receipt_line_id=1, quantity=1, unit_rate=100,
            taxable_value=100, gst_rate=18, cgst_amount=9, sgst_amount=9,
        ),
        SupplierInvoiceLineInput(
            purchase_order_line_id=2, goods_receipt_line_id=2, quantity=1, unit_rate=100,
            taxable_value=100, gst_rate=18, igst_amount=18,
        ),
    ]
    with pytest.raises(HTTPException, match="cannot mix IGST"):
        validate_supplier_invoice_tax_mode(lines)


def test_supplier_invoice_rejection_requires_and_trims_reason():
    review = SupplierInvoiceReviewReason(reason="  Rate mismatch  ")
    assert review.reason == "Rate mismatch"

    with pytest.raises(ValueError, match="at least 3 characters"):
        SupplierInvoiceReviewReason(reason="  ")


def test_supplier_invoice_requires_qc_accepted_grn_status():
    assert supplier_invoice_grn_is_accepted("accepted")
    assert supplier_invoice_grn_is_accepted("partially_accepted")
    assert not supplier_invoice_grn_is_accepted("pending_qc")
    assert not supplier_invoice_grn_is_accepted("rejected")


def test_supplier_return_debit_note_must_reduce_supplier_payable_by_voucher_total():
    assert supplier_return_ap_debit_matches(Decimal("277.35"), Decimal("277.35"))
    assert not supplier_return_ap_debit_matches(Decimal("277.35"), Decimal("247.35"))


def test_supplier_return_requires_component_wise_input_gst_reversal():
    expected = {"cgst": Decimal("9.00"), "sgst": Decimal("9.00"), "igst": Decimal("0.00")}
    assert supplier_return_gst_reversal_matches(
        expected, {"cgst": Decimal("9.00"), "sgst": Decimal("9.00"), "igst": Decimal("0.00")}
    )
    assert not supplier_return_gst_reversal_matches(
        expected, {"cgst": Decimal("18.00"), "sgst": Decimal("0.00"), "igst": Decimal("0.00")}
    )
    assert not supplier_return_gst_reversal_matches(
        expected, {"cgst": Decimal("9.00"), "sgst": Decimal("8.99"), "igst": Decimal("0.00")}
    )


def test_supplier_return_debit_note_voucher_cannot_be_reused():
    from app.api.purchasing_lifecycle import supplier_return_voucher_is_unallocated

    assert supplier_return_voucher_is_unallocated(None)
    assert not supplier_return_voucher_is_unallocated(42)


from datetime import date
from app.services.accounting_posting import (
    PostingConfigurationError,
    build_supplier_invoice_mapping_lines,
)


def _purchase_mapping(role, account_id, component=None):
    return {
        "legal_entity_code": "DEFAULT", "source_module": "purchasing",
        "event_type": "supplier_invoice_approval", "line_role": role,
        "tax_component": component, "account_id": account_id,
        "status": "approved", "effective_from": date(2026, 4, 1),
        "effective_to": None,
    }


def test_supplier_invoice_uses_approved_event_mappings_and_balances():
    mappings = [
        _purchase_mapping("grni_clearing", 2050),
        _purchase_mapping("input_tax", 1300, "cgst"),
        _purchase_mapping("input_tax", 1301, "sgst"),
        _purchase_mapping("accounts_payable", 2000),
    ]
    invoice = {
        "taxable_value": "1000", "freight_amount": "50", "discount_amount": "10",
        "cgst_amount": "93.60", "sgst_amount": "93.60", "igst_amount": "0",
        "cess_amount": "0", "invoice_total": "1227.20",
    }
    lines = build_supplier_invoice_mapping_lines(
        invoice, mappings, legal_entity_code="DEFAULT", event_date=date(2026, 11, 2)
    )
    assert [line["account_id"] for line in lines] == [2050, 1300, 1301, 2000]
    assert sum(line["debit"] for line in lines) == Decimal("1227.20")
    assert sum(line["credit"] for line in lines) == Decimal("1227.20")


def test_supplier_invoice_mapping_fails_closed_for_missing_or_duplicate_mapping():
    invoice = {
        "taxable_value": "100", "freight_amount": "0", "discount_amount": "0",
        "cgst_amount": "0", "sgst_amount": "0", "igst_amount": "0",
        "cess_amount": "0", "invoice_total": "100",
    }
    with pytest.raises(PostingConfigurationError, match="found 0"):
        build_supplier_invoice_mapping_lines(
            invoice, [], legal_entity_code="DEFAULT", event_date=date(2026, 11, 2)
        )
    mappings = [
        _purchase_mapping("grni_clearing", 2050),
        _purchase_mapping("grni_clearing", 2051),
        _purchase_mapping("accounts_payable", 2000),
    ]
    with pytest.raises(PostingConfigurationError, match="found 2"):
        build_supplier_invoice_mapping_lines(
            invoice, mappings, legal_entity_code="DEFAULT", event_date=date(2026, 11, 2)
        )
