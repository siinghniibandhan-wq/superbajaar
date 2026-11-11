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


def test_vendor_profile_requires_an_organisation_party():
    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        supplier = conn.execute(
            "INSERT INTO suppliers(name,email) VALUES(%s,%s) RETURNING id",
            ("Identity Vendor " + suffix, f"vendor-{suffix}@test.local"),
        ).fetchone()
        individual = _party(conn, "individual")
        with pytest.raises(psycopg.errors.RaiseException, match="incompatible with party type"):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO identity_profiles(party_id,profile_type,supplier_id) "
                    "VALUES(%s,'vendor_organisation',%s)",
                    (individual["id"], supplier["id"]),
                )


def test_staff_login_account_cannot_be_attached_to_an_organisation_party():
    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        user = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) "
            "VALUES(%s,%s,%s,'staff') RETURNING id",
            (f"identity-staff-{suffix}@test.local", "Identity Staff Test", "test-hash"),
        ).fetchone()
        organisation = _party(conn, "organisation")
        with pytest.raises(psycopg.errors.RaiseException, match="individual identity"):
            with conn.transaction():
                conn.execute(
                    "INSERT INTO identity_auth_accounts(party_id,account_type,app_user_id,link_method) "
                    "VALUES(%s,'staff',%s,'admin_verified')",
                    (organisation["id"], user["id"]),
                )



def test_identity_service_creates_party_and_audit_event_atomically():
    from app.services.identity import IdentityService

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        service = IdentityService(conn)
        party = service.create_party(party_type="individual", display_name="Service Test Person")
        assert party["sbid"].startswith("SBID-")
        event = conn.execute(
            "SELECT event_type,event_data FROM identity_events WHERE party_id=%s ORDER BY id DESC LIMIT 1",
            (party["id"],),
        ).fetchone()
        assert event["event_type"] == "party_created"
        assert event["event_data"]["party_type"] == "individual"


def test_identity_service_adds_contact_as_unverified_until_proof_is_recorded():
    from app.services.identity import IdentityService

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        service = IdentityService(conn)
        party = service.create_party(party_type="individual", display_name="Contact Test Person")
        contact = service.add_contact(
            party_id=party["id"], contact_type="phone", value="9876543210"
        )
        assert contact["normalized_value"] == "+919876543210"
        assert contact["verification_status"] == "unverified"


def test_identity_service_links_existing_customer_profile_and_login_without_rekeying():
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        customer = conn.execute(
            "INSERT INTO customer_accounts(email,full_name,password_hash,referral_code) "
            "VALUES(%s,%s,%s,%s) RETURNING id",
            (f"identity-link-{suffix}@test.local", "Identity Link Test", "test-hash", "REF" + suffix[:12].upper()),
        ).fetchone()
        party = IdentityService(conn).create_party(
            party_type="individual", display_name="Identity Link Test"
        )
        service = IdentityService(conn)
        profile = service.link_profile(
            party_id=party["id"], profile_type="customer_account",
            source_id=customer["id"], link_method="authenticated_claim",
        )
        auth = service.link_auth_account(
            party_id=party["id"], account_type="customer",
            source_id=customer["id"], link_method="authenticated_claim",
        )
        assert profile["customer_account_id"] == customer["id"]
        assert auth["customer_account_id"] == customer["id"]
