import pytest
from fastapi import HTTPException

from app.api.inventory_locations import validate_internal_location_parent


def test_internal_location_parent_must_belong_to_selected_facility():
    with pytest.raises(HTTPException) as error:
        validate_internal_location_parent(
            facility_id=10,
            parent={"id": 3, "facility_id": 11},
        )
    assert error.value.status_code == 422


def test_internal_location_allows_root_location_without_parent():
    assert validate_internal_location_parent(facility_id=10, parent=None) is None


def test_internal_location_parent_cannot_be_itself():
    with pytest.raises(HTTPException) as error:
        validate_internal_location_parent(
            facility_id=10,
            parent={"id": 5, "facility_id": 10},
            location_id=5,
        )
    assert error.value.status_code == 422
