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
| `browser-quality.yml` | PR/push as defined in file | Browser-level quality checks | No |
| `migration-check.yml` | PR and push to main | Disposable PostgreSQL validation and migration-runner tests | No |
| `schema-governance.yml` | PR to main | Prevent migration edits, renames, deletions and duplicate numbering | No |
| `gitleaks.yml` | Workflow-defined security trigger | Secret scanning | No |
| `semgrep.yml` | Workflow-defined security trigger | Static security analysis | No |
| `deploy.yml` | Matching application-path push to main, PR verification, or manual dispatch | Verify and deploy backend/Amplify | Yes, on eligible main/manual events |
| `production-database-migrations.yml` | Schema-path push or manual dispatch | Read-only preflight by default; gated production apply | Yes, only through the separately approved apply path |
| `automation.yml` | Workflow-defined automation trigger | Repository automation | Depends on its job permissions; inspect before relying on it |

The trigger and job conditions in the YAML are authoritative. This table is an orientation summary, not a replacement for reviewing the workflow file.

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
- Workflow YAML does not prove the most recent run succeeded. Check the run history for the release commit.
- CI PostgreSQL containers are disposable test services, not production replicas and not staging databases.
- The previous production deployment attempt recorded in project history failed at AWS OIDC role assumption. That historical result must not be treated as the current deployment status; verify the latest run.

## 9. Related references

- [Repository README](../README.md)
- [Database migration operations](DATABASE_MIGRATIONS.md)
- [Production deployment runbook](operations/PRODUCTION_DEPLOYMENT.md)
- [Unified Identity implementation](UNIFIED_IDENTITY_SYSTEM_IMPLEMENTATION.md)
- [Unified Identity production rollout](UNIFIED_IDENTITY_SYSTEM_PRODUCTION_ROLLOUT.md)
