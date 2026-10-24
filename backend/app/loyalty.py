"""Configurable Super Bajaar Super Coin loyalty engine."""
import json
from decimal import Decimal, ROUND_DOWN
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from .auth import _current, _require, _db

router = APIRouter(prefix="/api/loyalty", tags=["loyalty"])


def _ensure(conn: Any) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_loyalty_program (
        id SMALLINT PRIMARY KEY DEFAULT 1 CHECK(id=1),
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        program_name TEXT NOT NULL DEFAULT 'Super Coins',
        coin_name TEXT NOT NULL DEFAULT 'Super Coin',
        earn_rate NUMERIC(10,4) NOT NULL DEFAULT 1 CHECK(earn_rate>=0),
        earn_basis TEXT NOT NULL DEFAULT 'subtotal' CHECK(earn_basis IN ('subtotal','total')),
        redemption_value NUMERIC(10,4) NOT NULL DEFAULT 1 CHECK(redemption_value>0),
        max_redemption_percent NUMERIC(5,2) NOT NULL DEFAULT 50 CHECK(max_redemption_percent>=0 AND max_redemption_percent<=100),
        min_redeem_coins INTEGER NOT NULL DEFAULT 100 CHECK(min_redeem_coins>=0),
        welcome_coins INTEGER NOT NULL DEFAULT 0 CHECK(welcome_coins>=0),
        referral_coins INTEGER NOT NULL DEFAULT 0 CHECK(referral_coins>=0),
        expiry_days INTEGER CHECK(expiry_days IS NULL OR expiry_days>=0),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_by BIGINT)""")
    conn.execute("INSERT INTO sb_loyalty_program(id) VALUES(1) ON CONFLICT(id) DO NOTHING")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_loyalty_wallets (
        user_id BIGINT PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
        balance BIGINT NOT NULL DEFAULT 0 CHECK(balance>=0), lifetime_earned BIGINT NOT NULL DEFAULT 0 CHECK(lifetime_earned>=0),
        lifetime_redeemed BIGINT NOT NULL DEFAULT 0 CHECK(lifetime_redeemed>=0), tier TEXT NOT NULL DEFAULT 'Member',
        card_number TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_loyalty_transactions (
        id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('earn','redeem','welcome','referral','admin_adjustment','expiry','refund')),
        coins BIGINT NOT NULL CHECK(coins>0), balance_after BIGINT NOT NULL CHECK(balance_after>=0),
        order_id BIGINT, description TEXT NOT NULL, expires_at TIMESTAMPTZ,
        idempotency_key TEXT UNIQUE, created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_loyalty_tiers (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, min_lifetime_earned BIGINT NOT NULL DEFAULT 0 CHECK(min_lifetime_earned>=0),
        earn_multiplier NUMERIC(6,3) NOT NULL DEFAULT 1 CHECK(earn_multiplier>=0), benefits JSONB NOT NULL DEFAULT '[]'::jsonb,
        is_active BOOLEAN NOT NULL DEFAULT TRUE, sort_order INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""INSERT INTO sb_loyalty_tiers(name,min_lifetime_earned,earn_multiplier,benefits,sort_order)
        VALUES('Member',0,1,'["Earn Super Coins on eligible orders"]'::jsonb,0),
              ('Plus',5000,1.25,'["Bonus coin earning"]'::jsonb,1),
              ('VIP',20000,1.5,'["Higher coin earning"]'::jsonb,2)
        ON CONFLICT(name) DO NOTHING""")


def _program(conn: Any) -> dict[str, Any]:
    return conn.execute("SELECT * FROM sb_loyalty_program WHERE id=1").fetchone()


def _wallet(conn: Any, user_id: int) -> dict[str, Any]:
    row=conn.execute("SELECT * FROM sb_loyalty_wallets WHERE user_id=%s FOR UPDATE",(user_id,)).fetchone()
    if row:
        return row
    card="SB-"+__import__("secrets").token_hex(6).upper()
    try:
        return conn.execute("""INSERT INTO sb_loyalty_wallets(user_id,card_number) VALUES(%s,%s)
            ON CONFLICT(user_id) DO UPDATE SET user_id=EXCLUDED.user_id RETURNING *""",(user_id,card)).fetchone()
    except psycopg.errors.UniqueViolation:
        card="SB-"+__import__("secrets").token_hex(8).upper()
        return conn.execute("INSERT INTO sb_loyalty_wallets(user_id,card_number) VALUES(%s,%s) RETURNING *",(user_id,card)).fetchone()


def _tier(conn: Any, lifetime: int) -> dict[str, Any]:
    row=conn.execute("""SELECT * FROM sb_loyalty_tiers WHERE is_active AND min_lifetime_earned<=%s
        ORDER BY min_lifetime_earned DESC,sort_order DESC LIMIT 1""",(lifetime,)).fetchone()
    return row or {"name":"Member","earn_multiplier":Decimal("1"),"benefits":[]}


def _post(conn: Any, user_id: int, kind: str, coins: int, description: str, *,
          order_id: int | None = None, key: str | None = None, expires_at: Any = None, created_by: int | None = None) -> dict[str, Any]:
    if coins <= 0:
        raise HTTPException(status_code=422, detail="Coin amount must be greater than zero")
    if key:
        old=conn.execute("SELECT * FROM sb_loyalty_transactions WHERE idempotency_key=%s",(key,)).fetchone()
        if old:
            wallet=conn.execute("SELECT * FROM sb_loyalty_wallets WHERE user_id=%s",(user_id,)).fetchone()
            return {"transaction":old,"wallet":wallet,"duplicate":True}
    wallet=_wallet(conn,user_id)
    signed=coins if kind in ("earn","welcome","referral","admin_adjustment") and not description.startswith("DEBIT:") else -coins
    if signed<0 and wallet["balance"]<coins:
        raise HTTPException(status_code=422,detail="Not enough Super Coins in your wallet")
    new_balance=int(wallet["balance"])+signed
    earned=int(wallet["lifetime_earned"])+(coins if signed>0 else 0)
    redeemed=int(wallet["lifetime_redeemed"])+(coins if signed<0 else 0)
    tier=_tier(conn,earned)
    conn.execute("""UPDATE sb_loyalty_wallets SET balance=%s,lifetime_earned=%s,lifetime_redeemed=%s,tier=%s,updated_at=now()
        WHERE user_id=%s""",(new_balance,earned,redeemed,tier["name"],user_id))
    tx=conn.execute("""INSERT INTO sb_loyalty_transactions(user_id,kind,coins,balance_after,order_id,description,expires_at,idempotency_key,created_by)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (user_id,kind,coins,new_balance,order_id,description.replace("DEBIT:","",1),expires_at,key,created_by)).fetchone()
    return {"transaction":tx,"wallet":conn.execute("SELECT * FROM sb_loyalty_wallets WHERE user_id=%s",(user_id,)).fetchone(),"duplicate":False}


def award_order_coins(conn: Any, user_id: int, order_id: int, subtotal: Decimal, total: Decimal) -> dict[str, Any] | None:
    _ensure(conn)
    program=_program(conn)
    if not program["enabled"] or Decimal(str(program["earn_rate"]))<=0:
        return None
    basis=total if program["earn_basis"]=="total" else subtotal
    wallet=_wallet(conn,user_id)
    tier=_tier(conn,int(wallet["lifetime_earned"]))
    raw=basis*Decimal(str(program["earn_rate"]))*Decimal(str(tier["earn_multiplier"]))
    coins=int(raw.quantize(Decimal("1"),rounding=ROUND_DOWN))
    if coins<=0:
        return None
    expiry=None
    if program["expiry_days"] is not None:
        from datetime import timedelta
        expiry=conn.execute("SELECT now() + (%s * interval '1 day') AS value",(program["expiry_days"],)).fetchone()["value"]
    return _post(conn,user_id,"earn",coins,f"Super Coins earned for order #{order_id}",order_id=order_id,
                 key=f"order:{order_id}:earn",expires_at=expiry)


class ProgramInput(BaseModel):
    enabled: bool = True
    program_name: str = Field(default="Super Coins", min_length=2, max_length=100)
    coin_name: str = Field(default="Super Coin", min_length=2, max_length=40)
    earn_rate: Decimal = Field(default=Decimal("1"), ge=0, le=1000)
    earn_basis: str = Field(default="subtotal", pattern="^(subtotal|total)$")
    redemption_value: Decimal = Field(default=Decimal("1"), gt=0, le=1000)
    max_redemption_percent: Decimal = Field(default=Decimal("50"), ge=0, le=100)
    min_redeem_coins: int = Field(default=100, ge=0, le=100000000)
    welcome_coins: int = Field(default=0, ge=0, le=1000000)
    referral_coins: int = Field(default=0, ge=0, le=1000000)
    expiry_days: int | None = Field(default=None, ge=0, le=3650)


class AdjustmentInput(BaseModel):
    user_id: int = Field(gt=0)
    coins: int = Field(gt=0, le=1000000)
    direction: str = Field(pattern="^(credit|debit)$")
    reason: str = Field(min_length=3, max_length=300)


@router.get("/me")
def my_wallet(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user=_current(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                wallet=_wallet(conn,int(user["id"]))
                program=_program(conn)
                tier=_tier(conn,int(wallet["lifetime_earned"]))
                transactions=conn.execute("""SELECT id,kind,coins,balance_after,order_id,description,expires_at,created_at
                    FROM sb_loyalty_transactions WHERE user_id=%s ORDER BY created_at DESC,id DESC LIMIT 100""",(user["id"],)).fetchall()
                return {"program":program,"wallet":wallet,"tier":tier,"transactions":transactions,
                        "redemption_value_per_coin":program["redemption_value"],"min_redeem_coins":program["min_redeem_coins"] }
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Loyalty wallet is temporarily unavailable") from exc


@router.get("/program")
def get_program(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require(authorization,{"super_admin","admin"})
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"program":_program(conn),"tiers":conn.execute("SELECT * FROM sb_loyalty_tiers ORDER BY sort_order,id").fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Loyalty programme settings unavailable") from exc


@router.put("/program")
def update_program(body: ProgramInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user=_require(authorization,{"super_admin","admin"})
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            row=conn.execute("""UPDATE sb_loyalty_program SET enabled=%s,program_name=%s,coin_name=%s,earn_rate=%s,
                earn_basis=%s,redemption_value=%s,max_redemption_percent=%s,min_redeem_coins=%s,welcome_coins=%s,
                referral_coins=%s,expiry_days=%s,updated_at=now(),updated_by=%s WHERE id=1 RETURNING *""",
                (body.enabled,body.program_name,body.coin_name,body.earn_rate,body.earn_basis,body.redemption_value,
                 body.max_redemption_percent,body.min_redeem_coins,body.welcome_coins,body.referral_coins,body.expiry_days,user["id"])).fetchone()
            return {"program":row}
    except Exception as exc: raise HTTPException(status_code=503,detail="Loyalty programme settings could not be saved") from exc


@router.post("/adjust")
def adjust_wallet(body: AdjustmentInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user=_require(authorization,{"super_admin","admin"})
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                kind="admin_adjustment"
                description=("DEBIT:" if body.direction=="debit" else "")+"Admin adjustment: "+body.reason
                result=_post(conn,body.user_id,kind,body.coins,description,key=f"admin:{user['id']}:{__import__('secrets').token_hex(12)}",created_by=int(user["id"]))
                return result
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Loyalty adjustment failed") from exc


@router.post("/redeem")
def redeem_coins(coins: int = Field(gt=0), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user=_current(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                program=_program(conn)
                if not program["enabled"]: raise HTTPException(status_code=409,detail="Loyalty programme is currently disabled")
                wallet=_wallet(conn,int(user["id"]))
                if coins<int(program["min_redeem_coins"]): raise HTTPException(status_code=422,detail=f"Minimum redemption is {program['min_redeem_coins']} coins")
                value=(Decimal(coins)*Decimal(str(program["redemption_value"]))).quantize(Decimal("0.01"))
                result=_post(conn,int(user["id"]),"redeem",coins,f"Coins redeemed for {value} store credit",key=f"redeem:{user['id']}:{__import__('secrets').token_hex(12)}")
                return {**result,"store_credit":value,"message":"Coins redeemed. Store credit is recorded in your loyalty wallet."}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Coin redemption failed") from exc
