"""Private S3 storage for identity-verification evidence.

Uses the existing private document bucket and EC2 instance role. No public ACLs,
static AWS credentials, or permanent public URLs are created.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid

import boto3


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {
    "application/pdf": ("pdf", b"%PDF-"),
    "image/jpeg": ("jpg", bytes((0xFF, 0xD8, 0xFF))),
    "image/png": ("png", bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))),
}
DOCUMENT_TYPES = {"identity_proof", "address_proof", "business_proof", "other"}


class IdentityDocumentConfigurationError(RuntimeError):
    pass


class IdentityDocumentError(ValueError):
    pass


def _storage():
    bucket = os.getenv("SB_PRIVATE_DOCUMENT_BUCKET", "").strip()
    region = os.getenv("SB_S3_REGION", "").strip() or os.getenv("AWS_REGION", "").strip()
    if not bucket or not region:
        raise IdentityDocumentConfigurationError("Private identity document storage is not configured")
    return bucket, boto3.client("s3", region_name=region)


def validate_document(content: bytes, content_type: str, document_type: str) -> tuple[str, str]:
    if document_type not in DOCUMENT_TYPES:
        raise IdentityDocumentError("Unsupported identity document type")
    if content_type not in ALLOWED_TYPES:
        raise IdentityDocumentError("Upload a PDF, JPEG or PNG document")
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise IdentityDocumentError("Document must be between 1 byte and 10 MB")
    extension, signature = ALLOWED_TYPES[content_type]
    if not content.startswith(signature):
        raise IdentityDocumentError("Document content does not match its declared type")
    return extension, hashlib.sha256(content).hexdigest()


def upload_identity_document(*, party_id: int, user_id: int, document_type: str,
                             content_type: str, content: bytes) -> dict:
    if party_id <= 0 or user_id <= 0:
        raise IdentityDocumentError("A valid identity and uploader are required")
    extension, digest = validate_document(content, content_type, document_type)
    bucket, client = _storage()
    key = f"identity-verification/{party_id}/{uuid.uuid4().hex}.{extension}"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
        ServerSideEncryption="AES256",
        Metadata={
            "party-id": str(party_id),
            "uploaded-by-user-id": str(user_id),
            "sha256": digest,
            "document-type": document_type,
        },
    )
    return {
        "object_key": key,
        "content_type": content_type,
        "file_size_bytes": len(content),
        "sha256_hex": digest,
    }


def create_identity_document_download_url(*, party_id: int, object_key: str,
                                           expires_in: int = 300) -> str:
    if party_id <= 0 or not 60 <= expires_in <= 600:
        raise IdentityDocumentError("Invalid identity document download request")
    expected_prefix = f"identity-verification/{party_id}/"
    if not object_key.startswith(expected_prefix) or not re.fullmatch(
        r"identity-verification/\d+/[0-9a-f]{32}\.(pdf|jpg|png)", object_key
    ):
        raise IdentityDocumentError("Document is outside this identity's storage area")
    bucket, client = _storage()
    head = client.head_object(Bucket=bucket, Key=object_key)
    if head.get("Metadata", {}).get("party-id") != str(party_id):
        raise IdentityDocumentError("Document ownership metadata does not match")
    if head.get("ServerSideEncryption") != "AES256":
        raise IdentityDocumentError("Identity document is not stored with required encryption")
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": object_key}, ExpiresIn=expires_in
    )
