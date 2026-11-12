# Vendor Portal private AWS S3 storage

**Status:** Implementation and operations reference  
**Last reviewed:** 12 November 2026  
**Scope:** Private invoice/document storage for the Vendor Portal.

> This guide documents application configuration and security requirements. It does not confirm that a bucket, IAM role or production integration is currently provisioned. Verify the live AWS resources and backend service environment before making changes.

The Vendor Portal uploads invoice attachments through the FastAPI backend. Files are stored in a private Amazon S3 bucket; the browser never receives AWS credentials and does not upload directly to S3.

## Runtime configuration

Set these values in the backend service environment (not in frontend `VITE_*` variables):

- `SB_PRIVATE_DOCUMENT_BUCKET`: existing or newly provisioned private bucket name.
- `SB_S3_REGION`: exact AWS region in which that bucket exists.
- `AWS_REGION`: may remain set for other AWS integrations; `SB_S3_REGION` takes precedence for portal documents.

The backend uses Boto3's standard credential provider chain. On EC2, attach an instance profile/IAM role to the instance; do not put access keys in environment files, source code, or the repository.

## Bucket security

Configure the bucket with:

- S3 Block Public Access: all four settings enabled, at account and bucket level where possible.
- Object Ownership: Bucket owner enforced (ACLs disabled).
- Default encryption: SSE-S3 (AES-256). The application also requests `ServerSideEncryption=AES256` on upload.
- HTTPS-only access using a bucket policy that denies requests where `aws:SecureTransport` is false.
- No public website hosting and no public read policy.

The API validates PDF/JPEG/PNG content signatures and enforces a 10 MB maximum before upload. Objects use the `vendor-invoices/{supplier_id}/` key prefix and include the supplier ID as object metadata.

## EC2 instance-role permissions

Grant the backend instance role only the object operations needed for the portal, scoped to the bucket's vendor invoice prefix. Replace the bucket name below before applying:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VendorPortalInvoiceObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::REPLACE_WITH_PRIVATE_BUCKET/vendor-invoices/*"
    }
  ]
}
```

No bucket listing, deletion, ACL, or public-access permissions are required by the current portal upload/download code. Do not attach this policy until the bucket name and role have been verified.

## Download security

The API checks the authenticated vendor's supplier ID against the invoice record and requires the stored URI to be under that supplier's own prefix before generating a presigned `GetObject` URL. Links expire after five minutes. Keep the bucket private; a presigned URL is a temporary bearer link and should not be logged or shared.

## Production rollout checklist

1. Confirm the intended bucket name and its actual AWS region.
2. Confirm the EC2 instance profile role attached to the backend host.
3. Apply the bucket security settings and the narrowly scoped role policy.
4. Add `SB_PRIVATE_DOCUMENT_BUCKET` and `SB_S3_REGION` to the backend service environment without exposing credentials.
5. Restart the backend service during an approved deployment window.
6. Test an authenticated supplier upload, invoice attachment retrieval, expired link behavior, and cross-supplier access denial.
7. Confirm the object is private and encrypted, and that no static AWS access keys were introduced.

This document describes application integration requirements; it does not claim that an S3 bucket, IAM policy, or production environment has already been configured.
