# Odoo Community 20.0 source integration

## Authoritative upstream source

The complete, unmodified Odoo Community source is pinned as the Git submodule at `odoo/community`.

- Upstream: https://github.com/odoo/odoo
- Branch: `20.0`
- Pinned commit: `9099d343022cf6cf438e6fcc57cb848442236947`
- License: LGPL-3.0; retain upstream notices and license files.
- Enterprise source is not included.

The individual files staged directly under `odoo/` during the initial import are not a complete replacement for this upstream tree. The submodule is the authoritative runtime source; do not patch or fork upstream files to apply Super Bajaar branding.

## Checkout

For a fresh clone:

```bash
git clone --recurse-submodules https://github.com/siinghniibandhan-wq/superbajaar.git
cd superbajaar
```

For an existing checkout:

```bash
git submodule update --init --recursive -- odoo/community
```

The submodule is pinned to an exact commit. Do not run `git submodule update --remote` as part of a production deployment; update the pin only through a reviewed change that records the new upstream commit.

## Dependencies and launch

Create an isolated Python environment, install the exact upstream requirements, provision a disposable PostgreSQL database, and then start Odoo through the repository launcher:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r odoo/community/requirements.txt
./odoo/launch.sh -d superbajaar_odoo_dev --db_host=127.0.0.1 --db_user=odoo
```

Supply the PostgreSQL credentials through your local secure configuration. Never use the existing Super Bajaar production database for initial Odoo installation or tests.

The launcher includes both the complete upstream Community add-ons directory and `odoo/custom_addons` in the add-ons path. The existing `sb_theme_switcher` add-on is therefore discoverable without modifying upstream files.

## Important boundary

A complete upstream source checkout is not the same as a completed Super Bajaar migration. Module installation, database provisioning, Indian localisation/GST configuration, data migration, storefront API integration, security review, end-to-end acceptance, rollback planning and production cutover remain separate gates. Do not retire the existing FastAPI/admin/database services before those gates pass.
