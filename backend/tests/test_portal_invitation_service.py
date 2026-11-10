from datetime import datetime, timedelta, timezone
import json

from app.services.portal_invitation import (
    hash_invitation_token,
    invitation_is_usable,
    issue_invitation_token,
    send_resend_email,
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


def test_resend_email_posts_json_and_returns_message_id(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"id":"email_123"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("app.services.portal_invitation.urlopen", fake_urlopen)
    message_id = send_resend_email(
        api_key="re_test_secret",
        sender="Super Bajaar <onboarding@resend.dev>",
        recipient="owner@example.com",
        subject="Portal invitation",
        text="Activate your account",
    )

    assert message_id == "email_123"
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["authorization"] == "Bearer re_test_secret"
    assert captured["payload"] == {
        "from": "Super Bajaar <onboarding@resend.dev>",
        "to": ["owner@example.com"],
        "subject": "Portal invitation",
        "text": "Activate your account",
    }
    assert captured["timeout"] == 10


def test_resend_email_returns_none_when_provider_rejects_request(monkeypatch):
    from urllib.error import HTTPError

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 403, "Forbidden", None, None)

    monkeypatch.setattr("app.services.portal_invitation.urlopen", fake_urlopen)
    assert send_resend_email(
        api_key="re_test_secret",
        sender="onboarding@resend.dev",
        recipient="other@example.com",
        subject="Portal invitation",
        text="Activate your account",
    ) is None
