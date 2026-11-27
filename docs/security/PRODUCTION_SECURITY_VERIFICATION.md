# Production security verification

## Scope

The automated CI security workflow covers Python dependency advisories, Bandit static analysis, npm dependency advisories and Gitleaks history scanning. Frontend staff/customer bearer tokens are now moved from persistent localStorage to tab-scoped sessionStorage (existing tokens migrate once and are removed from localStorage). This reduces persistence after the browser tab session ends; it does not make tokens inaccessible to same-origin JavaScript or remove the need for frontend XSS controls. State-changing API requests with an Origin header are checked against configured/owned origins, and OAuth state uses an HttpOnly, Secure, SameSite=Lax nonce cookie. It does not prove the security posture of the live EC2 host, PostgreSQL instance, S3 bucket, instance profile, security groups or TLS endpoint.

## Read-only AWS host audit

The repository includes `scripts/security/read_only_aws_audit.sh`. It checks the running backend service, host listeners, Nginx TLS/security directives, PostgreSQL role attributes and grants, EC2 IMDSv2 and attached IAM policies, and S3 public-access/encryption/versioning/lifecycle controls.

Run it only through an authorized SSM Run Command session on the production EC2 instance:

```bash
sudo bash /opt/superbajaar/source/scripts/security/read_only_aws_audit.sh
```

If the deployed checkout does not yet contain this branch, first transfer the script through an approved deployment process; do not pull or deploy this security branch directly to production just to run the audit.

The script:
- Does not change AWS resources, database grants, service configuration or application files.
- Does not print environment variable values, database credentials, JWT secrets, Razorpay secrets or AWS credentials.
- May report `SKIP` when the EC2 instance profile lacks read permissions for IAM/S3/EC2 metadata APIs. A skip is not a pass.
- Prints host, role and bucket identifiers; keep the output private and redact identifiers before sharing externally.

## Required manual verification

An authorized AWS administrator must verify:
1. EC2 security group ingress is limited to required ports; PostgreSQL 5432 is not internet-accessible.
2. EC2 instance profile has least-privilege access only to the required S3 bucket prefixes, SSM and required operational APIs.
3. S3 Block Public Access is enabled at account and bucket level; bucket policy does not grant public access; default encryption is enabled; versioning and lifecycle/backup retention meet recovery requirements.
4. IMDSv2 is required and hop limit is appropriate.
5. EBS volumes and snapshots are encrypted; backups are encrypted and restore-tested.
6. Nginx terminates TLS with modern protocols, forwards the original client IP safely, applies request/body/time limits, and does not expose the backend listener.
7. PostgreSQL application role is not superuser, cannot create roles/databases, owns only required objects and has no unnecessary PUBLIC grants.
8. CloudTrail, GuardDuty and relevant alerting are enabled and monitored.

## Database migration gate

Migrations `067_distributed_api_rate_limits.sql` and `068_payment_idempotency.sql` are additive and are listed in `backend/schema_required.txt`. They must be applied through the existing schema automation after backup and staging verification. The application must not be deployed before both required migrations are confirmed applied. Manual payment creation must send an actor-scoped `Idempotency-Key`; the Payments workspace keeps the same key across retries and resets it when the payment payload changes.

## Verification boundary

A source-code review or successful CI run is not a live infrastructure certification. Record the SSM command ID, execution time, instance ID, region, command status and redacted output as the evidence for the production audit. Any missing permission, failed check or skipped control must remain open until independently verified.
