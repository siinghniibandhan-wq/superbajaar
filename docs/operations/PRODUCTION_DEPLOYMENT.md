# Production deployment automation

## What happens

A push to `main` runs backend tests/compile, admin tests, both frontend production builds, Gitleaks and Semgrep. Only after verification does GitHub Actions assume the configured AWS role through OIDC and ask the EC2 instance to deploy the exact commit using Systems Manager (SSM).

The EC2 script fast-forwards the existing `/opt/superbajaar/source` checkout, installs backend requirements into the service's existing virtualenv, compiles the backend, restarts only `superbajaar-new.service`, and checks the public API health endpoint plus the HR attendance-corrections route. A failed deployment attempts to restore the previous Git commit, reinstall its requirements, restart the service and verify health.

## Amplify publish protection and automatic recovery

Amplify Hosting uses atomic deployments: it updates the hosted application only after the deployment is complete. A failed build/deployment job is not published as the live website; the previously successful version normally remains live. This is the first protection layer, not a substitute for checking the live site after deployment.

The root Vite build embeds the Amplify-provided `AWS_COMMIT_ID` in `<meta name="sb-release">` (AWS documents this variable as the current build's commit ID). GitHub Actions then:

1. Finds the Amplify job for the exact pushed Git commit and records the latest earlier successful job as the rollback target.
2. Waits for the current Amplify job to finish.
3. Checks the live HTML release marker against the expected commit and downloads every referenced JavaScript/CSS asset to verify that each is reachable.
4. If the Amplify job failed, the previous version should still be live; if the new version published but fails the health check, it starts a retry of the recorded previous successful job.
5. Waits for the rollback job to succeed and repeats the release-marker and asset checks against the previous commit.

The workflow fails closed if it cannot identify a previous successful job or cannot prove that the restored release is healthy. The first rollback may target a pre-marker release from before this feature was introduced; in that one-time case, the previous successful Amplify job is pinned to the exact commit and its HTML plus all static bundles are checked, while subsequent rollbacks also require an exact HTML commit marker. It never treats an HTTP 200 homepage alone as proof of a healthy release. This HTTP-level verification checks the deployed HTML and static bundles; it does not prove every interactive user journey or backend integration.

## One-time GitHub configuration

Set these repository/environment values:

- Production environment secret `AWS_ROLE_TO_ASSUME`: IAM role ARN trusted by GitHub Actions OIDC.
- Repository variable `AWS_REGION`: AWS region containing EC2 and Amplify.
- Repository variable `EC2_INSTANCE_ID`: target EC2 instance ID.
- Repository variable `AMPLIFY_SITE_URL`: public production Amplify URL.
- Repository variable `AMPLIFY_APP_ID`: exact Amplify Hosting app ID (format starts with `d`).
- The Amplify production branch is currently configured as `main` in the workflow.

The GitHub OIDC role needs the existing SSM permissions plus the narrowly scoped Amplify permissions shown in `docs/operations/amplify-rollback-iam-policy.json`. Replace the placeholders in that policy with the account ID, region, and app ID, then add the statement to the existing `SuperBajaarGitHubDeployPolicy`. Do not replace the existing SSM statement. The EC2 instance profile and SSM agent configuration remain unchanged.

The EC2 instance must allow the `ubuntu` user to restart `superbajaar-new.service` without an interactive password.

## EC2 preflight (one-time)

The backend deployment script deliberately fails closed unless:

- checkout exists at `/opt/superbajaar/source`, is on `main`, and is clean;
- `superbajaar-new.service` is active and its WorkingDirectory is the repository root or `backend/`;
- the service ExecStart uses an existing `.venv` at `backend/.venv` or repository `.venv`.

If the current unit uses a different layout, adapt the deployment script to the actual unit before enabling production deployment. Do not guess or change the service unit blindly.

## Database safety

This workflow never runs SQL migrations or schema apply commands. Existing schema governance and the status-only migration timer remain separate and unchanged.

## Recovery limitations

Amplify rollback retries a prior successful job, so it relies on the source commit remaining available in the connected Git repository and on Amplify being able to rebuild that commit. It retains current Amplify environment settings. If the previous build is no longer available or its source cannot be retrieved, the workflow fails and reports that manual recovery is required. No production database migration is attempted by this pipeline.
