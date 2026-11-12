from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_purchasing_requires_database_configuration(monkeypatch):
    from app.api import purchasing

    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.get("/api/purchasing/suppliers")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_supplier_rejects_blank_name_before_database_access():
    response = client.post("/api/purchasing/suppliers", json={"name": "   "})
    assert response.status_code == 422


def test_supplier_rejects_invalid_gstin_shape_before_database_access():
    response = client.post("/api/purchasing/suppliers", json={"name": "Test supplier", "gstin": "INVALID"})
    assert response.status_code == 422


def test_purchase_order_requires_at_least_one_line():
    response = client.post("/api/purchasing/orders", json={
        "supplier_id": 1, "location_id": 1, "lines": [],
    })
    assert response.status_code == 422


def test_purchase_order_rejects_duplicate_variant_lines():
    response = client.post("/api/purchasing/orders", json={
        "supplier_id": 1, "location_id": 1,
        "lines": [
            {"variant_id": 1, "quantity": 2, "unit_cost": 10},
            {"variant_id": 1, "quantity": 3, "unit_cost": 11},
        ],
    })
    assert response.status_code == 422


def test_goods_receipt_requires_lines():
    response = client.post("/api/purchasing/orders/1/receive", json={"lines": []})
    assert response.status_code == 422


def test_purchase_order_cancel_requires_database_configuration(monkeypatch):
    from app.api import purchasing

    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.post("/api/purchasing/orders/1/cancel")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_purchase_order_cancel_rejects_non_integer_id():
    response = client.post("/api/purchasing/orders/not-a-number/cancel")
    assert response.status_code == 422


def test_purchase_order_approval_requires_authenticated_actor_before_database_access():
    response = client.post("/api/purchasing/orders/1/approve")
    assert response.status_code == 401
    assert response.json()["detail"] == "A valid staff session is required"


def test_purchase_order_approval_rejects_non_integer_id():
    response = client.post("/api/purchasing/orders/not-a-number/approve")
    assert response.status_code == 422


def test_purchasing_storage_error_does_not_reference_missing_migration_006():
    from app.api import purchasing

    response = purchasing._db_error(Exception())
    assert response.status_code == 503
    assert "migration 006" not in response.detail
    assert "purchasing, catalogue and inventory schema" in response.detail



def test_supplier_update_requires_database_configuration(monkeypatch):
    from app.api import purchasing

    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.put("/api/purchasing/suppliers/1", json={"name": "Updated supplier"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_supplier_update_rejects_invalid_gstin_before_database_access():
    response = client.put("/api/purchasing/suppliers/1", json={
        "name": "Updated supplier", "gstin": "INVALID",
    })
    assert response.status_code == 422


def test_supplier_update_rejects_non_integer_id():
    response = client.put("/api/purchasing/suppliers/not-a-number", json={"name": "Updated supplier"})
    assert response.status_code == 422


def test_draft_purchase_order_update_requires_authenticated_actor_before_database_access():
    response = client.put("/api/purchasing/orders/1", json={
        "supplier_id": 1, "location_id": 1,
        "lines": [{"variant_id": 1, "quantity": 2, "unit_cost": 10}],
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "A valid staff session is required"


def test_draft_purchase_order_update_rejects_empty_lines():
    response = client.put("/api/purchasing/orders/1", json={
        "supplier_id": 1, "location_id": 1, "lines": [],
    })
    assert response.status_code == 422


def test_draft_purchase_order_update_rejects_duplicate_variant_lines():
    response = client.put("/api/purchasing/orders/1", json={
        "supplier_id": 1, "location_id": 1,
        "lines": [
            {"variant_id": 1, "quantity": 2, "unit_cost": 10},
            {"variant_id": 1, "quantity": 3, "unit_cost": 11},
        ],
    })
    assert response.status_code == 422


def test_goods_receipt_rejects_invalid_idempotency_key():
    response = client.post("/api/purchasing/orders/1/receive", json={
        "idempotency_key": "not-a-uuid",
        "lines": [{"line_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422


def test_goods_receipt_accepts_uuid_and_requires_database_configuration(monkeypatch):
    from app.api import purchasing

    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.post("/api/purchasing/orders/1/receive", json={
        "idempotency_key": "00000000-0000-4000-8000-000000000001",
        "lines": [{"line_id": 1, "quantity": 1}],
    })
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_purchase_order_receipt_history_requires_database_configuration(monkeypatch):
    from app.api import purchasing

    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.get("/api/purchasing/orders/1/receipts")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_purchase_order_receipt_history_rejects_non_integer_id():
    response = client.get("/api/purchasing/orders/not-a-number/receipts")
    assert response.status_code == 422


def test_requisition_requires_database_configuration(monkeypatch):
    from app.api import purchasing
    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.get("/api/purchasing/requisitions")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_requisition_rejects_empty_lines():
    response = client.post("/api/purchasing/requisitions", json={
        "location_id": 1, "justification": "Restock",
        "lines": [],
    })
    assert response.status_code == 422


def test_requisition_rejects_duplicate_variant_lines():
    response = client.post("/api/purchasing/requisitions", json={
        "location_id": 1, "justification": "Restock",
        "lines": [
            {"variant_id": 1, "quantity": 2},
            {"variant_id": 1, "quantity": 3},
        ],
    })
    assert response.status_code == 422


def test_requisition_rejects_blank_justification():
    response = client.post("/api/purchasing/requisitions", json={
        "location_id": 1, "justification": "  ",
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422


def test_requisition_decision_rejects_unknown_decision():
    from fastapi import HTTPException
    from app.api.purchasing_lifecycle import DecisionInput, _validate_decision
    import pytest
    with pytest.raises(HTTPException) as error:
        _validate_decision("maybe", DecisionInput())
    assert error.value.status_code == 422


def test_requisition_rejection_requires_reason():
    from fastapi import HTTPException
    from app.api.purchasing_lifecycle import DecisionInput, _validate_decision
    import pytest
    with pytest.raises(HTTPException) as error:
        _validate_decision("reject", DecisionInput())
    assert error.value.status_code == 422


def test_requisition_requires_database_configuration(monkeypatch):
    from app.api import purchasing
    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.get("/api/purchasing/requisitions")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_requisition_rejects_empty_lines():
    response = client.post("/api/purchasing/requisitions", json={
        "location_id": 1, "justification": "Restock",
        "lines": [],
    })
    assert response.status_code == 422


def test_requisition_rejects_duplicate_variant_lines():
    response = client.post("/api/purchasing/requisitions", json={
        "location_id": 1, "justification": "Restock",
        "lines": [
            {"variant_id": 1, "quantity": 2},
            {"variant_id": 1, "quantity": 3},
        ],
    })
    assert response.status_code == 422


def test_requisition_rejects_blank_justification():
    response = client.post("/api/purchasing/requisitions", json={
        "location_id": 1, "justification": "  ",
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422


def test_rfq_rejects_duplicate_supplier_ids():
    from app.api.purchasing_lifecycle import RFQCreate
    import pytest
    with pytest.raises(ValueError):
        RFQCreate(requisition_id=1, supplier_ids=[2, 2])


def test_rfq_requires_at_least_one_supplier():
    response = client.post("/api/purchasing/rfqs", json={
        "requisition_id": 1, "supplier_ids": [],
    })
    assert response.status_code == 422


def test_quotation_rejects_duplicate_variant_lines():
    from app.api.purchasing_lifecycle import QuotationCreate
    import pytest
    with pytest.raises(ValueError):
        QuotationCreate(
            rfq_id=1, supplier_id=1, quotation_number="Q-1",
            lines=[
                {"variant_id": 1, "quantity": 1, "unit_price": 10},
                {"variant_id": 1, "quantity": 1, "unit_price": 9},
            ],
        )


def test_quotation_requires_at_least_one_line():
    response = client.post("/api/purchasing/quotations", json={
        "rfq_id": 1, "supplier_id": 1, "quotation_number": "Q-1",
        "lines": [],
    })
    assert response.status_code == 422


def test_grn_rejects_duplicate_purchase_lines():
    from app.api.purchasing_lifecycle import GRNCreate
    import uuid
    import pytest
    with pytest.raises(ValueError):
        GRNCreate(
            idempotency_key=uuid.uuid4(),
            lines=[
                {"line_id": 1, "quantity": 2},
                {"line_id": 1, "quantity": 1},
            ],
        )


def test_grn_requires_at_least_one_line():
    response = client.post("/api/purchasing/orders/1/grns", json={
        "idempotency_key": "00000000-0000-4000-8000-000000000002",
        "lines": [],
    })
    assert response.status_code == 422


def test_qc_rejects_unsupported_disposition():
    from app.api.purchasing_lifecycle import QCLineInput
    import pytest
    with pytest.raises(ValueError):
        QCLineInput(goods_receipt_line_id=1, disposition="released_to_stock", quantity=1)


def test_qc_requires_at_least_one_line():
    response = client.post("/api/purchasing/grns/1/qc", json={
        "idempotency_key": "00000000-0000-4000-8000-000000000003",
        "lines": [],
    })
    assert response.status_code == 422


def test_qc_payload_hash_is_order_independent():
    from app.api.purchasing_lifecycle import _payload_hash
    assert _payload_hash({"a": 1, "b": 2}) == _payload_hash({"b": 2, "a": 1})


def test_supplier_invoice_total_must_reconcile_to_gst_components():
    from app.api.purchasing_lifecycle import SupplierInvoiceCreate
    import pytest
    with pytest.raises(ValueError):
        SupplierInvoiceCreate(
            purchase_order_id=1, invoice_number="INV-1", invoice_date="2026-11-01",
            taxable_value=100, cgst_amount=9, sgst_amount=9, invoice_total=120,
            lines=[{
                "purchase_order_line_id": 1, "goods_receipt_line_id": 1,
                "quantity": 1, "unit_rate": 100, "taxable_value": 100,
            }],
        )


def test_supplier_invoice_requires_grn_link_for_three_way_match():
    from app.api.purchasing_lifecycle import SupplierInvoiceLineInput
    import pytest
    with pytest.raises(ValueError):
        SupplierInvoiceLineInput(
            purchase_order_line_id=1, quantity=1, unit_rate=100,
            taxable_value=100,
        )


def test_supplier_invoice_rejects_duplicate_po_lines():
    from app.api.purchasing_lifecycle import SupplierInvoiceCreate
    import pytest
    with pytest.raises(ValueError):
        SupplierInvoiceCreate(
            purchase_order_id=1, invoice_number="INV-2", invoice_date="2026-11-01",
            taxable_value=200, invoice_total=200,
            lines=[
                {"purchase_order_line_id": 1, "goods_receipt_line_id": 1, "quantity": 1, "unit_rate": 100, "taxable_value": 100},
                {"purchase_order_line_id": 1, "goods_receipt_line_id": 2, "quantity": 1, "unit_rate": 100, "taxable_value": 100},
            ],
        )


def test_payment_allocation_must_be_positive():
    from app.api.purchasing_lifecycle import PaymentAllocationInput
    import pytest
    with pytest.raises(ValueError):
        PaymentAllocationInput(accounting_voucher_id=1, allocated_amount=0)


def test_supplier_return_requires_unique_grn_lines():
    from app.api.purchasing_lifecycle import SupplierReturnCreate
    import pytest
    with pytest.raises(ValueError):
        SupplierReturnCreate(
            goods_receipt_id=1, reason="Damaged goods",
            lines=[
                {"goods_receipt_line_id": 1, "quantity": 1},
                {"goods_receipt_line_id": 1, "quantity": 2},
            ],
        )


def test_supplier_return_requires_reason_and_lines():
    response = client.post("/api/purchasing/supplier-returns", json={
        "goods_receipt_id": 1, "reason": " ", "lines": [],
    })
    assert response.status_code == 422


def test_supplier_return_credit_rejects_blank_debit_note_number():
    from app.api.purchasing_lifecycle import SupplierReturnCredit
    import pytest
    with pytest.raises(ValueError):
        SupplierReturnCredit(
            debit_note_number="   ", debit_note_date="2026-11-02",
            accounting_voucher_id=1,
        )


def test_supplier_payment_allocation_locks_voucher_to_prevent_overallocation(monkeypatch):
    from decimal import Decimal
    from types import SimpleNamespace
    from fastapi import Request
    from app.api import purchasing_lifecycle as lifecycle

    statements = []

    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def transaction(self):
            from contextlib import nullcontext
            return nullcontext()

        def execute(self, sql, params=()):
            statements.append(sql)
            if "FROM supplier_invoices i JOIN suppliers" in sql:
                return Result({"id": 1, "supplier_id": 2, "invoice_total": Decimal("100.00"),
                               "match_status": "approved", "supplier_name": "Supplier A"})
            if "FROM accounting_vouchers WHERE id=%s" in sql:
                return Result({"id": 3, "voucher_type": "payment", "status": "posted",
                               "party_type": "supplier", "party_name": "Supplier A",
                               "total_amount": Decimal("100.00")})
            if "FROM supplier_payment_allocations WHERE supplier_invoice_id" in sql:
                return Result({"amount": Decimal("0.00")})
            if "FROM supplier_payment_allocations WHERE accounting_voucher_id" in sql:
                return Result({"amount": Decimal("0.00")})
            if "INSERT INTO supplier_payment_allocations" in sql:
                return Result({"id": 9, "allocated_amount": Decimal("100.00")})
            raise AssertionError(f"Unexpected SQL: {sql}")

    monkeypatch.setattr(lifecycle, "_connect", Connection)
    monkeypatch.setattr(lifecycle, "_actor", lambda request: (7, "admin@example.test", "admin"))
    request = Request({"type": "http", "http_version": "1.1", "method": "POST",
                       "scheme": "http", "path": "/api/purchasing/supplier-invoices/1/payment-allocations",
                       "raw_path": b"/api/purchasing/supplier-invoices/1/payment-allocations",
                       "query_string": b"", "headers": [], "server": ("test", 80),
                       "client": ("test", 1234), "state": {}})
    payload = lifecycle.PaymentAllocationInput(accounting_voucher_id=3, allocated_amount=Decimal("100.00"))

    lifecycle.allocate_supplier_payment(1, payload, request)

    voucher_query = next(sql for sql in statements if "FROM accounting_vouchers WHERE id=%s" in sql)
    assert "FOR UPDATE" in voucher_query.upper()


def test_supplier_return_dispatch_can_consume_original_grn_batch_after_transfer(monkeypatch):
    from decimal import Decimal
    from app.api import purchasing_lifecycle as lifecycle

    class Result:
        def __init__(self, rows=None, row=None):
            self.rows = rows or []
            self.row = row

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.calls = []
            self.next_movement = 500

        def execute(self, sql, params=()):
            self.calls.append((sql, params))
            if "SELECT DISTINCT cl.location_id FROM inventory_cost_layers cl" in sql:
                return Result(rows=[{"location_id": 1}, {"location_id": 2}])
            if "SELECT location_id,on_hand,reserved FROM inventory_balances" in sql:
                return Result(rows=[
                    {"location_id": 1, "on_hand": Decimal("1"), "reserved": Decimal("0")},
                    {"location_id": 2, "on_hand": Decimal("3"), "reserved": Decimal("1")},
                ])
            if "SELECT id,location_id,remaining_quantity,unit_cost FROM inventory_cost_layers" in sql:
                return Result(rows=[
                    {"id": 11, "location_id": 1, "remaining_quantity": Decimal("2"), "unit_cost": Decimal("5")},
                    {"id": 12, "location_id": 2, "remaining_quantity": Decimal("2"), "unit_cost": Decimal("5")},
                ])
            if "INSERT INTO inventory_movements" in sql:
                self.next_movement += 1
                return Result(row={"id": self.next_movement})
            return Result()

    conn = Connection()
    monkeypatch.setattr(lifecycle, "money", lambda value: value.quantize(Decimal("0.01")))
    result = lifecycle._dispatch_supplier_return_line(
        conn, return_id=8, return_number="SR-8", establishment_id=12,
        line={"goods_receipt_line_id": 77, "variant_id": 9, "quantity": Decimal("2")},
    )

    assert [(item["location_id"], item["quantity"]) for item in result] == [
        (1, Decimal("1")), (2, Decimal("1")),
    ]
    layer_query = next(sql for sql, _ in conn.calls if "SELECT id,location_id,remaining_quantity,unit_cost FROM inventory_cost_layers" in sql)
    assert "location_id=ANY(%s)" in layer_query


def test_rfq_award_endpoint_requires_staff_session_before_database_access():
    response = client.post("/api/purchasing/rfqs/1/award", json={"quotation_id": 1})
    assert response.status_code == 401
    assert response.json()["detail"] == "A valid staff session is required"


def test_supplier_return_dispatch_only_selects_batches_from_purchase_establishment():
    from decimal import Decimal
    import pytest
    from fastapi import HTTPException
    from app.api.purchasing_lifecycle import _dispatch_supplier_return_line

    class Result:
        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.calls = []
        def execute(self, sql, params=()):
            self.calls.append((sql, params))
            return Result()

    conn = Connection()
    with pytest.raises(HTTPException) as error:
        _dispatch_supplier_return_line(
            conn, return_id=5, return_number="SR-5", establishment_id=12,
            line={"goods_receipt_line_id": 44, "variant_id": 9, "quantity": Decimal("1")},
        )
    assert error.value.status_code == 409
    assert "sl.establishment_id=%s" in conn.calls[0][0]
    assert conn.calls[0][1] == (44, 12)


def test_supplier_creation_returns_the_generated_sbid(monkeypatch):
    from datetime import datetime, timezone
    from app.api import purchasing
    from app.services import identity

    class Result:
        def fetchone(self):
            return {
                "id": 41, "name": "Verified Supplier", "contact_name": None,
                "phone": None, "email": None, "gstin": None, "address": None,
                "is_active": True, "created_at": datetime.now(timezone.utc),
            }

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def transaction(self):
            from contextlib import nullcontext
            return nullcontext()

        def execute(self, query, params=()):
            assert "INSERT INTO suppliers" in query
            return Result()

    class FakeIdentityService:
        def __init__(self, conn):
            pass

        def create_party(self, **kwargs):
            return {"id": 900, "sbid": "SBID-0123456789ABCDEF0123"}

        def link_profile(self, **kwargs):
            return {"id": 1}

    monkeypatch.setattr(purchasing, "_connect", Connection)
    monkeypatch.setattr(identity, "IdentityService", FakeIdentityService)

    result = purchasing.create_supplier(purchasing.SupplierCreate(name="Verified Supplier"))

    assert result["id"] == 41
    assert result["sbid"] == "SBID-0123456789ABCDEF0123"


def test_supplier_update_preserves_and_returns_existing_sbid(monkeypatch):
    from app.api import purchasing

    class Result:
        def __init__(self, row):
            self.row = row
        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def transaction(self):
            from contextlib import nullcontext
            return nullcontext()
        def execute(self, sql, params=()):
            if "UPDATE suppliers SET" in sql:
                return Result({"id": 41, "name": "Updated Supplier", "email": None, "phone": None})
            if "FROM identity_profiles ip" in sql:
                return Result({"id": 900, "sbid": "SBID-0123456789ABCDEF0123"})
            if "UPDATE identity_parties SET display_name" in sql:
                return Result(None)
            raise AssertionError(f"Unexpected SQL: {sql}")

    monkeypatch.setattr(purchasing, "_connect", Connection)
    result = purchasing.update_supplier(41, purchasing.SupplierCreate(name="Updated Supplier"))
    assert result["sbid"] == "SBID-0123456789ABCDEF0123"
