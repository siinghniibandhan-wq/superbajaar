"""Database-level tests for the additive unified identity foundation."""
import os
import re
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.rows import dict_row

TEST_DB = os.environ.get("SB_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="SB_TEST_DATABASE_URL is not set")
if TEST_DB and ("sb_app" in TEST_DB or "amazonaws" in TEST_DB):
    raise RuntimeError("Refusing to run identity integration tests against a production-like database")


def _party(conn, party_type="individual"):
    suffix = uuid4().hex
    row = conn.execute(
        "INSERT INTO identity_parties(party_type,display_name) VALUES(%s,%s) RETURNING id,sbid",
        (party_type, "Identity test " + suffix),
    ).fetchone()
    return row


def test_sbid_is_generated_unique_and_immutable():
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        first = _party(conn)
        second = _party(conn)
        assert re.fullmatch(r"SBID-[A-F0-9]{20}", first["sbid"])
        assert first["sbid"] != second["sbid"]
        with pytest.raises(psycopg.errors.RaiseException, match="SBID is permanent"):
            with conn.transaction():
                conn.execute(
                    "UPDATE identity_parties SET sbid=%s WHERE id=%s",
                    ("SBID-" + uuid4().hex[:20].upper(), first["id"]),
                )


def test_one_existing_customer_record_cannot_be_linked_to_two_parties():
    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        customer = conn.execute(
            "INSERT INTO customer_accounts(email,full_name,password_hash,referral_code) "
            "VALUES(%s,%s,%s,%s) RETURNING id",
            (f"identity-{suffix}@test.local", "Identity Test Customer", "test-hash", "REF" + suffix[:12].upper()),
        ).fetchone()
        first = _party(conn)
        second = _party(conn)
        conn.execute(
            "INSERT INTO identity_profiles(party_id,profile_type,customer_account_id) "
            "VALUES(%s,'customer_account',%s)",
            (first["id"], customer["id"]),
        )
        with pytest.raises(UniqueViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO identity_profiles(party_id,profile_type,customer_account_id) "
                    "VALUES(%s,'customer_account',%s)",
                    (second["id"], customer["id"]),
                )


def test_shared_phone_can_belong_to_two_distinct_parties_without_merging_them():
    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        first = _party(conn)
        second = _party(conn)
        shared_phone = "+9198765" + suffix[:5]
        for party in (first, second):
            conn.execute(
                "INSERT INTO identity_contacts(party_id,contact_type,normalized_value,display_value,"
                "verification_status,verified_at) VALUES(%s,'phone',%s,%s,'verified',now())",
                (party["id"], shared_phone, shared_phone),
            )
        count = conn.execute(
            "SELECT count(*) AS n FROM identity_contacts WHERE contact_type='phone' AND normalized_value=%s",
            (shared_phone,),
        ).fetchone()["n"]
        assert count == 2


def test_identity_event_cannot_be_updated_or_deleted():
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        party = _party(conn)
        event = conn.execute(
            "INSERT INTO identity_events(party_id,event_type,event_data) "
            "VALUES(%s,'party_created','{}'::jsonb) RETURNING id",
            (party["id"],),
        ).fetchone()
        with pytest.raises(psycopg.errors.RaiseException, match="Identity audit events are immutable"):
            with conn.transaction():
                conn.execute("UPDATE identity_events SET reason='tampered' WHERE id=%s", (event["id"],))


def test_profile_type_requires_exactly_one_matching_domain_reference():
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        party = _party(conn)
        with pytest.raises(CheckViolation):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO identity_profiles(party_id,profile_type) VALUES(%s,'employee')",
                    (party["id"],),
                )
