"""Deterministic Indian GST arithmetic for order-line tax snapshots.

The caller must resolve the effective HSN/GST rule and supply type before calling
this module. This module deliberately does not guess tax rates or jurisdiction.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")
MAX_GST_RATE = Decimal("100")


def _decimal(value, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid decimal amount") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def calculate_indian_gst(*, taxable_value, gst_rate, supply_type: str, hsn_code: str | None = None) -> dict:
    """Calculate line GST for intra-state or inter-state supply, rounded to paise."""
    taxable = _decimal(taxable_value, "taxable_value")
    rate = _decimal(gst_rate, "gst_rate")
    if taxable < 0:
        raise ValueError("taxable_value cannot be negative")
    if rate < 0 or rate > MAX_GST_RATE:
        raise ValueError("gst_rate must be between 0 and 100")
    if supply_type not in {"intra_state", "inter_state"}:
        raise ValueError("supply_type must be intra_state or inter_state")
    if hsn_code is not None and (not isinstance(hsn_code, str) or len(hsn_code) != 8 or not hsn_code.isdigit()):
        raise ValueError("hsn_code must contain exactly 8 digits")

    taxable = taxable.quantize(MONEY, rounding=ROUND_HALF_UP)
    total_tax = (taxable * rate / Decimal("100")).quantize(MONEY, rounding=ROUND_HALF_UP)
    if supply_type == "intra_state":
        cgst = (total_tax / Decimal("2")).quantize(MONEY, rounding=ROUND_HALF_UP)
        sgst = total_tax - cgst
        igst = Decimal("0.00")
    else:
        cgst = Decimal("0.00")
        sgst = Decimal("0.00")
        igst = total_tax

    return {
        "hsn_code": hsn_code,
        "taxable_value": taxable,
        "gst_rate": rate,
        "supply_type": supply_type,
        "cgst_rate": rate / Decimal("2") if supply_type == "intra_state" else Decimal("0"),
        "sgst_rate": rate / Decimal("2") if supply_type == "intra_state" else Decimal("0"),
        "igst_rate": rate if supply_type == "inter_state" else Decimal("0"),
        "cgst_amount": cgst,
        "sgst_amount": sgst,
        "igst_amount": igst,
        "total_tax": total_tax,
        "line_total": taxable + total_tax,
    }

def calculate_indian_gst_inclusive(*, gross_value, gst_rate, supply_type: str, hsn_code: str | None = None) -> dict:
    """Extract GST from a GST-inclusive retail price without changing the payable amount."""
    gross = _decimal(gross_value, "gross_value")
    rate = _decimal(gst_rate, "gst_rate")
    if gross < 0:
        raise ValueError("gross_value cannot be negative")
    if rate < 0 or rate > MAX_GST_RATE:
        raise ValueError("gst_rate must be between 0 and 100")
    if supply_type not in {"intra_state", "inter_state"}:
        raise ValueError("supply_type must be intra_state or inter_state")
    if hsn_code is not None and (not isinstance(hsn_code, str) or len(hsn_code) != 8 or not hsn_code.isdigit()):
        raise ValueError("hsn_code must contain exactly 8 digits")
    gross = gross.quantize(MONEY, rounding=ROUND_HALF_UP)
    if rate == 0:
        taxable = gross
    else:
        taxable = (gross / (Decimal("1") + rate / Decimal("100"))).quantize(MONEY, rounding=ROUND_HALF_UP)
    total_tax = gross - taxable
    if supply_type == "intra_state":
        cgst = (total_tax / Decimal("2")).quantize(MONEY, rounding=ROUND_HALF_UP)
        sgst = total_tax - cgst
        igst = Decimal("0.00")
    else:
        cgst = sgst = Decimal("0.00")
        igst = total_tax
    return {
        "hsn_code": hsn_code, "gross_value": gross, "taxable_value": taxable,
        "gst_rate": rate, "supply_type": supply_type,
        "cgst_rate": rate / Decimal("2") if supply_type == "intra_state" else Decimal("0"),
        "sgst_rate": rate / Decimal("2") if supply_type == "intra_state" else Decimal("0"),
        "igst_rate": rate if supply_type == "inter_state" else Decimal("0"),
        "cgst_amount": cgst, "sgst_amount": sgst, "igst_amount": igst,
        "total_tax": total_tax, "line_total": gross,
    }

