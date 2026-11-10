"""Supplier-return invoice quantity controls against disposable PostgreSQL."""
import uuid

import psycopg
import pytest

from test_accounting_integration import TEST_DB, api


pytestmark = pytest.mark.skipif(not TEST_DB, reason="SB_TEST_DATABASE_URL is not set")


def _seed_approved_invoice(db_url):
    suffix = uuid.uuid4().hex[:12]
    with psycopg.connect(db_url) as conn:
        supplier_id = conn.execute(
            "INSERT INTO suppliers(name) VALUES(%s) RETURNING id",
            (f"Return supplier {suffix}",),
        ).fetchone()[0]
        location_id = conn.execute(
            "INSERT INTO stock_locations(name,location_type) VALUES(%s,'warehouse') RETURNING id",
            (f"Return warehouse {suffix}",),
        ).fetchone()[0]
        category_id = conn.execute(
            "INSERT INTO categories(name,slug) VALUES(%s,%s) RETURNING id",
            (f"Return category {suffix}", f"return-category-{suffix}"),
        ).fetchone()[0]
        product_id = conn.execute(
            "INSERT INTO products(category_id,name,slug,status) VALUES(%s,%s,%s,'active') RETURNING id",
            (category_id, f"Return product {suffix}", f"return-product-{suffix}"),
        ).fetchone()[0]
        variant_id = conn.execute(
            "INSERT INTO product_variants(product_id,sku,selling_price,cost_price) VALUES(%s,%s,100,50) RETURNING id",
            (product_id, f"RETURN-{suffix}"),
        ).fetchone()[0]
        po_id = conn.execute(
            "INSERT INTO purchase_orders(purchase_number,supplier_id,location_id,status,subtotal) "
            "VALUES(%s,%s,%s,'ordered',200) RETURNING id",
            (f"RETURN-PO-{suffix}", supplier_id, location_id),
        ).fetchone()[0]
        po_line_id = conn.execute(
            "INSERT INTO purchase_order_lines(purchase_order_id,variant_id,quantity_ordered,unit_cost) "
            "VALUES(%s,%s,4,50) RETURNING id",
            (po_id, variant_id),
        ).fetchone()[0]
        grn_id = conn.execute(
            "INSERT INTO goods_receipts(grn_number,purchase_order_id,supplier_id,location_id,idempotency_key,payload_hash,status) "
            "VALUES(%s,%s,%s,%s,%s,%s,'accepted') RETURNING id",
            (f"RETURN-GRN-{suffix}", po_id, supplier_id, location_id, uuid.uuid4(), "a" * 64),
        ).fetchone()[0]
        grn_line_id = conn.execute(
            "INSERT INTO goods_receipt_lines(goods_receipt_id,purchase_order_line_id,variant_id,received_quantity,accepted_quantity,unit_cost) "
            "VALUES(%s,%s,%s,4,4,50) RETURNING id",
            (grn_id, po_line_id, variant_id),
        ).fetchone()[0]
        invoice_id = conn.execute(
            "INSERT INTO supplier_invoices(supplier_id,purchase_order_id,invoice_number,invoice_date,taxable_value,invoice_total,match_status) "
            "VALUES(%s,%s,%s,current_date,150,150,'approved') RETURNING id",
            (supplier_id, po_id, f"RETURN-BILL-{suffix}"),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO supplier_invoice_lines(supplier_invoice_id,purchase_order_line_id,goods_receipt_line_id,variant_id,quantity,unit_rate,taxable_value) "
            "VALUES(%s,%s,%s,%s,3,50,150)",
            (invoice_id, po_line_id, grn_line_id, variant_id),
        )
    return grn_id, grn_line_id, invoice_id


def test_cumulative_supplier_returns_cannot_exceed_linked_invoice_quantity(api):
    grn_id, grn_line_id, invoice_id = _seed_approved_invoice(TEST_DB)
    first = api.post("/api/purchasing/supplier-returns", json={
        "goods_receipt_id": grn_id,
        "supplier_invoice_id": invoice_id,
        "reason": "First partial return",
        "lines": [{"goods_receipt_line_id": grn_line_id, "quantity": "2.000"}],
    })
    assert first.status_code == 201, first.text

    over_limit = api.post("/api/purchasing/supplier-returns", json={
        "goods_receipt_id": grn_id,
        "supplier_invoice_id": invoice_id,
        "reason": "Would exceed invoice quantity",
        "lines": [{"goods_receipt_line_id": grn_line_id, "quantity": "1.001"}],
    })
    assert over_limit.status_code == 409, over_limit.text
    assert "remaining quantity on the linked supplier invoice" in over_limit.text

    exact_remainder = api.post("/api/purchasing/supplier-returns", json={
        "goods_receipt_id": grn_id,
        "supplier_invoice_id": invoice_id,
        "reason": "Return remaining invoiced quantity",
        "lines": [{"goods_receipt_line_id": grn_line_id, "quantity": "1.000"}],
    })
    assert exact_remainder.status_code == 201, exact_remainder.text
