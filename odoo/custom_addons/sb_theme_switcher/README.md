# Super Bajaar Theme Switcher

An Odoo 20.0 Community addon that adds two backend presentation themes:

- **Odoo Classic** — the familiar Odoo interface with Super Bajaar's purple brand accent.
- **Super Bajaar Glassmorphism** — a blue/orange branded glass surface treatment.

The addon does not replace Odoo views, models, menus, business logic, access rules, or workflows. It stores the selected theme on the current `res.users` record and exposes it in the authenticated backend session. Each internal user can select their own theme from the user menu.

## Installation

1. Add this directory to an Odoo 20.0 addons path.
2. Restart Odoo and update the Apps list.
3. Install **Super Bajaar Theme Switcher**.
4. Open the user menu and choose the desired theme.

## Compatibility and safeguards

- Community addon only; no Enterprise code is used.
- Uses Odoo's `web.assets_backend` bundle and `user_menuitems` registry.
- Theme changes are presentation-only and are persisted server-side per user.
- Odoo's existing business data, access control, and workflows remain unchanged.
- The Glassmorphism stylesheet includes a reduced-transparency fallback.

## Verification

Run the addon tests in an Odoo 20.0 test database:

```bash
./odoo-bin --addons-path=addons,odoo/custom_addons -d sb_theme_test -i sb_theme_switcher --test-enable --stop-after-init
```
