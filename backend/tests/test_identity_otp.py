"""Unit tests for secure identity OTP primitives."""
import pytest

from app.services.identity_otp import (
    OTPConfigurationError,
    generate_otp,
    otp_digest,
    verify_otp_digest,
)


def test_generated_otp_is_six_numeric_digits():
    code = generate_otp()
    assert len(code) == 6
    assert code.isdigit()


def test_otp_digest_is_bound_to_challenge_and_secret():
    digest = otp_digest("challenge-one", "123456", "x" * 32)
    assert verify_otp_digest("challenge-one", "123456", digest, "x" * 32)
    assert not verify_otp_digest("challenge-two", "123456", digest, "x" * 32)
    assert not verify_otp_digest("challenge-one", "654321", digest, "x" * 32)
    assert not verify_otp_digest("challenge-one", "123456", digest, "y" * 32)


def test_otp_digest_rejects_invalid_code():
    with pytest.raises(ValueError):
        otp_digest("challenge-one", "12ab56", "x" * 32)


def test_otp_digest_requires_strong_secret():
    with pytest.raises(OTPConfigurationError):
        otp_digest("challenge-one", "123456", "short")
