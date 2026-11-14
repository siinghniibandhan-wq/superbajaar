import pytest
from pydantic import ValidationError

from app.api.inventory import FacilityProfileCreate


def valid_profile(**overrides):
    payload = {
        "facility_code": " pat-warehouse-01 ",
        "address_line1": "Plot 12, Industrial Area",
        "city": "Patna",
        "state": "Bihar",
        "country": "India",
        "pin_code": "800001",
    }
    payload.update(overrides)
    return payload


def test_facility_profile_normalises_unique_code_and_required_address():
    profile = FacilityProfileCreate.model_validate(valid_profile())
    assert profile.facility_code == "PAT-WAREHOUSE-01"
    assert profile.pin_code == "800001"


@pytest.mark.parametrize("pin", ["80001", "8000012", "ABC001", ""])
def test_facility_profile_rejects_invalid_indian_pin(pin):
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(pin_code=pin))


def test_facility_profile_rejects_non_positive_capacity():
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(capacity=0))


def test_facility_profile_rejects_invalid_operating_days():
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(operating_days=["mon", "MON"]))
