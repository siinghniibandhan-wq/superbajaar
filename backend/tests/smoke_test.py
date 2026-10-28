"""Read-only integration smoke test for the canonical /api routes.

Set SB_SMOKE_BASE_URL, SB_ADMIN_EMAIL and SB_ADMIN_PASSWORD in the test environment.
This test deliberately avoids creating or modifying production records.
"""
import json
import os
import urllib.error
import urllib.request

BASE = os.getenv("SB_SMOKE_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
ADMIN_EMAIL = os.environ["SB_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["SB_ADMIN_PASSWORD"]


def request(method, path, payload=None, token=None, expected=200):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    if status != expected:
        raise AssertionError(
            f"{method} {path}: expected {expected}, got {status}: "
            f"{body.decode(errors='replace')}"
        )
    return json.loads(body) if body else {}


def main():
    assert request("GET", "/api/health") == {"status": "ok"}

    login = request(
        "POST",
        "/api/auth/login",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    token = login.get("token")
    assert token and login.get("user", {}).get("role") in {"admin", "owner"}, (
        "Admin login did not return an authenticated admin/owner session"
    )

    # Each path below is registered by the current backend route modules.
    paths = [
        "/api/auth/me",
        "/api/auth/users",
        "/api/catalogue/categories",
        "/api/catalogue/products?limit=5",
        "/api/catalogue/variants?limit=5",
        "/api/inventory/locations?limit=5",
        "/api/inventory/balances?limit=5",
        "/api/inventory/movements?limit=5",
        "/api/orders?limit=5",
        "/api/payments?limit=5",
        "/api/delivery/shipments?limit=5",
        "/api/customers?limit=5",
        "/api/customers/support-cases?limit=5",
        "/api/purchasing/suppliers?limit=5",
        "/api/purchasing/orders?limit=5",
    ]
    for path in paths:
        request("GET", path, token=token)
    print(f"Super Bajaar API smoke test passed: {len(paths) + 2} read-only checks.")


if __name__ == "__main__":
    main()
