


def test_cost_layer_allocation_applies_configured_minimum_remaining_shelf_life():
    from decimal import Decimal
    from app.services.inventory_costing import allocate_cost_layers

    class Result:
        def fetchall(self):
            return [{"id": 1, "remaining_quantity": Decimal("5"), "unit_cost": Decimal("2")}]

    class Connection:
        def __init__(self):
            self.statements = []
        def execute(self, sql, params=()):
            self.statements.append((sql, params))
            return Result()

    conn = Connection()
    result = allocate_cost_layers(
        conn, movement_id=10, variant_id=2, location_id=3,
        quantity=Decimal("1"), method="fefo",
        minimum_remaining_shelf_life_days=14,
    )
    select_sql, select_params = next((sql, params) for sql, params in conn.statements if sql.startswith("SELECT id,remaining_quantity,unit_cost"))
    assert "CURRENT_DATE + (%s * INTERVAL '1 day')" in select_sql
    assert select_params == (2, 3, 14)
    assert result["quantity"] == Decimal("1")


def test_cost_layer_allocation_rejects_negative_shelf_life_days():
    from decimal import Decimal
    import pytest
    from fastapi import HTTPException
    from app.services.inventory_costing import allocate_cost_layers

    with pytest.raises(HTTPException) as error:
        allocate_cost_layers(
            object(), movement_id=10, variant_id=2, location_id=3,
            quantity=Decimal("1"), minimum_remaining_shelf_life_days=-1,
        )
    assert error.value.status_code == 422


def test_inventory_approval_payload_hash_is_stable_across_json_and_decimal_models():
    from app.api.inventory import _inventory_payload_hash
    request_payload = {
        "variant_id": 7, "location_id": 3, "quantity": 1.0,
        "unit_cost": 12.5000, "note": "opening stock",
    }
    validated_payload = {
        "variant_id": 7, "location_id": 3, "quantity": "1.000",
        "unit_cost": "12.5000", "note": "opening stock",
    }
    assert _inventory_payload_hash(request_payload) == _inventory_payload_hash(validated_payload)


def test_inventory_approval_payload_hash_distinguishes_business_payload_changes():
    from app.api.inventory import _inventory_payload_hash
    original = {"variant_id": 7, "location_id": 3, "quantity": "1.000", "note": "approved"}
    changed = {**original, "quantity": "2.000"}
    assert _inventory_payload_hash(original) != _inventory_payload_hash(changed)


def test_inventory_quantity_threshold_requires_approval_before_stock_issue(monkeypatch):
    import pytest
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.api import inventory

    class Result:
        def __init__(self, row=None):
            self.row = row
        def fetchone(self):
            return self.row

    class Connection:
        def execute(self, sql, params=()):
            if "SELECT establishment_id FROM stock_locations" in sql:
                return Result({"establishment_id": 9})
            if "SELECT id,created_by_user_id FROM inventory_event_approval_requests" in sql:
                return Result(None)
            raise AssertionError(f"Unexpected query: {sql}")

    monkeypatch.setattr(inventory, "load_active_policy", lambda *args: {
        "id": 77,
        "policy_config": {
            "event_policies": {
                "issue": {
                    "approval_required": False,
                    "approval_thresholds": {"quantity": "5"},
                    "stages": [{"sequence": 1, "approver_roles": ["manager"]}],
                }
            },
            "shelf_life": {"default_minimum_remaining_days": None},
        },
    })
    request = SimpleNamespace(state=SimpleNamespace(user_id=123))
    payload = inventory.StockIssue(
        variant_id=3, location_id=4, quantity="6",
        note="threshold test", reason_type="issue", allocation_method="fifo",
    )

    with pytest.raises(HTTPException) as error:
        inventory._require_inventory_event_policy(
            Connection(), 4, "issue", payload=payload, request=request,
        )

    assert error.value.status_code == 409
    assert "approval" in error.value.detail.lower()
