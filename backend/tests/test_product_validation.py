"""Focused validation tests for product delivery configuration models.

Run from repository root with: python -m pytest backend/tests -q
These tests are database-free and do not change the application database.
"""
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import ProductAvailabilityRuleInput, ProductRegionWriteInput


def test_availability_defaults_to_unrestricted_selection():
    payload = ProductAvailabilityRuleInput()
    assert payload.region_ids == []
    assert payload.pincodes == []
    assert payload.warehouse_ids == []
    assert payload.variant_id is None


def test_availability_accepts_variant_and_delivery_scopes():
    payload = ProductAvailabilityRuleInput(
        variant_id=12,
        region_ids=[1, 2],
        pincodes=["110001", "560001"],
        warehouse_ids=[3],
    )
    assert payload.variant_id == 12
    assert payload.region_ids == [1, 2]
    assert payload.pincodes == ["110001", "560001"]
    assert payload.warehouse_ids == [3]


@pytest.mark.parametrize("variant_id", [0, -1])
def test_availability_rejects_nonpositive_variant_id(variant_id):
    with pytest.raises(ValidationError):
        ProductAvailabilityRuleInput(variant_id=variant_id)


def test_region_requires_a_name_and_code():
    with pytest.raises(ValidationError):
        ProductRegionWriteInput(name="x", code="x")


def test_region_accepts_six_digit_pincodes_as_strings():
    payload = ProductRegionWriteInput(
        name="Delhi NCR",
        code="DELHI_NCR",
        pincodes=["110001", "011001"],
    )
    assert payload.pincodes == ["110001", "011001"]


def test_region_rejects_too_many_pincodes():
    with pytest.raises(ValidationError):
        ProductRegionWriteInput(
            name="Delhi NCR",
            code="DELHI_NCR",
            pincodes=["110001"] * 2001,
        )
