"""Unit tests for support-ticket categories and private attachment handling."""
import pytest
from pydantic import ValidationError

from app.api.customers import SUPPORT_CATEGORIES, CustomerSupportTicketIn
from app.services.support_attachments import (
    SupportAttachmentError,
    clean_filename,
    create_support_attachment_download_url,
    upload_support_attachment,
    validate_attachment,
)

PNG = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)) + b"data"
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "


def test_ticket_subjects_match_the_customer_dropdown_in_order():
    assert list(SUPPORT_CATEGORIES.values()) == [
        "Item Not Listed", "Account Issue", "Supercoin", "Order Delayed",
        "Cancellation & Refund", "Payment Issue", "Referral Earning", "Feedback",
    ]


def test_ticket_accepts_a_category_without_a_free_text_subject():
    ticket = CustomerSupportTicketIn(category="order_delayed", description="  Still waiting  ")
    assert ticket.category == "order_delayed"
    assert ticket.description == "Still waiting"


def test_ticket_rejects_unknown_category_and_missing_subject():
    with pytest.raises(ValidationError):
        CustomerSupportTicketIn(category="made_up", description="help")
    with pytest.raises(ValidationError):
        CustomerSupportTicketIn(description="help")


def test_legacy_subject_only_tickets_still_validate():
    ticket = CustomerSupportTicketIn(subject="Insurance consultation request", description="Call me")
    assert ticket.category is None


@pytest.mark.parametrize("content,content_type,ext", [
    (b"%PDF-1.7 x", "application/pdf", "pdf"),
    (b"\xff\xd8\xffabc", "image/jpeg", "jpg"),
    (PNG, "image/png", "png"),
    (WEBP, "image/webp", "webp"),
])
def test_validate_accepts_supported_files(content, content_type, ext):
    extension, digest = validate_attachment(content, content_type)
    assert extension == ext and len(digest) == 64


@pytest.mark.parametrize("content,content_type", [
    (b"", "image/png"),
    (b"plain text", "application/pdf"),
    (b"GIF89a", "image/gif"),
    (b"RIFF\x00\x00\x00\x00WAVEfmt ", "image/webp"),
    (b"%PDF-" + b"0" * (5 * 1024 * 1024), "application/pdf"),
])
def test_validate_rejects_bad_files(content, content_type):
    with pytest.raises(SupportAttachmentError):
        validate_attachment(content, content_type)


def test_clean_filename_strips_paths_and_control_characters():
    assert clean_filename("..\\..\\evil/path\\photo\x00.png") == "photo.png"
    assert clean_filename("") == "attachment"


def test_upload_uses_private_encrypted_s3_object(monkeypatch):
    calls = {}

    class FakeS3:
        def put_object(self, **kwargs):
            calls.update(kwargs)

    monkeypatch.setenv("SB_PRIVATE_DOCUMENT_BUCKET", "private-documents")
    monkeypatch.setenv("SB_S3_REGION", "ap-south-1")
    monkeypatch.setattr("app.services.support_attachments.boto3.client", lambda *a, **k: FakeS3())
    stored = upload_support_attachment(case_id=7, customer_account_id=3, content_type="image/png", content=PNG)
    assert stored["object_key"].startswith("support-tickets/7/")
    assert calls["ServerSideEncryption"] == "AES256"
    assert "ACL" not in calls


def test_download_url_is_limited_to_the_tickets_own_objects(monkeypatch):
    class FakeS3:
        def generate_presigned_url(self, *a, **k):
            return "https://signed.example/x"

    monkeypatch.setenv("SB_PRIVATE_DOCUMENT_BUCKET", "private-documents")
    monkeypatch.setenv("SB_S3_REGION", "ap-south-1")
    monkeypatch.setattr("app.services.support_attachments.boto3.client", lambda *a, **k: FakeS3())
    key = "support-tickets/7/" + "a" * 32 + ".png"
    assert create_support_attachment_download_url(case_id=7, object_key=key, filename="a.png")
    with pytest.raises(SupportAttachmentError):
        create_support_attachment_download_url(case_id=8, object_key=key, filename="a.png")
    with pytest.raises(SupportAttachmentError):
        create_support_attachment_download_url(case_id=7, object_key="identity-verification/7/x.png", filename="a.png")
