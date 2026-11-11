# Production deployment automation

## What happens
A push to `main` runs backend tests/compile, admin tests, both frontend production builds, Gitleaks and Semgrep. Only after verification does GitHub Actions assume the configured AWS role through OIDC and ask the EC2 instance to deploy the exact commit using Systems Manager (SSM).

The EC2 script fast-forwards the existing `/opt/superbajaar/source` checkout, installs backend requirements into the service's existing virtualenv, compiles the backend, restarts only `superbajaar-new.service`, and checks the public API health endpoint plus the HR attendance-corrections route. A failed deployment attempts to restore the previous Git commit, reinstall its requirements, restart the service and verify health.

Amplify is checked independently using `AMPLIFY_SITE_URL`. This confirms that the configured site is serving HTML; it does not claim that Amplify's deployed commit matches the GitHub SHA.

## One-time GitHub configuration
Set these repository/environment values:
- Production environment secret `AWS_ROLE_TO_ASSUME`: IAM role ARN trusted by GitHub Actions OIDC.
- Repository variable `AWS_REGION`: AWS region containing the EC2 instance.
- Repository variable `EC2_INSTANCE_ID`: target EC2 instance ID.
- Repository variable `AMPLIFY_SITE_URL`: public Amplify URL.

The IAM role needs only SSM send-command and command-status permissions scoped to the target instance/document. The EC2 instance profile must allow SSM command execution. The instance must have the AWS SSM agent online and allow the `ubuntu` user to restart `superbajaar-new.service` without an interactive password.

## EC2 preflight (one-time)
The script deliberately fails closed unless:
- checkout exists at `/opt/superbajaar/source`, is on `main`, and is clean;
- `superbajaar-new.service` is active and its WorkingDirectory is the repository root or `backend/`;
- the service ExecStart uses an existing `.venv` at `backend/.venv` or repository `.venv`.

If the current unit uses a different layout, adapt the deployment script to the actual unit before enabling production deployment. Do not guess or change the service unit blindly.

## Database safety
This workflow never runs SQL migrations or schema apply commands. Existing schema governance and the status-only migration timer remain separate and unchanged.

## Limitations
Rollback restores application source/dependencies and restarts the previous code. It cannot reverse a database migration or external side effect; this pipeline intentionally does not apply migrations. The Amplify check verifies availability only, not commit identity.
