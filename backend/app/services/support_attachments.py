"""Private S3 storage for customer support-ticket attachments.

Uses the same private document bucket and instance role as identity evidence.
Objects are never public; staff and customers receive short-lived signed URLs
only after the API has checked ticket ownership or staff access.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid

import boto3


MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_FILES_PER_UPLOAD = 3
MAX_FILES_PER_TICKET = 10
ALLOWED_TYPES = {
    "application/pdf": ("pdf", (b"%PDF-",)),
    "image/jpeg": ("jpg", (bytes((0xFF, 0xD8, 0xFF)),)),
    "image/png": ("png", (bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)),)),
    "image/webp": ("webp", (b"RIFF",)),
}
_KEY_RE = re.compile(r"support-tickets/(\d+)/[0-9a-f]{32}\.(pdf|jpg|png|webp)")


class SupportAttachmentConfigurationError(RuntimeError):
    pass


class SupportAttachmentError(ValueError):
    pass


def _storage():
    bucket = os.getenv("SB_PRIVATE_DOCUMENT_BUCKET", "").strip()
    region = os.getenv("SB_S3_REGION", "").strip() or os.getenv("AWS_REGION", "").strip()
    if not bucket or not region:
        raise SupportAttachmentConfigurationError("Support attachment storage is not configured")
    return bucket, boto3.client("s3", region_name=region)


def clean_filename(name: str | None) -> str:
    """Return a display-safe base name (no path, no control characters)."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return (base or "attachment")[:255]


def validate_attachment(content: bytes, content_type: str) -> tuple[str, str]:
    if content_type not in ALLOWED_TYPES:
        raise SupportAttachmentError("Attach a JPG, PNG, WebP or PDF file")
    if not content:
        raise SupportAttachmentError("The attached file is empty")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise SupportAttachmentError("Each attachment must be 5 MB or smaller")
    extension, signatures = ALLOWED_TYPES[content_type]
    if not any(content.startswith(sig) for sig in signatures):
        raise SupportAttachmentError("The file content does not match its type")
    if content_type == "image/webp" and content[8:12] != b"WEBP":
        raise SupportAttachmentError("The file content does not match its type")
    return extension, hashlib.sha256(content).hexdigest()


def upload_support_attachment(*, case_id: int, customer_account_id: int,
                              content_type: str, content: bytes) -> dict:
    if case_id <= 0 or customer_account_id <= 0:
        raise SupportAttachmentError("A valid ticket and uploader are required")
    extension, digest = validate_attachment(content, content_type)
    bucket, client = _storage()
    key = f"support-tickets/{case_id}/{uuid.uuid4().hex}.{extension}"
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
        ServerSideEncryption="AES256",
        Metadata={
            "case-id": str(case_id),
            "uploaded-by-customer-account-id": str(customer_account_id),
            "sha256": digest,
        },
    )
    return {
        "object_key": key,
        "content_type": content_type,
        "file_size_bytes": len(content),
        "sha256_hex": digest,
    }


def delete_support_attachment_object(object_key: str) -> None:
    """Best-effort cleanup when the database insert fails after upload."""
    try:
        bucket, client = _storage()
        client.delete_object(Bucket=bucket, Key=object_key)
    except Exception:
        pass


def create_support_attachment_download_url(*, case_id: int, object_key: str,
                                           filename: str, expires_in: int = 300) -> str:
    if case_id <= 0 or not 60 <= expires_in <= 600:
        raise SupportAttachmentError("Invalid attachment download request")
    match = _KEY_RE.fullmatch(object_key)
    if not match or int(match.group(1)) != case_id:
        raise SupportAttachmentError("Attachment is outside this ticket's storage area")
    bucket, client = _storage()
    safe_name = clean_filename(filename).replace('"', "").replace(";", "_")
    safe_name = safe_name.encode("ascii", "ignore").decode() or "attachment"
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": object_key,
            "ResponseContentDisposition": f'attachment; filename="{safe_name}"',
        },
        ExpiresIn=expires_in,
    )
