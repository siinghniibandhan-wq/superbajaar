"""Secure, operator-run provisioning of the first Super Admin.

Interactive use:
    python scripts/provision_super_admin.py

Non-interactive AWS SSM Run Command use:
    Set SB_SUPER_ADMIN_FULL_NAME and SB_SUPER_ADMIN_PASSWORD_PARAMETER.
    The parameter must be an AWS Systems Manager Parameter Store SecureString.
    The EC2 instance role needs ssm:GetParameter and ssm:DeleteParameter.
    The one-time parameter is deleted only after the database transaction commits.

The password is never accepted in command-line arguments, environment variables,
or logs. In non-interactive execution it is retrieved directly from Parameter
Store with decryption enabled.
"""
import getpass
import os
import re
import sys

import boto3
import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from psycopg.rows import dict_row

from app.api.auth import _password_hash


class ProvisioningInputError(Exception):
    """Raised when secure operator input is unavailable or invalid."""


def _read_full_name() -> str:
    full_name = os.environ.get("SB_SUPER_ADMIN_FULL_NAME", "").strip()
    if full_name:
        return full_name
    if not sys.stdin.isatty():
        raise ProvisioningInputError(
            "Non-interactive provisioning requires SB_SUPER_ADMIN_FULL_NAME."
        )
    try:
        return input("Super Admin full name: ").strip()
    except EOFError as exc:
        raise ProvisioningInputError(
            "No interactive input is available. Set SB_SUPER_ADMIN_FULL_NAME."
        ) from exc


def _read_password() -> tuple[str, object | None, str | None]:
    parameter_name = os.environ.get("SB_SUPER_ADMIN_PASSWORD_PARAMETER", "").strip()
    if parameter_name:
        try:
            ssm = boto3.client("ssm")
            response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        except (BotoCoreError, ClientError) as exc:
            raise ProvisioningInputError(
                "Unable to retrieve the Super Admin password from Parameter Store. "
                "Check the parameter name, AWS region, and EC2 role permissions."
            ) from exc

        parameter = response.get("Parameter", {})
        if parameter.get("Type") != "SecureString":
            raise ProvisioningInputError(
                "SB_SUPER_ADMIN_PASSWORD_PARAMETER must reference a SecureString parameter."
            )
        password = parameter.get("Value", "")
        if len(password) < 12:
            raise ProvisioningInputError(
                "The SecureString password must contain at least 12 characters."
            )
        return password, ssm, parameter_name

    if not sys.stdin.isatty():
        raise ProvisioningInputError(
            "Non-interactive provisioning requires SB_SUPER_ADMIN_PASSWORD_PARAMETER "
            "to reference an AWS Systems Manager Parameter Store SecureString. "
            "The EC2 role needs ssm:GetParameter and ssm:DeleteParameter."
        )

    try:
        password = getpass.getpass("New Super Admin password (minimum 12 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
    except EOFError as exc:
        raise ProvisioningInputError(
            "The terminal did not provide interactive password input. "
            "Use a Parameter Store SecureString for non-interactive provisioning."
        ) from exc

    if password != confirmation:
        raise ProvisioningInputError("Passwords do not match.")
    return password, None, None


def main() -> int:
    dsn = os.environ.get("DATABASE_URL", "").strip()
    email = os.environ.get("SB_SUPER_ADMIN_EMAIL", "").strip().lower()
    if not dsn:
        print("ERROR: DATABASE_URL is not configured.", file=sys.stderr)
        return 2
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        print("ERROR: Set SB_SUPER_ADMIN_EMAIL to the intended Super Admin email.", file=sys.stderr)
        return 2

    try:
        full_name = _read_full_name()
        password, ssm, parameter_name = _read_password()
    except ProvisioningInputError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if not full_name or len(password) < 12:
        print(
            "ERROR: Name is required; password must contain at least 12 characters.",
            file=sys.stderr,
        )
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
                print(
                    "REFUSED: A Super Admin already exists. Use normal user/password management.",
                    file=sys.stderr,
                )
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

    if ssm is not None and parameter_name:
        try:
            ssm.delete_parameter(Name=parameter_name)
        except (BotoCoreError, ClientError):
            print(
                "WARNING: Super Admin was provisioned, but the one-time SecureString "
                "could not be deleted. Remove that parameter manually from Parameter Store.",
                file=sys.stderr,
            )
            return 4

    print(f"Super Admin provisioned for {row['email']} (user ID {row['id']}).")
    print("Sign in through the normal Super Bajaar login screen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
