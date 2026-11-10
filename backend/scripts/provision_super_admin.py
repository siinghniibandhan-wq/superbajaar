"""Secure, operator-run provisioning of the first Super Admin.

Run from backend/ after applying required schema:
    python scripts/provision_super_admin.py

The email is read from SB_SUPER_ADMIN_EMAIL; the password is entered
interactively and is never accepted from command-line arguments or logged.
"""
import getpass
import os
import re
import sys

import psycopg
from psycopg.rows import dict_row

from app.api.auth import _password_hash


def main() -> int:
    dsn = os.environ.get("DATABASE_URL", "").strip()
    email = os.environ.get("SB_SUPER_ADMIN_EMAIL", "").strip().lower()
    if not dsn:
        print("ERROR: DATABASE_URL is not configured.", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        print("ERROR: Set SB_SUPER_ADMIN_EMAIL to the intended Super Admin email.", file=sys.stderr)
        return 2

    full_name = input("Super Admin full name: ").strip()
    password = getpass.getpass("New Super Admin password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if not full_name or len(password) < 12 or password != confirmation:
        print("ERROR: Name is required; passwords must match and contain at least 12 characters.", file=sys.stderr)
        return 2

    password_hash = _password_hash(password)
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.transaction():
            # Serialize provisioning attempts, including when the table is empty.
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('superbajaar:first-super-admin'))")
            existing_admin = conn.execute(
                "SELECT id FROM app_users WHERE role='super_admin' LIMIT 1 FOR UPDATE"
            ).fetchone()
            if existing_admin:
                print("REFUSED: A Super Admin already exists. Use normal user/password management.", file=sys.stderr)
                return 3

            existing_user = conn.execute(
                "SELECT id FROM app_users WHERE lower(email)=lower(%s) FOR UPDATE",
                (email,),
            ).fetchone()
            if existing_user:
                row = conn.execute(
                    "UPDATE app_users SET full_name=%s,password_hash=%s,role='super_admin',is_active=TRUE,updated_at=now() "
                    "WHERE id=%s RETURNING id,email",
                    (full_name, password_hash, existing_user["id"]),
                ).fetchone()
                conn.execute(
                    "UPDATE app_user_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL",
                    (row["id"],),
                )
            else:
                row = conn.execute(
                    "INSERT INTO app_users(email,full_name,password_hash,role,is_active) "
                    "VALUES(%s,%s,%s,'super_admin',TRUE) RETURNING id,email",
                    (email, full_name, password_hash),
                ).fetchone()

    print(f"Super Admin provisioned for {row['email']} (user ID {row['id']}).")
    print("Sign in through the normal Super Bajaar login screen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
