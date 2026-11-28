from decimal import Decimal

import pytest

from app.services.indian_gst import calculate_indian_gst


def test_intrastate_gst_splits_equally_between_cgst_and_sgst():
    result = calculate_indian_gst(
        taxable_value="100.00", gst_rate="18", supply_type="intra_state", hsn_code="61091000"
    )
    assert result["cgst_amount"] == Decimal("9.00")
    assert result["sgst_amount"] == Decimal("9.00")
    assert result["igst_amount"] == Decimal("0.00")
    assert result["total_tax"] == Decimal("18.00")
    assert result["line_total"] == Decimal("118.00")


def test_interstate_gst_uses_igst_only():
    result = calculate_indian_gst(taxable_value="100", gst_rate="5", supply_type="inter_state")
    assert result["cgst_amount"] == Decimal("0.00")
    assert result["sgst_amount"] == Decimal("0.00")
    assert result["igst_amount"] == Decimal("5.00")
    assert result["line_total"] == Decimal("105.00")


def test_tax_rounding_is_half_up_to_paise():
    result = calculate_indian_gst(taxable_value="0.10", gst_rate="5", supply_type="inter_state")
    assert result["total_tax"] == Decimal("0.01")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"taxable_value": "-1", "gst_rate": "5", "supply_type": "inter_state"},
        {"taxable_value": "1", "gst_rate": "101", "supply_type": "inter_state"},
        {"taxable_value": "1", "gst_rate": "5", "supply_type": "unknown"},
        {"taxable_value": "1", "gst_rate": "5", "supply_type": "intra_state", "hsn_code": "123"},
        {"taxable_value": "NaN", "gst_rate": "5", "supply_type": "inter_state"},
    ],
)
def test_invalid_gst_inputs_are_rejected(kwargs):
    with pytest.raises(ValueError):
        calculate_indian_gst(**kwargs)


def test_zero_rate_tax_is_supported():
    result = calculate_indian_gst(taxable_value="99.99", gst_rate="0", supply_type="intra_state")
    assert result["total_tax"] == Decimal("0.00")
    assert result["line_total"] == Decimal("99.99")

def test_inclusive_gst_extracts_cgst_sgst_without_changing_payable_total():
    from app.services.indian_gst import calculate_indian_gst_inclusive

    result = calculate_indian_gst_inclusive(
        gross_value="118.00", gst_rate="18", supply_type="intra_state", hsn_code="12345678",
    )
    assert result["taxable_value"] == Decimal("100.00")
    assert result["cgst_amount"] == Decimal("9.00")
    assert result["sgst_amount"] == Decimal("9.00")
    assert result["igst_amount"] == Decimal("0.00")
    assert result["line_total"] == Decimal("118.00")


def test_inclusive_gst_extracts_igst_for_inter_state_supply():
    from app.services.indian_gst import calculate_indian_gst_inclusive

    result = calculate_indian_gst_inclusive(
        gross_value="118.00", gst_rate="18", supply_type="inter_state", hsn_code="12345678",
    )
    assert result["taxable_value"] == Decimal("100.00")
    assert result["igst_amount"] == Decimal("18.00")
    assert result["cgst_amount"] == Decimal("0.00")
    assert result["sgst_amount"] == Decimal("0.00")
    assert result["line_total"] == Decimal("118.00")
