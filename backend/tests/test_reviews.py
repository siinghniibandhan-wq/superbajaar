import pytest
from fastapi import HTTPException

from app.api import reviews
from app.core.auth_middleware import _action_for_request, _module_for_path


class _State:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Req:
    def __init__(self, **kw):
        self.state = _State(**kw)


def test_public_name_is_masked():
    assert reviews._public_name("Ravi Kumar Singh") == "Ravi S."
    assert reviews._public_name("Asha") == "Asha"
    assert reviews._public_name("") == "Customer"


def test_customer_required_to_review():
    with pytest.raises(HTTPException) as err:
        reviews._customer(_Req(role="admin"))
    assert err.value.status_code == 401
    assert reviews._customer(_Req(role="customer", customer_id=7, customer_email=" A@B.com ")) == (7, "a@b.com")


def test_staff_required_for_moderation():
    with pytest.raises(HTTPException) as err:
        reviews._staff(_Req(role="customer"))
    assert err.value.status_code == 403
    assert reviews._staff(_Req(role="admin", user_email="x@y.z")) == "x@y.z"


def test_staff_moderation_uses_catalogue_permissions():
    assert _module_for_path("/api/reviews/admin") == "catalogue"
    assert _action_for_request("GET", "/api/reviews/admin") == "read"
    assert _action_for_request("POST", "/api/reviews/admin/5/approve") == "approve"


def test_rating_must_be_1_to_5():
    with pytest.raises(Exception):
        reviews.ReviewCreate(product_id=1, rating=6)
    with pytest.raises(Exception):
        reviews.ReviewCreate(product_id=1, rating=0)
    assert reviews.ReviewCreate(product_id=1, rating=5).rating == 5
