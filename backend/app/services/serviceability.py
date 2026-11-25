"""Regional serviceability: State -> District -> PIN coverage for warehouses, plus product availability.

Coverage rules (applied to both standard and express delivery):
  * PIN codes listed  -> ONLY those PINs are served.
  * Else districts    -> every PIN in those districts (inside the selected states) is served.
  * Else states       -> every PIN in those states is served.
  * Nothing listed    -> standard: the warehouse's own state; express: the whole standard area.
Express additionally requires ``express_enabled`` and is always a subset of standard coverage.
"""
import json
import os
import re
import urllib.error
import urllib.request

PIN_RE = re.compile(r"^[1-9][0-9]{5}$")

# ISO 3166-2:IN codes, keyed by normalised state / UT name.
STATE_CODES = {
    "andhra pradesh": "IN-AP", "arunachal pradesh": "IN-AR", "assam": "IN-AS", "bihar": "IN-BR",
    "chhattisgarh": "IN-CG", "goa": "IN-GA", "gujarat": "IN-GJ", "haryana": "IN-HR",
    "himachal pradesh": "IN-HP", "jharkhand": "IN-JH", "karnataka": "IN-KA", "kerala": "IN-KL",
    "madhya pradesh": "IN-MP", "maharashtra": "IN-MH", "manipur": "IN-MN", "meghalaya": "IN-ML",
    "mizoram": "IN-MZ", "nagaland": "IN-NL", "odisha": "IN-OD", "punjab": "IN-PB",
    "rajasthan": "IN-RJ", "sikkim": "IN-SK", "tamil nadu": "IN-TN", "telangana": "IN-TS",
    "tripura": "IN-TR", "uttar pradesh": "IN-UP", "uttarakhand": "IN-UK", "west bengal": "IN-WB",
    "andaman and nicobar islands": "IN-AN", "chandigarh": "IN-CH",
    "dadra and nagar haveli and daman and diu": "IN-DH", "delhi": "IN-DL",
    "jammu and kashmir": "IN-JK", "ladakh": "IN-LA", "lakshadweep": "IN-LD", "puducherry": "IN-PY",
}
_ALIASES = {
    "nct of delhi": "delhi", "new delhi": "delhi", "orissa": "odisha", "uttaranchal": "uttarakhand",
    "pondicherry": "puducherry", "jammu & kashmir": "jammu and kashmir",
    "dadra and nagar haveli": "dadra and nagar haveli and daman and diu",
    "daman and diu": "dadra and nagar haveli and daman and diu",
    "andaman & nicobar islands": "andaman and nicobar islands",
}

SERVICE_AREA_KEYS = ("service_states", "service_districts", "service_pin_codes")
EXPRESS_AREA_KEYS = ("express_states", "express_districts", "express_pin_codes")


def norm(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "").replace("&", " and ").strip().lower())
    return re.sub(r"\s+", " ", text)


def norm_state(value) -> str:
    text = norm(value)
    return _ALIASES.get(text, text)


def clean_list(values, normaliser=norm) -> list[str]:
    return [normaliser(v) for v in (values or []) if str(v or "").strip()]


# ---------------------------------------------------------------- PIN -> state / district
def _online_lookup(pin: str):
    """Look a PIN up on India Post's public directory. Never raises."""
    if os.getenv("SB_PIN_LOOKUP_ONLINE", "1").strip().lower() in {"0", "false", "no"}:
        return None
    try:
        request = urllib.request.Request(
            "https://api.postalpincode.in/pincode/" + pin, headers={"User-Agent": "SuperBajaar/1.0"}
        )
        with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310 - fixed https host
            data = json.loads(response.read().decode("utf-8"))
        offices = (data[0] or {}).get("PostOffice") or [] if data else []
        if not offices:
            return None
        office = offices[0]
        state = str(office.get("State") or "").strip()
        if not state:
            return None
        return {"state": state, "district": str(office.get("District") or "").strip() or None,
                "office": str(office.get("Name") or "").strip() or None}
    except Exception:  # network, JSON or schema problems must never break checkout
        return None


def lookup_pin(conn, pin: str):
    """Return {'pin_code','state','district'} or None when the PIN cannot be resolved."""
    if not PIN_RE.match(pin or ""):
        return None
    try:
        row = conn.execute("SELECT pin_code, state, district FROM india_pin_directory WHERE pin_code=%s", (pin,)).fetchone()
    except Exception:
        row = None  # directory table not migrated yet; fall through to online lookup
    if row:
        return {"pin_code": pin, "state": row["state"], "district": row["district"]}
    found = _online_lookup(pin)
    if not found:
        return None
    try:
        conn.execute(
            "INSERT INTO india_pin_directory(pin_code,state,district,office,source) VALUES(%s,%s,%s,%s,'india_post_api') "
            "ON CONFLICT (pin_code) DO NOTHING",
            (pin, found["state"], found["district"], found["office"]),
        )
    except Exception:
        pass
    return {"pin_code": pin, "state": found["state"], "district": found["district"]}


# ---------------------------------------------------------------- coverage matching
def _effective_profile(row) -> dict:
    data = row.get("profile_data") or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    data = dict(data)
    has_area = any(data.get(key) for key in SERVICE_AREA_KEYS)
    if not has_area:
        if data.get("state") or row.get("state"):
            data["service_states"] = [data.get("state") or row.get("state")]
        elif row.get("pin_code"):
            data["service_pin_codes"] = [row["pin_code"]]  # legacy warehouse without a profile
    return data


def _covers(data: dict, pin: str, info, prefix: str) -> bool:
    pins = {str(p).strip() for p in data.get(prefix + "_pin_codes") or [] if str(p).strip()}
    if pins:
        return pin in pins
    states = clean_list(data.get(prefix + "_states"), norm_state)
    districts = clean_list(data.get(prefix + "_districts"))
    if not states and not districts:
        return False
    if not info:
        return False
    if states and norm_state(info.get("state")) not in states:
        return False
    if districts and norm(info.get("district")) not in districts:
        return False
    return True


def location_serves(row, pin: str, info, express: bool = False) -> bool:
    data = _effective_profile(row)
    if not _covers(data, pin, info, "service"):
        return False
    if not express:
        return True
    if not data.get("express_enabled"):
        return False
    if not any(data.get(key) for key in EXPRESS_AREA_KEYS):
        return True  # express switched on without a narrower area: whole standard area
    return _covers(data, pin, info, "express")


_CANDIDATE_SQL = (
    "SELECT sl.id, sl.name, sl.location_type, sl.pin_code, sl.region_code, sl.city, sl.district, sl.state, "
    "COALESCE(p.profile_data,'{}'::jsonb) AS profile_data "
    "FROM stock_locations sl LEFT JOIN stock_location_profiles p ON p.location_id=sl.id "
    "WHERE sl.is_active=TRUE AND sl.is_fulfillable=TRUE "
    "AND COALESCE((p.profile_data->>'storefront_available')::boolean, TRUE)=TRUE "
    "AND COALESCE((p.profile_data->>'dispatches_stock')::boolean, TRUE)=TRUE "
    "AND (COALESCE(jsonb_array_length(p.profile_data->'operating_days'),0)=0 "
    "OR p.profile_data->'operating_days' ? lower(to_char(now() AT TIME ZONE 'Asia/Kolkata','Dy'))) "
    "AND (p.profile_data->>'opening_time' IS NULL OR "
    "to_char(now() AT TIME ZONE 'Asia/Kolkata','HH24:MI') >= p.profile_data->>'opening_time') "
    "AND (p.profile_data->>'closing_time' IS NULL OR "
    "to_char(now() AT TIME ZONE 'Asia/Kolkata','HH24:MI') <= p.profile_data->>'closing_time') "
    "ORDER BY COALESCE((p.profile_data->>'routing_priority')::integer,100), sl.id"
)


def eligible_locations(conn, pin: str, express: bool = False, info=None, lock: bool = False):
    """Fulfilment locations (in routing order) that serve this PIN. ``info`` is the lookup_pin() result."""
    if info is None:
        info = lookup_pin(conn, pin)
    rows = conn.execute(_CANDIDATE_SQL + (" FOR UPDATE OF sl" if lock else "")).fetchall()
    return [row for row in rows if location_serves(row, pin, info, express)]


# ---------------------------------------------------------------- product availability
def _region_tokens(info, locations) -> set[str]:
    tokens = set()
    if info:
        state = norm_state(info.get("state"))
        tokens.update({state, norm(info.get("district")), norm(STATE_CODES.get(state, ""))})
    for row in locations:
        tokens.add(norm(row.get("region_code")))
    tokens.discard("")
    return tokens


def blocked_product_ids(conn, pin: str, info, locations, channel: str = "website", product_ids=None) -> set[int]:
    """Product ids that must not be sold for this PIN under the configured availability rules."""
    sql = "SELECT product_id, region_code, pincode, location_id, is_allowed FROM product_availability_rules WHERE channel=%s"
    params = [channel]
    if product_ids is not None:
        sql += " AND product_id = ANY(%s)"
        params.append(list(product_ids))
    try:
        rules = conn.execute(sql, params).fetchall()
    except Exception:
        return set()
    tokens = _region_tokens(info, locations)
    location_ids = {int(row["id"]) for row in locations}
    by_product: dict[int, list] = {}
    for rule in rules:
        by_product.setdefault(int(rule["product_id"]), []).append(rule)

    def matches(rule) -> bool:
        if rule["pincode"] and str(rule["pincode"]).strip() == pin:
            return True
        if rule["region_code"] and norm_state(rule["region_code"]) in tokens:
            return True
        if rule["location_id"] is not None and int(rule["location_id"]) in location_ids:
            return True
        return False

    blocked = set()
    for product_id, product_rules in by_product.items():
        if any(matches(r) for r in product_rules if not r["is_allowed"]):
            blocked.add(product_id)
            continue
        allow_rules = [r for r in product_rules if r["is_allowed"]]
        if allow_rules and not any(matches(r) for r in allow_rules):
            blocked.add(product_id)
    return blocked


def check_pin(conn, pin: str) -> dict:
    """Full storefront answer for a PIN: region, standard/express coverage and blocked products."""
    info = lookup_pin(conn, pin)
    standard = eligible_locations(conn, pin, False, info)
    express = eligible_locations(conn, pin, True, info) if standard else []
    blocked = sorted(blocked_product_ids(conn, pin, info, standard)) if standard else []
    if standard:
        message = "Super Bajaar is available in your region. Delivery is available at " + pin + "."
        if express:
            message += " Express delivery is available too."
    else:
        message = "Sorry, Super Bajaar isn't available in your region yet."
    return {
        "pin_code": pin,
        "serviceable": bool(standard),
        "express_available": bool(express),
        "status": "serviceable" if standard else "not_serviceable",
        "state": info["state"] if info else None,
        "district": info["district"] if info else None,
        "locations": [{"id": r["id"], "name": r["name"], "location_type": r["location_type"],
                       "region_code": r["region_code"], "city": r["city"], "district": r["district"], "state": r["state"]}
                      for r in standard],
        "blocked_product_ids": blocked,
        "message": message,
    }
