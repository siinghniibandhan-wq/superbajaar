"""Shared, authenticated business settings for Super Bajaar."""
import re
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.v1.auth import current_user
from app.core.config import settings

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULT_SETTINGS = {
    "businessName": "Super Bajaar",
    "legalName": "",
    "gstin": "",
    "supportEmail": "",
    "supportPhone": "",
    "currency": "INR",
    "timezone": "Asia/Kolkata",
    "taxMode": "exclusive",
    "defaultGstRate": "18",
    "lowStockThreshold": "5",
    "allowBackorders": False,
    "requireOrderReview": True,
    "deliveryMode": "serviceable-pincode",
    "estimatedDeliveryDays": "2-5",
    "orderEmailAlerts": True,
    "stockAlerts": True,
    "paymentAlerts": True,
    "marketingEmails": False,
    "theme": "system",
}


class BusinessSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    businessName: str = Field(default="Super Bajaar", min_length=1, max_length=120)
    legalName: str = Field(default="", max_length=160)
    gstin: str = Field(default="", max_length=15)
    supportEmail: str = Field(default="", max_length=254)
    supportPhone: str = Field(default="", max_length=20)
    currency: Literal["INR"] = "INR"
    timezone: Literal["Asia/Kolkata", "UTC"] = "Asia/Kolkata"
    taxMode: Literal["exclusive", "inclusive"] = "exclusive"
    defaultGstRate: str = Field(default="18", pattern=r"^(?:100(?:\.0{1,2})?|\d{1,2}(?:\.\d{1,2})?)$")
    lowStockThreshold: str = Field(default="5", pattern=r"^\d{1,7}$")
    allowBackorders: bool = False
    requireOrderReview: bool = True
    deliveryMode: Literal["serviceable-pincode", "manual"] = "serviceable-pincode"
    estimatedDeliveryDays: str = Field(default="2-5", max_length=40)
    orderEmailAlerts: bool = True
    stockAlerts: bool = True
    paymentAlerts: bool = True
    marketingEmails: bool = False
    theme: Literal["system", "light", "dark"] = "system"

    @field_validator("businessName", "legalName", "supportEmail", "supportPhone", "estimatedDeliveryDays")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value: str) -> str:
        value = value.strip().upper()
        if value and not re.fullmatch(r"[0-9A-Z]{15}", value):
            raise ValueError("GSTIN must contain 15 letters/numbers")
        return value

    @field_validator("supportEmail")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if value and (value.count("@") != 1 or "." not in value.rsplit("@", 1)[-1] or " " in value):
            raise ValueError("Enter a valid support email")
        return value

    @field_validator("defaultGstRate")
    @classmethod
    def validate_gst_rate(cls, value: str) -> str:
        if not 0 <= float(value) <= 100:
            raise ValueError("Default GST rate must be between 0 and 100")
        return str(float(value)).rstrip("0").rstrip(".") if "." in str(float(value)) else str(int(float(value)))

    @field_validator("lowStockThreshold")
    @classmethod
    def validate_threshold(cls, value: str) -> str:
        if int(value) > 1_000_000:
            raise ValueError("Low-stock threshold is too large")
        return str(int(value))


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Settings database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Settings database is unavailable") from exc


def _can_manage(user):
    if user.get("role") not in {"owner", "admin"}:
        raise HTTPException(403, "Only an owner or admin can change shared business settings")


@router.get("")
def get_settings(user=Depends(current_user)):
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT settings, updated_at FROM app_business_settings WHERE settings_key='global'"
            ).fetchone()
        values = {**DEFAULT_SETTINGS, **(row["settings"] if row else {})}
        validated = BusinessSettings.model_validate(values).model_dump(mode="json")
        return {
            "settings": validated,
            "updated_at": row["updated_at"].isoformat() if row and row["updated_at"] else None,
            "storage": "shared",
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Shared settings storage unavailable; apply migration 008_business_settings.sql") from exc
    except ValueError as exc:
        raise HTTPException(503, "Stored business settings are invalid; review the saved configuration") from exc


@router.put("")
def update_settings(payload: BusinessSettings, user=Depends(current_user)):
    _can_manage(user)
    values = payload.model_dump(mode="json")
    try:
        with _connect() as conn:
            row = conn.execute(
                """INSERT INTO app_business_settings (settings_key, settings, updated_by, updated_at)
                   VALUES ('global', %s, %s, now())
                   ON CONFLICT (settings_key) DO UPDATE
                   SET settings=EXCLUDED.settings, updated_by=EXCLUDED.updated_by, updated_at=now()
                   RETURNING settings, updated_at""",
                (Jsonb(values), user["id"]),
            ).fetchone()
        return {
            "settings": row["settings"],
            "updated_at": row["updated_at"].isoformat(),
            "storage": "shared",
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Could not save shared settings; apply migration 008_business_settings.sql") from exc
