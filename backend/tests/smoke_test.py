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
    product=request("POST","/api/admin/products",{"sku":f"SMOKE-{suffix}","name":"Smoke Test Product","category":"Testing","description":"Smoke-test item","image_url":"","price_paise":10000,"mrp_paise":12000,"variants":["Standard"],"quantity":5},token=logged["token"],expected=201)
    assert product.get("id") and product.get("quantity")==5
    order=request("POST","/api/orders",{"items":[{"product_id":product["id"],"variant":"Standard","quantity":1}],"address":{"name":"Smoke Test Customer","phone":"9876543210","line":"1 Test Road","city":"Bengaluru","state":"Karnataka","pin":"560001"},"coupon":""},token=registered["token"],expected=201)
    assert order.get("id") and order.get("status")=="placed"
    changed=request("PATCH",f"/api/admin/orders/{order['id']}/status",{"status":"confirmed"},token=logged["token"])
    assert changed=={"id":order["id"],"status":"confirmed"}
    print("PASS: health, register, bad login (401), admin login, product create, order, status change")


if __name__=="__main__": main()
