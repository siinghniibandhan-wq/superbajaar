# Production deployment automation

## Trigger and release scope

The authoritative trigger configuration is `.github/workflows/deploy.yml`.

- Pull requests targeting `main` run source verification only; deployment jobs do not run for pull-request events.
- Pushes to `main` start this workflow only when configured application paths change. Documentation-only and schema-only pushes are excluded by the push path filter.
- Manual workflow dispatch is also supported and must be treated as a production-capable operation.

For a qualifying application push, the workflow runs backend tests/compile, admin tests, both frontend production builds, Gitleaks and Semgrep. Only after verification does GitHub Actions assume the configured AWS role through OIDC and ask the EC2 instance to deploy the exact commit using Systems Manager (SSM). The separate [environment and CI/CD guide](../ENVIRONMENTS_AND_CICD.md) documents every workflow and trigger.



The EC2 script fast-forwards the existing `/opt/superbajaar/source` checkout, installs backend requirements into the service's existing virtualenv, compiles the backend, restarts only `superbajaar-backend.service`, and checks the public API health endpoint plus the HR attendance-corrections route. A failed deployment attempts to restore the previous Git commit, reinstall its requirements, restart the service and verify health. The 12 November 2026 EC2 diagnostic confirmed that `superbajaar-backend.service` is the installed, active production unit; `superbajaar-new.service` is not installed.

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

- Repository secret `AWS_ROLE_TO_ASSUME`: IAM role ARN trusted by GitHub Actions OIDC.
- Repository variable `AWS_REGION`: AWS region containing EC2 and Amplify.
- Repository variable `EC2_INSTANCE_ID`: target EC2 instance ID.
- Repository variable `AMPLIFY_SITE_URL`: public production Amplify URL.
- Repository variable `AMPLIFY_APP_ID`: exact Amplify Hosting app ID (format starts with `d`).
- The Amplify production branch is currently configured as `main` in the workflow. The deployment jobs intentionally do not bind to a GitHub Environment: the IAM trust policy is restricted to the exact OIDC subject `repo:siinghniibandhan-wq/superbajaar:ref:refs/heads/main`, and attaching a GitHub Environment changes the OIDC subject to an environment-based subject.

The GitHub OIDC role needs the existing SSM permissions plus the narrowly scoped Amplify permissions shown in `docs/operations/amplify-rollback-iam-policy.json`. Replace the placeholders in that policy with the account ID, region, and app ID, then add the statement to the existing `SuperBajaarGitHubDeployPolicy`. Do not replace the existing SSM statement. The EC2 instance profile and SSM agent configuration remain unchanged.

The EC2 instance must allow the `ubuntu` user to restart `superbajaar-backend.service` without an interactive password.

## EC2 preflight (one-time)

The backend deployment script deliberately fails closed unless:

- checkout exists at `/opt/superbajaar/source`, is on `main`, and is clean;
- `superbajaar-backend.service` is active and its WorkingDirectory is exactly `/opt/superbajaar/source/backend`;
- the service ExecStart uses the existing backend virtual environment (the 12 November 2026 diagnostic observed `/opt/superbajaar/source/backend/venv/bin/gunicorn`).

If the current unit uses a different layout, adapt the deployment script to the actual unit before enabling production deployment. Do not guess or change the service unit blindly.

## Amplify trigger boundary

The GitHub `deploy.yml` path filter controls when its verification/monitoring workflow starts; it does not configure AWS Amplify's native connected-repository auto-build trigger. The repository root listing reviewed on 12 November 2026 did not contain an `amplify.yml` build specification. Confirm Amplify's connected branch, build settings and any monorepo/path-ignore rules in the AWS Amplify console. Until that is verified, do not promise that a docs-only commit can never start an Amplify build.

The EC2 `main` auto-sync timer documented in [GitHub main auto-sync](GITHUB_MAIN_AUTO_SYNC.md) updates the source checkout only. It does not build, migrate or restart the application service.

## Database safety

This workflow never runs SQL migrations or schema apply commands. Existing schema governance and the status-only migration timer remain separate and unchanged.

## Recovery limitations

Amplify rollback retries a prior successful job, so it relies on the source commit remaining available in the connected Git repository and on Amplify being able to rebuild that commit. It retains current Amplify environment settings. If the previous build is no longer available or its source cannot be retrieved, the workflow fails and reports that manual recovery is required. No production database migration is attempted by this pipeline.


## Verified EC2 runtime snapshot — 12 November 2026

A read-only host diagnostic at 06:46 UTC reported:

| Item | Observed state |
|---|---|
| Production backend unit | `superbajaar-backend.service` — loaded, active, running |
| Legacy unit name | `superbajaar-new.service` — not found |
| Backend working directory | `/opt/superbajaar/source/backend` |
| Runtime user | `ubuntu` |
| Gunicorn executable | `/opt/superbajaar/source/backend/venv/bin/gunicorn` |
| Bind address | `127.0.0.1:8001` |
| Git branch / checkout | `main` at `bf01a6d40ec5801cdb3ba98a99e410b421411c5d` |
| Git sync timer | Active; latest observed sync exited 0 and found checkout current with `origin/main` |
| Git object directory | Writable by `ubuntu` |

This is a timestamped observation, not a guarantee of current state. Re-run the read-only host checks before an operational change. Do not use the legacy `superbajaar-new.service` name in deployment commands or runbooks unless a future verified host configuration actually installs it.


---

## Last-good backend rollback reference — 12 November 2026

The backend deployment script now persists the last verified deployment SHA in the EC2 checkout under `refs/deploy/last-good`. This change was merged in PR #63, commit `4580ad3f2ed2155ba466932b2ac0bad229a5b0f1`.

### Why the ref is required

The two-minute source-sync timer can fast-forward `/opt/superbajaar/source` before the deployment workflow acquires the shared lock. The lock prevents simultaneous operations but does not enforce scheduling order. If deployment used current `HEAD` as its rollback point after sync had advanced it, rollback could target the same failing revision.

### Behaviour

- At deployment start, use `refs/deploy/last-good` if present.
- If no ref exists, fall back to `HEAD` (first-deployment behaviour).
- Deploy the exact target SHA, install dependencies, compile, restart `superbajaar-backend.service`, and run health plus HR-route checks.
- On failure, reset to the saved last-good SHA, restore dependencies, restart the service and check health.
- Only after all checks pass, update `refs/deploy/last-good` to the verified `HEAD`.

The ref is saved in the EC2 Git repository; it is not a database backup and does not reverse schema changes.

### Live verification checklist

The fix being merged is not proof that it has been exercised successfully in production. Confirm the GitHub `Deploy Super Bajaar backend` run and that its EC2 SSM job actually ran (not skipped). Then inspect:

```bash
sudo -u ubuntu git -C /opt/superbajaar/source rev-parse HEAD
sudo -u ubuntu git -C /opt/superbajaar/source rev-parse refs/deploy/last-good
sudo systemctl is-active superbajaar-backend.service
curl --fail --silent --show-error https://superappkart.duckdns.org/api/health
```

The first successful deployment after this change establishes the ref; before it exists, the script falls back to `HEAD`. As of the owner report dated 12 November 2026, the run result for commit `4580ad3` and the server values were still unverified. Do not report the fix as live until those checks are recorded.

See [Production governance and readiness](../PRODUCTION_GOVERNANCE_AND_READINESS.md) for the consolidated accepted risks and open verification list.
---

## Verified production deployment snapshot — 12 November 2026

This section records the read-only EC2 diagnostics and owner-supplied Amplify console screenshot from 12 November 2026. It supersedes older runtime snapshots where they conflict; those snapshots remain historical.

### EC2 source and backend runtime

- Checkout: `/opt/superbajaar/source`
- EC2 `HEAD`: `9b7980954cf0550383e8c34b2fcd89be219bc17a`
- `origin/main`: same SHA.
- Service: `superbajaar-backend.service`, active/running.
- Working directory: `/opt/superbajaar/source/backend`.
- Local and public `/api/health`: HTTP 200; both return `{"status":"ok","database":"connected"}`.

The checkout's `refs/deploy/last-good` points to `4580ad3f2ed2155ba466932b2ac0bad229a5b0f1`. Comparing that ref with `HEAD` showed only documentation files changed; the comparison restricted to deployment-relevant application paths was empty. Do not move the ref merely to match a docs-only `main` commit. It records the last verified backend application release.

### Database status automation (deployment-adjacent operational check)

The installed timer is `superbajaar-schema.timer`, not `sb-schema.timer`. It is enabled and active with `OnCalendar=*:0/2` (every two minutes). It triggers the static oneshot `superbajaar-schema.service`, whose effective command runs `apply_schema.sh ... --status`. Its last observed run completed with exit 0 / SUCCESS. An oneshot service being inactive/dead after successful completion is expected; the timer remains active.

The runner reported all 40 current SQL files as APPLIED. The production ledger contains 41 rows because it retains the historical `036_super_admin_role.sql` entry in addition to current `036_configurable_rbac.sql`. Git history confirms the former was introduced in commit `7308938e7a811a4486079a65c8e6e11d82615103` and removed in `5dbe8cf2a1ee9602953f92bce1cee60897a2c67`. Current schema filenames have no duplicate numeric prefixes.

The current baseline file and its production ledger checksum both equal `519e4467a6af9c1f87dd06cbdb80ef4545b1ae04edfe8937966799792168d938`. A failure-table row with older checksum `f95b15efed9e49e11e85bcf1786ae89ff10d29a60bb44774eedca3d82813a578` is retained as historical evidence and is not a current baseline mismatch.

Migration `045_identity_claim_cancellation_event.sql` is APPLIED; its ledger SHA-256 is `874886ce7aae2bc6c4f541e95f63bf231ac06b187a62aeb94cef6f58cbf2b948`. The status runner exited 0. The timer is status-only; it does not authorize or automatically apply migrations.

### Amplify deployment observed in console

The owner-provided AWS Amplify screenshot shows deployment 113 with status **Deployed**, repository/branch `superbajaar:main`, and a commit message beginning “Merge pull request #65”. The displayed production branch domain is:

`https://main.d334sr8jkx3zux.amplifyapp.com`

The console shows a deployment start of 12 Nov 2026, 15:28 (timezone not independently confirmed), build duration 1 minute 4 seconds and deploy duration 42 seconds.

This confirms the Amplify console reported deployment 113 as deployed for the connected main branch. It also shows a deployment associated with docs-only PR #65, even though the GitHub Actions `deploy.yml` push path filter excludes docs-only changes. Amplify's connected-repository build trigger is separate from the GitHub backend deployment workflow.

The screenshot does not expose the exact commit SHA, app ID, native auto-build setting, build specification/app root, or prove that the live storefront and admin routes are functionally correct. These remain open. The owner has AWS RunShell access, not AWS CloudShell; do not ask them to run CloudShell-only CLI commands.

No deployment, restart, migration, timer change, IAM change or AWS infrastructure mutation was performed as part of this audit.
