from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_catalogue_requires_database_configuration(monkeypatch):
    from app.api import catalogue

    monkeypatch.setattr(catalogue.settings, "database_url", "")
    response = client.get("/api/catalogue/categories")
    assert response.status_code == 503
    assert response.json()["detail"] == "Catalogue database is not configured"


def test_category_rejects_invalid_slug_before_database_access():
    response = client.post("/api/catalogue/categories", json={"name": "Drinks", "slug": "Not A Valid Slug"})
    assert response.status_code == 422


def test_category_update_rejects_invalid_slug_before_database_access():
    response = client.put("/api/catalogue/categories/1", json={"name": "Drinks", "slug": "Not A Valid Slug"})
    assert response.status_code == 422


def test_product_rejects_out_of_range_tax_rate():
    response = client.post("/api/catalogue/products", json={"name": "Juice", "slug": "juice", "tax_rate": 150})
    assert response.status_code == 422


def test_blank_category_name_rejected_before_database_access():
    response = client.post("/api/catalogue/categories", json={"name": "   ", "slug": "drinks"})
    assert response.status_code == 422


def test_attribute_requires_options_for_select():
    response = client.post("/api/catalogue/attributes", json={
        "name": "Size", "code": "size", "value_type": "size", "is_variant_attribute": True,
    })
    assert response.status_code == 422


def test_variant_requires_nonnegative_price_and_valid_mrp():
    response = client.post("/api/catalogue/products/1/variants", json={
        "sku": "SKU-1", "selling_price": 100, "mrp": 90,
    })
    assert response.status_code == 422


def test_product_image_rejects_non_http_url_before_database_access():
    response = client.post("/api/catalogue/products/1/images", json={
        "image_url": "javascript:alert(1)",
    })
    assert response.status_code == 422


def test_product_image_rejects_invalid_sort_order_before_database_access():
    response = client.post("/api/catalogue/products/1/images", json={
        "image_url": "https://example.com/product.jpg", "sort_order": -1,
    })
    assert response.status_code == 422


def test_variant_price_update_rejects_mrp_below_selling_price():
    response = client.put("/api/catalogue/variants/1/price", json={
        "selling_price": 100, "mrp": 99, "cost_price": 50,
    })
    assert response.status_code == 422


def test_variant_price_update_rejects_negative_cost_price():
    response = client.put("/api/catalogue/variants/1/price", json={
        "selling_price": 50, "mrp": 50, "cost_price": -1,
    })
    assert response.status_code == 422


def test_product_accepts_multiple_category_ids():
    from app.api.catalogue import ProductCreate

    payload = ProductCreate(name="Juice", slug="juice", category_ids=[1, 2, 3])
    assert payload.category_ids == [1, 2, 3]


def test_product_rejects_nonpositive_category_ids_before_database_access():
    response = client.post("/api/catalogue/products", json={
        "name": "Juice", "slug": "juice", "category_ids": [0, 2],
    })
    assert response.status_code == 422


def test_product_status_defaults_to_active():
    from app.api.catalogue import ProductCreate

    payload = ProductCreate(name="Juice", slug="juice")
    assert payload.status == "active"


def test_product_rejects_unsupported_status_before_database_access():
    response = client.post("/api/catalogue/products", json={
        "name": "Juice", "slug": "juice", "status": "published",
    })
    assert response.status_code == 422


def test_archived_product_status_is_valid_for_product_updates():
    from app.api.catalogue import ProductUpdate

    payload = ProductUpdate(name="Juice", slug="juice", status="archived")
    assert payload.status == "archived"


def test_category_accepts_parent_id_for_subcategory():
    from app.api.catalogue import CategoryCreate

    payload = CategoryCreate(name="Tea", slug="tea", parent_id=10)
    assert payload.parent_id == 10



def test_variant_sku_is_optional_for_server_generation():
    from app.api.catalogue import VariantCreate

    payload = VariantCreate(selling_price=199, attributes={"colour": "Black", "size": "L"})
    assert payload.sku is None


def test_blank_variant_sku_uses_server_generation():
    from app.api.catalogue import VariantCreate

    payload = VariantCreate(sku="   ", selling_price=199)
    assert payload.sku is None


def test_category_sku_codes_match_superbajaar_categories():
    from app.api.catalogue import _category_sku_code

    assert _category_sku_code("Fashion") == "FS"
    assert _category_sku_code("Grocery") == "GR"
    assert _category_sku_code("Personal Care") == "PC"


def test_product_delete_reason_is_required_and_trimmed():
    from app.api.catalogue import ProductDeleteRequest

    payload = ProductDeleteRequest(reason="  Incorrect test product created during catalogue validation  ")
    assert payload.reason == "Incorrect test product created during catalogue validation"


def test_product_delete_rejects_blank_or_short_reason():
    from pydantic import ValidationError
    from app.api.catalogue import ProductDeleteRequest

    for reason in ("", "   ", "wrong"):
        try:
            ProductDeleteRequest(reason=reason)
            assert False, "Expected a validation error"
        except ValidationError:
            pass



def test_required_variant_attribute_rejects_missing_value():
    from fastapi import HTTPException
    from app.api.catalogue import _validate_required_variant_attributes

    definitions = [
        {"code": "size", "name": "Size", "is_required": True},
        {"code": "colour", "name": "Colour", "is_required": False},
    ]
    try:
        _validate_required_variant_attributes(definitions, {"colour": "Blue"})
        assert False, "Expected required attribute validation to fail"
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "Size" in exc.detail


def test_required_variant_attribute_accepts_false_boolean():
    from app.api.catalogue import _validate_required_variant_attributes

    definitions = [{"code": "is_refillable", "name": "Refillable", "is_required": True}]
    _validate_required_variant_attributes(definitions, {"is_refillable": False})


def test_required_variant_attribute_rejects_blank_text_and_empty_multi_select():
    from fastapi import HTTPException
    from app.api.catalogue import _validate_required_variant_attributes

    definitions = [
        {"code": "material", "name": "Material", "is_required": True},
        {"code": "features", "name": "Features", "is_required": True},
    ]
    for values in ({"material": "   ", "features": ["Eco"]}, {"material": "Cotton", "features": []}):
        try:
            _validate_required_variant_attributes(definitions, values)
            assert False, "Expected required attribute validation to fail"
        except HTTPException as exc:
            assert exc.status_code == 422


def test_attribute_date_validation_rejects_impossible_dates():
    from fastapi import HTTPException
    from app.api.catalogue import _validate_attribute_value

    attribute = {"name": "Manufacture date", "value_type": "date", "options": []}
    _validate_attribute_value(None, attribute, "2026-10-30")
    for value in ("2026-02-30", "2026-2-03", "not-a-date"):
        try:
            _validate_attribute_value(None, attribute, value)
            assert False, f"Expected invalid date to be rejected: {value}"
        except HTTPException as exc:
            assert exc.status_code == 422


def test_attribute_number_validation_rejects_non_finite_values():
    from fastapi import HTTPException
    from app.api.catalogue import _validate_attribute_value

    attribute = {"name": "Weight", "value_type": "number", "options": []}
    _validate_attribute_value(None, attribute, 1.25)
    for value in (float("nan"), float("inf"), float("-inf"), True):
        try:
            _validate_attribute_value(None, attribute, value)
            assert False, f"Expected invalid number to be rejected: {value}"
        except HTTPException as exc:
            assert exc.status_code == 422
