# Super Bajaar target architecture: Storefront + Odoo

## Approved target

Super Bajaar will operate as two product surfaces:

1. **Customer storefront:** retain the existing React/Vite storefront and its customer-facing design and workflows.
2. **Odoo Community 20.0:** the single business application and system of record for administration, catalogue, stock, purchasing, sales, POS, CRM, accounting, payments, fulfilment, delivery, HR, loyalty, reporting, users and permissions.

There will be no parallel Super Bajaar FastAPI business platform or separate custom admin application after migration and cutover. Existing systems remain untouched until their Odoo replacements have been migrated, tested and accepted.

## Repository and complete upstream source

The approved repository target is the existing `siinghniibandhan-wq/superbajaar` repository. The complete, unmodified Odoo Community source is now pinned as a Git submodule at `odoo/community`; Super Bajaar-specific addons remain under `odoo/custom_addons/`.

- Upstream repository: [odoo/odoo](https://github.com/odoo/odoo)
- Upstream branch: `20.0`
- Pinned source commit: `9099d343022cf6cf438e6fcc57cb848442236947`
- License: LGPL-3.0; upstream notices and history are retained.
- Odoo Enterprise source is not included.

The submodule gives a complete, exact upstream checkout while preserving Odoo's source history. It is not a hand-copied or modified approximation. Fresh clones must use `git clone --recurse-submodules`; existing clones must run `git submodule update --init --recursive -- odoo/community`. See [Odoo source integration and launch instructions](../odoo/SUPERBAJAAR_INTEGRATION.md).

The individually staged files directly under `odoo/` from the initial connector-based import are incomplete and are not the authoritative runtime source. Use `odoo/community` for Odoo core and official Community addons. Do not patch upstream files to apply Super Bajaar branding.

## Theme decision

Odoo remains the only administration application. It will offer two user-selectable themes:

- **Odoo Classic:** familiar Odoo navigation and interaction patterns with the Odoo purple brand foundation.
- **Super Bajaar Glassmorphism:** Super Bajaar blue with restrained orange accents, frosted surfaces, subtle depth and blur.

The selected theme is stored on each Odoo user record. It changes presentation only: business data, permissions, views' underlying actions and workflows remain the same. The storefront is not affected by the Odoo backend theme.

The first implementation is the `sb_theme_switcher` Community addon in `odoo/custom_addons/`. It adds a per-user preference, exposes it to the authenticated web-client session and adds a theme switch action to the Odoo user menu.

## Migration and safety sequence

1. Check out the pinned complete Odoo Community 20.0 source and install its dependencies in an isolated environment.
2. Provision a separate Odoo development/staging PostgreSQL database; do not reuse the existing Super Bajaar production database.
3. Install and validate the Odoo Community modules required by Super Bajaar.
4. Install the Super Bajaar theme addon and verify both themes on supported Odoo views and screen sizes.
5. Map existing storefront API operations to Odoo's supported APIs and implement only missing Super Bajaar-specific behavior as Odoo addons.
6. Migrate and reconcile products, categories, stock, customers, vendors, orders, payments, invoices, employees, roles and other approved records.
7. Run staging integration, security, accounting, GST, payment, inventory and end-to-end acceptance tests.
8. Cut over the storefront to Odoo only after acceptance and a verified rollback plan.
9. Retire the FastAPI backend, separate admin UI and duplicate business data/services only after cutover is proven stable.

## Current implementation status

- Existing storefront and legacy backend have not been deleted or modified by this architecture work.
- Complete Odoo Community source is linked at `odoo/community`, pinned to the official upstream commit above. Checkout requires Git submodule initialization.
- The initial theme addon and its preference tests are present under `odoo/custom_addons/sb_theme_switcher`.
- A repository launcher is available at `odoo/launch.sh`; it initializes the submodule when needed and includes upstream Community addons plus Super Bajaar custom addons in the addons path.
- The launcher passed Bash syntax validation. Odoo dependency installation, PostgreSQL startup, addon installation, Odoo TransactionCase tests and browser verification have **not** been run in this environment.
- The source checkout is complete, but the Super Bajaar migration is **not complete**: module configuration, Indian localisation/GST validation, data migration, storefront API integration, security review, end-to-end acceptance, rollback and production cutover remain open.
- No production services, databases, credentials, deployment automation or DNS have been changed.

## Non-negotiable safeguards

- Do not remove legacy code or production services before successful migration and cutover.
- Do not change the existing storefront's customer experience as part of the Odoo backend theme work.
- Do not duplicate Odoo business logic in another service or database.
- Do not modify the existing SQL migration automation as part of this migration.
- Preserve Odoo's LGPL-3 notices and do not import Enterprise-only code into the Community fork.
