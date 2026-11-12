"""Database integration tests for reviewed identity contact verification."""
import os
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi import HTTPException
from psycopg.rows import dict_row

TEST_DB = os.environ.get("SB_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="SB_TEST_DATABASE_URL is not set")
if TEST_DB and ("sb_app" in TEST_DB or "amazonaws" in TEST_DB):
    raise RuntimeError("Refusing to run identity contact tests against a production-like database")


def test_admin_verification_records_contact_state_and_audit_evidence(monkeypatch):
    from app.api import identity as identity_api
    from app.api.identity import ContactVerifyIn, verify_contact
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        party = IdentityService(conn).create_party(
            party_type="individual",
            display_name="Contact Verification " + suffix,
            reason="Contact verification integration fixture",
        )
        contact = IdentityService(conn).add_contact(
            party_id=party["id"],
            contact_type="email",
            value=f"verify-{suffix}@test.local",
            source="identity_verification_test",
        )
        admin = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"contact-reviewer-{suffix}@test.local", "Contact Reviewer", "test-hash"),
        ).fetchone()

    monkeypatch.setattr(identity_api.settings, "database_url", TEST_DB)
    request = SimpleNamespace(state=SimpleNamespace(user_id=admin["id"], role="admin"))
    result = verify_contact(
        contact["id"],
        ContactVerifyIn(
            proof_method="document_review",
            reason="Reviewed the original supporting document",
        ),
        request,
    )

    assert result["status"] == "verified"
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        saved = conn.execute(
            "SELECT verification_status,verified_at FROM identity_contacts WHERE id=%s",
            (contact["id"],),
        ).fetchone()
        event = conn.execute(
            "SELECT event_type,actor_user_id,reason,event_data FROM identity_events "
            "WHERE party_id=%s ORDER BY id DESC LIMIT 1",
            (party["id"],),
        ).fetchone()
    assert saved["verification_status"] == "verified"
    assert saved["verified_at"] is not None
    assert event["event_type"] == "contact_verified"
    assert event["actor_user_id"] == admin["id"]
    assert event["reason"] == "Reviewed the original supporting document"
    assert event["event_data"]["proof_method"] == "document_review"


def test_revoked_or_historic_contact_cannot_be_verified(monkeypatch):
    from app.api import identity as identity_api
    from app.api.identity import ContactVerifyIn, verify_contact
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        party = IdentityService(conn).create_party(
            party_type="individual",
            display_name="Revoked Contact " + suffix,
            reason="Revoked contact integration fixture",
        )
        contact = IdentityService(conn).add_contact(
            party_id=party["id"],
            contact_type="email",
            value=f"revoked-{suffix}@test.local",
            source="identity_verification_test",
        )
        conn.execute(
            "UPDATE identity_contacts SET verification_status='revoked',valid_to=now() WHERE id=%s",
            (contact["id"],),
        )
        admin = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"contact-reviewer-revoked-{suffix}@test.local", "Contact Reviewer", "test-hash"),
        ).fetchone()

    monkeypatch.setattr(identity_api.settings, "database_url", TEST_DB)
    request = SimpleNamespace(state=SimpleNamespace(user_id=admin["id"], role="admin"))
    with pytest.raises(HTTPException) as rejected:
        verify_contact(
            contact["id"],
            ContactVerifyIn(
                proof_method="in_person",
                reason="Attempted to verify a revoked contact",
            ),
            request,
        )
    assert rejected.value.status_code == 409


def test_admin_can_revoke_an_active_organisation_relationship_with_audit_reason(monkeypatch):
    from app.api import identity as identity_api
    from app.api.identity import RelationshipRevokeIn, revoke_relationship
    from app.services.identity import IdentityService

    suffix = uuid4().hex
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        service = IdentityService(conn)
        person = service.create_party(
            party_type="individual",
            display_name="Relationship Person " + suffix,
            reason="Relationship revocation integration fixture",
        )
        organisation = service.create_party(
            party_type="organisation",
            display_name="Relationship Organisation " + suffix,
            reason="Relationship revocation integration fixture",
        )
        relationship = service.create_relationship(
            from_party_id=person["id"],
            to_party_id=organisation["id"],
            relationship_type="authorised_vendor_user",
            scope={"portal_access": True},
            reason="Authorised vendor portal access",
        )
        admin = conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'admin') RETURNING id",
            (f"relationship-reviewer-{suffix}@test.local", "Relationship Reviewer", "test-hash"),
        ).fetchone()

    monkeypatch.setattr(identity_api.settings, "database_url", TEST_DB)
    request = SimpleNamespace(state=SimpleNamespace(user_id=admin["id"], role="admin"))
    result = revoke_relationship(
        relationship["id"],
        RelationshipRevokeIn(reason="Vendor authority has been withdrawn"),
        request,
    )

    assert result["status"] == "revoked"
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        saved = conn.execute(
            "SELECT status,valid_to FROM identity_relationships WHERE id=%s",
            (relationship["id"],),
        ).fetchone()
        event = conn.execute(
            "SELECT event_type,actor_user_id,reason,event_data FROM identity_events "
            "WHERE party_id=%s ORDER BY id DESC LIMIT 1",
            (person["id"],),
        ).fetchone()
    assert saved["status"] == "revoked"
    assert saved["valid_to"] is not None
    assert event["event_type"] == "relationship_revoked"
    assert event["actor_user_id"] == admin["id"]
    assert event["reason"] == "Vendor authority has been withdrawn"
    assert event["event_data"]["relationship_id"] == relationship["id"]
