import json, os, urllib.error, urllib.request, uuid

BASE=os.getenv("SB_SMOKE_BASE_URL","http://127.0.0.1:8001").rstrip("/")
ADMIN_EMAIL=os.environ["SB_ADMIN_EMAIL"]
ADMIN_PASSWORD=os.environ["SB_ADMIN_PASSWORD"]


def request(method,path,payload=None,token=None,expected=200):
    data=None if payload is None else json.dumps(payload).encode()
    headers={"Accept":"application/json"}
    if data is not None: headers["Content-Type"]="application/json"
    if token: headers["Authorization"]="Bearer "+token
    req=urllib.request.Request(BASE+path,data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=15) as response: status,body=response.status,response.read()
    except urllib.error.HTTPError as error: status,body=error.code,error.read()
    if status!=expected: raise AssertionError(f"{method} {path}: expected {expected}, got {status}: {body.decode(errors='replace')}")
    return json.loads(body) if body else {}


def main():
    assert request("GET","/api/health")=={"status":"ok","database":"connected"}
    suffix=uuid.uuid4().hex[:10]
    registered=request("POST","/api/auth/register",{"name":"Smoke Test Customer","email":f"smoke-{suffix}@example.com","phone":"9876543210","password":"Smoke-test-Password-123!"},expected=201)
    assert registered.get("token") and registered.get("user")
    request("POST","/api/auth/login",{"email":registered["user"]["email"],"password":"definitely-wrong-password"},expected=401)
    logged=request("POST","/api/auth/login",{"email":ADMIN_EMAIL,"password":ADMIN_PASSWORD})
    assert logged.get("token") and logged.get("user",{}).get("role")=="admin"
    availability=request("GET","/api/delivery/availability?pin=560001")
    assert availability.get("pin")=="560001" and availability.get("status") in ("not_configured","serviceable","not_serviceable")
    configured_pins=[value.strip() for value in os.getenv("SB_SERVICEABLE_PINS","").split(",") if value.strip()]
    order_pin=configured_pins[0] if configured_pins else "560001"
    product=request("POST","/api/admin/products",{"sku":f"SMOKE-{suffix}","name":"Smoke Test Product","category":"Testing","description":"Smoke-test item","image_url":"","price_paise":10000,"mrp_paise":12000,"variants":["Standard"],"quantity":5},token=logged["token"],expected=201)
    assert product.get("id") and product.get("quantity")==5
    updated=request("PATCH",f"/api/admin/products/{product['id']}",{"sku":f"SMOKE-{suffix}","name":"Smoke Test Product Updated","category":"Testing","description":"Updated smoke-test item","image_url":"","price_paise":11000,"mrp_paise":12000,"variants":["Standard"],"quantity":5},token=logged["token"])
    assert updated.get("name")=="Smoke Test Product Updated" and updated.get("price")==110.0
    order_payload={"items":[{"product_id":product["id"],"variant":"Standard","quantity":1}],"address":{"name":"Smoke Test Customer","phone":"9876543210","line":"1 Test Road","city":"Bengaluru","state":"Karnataka","pin":order_pin},"coupon":""}
    request("POST","/api/orders",{**order_payload,"items":[{"product_id":product["id"],"variant":"Not a real option","quantity":1}]},token=registered["token"],expected=422)
    request("POST","/api/orders",{**order_payload,"items":[{"product_id":product["id"],"variant":"Standard","quantity":6}]},token=registered["token"],expected=409)
    order=request("POST","/api/orders",order_payload,token=registered["token"],expected=201)
    assert order.get("id") and order.get("status")=="placed"
    assert order.get("items")==[{"product_id":product["id"],"sku":f"SMOKE-{suffix}","name":"Smoke Test Product Updated","variant":"Standard","quantity":1,"price":110.0}]
    request("PATCH",f"/api/admin/orders/{order['id']}/status",{"status":"shipped"},token=logged["token"],expected=409)
    admin_orders=request("GET","/api/admin/orders",token=logged["token"])
    admin_order=next((item for item in admin_orders.get("items",[]) if item.get("code")==order["id"]),None)
    assert admin_order and admin_order.get("address",{}).get("pin")==order_pin
    assert admin_order.get("items") and admin_order["items"][0].get("name")=="Smoke Test Product Updated"
    changed=request("PATCH",f"/api/admin/orders/{order['id']}/status",{"status":"confirmed"},token=logged["token"])
    assert changed=={"id":order["id"],"status":"confirmed"}
    cancelled=request("PATCH",f"/api/orders/{order['id']}/cancel",token=registered["token"])
    assert cancelled=={"id":order["id"],"status":"cancelled"}
    remaining=request("GET",f"/api/products?q=SMOKE-{suffix}")
    assert remaining.get("items") and remaining["items"][0].get("quantity")==5
    request("PATCH",f"/api/orders/{order['id']}/cancel",token=registered["token"],expected=409)
    print("PASS: health, PIN availability, register, bad login (401), admin login, product create/edit, invalid variant rejection, stock oversell rejection, server-priced order items, cancellation and stock restoration")


if __name__=="__main__": main()
