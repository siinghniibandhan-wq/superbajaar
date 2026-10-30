# Important project updates

> [!IMPORTANT]
> ## LATEST AUDIT STATUS — SCHEMA REVIEW
> **Status:** IN PROGRESS — repository/schema review underway; production schema state NOT VERIFIED.
>
> **Latest critical finding:** Git files and CI cannot establish which migrations are applied in production. The live `sb_app` `schema_migrations` ledger, checksums, runner `--status`, and backup readiness have not been inspected in this review. Do not merge or deploy on the assumption that repository files are applied.
>
> **Repository review completed so far (2026-10-30):**
> - Confirmed the schema directory contains the baseline plus the current `009`, `010`, `011`, `012`, and `013` migration files.
> - The duplicated `009` and `012` prefixes are the exact four documented legacy files; the workflow explicitly protects these pairs. Do not rename, reorder, or reuse those prefixes.
> - Confirmed every non-comment entry in `backend/schema_required.txt` maps to a file in `backend/schema/`. `011_customer_phone_uniqueness.sql` is intentionally omitted according to the file's own note because application validation handles duplicate mobile numbers.
> - PR #158's order-reservation implementation uses existing baseline objects (`orders`, `order_lines`, `deliveries`, `inventory_balances`, `inventory_movements`, and `stock_locations`) plus `orders.customer_email` from the required loyalty migration. No new schema file is indicated by the reviewed code.
> - Static review does not prove live compatibility or application status. The baseline's `CREATE TABLE IF NOT EXISTS` statements do not reconcile pre-existing tables with different definitions; it remains a one-time bootstrap, not a repair migration.
>
> **Next required checks:** Finish the migration-by-migration static review; then have the Database Owner run the read-only production checks in `docs/RELEASE_GATES.md` (database/version, full ledger and checksums, runner `--status` exit code, and backup storage). Record unavailable checks as NOT VERIFIED. No SQL, schema files, required-schema list, production database, merge, or deployment changed in this review.

---

This file is the concise, chronological change log for major Super Bajaar project updates. It complements `README.md`, which contains the detailed architecture, API contracts, workflows, setup and safety rules.

## How to maintain this log

- Add an entry for every major feature, API, database/schema, security, architecture, integration, deployment or workflow change.
- Keep each entry short: date, summary, impact, verification and PR/commit reference.
- Update this file in the same feature branch and pull request as the related change.
- Do not log secrets, tokens, passwords, private customer data or production connection strings.
- Routine formatting and minor non-functional fixes do not need entries.
- Record the actual status: proposed, implemented, CI-verified, merged or production-verified. Do not treat these as interchangeable.

---

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
