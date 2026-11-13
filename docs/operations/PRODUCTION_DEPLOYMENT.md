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

AWS Amplify's connected application is configured in the Amplify Console as a monorepo application with `appRoot: frontend`. Its build specification runs `npm install`, then `npm run build`, and publishes `dist` relative to that app root (repository path `frontend/dist`). The root Vite project is a compatibility build; it is not the artifact Amplify publishes.

The canonical `frontend/vite.config.js` injects the Amplify-provided `AWS_COMMIT_ID` into `<meta name="sb-release">`. The root Vite build retains its own release marker for compatibility-build verification. GitHub Actions checks the marker in both generated build outputs; its live Amplify check compares the published HTML marker with the exact pushed commit SHA.

For an eligible `main` application release, GitHub Actions then:

1. Finds the Amplify job for the exact pushed Git commit and records the latest earlier successful job as the rollback target.
2. Waits for the current Amplify job to finish.
3. Checks the live HTML release marker against the expected commit and downloads every referenced JavaScript/CSS asset to verify that each is reachable.
4. If the Amplify job failed, the previous version should still be live; if the new version published but fails the health check, it starts a retry of the recorded previous successful job.
5. Waits for the rollback job to succeed and repeats the release-marker and asset checks against the previous commit.

The workflow fails closed if it cannot identify a previous successful job or cannot prove that the restored release is healthy. The first rollback may target a pre-marker release from before this feature was introduced; in that one-time case, the previous successful Amplify job is pinned to the exact commit and its HTML plus all static bundles are checked, while subsequent rollbacks also require an exact HTML commit marker. It never treats an HTTP 200 homepage alone as proof of a healthy release. This HTTP-level verification checks the deployed HTML and static bundles; it does not prove every interactive user journey or backend integration.

### Release-marker incident and verified correction — 12 November 2026

The production verification failure was caused by a build-target mismatch: CI originally checked the root compatibility build's release marker, while Amplify publishes the canonical `frontend/` build. The live HTML therefore lacked the marker expected by the deployment health check, even though the Amplify build job itself had succeeded.

PR [#67](https://github.com/siinghniibandhan-wq/superbajaar/pull/67), merged as commit `58ee8e2a64ad844cc45afdb02803c81c6c66a3b1`, corrected this by adding the release marker to `frontend/vite.config.js` and checking `frontend/dist/index.html` in CI. The root compatibility build and its existing marker check remain in place.

The subsequent main-branch deployment run [#43206976831](https://github.com/siinghniibandhan-wq/superbajaar/actions/runs/43206976831) completed successfully: source verification passed, the EC2 SSM backend deployment job succeeded, Amplify job `116` reported `SUCCEED`, the live HTML marker matched the target commit, and both referenced JavaScript/CSS assets were verified. Automatic rollback was skipped. No database migration was part of this release.

The separate documentation-governance workflow for the PR #67 merge failed because the implementation/workflow change did not include a documentation update in the same PR. This documentation-only follow-up records the release-marker design and incident resolution.

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


---

## AWS-native three-lane auto-deployment — 13 November 2026

**Current configuration supplied by the project owner.** This section is the current operating description and supersedes older statements in this file that describe the schema timer as status-only/manual or the backend as deployed only through GitHub Actions/SSM. Historical verification snapshots below remain records of the configuration observed at their timestamps. This documentation change did not connect to EC2, inspect live AWS settings, execute a deployment or change infrastructure.

### Environment identity

| Item | Supplied configuration |
|---|---|
| AWS region | `us-east-1` (N. Virginia) |
| EC2 instance | `i-08814a9225c19ee91` |
| EC2 instance role | `SuperBajaar-EC2-Role` |
| Linux service user | `ubuntu` |
| Repository checkout | `/opt/superbajaar/source` |
| Deployment branch | `main` |
| AWS account | `715975223136` |
| Backend runtime | `superbajaar-backend.service`, health URL `http://127.0.0.1:8001/api/health` |

### Lane A — GitHub source synchronization (unchanged)

- Timer: `superbajaar-github-sync.timer` (existing timer, left unchanged).
- Script: `backend/scripts/sync_main.sh`.
- Action: fetch `origin/main` and fast-forward only when the checkout is clean and on the expected branch.
- It does not build, apply migrations, deploy backend code or restart services.
- A dirty checkout blocks synchronization/deployment; never edit files directly under `/opt/superbajaar/source` on the server.

### Lane B — automatic database schema apply (updated)

- Timer: `superbajaar-schema.timer`, scheduled `OnCalendar=*:0/2` (even minutes).
- Service: `superbajaar-schema.service`, run as `ubuntu`.
- Drop-in: `/etc/systemd/system/superbajaar-schema.service.d/override.conf`.
- Previous drop-in backup: `override.conf.bak-20261113T002237Z`.
- Runs `/opt/superbajaar/source/backend/scripts/apply_schema.sh` in APPLY mode, with `SB_ON_FAILURE=stop`; it is no longer a `--status`-only timer.
- After each run, `sb-db-lane-post.sh` copies newly created backups to S3 and ships new log lines.
- The schema lane does not restart the backend.

Runner v2 compares every `backend/schema/*.sql` file with `schema_migrations` by filename and SHA-256. It requires a verified backup before changing the database; applies each file and its ledger record in one transaction; records failures in `schema_migration_failures`; suppresses repeat attempts for unchanged failed content; and never reapplies an applied file whose contents have changed. It stops for duplicate numeric prefixes, invalid `NNN_name.sql` filenames, or table names duplicated across schemas. A lock at `/tmp/sb_schema.lock` prevents concurrent runs. `SB_ON_FAILURE=stop` halts on the first failed file. A post-apply check calls `http://127.0.0.1:8001/api/health`.

Local backups are stored in `/var/lib/superbajaar/backups`, retained for 14 days with at least the three newest preserved. New backups are copied to the private S3 bucket `superbajaar-db-backups-715975223136-715975223136-us-east-1-an`; the supplied bucket lifecycle expires objects after 30 days. Upload success and object readability still need to be checked in operational evidence.

### Lane C — automatic backend deployment (new)

- Timer/service: `superbajaar-backend-deploy.timer` / `superbajaar-backend-deploy.service`.
- Timer schedule: `OnCalendar=*:1/2` (odd minutes).
- Script: `/usr/local/bin/sb-backend-lane.sh`.
- Mode file: `/etc/default/superbajaar-backend-lane`.
- Active mode: `SB_BACKEND_LANE_MODE=live`. The alternative `report` mode is test/report-only and deploys nothing.
- Timeout: 15 minutes.
- Previous script backup: `/usr/local/bin/sb-backend-lane.sh.bak-20261113T005650Z`.

Each backend-lane run takes its lock, fetches `origin/main`, and compares the fetched commit with `refs/deploy/last-good` (the currently running/last verified backend version). It examines changes under `backend/` while excluding `backend/schema/`. It skips when no backend application changes exist or when the target SHA is listed in `backend-failed-shas.txt`.

If the target commit's `backend/schema_required.txt` lists a migration not yet present in `schema_migrations`, the lane waits/skips that deployment attempt; the next scheduled run retries after the schema lane has had time to apply it. Once the required migrations are present, the lane calls:

```bash
deploy_backend.sh <target-sha>
```

The deployment script fast-forwards to the exact SHA, installs backend requirements, runs a compile check, restarts `superbajaar-backend.service`, and checks the health endpoint (18 attempts, 5 seconds apart) plus the HR route (2xx, 401 or 403 are accepted). If any check fails, it restores the prior code, reinstalls the prior dependencies, restarts the service and checks the old version's health. A failed target SHA is recorded and is not retried; a later new commit can be attempted normally. On success, `refs/deploy/last-good` is advanced.

First reported automatic deployment: commit `30e38fc` at 00:47 UTC on 13 November 2026; the previously running backend commit was `f77b07c`. This is owner-supplied deployment history, not an independently verified live release record in this documentation PR.

### End-to-end sequence

```text
GitHub push to main
  -> source sync timer (every 2 minutes)
  -> schema apply timer (even minutes)
  -> backend deploy timer (odd minutes)
       -> wait until schema_required files are in schema_migrations
       -> deploy exact backend commit
       -> health + HR route checks
       -> rollback to previous code/dependencies if checks fail
```

The expected end-to-end delay is approximately 2–4 minutes, not a strict service-level guarantee. Long migrations, lock contention, a dirty checkout, failed backup, required-file mismatch or a failed backend health check can extend or stop the release.

### AWS backup and log shipping

| Resource | Supplied configuration |
|---|---|
| S3 bucket | `superbajaar-db-backups-715975223136-715975223136-us-east-1-an` (private) |
| S3 lifecycle | 30-day object expiration |
| CloudWatch log group | `/superbajaar/backend-deploy` |
| CloudWatch log group | `/superbajaar/db-migration` |
| Intended log retention | 90 days; actual setting still requires verification |
| Instance role | `SuperBajaar-EC2-Role` |
| Inline policy | `SuperBajaar-Deploy` |
| Reported log actions | `logs:CreateLogStream`, `logs:PutLogEvents` on `/superbajaar/*` |
| Reported S3 actions | `s3:PutObject`, `s3:GetObject` on `superbajaar-db-backups-*/*` |
| AWS CLI | v2 at `/usr/local/bin/aws` |

SNS email alerts and a DynamoDB run-history table were not created. The supplied setup notes identify harmless leftovers `test/sb-test.txt` in the bucket and the CloudWatch stream `setup-test`. The S3 bucket name, IAM policy scope, actual CloudWatch retention and successful backup/log uploads should be verified against AWS before being treated as independently audited facts.

### Monitoring commands (read-only)

```bash
systemctl list-timers --all | grep superbajaar
tail -n 30 /var/lib/superbajaar/lane-state/backend-deploy.log
tail -n 30 /var/log/superbajaar/schema.log
curl -s http://127.0.0.1:8001/api/health
```

For sync-specific diagnostics, use the [GitHub main auto-sync runbook](GITHUB_MAIN_AUTO_SYNC.md). These commands read state; they do not trigger deployment or migration.

### Emergency lane controls

Disable only the affected lane:

```bash
sudo systemctl disable --now superbajaar-backend-deploy.timer
sudo systemctl disable --now superbajaar-schema.timer
```

Re-enable the selected lane with:

```bash
sudo systemctl enable --now superbajaar-backend-deploy.timer
sudo systemctl enable --now superbajaar-schema.timer
```

The GitHub sync lane has its own timer and is not disabled by either command. Disabling a timer does not roll back code or database changes already completed.

To restore the previous backend-lane script, first preserve the current script and inspect the backup timestamp, then use the supplied backup path:

```bash
sudo cp /usr/local/bin/sb-backend-lane.sh.bak-20261113T005650Z /usr/local/bin/sb-backend-lane.sh
```

Do not select a backup by wildcard without checking which file is newest and appropriate. Reload/restart behaviour should follow the actual installed unit/script procedure; this document does not prescribe an unverified service mutation.

### Known limits and accepted operational risks

- No SNS/email alerting is configured; failures are visible in local logs and CloudWatch only if shipping succeeds.
- Storefront/frontend deployment is not part of these EC2 lanes; Amplify is separate.
- Backend rollback catches startup/health/HR-route failures, not incorrect business behaviour that still returns acceptable responses.
- The HR route check can cause rollback; it is not warning-only.
- Any change under `backend/` other than `backend/schema/` may trigger a backend restart, including tests or documentation stored under backend.
- Migration lock waiting has no configured maximum; a heavy migration on a busy table may temporarily affect store performance.
- After a failed backend deployment, the bad commit can remain in the checkout because sync continues to fetch it; the running service should be restored to the prior version.
- Report mode does not deploy. Confirm `SB_BACKEND_LANE_MODE=live` before interpreting a lane run as a production deployment.
- A timer being enabled is not proof that its latest service run succeeded. Inspect logs, ledger state, current running commit and health separately.

### Repository and production boundary

The scripts, units, mode file, IAM policy, S3 bucket and CloudWatch groups described in this section are supplied as server-side configuration. The owner states that no corresponding files were changed in GitHub as part of the infrastructure setup. Do not create repository copies or alter the server configuration merely to make documentation match. Never hand-edit files under `/opt/superbajaar/source`; changes must arrive through the clean fast-forward sync from `main`.

For the canonical database safety rules, see [Database migrations](../DATABASE_MIGRATIONS.md). For source synchronization details, see [GitHub main auto-sync](GITHUB_MAIN_AUTO_SYNC.md). For the broader release model, see [Environments and CI/CD](../ENVIRONMENTS_AND_CICD.md).
