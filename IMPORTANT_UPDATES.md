# Important project updates

This file is the concise, chronological change log for major Super Bajaar project updates. It complements `README.md`, which contains the detailed architecture, API contracts, workflows, setup and safety rules.

## 2026-10-30 — Project documentation and operating model expansion

**Status:** Updated on documentation PR [#170](https://github.com/siinghniibandhan-wq/superbajaar/pull/170); review and CI pending.

- Reorganised `README.md` as the central project handbook with latest status, critical findings, architecture, tool register, schema automation overview, diagnostic guide, GitHub flow and documentation index.
- Added `docs/DEVELOPMENT_WORKFLOW.md` as the canonical register for tools, primary use, diagnostic order, Codespaces/Swagger/AWS decision rules, GitHub lifecycle and PR operating targets.
- Rewrote `docs/architecture.md` to distinguish actual implementation from target patterns and document runtime topology, request lifecycle, domain boundaries, API contract change control and schema data flow.
- Expanded `docs/DATABASE_CHANGE_RULES.md` with the checked-in runner's actual modes, backup/transaction/checksum/failure behaviour, required-file gate, exit codes and CI boundaries.
- Updated `AGENTS.md`, `CLAUDE.md` and the PR template with mandatory reading, document-update responsibilities, database authorship controls and evidence requirements.
- PR operating targets: no more than 15 open PRs in normal conditions; 5-day resolution target; Day 7 escalation; Day 10 target closure. These are team targets, not automatic GitHub enforcement.

**Verification boundary:** Documentation was prepared against checked-in project documents, the schema runner, required-schema manifest and GitHub workflow definitions. This update does not execute production preflight, apply migrations, change application code, alter production data or deploy services. PR CI and final cross-reference checks remain pending.

**Files updated:** README, AGENTS, CLAUDE, architecture, database rules, PR template, this history; new `docs/DEVELOPMENT_WORKFLOW.md`.

---

## How to maintain this log

- Add an entry for every major feature, API, database/schema, security, architecture, integration, deployment or workflow change.
- Keep each entry short: date, summary, impact, verification and PR/commit reference.
- Update this file in the same feature branch and pull request as the related change.
- Do not log secrets, tokens, passwords, private customer data or production connection strings.
- Routine formatting and minor non-functional fixes do not need entries.
- Record the actual status: proposed, implemented, CI-verified, merged or production-verified. Do not treat these as interchangeable.

---

## 2026-10-30 — Standard project progress structure

**Status:** Merged into `main` in PR [#169](https://github.com/siinghniibandhan-wq/superbajaar/pull/169).

- Added `docs/PROJECT_PROGRESS_STRUCTURE.md` as the standard work breakdown for Development, Deployment and Audit; expanded the Audit section to include database/schema, integrations/automation, infrastructure/deployment, documentation/compliance and evidence-based finding records. The audit framework remains in this same file; no separate audit folder or structure file is required.
- Development is split into Coding and Bug / Error Fixing, each with Frontend, Backend, API and UI / Interface workstreams.
- Added Database / Schema and Integrations / Automation workstreams to avoid hiding cross-layer work.
- Added separate Deployment stages, Audit categories (Frontend, Backend, API, UI, Security and Others), QA / Testing and Documentation / Release Records.
- Defined evidence-based status vocabulary and a required progress-report template, with latest findings and critical blockers shown first.
- Linked the structure from the main README.

**Impact:** Project updates can now report work consistently without confusing code completion, CI success, deployment, audit approval and production verification.

**Verification:** PR #169 merged after its CI checks passed. No application code, schema, production data or deployment configuration changed.


## 2026-10-30 — Database migration safety and protected-main controls

**Status:** Merged to `main` in PR [#150](https://github.com/siinghniibandhan-wq/superbajaar/pull/150).

- Added a guarded database migration runner with dry-run/status/retry behaviour, migration checksum ledger, backup validation, per-file transactions and explicit failure codes.
- Added baseline protection for populated databases, least-privilege expectations and protection for historical migration filenames.
- Added PostgreSQL 15 and 16 CI matrix coverage and release-gate documentation.
- Enabled protected-main workflow requiring pull requests and the database matrix checks.

**Verification:** PR #150 CI passed its PostgreSQL 15/16 database checks and configured backend/frontend checks on the tested commit. These ran against disposable test databases. No production database migration, production backup validation or deployment was performed by those tests.

**References:** PR #150; merge commit `a693150d750182d91f4681259d655128f37f56db`.

## 2026-10-30 — README architecture, progress and API handbook

**Status:** Merged to `main` in PR [#151](https://github.com/siinghniibandhan-wq/superbajaar/pull/151).

- Added prominent GitHub Markdown caution, warning and important callouts for production safety, verification boundaries and documentation requirements.
- Added a project overview and evidence-based progress table separating CI results from production verification.
- Added overall infrastructure and request-flow diagrams, plus customer, admin and employee workflow diagrams.
- Expanded the API guide with authentication/public-route rules, route inventory, request lifecycle, HTTP error interpretation and debugging order.
- Documented current limitations, including no checkout stock reservation, no payment gateway charge/refund integration, no carrier integration and incomplete employee UI entry.

**Impact:** Future contributors have one source of truth for the architecture, role boundaries, API paths and known implementation gaps. Update the relevant README section whenever those contracts or workflows change.

**Verification:** Source files and route declarations were reviewed to prepare the documentation. The README update itself is documentation-only; production behaviour is not certified by this entry.

**References:** [PR #151](https://github.com/siinghniibandhan-wq/superbajaar/pull/151); latest README commit `178351f9ae1a697ba27a493cd608dd5af0c02c00` (branch `docs/readme-database-safety-20261030`).

## 2026-10-30 — Multi-category catalogue and storefront product details

**Status:** Implemented in PR #149; CI verification pending.

- Product create/edit supports assigning one product to multiple categories while retaining the legacy primary category field.
- Storefront category filters use assigned category IDs; product cards represent one parent product and product detail pages support variant selection and quantity before adding to basket.
- POS catalogue cards hide SKU while operational product/variant details retain it; POS layout styling is responsive.
- Reuses the existing `012_product_category_assignments.sql` schema; no duplicate migration was added.

**Verification:** Backend tests and both frontend production builds are being run in GitHub Actions. No production database migration or deployment is included.

## 2026-10-30 — Audited product deletion for owner/admin

**Status:** Implemented on a feature branch; CI and review pending.

- Added a Delete action for owner/admin catalogue users, with mandatory reason and confirmation.
- Backend enforces the role and writes a durable audit record in the same transaction as deletion.
- Products referenced by operational records are protected by database constraints; failed deletes roll back and direct users to Archive.
- Added additive migration `013_product_deletion_audit.sql` and marked it release-required.

**Verification:** Automated validation and CI pending. No production migration, database cleanup or deployment was performed.

## Ongoing documentation rule

For every future major change:
1. Update the relevant detailed section and diagrams in `README.md`.
2. Add a concise dated entry here in `IMPORTANT_UPDATES.md`.
3. Keep both changes in the same feature branch and PR as the implementation where practical.
4. Include only verified endpoints, status and test evidence.
5. Never push directly to `main`; use the protected pull-request process.
