"""Unit tests for secure identity OTP primitives and existing Resend integration."""
from app.services import identity_otp


def test_generated_otp_is_six_numeric_digits():
    code = identity_otp.generate_otp()
    assert len(code) == 6
    assert code.isdigit()


def test_otp_digest_is_bound_to_challenge_and_secret():
    digest = identity_otp.otp_digest("challenge-one", "123456", "x" * 32)
    assert identity_otp.verify_otp_digest("challenge-one", "123456", digest, "x" * 32)
    assert not identity_otp.verify_otp_digest("challenge-two", "123456", digest, "x" * 32)
    assert not identity_otp.verify_otp_digest("challenge-one", "654321", digest, "x" * 32)
    assert not identity_otp.verify_otp_digest("challenge-one", "123456", digest, "y" * 32)


def test_otp_digest_rejects_invalid_code():
    import pytest
    with pytest.raises(ValueError):
        identity_otp.otp_digest("challenge-one", "12ab56", "x" * 32)


def test_otp_digest_requires_strong_secret():
    import pytest
    with pytest.raises(identity_otp.OTPConfigurationError):
        identity_otp.otp_digest("challenge-one", "123456", "short")


def test_email_otp_uses_existing_resend_service(monkeypatch):
    sent = {}
    monkeypatch.setenv("SB_EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-api-key")
    monkeypatch.setenv("SB_SMTP_FROM", "security@example.com")
    monkeypatch.delenv("RESEND_TEST_RECIPIENT", raising=False)
    def fake_send(**kwargs):
        sent.update(kwargs)
        return "resend-message-id"
    monkeypatch.setattr(identity_otp, "send_resend_email", fake_send)

    identity_otp.deliver_otp("email", "person@example.com", "123456")

    assert sent["recipient"] == "person@example.com"
    assert sent["subject"] == "Your Super Bajaar verification code"
    assert "123456" in sent["text"]
    assert sent["api_key"] == "test-api-key"


def test_resend_shared_test_sender_cannot_send_to_unverified_recipient(monkeypatch):
    import pytest
    monkeypatch.setenv("SB_EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-api-key")
    monkeypatch.setenv("SB_SMTP_FROM", "onboarding@resend.dev")
    monkeypatch.setenv("RESEND_TEST_RECIPIENT", "owner@example.com")

    with pytest.raises(identity_otp.OTPConfigurationError):
        identity_otp.deliver_otp("email", "other@example.com", "123456")


def test_resend_delivery_failure_is_not_reported_as_success(monkeypatch):
    import pytest
    monkeypatch.setenv("SB_EMAIL_PROVIDER", "resend")
    monkeypatch.setenv("RESEND_API_KEY", "test-api-key")
    monkeypatch.setenv("SB_SMTP_FROM", "security@example.com")
    monkeypatch.setattr(identity_otp, "send_resend_email", lambda **kwargs: None)

    with pytest.raises(identity_otp.OTPDeliveryError):
        identity_otp.deliver_otp("email", "person@example.com", "123456")
