# Environments, CI/CD and release governance

**Document owner:** Super Bajaar Engineering  
**Status:** Current repository workflow reference  
**Last verified:** 12 November 2026  
**Source of truth:** `.github/workflows/*.yml`, application build configuration and verified runtime configuration  
**Approval boundary:** This document explains automation. It does not authorize production deployment, database migration or infrastructure changes.

## 1. Executive summary

The repository currently demonstrates three execution contexts:

| Context | Purpose | How it is created | Persistence |
|---|---|---|---|
| Local development | Developer workstations | Vite and FastAPI run locally with developer-selected test services | Developer-managed |
| CI / test | Automated verification | GitHub Actions jobs create disposable PostgreSQL services and build/test the code | Ephemeral; not a staging environment |
| Production | Customer-facing application and backend | AWS Amplify Hosting for the frontend and an EC2-hosted FastAPI service; PostgreSQL is hosted on the EC2 machine | Persistent |

**A dedicated staging/pre-production environment is not evidenced by the current repository configuration reviewed on 12 November 2026.** Do not describe CI as staging. Do not assume a second Amplify branch, staging database, staging EC2 instance or staging URL exists without checking the AWS and GitHub configuration.

The word *environment* can refer to a deployment tier, an individual hosting service, a database, or a CI job. For release governance, count the three execution contexts above; within production, the frontend, backend and database are separate components with separate release controls.

## 2. Production topology

```text
GitHub repository (main)
        |
        +--> GitHub Actions verification
        |       +--> disposable PostgreSQL
        |       +--> backend tests
        |       +--> storefront/root Vite build
        |       +--> frontend/ admin build and tests
        |       +--> security and browser checks
        |
        +--> AWS Amplify Hosting
        |       +--> frontend build/publish
        |       +--> release marker and asset verification
        |       +--> prior successful build recovery on detected failure
        |
        +--> AWS Systems Manager (SSM)
        |       +--> EC2 deployment script
        |               +--> FastAPI service
        |
        +--> Separate database migration workflow
                +--> read-only status/dry-run on push
                +--> gated manual apply after approval
                        |
                        v
                PostgreSQL on EC2
```

The production database identity documented by the migration runbook is database `superbajaar`, application role `superbajaar_app`, PostgreSQL port `5432`, host `127.0.0.1`. These are recorded production facts from the prior host verification, not a live infrastructure query performed by this documentation review. Reconfirm on the host before an operational change. The runner's historical default `sb_app` is not the production target; always set `SB_DB=superbajaar` explicitly.

## 3. What happens when code is committed to main?

A commit to `main` does not have one universal outcome. The changed file paths determine which push workflows start.

### 3.1 Application code changes

The current `.github/workflows/deploy.yml` push trigger includes these paths:

- `backend/app/**`
- `backend/requirements.txt`
- `backend/scripts/deploy_backend.sh`
- `frontend/**`
- `src/**`
- `public/**`
- `index.html`
- `package.json`
- `package-lock.json`
- `vite.config.*`

For a matching push to `main`:

1. GitHub Actions starts the verification job.
2. A disposable PostgreSQL 15 service is created for the workflow.
3. The workflow installs backend dependencies and applies repository schema SQL to that disposable database only.
4. Backend compilation/tests, frontend unit/route tests, root and admin builds, Gitleaks and Semgrep run.
5. If verification succeeds, the EC2 deployment job assumes the AWS role through GitHub OIDC and uses SSM to invoke the deployment script for the exact commit.
6. The Amplify job waits for the Amplify build for that commit, checks the published release marker and referenced assets, and attempts recovery to a prior successful release if verification fails.

A workflow run being green proves only the checks represented by that run. Confirm the EC2 command, Amplify job and live release marker before claiming production is updated.

### 3.2 Documentation-only changes

The `deploy.yml` push trigger has path filters and does not include `docs/**` or `README.md`. Therefore a docs-only push to `main` does not start this production deploy workflow.

A pull request targeting `main` can still start the `deploy.yml` verification job because the pull-request trigger is not path-filtered. Its deploy jobs are conditioned on a push/manual event on `main`, so a pull-request run does not deploy to EC2 or publish Amplify.

### 3.3 Schema-only changes

The separate `.github/workflows/production-database-migrations.yml` is triggered on pushes to `main` that change `backend/schema/**` or `backend/schema_required.txt`. A push starts source/baseline verification and a read-only migration dry-run. It does **not** automatically apply SQL.

A real apply requires all of the following:
- a manual `workflow_dispatch` with operation `apply`;
- the exact confirmation string `APPLY SUPERBAJAAR`;
- successful preflight and immutable-baseline checks;
- approval through the protected GitHub environment `production-database`;
- a verified backup and successful post-apply required-migration checks.

The workflow file is not itself proof that the environment protection reviewers are configured correctly. Confirm those GitHub settings before relying on the gate.

## 4. Workflow types and responsibilities

| Workflow | Trigger | Responsibility | Can change production? |
|---|---|---|---|
| `ci.yml` | PR/push as defined in file | General build and test checks | No |
| `documentation-governance.yml` | PR/push to main or manual | Fails when governed implementation/configuration changes lack a same-change documentation update | No |
| `browser-quality.yml` | PR/push as defined in file | Browser-level quality checks | No |
| `migration-check.yml` | PR and push to main | Disposable PostgreSQL validation and migration-runner tests | No |
| `schema-governance.yml` | PR to main | Prevent migration edits, renames, deletions and duplicate numbering | No |
| `gitleaks.yml` | Workflow-defined security trigger | Secret scanning | No |
| `semgrep.yml` | Workflow-defined security trigger | Static security analysis | No |
| `deploy.yml` | Matching application-path push to main, PR verification, or manual dispatch | Verify and deploy backend/Amplify | Yes, on eligible main/manual events |
| `production-database-migrations.yml` | Schema-path push or manual dispatch | Read-only preflight by default; gated production apply | Yes, only through the separately approved apply path |
| `automation.yml` | Workflow-defined automation trigger | Repository automation | Depends on its job permissions; inspect before relying on it |

The trigger and job conditions in the YAML are authoritative. The documentation-governance check makes a relevant documentation change part of the same PR/commit as governed implementation and configuration changes. The PR must update `docs/**`, a relevant README, or `CHANGELOG.md`; do not defer it to a later release. This table is an orientation summary, not a replacement for reviewing the workflow file.

## 5. Release types

### Pull request verification
Code is checked before merge. CI may build, test, scan and validate migrations against disposable services. It does not mean code is live.

### Main-branch application release
A qualifying application-code push runs verification and, on success, may deploy the backend and publish/verify the Amplify frontend.

### Documentation release
Documentation merges into Git. A docs-only push does not match the application deployment path filter. Documentation may still be checked in pull-request workflows.

### Database migration release
A schema change is validated in CI and receives a read-only production preflight on a matching main push. The actual apply is a distinct manual, approval-gated operation.

### Manual workflow dispatch
A maintainer can manually start a workflow. Manual dispatch is not blanket authorization: inspect inputs, conditions, protected environments and target commit before starting it.

### Recovery / rollback
The backend deployment script has a recovery path for failed deployment. The Amplify workflow can retry a previous successful build after failed release verification. Database recovery is different: it requires a database-owner-approved restore/recovery decision. Application rollback does not roll back database schema.

## 6. Database and application release separation

Treat these as three independent release components:

1. **Frontend:** Amplify build and publication.
2. **Backend:** EC2 deployment through SSM.
3. **Database:** separately approved migration workflow.

A successful frontend deployment does not prove the backend is deployed. A successful backend deployment does not prove the database is migrated. A migration being present in Git or listed in `schema_required.txt` does not prove it is applied.

Migration 045 is `045_identity_claim_cancellation_event.sql`. It permits `link_cancelled` as an identity audit-event type. It is merged into `main`; production application remains pending verification and separate approval.

## 7. Required release evidence

For every application release, record:
- source commit SHA and PR;
- relevant workflow run IDs and final statuses;
- backend SSM command result and service health;
- Amplify job ID, deployed commit marker and asset verification;
- any rollback/recovery action.

For every database release, additionally record:
- exact database target;
- migration filenames and SHA-256 checksums;
- dry-run output;
- verified backup identifier and validation;
- approval record;
- post-apply migration ledger and schema verification.

Never publish credentials, tokens, customer data or raw secrets in release evidence.

## 8. Known limitations and verification gaps

- No dedicated staging/pre-production tier is evidenced in the reviewed repository workflows.
- The actual Amplify app ID, branch settings, build specification and public domain must be confirmed in AWS Amplify; workflow logic alone does not prove the live configuration.
- The actual GitHub protected-environment reviewers and branch protection/ruleset settings must be confirmed in GitHub settings.
- The repository has a separate EC2 `main` auto-sync timer documented in [GitHub main auto-sync](operations/GITHUB_MAIN_AUTO_SYNC.md). It fast-forwards the source checkout but does not build, apply SQL or restart the backend service; it is source synchronization, not a deployment release.
- No repository-root `amplify.yml` build specification was found in the inspected root listing, and the Amplify app's native auto-build/path-filter settings are not visible in Git. Confirm those settings in the AWS Amplify console. The GitHub `deploy.yml` path filter does not control Amplify's own connected-repository trigger.
- The current repository tree does not identify a dedicated staging application or staging environment configuration.
- Workflow YAML does not prove the most recent run succeeded. Check the run history for the release commit.

- **EC2 runtime verification (12 November 2026, 06:46 UTC):** the installed backend unit was `superbajaar-backend.service` (active/running), with WorkingDirectory `/opt/superbajaar/source/backend`; `superbajaar-new.service` was not found. The checkout and `origin/main` were both at `bf01a6d40ec5801cdb3ba98a99e410b421411c5d`. The Git sync timer was active and its latest run exited 0. The schema status timer was active, but its service returned exit code 10 because the applied baseline checksum mismatch and pending required migration 045 need attention. See [production deployment runtime snapshot](operations/PRODUCTION_DEPLOYMENT.md#verified-ec2-runtime-snapshot--12-november-2026) and [database migration status](DATABASE_MIGRATIONS.md#8-verified-production-migration-status--12-november-2026).
- A dated 10 November operations record reports PostgreSQL 18.6 on the EC2 host, while CI workflows explicitly test PostgreSQL 15 and 16. These are different facts (production host versus CI matrix); re-check the live production server version before documenting it as current.
- The repository documents an EC2 source auto-sync timer that fast-forwards `/opt/superbajaar/source` every two minutes. It does not restart the service. Source files can therefore be synchronized before the backend deployment job performs its controlled restart; do not call source synchronization a live application release.
- CI PostgreSQL containers are disposable test services, not production replicas and not staging databases.
- The previous production deployment attempt recorded in project history failed at AWS OIDC role assumption. That historical result must not be treated as the current deployment status; verify the latest run.

## 9. Related references

- [Repository README](../README.md)
- [Database migration operations](DATABASE_MIGRATIONS.md)
- [Production deployment runbook](operations/PRODUCTION_DEPLOYMENT.md)
- [Unified Identity implementation](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md)
- [Unified Identity production rollout](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md)


---

## 10. Production approval model and owner-accepted risks — 12 November 2026

The owner has explicitly accepted the current single-owner review model. The owner is the sole required reviewer on the GitHub environment `production-database` and retains authority to approve their own production migration.

- Run #10 attempt 2 was re-run by `siinghniibandhan-wq` and approved by the same account.
- The "Prevent self-review" setting page was not inspected; its off state is inferred.
- The owner decision is to keep "Prevent self-review" off because there is no team and enabling it with one reviewer would block all approvals.
- The owner reports that "Allow administrators to bypass" was unticked; this has not been independently verified from a screenshot.
- The owner-only reviewer configuration is intentional and accepted as a risk: no independent second-person review currently occurs. Revisit when a second reviewer is added.

The IAM trust arrangement also currently accepts a risk: the main-ref OIDC subject can assume the deployment role, whose SSM permissions allow AWS-RunShellScript on the production EC2 instance. The environment reviewer gate is a GitHub workflow control, not an IAM trust boundary. A separate apply role trusted only by the exact `production-database` environment subject is deferred by owner decision.

Do not describe either owner-reported settings as independently inspected. Do not claim that CI is staging or that the protected environment alone guarantees IAM isolation. The detailed evidence, trade-offs and future hardening actions are recorded in [Production governance and readiness](PRODUCTION_GOVERNANCE_AND_READINESS.md).
---

## 12. Live deployment audit update — 12 November 2026

This dated update records the owner-supplied production diagnostics and Amplify console screenshot. It supersedes earlier dated statements in this document that said the EC2 runtime, migration 045 or Amplify deployment were still wholly unverified. Older snapshots remain historical evidence.

### Confirmed production components

| Component | Latest observed evidence |
|---|---|
| GitHub main / EC2 source | Both at `9b7980954cf0550383e8c34b2fcd89be219bc17a` |
| EC2 backend service | `superbajaar-backend.service` active/running |
| Public and local API | HTTP 200; database reports connected |
| PostgreSQL migration runner | Status mode exit 0; all 40 current SQL files reported APPLIED |
| Migration ledger | 41 rows, including a historical removed migration with prefix 036 |
| Schema status timer | `superbajaar-schema.timer` enabled/active, every 2 minutes; oneshot status service last exited 0 |
| Amplify | Deployment 113 shown as Deployed for repository/branch `superbajaar:main`; commit message references PR #65 |

### Amplify is an independent deployment trigger

The Amplify console screenshot shows deployment 113 as deployed, with repository `superbajaar:main`, commit message beginning “Merge pull request #65”, domain `https://main.d334sr8jkx3zux.amplifyapp.com`, build duration 1:04 and deploy duration 0:42. The console displayed a start time of 12 Nov 2026, 15:28; timezone was not independently established.

This is direct screenshot evidence that Amplify published a deployment associated with the PR #65 merge. The GitHub Actions `deploy.yml` push path filter excludes documentation-only paths, so this Amplify deployment demonstrates that Amplify's Git-connected trigger is separate from the GitHub backend deployment workflow. It does **not** establish the precise native auto-build setting or prove that every main commit always triggers a build.

The exact deployment commit SHA, Amplify app ID, app-root/build specification, and live storefront/admin functional state have not yet been captured. Deployment status alone does not prove the expected frontend content or every user journey is working.

### Release-path interpretation

- A docs-only merge can update GitHub `main` and, as observed for PR #65, can also result in an Amplify deployment.
- The GitHub Actions backend deployment workflow remains governed by its own application-path filters and job conditions.
- EC2 source synchronization, backend service deployment, Amplify frontend publication and database migration are separate mechanisms. Do not treat one successful path as proof that the other three completed.
- The latest EC2 checkout SHA matching `main` is source-sync evidence. The backend service was active and health checks passed, but this audit did not independently tie a specific GitHub Actions SSM deployment run to that running process.
- Migration status is a separate read-only timer operation; it does not apply SQL.

The user has access to AWS RunShell but not AWS CloudShell. CloudShell-only AWS CLI instructions are therefore not an accepted verification procedure for this operator.

### Remaining release evidence

To close the frontend release audit, capture the exact commit SHA and build/app-root details from Amplify deployment 113's build details, then inspect the live storefront and admin in a browser. Keep the Amplify app ID and `enableAutoBuild` setting marked unverified until visible evidence is obtained.
