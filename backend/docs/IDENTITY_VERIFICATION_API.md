# Identity verification API

These endpoints are additive. Existing customer registration, login, staff login, and identity administration routes remain unchanged.

## Customer email verification

All routes require an active customer bearer session.

- `POST /api/customer-auth/identity-verification/otp/request` — sends a five-minute email OTP to the signed-in customer's own account email. The shared Resend test sender remains restricted to its configured test recipient.
- `POST /api/customer-auth/identity-verification/otp/verify` — verifies the challenge and records the customer's email as a verified SBID contact. Codes are single-use, limited to five attempts, and rate-limited to five requests per contact per hour.

## Existing-SBID claim confirmation

The target identity owner, not the claimant, must confirm the claim.

1. The target customer verifies their own email using the email verification endpoints above.
2. `GET /api/customer-auth/identity-verification/claims/pending` lists claims addressed to that customer's SBID without exposing claimant or identity details.
3. `POST /api/customer-auth/identity-verification/claims/{request_id}/otp/request` sends an OTP to the target identity's verified email.
4. `POST /api/customer-auth/identity-verification/claims/{request_id}/otp/verify` records `email_otp` proof and moves the request to the administrator review queue.
5. An administrator reviews and approves or rejects the request through the existing identity review queue. The API rejects `email_otp` approval unless the target-owner OTP proof is persisted.

If the target SBID has no customer login, the customer OTP flow cannot confirm it; an administrator must use the existing documented/manual proof process. Exact-contact matches alone never authorize a link or merge.

## Private identity evidence

- `POST /api/customer-auth/identity-verification/documents` — uploads PDF/JPEG/PNG evidence (maximum 10 MB) for the signed-in customer's own SBID.
- `GET /api/customer-auth/identity-verification/documents/{document_id}/download` — issues a five-minute presigned URL only for the customer's own evidence.
- `GET /api/identity/documents/review-queue` — administrator-only pending evidence queue.
- `GET /api/identity/documents/{document_id}/download` — administrator-only five-minute presigned download.
- `POST /api/identity/documents/{document_id}/review` — administrator-only accept/reject decision with a reason and audit event.

Files are stored in the existing private S3 bucket with AES256 server-side encryption. PostgreSQL stores metadata and object keys only. No public ACL or permanent public URL is created.

## Configuration and deployment

Set `IDENTITY_OTP_HMAC_SECRET` to a random secret of at least 32 characters. Email delivery reuses the existing Resend configuration. Private evidence reuses `SB_PRIVATE_DOCUMENT_BUCKET` and the EC2 IAM role.

Migration `046_identity_otp_verification.sql` is additive and must be applied only through the repository's separately approved schema migration process. CI does not apply migrations, send real email, or write to S3.
