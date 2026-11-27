"""POS register and cash-drawer workflows.

Each physical counter owns one register and may have only one open shift.
Cash movements and close snapshots are append-only/auditable records.
"""
from decimal import Decimal
import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

router = APIRouter(prefix="/pos", tags=["pos-registers"])


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="POS database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="POS database is unavailable") from exc


def _actor(request: Request) -> int:
    actor = getattr(request.state, "user_id", None)
    if not actor:
        raise HTTPException(status_code=403, detail="An authenticated staff account is required")
    return int(actor)


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


class RegisterCreate(BaseModel):
    location_id: int = Field(gt=0)
    register_code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=120)

    @field_validator("register_code", "name")
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class ShiftOpen(BaseModel):
    cashier_user_id: int | None = Field(default=None, gt=0)
    opening_float: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class CashMovement(BaseModel):
    movement_type: str
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)
    reference: str | None = Field(default=None, max_length=120)

    @field_validator("movement_type")
    @classmethod
    def valid_type(cls, value):
        if value not in {"cash_in", "cash_out"}:
            raise ValueError("Movement type must be cash_in or cash_out")
        return value

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A reason of at least three characters is required")
        return value


class ShiftClose(BaseModel):
    counted_cash: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    closing_note: str | None = Field(default=None, max_length=1000)


@router.get("/registers")
def list_registers(location_id: int | None = None):
    try:
        with _connect() as conn:
            rows = conn.execute(
                """SELECT r.id,r.location_id,l.name AS location_name,r.register_code,r.name,r.is_active,
                          s.id AS open_shift_id,s.cashier_user_id,s.opened_at,s.opening_float
                   FROM pos_registers r JOIN stock_locations l ON l.id=r.location_id
                   LEFT JOIN pos_register_shifts s ON s.register_id=r.id AND s.status='open'
                   WHERE (%s::bigint IS NULL OR r.location_id=%s) AND r.is_active=TRUE
                   ORDER BY l.name,r.register_code""",
                (location_id, location_id),
            ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="POS registers are unavailable") from exc


@router.post("/registers", status_code=201)
def create_register(payload: RegisterCreate, request: Request):
    actor = _actor(request)
    if getattr(request.state, "role", "") not in {"manager", "admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Register setup is restricted to managers")
    try:
        with _connect() as conn:
            row = conn.execute(
                """INSERT INTO pos_registers(location_id,register_code,name,created_by)
                   VALUES(%s,%s,%s,%s)
                   RETURNING id,location_id,register_code,name,is_active,created_at""",
                (payload.location_id, payload.register_code.upper(), payload.name, actor),
            ).fetchone()
            conn.execute(
                "INSERT INTO pos_register_audit(register_id,event_type,actor_user_id,event_data) VALUES(%s,'register_created',%s,%s)",
                (row["id"], actor, Jsonb({"register_code": row["register_code"], "location_id": payload.location_id})),
            )
        return row
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="That register code already exists at this store") from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(status_code=422, detail="Selected store/location does not exist") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Register could not be saved") from exc



@router.get("/registers/{register_id}/shifts")
def shift_history(register_id: int, request: Request, limit: int = 50):
    actor = _actor(request)
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 200")
    try:
        with _connect() as conn:
            register = conn.execute("SELECT id FROM pos_registers WHERE id=%s", (register_id,)).fetchone()
            if register is None:
                raise HTTPException(status_code=404, detail="Register not found")
            role = getattr(request.state, "role", "")
            if role not in {"manager","admin","super_admin"}:
                rows = conn.execute(
                    """SELECT id,register_id,cashier_user_id,opened_by,opening_float,opened_at,status,
                              expected_cash,counted_cash,cash_variance,closing_note,closed_by,closed_at
                       FROM pos_register_shifts WHERE register_id=%s AND cashier_user_id=%s
                       ORDER BY opened_at DESC LIMIT %s""",
                    (register_id,actor,limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id,register_id,cashier_user_id,opened_by,opening_float,opened_at,status,
                              expected_cash,counted_cash,cash_variance,closing_note,closed_by,closed_at
                       FROM pos_register_shifts WHERE register_id=%s
                       ORDER BY opened_at DESC LIMIT %s""",
                    (register_id,limit),
                ).fetchall()
        return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Shift history is unavailable") from exc


@router.get("/registers/{register_id}/shift")
def current_shift(register_id: int, request: Request):
    try:
        with _connect() as conn:
            row = conn.execute(
                """SELECT s.*,r.register_code,r.name AS register_name,r.location_id
                   FROM pos_register_shifts s JOIN pos_registers r ON r.id=s.register_id
                   WHERE s.register_id=%s AND s.status='open'""",
                (register_id,),
            ).fetchone()
            if row is None:
                return {"shift": None}
            actor = _actor(request)
            if int(row["cashier_user_id"]) != actor and getattr(request.state, "role", "") not in {"manager","admin","super_admin"}:
                raise HTTPException(status_code=403, detail="Only the assigned cashier or a manager can view this shift")
            totals = _shift_cash_totals(conn, int(row["id"]))
            movements = conn.execute(
                "SELECT id,movement_type,amount,reason,reference,created_by,created_at FROM pos_cash_movements WHERE shift_id=%s ORDER BY created_at DESC,id DESC",
                (row["id"],),
            ).fetchall()
        return {"shift": row, "cash": totals, "movements": movements}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Shift details are unavailable") from exc


def _expected_cash(opening_float, totals):
    return _money(
        Decimal(str(opening_float)) + Decimal(str(totals["cash_sales"]))
        - Decimal(str(totals["cash_refunds"])) + Decimal(str(totals["cash_in"]))
        - Decimal(str(totals["cash_out"]))
    )


def _shift_cash_totals(conn, shift_id: int):
    row = conn.execute(
        """SELECT
             COALESCE(sum(p.amount) FILTER (WHERE p.status='captured' AND p.method='cod'),0) AS cash_sales,
             COALESCE(sum(p.amount) FILTER (WHERE p.status='refunded' AND p.method='cod'),0) AS cash_refunds
           FROM payments p JOIN orders o ON o.id=p.order_id
           WHERE o.pos_register_shift_id=%s""",
        (shift_id,),
    ).fetchone()
    movement = conn.execute(
        """SELECT COALESCE(sum(amount) FILTER (WHERE movement_type='cash_in'),0) AS cash_in,
                  COALESCE(sum(amount) FILTER (WHERE movement_type='cash_out'),0) AS cash_out
           FROM pos_cash_movements WHERE shift_id=%s""",
        (shift_id,),
    ).fetchone()
    return {
        "cash_sales": row["cash_sales"],
        "cash_refunds": row["cash_refunds"],
        "cash_in": movement["cash_in"],
        "cash_out": movement["cash_out"],
    }


@router.post("/registers/{register_id}/open", status_code=201)
def open_shift(register_id: int, payload: ShiftOpen, request: Request):
    actor = _actor(request)
    cashier = payload.cashier_user_id or actor
    if cashier != actor and getattr(request.state, "role", "") not in {"manager", "admin", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only a manager can open a shift for another cashier")
    try:
        with _connect() as conn:
            with conn.transaction():
                register = conn.execute(
                    "SELECT id FROM pos_registers WHERE id=%s AND is_active=TRUE FOR UPDATE",
                    (register_id,),
                ).fetchone()
                if register is None:
                    raise HTTPException(status_code=404, detail="Active register not found")
                row = conn.execute(
                    """INSERT INTO pos_register_shifts(register_id,cashier_user_id,opened_by,opening_float)
                       VALUES(%s,%s,%s,%s)
                       RETURNING id,register_id,cashier_user_id,opened_by,opening_float,opened_at,status""",
                    (register_id, cashier, actor, _money(payload.opening_float)),
                ).fetchone()
                conn.execute(
                    "INSERT INTO pos_register_audit(register_id,shift_id,event_type,actor_user_id,event_data) VALUES(%s,%s,'shift_opened',%s,%s)",
                    (register_id, row["id"], actor, Jsonb({"cashier_user_id": cashier, "opening_float": str(row["opening_float"])})),
                )
        return row
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="This register already has an open cashier shift") from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(status_code=422, detail="Cashier account does not exist") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not open register shift") from exc


@router.post("/shifts/{shift_id}/cash-movements", status_code=201)
def add_cash_movement(shift_id: int, payload: CashMovement, request: Request):
    actor = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                shift = conn.execute(
                    "SELECT id,register_id,cashier_user_id FROM pos_register_shifts WHERE id=%s AND status='open' FOR UPDATE",
                    (shift_id,),
                ).fetchone()
                if shift is None:
                    raise HTTPException(status_code=409, detail="Cash movements require an open shift")
                if int(shift["cashier_user_id"]) != actor and getattr(request.state, "role", "") not in {"manager","admin","super_admin"}:
                    raise HTTPException(status_code=403, detail="Only the assigned cashier or a manager can record drawer movements")
                row = conn.execute(
                    """INSERT INTO pos_cash_movements(shift_id,movement_type,amount,reason,reference,created_by)
                       VALUES(%s,%s,%s,%s,%s,%s)
                       RETURNING id,shift_id,movement_type,amount,reason,reference,created_at""",
                    (shift_id,payload.movement_type,_money(payload.amount),payload.reason,payload.reference,actor),
                ).fetchone()
                conn.execute(
                    "INSERT INTO pos_register_audit(register_id,shift_id,event_type,actor_user_id,event_data) VALUES(%s,%s,'cash_movement',%s,%s)",
                    (shift["register_id"],shift_id,actor,Jsonb({"movement_type": payload.movement_type,"amount": str(row["amount"]),"reason": payload.reason})),
                )
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Cash movement could not be recorded") from exc



@router.post("/shifts/{shift_id}/payments/{payment_id}/confirm-cash")
def confirm_cash_payment(shift_id: int, payment_id: int, request: Request):
    """Capture a physical cash tender only from the cashier shift that owns the sale."""
    actor = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                shift = conn.execute(
                    "SELECT id,register_id,cashier_user_id FROM pos_register_shifts WHERE id=%s AND status='open' FOR UPDATE",
                    (shift_id,),
                ).fetchone()
                if shift is None:
                    raise HTTPException(status_code=409, detail="Cash confirmation requires an open shift")
                if int(shift["cashier_user_id"]) != actor and getattr(request.state, "role", "") not in {"manager","admin","super_admin"}:
                    raise HTTPException(status_code=403, detail="Only the assigned cashier or a manager can confirm this cash tender")
                payment = conn.execute(
                    """SELECT p.id,p.payment_reference,p.method,p.amount,p.status,o.id AS order_id,o.order_number,o.status AS order_status
                       FROM payments p JOIN orders o ON o.id=p.order_id
                       WHERE p.id=%s AND o.channel='pos' AND o.pos_register_shift_id=%s
                       FOR UPDATE OF p,o""",
                    (payment_id,shift_id),
                ).fetchone()
                if payment is None:
                    raise HTTPException(status_code=404, detail="Cash tender does not belong to this register shift")
                if payment["order_status"] == "cancelled":
                    raise HTTPException(status_code=409, detail="A cancelled POS order cannot receive a cash confirmation")
                if payment["method"] != "cod":
                    raise HTTPException(status_code=422, detail="Only physical cash tenders can be confirmed here")
                if payment["status"] != "pending":
                    raise HTTPException(status_code=409, detail="Cash tender is not pending confirmation")
                updated = conn.execute(
                    "UPDATE payments SET status='captured',note='Physical cash received and confirmed by POS cashier',updated_at=now() WHERE id=%s AND status='pending' RETURNING id,payment_reference,method,amount,status,updated_at",
                    (payment_id,),
                ).fetchone()
                conn.execute(
                    "INSERT INTO pos_register_audit(register_id,shift_id,event_type,actor_user_id,event_data) VALUES(%s,%s,'cash_tender_confirmed',%s,%s)",
                    (shift["register_id"],shift_id,actor,Jsonb({"payment_id":payment_id,"order_number":payment["order_number"],"amount":str(payment["amount"])})),
                )
        return updated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Cash tender could not be confirmed") from exc


@router.post("/shifts/{shift_id}/close")
def close_shift(shift_id: int, payload: ShiftClose, request: Request):
    actor = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                shift = conn.execute(
                    "SELECT * FROM pos_register_shifts WHERE id=%s AND status='open' FOR UPDATE",
                    (shift_id,),
                ).fetchone()
                if shift is None:
                    raise HTTPException(status_code=409, detail="Shift is already closed or does not exist")
                if int(shift["cashier_user_id"]) != actor and getattr(request.state, "role", "") not in {"manager","admin","super_admin"}:
                    raise HTTPException(status_code=403, detail="Only the assigned cashier or a manager can close this shift")
                totals = _shift_cash_totals(conn, shift_id)
                expected = _expected_cash(shift["opening_float"], totals)
                counted = _money(payload.counted_cash)
                variance = _money(counted - expected)
                row = conn.execute(
                    """UPDATE pos_register_shifts
                       SET status='closed',expected_cash=%s,counted_cash=%s,cash_variance=%s,
                           closing_note=%s,closed_by=%s,closed_at=now()
                       WHERE id=%s
                       RETURNING id,register_id,cashier_user_id,status,opening_float,expected_cash,
                                 counted_cash,cash_variance,closing_note,opened_at,closed_at""",
                    (expected,counted,variance,payload.closing_note,actor,shift_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO pos_register_audit(register_id,shift_id,event_type,actor_user_id,event_data) VALUES(%s,%s,'shift_closed',%s,%s)",
                    (shift["register_id"],shift_id,actor,Jsonb({"expected_cash":str(expected),"counted_cash":str(counted),"variance":str(variance)})),
                )
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Shift could not be closed") from exc
