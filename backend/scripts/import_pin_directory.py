#!/usr/bin/env python3
"""Import the India Post PIN directory (CSV) into india_pin_directory.

Usage:  python backend/scripts/import_pin_directory.py all_india_pin_code.csv

Accepts the data.gov.in "All India Pincode Directory" columns (officename, pincode,
districtname, statename); header names are matched case-insensitively. One row per PIN is kept.
The storefront also caches unknown PINs automatically from India Post's public API, so this
import is optional but makes lookups instant and independent of that service.
"""
import csv
import sys

import psycopg

from app.core.config import settings


def pick(row, *names):
    lowered = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for name in names:
        if lowered.get(name):
            return lowered[name]
    return ""


def main(path):
    if not settings.database_url:
        sys.exit("DATABASE_URL is not configured")
    seen, rows = set(), []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            pin = pick(row, "pincode", "pin_code", "pin").split(".")[0].zfill(6)
            state = pick(row, "statename", "state")
            if not (pin.isdigit() and len(pin) == 6 and pin[0] != "0" and state) or pin in seen:
                continue
            seen.add(pin)
            rows.append((pin, state.title(), pick(row, "districtname", "district").title() or None,
                         pick(row, "officename", "office") or None))
    with psycopg.connect(settings.database_url) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO india_pin_directory(pin_code,state,district,office,source) VALUES(%s,%s,%s,%s,'import') "
                "ON CONFLICT (pin_code) DO UPDATE SET state=EXCLUDED.state, district=EXCLUDED.district, "
                "office=EXCLUDED.office, source='import', updated_at=now()", rows)
    print(f"Imported {len(rows)} PIN codes")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
