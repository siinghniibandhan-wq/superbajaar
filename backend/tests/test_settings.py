import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.settings import BusinessSettings, DEFAULT_SETTINGS, _can_manage


def test_settings_defaults_validate():
    payload = BusinessSettings.model_validate(DEFAULT_SETTINGS)
    assert payload.businessName == "Super Bajaar"
    assert payload.currency == "INR"
    assert payload.timezone == "Asia/Kolkata"
    assert payload.lowStockThreshold == "5"


def test_gstin_is_normalized_and_validated():
    payload = BusinessSettings(gstin="27ABCDE1234F1Z5")
    assert payload.gstin == "27ABCDE1234F1Z5"
    with pytest.raises(ValidationError):
        BusinessSettings(gstin="not-a-gstin")


def test_tax_rate_and_threshold_bounds_are_enforced():
    with pytest.raises(ValidationError):
        BusinessSettings(defaultGstRate="101")
    with pytest.raises(ValidationError):
        BusinessSettings(lowStockThreshold="-1")


def test_only_owner_or_admin_can_change_settings():
    _can_manage({"role": "owner"})
    _can_manage({"role": "admin"})
    with pytest.raises(HTTPException) as exc:
        _can_manage({"role": "staff"})
    assert exc.value.status_code == 403
