import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.auth import PasswordChange
from app.api.v1.users import UserCreate, UserPasswordReset, UserUpdate, _require_owner


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


def test_password_change_requires_minimum_length():
    with pytest.raises(ValidationError):
        PasswordChange(current_password="old", new_password="short")
    with pytest.raises(ValidationError):
        UserPasswordReset(password="short")
    payload = PasswordChange(current_password="old-password", new_password="a-strong-new-password")
    assert payload.new_password == "a-strong-new-password"
