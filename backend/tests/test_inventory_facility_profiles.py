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


@pytest.mark.parametrize("pin", ["80001", "8000012", "ABC001", "", "000001"])
def test_facility_profile_rejects_invalid_indian_pin(pin):
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(pin_code=pin))


def test_facility_profile_rejects_non_positive_capacity():
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(capacity=0))


def test_facility_profile_rejects_invalid_operating_days():
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(operating_days=["mon", "MON"]))



def test_facility_profile_defaults_to_legacy_primary_pin_routing_configuration():
    profile = FacilityProfileCreate.model_validate(valid_profile())
    assert profile.service_pin_codes == []
    assert profile.routing_priority == 100
    assert profile.storefront_available is True
    assert profile.is_fulfillable is None


def test_facility_profile_accepts_multiple_unique_service_pins():
    profile = FacilityProfileCreate.model_validate(valid_profile(service_pin_codes=["800001", "800002"]))
    assert profile.service_pin_codes == ["800001", "800002"]


@pytest.mark.parametrize("pins", [["800001", "800001"], ["80001"], ["ABC001"]])
def test_facility_profile_rejects_duplicate_or_invalid_service_pins(pins):
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(service_pin_codes=pins))


def test_facility_profile_rejects_opening_time_after_closing_time():
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(opening_time="21:00", closing_time="09:00"))


def test_facility_profile_requires_both_operating_times():
    with pytest.raises(ValidationError):
        FacilityProfileCreate.model_validate(valid_profile(opening_time="09:00"))
