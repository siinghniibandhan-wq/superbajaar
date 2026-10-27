import hashlib, hmac, json, os, secrets, sqlite3, time
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

BASE = Path(__file__).resolve().parent
DB_PATH = os.getenv("SB_DATABASE_PATH", str(BASE / "superbajaar.db"))
SECRET = os.getenv("SB_SECRET_KEY", "")
ADMIN_EMAIL = os.getenv("SB_ADMIN_EMAIL", "").lower().strip()
ADMIN_PASSWORD = os.getenv("SB_ADMIN_PASSWORD", "")
app = FastAPI(title="Super Bajaar API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("SB_CORS_ORIGINS", "http://localhost:5173").split(",") if x.strip()], allow_credentials=True, allow_methods=["GET","POST","PATCH","OPTIONS"], allow_headers=["Authorization","Content-Type"])

def stamp():
    return datetime.now(timezone.utc).isoformat()

def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c

def pw_hash(p, salt=None):
    salt = salt or secrets.token_bytes(16)
    return salt.hex()+"$"+hashlib.pbkdf2_hmac("sha256", p.encode(), salt, 310000).hex()

def pw_ok(p, saved):
    try:
        salt, _ = saved.split("$",1)
        return hmac.compare_digest(pw_hash(p,bytes.fromhex(salt)),saved)
    except (ValueError,TypeError):
        return False

def setup():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'customer',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',image_url TEXT NOT NULL DEFAULT '',price_paise INTEGER NOT NULL CHECK(price_paise>=0),mrp_paise INTEGER NOT NULL CHECK(mrp_paise>=price_paise),variants TEXT NOT NULL DEFAULT '[]',active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS inventory(product_id INTEGER PRIMARY KEY REFERENCES products(id),quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity>=0),updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS price_history(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL REFERENCES products(id),price_paise INTEGER NOT NULL,observed_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS history_lookup ON price_history(product_id,observed_at);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,user_id INTEGER NOT NULL REFERENCES users(id),status TEXT NOT NULL,payment_status TEXT NOT NULL,subtotal INTEGER NOT NULL,delivery INTEGER NOT NULL,discount INTEGER NOT NULL,total INTEGER NOT NULL,address TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY,order_id INTEGER NOT NULL REFERENCES orders(id),product_id INTEGER NOT NULL REFERENCES products(id),sku TEXT NOT NULL,name TEXT NOT NULL,variant TEXT NOT NULL,quantity INTEGER NOT NULL,unit_price INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),topic TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL);
        """)
        if ADMIN_EMAIL and ADMIN_PASSWORD and not c.execute("SELECT id FROM users WHERE email=?",(ADMIN_EMAIL,)).fetchone():
            c.execute("INSERT INTO users(email,name,password_hash,role,created_at) VALUES(?,?,?,?,?)",(ADMIN_EMAIL,"Super Bajaar Admin",pw_hash(ADMIN_PASSWORD),"admin",stamp()))

def token(u):
    import base64
    body=base64.urlsafe_b64encode(json.dumps({"sub":u["id"],"role":u["role"],"exp":int(time.time())+43200},separators=(",",":")).encode()).decode().rstrip("=")
    return body+"."+hmac.new(SECRET.encode(),body.encode(),hashlib.sha256).hexdigest()

def auth(authorization: str | None=Header(default=None)):
    if len(SECRET)<32: raise HTTPException(503,"Configure SB_SECRET_KEY (32+ characters)")
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Sign in required")
    try:
        import base64
        body,sig=authorization[7:].strip().split(".",1)
        if not hmac.compare_digest(sig,hmac.new(SECRET.encode(),body.encode(),hashlib.sha256).hexdigest()): raise ValueError()
        p=json.loads(base64.urlsafe_b64decode(body+"="*(-len(body)%4)))
        if p["exp"]<int(time.time()): raise ValueError()
        with connect() as c: u=c.execute("SELECT id,email,name,phone,role FROM users WHERE id=?",(p["sub"],)).fetchone()
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
class Stock(BaseModel):
    quantity:int=Field(ge=0)
class Address(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    phone:str=Field(pattern=r"^[0-9]{10}$")
    line:str=Field(min_length=5,max_length=300)
    city:str=Field(min_length=2,max_length=100)
    state:str=Field(min_length=2,max_length=100)
    pin:str=Field(pattern=r"^[0-9]{6}$")
class Line(BaseModel):
    product_id:int=Field(gt=0)
    variant:str=Field(default="",max_length=100)
    quantity:int=Field(gt=0,le=99)
class NewOrder(BaseModel):
    items:list[Line]=Field(min_length=1,max_length=100)
    address:Address
    coupon:str=Field(default="",max_length=40)
class Status(BaseModel):
    status:str=Field(pattern=r"^(placed|confirmed|packed|shipped|out_for_delivery|delivered|cancelled)$")
class Ticket(BaseModel):
    topic:str=Field(min_length=2,max_length=100)
    message:str=Field(min_length=5,max_length=4000)

@app.on_event("startup")
def startup(): setup()

@app.get("/api/health")
def health():
    with connect() as c: c.execute("SELECT 1")
    return {"status":"ok","database":"connected"}

@app.post("/api/auth/register",status_code=201)
def register(d:Register):
    if len(SECRET)<32: raise HTTPException(503,"Authentication is not configured")
    try:
        with connect() as c:
            cur=c.execute("INSERT INTO users(email,name,phone,password_hash,created_at) VALUES(?,?,?,?,?)",(str(d.email).lower(),d.name.strip(),d.phone,pw_hash(d.password),stamp()))
            u=c.execute("SELECT id,email,name,phone,role FROM users WHERE id=?",(cur.lastrowid,)).fetchone()
    except sqlite3.IntegrityError: raise HTTPException(409,"Email already registered")
    return {"token":token(u),"user":dict(u)}

@app.post("/api/auth/login")
def login(d:Login):
    if len(SECRET)<32: raise HTTPException(503,"Authentication is not configured")
    with connect() as c: u=c.execute("SELECT * FROM users WHERE email=?",(str(d.email).lower(),)).fetchone()
    if not u or not pw_ok(d.password,u["password_hash"]): raise HTTPException(401,"Email or password is incorrect")
    return {"token":token(u),"user":{k:u[k] for k in ("id","email","name","phone","role")}}

@app.get("/api/auth/me")
def me(u=Depends(auth)): return {"user":u}

def product_row(row):
    d=dict(row); d["variants"]=json.loads(d.pop("variants")); d["price"]=d.pop("price_paise")/100; d["mrp"]=d.pop("mrp_paise")/100; d["in_stock"]=d.get("quantity",0)>0; return d

@app.get("/api/products")
def products(q:str="",category:str="",limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    wh=["p.active=1"]; args=[]
    if q.strip(): wh.append("(p.name LIKE ? OR p.sku LIKE ? OR p.category LIKE ?)"); args.extend(["%"+q.strip()+"%"]*3)
    if category.strip(): wh.append("p.category=?"); args.append(category.strip())
    clause=" AND ".join(wh)
    with connect() as c:
        rows=c.execute("SELECT p.*,COALESCE(i.quantity,0) quantity FROM products p LEFT JOIN inventory i ON i.product_id=p.id WHERE "+clause+" ORDER BY p.id DESC LIMIT ? OFFSET ?",(*args,limit,offset)).fetchall()
        total=c.execute("SELECT COUNT(*) FROM products p WHERE "+clause,args).fetchone()[0]
    return {"items":[product_row(x) for x in rows],"total":total,"limit":limit,"offset":offset}

@app.post("/api/admin/products",status_code=201)
def create_product(d:Product,u=Depends(admin)):
    if d.mrp_paise<d.price_paise: raise HTTPException(422,"MRP cannot be lower than selling price")
    t=stamp()
    try:
        with connect() as c:
            cur=c.execute("INSERT INTO products(sku,name,category,description,image_url,price_paise,mrp_paise,variants,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(d.sku.strip(),d.name.strip(),d.category.strip(),d.description,d.image_url,d.price_paise,d.mrp_paise,json.dumps(d.variants),t,t)); pid=cur.lastrowid
            c.execute("INSERT INTO inventory VALUES(?,?,?)",(pid,d.quantity,t)); c.execute("INSERT INTO price_history(product_id,price_paise,observed_at) VALUES(?,?,?)",(pid,d.price_paise,t))
            row=c.execute("SELECT p.*,i.quantity FROM products p JOIN inventory i ON i.product_id=p.id WHERE p.id=?",(pid,)).fetchone()
    except sqlite3.IntegrityError: raise HTTPException(409,"SKU already exists")
    return product_row(row)

@app.patch("/api/admin/products/{pid}")
def update_product(pid:int,d:Product,u=Depends(admin)):
    if d.mrp_paise<d.price_paise: raise HTTPException(422,"MRP cannot be lower than selling price")
    t=stamp()
    try:
        with connect() as c:
            old=c.execute("SELECT price_paise FROM products WHERE id=? AND active=1",(pid,)).fetchone()
            if not old: raise HTTPException(404,"Product not found")
            c.execute("UPDATE products SET sku=?,name=?,category=?,description=?,image_url=?,price_paise=?,mrp_paise=?,variants=?,updated_at=? WHERE id=?",(d.sku.strip(),d.name.strip(),d.category.strip(),d.description,d.image_url,d.price_paise,d.mrp_paise,json.dumps(d.variants),t,pid))
            c.execute("INSERT INTO inventory VALUES(?,?,?) ON CONFLICT(product_id) DO UPDATE SET quantity=excluded.quantity,updated_at=excluded.updated_at",(pid,d.quantity,t))
            if old["price_paise"]!=d.price_paise: c.execute("INSERT INTO price_history(product_id,price_paise,observed_at) VALUES(?,?,?)",(pid,d.price_paise,t))
            row=c.execute("SELECT p.*,i.quantity FROM products p JOIN inventory i ON i.product_id=p.id WHERE p.id=?",(pid,)).fetchone()
    except sqlite3.IntegrityError: raise HTTPException(409,"SKU already exists")
    return product_row(row)

@app.patch("/api/admin/products/{pid}/stock")
def stock(pid:int,d:Stock,u=Depends(admin)):
    with connect() as c:
        if not c.execute("SELECT id FROM products WHERE id=? AND active=1",(pid,)).fetchone(): raise HTTPException(404,"Product not found")
        c.execute("INSERT INTO inventory VALUES(?,?,?) ON CONFLICT(product_id) DO UPDATE SET quantity=excluded.quantity,updated_at=excluded.updated_at",(pid,d.quantity,stamp()))
    return {"product_id":pid,"quantity":d.quantity}

@app.get("/api/products/{pid}/price-history")
def history(pid:int,days:int=Query(30,ge=1,le=365)):
    since=datetime.fromtimestamp(time.time()-days*86400,timezone.utc).isoformat()
    with connect() as c:
        if not c.execute("SELECT id FROM products WHERE id=? AND active=1",(pid,)).fetchone(): raise HTTPException(404,"Product not found")
        rows=c.execute("SELECT price_paise,observed_at FROM price_history WHERE product_id=? AND observed_at>=? ORDER BY observed_at",(pid,since)).fetchall()
    return {"product_id":pid,"days":days,"observations":[{"price":r["price_paise"]/100,"observed_at":r["observed_at"]} for r in rows],"note":"Only recorded observations are returned; history is never fabricated."}

@app.post("/api/orders",status_code=201)
def order(d:NewOrder,u=Depends(auth)):
    t=stamp()
    with connect() as c:
        subtotal=0; lines=[]
        for item in d.items:
            p=c.execute("SELECT p.id,p.sku,p.name,p.price_paise,COALESCE(i.quantity,0) quantity FROM products p LEFT JOIN inventory i ON i.product_id=p.id WHERE p.id=? AND p.active=1",(item.product_id,)).fetchone()
            if not p: raise HTTPException(404,"Product unavailable")
            if p["quantity"]<item.quantity: raise HTTPException(409,"Insufficient stock for "+p["name"])
            subtotal+=p["price_paise"]*item.quantity; lines.append((p,item))
        discount=min(round(subtotal*.1),30000) if d.coupon.strip().upper()=="WELCOME10" else 0
        delivery=0 if subtotal>=79900 else 4900; total=max(0,subtotal-discount+delivery); code="SB"+secrets.token_hex(5).upper()
        cur=c.execute("INSERT INTO orders(code,user_id,status,payment_status,subtotal,delivery,discount,total,address,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(code,u["id"],"placed","pending",subtotal,delivery,discount,total,d.address.model_dump_json(),t,t))
        for p,item in lines:
            changed=c.execute("UPDATE inventory SET quantity=quantity-?,updated_at=? WHERE product_id=? AND quantity>=?",(item.quantity,t,p["id"],item.quantity)).rowcount
            if changed!=1: raise HTTPException(409,"Stock changed; retry checkout")
            c.execute("INSERT INTO order_items(order_id,product_id,sku,name,variant,quantity,unit_price) VALUES(?,?,?,?,?,?,?)",(cur.lastrowid,p["id"],p["sku"],p["name"],item.variant,item.quantity,p["price_paise"]))
    return {"id":code,"status":"placed","payment_status":"pending","subtotal":subtotal/100,"delivery":delivery/100,"discount":discount/100,"total":total/100,"created_at":t}

@app.get("/api/orders")
def my_orders(u=Depends(auth)):
    with connect() as c:
        orders=c.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC",(u["id"],)).fetchall(); result=[]
        for o in orders:
            items=c.execute("SELECT product_id,sku,name,variant,quantity,unit_price FROM order_items WHERE order_id=?",(o["id"],)).fetchall()
            result.append({"id":o["code"],"status":o["status"],"payment_status":o["payment_status"],"subtotal":o["subtotal"]/100,"delivery":o["delivery"]/100,"discount":o["discount"]/100,"total":o["total"]/100,"address":json.loads(o["address"]),"created_at":o["created_at"],"items":[{"product_id":i["product_id"],"sku":i["sku"],"name":i["name"],"variant":i["variant"],"quantity":i["quantity"],"price":i["unit_price"]/100} for i in items]})
    return {"items":result}

@app.get("/api/admin/orders")
def admin_orders(u=Depends(admin)):
    with connect() as c: rows=c.execute("SELECT o.code,o.status,o.payment_status,o.total,o.created_at,u.email,u.name FROM orders o JOIN users u ON u.id=o.user_id ORDER BY o.id DESC").fetchall()
    return {"items":[{**dict(x),"total":x["total"]/100} for x in rows]}

@app.patch("/api/admin/orders/{code}/status")
def status(code:str,d:Status,u=Depends(admin)):
    with connect() as c:
        row=c.execute("SELECT id,status FROM orders WHERE code=?",(code,)).fetchone()
        if not row: raise HTTPException(404,"Order not found")
        if row["status"] in ("delivered","cancelled") and d.status!=row["status"]: raise HTTPException(409,"Final order status cannot be changed")
        c.execute("UPDATE orders SET status=?,updated_at=? WHERE id=?",(d.status,stamp(),row["id"]))
    return {"id":code,"status":d.status}

@app.post("/api/support",status_code=201)
def support(d:Ticket,u=Depends(auth)):
    with connect() as c: cur=c.execute("INSERT INTO tickets(user_id,topic,message,created_at) VALUES(?,?,?,?)",(u["id"],d.topic.strip(),d.message.strip(),stamp()))
    return {"id":cur.lastrowid,"status":"open"}

@app.get("/api/admin/support")
def support_queue(u=Depends(admin)):
    with connect() as c: rows=c.execute("SELECT t.id,t.topic,t.message,t.status,t.created_at,u.email FROM tickets t JOIN users u ON u.id=t.user_id ORDER BY t.id DESC").fetchall()
    return {"items":[dict(x) for x in rows]}
