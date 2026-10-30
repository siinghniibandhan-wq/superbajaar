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


def test_attribute_rejects_legacy_number_type():
    response = client.post("/api/catalogue/attributes", json={"name": "Weight", "code": "weight", "value_type": "number"})
    assert response.status_code == 422


def test_attribute_accepts_three_value_types_and_display_type():
    from app.api.catalogue import AttributeCreate
    display_types = {"text": "button", "colour": "colour", "image": "image"}
    for value_type, display_type in display_types.items():
        payload = AttributeCreate(name="Example", code="example", value_type=value_type, display_type=display_type, options=["one"] if value_type in {"colour", "image"} else [])
        assert payload.value_type == value_type
        assert payload.display_type == display_type


def test_attribute_rejects_invalid_display_type():
    from pydantic import ValidationError
    from app.api.catalogue import AttributeCreate
    try:
        AttributeCreate(name="Size", code="size", value_type="text", display_type="radio")
        assert False, "Expected a validation error"
    except ValidationError:
        pass


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

def test_shared_attribute_options_append_and_deduplicate_values():
    from app.api.catalogue import _merge_attribute_options

    assert _merge_attribute_options(
        ["Red", "Yellow"],
        [" Pink ", "red", "", "PINK", "Blue"],
    ) == ["Red", "Yellow", "Pink", "Blue"]


def test_shared_attribute_options_reject_non_scalar_values():
    from fastapi import HTTPException
    from app.api.catalogue import _merge_attribute_options

    try:
        _merge_attribute_options(["Red"], [{"name": "Pink"}])
        assert False, "Expected invalid option to be rejected"
    except HTTPException as exc:
        assert exc.status_code == 422


def test_shared_attribute_options_rejects_an_empty_initial_list():
    from fastapi import HTTPException
    from app.api.catalogue import _merge_attribute_options

    try:
        _merge_attribute_options([], [" ", ""])
        assert False, "Expected an empty option list to be rejected"
    except HTTPException as exc:
        assert exc.status_code == 422



def test_attribute_update_trims_name_and_accepts_metadata_fields():
    from app.api.catalogue import AttributeUpdate

    payload = AttributeUpdate(name="  Colour  ", is_required=False, is_variant_attribute=True)
    assert payload.name == "Colour"
    assert payload.is_required is False
    assert payload.is_variant_attribute is True


def test_attribute_update_rejects_blank_name():
    from pydantic import ValidationError
    from app.api.catalogue import AttributeUpdate

    try:
        AttributeUpdate(name="   ")
        assert False, "Expected a validation error"
    except ValidationError:
        pass


def test_attribute_update_rejects_unsupported_value_type():
    from pydantic import ValidationError
    from app.api.catalogue import AttributeUpdate

    try:
        AttributeUpdate(value_type="currency")
        assert False, "Expected a validation error"
    except ValidationError:
        pass


def test_attribute_update_route_rejects_invalid_payload_before_database_access():
    response = client.put("/api/catalogue/attributes/1", json={"name": "   "})
    assert response.status_code == 422


def test_attribute_option_removal_requires_a_value():
    response = client.request("DELETE", "/api/catalogue/attributes/1/options", json={})
    assert response.status_code == 422



def test_attribute_rejects_incompatible_display_type():
    from pydantic import ValidationError
    from app.api.catalogue import AttributeCreate
    try:
        AttributeCreate(name="Colour", code="colour", value_type="colour", display_type="image", options=["Red"])
        assert False, "Expected a validation error"
    except ValidationError:
        pass
