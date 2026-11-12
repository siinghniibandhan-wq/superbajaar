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



def test_merge_consolidates_duplicate_contacts_without_losing_verification_history():
    from app.api.identity import _merge_claimed_party

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        actor = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"identity-merge-{suffix}@test.local", "Identity Merge Admin", "test-hash"),
        ).fetchone()
        source = _party(conn)
        target = _party(conn)
        email = f"merge-{suffix}@test.local"
        conn.execute(
            "INSERT INTO identity_contacts(party_id,contact_type,normalized_value,display_value,verification_status,verified_at,source) "
            "VALUES(%s,'email',%s,%s,'verified',now(),'crm_customer')",
            (source["id"], email, email),
        )
        conn.execute(
            "INSERT INTO identity_contacts(party_id,contact_type,normalized_value,display_value,verification_status,source) "
            "VALUES(%s,'email',%s,%s,'unverified','customer_registration')",
            (target["id"], email, email),
        )

        result = _merge_claimed_party(
            conn, source["id"], target["id"], actor["id"],
            "Verified duplicate customer identity", "document_review",
        )

        assert result["status"] == "merged"
        contacts = conn.execute(
            "SELECT party_id,verification_status,verified_at,valid_to,source "
            "FROM identity_contacts WHERE contact_type='email' AND normalized_value=%s ORDER BY id",
            (email,),
        ).fetchall()
        assert len(contacts) == 2
        active = [row for row in contacts if row["valid_to"] is None]
        historical = [row for row in contacts if row["valid_to"] is not None]
        assert len(active) == 1 and active[0]["party_id"] == target["id"]
        assert active[0]["verification_status"] == "verified"
        assert active[0]["verified_at"] is not None
        assert len(historical) == 1 and historical[0]["party_id"] == source["id"]
        assert historical[0]["source"] == "crm_customer"

@pytest.mark.parametrize(
    "relationship_type",
    ["owner", "director", "representative", "authorised_vendor_user"],
)
def test_individual_to_organisation_relationships_are_audited_and_unique(relationship_type):
    from app.services.identity import IdentityService

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        individual = _party(conn, "individual")
        organisation = _party(conn, "organisation")
        service = IdentityService(conn)
        relationship = service.create_relationship(
            from_party_id=individual["id"],
            to_party_id=organisation["id"],
            relationship_type=relationship_type,
            scope={"organisation_unit": "head_office"},
            reason="Verified organisation relationship",
        )
        assert relationship["relationship_type"] == relationship_type
        assert relationship["status"] == "active"
        assert relationship["scope"] == {"organisation_unit": "head_office"}
        event = conn.execute(
            "SELECT event_type,event_data FROM identity_events WHERE party_id=%s ORDER BY id DESC LIMIT 1",
            (individual["id"],),
        ).fetchone()
        assert event["event_type"] == "relationship_created"
        assert event["event_data"]["relationship_type"] == relationship_type

        with pytest.raises(UniqueViolation):
            with conn.transaction():
                service.create_relationship(
                    from_party_id=individual["id"],
                    to_party_id=organisation["id"],
                    relationship_type=relationship_type,
                    reason="Duplicate active relationship",
                )


def test_identity_relationship_rejects_self_relationship():
    from app.services.identity import IdentityService

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        party = _party(conn)
        with pytest.raises(ValueError, match="two distinct valid parties"):
            IdentityService(conn).create_relationship(
                from_party_id=party["id"],
                to_party_id=party["id"],
                relationship_type="owner",
                reason="Invalid self relationship",
            )


def test_hr_employee_and_supplier_profiles_reject_conflicting_identity_links():
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        employee = conn.execute(
            "INSERT INTO hr_employees(employee_code,first_name,last_name,email,designation,joining_date) "
            "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
            ("ID-" + suffix[:12], "Identity", "Employee", f"hr-{suffix}@test.local", "Associate", "2026-01-01"),
        ).fetchone()
        supplier = conn.execute(
            "INSERT INTO suppliers(name,email) VALUES(%s,%s) RETURNING id",
            ("Identity Supplier " + suffix, f"supplier-{suffix}@test.local"),
        ).fetchone()
        employee_party = _party(conn, "individual")
        other_employee_party = _party(conn, "individual")
        supplier_party = _party(conn, "organisation")
        other_supplier_party = _party(conn, "organisation")
        service = IdentityService(conn)

        service.link_profile(
            party_id=employee_party["id"], profile_type="employee",
            source_id=employee["id"], link_method="admin_verified",
            reason="Verified HR onboarding identity",
        )
        with pytest.raises(UniqueViolation):
            with conn.transaction():
                service.link_profile(
                    party_id=other_employee_party["id"], profile_type="employee",
                    source_id=employee["id"], link_method="admin_verified",
                    reason="Conflicting employee identity",
                )

        service.link_profile(
            party_id=supplier_party["id"], profile_type="vendor_organisation",
            source_id=supplier["id"], link_method="admin_verified",
            reason="Verified supplier onboarding identity",
        )
        with pytest.raises(UniqueViolation):
            with conn.transaction():
                service.link_profile(
                    party_id=other_supplier_party["id"], profile_type="vendor_organisation",
                    source_id=supplier["id"], link_method="admin_verified",
                    reason="Conflicting supplier identity",
                )

def test_employee_portal_activation_reuses_hr_identity_without_duplicate_profile():
    from app.api.portal_invitations import _ensure_employee_portal_identity
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        employee = conn.execute(
            "INSERT INTO hr_employees(employee_code,first_name,last_name,email,designation,joining_date) "
            "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
            ("PORTAL-" + suffix[:12], "Portal", "Employee", f"portal-{suffix}@test.local", "Associate", "2026-01-01"),
        ).fetchone()
        user = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'staff') RETURNING id",
            (f"portal-{suffix}@test.local", "Portal Employee", "test-hash"),
        ).fetchone()
        identity = IdentityService(conn)
        party = identity.create_party(
            party_type="individual", display_name="Portal Employee",
            reason="HR onboarding created permanent identity",
        )
        identity.link_profile(
            party_id=party["id"], profile_type="employee",
            source_id=employee["id"], link_method="admin_verified",
            reason="HR onboarding employee profile",
        )
        identity.add_contact(
            party_id=party["id"], contact_type="email",
            value=f"portal-{suffix}@test.local", source="hr_employee",
        )

        linked_party_id = _ensure_employee_portal_identity(
            conn, identity, employee["id"], user["id"],
            f"portal-{suffix}@test.local", "Portal Employee",
        )
        assert linked_party_id == party["id"]
        assert conn.execute(
            "SELECT count(*) AS n FROM identity_profiles WHERE profile_type='employee' AND employee_id=%s",
            (employee["id"],),
        ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT count(*) AS n FROM identity_auth_accounts WHERE app_user_id=%s AND party_id=%s AND status='active'",
            (user["id"], party["id"]),
        ).fetchone()["n"] == 1
        assert conn.execute(
            "SELECT count(*) AS n FROM identity_contacts WHERE party_id=%s AND contact_type='email' AND valid_to IS NULL",
            (party["id"],),
        ).fetchone()["n"] == 1


def test_employee_portal_activation_rejects_login_owned_by_another_identity():
    from fastapi import HTTPException
    from app.api.portal_invitations import _ensure_employee_portal_identity
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        employee = conn.execute(
            "INSERT INTO hr_employees(employee_code,first_name,last_name,email,designation,joining_date) "
            "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
            ("PORTAL-CONFLICT-" + suffix[:8], "Portal", "Conflict", f"portal-conflict-{suffix}@test.local", "Associate", "2026-01-01"),
        ).fetchone()
        user = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'staff') RETURNING id",
            (f"portal-user-conflict-{suffix}@test.local", "Existing Portal User", "test-hash"),
        ).fetchone()
        identity = IdentityService(conn)
        employee_party = identity.create_party(
            party_type="individual", display_name="Employee Party",
            reason="Employee identity for portal conflict",
        )
        identity.link_profile(
            party_id=employee_party["id"], profile_type="employee",
            source_id=employee["id"], link_method="admin_verified",
            reason="Employee identity link",
        )
        other_party = identity.create_party(
            party_type="individual", display_name="Other Party",
            reason="Existing login identity",
        )
        identity.link_auth_account(
            party_id=other_party["id"], account_type="staff",
            source_id=user["id"], link_method="admin_verified",
        )

        with pytest.raises(HTTPException) as conflict:
            _ensure_employee_portal_identity(
                conn, identity, employee["id"], user["id"],
                f"portal-conflict-{suffix}@test.local", "Portal Conflict",
            )
        assert conflict.value.status_code == 409


def test_employee_portal_activation_backfills_identity_for_legacy_employee():
    from app.api.portal_invitations import _ensure_employee_portal_identity
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        employee = conn.execute(
            "INSERT INTO hr_employees(employee_code,first_name,last_name,email,designation,joining_date) "
            "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",
            ("LEGACY-PORTAL-" + suffix[:8], "Legacy", "Employee", f"legacy-portal-{suffix}@test.local", "Associate", "2026-01-01"),
        ).fetchone()
        user = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'staff') RETURNING id",
            (f"legacy-portal-{suffix}@test.local", "Legacy Employee", "test-hash"),
        ).fetchone()
        party_id = _ensure_employee_portal_identity(
            conn, IdentityService(conn), employee["id"], user["id"],
            f"legacy-portal-{suffix}@test.local", "Legacy Employee",
        )
        assert conn.execute(
            "SELECT count(*) AS n FROM identity_profiles WHERE profile_type='employee' AND employee_id=%s AND party_id=%s",
            (employee["id"], party_id),
        ).fetchone()["n"] == 1

def test_admin_can_request_owner_relationship_for_an_explicit_individual_identity(monkeypatch):
    from types import SimpleNamespace
    from app.api import identity as identity_api
    from app.api.identity import LinkRequestIn, ReviewIn, create_link_request, review_link_request
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        admin = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"identity-admin-{suffix}@test.local", "Identity Admin", "test-hash"),
        ).fetchone()
        reviewer = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"identity-reviewer-{suffix}@test.local", "Independent Identity Reviewer", "test-hash"),
        ).fetchone()
        individual = _party(conn, "individual")
        organisation = _party(conn, "organisation")
    monkeypatch.setattr(identity_api.settings, "database_url", TEST_DB)
    request = SimpleNamespace(state=SimpleNamespace(user_id=admin["id"], role="admin"))
    payload = LinkRequestIn(
        target_party_id=organisation["id"],
        requester_party_id=individual["id"],
        request_type="organisation_relationship",
        relationship_type="owner",
        idempotency_key="identity-owner-" + suffix,
        reason="Verified ownership documentation submitted",
    )
    result = create_link_request(payload, request)
    assert result["request"]["status"] == "proof_required"
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as self_approval:
        review_link_request(
            result["request"]["id"],
            ReviewIn(
                decision="approve", proof_verified=True,
                proof_method="document_review",
                reason="Ownership evidence reviewed and approved",
            ),
            request,
        )
    assert self_approval.value.status_code == 403
    request.state.user_id = reviewer["id"]
    approved = review_link_request(
        result["request"]["id"],
        ReviewIn(
            decision="approve", proof_verified=True,
            proof_method="document_review",
            reason="Ownership evidence reviewed and approved",
        ),
        request,
    )
    assert approved["status"] == "approved"
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        relationship = conn.execute(
            "SELECT relationship_type,status,approved_by_user_id FROM identity_relationships "
            "WHERE from_party_id=%s AND to_party_id=%s",
            (individual["id"], organisation["id"]),
        ).fetchone()
        assert relationship["relationship_type"] == "owner"
        assert relationship["status"] == "active"
        assert relationship["approved_by_user_id"] == admin["id"]
        saved = conn.execute(
            "SELECT requester_party_id,target_party_id,request_type,status "
            "FROM identity_link_requests WHERE idempotency_key=%s",
            ("identity-owner-" + suffix,),
        ).fetchone()
    assert saved["requester_party_id"] == individual["id"]
    assert saved["target_party_id"] == organisation["id"]
    assert saved["request_type"] == "organisation_relationship"
    assert saved["status"] == "proof_required"


def test_admin_cannot_request_organisation_relationship_for_wrong_party_types(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.api import identity as identity_api
    from app.api.identity import LinkRequestIn, create_link_request

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        admin = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"identity-admin-invalid-{suffix}@test.local", "Identity Admin", "test-hash"),
        ).fetchone()
        first = _party(conn, "organisation")
        second = _party(conn, "individual")
    monkeypatch.setattr(identity_api.settings, "database_url", TEST_DB)
    request = SimpleNamespace(state=SimpleNamespace(user_id=admin["id"], role="admin"))
    payload = LinkRequestIn(
        target_party_id=second["id"],
        requester_party_id=first["id"],
        request_type="organisation_relationship",
        relationship_type="director",
        idempotency_key="identity-invalid-" + suffix,
        reason="Attempted invalid relationship direction",
    )
    with pytest.raises(HTTPException) as invalid:
        create_link_request(payload, request)
    assert invalid.value.status_code == 409

def test_customer_identity_claim_is_reviewed_and_history_survives_merge(monkeypatch):
    from types import SimpleNamespace
    from app.api import customer_auth, identity as identity_api
    from app.api.customer_auth import IdentityClaimIn, list_identity_claims, request_identity_claim
    from app.api.identity import ReviewIn, review_link_request

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        customer = conn.execute(
            "INSERT INTO customer_accounts(email,full_name,phone,password_hash,referral_code) "
            "VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (f"claim-{suffix}@test.local", "Claim Customer", "+9198" + suffix[:8], "test-hash", "CL" + suffix[:10].upper()),
        ).fetchone()
        target = _party(conn, "individual")
        admin = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"claim-admin-{suffix}@test.local", "Claim Reviewer", "test-hash"),
        ).fetchone()
    monkeypatch.setattr(customer_auth.settings, "database_url", TEST_DB)
    monkeypatch.setattr(identity_api.settings, "database_url", TEST_DB)
    customer_request = SimpleNamespace(state=SimpleNamespace(customer_id=customer["id"]))
    submitted = request_identity_claim(
        IdentityClaimIn(target_sbid=target["sbid"], reason="This is my historical customer identity"),
        customer_request,
    )
    assert submitted["status"] == "submitted"
    history = list_identity_claims(customer_request)
    assert len(history["items"]) == 1
    assert history["items"][0]["status"] == "proof_required"
    assert "requested_sbid" not in history["items"][0]

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        request_row = conn.execute(
            "SELECT id,requester_party_id,target_party_id FROM identity_link_requests "
            "WHERE request_type='claim_existing_identity' AND requester_party_id IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
        ).fetchone()
    reviewer_request = SimpleNamespace(state=SimpleNamespace(user_id=admin["id"], role="admin"))
    reviewed = review_link_request(
        request_row["id"],
        ReviewIn(
            decision="approve", proof_verified=True,
            proof_method="document_review",
            reason="Government identity evidence verified",
        ),
        reviewer_request,
    )
    assert reviewed["status"] == "approved"
    history_after_merge = list_identity_claims(customer_request)
    assert history_after_merge["items"][0]["status"] == "approved"
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        alias = conn.execute(
            "SELECT canonical_party_id FROM identity_aliases WHERE source_party_id=%s",
            (request_row["requester_party_id"],),
        ).fetchone()
    assert alias["canonical_party_id"] == target["id"]


def test_unmatched_customer_identity_claim_can_be_rejected_without_disclosing_target(monkeypatch):
    from types import SimpleNamespace
    from app.api import customer_auth, identity as identity_api
    from app.api.customer_auth import IdentityClaimIn, list_identity_claims, request_identity_claim
    from app.api.identity import ReviewIn, review_link_request

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        customer = conn.execute(
            "INSERT INTO customer_accounts(email,full_name,phone,password_hash,referral_code) "
            "VALUES(%s,%s,%s,%s,%s) RETURNING id",
            (f"unmatched-{suffix}@test.local", "Unmatched Customer", "+9197" + suffix[:8], "test-hash", "UN" + suffix[:10].upper()),
        ).fetchone()
        admin = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"unmatched-admin-{suffix}@test.local", "Unmatched Reviewer", "test-hash"),
        ).fetchone()
    monkeypatch.setattr(customer_auth.settings, "database_url", TEST_DB)
    monkeypatch.setattr(identity_api.settings, "database_url", TEST_DB)
    customer_request = SimpleNamespace(state=SimpleNamespace(customer_id=customer["id"]))
    request_identity_claim(
        IdentityClaimIn(
            target_sbid="SBID-FFFFFFFFFFFFFFFFFFFF",
            reason="I believe this old account belongs to me",
        ),
        customer_request,
    )
    history = list_identity_claims(customer_request)
    assert len(history["items"]) == 1
    assert history["items"][0]["status"] == "proof_required"
    assert "requested_sbid" not in history["items"][0]

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        request_row = conn.execute(
            "SELECT id,target_party_id FROM identity_link_requests "
            "WHERE request_type='claim_existing_identity' AND requester_party_id IN "
            "(SELECT party_id FROM identity_profiles WHERE customer_account_id=%s) "
            "ORDER BY id DESC LIMIT 1",
            (customer["id"],),
        ).fetchone()
    assert request_row["target_party_id"] is None
    reviewer_request = SimpleNamespace(state=SimpleNamespace(user_id=admin["id"], role="admin"))
    reviewed = review_link_request(
        request_row["id"],
        ReviewIn(decision="reject", reason="No matching identity record or evidence supplied"),
        reviewer_request,
    )
    assert reviewed["status"] == "rejected"
    assert list_identity_claims(customer_request)["items"][0]["status"] == "rejected"

