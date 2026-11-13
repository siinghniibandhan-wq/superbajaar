# Production governance, deployment and recovery

> **Canonical operational snapshot — 12 November 2026**  
> **Status:** Owner-approved decisions recorded; several live checks remain outstanding.  
> **Scope:** GitHub release controls, AWS deployment access, production database migration governance, backup evidence and rollback.  
> **Approval boundary:** This document records decisions and procedures. It does not authorize a production deployment, database restore, IAM change or infrastructure mutation.

## Executive status

Super Bajaar has three distinct execution contexts: local development, ephemeral GitHub Actions CI, and production. CI is not staging. Production comprises separately controlled frontend hosting (Amplify), backend runtime (EC2/SSM) and PostgreSQL on the EC2 host.

| Area | Current recorded state | Evidence classification |
|---|---|---|
| IAM approval boundary | Main-ref OIDC trust can reach the deploy role; owner accepts this risk for now. A separate environment-only apply role is deferred. | Owner decision + run #9 observation |
| Production database reviewer | Owner is the sole required reviewer and deliberately retains self-approval authority. | Owner decision (12 Nov 2026) |
| Backend rollback | Last-good SHA fix is merged in commit `4580ad3f2ed2155ba466932b2ac0bad229a5b0f1`; live deployment/ref verification is outstanding. | Git-confirmed; runtime unverified |
| Migration 045 | Applied and verified; ledger reports 41, checksum recorded below. | Owner-provided production verification |
| Vendor/bootstrap IAM | Vendor policy JSON and bootstrap parameter existence have not been verified. | Open verification |
| Backups | A restorable pre-045 dump exists on instance storage; no off-instance mechanism was observed. | Backup evidence; off-instance status unknown |

## 1. Environment and release model

```mermaid
flowchart TD
  DEV[Local development] --> PR[Pull request]
  PR --> CI[GitHub Actions CI]
  CI --> MAIN[Merge to main]
  MAIN --> APP{Changed paths}
  APP -->|Application paths| VERIFY[Deploy workflow verification]
  VERIFY --> SSM[SSM command to EC2]
  SSM --> API[FastAPI service]
  APP -->|Frontend paths| AMP[Amplify build and publish]
  APP -->|Schema paths| PREFLIGHT[Read-only migration preflight]
  PREFLIGHT --> APPROVAL[Manual apply + production-database approval]
  APPROVAL --> DB[(PostgreSQL: superbajaar)]
  DOC[Docs-only paths] --> DOC_CI[Documentation governance]
  DOC_CI --> NO_DEPLOY[No GitHub deploy.yml application-path deployment]
```

- **Local:** developer workstation and explicitly selected local/test services.
- **CI:** ephemeral test jobs and disposable PostgreSQL. Not a persistent staging environment.
- **Production:** AWS Amplify frontend, EC2-hosted FastAPI backend, and self-managed PostgreSQL on EC2.
- **Staging:** no dedicated staging environment is evidenced in the repository configuration reviewed for this record. Do not describe CI as staging.

A commit to `main` does not mean every component deploys. Workflow path filters and job conditions decide what runs. Verify the exact workflow run, job outcomes, deployed commit marker and service health before calling a release live. A schema-path push performs read-only preflight; applying SQL is a separate manually dispatched and approval-gated action.

## 2. IAM approval bypass — accepted risk

**Decision:** YES, the current trust arrangement can permit IAM approval bypass for the database apply path. The owner explicitly accepts this risk for now.

### Evidence and interpretation

- Run #9 used a status job without a GitHub Environment. The main-branch OIDC subject assumed `SuperBajaarGitHubDeploy` and returned live database status.
- The role permits `ssm:SendCommand` with `AWS-RunShellScript` on EC2 instance `i-08814a9225c19ee91`. A workflow running under that trusted subject can therefore execute commands on the instance within the role's permissions.
- The GitHub `production-database` reviewer gate is a workflow/environment control. It is not, by itself, an IAM trust-policy boundary.
- The owner reports that the trust policy's `sub` condition is a list containing both the main-ref subject and the `production-database` environment subject.
- The owner reports that main has no branch protection because the owner removed the rule.

### Owner decision

The sole owner accepts the current risk because there is no team. A separate, narrowly scoped database-apply role trusted only by the `production-database` environment subject is deferred.

**Required future improvement:** separate read-only/status access from production apply access. The apply role should trust only the exact repository + protected environment OIDC subject, have the minimum required SSM/database permissions, and not be assumable by an ordinary main-ref job. Review branch/ruleset protections when a second contributor or reviewer is introduced.

Do not describe the GitHub environment gate as an IAM guarantee.

## 3. Production self-approval — explicit owner decision

### 2. SELF-APPROVAL: YES. OWNER RETAINS REVIEWER AUTHORITY BY DECISION.

**Evidence:** run #10 attempt 2 was re-run by `siinghniibandhan-wq` and approved by the same account on `production-database`. The "Prevent self-review" setting page was never viewed, so it is inferred off.

**Owner decision (12 Nov 2026):** the owner is the sole required reviewer on `production-database` and retains full authority to approve their own production migrations. "Prevent self-review" stays off, because there is no team and enabling it with one reviewer would block all approvals. "Allow administrators to bypass" was unticked by the owner (reported, not seen on screen). Revisit when a second reviewer is added.

### Changes recorded

- `production-database` reviewer: owner only (sole reviewer, by decision).
- The owner accepts the absence of independent second-person review as a current operational risk.
- Admin-bypass checkbox state is owner-reported, not independently screenshot-verified.
- Do not claim that the settings page was inspected. A screenshot showing required reviewers and the bypass checkbox is the evidence needed to independently verify the visible configuration.

## 4. Backend deployment and last-good rollback

### Failure mechanism

The EC2 source-sync timer runs `sync_main.sh` and can fast-forward `/opt/superbajaar/source` to the new `main` commit before the deployment workflow starts. The sync and deployment scripts share a lock, which prevents simultaneous checkout mutation but does not guarantee which scheduled operation runs first.

If deployment records `HEAD` as its rollback point after sync has already advanced the checkout, the rollback point may equal the new target. A failed deployment can then restore the same broken source revision.

### Implemented fix

The fix is merged in PR #63, merge commit `4580ad3f2ed2155ba466932b2ac0bad229a5b0f1`.

The deployed script now:

1. Reads `refs/deploy/last-good` as the rollback SHA when that ref exists.
2. Falls back to current `HEAD` on the first deployment, when no saved ref exists.
3. Fetches and fast-forwards to the requested target SHA.
4. Installs dependencies, compiles the backend, restarts `superbajaar-backend.service`, checks API health and validates the HR route.
5. On failure, resets to the saved rollback SHA, restores dependencies, restarts the service and checks health.
6. Only after all deployment checks succeed, updates `refs/deploy/last-good` to the verified deployed `HEAD`.

The final success sequence in `backend/scripts/deploy_backend.sh` is:

```bash
rollback_needed=0
git update-ref refs/deploy/last-good "$(git rev-parse HEAD)"
trap - EXIT
log "Deployment verified: $(git rev-parse HEAD); health=OK; HR route HTTP $hr_code"
```

The rollback point is a Git ref on the EC2 checkout; it is not a database backup and does not reverse schema changes.

### First deployment after the fix

If `refs/deploy/last-good` does not yet exist, the script deliberately falls back to `HEAD`. After that deployment passes all verification steps, it writes the ref. The first successful deployment establishes the persistent last-good reference; it cannot use a previously saved last-good ref that does not exist.

### Verification still required

Do not claim the fix is live until all of the following have been observed for the deployment associated with commit `4580ad3` (or a later qualifying deployment):

```bash
sudo -u ubuntu git -C /opt/superbajaar/source rev-parse HEAD
sudo -u ubuntu git -C /opt/superbajaar/source rev-parse refs/deploy/last-good
sudo systemctl is-active superbajaar-backend.service
curl --fail --silent --show-error https://superappkart.duckdns.org/api/health
```

Also confirm the GitHub Actions `Deploy Super Bajaar backend` run and its EC2 SSM job result. A workflow-level success that skips the EC2 job is not a production deployment.

**Deployment verification status at the time of this record:** not yet confirmed for `4580ad3`; server `HEAD`, `refs/deploy/last-good`, service state and HTTP 200 remain outstanding.

## 5. Database migration governance

### Production target

| Setting | Recorded production value |
|---|---|
| Database | `superbajaar` |
| Application role | `superbajaar_app` |
| PostgreSQL | EC2-local, port 5432, host 127.0.0.1 |
| Checkout | `/opt/superbajaar/source` |
| Schema directory | `/opt/superbajaar/source/backend/schema` |
| Migration runner | `backend/scripts/apply_schema.sh` |
| Required manifest | `backend/schema_required.txt` |

The runner's fallback `sb_app` is historical and is not the confirmed production database. Production commands must explicitly set `SB_DB=superbajaar`.

### Migration 045 — applied and verified

| Field | Recorded value |
|---|---|
| File | `045_identity_claim_cancellation_event.sql` |
| Production result | Applied and verified (owner-reported 12 Nov 2026) |
| Migration ledger count | 41 |
| SHA-256 | `874886ce7aae2bc6c4f541e95f63bf231ac06b187a62aeb94cef6f58cbf2b948` |
| Constraint | Includes `link_cancelled` |
| Identity event rows | 0 |

The zero-row `identity_events` result is a count at verification time; it does not mean the migration failed. Do not reapply migration 045. Reconfirm the ledger and checksum with a read-only status query before any subsequent database operation.

### Immutable migration controls

- New schema files use `NNN_lowercase_description.sql` with unique three-digit prefixes.
- Never renumber, edit, move or delete an applied migration. A correction is a new unused migration.
- SQL files contain schema/data changes only, never shell, deployment, systemd or CI configuration.
- A verified pre-change backup is required before an approved apply.
- Each migration is applied in its own transaction and recorded with a checksum.
- The scheduled schema runner is status-only; a timer tick is not permission to apply.
- A Git merge, CI pass or green deployment workflow does not authorize a production schema change.

## 6. Backup and recovery posture

### Known evidence

A restorable pre-045 custom-format dump was reported on the EC2 instance:

- File: `superbajaar-pre-045-20261112T085030Z.dump`
- SHA-256: `de8fadf361d29e195c37a75a7fc08b17fbd185c0a2793cda309422635d44b24e`
- Location: `/var/lib/superbajaar/backups`
- Owner reports the dump is restorable.

Manual dumps and migration-runner pre-migration dumps were also observed on the instance disk. The 0-byte dump was removed and the new dump plus checksum file were chowned to `ubuntu`.

### What is not established

**Accurate conclusion: no off-instance mechanism was observed.** This is not proof that none exists.

Not yet checked: scheduled EBS snapshots, Data Lifecycle Manager (DLM), AWS Backup, S3 copy/replication, lifecycle retention or an independent restore test from an off-instance copy.

### Recovery policy

1. Preserve the pre-045 dump and checksum.
2. Before each production migration, create and validate a fresh dump.
3. Inspect AWS snapshot/backup configuration and S3 destinations before making claims about off-instance protection.
4. Decide and document retention, encryption, access controls, RPO and RTO.
5. Test restore to an isolated database before relying on a backup as a recovery control.
6. Never restore over production without a separate explicit approval and impact assessment.

## 7. Vendor and bootstrap IAM verification

- The `SuperBajaarVendorPort...` policy JSON was not inspected; its S3-related permission scope remains unverified.
- `SuperBajaarDeleteBootstrapPassword` reportedly allows `ssm:DeleteParameter` only on `/superbajaar/bootstrap/super-admin-password`.
- Whether that Parameter Store parameter still exists has not been checked. Therefore whether the delete policy is still required is unknown.
- Do not delete the policy or parameter, broaden permissions, or infer that bootstrap provisioning is complete without checking the exact policy document and parameter metadata.

## 8. Open actions and acceptance criteria

| Priority | Action | Completion evidence |
|---:|---|---|
| 1 | Verify deployment for `4580ad3` / later qualifying commit | Workflow + EC2 SSM job succeeded; server HEAD and last-good ref; service active; health HTTP 200 |
| 2 | Inspect vendor policy and bootstrap parameter | Exact IAM policy JSON and Parameter Store existence/metadata recorded |
| 3 | Inspect off-instance backup controls | EBS/DLM/AWS Backup/S3 configuration and retention findings recorded |
| 4 | Decide backup retention and off-instance copy | Owner-approved RPO/RTO, retention, encryption and restore-test plan |
| 5 | Revisit reviewer model when a second reviewer is added | Updated environment reviewers and self-review setting verified |
| 6 | Consider separate apply IAM role | Environment-only trust and least-privilege policy reviewed and tested |

## 9. Change log and evidence discipline

- **12 Nov 2026:** Owner-approved IAM/self-approval decisions recorded; migration 045 reported applied and verified; last-good rollback fix merged; pre-045 dump identified.
- **12 Nov 2026:** This document consolidates the current production governance position. It supersedes older conflicting point-in-time status statements only where explicitly noted above. Historical incident records remain historical evidence.

Every status statement must be labelled as one of:
- **Verified from Git/source:** reproducible from repository content or commit history.
- **Observed live:** captured from the relevant AWS, GitHub, EC2 or database interface at a stated time.
- **Owner-reported:** provided by the system owner but not independently inspected.
- **Inferred:** derived from other evidence and explicitly identified as inference.
- **Open/unverified:** evidence has not yet been collected.

Do not convert owner-reported or inferred settings into independently verified facts.
---

## 10. Live production audit update — 12 November 2026

This section records the read-only EC2/database checks and the AWS Amplify console screenshot supplied by the owner on 12 November 2026. It supersedes earlier statements in this document that described backend deployment, migration 045, baseline checksum or migration 036 reconciliation as unverified/pending. It does not supersede the still-open Amplify details listed below.

### EC2 source, backend and API

| Check | Observed result |
|---|---|
| Production checkout | `/opt/superbajaar/source` |
| EC2 `HEAD` | `9b7980954cf0550383e8c34b2fcd89be219bc17a` |
| `origin/main` | Same SHA as EC2 `HEAD` |
| Backend service | `superbajaar-backend.service`, active/running |
| Service working directory | `/opt/superbajaar/source/backend` |
| Local API health | HTTP 200; `{"status":"ok","database":"connected"}` |
| Public API health | HTTP 200; `{"status":"ok","database":"connected"}` |

The source checkout is aligned with GitHub `main` at the time of the supplied diagnostic. This is source alignment; it is not, by itself, proof that every commit was deployed through the controlled backend deployment workflow.

### Backend last-good reference

The EC2 ref `refs/deploy/last-good` exists and points to:

```text
4580ad3f2ed2155ba466932b2ac0bad229a5b0f1
```

Comparing that commit with EC2 `HEAD` showed only six documentation files changed: `README.md`, `docs/DATABASE_MIGRATIONS.md`, `docs/ENVIRONMENTS_AND_CICD.md`, `docs/PRODUCTION_GOVERNANCE_AND_READINESS.md`, `docs/README.md`, and `docs/operations/PRODUCTION_DEPLOYMENT.md`. The deployment-relevant path comparison was empty. Therefore the running application source has no code difference from `main` in this comparison. Do not advance the last-good ref solely to include documentation-only commits; it represents the last verified backend application release.

### Database and migration runner

| Check | Observed result |
|---|---|
| Production database | `superbajaar` |
| Current schema SQL files | 40 |
| Production `schema_migrations` rows | 41 |
| Current files reported by `--status` | All APPLIED, including 045 |
| Status runner exit code | 0 |
| Migration 045 SHA-256 | `874886ce7aae2bc6c4f541e95f63bf231ac06b187a62aeb94cef6f58cbf2b948` |
| Schema timer | `superbajaar-schema.timer`, enabled and active |
| Timer cadence | Every 2 minutes |
| Last observed status service execution | `superbajaar-schema.service`, exit 0 / SUCCESS |

The timer service is a oneshot status check. Its being `inactive (dead)` after a successful run is normal; the timer remains active and schedules the next run. The correct installed unit names are `superbajaar-schema.timer` and `superbajaar-schema.service`; `sb-schema.timer` is not installed. The effective service command explicitly invokes `apply_schema.sh ... --status`, not apply mode.

### Baseline checksum and historical failure record

The current baseline file and production ledger row both have SHA-256:

```text
519e4467a6af9c1f87dd06cbdb80ef4545b1ae04edfe8937966799792168d938
```

The failure table retains an older record for `000_baseline_schema.sql` with SHA-256 `f95b15efed9e49e11e85bcf1786ae89ff10d29a60bb44774eedca3d82813a578` and error `changed after it was applied; not re-applied`. This is historical evidence for superseded file content; it is not a current baseline checksum mismatch. Preserve the historical failure row.

### Historical duplicate migration prefix 036

The 41st ledger row is explained by the historical migration `036_super_admin_role.sql`. Git history shows:

- `7308938e7a811a4486079a65c8e6e11d82615103` — introduced the separate Super Admin role migration.
- `5dbe8cf2a1ee9602953f92bce1cee60897a2c67` — removed that separate migration after the role work was consolidated.

The production ledger retains both `036_super_admin_role.sql` and `036_configurable_rbac.sql`; the current schema directory contains only `036_configurable_rbac.sql`. A scan of current schema filenames found no duplicate numeric prefixes. This is a historical migration-history exception, not a current repository numbering duplicate. Do not delete ledger rows, restore the removed file to the active schema directory, or rename/edit applied migrations.

### Amplify frontend evidence

The owner supplied an AWS Amplify console screenshot showing:

| Field | Screenshot observation |
|---|---|
| Deployment | 113 |
| Status | Deployed |
| Branch / repository | `main` / `superbajaar:main` |
| Commit message | “Merge pull request #65 …” |
| Deployment start shown | 12 Nov 2026, 15:28 (console timezone not independently established) |
| Build duration | 1 minute 4 seconds |
| Deploy duration | 42 seconds |
| Amplify domain | `https://main.d334sr8jkx3zux.amplifyapp.com` |

This establishes that Amplify reports deployment 113 as deployed for the connected `superbajaar:main` branch and that the displayed commit message refers to PR #65. It also demonstrates that Amplify published a deployment associated with the documentation PR, even though the GitHub `deploy.yml` application-path push filter excludes docs-only changes. Amplify's connected-repository trigger is therefore separate from that GitHub Actions path filter.

**Not established from the screenshot:** exact commit SHA for deployment 113; Amplify app ID; native `enableAutoBuild` setting; build specification / monorepo app-root configuration; whether the live build contains the expected storefront and admin bundles; functional browser journeys. Do not infer these from the deployment card alone. The owner has access to AWS RunShell rather than CloudShell, so AWS CLI/CloudShell commands are not an available verification path in this audit.

### Remaining verification

1. Inspect the Amplify deployment 113 build details in the console/RunShell-accessible interface to capture the exact commit SHA and build configuration.
2. Verify the deployed storefront and admin UI in a browser, including the actual route and static assets.
3. Record the Amplify app ID and native branch auto-build setting if visible through the available AWS access.

No production configuration, service, database, migration, IAM policy, timer or infrastructure changes were made during this audit. All EC2/database checks described above were read-only; the Amplify evidence was a screenshot supplied by the owner.


---

## AWS-native auto-deploy system — owner-supplied update, 13 November 2026

The owner reports that production now uses three independent EC2 systemd lanes: GitHub source synchronization, automatic schema application and automatic backend deployment. This section supersedes earlier current-state statements in this guide that the schema timer is status-only or that backend deployment is exclusively initiated through GitHub Actions/SSM. Older dated evidence remains historical.

**Infrastructure details supplied:** AWS account `715975223136`, region `us-east-1`, EC2 instance `i-08814a9225c19ee91`, instance role `SuperBajaar-EC2-Role`, checkout `/opt/superbajaar/source`, branch `main`, Linux user `ubuntu`.

### Current lane state as reported

| Lane | Unit | Schedule | Mode |
|---|---|---|---|
| GitHub sync | `superbajaar-github-sync.timer` | Every 2 minutes | Fetch + fast-forward only; unchanged |
| Schema | `superbajaar-schema.timer` | Even minutes | APPLY mode; `SB_ON_FAILURE=stop` |
| Backend | `superbajaar-backend-deploy.timer` | Odd minutes | `SB_BACKEND_LANE_MODE=live`; 15-minute timeout |

The schema service drop-in is `/etc/systemd/system/superbajaar-schema.service.d/override.conf`; its previous copy is `override.conf.bak-20261113T002237Z`. The backend lane script is `/usr/local/bin/sb-backend-lane.sh`, with backup `sb-backend-lane.sh.bak-20261113T005650Z`; its mode file is `/etc/default/superbajaar-backend-lane`. Detailed execution, migration gate, rollback, monitoring and off-switch instructions are in the [production deployment runbook](operations/PRODUCTION_DEPLOYMENT.md#aws-native-three-lane-auto-deployment--13-november-2026).

### AWS backup and observability resources as reported

- Private S3 backup bucket: `superbajaar-db-backups-715975223136-715975223136-us-east-1-an`; reported lifecycle expiry is 30 days.
- CloudWatch groups: `/superbajaar/backend-deploy` and `/superbajaar/db-migration`; 90-day retention is intended but must be checked in AWS.
- EC2 inline policy `SuperBajaar-Deploy` on `SuperBajaar-EC2-Role` is reported to grant log stream creation/event writes and S3 object get/put access for the backup bucket.
- SNS email alerts and DynamoDB run-history were not created.
- AWS CLI v2 is reported at `/usr/local/bin/aws`.

These are owner-supplied configuration details, not an independent AWS audit. Do not claim the CloudWatch retention, IAM resource scope, S3 upload success or current timer health is independently verified from this documentation change.

### Initial backend deployment report

The first automatic backend deployment is reported as commit `30e38fc` at 00:47 UTC on 13 November 2026, replacing previously running commit `f77b07c`. Treat this as owner-supplied deployment history; re-check the running service and `refs/deploy/last-good` before using it as current release evidence.

### Governance and safety boundaries

- A new migration uses the next unused three-digit number and a lowercase filename such as `046_something.sql`. Never reuse a prefix or edit an applied file; create a new migration for subsequent changes.
- Schema SQL is additive. Do not rename or delete database objects still used by the running application.
- If backend code requires a migration, include its exact filename in `backend/schema_required.txt` in the same commit. The backend lane waits for that migration to be recorded in `schema_migrations`.
- Keep SQL files limited to schema/database changes; do not embed deployment tooling or systemd configuration in SQL.
- The server checkout must remain clean. Do not edit `/opt/superbajaar/source` directly.
- Frontend/storefront delivery remains separate through Amplify.
- There are no configured SNS alerts; local/CloudWatch logs are the reported failure-observation path.
- Backend rollback validates service health and an HR route but cannot detect incorrect business logic that still passes those checks.
- A change anywhere under `backend/` except `backend/schema/` can restart the backend, including tests.
- Migration lock waits have no maximum duration and a heavy schema operation can affect a busy table.
- Failed backend code may remain downloaded in the checkout even when the previous version has been restored to service.

### Read-only operations

```bash
systemctl list-timers --all | grep superbajaar
tail -n 30 /var/lib/superbajaar/lane-state/backend-deploy.log
tail -n 30 /var/log/superbajaar/schema.log
curl -s http://127.0.0.1:8001/api/health
```

Emergency switches stop only their named lane:

```bash
sudo systemctl disable --now superbajaar-backend-deploy.timer
sudo systemctl disable --now superbajaar-schema.timer
```

Re-enable the relevant timer with the same command using `enable --now`. These controls do not revert prior backend or database changes.

**Verification boundary:** this update records the supplied configuration and operational intent. It does not prove that the timers are currently enabled, the latest runs succeeded, the health endpoint is currently healthy, S3 objects were uploaded, CloudWatch retention is 90 days, or the first deployment is still running. Verify each before an operational decision.
