"""Provider-backed travel booking and ledger-backed advance disbursement."""
from __future__ import annotations
import os
from datetime import date
from decimal import Decimal
import httpx
from fastapi import HTTPException
from app.api.accounting import _accounts_by_code, _post_voucher

class TravelIntegrationConfigurationError(RuntimeError): pass

def create_provider_booking(*,travel:dict,booking:dict,record_id:int)->dict:
    base=os.getenv("SB_TRAVEL_BOOKING_API_URL","").strip().rstrip("/")
    token=os.getenv("SB_TRAVEL_BOOKING_API_TOKEN","").strip()
    provider=os.getenv("SB_TRAVEL_BOOKING_PROVIDER","").strip()
    if not base or not token or not provider:
        raise TravelIntegrationConfigurationError(
            "Travel booking integration is not configured; set SB_TRAVEL_BOOKING_API_URL, SB_TRAVEL_BOOKING_API_TOKEN and SB_TRAVEL_BOOKING_PROVIDER"
        )
    body={
        "external_reference":str(booking.get("client_reference") or f"superbajaar-hr-travel-{record_id}"),
        "destination":travel.get("destination"),
        "purpose":travel.get("purpose"),
        "start_date":travel.get("start_date"),
        "end_date":travel.get("end_date"),
        "traveller_reference":str(travel.get("employee_id") or ""),
        "quoted_amount":str(booking.get("booked_cost")),
        "maximum_allowed_amount":str(booking.get("maximum_allowed_amount") or booking.get("booked_cost")),
        "currency":str(booking.get("currency") or travel.get("currency") or "INR").upper(),
        "booking_details":booking.get("booking_details") or {},
    }
    try:
        response=httpx.post(
            f"{base}/bookings",json=body,
            headers={"Authorization":f"Bearer {token}","Idempotency-Key":body["external_reference"]},
            timeout=httpx.Timeout(20.0,connect=5.0),
        )
        response.raise_for_status()
        result=response.json()
    except (httpx.HTTPError,ValueError) as exc:
        raise HTTPException(502,"Configured travel booking provider did not confirm the booking") from exc
    reference=str(result.get("booking_reference") or result.get("id") or "").strip()
    if not reference:
        raise HTTPException(502,"Travel booking provider response did not contain a booking reference")
    try: confirmed=Decimal(str(result.get("confirmed_amount",booking["booked_cost"])))
    except Exception as exc: raise HTTPException(502,"Travel booking provider returned an invalid confirmed amount") from exc
    if confirmed<=0: raise HTTPException(502,"Travel booking provider returned a non-positive booking amount")
    return {"provider":provider,"booking_reference":reference,"provider_booking_id":str(result.get("id") or reference),
            "booked_cost":str(confirmed),"provider_status":str(result.get("status") or "confirmed")}

def disburse_travel_advance(conn,*,record_id:int,employee_id:int,amount:Decimal,currency:str,actor_user_id:int|None)->int:
    if currency.upper()!="INR":
        raise HTTPException(422,"Travel advance ledger posting currently supports INR only")
    advance_code=os.getenv("SB_TRAVEL_ADVANCE_ACCOUNT_CODE","").strip()
    bank_code=os.getenv("SB_TRAVEL_BANK_ACCOUNT_CODE","").strip()
    if not advance_code or not bank_code:
        raise TravelIntegrationConfigurationError(
            "Travel advance accounting is not configured; set SB_TRAVEL_ADVANCE_ACCOUNT_CODE and SB_TRAVEL_BANK_ACCOUNT_CODE"
        )
    accounts=_accounts_by_code(conn,[advance_code,bank_code])
    if set(accounts)!={advance_code,bank_code}:
        raise HTTPException(503,"Configured travel advance or bank ledger account code does not exist")
    if accounts[advance_code]["account_type"]!="asset" or accounts[bank_code]["account_type"]!="asset":
        raise HTTPException(422,"Travel advance and bank ledger accounts must both be asset accounts")
    if accounts[bank_code]["sub_type"] not in {"bank","cash"}:
        raise HTTPException(422,"Travel disbursement credit account must be a cash or bank account")
    voucher_id=_post_voucher(conn,{
        "voucher_type":"payment","voucher_date":date.today(),
        "narration":f"Employee travel advance disbursement #{record_id}",
        "reference":f"HR-TRAVEL-ADV-{record_id}","party_type":"employee",
        "party_name":f"Employee #{employee_id}","due_date":None,
        "idempotency_key":f"hr-travel-advance-{record_id}",
    },[
        {"account_id":accounts[advance_code]["id"],"debit":amount,"credit":Decimal("0"),"description":"Employee travel advance"},
        {"account_id":accounts[bank_code]["id"],"debit":Decimal("0"),"credit":amount,"description":"Travel advance bank disbursement"},
    ],(actor_user_id,None))
    return voucher_id
