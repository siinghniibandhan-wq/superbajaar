"""Regression tests for explicit and audited identity relationships."""

import pytest

from app.services.identity import IdentityService


class RecordingConnection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))

        class Result:
            def fetchone(self):
                return {"id": 73, "from_party_id": params[0], "to_party_id": params[1], "relationship_type": params[2], "status": "active"}

        return Result()


def test_vendor_representative_relationship_is_explicit_and_audited():
    connection = RecordingConnection()
    relationship = IdentityService(connection).create_relationship(
        from_party_id=11,
        to_party_id=22,
        relationship_type="authorised_vendor_user",
        scope={"supplier_id": 9, "portal_access": True},
        actor_user_id=5,
        reason="Accepted vendor portal invitation",
    )
    assert relationship["id"] == 73
    insert_sql, insert_params = connection.calls[0]
    assert "identity_relationships" in insert_sql
    assert insert_params[:3] == (11, 22, "authorised_vendor_user")
    audit_sql, audit_params = connection.calls[1]
    assert "identity_events" in audit_sql
    assert audit_params[1] == "relationship_created"


def test_relationship_rejects_same_party_and_unknown_relationship_type():
    connection = RecordingConnection()
    service = IdentityService(connection)
    with pytest.raises(ValueError):
        service.create_relationship(from_party_id=1, to_party_id=1, relationship_type="representative")
    with pytest.raises(ValueError):
        service.create_relationship(from_party_id=1, to_party_id=2, relationship_type="made_up")
    assert connection.calls == []
