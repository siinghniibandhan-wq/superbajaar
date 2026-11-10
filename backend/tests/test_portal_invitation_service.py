from datetime import datetime, timedelta, timezone

from app.services.portal_invitation import (
    hash_invitation_token,
    issue_invitation_token,
    invitation_is_usable,
)


def test_invitation_token_is_random_and_only_hash_is_stored():
    raw, digest = issue_invitation_token()
    assert len(raw) >= 40
    assert digest == hash_invitation_token(raw)
    assert raw != digest


def test_invitation_token_hash_is_stable_and_not_plaintext():
    token = "a-secure-one-time-invitation-token"
    assert hash_invitation_token(token) == hash_invitation_token(token)
    assert hash_invitation_token(token) != token


def test_invitation_is_usable_only_before_expiry_and_before_accept_or_revoke():
    now = datetime.now(timezone.utc)
    assert invitation_is_usable(now + timedelta(minutes=5), None, None, now)
    assert not invitation_is_usable(now - timedelta(seconds=1), None, None, now)
    assert not invitation_is_usable(now + timedelta(minutes=5), now, None, now)
    assert not invitation_is_usable(now + timedelta(minutes=5), None, now, now)
