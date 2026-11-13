"""Unit tests for private S3 identity evidence handling."""
import pytest

from app.services.identity_documents import (
    IdentityDocumentError,
    create_identity_document_download_url,
    upload_identity_document,
    validate_document,
)


def test_validate_pdf_and_digest():
    extension, digest = validate_document(b"%PDF-test", "application/pdf", "identity_proof")
    assert extension == "pdf"
    assert len(digest) == 64


@pytest.mark.parametrize("content,content_type", [
    (b"not-a-pdf", "application/pdf"),
    (b"\x00", "image/jpeg"),
    (b"", "image/png"),
])
def test_rejects_invalid_document_bytes(content, content_type):
    with pytest.raises(IdentityDocumentError):
        validate_document(content, content_type, "identity_proof")


def test_rejects_unsupported_document_type():
    with pytest.raises(IdentityDocumentError):
        validate_document(b"%PDF-test", "application/pdf", "passport_number")


def test_upload_uses_private_encrypted_s3_object(monkeypatch):
    calls = {}
    class FakeS3:
        def put_object(self, **kwargs):
            calls.update(kwargs)
    monkeypatch.setenv("SB_PRIVATE_DOCUMENT_BUCKET", "private-documents")
    monkeypatch.setenv("SB_S3_REGION", "ap-south-1")
    monkeypatch.setattr("app.services.identity_documents.boto3.client", lambda *a, **k: FakeS3())

    result = upload_identity_document(
        party_id=7, user_id=11, document_type="identity_proof",
        content_type="application/pdf", content=b"%PDF-test",
    )

    assert calls["Bucket"] == "private-documents"
    assert calls["ServerSideEncryption"] == "AES256"
    assert calls["Key"].startswith("identity-verification/7/")
    assert result["object_key"] == calls["Key"]
    assert calls["Metadata"]["party-id"] == "7"


def test_download_rejects_another_partys_object_before_s3_access(monkeypatch):
    monkeypatch.setenv("SB_PRIVATE_DOCUMENT_BUCKET", "private-documents")
    monkeypatch.setenv("SB_S3_REGION", "ap-south-1")
    with pytest.raises(IdentityDocumentError):
        create_identity_document_download_url(
            party_id=7, object_key="identity-verification/8/" + "a" * 32 + ".pdf"
        )
