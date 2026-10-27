import base64, hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, field_validator

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SECRET = os.getenv("SB_SECRET_KEY", "")
ADMIN_EMAIL = os.getenv("SB_ADMIN_EMAIL", "").lower().strip()
ADMIN_PASSWORD = os.getenv("SB_ADMIN_PASSWORD", "")
app = FastAPI(title="Super Bajaar API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("SB_CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()], allow_credentials=True, allow_methods=["GET","POST","PATCH","OPTIONS"], allow_headers=["Authorization","Content-Type"])


def stamp():
    return datetime.now(timezone.utc)


def connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL must be configured")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def pw_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    return salt.hex()+"$"+hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000).hex()


def pw_ok(password, saved):
    try:
        salt, _ = saved.split("$", 1)
        return hmac.compare_digest(pw_hash(password, bytes.fromhex(salt)), saved)
    except (ValueError, TypeError):
        return False


def setup():
    ddl = [
        """CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'customer',created_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS products(id BIGSERIAL PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',image_url TEXT NOT NULL DEFAULT '',price_paise BIGINT NOT NULL CHECK(price_paise>=0),mrp_paise BIGINT NOT NULL CHECK(mrp_paise>=price_paise),variants JSONB NOT NULL DEFAULT '[]'::jsonb,active BOOLEAN NOT NULL DEFAULT TRUE,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS inventory(product_id BIGINT PRIMARY KEY REFERENCES products(id),quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),updated_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS price_history(id BIGSERIAL PRIMARY KEY,product_id BIGINT NOT NULL REFERENCES products(id),price_paise BIGINT NOT NULL CHECK(price_paise>=0),observed_at TIMESTAMPTZ NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS history_lookup ON price_history(product_id,observed_at)",
        """CREATE TABLE IF NOT EXISTS orders(id BIGSERIAL PRIMARY KEY,code TEXT UNIQUE NOT NULL,user_id BIGINT NOT NULL REFERENCES users(id),status TEXT NOT NULL,payment_status TEXT NOT NULL,subtotal BIGINT NOT NULL,delivery BIGINT NOT NULL,discount BIGINT NOT NULL,total BIGINT NOT NULL,address JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL,updated_at TIMESTAMPTZ NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS order_items(id BIGSERIAL PRIMARY KEY,order_id BIGINT NOT NULL REFERENCES orders(id),product_id BIGINT NOT NULL REFERENCES products(id),sku TEXT NOT NULL,name TEXT NOT NULL,variant TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),unit_price BIGINT NOT NULL CHECK(unit_price>=0))""",
        """CREATE TABLE IF NOT EXISTS tickets(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id),topic TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TIMESTAMPTZ NOT NULL)""",
    ]
    with connect() as c:
        for statement in ddl:
            c.execute(statement)
        if ADMIN_EMAIL and ADMIN_PASSWORD:
            c.execute("""INSERT INTO users(email,name,password_hash,role,created_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(email) DO UPDATE SET name=EXCLUDED.name,password_hash=EXCLUDED.password_hash,role='admin'""",
                      (ADMIN_EMAIL,"Super Bajaar Admin",pw_hash(ADMIN_PASSWORD),"admin",stamp()))


def token(u):
    body=base64.urlsafe_b64encode(json.dumps({"sub":u["id"],"role":u["role"],"exp":int(time.time())+43200},separators=(",",":")).encode()).decode().rstrip("=")
    return body+"."+hmac.new(SECRET.encode(),body.encode(),hashlib.sha256).hexdigest()


def auth(authorization: str | None=Header(default=None)):
    if len(SECRET)<32: raise HTTPException(503,"Configure SB_SECRET_KEY (32+ characters)")
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Sign in required")
    try:
        body,sig=authorization[7:].strip().split(".",1)
        if not hmac.compare_digest(sig,hmac.new(SECRET.encode(),body.encode(),hashlib.sha256).hexdigest()): raise ValueError()
        p=json.loads(base64.urlsafe_b64decode(body+"="*(-len(body)%4)))
        if p["exp"]<int(time.time()): raise ValueError()
        with connect() as c: u=c.execute("SELECT id,email,name,phone,role FROM users WHERE id=%s",(p["sub"],)).fetchone()
        if not u or u["role"]!=p["role"]: raise ValueError()
        return dict(u)
    except (ValueError,KeyError,TypeError,json.JSONDecodeError): raise HTTPException(401,"Invalid or expired session")


def admin(u=Depends(auth)):
    if u["role"]!="admin": raise HTTPException(403,"Administrator access required")
    return u


class Register(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    email:EmailStr
    phone:str=Field(default="",max_length=15)
    password:str=Field(min_length=10,max_length=128)
    @field_validator("name", mode="before")
    @classmethod
    def nonblank_name(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Name cannot be blank")
        return value.strip()
class Login(BaseModel):
    email:EmailStr
    password:str=Field(min_length=1,max_length=128)
class Product(BaseModel):
    sku:str=Field(min_length=2,max_length=80)
    name:str=Field(min_length=2,max_length=200)
    category:str=Field(min_length=2,max_length=100)
    description:str=Field(default="",max_length=5000)
    image_url:str=Field(default="",max_length=1000)
    price_paise:int=Field(ge=0)
    mrp_paise:int=Field(ge=0)
    variants:list[str]=Field(default_factory=list,max_length=100)
    quantity:int=Field(default=0,ge=0)
    @field_validator("variants", mode="before")
    @classmethod
    def normalize_variants(cls, value):
        if value is None or value == []:
            return ["Standard"]
        if not isinstance(value, list):
            raise ValueError("Variants must be a list")
        normalized = []
        for variant in value:
            if not isinstance(variant, str) or not variant.strip():
                raise ValueError("Variants cannot be blank")
            cleaned = variant.strip()
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized or ["Standard"]
    @field_validator("sku", "name", "category", mode="before")
    @classmethod
    def required_product_text(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("This product field cannot be blank")
        return value.strip()
class Stock(BaseModel):
    quantity:int=Field(ge=0)
class Address(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    phone:str=Field(pattern=r"^[0-9]{10}$")
    line:str=Field(min_length=5,max_length=300)
    city:str=Field(min_length=2,max_length=100)
    state:str=Field(min_length=2,max_length=100)
    pin:str=Field(pattern=r"^[0-9]{6}$")
    @field_validator("name", "line", "city", "state", mode="before")
    @classmethod
    def required_address_text(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("This address field cannot be blank")
        return value.strip()
class Line(BaseModel):
    product_id:int=Field(gt=0)
    variant:str=Field(default="Standard",max_length=100)
    quantity:int=Field(gt=0,le=99)
    @field_validator("variant", mode="before")
    @classmethod
    def normalize_variant(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return "Standard"
        if not isinstance(value, str):
            raise ValueError("Variant must be text")
        return value.strip()
class NewOrder(BaseModel):
    items:list[Line]=Field(min_length=1,max_length=100)
    address:Address
    coupon:str=Field(default="",max_length=40)
class Status(BaseModel):
    status:str=Field(pattern=r"^(placed|confirmed|packed|shipped|out_for_delivery|delivered|cancelled)$")
class Ticket(BaseModel):
    topic:str=Field(min_length=2,max_length=100)
    message:str=Field(min_length=5,max_length=4000)
    @field_validator("topic", "message", mode="before")
    @classmethod
    def required_ticket_text(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Support topic and message cannot be blank")
        return value.strip()
class TicketStatus(BaseModel):
    status:str=Field(pattern=r"^(open|in_progress|resolved|closed)$")


@app.on_event("startup")
def startup(): setup()

@app.get("/api/health")
def health():
    with connect() as c: c.execute("SELECT 1")
    return {"status":"ok","database":"connected"}

@app.get("/api/delivery/availability")
def delivery_availability(pin: str = Query(..., pattern=r"^[0-9]{6}$")):
    configured = {value.strip() for value in os.getenv("SB_SERVICEABLE_PINS", "").split(",") if value.strip()}
    if not configured:
        return {"pin":pin,"status":"not_configured","serviceable":None,"message":"Delivery PIN coverage has not been configured."}
    serviceable = pin in configured
    return {"pin":pin,"status":"serviceable" if serviceable else "not_serviceable","serviceable":serviceable,"message":"Delivery is available for this PIN." if serviceable else "Delivery is not available for this PIN."}

@app.post("/api/auth/register",status_code=201)
def register(d:Register):
    if len(SECRET)<32: raise HTTPException(503,"Authentication is not configured")
    try:
        with connect() as c:
            u=c.execute("INSERT INTO users(email,name,phone,password_hash,created_at) VALUES(%s,%s,%s,%s,%s) RETURNING id,email,name,phone,role",
                         (str(d.email).lower(),d.name.strip(),d.phone,pw_hash(d.password),stamp())).fetchone()
    except psycopg.errors.UniqueViolation: raise HTTPException(409,"Email already registered")
    return {"token":token(u),"user":dict(u)}

@app.post("/api/auth/login")
def login(d:Login):
    if len(SECRET)<32: raise HTTPException(503,"Authentication is not configured")
    with connect() as c: u=c.execute("SELECT * FROM users WHERE email=%s",(str(d.email).lower(),)).fetchone()
    if not u or not pw_ok(d.password,u["password_hash"]): raise HTTPException(401,"Email or password is incorrect")
    return {"token":token(u),"user":{k:u[k] for k in ("id","email","name","phone","role")}}

@app.get("/api/auth/me")
def me(u=Depends(auth)): return {"user":u}


def product_row(row):
    d=dict(row)
    d["variants"]=d["variants"] if isinstance(d["variants"],list) else []
    d["price"]=d.pop("price_paise")/100
    d["mrp"]=d.pop("mrp_paise")/100
    d["in_stock"]=d.get("quantity",0)>0
    return d

@app.get("/api/products")
def products(q:str="",category:str="",limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    where=["p.active IS TRUE"]; args=[]
    if q.strip(): where.append("(p.name ILIKE %s OR p.sku ILIKE %s OR p.category ILIKE %s)"); args.extend(["%"+q.strip()+"%"]*3)
    if category.strip(): where.append("p.category=%s"); args.append(category.strip())
    clause=" AND ".join(where)
    with connect() as c:
        rows=c.execute("SELECT p.*,COALESCE(i.quantity,0) AS quantity FROM products p LEFT JOIN inventory i ON i.product_id=p.id WHERE "+clause+" ORDER BY p.id DESC LIMIT %s OFFSET %s",(*args,limit,offset)).fetchall()
        total=c.execute("SELECT COUNT(*) FROM products p WHERE "+clause,args).fetchone()["count"]
    return {"items":[product_row(x) for x in rows],"total":total,"limit":limit,"offset":offset}

@app.post("/api/admin/products",status_code=201)
def create_product(d:Product,u=Depends(admin)):
    if d.mrp_paise<d.price_paise: raise HTTPException(422,"MRP cannot be lower than selling price")
    now=stamp()
    try:
        with connect() as c:
            pid=c.execute("INSERT INTO products(sku,name,category,description,image_url,price_paise,mrp_paise,variants,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (d.sku.strip(),d.name.strip(),d.category.strip(),d.description,d.image_url,d.price_paise,d.mrp_paise,Jsonb(d.variants),now,now)).fetchone()["id"]
            c.execute("INSERT INTO inventory(product_id,quantity,updated_at) VALUES(%s,%s,%s)",(pid,d.quantity,now))
            c.execute("INSERT INTO price_history(product_id,price_paise,observed_at) VALUES(%s,%s,%s)",(pid,d.price_paise,now))
            row=c.execute("SELECT p.*,i.quantity FROM products p JOIN inventory i ON i.product_id=p.id WHERE p.id=%s",(pid,)).fetchone()
    except psycopg.errors.UniqueViolation: raise HTTPException(409,"SKU already exists")
    return product_row(row)

@app.patch("/api/admin/products/{pid}")
def update_product(pid:int,d:Product,u=Depends(admin)):
    if d.mrp_paise<d.price_paise: raise HTTPException(422,"MRP cannot be lower than selling price")
    now=stamp()
    try:
        with connect() as c:
            old=c.execute("SELECT price_paise FROM products WHERE id=%s AND active IS TRUE",(pid,)).fetchone()
            if not old: raise HTTPException(404,"Product not found")
            c.execute("UPDATE products SET sku=%s,name=%s,category=%s,description=%s,image_url=%s,price_paise=%s,mrp_paise=%s,variants=%s,updated_at=%s WHERE id=%s",
                (d.sku.strip(),d.name.strip(),d.category.strip(),d.description,d.image_url,d.price_paise,d.mrp_paise,Jsonb(d.variants),now,pid))
            c.execute("INSERT INTO inventory(product_id,quantity,updated_at) VALUES(%s,%s,%s) ON CONFLICT(product_id) DO UPDATE SET quantity=EXCLUDED.quantity,updated_at=EXCLUDED.updated_at",(pid,d.quantity,now))
            if old["price_paise"]!=d.price_paise: c.execute("INSERT INTO price_history(product_id,price_paise,observed_at) VALUES(%s,%s,%s)",(pid,d.price_paise,now))
            row=c.execute("SELECT p.*,i.quantity FROM products p JOIN inventory i ON i.product_id=p.id WHERE p.id=%s",(pid,)).fetchone()
    except psycopg.errors.UniqueViolation: raise HTTPException(409,"SKU already exists")
    return product_row(row)

@app.patch("/api/admin/products/{pid}/stock")
def stock(pid:int,d:Stock,u=Depends(admin)):
    with connect() as c:
        if not c.execute("SELECT id FROM products WHERE id=%s AND active IS TRUE",(pid,)).fetchone(): raise HTTPException(404,"Product not found")
        c.execute("INSERT INTO inventory(product_id,quantity,updated_at) VALUES(%s,%s,%s) ON CONFLICT(product_id) DO UPDATE SET quantity=EXCLUDED.quantity,updated_at=EXCLUDED.updated_at",(pid,d.quantity,stamp()))
    return {"product_id":pid,"quantity":d.quantity}

@app.get("/api/products/{pid}/price-history")
def history(pid:int,days:int=Query(30,ge=1,le=365)):
    since=datetime.fromtimestamp(time.time()-days*86400,timezone.utc)
    with connect() as c:
        if not c.execute("SELECT id FROM products WHERE id=%s AND active IS TRUE",(pid,)).fetchone(): raise HTTPException(404,"Product not found")
        rows=c.execute("SELECT price_paise,observed_at FROM price_history WHERE product_id=%s AND observed_at>=%s ORDER BY observed_at",(pid,since)).fetchall()
    return {"product_id":pid,"days":days,"observations":[{"price":x["price_paise"]/100,"observed_at":x["observed_at"]} for x in rows],"note":"Only recorded observations are returned; history is never fabricated."}

@app.post("/api/orders",status_code=201)
def order(d:NewOrder,u=Depends(auth)):
    configured_pins = {value.strip() for value in os.getenv("SB_SERVICEABLE_PINS", "").split(",") if value.strip()}
    if not configured_pins:
        raise HTTPException(503, "Delivery coverage is not configured. Please contact the store before placing an order.")
    if d.address.pin not in configured_pins:
        raise HTTPException(422, "Delivery is not available for this PIN code")
    now=stamp()
    with connect() as c:
        required={}
        for item in d.items: required[item.product_id]=required.get(item.product_id,0)+item.quantity
        products_by_id={}
        # Lock inventory rows in stable ID order so concurrent checkouts cannot oversell stock.
        for pid in sorted(required):
            p=c.execute("SELECT id,sku,name,price_paise,variants FROM products WHERE id=%s AND active IS TRUE",(pid,)).fetchone()
            if not p: raise HTTPException(404,"Product unavailable")
            requested_variants={item.variant.strip() for item in d.items if item.product_id==pid}
            allowed_variants=p["variants"] if isinstance(p["variants"],list) else []
            if allowed_variants and any(variant not in allowed_variants for variant in requested_variants):
                raise HTTPException(422,"Selected product option is no longer available for "+p["name"])
            inv=c.execute("SELECT quantity FROM inventory WHERE product_id=%s FOR UPDATE",(pid,)).fetchone()
            if (inv["quantity"] if inv else 0)<required[pid]: raise HTTPException(409,"Insufficient stock for "+p["name"])
            products_by_id[pid]=p
        subtotal=sum(products_by_id[x.product_id]["price_paise"]*x.quantity for x in d.items)
        discount=min((subtotal+5)//10,30000) if d.coupon.strip().upper()=="WELCOME10" else 0
        delivery=0 if subtotal>=79900 else 4900; total=max(0,subtotal-discount+delivery); code="SB"+secrets.token_hex(5).upper()
        order_id=c.execute("INSERT INTO orders(code,user_id,status,payment_status,subtotal,delivery,discount,total,address,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (code,u["id"],"placed","pending",subtotal,delivery,discount,total,Jsonb(d.address.model_dump()),now,now)).fetchone()["id"]
        for pid,qty in required.items(): c.execute("UPDATE inventory SET quantity=quantity-%s,updated_at=%s WHERE product_id=%s",(qty,now,pid))
        for item in d.items:
            p=products_by_id[item.product_id]
            c.execute("INSERT INTO order_items(order_id,product_id,sku,name,variant,quantity,unit_price) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (order_id,item.product_id,p["sku"],p["name"],item.variant,item.quantity,p["price_paise"]))
    return {"id":code,"status":"placed","payment_status":"pending","subtotal":subtotal/100,"delivery":delivery/100,"discount":discount/100,"total":total/100,"created_at":now,"items":[{"product_id":item.product_id,"sku":products_by_id[item.product_id]["sku"],"name":products_by_id[item.product_id]["name"],"variant":item.variant,"quantity":item.quantity,"price":products_by_id[item.product_id]["price_paise"]/100} for item in d.items]}

@app.get("/api/orders")
def my_orders(u=Depends(auth)):
    with connect() as c:
        orders=c.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY id DESC",(u["id"],)).fetchall(); result=[]
        for o in orders:
            items=c.execute("SELECT product_id,sku,name,variant,quantity,unit_price FROM order_items WHERE order_id=%s",(o["id"],)).fetchall()
            result.append({"id":o["code"],"status":o["status"],"payment_status":o["payment_status"],"subtotal":o["subtotal"]/100,"delivery":o["delivery"]/100,"discount":o["discount"]/100,"total":o["total"]/100,"address":o["address"],"created_at":o["created_at"],"items":[{"product_id":i["product_id"],"sku":i["sku"],"name":i["name"],"variant":i["variant"],"quantity":i["quantity"],"price":i["unit_price"]/100} for i in items]})
    return {"items":result}

@app.get("/api/admin/orders")
def admin_orders(u=Depends(admin)):
    with connect() as c:
        rows=c.execute("SELECT o.id,o.code,o.status,o.payment_status,o.subtotal,o.delivery,o.discount,o.total,o.address,o.created_at,u.email,u.name FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC").fetchall()
        items=[]
        for order in rows:
            lines=c.execute("SELECT product_id,sku,name,variant,quantity,unit_price FROM order_items WHERE order_id=%s ORDER BY id",(order["id"],)).fetchall()
            item=dict(order); item.pop("id",None)
            for key in ("subtotal","delivery","discount","total"): item[key]=item[key]/100
            item["items"]=[{**dict(line),"price":line["unit_price"]/100} for line in lines]
            for line in item["items"]: line.pop("unit_price",None)
            items.append(item)
    return {"items":items}


@app.get("/api/admin/customers")
def admin_customers(u=Depends(admin)):
    with connect() as c:
        rows=c.execute("""
            SELECT u.id,u.name,u.email,u.phone,u.created_at,
                   COUNT(o.id)::INTEGER AS order_count
            FROM users u
            LEFT JOIN orders o ON o.user_id=u.id
            WHERE u.role='customer'
            GROUP BY u.id,u.name,u.email,u.phone,u.created_at
            ORDER BY u.created_at DESC,u.id DESC
        """).fetchall()
    return {"items":[dict(row) for row in rows]}

def restock_cancelled_order(c, order_id, now):
    items=c.execute("SELECT product_id,quantity FROM order_items WHERE order_id=%s",(order_id,)).fetchall()
    for item in items:
        c.execute("INSERT INTO inventory(product_id,quantity,updated_at) VALUES(%s,%s,%s) ON CONFLICT(product_id) DO UPDATE SET quantity=inventory.quantity+EXCLUDED.quantity,updated_at=EXCLUDED.updated_at",(item["product_id"],item["quantity"],now))


@app.patch("/api/orders/{code}/cancel")
def cancel_my_order(code:str,u=Depends(auth)):
    now=stamp()
    with connect() as c:
        row=c.execute("SELECT id,status FROM orders WHERE code=%s AND user_id=%s FOR UPDATE",(code,u["id"])).fetchone()
        if not row: raise HTTPException(404,"Order not found")
        if row["status"] not in ("placed","confirmed"): raise HTTPException(409,"This order can no longer be cancelled")
        restock_cancelled_order(c,row["id"],now)
        c.execute("UPDATE orders SET status=%s,updated_at=%s WHERE id=%s",("cancelled",now,row["id"]))
    return {"id":code,"status":"cancelled"}


@app.patch("/api/admin/orders/{code}/status")
def status(code:str,d:Status,u=Depends(admin)):
    now=stamp()
    with connect() as c:
        row=c.execute("SELECT id,status FROM orders WHERE code=%s FOR UPDATE",(code,)).fetchone()
        if not row: raise HTTPException(404,"Order not found")
        transitions={"placed":{"confirmed","cancelled"},"confirmed":{"packed","cancelled"},"packed":{"shipped","cancelled"},"shipped":{"out_for_delivery"},"out_for_delivery":{"delivered"},"delivered":set(),"cancelled":set()}
        if d.status!=row["status"] and d.status not in transitions.get(row["status"],set()):
            raise HTTPException(409,"Order cannot move from "+row["status"]+" to "+d.status)
        if d.status=="cancelled" and row["status"]!="cancelled": restock_cancelled_order(c,row["id"],now)
        c.execute("UPDATE orders SET status=%s,updated_at=%s WHERE id=%s",(d.status,now,row["id"]))
    return {"id":code,"status":d.status}

@app.post("/api/support",status_code=201)
def support(d:Ticket,u=Depends(auth)):
    with connect() as c: tid=c.execute("INSERT INTO tickets(user_id,topic,message,created_at) VALUES(%s,%s,%s,%s) RETURNING id",(u["id"],d.topic.strip(),d.message.strip(),stamp())).fetchone()["id"]
    return {"id":tid,"status":"open"}

@app.get("/api/admin/support")
def support_queue(u=Depends(admin)):
    with connect() as c: rows=c.execute("SELECT t.id,t.topic,t.message,t.status,t.created_at,u.email FROM tickets t JOIN users u ON u.id=t.user_id ORDER BY t.id DESC").fetchall()
    return {"items":[dict(x) for x in rows]}

@app.patch("/api/admin/support/{ticket_id}/status")
def update_support_status(ticket_id:int,d:TicketStatus,u=Depends(admin)):
    with connect() as c:
        if not c.execute("SELECT id FROM tickets WHERE id=%s",(ticket_id,)).fetchone(): raise HTTPException(404,"Support ticket not found")
        c.execute("UPDATE tickets SET status=%s WHERE id=%s",(d.status,ticket_id))
    return {"id":ticket_id,"status":d.status}
