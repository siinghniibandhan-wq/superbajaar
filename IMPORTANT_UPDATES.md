# Important project updates

This file is the concise chronological change log for major Superbajaar project updates. It complements README.md, which contains the detailed architecture, API contracts, workflows, setup and safety rules.

## 2026-11-06 — Launch-readiness pass: responsive UI, customer order history and launch assets

**Status:** Prepared in a working copy; CI, review, merge and deployment were not yet completed in the source record.

- Added customer-authenticated order list/detail endpoints restricted to website orders associated with the signed-in customer's verified account email. Included items, payment status and delivery progress, plus a support-ticket entry point. The source record states no schema/migration change and an update to the customer-session route allow-list.
- Storefront: enabled My Orders list/detail and ticket link; added responsive styling for screen-reader labels, hero heading contrast, mobile/tablet header, account navigation, touch targets, safe areas and reduced motion.
- Admin: added responsive workspace styling and formula-injection-safe CSV export for Orders.
- Launch assets: favicon, web manifest and placeholder image; SEO/Open Graph/PWA metadata and noscript message.
- Verification recorded: frontend esbuild bundle and Python compileall passed; browser render checks at 360/390/768/1280 px reported no horizontal overflow on listed storefront/admin pages using mocked APIs. Backend pytest, npm production build and Playwright were NOT RUN in that working copy and remained CI requirements.

## 2026-11-04 — Razorpay checkout readiness follow-up

**Status:** Implemented on an isolated PR branch. Original implementation CI passed on 0e381566f73be346ef9feae5d73bd0647aeba70d; review fixes on ca3751fa3118a88a9fab68b431186695e2711152 required a fresh CI run. Review, merge and release were pending in the source record.

- Added mocked backend coverage for Razorpay order creation, server-side capture verification, signed webhook capture/deduplication and late captured payments after order cancellation.
- Prevented a late captured payment from resurrecting a cancelled order; customer messaging indicates refund follow-up is required.
- Added release-manifest references for required schema files and migration 033_razorpay_webhook_inbox.sql for provider order ID, INR currency metadata and deduplicated provider-event inbox. No existing migration was edited.
- Documented customer checkout, provider verification and webhook API contract/limits.
- Added exact-fingerprint Gitleaks exceptions for reviewed historical false positives, with rationale in SECURITY_GOVERNANCE.md.
- The source record reports 27 backend tests passed; frontend build passed with an existing large-chunk warning and sitemap/robots generation skipped because VITE_SITE_URL was unset; 4 mocked checkout E2E tests passed; required-schema check and PostgreSQL 15/16 migration workflow passed.
- GitHub Actions recorded as passed on commit 474bc1522e7a73ec5422b72edc0d3017445cdc5e: CI #41831630078, browser quality #41831637192, migration #41831637219, Semgrep #41831637926 and Gitleaks #41831637936.
- Live provider checkout, webhook delivery, production migration state and deployment were NOT VERIFIED.

## 2026-11-02 — CRM support workspace hardening and migration sequencing

**Status:** Implemented on feature/crm-workspace-20261102; latest-code CI, independent review, PR, merge and production release remained pending in the source record.

- Added Customer 360, staff case management, public/internal messages, append-only case events, customer support portal, explicit one-to-one website-account linking and calendar-minute SLA policies.
- Hardened staff-created cases so initial public descriptions record first_response_at.
- Restricted SLA policy create/update to owner/admin; managers and staff cannot change SLA configuration.
- Documented CRM API/authentication, customer privacy, phone-based order-match and SLA limitations.
- Historical sequencing note: main ended at 016, ERP PR #237 reserved 017–020, and CRM migration 021 was not to merge ahead of that sequence. This is a dated snapshot only; re-check current GitHub and production ledger before relying on it.
- Earlier CRM CI run #740 passed on 7d00ad5d63ff5b470a5f542611e3026ababebaea; PostgreSQL 15/16 migration workflow #478 passed on 508d4a81823fb99eebe240040b788240a85aa3a5. Later code fixes were not covered by those runs.
- The source record noted 32 open PRs against a normal operating target of 15; preserve valid work and dependencies rather than closing unrelated PRs to meet a target.

## 2026-11-01 — AI review governance: Copilot removed from PR review

- ChatGPT is CTO/lead technical reviewer; Perplexity is independent technical reviewer.
- Repository owner is the sole formal GitHub approver, merge authority and production-release decision-maker. AI reviews are advisory.
- Copilot remains an optional secondary coding agent, not a PR reviewer, approver, assigned reviewer or release gate.
- Gemini is outside the active review/approval chain unless the owner changes policy; Claude remains the database specialist.
- Policy was synchronized across AGENTS.md, README.md, AI collaboration/operating-model documents, development workflow, security governance, Copilot documentation and .github/copilot-instructions.md.
- The source record said the live Protect main - Enhanced ruleset still had copilot_code_review.review_on_push=true and the available GitHub connection could only read rulesets. Do not claim the GitHub setting was disabled without administrator verification.

## 2026-10-31 — GitHub Copilot documentation and usage governance

- Added Copilot documentation covering plans, published allowances, billing controls, feature caveats, team delegation and safeguards.
- Added Copilot to the tool register as an additional coding assistant, not an autonomous owner or review/CI replacement.
- Added .github/copilot-instructions.md for shared governance, branch workflow, schema protections, secret safety and owner-controlled merge/deployment.
- The source record documented published plan allowances and explicitly did not assume the user's assigned plan, remaining balance, enabled features or billing budget.
- No application code, schema, production data, secrets, deployment or GitHub billing settings changed.

## 2026-10-30 — Project documentation and operating model expansion

- Reorganised README.md as the central project handbook with status, architecture, tool register, schema automation overview, diagnostics, GitHub flow and document index.
- Added docs/DEVELOPMENT_WORKFLOW.md as the canonical tool/diagnostic/GitHub/PR workflow.
- Reworked docs/architecture.md to distinguish actual implementation from target patterns and document runtime topology, request lifecycle, domain boundaries, API contract control and schema flow.
- Expanded docs/DATABASE_CHANGE_RULES.md with runner modes, backup/transaction/checksum/failure behaviour, required-file gate, exit codes and CI boundaries.
- Updated AGENTS.md, CLAUDE.md and PR template with mandatory reading, document-update responsibilities, database authorship controls and evidence requirements.
- PR operating targets were documented as 15 open PRs normally, 5-day resolution target, Day 7 escalation and Day 10 target closure. These are operating targets, not GitHub enforcement.
- Verification boundary: documentation was prepared against repository files and workflow definitions; no production preflight, migration, application-code change, production-data change or deployment was performed.

## 2026-10-30 — Standard project progress structure

- Added docs/PROJECT_PROGRESS_STRUCTURE.md as the standard work breakdown for Development, Deployment and Audit, including database/schema, integrations/automation, infrastructure, documentation/compliance, QA/testing and release records.
- Defined evidence-based status vocabulary and a required progress-report template, with latest findings and critical blockers first.
- Linked the structure from README.md.
- Source record states PR #169 merged after CI passed. No application code, schema, production data or deployment configuration changed.

## 2026-10-30 — Database migration safety and protected-main controls

- Added a guarded migration runner with dry-run/status/retry behaviour, checksum ledger, backup validation, per-file transactions and explicit failure codes.
- Added baseline protection for populated databases, least-privilege expectations and protection for historical migration filenames.
- Added PostgreSQL 15/16 CI matrix coverage and release-gate documentation.
- Enabled protected-main workflow requiring PRs and database matrix checks.
- Source record states PR #150 CI passed against disposable databases. No production migration, backup validation or deployment was performed by those tests.

## 2026-10-30 — README architecture, progress and API handbook

- Added GitHub Markdown caution/warning callouts, project overview and evidence-based progress table separating CI from production verification.
- Added infrastructure/request-flow and customer/admin/employee workflow diagrams.
- Expanded API guide with authentication/public-route rules, route inventory, request lifecycle, HTTP error interpretation and debugging order.
- Documented limitations at that time: no checkout stock reservation, payment gateway charge/refund integration, carrier integration and incomplete employee UI entry.
- Source record states PR #151 merged. This is a historical snapshot, not a statement of current completeness.

## 2026-10-30 — Multi-category catalogue and storefront product details

- Product create/edit supported multiple category assignments while retaining the legacy primary category.
- Storefront filters used assigned category IDs; product cards represented parent products and detail pages supported variant selection and quantity before basket add.
- POS cards hid SKU while operational details retained it; POS styling was responsive.
- Reused the existing 012_product_category_assignments.sql; no duplicate migration was added.
- CI status was pending in the source record.

## 2026-10-30 — Audited product deletion for owner/admin

- Added owner/admin Delete action with mandatory reason and confirmation.
- Backend enforced role and wrote a durable audit record in the deletion transaction.
- Operationally referenced products were protected by database constraints; failed deletes rolled back and directed users to Archive.
- Added additive migration 013_product_deletion_audit.sql and marked it release-required.
- Verification was pending in the source record; no production migration, cleanup or deployment was performed.

## Ongoing documentation rule

For every major change:
1. Update the relevant detailed section and diagrams in README.md.
2. Add a concise dated entry here in IMPORTANT_UPDATES.md.
3. Keep documentation with the implementation change where practical.
4. Include only verified endpoints, status and test evidence.
5. Never log secrets, tokens, passwords, private customer data or production connection strings.
6. Record actual status: proposed, implemented, CI-verified, merged or production-verified. These are not interchangeable.

