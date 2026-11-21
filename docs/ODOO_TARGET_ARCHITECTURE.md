# Super Bajaar target architecture: Storefront + Odoo

## Approved target

Super Bajaar will operate as two product surfaces:

1. **Customer storefront:** retain the existing React/Vite storefront and its customer-facing design and workflows.
2. **Odoo Community 20.0:** the single business application and system of record for administration, catalogue, stock, purchasing, sales, POS, CRM, accounting, payments, fulfilment, delivery, HR, loyalty, reporting, users and permissions.

There will be no parallel Super Bajaar FastAPI business platform or separate custom admin application after migration and cutover. Existing systems remain untouched until their Odoo replacements have been migrated, tested and accepted.

## Repository direction

The approved repository target is the existing `siinghniibandhan-wq/superbajaar` repository. The Odoo Community source must ultimately be incorporated under `odoo/`, with Super Bajaar-specific Odoo addons under `odoo/custom_addons/`. Do not create another Super Bajaar business application or duplicate database.

The upstream Odoo Community source is available at [odoo/odoo, branch 20.0](https://github.com/odoo/odoo/tree/20.0). Its LGPL-3 notices and source history must be preserved when it is incorporated. The separately created GitHub fork is an upstream working copy; it is not a second Super Bajaar business system.

## Theme decision

Odoo remains the only administration application. It will offer two user-selectable themes:

- **Odoo Classic:** familiar Odoo navigation and interaction patterns with the Odoo purple brand foundation.
- **Super Bajaar Glassmorphism:** Super Bajaar blue with restrained orange accents, frosted surfaces, subtle depth and blur.

The selected theme is stored on each Odoo user record. It changes presentation only: business data, permissions, views' underlying actions and workflows remain the same. The storefront is not affected by the Odoo backend theme.

The first implementation is the `sb_theme_switcher` Community addon in `odoo/custom_addons/`. It adds a per-user preference, exposes it to the authenticated web-client session and adds a theme switch action to the Odoo user menu.

## Migration and safety sequence

1. Incorporate the complete Odoo Community 20.0 source into the existing Super Bajaar repository while preserving upstream licensing and history.
2. Install and validate the Odoo Community modules required by Super Bajaar.
3. Install the Super Bajaar theme addon and verify both themes on supported Odoo views and screen sizes.
4. Map existing storefront API operations to Odoo's supported APIs and implement only missing Super Bajaar-specific behavior as Odoo addons.
5. Migrate and reconcile products, categories, stock, customers, vendors, orders, payments, invoices, employees, roles and other approved records.
6. Run staging integration, security, accounting, GST, payment, inventory and end-to-end acceptance tests.
7. Cut over the storefront to Odoo only after acceptance and a verified rollback plan.
8. Retire the FastAPI backend, separate admin UI and duplicate business data/services only after cutover is proven stable.

## Current implementation status

- Existing storefront and legacy backend have not been deleted or modified by this architecture work.
- The Odoo Community 20.0 fork exists at [siinghniibandhan-wq/odoo](https://github.com/siinghniibandhan-wq/odoo).
- The initial theme addon and its preference tests have been added on the `feature/odoo-theme-system` branch of the Super Bajaar repository.
- The addon has not yet been installed or run against an Odoo 20.0 server. Runtime tests, browser verification and full source incorporation remain pending.
- No production services, databases, credentials, deployment automation or DNS have been changed.

## Non-negotiable safeguards

- Do not remove legacy code or production services before successful migration and cutover.
- Do not change the existing storefront's customer experience as part of the Odoo backend theme work.
- Do not duplicate Odoo business logic in another service or database.
- Do not modify the existing SQL migration automation as part of this migration.
- Preserve Odoo's LGPL-3 notices and do not import Enterprise-only code into the Community fork.
