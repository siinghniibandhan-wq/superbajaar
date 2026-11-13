# Identity verification — PR #84 production status

**Status date:** 14 November 2026  
**Scope:** Evidence collected during the PR #84 production readiness check.  
**PR:** [#84 — Add Resend OTP and private S3 identity evidence foundation](https://github.com/siinghniibandhan-wq/superbajaar/pull/84)  
**Merge commit:** `9c0f20c03859e30e60827e86b008e704dd0c3eee`

This document records only the checks completed in this session. It is not a production-readiness approval.

## Confirmed

### Database

- Production database checked: `superbajaar`.
- Migration runner status listed `046_identity_otp_verification.sql` as `APPLIED`.
- A read-only PostgreSQL check confirmed both relations exist:
  - `public.identity_otp_challenges`
  - `public.identity_verification_documents`

### Backend runtime and source presence

- `superbajaar-backend.service` reported `active (running)`.
- The service's health endpoint returned HTTP 200 in the supplied service log.
- The EC2 source checkout contains:
  - `backend/app/api/customer_identity_verification.py`
  - `backend/app/api/identity.py`
- The source search found OTP challenge and identity document database operations in those files.
- These observations establish that the files are present in the checkout and the service is running. They do not independently prove which commit the running Gunicorn workers loaded.

### OTP secret configuration

- The operator reported that the command to generate and write `IDENTITY_OTP_HMAC_SECRET` and restart `superbajaar-backend.service` completed with exit/error code 0.
- The secret value was not displayed or recorded in this document.
- The Resend API key was found configured in the environment files.

## Not yet verified

- No verified sending domain or production sender address was identified.
- The Resend sender address is therefore unresolved.
- No live OTP request was completed and no delivered OTP email was observed.
- Arbitrary customer email delivery has not been demonstrated.
- No end-to-end S3 evidence upload or download was performed.
- No end-to-end administrator evidence review was performed.
- Customer-facing and admin frontend integration was not verified in this check.
- The running service's exact deployed commit was not independently checked.

## OTP behaviour documented by the implementation

The customer OTP endpoint requires an active customer bearer session and sends to the email address on that signed-in customer's account. The backend generates a six-digit code, stores a digest rather than the plaintext code, and calls the configured Resend delivery integration. The documented challenge lifetime is five minutes, with single-use verification, a maximum of five attempts, and a limit of five requests per contact per hour.

Relevant API routes:

- `POST /api/customer-auth/identity-verification/otp/request`
- `POST /api/customer-auth/identity-verification/otp/verify`

The Resend test sender `onboarding@resend.dev` is restricted to its permitted test recipient. This is not evidence of production customer delivery.

## Remaining verification

1. Resolve a sender/domain configuration accepted by Resend for production use.
2. Send an OTP to a real customer account email and verify the received code.
3. Verify private S3 evidence upload and party-scoped download.
4. Verify administrator review queue, secure download, accept/reject, and audit event.
5. Independently confirm the running backend release/commit and frontend route integration.

## Safety boundary

This status record does not authorize a deployment, migration, DNS change, email configuration change, S3 operation, or other production modification. Do not record API keys, HMAC secrets, OTP values, or other credentials in documentation or logs.
