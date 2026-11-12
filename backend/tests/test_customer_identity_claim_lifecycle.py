"""Database integration tests for customer-owned identity claim lifecycle."""
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
    raise RuntimeError("Refusing to run customer identity claim tests against a production-like database")


def _party(conn):
    return conn.execute(
        "INSERT INTO identity_parties(party_type,display_name) VALUES('individual',%s) RETURNING id,sbid",
        ("Claim lifecycle target " + uuid4().hex,),
    ).fetchone()


def _customer(conn, label):
    suffix = uuid4().hex
    return conn.execute(
        "INSERT INTO customer_accounts(email,full_name,phone,password_hash,referral_code) "
        "VALUES(%s,%s,%s,%s,%s) RETURNING id",
        (f"{label}-{suffix}@test.local", "Claim Lifecycle Customer", "+9198" + suffix[:8], "test-hash", "CL" + suffix[:10].upper()),
    ).fetchone()


def test_customer_can_cancel_own_unreviewed_claim_and_history_updates(monkeypatch):
    from app.api import customer_auth
    from app.api.customer_auth import IdentityClaimIn, cancel_identity_claim, list_identity_claims, request_identity_claim

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        customer = _customer(conn, "claim-cancel")
        target = _party(conn)
    monkeypatch.setattr(customer_auth.settings, "database_url", TEST_DB)
    customer_request = SimpleNamespace(state=SimpleNamespace(customer_id=customer["id"]))
    request_identity_claim(
        IdentityClaimIn(target_sbid=target["sbid"], reason="This historical identity belongs to me"),
        customer_request,
    )
    claim = list_identity_claims(customer_request)["items"][0]

    result = cancel_identity_claim(claim["id"], customer_request)

    assert result["status"] == "cancelled"
    assert list_identity_claims(customer_request)["items"][0]["status"] == "cancelled"
    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        event = conn.execute(
            "SELECT event_type,reason FROM identity_events "
            "WHERE event_type='link_cancelled' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert event["event_type"] == "link_cancelled"
    assert event["reason"] == "Customer cancelled their identity claim"


def test_customer_cannot_cancel_another_customers_claim(monkeypatch):
    from app.api import customer_auth
    from app.api.customer_auth import IdentityClaimIn, cancel_identity_claim, list_identity_claims, request_identity_claim

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        owner = _customer(conn, "claim-owner")
        other = _customer(conn, "claim-other")
        target = _party(conn)
    monkeypatch.setattr(customer_auth.settings, "database_url", TEST_DB)
    owner_request = SimpleNamespace(state=SimpleNamespace(customer_id=owner["id"]))
    other_request = SimpleNamespace(state=SimpleNamespace(customer_id=other["id"]))
    request_identity_claim(
        IdentityClaimIn(target_sbid=target["sbid"], reason="This historical identity belongs to me"),
        owner_request,
    )
    claim = list_identity_claims(owner_request)["items"][0]

    with pytest.raises(HTTPException) as rejected:
        cancel_identity_claim(claim["id"], other_request)
    assert rejected.value.status_code == 404
    assert list_identity_claims(owner_request)["items"][0]["status"] == "proof_required"


def test_customer_claim_submission_is_rate_limited_per_identity(monkeypatch):
    from app.api import customer_auth
    from app.api.customer_auth import IdentityClaimIn, request_identity_claim

    with psycopg.connect(TEST_DB, row_factory=dict_row) as conn:
        customer = _customer(conn, "claim-rate")
        target = _party(conn)
    monkeypatch.setattr(customer_auth.settings, "database_url", TEST_DB)
    customer_request = SimpleNamespace(state=SimpleNamespace(customer_id=customer["id"]))
    payload = IdentityClaimIn(
        target_sbid=target["sbid"],
        reason="This historical identity belongs to me",
    )
    for _ in range(5):
        assert request_identity_claim(payload, customer_request)["status"] == "submitted"

    with pytest.raises(HTTPException) as limited:
        request_identity_claim(payload, customer_request)
    assert limited.value.status_code == 429
