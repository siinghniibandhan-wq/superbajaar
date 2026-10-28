"""Create the first owner interactively after database migration 007."""
import getpass
import os
import re
import sys
from pathlib import Path
import psycopg

# Make the backend package importable when this script is launched by path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.auth import _password_hash


def main():
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("Set DATABASE_URL before running this command.")
    email = input("Owner email: ").strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("Enter a valid email address.")
    name = input("Owner full name: ").strip()
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if not name or len(password) < 12 or password != confirm:
        raise SystemExit("Name is required; passwords must match and contain at least 12 characters.")
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            count = conn.execute("SELECT count(*) FROM app_users").fetchone()[0]
            if count:
                raise SystemExit("Bootstrap refused: an account already exists.")
            row = conn.execute(
                "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'owner') RETURNING id,email",
                (email, name, _password_hash(password)),
            ).fetchone()
    print(f"Initial owner created: {row[1]} (user ID {row[0]}).")


if __name__ == "__main__":
    main()
