import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.users import UserCreate, UserUpdate, _require_owner


def test_user_creation_normalizes_email_and_name():
    payload = UserCreate(
        email="  STORE@example.com ",
        full_name="  Store Operator ",
        password="secure-temporary-pass",
        role="staff",
    )
    assert payload.email == "store@example.com"
    assert payload.full_name == "Store Operator"


def test_user_creation_requires_long_password_and_valid_role():
    with pytest.raises(ValidationError):
        UserCreate(email="store@example.com", full_name="Operator", password="short", role="staff")
    with pytest.raises(ValidationError):
        UserCreate(email="store@example.com", full_name="Operator", password="secure-temporary-pass", role="root")


def test_user_update_rejects_blank_name():
    with pytest.raises(ValidationError):
        UserUpdate(full_name="   ")


def test_only_owner_can_manage_accounts():
    _require_owner({"role": "owner"})
    with pytest.raises(HTTPException) as exc:
        _require_owner({"role": "admin"})
    assert exc.value.status_code == 403
