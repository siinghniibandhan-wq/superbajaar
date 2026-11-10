"""Order -> Inventory -> Accounting COGS integration on disposable PostgreSQL."""
import os
import uuid
import json
from decimal import Decimal

import psycopg
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.auth_middleware import require_active_session
from app.main import app

TEST_DB=os.environ.get("SB_TEST_DATABASE_URL","")
pytestmark=pytest.mark.skipif(not TEST_DB,reason="SB_TEST_DATABASE_URL is not set")
if TEST_DB and ("sb_app" in TEST_DB or "amazonaws" in TEST_DB):
    raise RuntimeError("Refusing to run order/inventory integration tests against production-like database")


@pytest.fixture()
def api(monkeypatch):
    suffix=uuid.uuid4().hex[:10]
    with psycopg.connect(TEST_DB) as conn:
        user_id=conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'super_admin') RETURNING id",
            (f"order-{suffix}@test.local","Order Integration Test","test-hash"),
        ).fetchone()[0]
        category_id=conn.execute(
            "INSERT INTO categories(name,slug) VALUES(%s,%s) RETURNING id",
            ("Order Test "+suffix,"order-test-"+suffix),
        ).fetchone()[0]
        product_id=conn.execute(
            "INSERT INTO products(category_id,name,slug,status) VALUES(%s,%s,%s,'active') RETURNING id",
            (category_id,"Order Test Product "+suffix,"order-test-product-"+suffix),
        ).fetchone()[0]
        variant_id=conn.execute(
            "INSERT INTO product_variants(product_id,sku,selling_price,cost_price) VALUES(%s,%s,100,10) RETURNING id",
            (product_id,"OT-"+suffix),
        ).fetchone()[0]
        establishment_id=conn.execute(
            "INSERT INTO hr_establishments(code,legal_name,display_name,state_code) VALUES(%s,%s,%s,'JH') RETURNING id",
            ("OT-"+suffix,"Order Test Legal Entity "+suffix,"Order Test Establishment "+suffix),
        ).fetchone()[0]
        policy_config={
            "event_policies":{"dispatch":{"approval_required":False}},
            "shelf_life":{"default_minimum_remaining_days":None},
        }
        conn.execute(
            "INSERT INTO organisation_policy_versions(establishment_id,domain,version_label,effective_from,policy_config,status,created_by_user_id,activated_by_user_id,activated_at) "
            "VALUES(%s,'inventory','Integration test policy',CURRENT_DATE,%s::jsonb,'active',%s,%s,now())",
            (establishment_id,json.dumps(policy_config),user_id,user_id),
        )
        location_id=conn.execute(
            "INSERT INTO stock_locations(name,location_type,establishment_id) VALUES(%s,'warehouse',%s) RETURNING id",
            ("Order Test Warehouse "+suffix,establishment_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO inventory_balances(variant_id,location_id,on_hand,reserved) VALUES(%s,%s,5,0)",
            (variant_id,location_id),
        )
        movement_id=conn.execute(
            "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,note) "
            "VALUES(%s,%s,'receipt',5,'integration_test','Seed valued stock') RETURNING id",
            (variant_id,location_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO inventory_cost_layers(variant_id,location_id,receipt_movement_id,batch_code,"
            "received_quantity,remaining_quantity,unit_cost) VALUES(%s,%s,%s,%s,5,5,10)",
            (variant_id,location_id,movement_id,"BATCH-"+suffix),
        )
    role={"value":"super_admin"}
    async def fake_session(request:Request):
        request.state.role=role["value"]
        request.state.user_id=user_id
        request.state.user_email=f"order-{suffix}@test.local"
    from app.api import orders
    monkeypatch.setattr(orders.settings,"database_url",TEST_DB)
    from app.api import accounting
    monkeypatch.setattr(accounting.settings,"database_url",TEST_DB)
    from app.api import delivery
    monkeypatch.setattr(delivery.settings,"database_url",TEST_DB)
    from app.api import fulfilment
    monkeypatch.setattr(fulfilment.settings,"database_url",TEST_DB)
    from app.api import inventory
    monkeypatch.setattr(inventory.settings,"database_url",TEST_DB)
    app.dependency_overrides[require_active_session]=fake_session
    client=TestClient(app)
    client.role=role
    client.variant_id=variant_id
    client.location_id=location_id
    client.establishment_id=establishment_id
    client.legal_entity_code="OT-"+suffix
    client.suffix=suffix
    yield client
    app.dependency_overrides.pop(require_active_session,None)


def ok(response,status=200):
    assert response.status_code==status,response.text
    return response.json()


def test_pos_order_reservation_dispatch_and_cogs_posting(api):
    order=ok(api.post("/api/orders",json={
        "channel":"pos","customer_name":"POS Test Customer","location_id":api.location_id,
        "lines":[{"variant_id":api.variant_id,"quantity":3}]
    }),201)
    order_id=order["id"]
    assert order["stock_reserved"] is True
    with psycopg.connect(TEST_DB) as conn:
        balance=conn.execute(
            "SELECT on_hand,reserved FROM inventory_balances WHERE variant_id=%s AND location_id=%s",
            (api.variant_id,api.location_id),
        ).fetchone()
        assert balance[0]==5 and balance[1]==3

    for status in ("confirmed","processing","ready_for_dispatch"):
        ok(api.patch("/api/orders/"+str(order_id)+"/status",json={"status":status}))

    shipment=ok(api.post("/api/delivery/shipments",json={
        "order_id":order_id,"delivery_pin":"123456","recipient_name":"POS Test Customer",
        "recipient_phone":"9876543210","address":"Test dispatch address",
        "location_id":api.location_id,
    }),201)
    task=ok(api.post(f"/api/fulfilment/shipments/{shipment['id']}/pick-task",json={}),201)
    task_detail=ok(api.get(f"/api/fulfilment/pick-tasks/{task['id']}"))
    pick_line=task_detail["lines"][0]
    ok(api.patch(f"/api/fulfilment/pick-tasks/{task['id']}/lines/{pick_line['id']}",json={
        "picked_quantity":3,"short_quantity":0,
    }))
    ok(api.post(f"/api/fulfilment/pick-tasks/{task['id']}/complete",json={}))
    package=ok(api.post(f"/api/fulfilment/shipments/{shipment['id']}/packages",json={
        "package_number":"PKG-"+api.suffix,
        "lines":[{"pick_task_line_id":pick_line["id"],"order_line_id":pick_line["order_line_id"],"quantity":3}],
    }),201)
    ok(api.patch(f"/api/fulfilment/packages/{package['id']}/seal",json={}))
    ok(api.patch(f"/api/delivery/shipments/{shipment['id']}/status",json={"status":"assigned"}))
    with psycopg.connect(TEST_DB) as conn:
        package_line_id=conn.execute(
            "SELECT id FROM fulfilment_package_lines WHERE package_id=%s",(package["id"],)
        ).fetchone()[0]
    first_dispatch_id=str(uuid.uuid4())
    first_dispatch={"status":"dispatched","dispatch_id":first_dispatch_id,
                    "package_lines":[{"package_line_id":package_line_id,"quantity":1}]}
    ok(api.patch(f"/api/delivery/shipments/{shipment['id']}/status",json=first_dispatch))
    with psycopg.connect(TEST_DB) as conn:
        balance=conn.execute(
            "SELECT on_hand,reserved FROM inventory_balances WHERE variant_id=%s AND location_id=%s",
            (api.variant_id,api.location_id),
        ).fetchone()
        assert balance[0]==4 and balance[1]==2
        assert conn.execute(
            "SELECT count(*) FROM accounting_vouchers WHERE source_type='order_fulfilment' AND source_id=%s",
            (str(order_id),),
        ).fetchone()[0]==0

    replay=ok(api.patch(f"/api/delivery/shipments/{shipment['id']}/status",json=first_dispatch))
    assert replay["duplicate"] is True
    conflict={**first_dispatch,"package_lines":[{"package_line_id":package_line_id,"quantity":2}]}
    assert api.patch(f"/api/delivery/shipments/{shipment['id']}/status",json=conflict).status_code==409
    assert api.patch(f"/api/delivery/shipments/{shipment['id']}/status",json={
        "status":"dispatched","dispatch_id":str(uuid.uuid4()),
        "package_lines":[{"package_line_id":package_line_id,"quantity":3}],
    }).status_code==409

    ok(api.patch(f"/api/delivery/shipments/{shipment['id']}/status",json={
        "status":"dispatched","dispatch_id":str(uuid.uuid4()),
        "package_lines":[{"package_line_id":package_line_id,"quantity":1}],
    }))
    ok(api.patch(f"/api/delivery/shipments/{shipment['id']}/status",json={
        "status":"dispatched","dispatch_id":str(uuid.uuid4()),
        "package_lines":[{"package_line_id":package_line_id,"quantity":1}],
    }))
    with psycopg.connect(TEST_DB) as conn:
        balance=conn.execute(
            "SELECT on_hand,reserved FROM inventory_balances WHERE variant_id=%s AND location_id=%s",
            (api.variant_id,api.location_id),
        ).fetchone()
        assert balance[0]==2 and balance[1]==0
        layer=conn.execute(
            "SELECT remaining_quantity FROM inventory_cost_layers WHERE variant_id=%s AND location_id=%s",
            (api.variant_id,api.location_id),
        ).fetchone()
        assert layer[0]==2
        issue=conn.execute(
            "SELECT sum(total_cost) FROM inventory_order_issues WHERE order_id=%s",
            (order_id,),
        ).fetchone()
        assert Decimal(str(issue[0]))==Decimal("30.00")
        voucher=conn.execute(
            "SELECT id,total_amount,status FROM accounting_vouchers WHERE source_type='order_fulfilment' AND source_id=%s",
            (str(order_id),),
        ).fetchone()
        assert voucher is not None and voucher[2]=="posted"
        assert Decimal(str(voucher[1]))==Decimal("30.00")
        dispatch_package_lines=conn.execute(
            "SELECT count(*),sum(quantity) FROM fulfilment_dispatch_event_lines WHERE package_line_id=%s",
            (package_line_id,),
        ).fetchone()
        assert dispatch_package_lines[0]==3 and dispatch_package_lines[1]==3
        lines=conn.execute(
            "SELECT a.code,l.debit,l.credit FROM accounting_voucher_lines l "
            "JOIN accounting_accounts a ON a.id=l.account_id WHERE l.voucher_id=%s ORDER BY a.code",
            (voucher[0],),
        ).fetchall()
        by_code={row[0]:(Decimal(str(row[1])),Decimal(str(row[2]))) for row in lines}
        assert by_code["5000"]==(Decimal("30.00"),Decimal("0.00"))
        assert by_code["1200"]==(Decimal("0.00"),Decimal("30.00"))

        return_mapping_accounts=conn.execute(
            "SELECT id,code FROM accounting_accounts WHERE code IN ('1200','5000')"
        ).fetchall()
        account_ids={row[1]:row[0] for row in return_mapping_accounts}
        for event_type,role,code in (
            ("inventory_return","inventory_asset","1200"),
            ("inventory_return","inventory_cogs_reversal","5000"),
            ("inventory_return_writeoff","inventory_return_writeoff_expense","5020"),
            ("inventory_return_writeoff","inventory_cogs_reversal","5000"),
        ):
            conn.execute(
                "INSERT INTO accounting_event_account_mappings "
                "(legal_entity_code,source_module,event_type,line_role,account_id,effective_from,status,approved_by_user_id,approved_at) "
                "VALUES(%s,'inventory',%s,%s,%s,CURRENT_DATE,'approved',%s,now())",
                (api.legal_entity_code,event_type,role,account_ids[code] if code in account_ids else conn.execute("SELECT id FROM accounting_accounts WHERE code=%s",(code,)).fetchone()[0],1),
            )

    with psycopg.connect(TEST_DB) as conn:
        order_line_id=conn.execute("SELECT id FROM order_lines WHERE order_id=%s",(order_id,)).fetchone()[0]
    ok(api.patch(f"/api/delivery/shipments/{shipment['id']}/status",json={"status":"in_transit"}))

    def request_and_inspect(quantity, inspection_status, reason):
        created=ok(api.post(f"/api/fulfilment/shipments/{shipment['id']}/returns",json={
            "reason":reason,"lines":[{"order_line_id":order_line_id,"quantity":quantity}],
        }),201)
        detail=ok(api.get(f"/api/fulfilment/returns/{created['id']}"))
        line_id=detail["lines"][0]["id"]
        ok(api.post(f"/api/fulfilment/returns/{created['id']}/receive"))
        inspected=ok(api.patch(f"/api/fulfilment/returns/{created['id']}/lines/{line_id}/inspection",json={
            "received_quantity":quantity,"inspection_status":inspection_status,"inspection_note":reason,
        }))
        assert inspected["return_status"]=="approved"
        return created,line_id

    restock_return,restock_line=request_and_inspect(1,"accepted","Sealed and saleable")
    posted=ok(api.post(f"/api/fulfilment/returns/{restock_return['id']}/lines/{restock_line}/disposition",json={
        "disposition":"restock","location_id":api.location_id,
    }))
    assert posted["status"]=="posted" and Decimal(str(posted["total_cost"]))==Decimal("10.00")

    holding=ok(api.post("/api/inventory/locations",json={
        "name":"Return Quarantine "+api.suffix,"location_type":"warehouse",
        "establishment_id":api.establishment_id,"is_fulfillable":False,
    }),201)
    quarantine_return,quarantine_line=request_and_inspect(1,"quarantined","Needs quarantine review")
    quarantined=ok(api.post(f"/api/fulfilment/returns/{quarantine_return['id']}/lines/{quarantine_line}/disposition",json={
        "disposition":"quarantine","location_id":holding["id"],
    }))
    assert quarantined["status"]=="posted" and Decimal(str(quarantined["total_cost"]))==Decimal("10.00")
    blocked_order=api.post("/api/orders",json={
        "channel":"pos","customer_name":"Quarantine reservation must fail",
        "location_id":holding["id"],"lines":[{"variant_id":api.variant_id,"quantity":1}],
    })
    assert blocked_order.status_code==409

    writeoff_return,writeoff_line=request_and_inspect(1,"damaged","Not recoverable")
    written_off=ok(api.post(f"/api/fulfilment/returns/{writeoff_return['id']}/lines/{writeoff_line}/disposition",json={
        "disposition":"write_off",
    }))
    assert written_off["status"]=="posted" and Decimal(str(written_off["total_cost"]))==Decimal("10.00")

    replay=ok(api.post(f"/api/fulfilment/returns/{restock_return['id']}/lines/{restock_line}/disposition",json={
        "disposition":"restock","location_id":api.location_id,
    }))
    assert replay["duplicate"] is True
    with psycopg.connect(TEST_DB) as conn:
        warehouse_balance=conn.execute(
            "SELECT on_hand,reserved FROM inventory_balances WHERE variant_id=%s AND location_id=%s",
            (api.variant_id,api.location_id),
        ).fetchone()
        holding_balance=conn.execute(
            "SELECT on_hand,reserved FROM inventory_balances WHERE variant_id=%s AND location_id=%s",
            (api.variant_id,holding["id"]),
        ).fetchone()
        assert warehouse_balance[0]==3 and warehouse_balance[1]==0
        assert holding_balance[0]==1 and holding_balance[1]==0
        assert conn.execute("SELECT is_fulfillable FROM stock_locations WHERE id=%s",(holding["id"],)).fetchone()[0] is False
        assert conn.execute(
            "SELECT sum(remaining_quantity) FROM inventory_cost_layers WHERE variant_id=%s",
            (api.variant_id,),
        ).fetchone()[0]==4
        assert conn.execute(
            "SELECT count(*),sum(quantity) FROM fulfilment_return_dispatch_allocations WHERE return_line_id IN (%s,%s,%s)",
            (restock_line,quarantine_line,writeoff_line),
        ).fetchone()==(3,Decimal("3.000"))
        writeoff_voucher=conn.execute(
            "SELECT id,total_amount,status FROM accounting_vouchers WHERE source_type='fulfilment_return_line' AND source_id=%s",
            (str(writeoff_line),),
        ).fetchone()
        assert writeoff_voucher is not None and writeoff_voucher[2]=="posted"
        assert Decimal(str(writeoff_voucher[1]))==Decimal("10.00")
        writeoff_lines=conn.execute(
            "SELECT a.code,l.debit,l.credit FROM accounting_voucher_lines l "
            "JOIN accounting_accounts a ON a.id=l.account_id WHERE l.voucher_id=%s",
            (writeoff_voucher[0],),
        ).fetchall()
        writeoff_by_code={row[0]:(Decimal(str(row[1])),Decimal(str(row[2]))) for row in writeoff_lines}
        assert writeoff_by_code["5020"]==(Decimal("10.00"),Decimal("0.00"))
        assert writeoff_by_code["5000"]==(Decimal("0.00"),Decimal("10.00"))
        assert conn.execute(
            "SELECT count(*) FROM accounting_vouchers WHERE source_type='fulfilment_return_line'",
        ).fetchone()[0]==3
