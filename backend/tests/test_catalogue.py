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
    response = client.post(
        "/api/v1/catalogue/categories",
        json={"name": "Drinks", "slug": "Not A Valid Slug"},
    )
    assert response.status_code == 422


def test_product_rejects_out_of_range_tax_rate():
    response = client.post(
        "/api/v1/catalogue/products",
        json={"name": "Juice", "slug": "juice", "tax_rate": 150},
    )
    assert response.status_code == 422
