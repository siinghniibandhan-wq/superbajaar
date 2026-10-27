from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_catalogue_requires_database_configuration(monkeypatch):
    from app.api.v1 import catalogue

    monkeypatch.setattr(catalogue.settings, "database_url", "")
    response = client.get("/api/v1/catalogue/categories")
    assert response.status_code == 503
    assert response.json()["detail"] == "Catalogue database is not configured"


def test_category_rejects_invalid_slug_before_database_access():
    response = client.post("/api/v1/catalogue/categories", json={"name": "Drinks", "slug": "Not A Valid Slug"})
    assert response.status_code == 422


def test_product_rejects_out_of_range_tax_rate():
    response = client.post("/api/v1/catalogue/products", json={"name": "Juice", "slug": "juice", "tax_rate": 150})
    assert response.status_code == 422


def test_blank_category_name_rejected_before_database_access():
    response = client.post("/api/v1/catalogue/categories", json={"name": "   ", "slug": "drinks"})
    assert response.status_code == 422


def test_attribute_requires_options_for_select():
    response = client.post("/api/v1/catalogue/attributes", json={
        "name": "Size", "code": "size", "value_type": "size", "is_variant_attribute": True,
    })
    assert response.status_code == 422


def test_variant_requires_nonnegative_price_and_valid_mrp():
    response = client.post("/api/v1/catalogue/products/1/variants", json={
        "sku": "SKU-1", "selling_price": 100, "mrp": 90,
    })
    assert response.status_code == 422


def test_product_image_rejects_non_http_url_before_database_access():
    response = client.post("/api/v1/catalogue/products/1/images", json={
        "image_url": "javascript:alert(1)",
    })
    assert response.status_code == 422


def test_product_image_rejects_invalid_sort_order_before_database_access():
    response = client.post("/api/v1/catalogue/products/1/images", json={
        "image_url": "https://example.com/product.jpg", "sort_order": -1,
    })
    assert response.status_code == 422
