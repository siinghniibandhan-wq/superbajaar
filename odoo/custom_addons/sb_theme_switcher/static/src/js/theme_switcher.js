/** @odoo-module **/

import { usePlugin } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { ORM } from "@web/core/orm_plugin";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

function applyTheme(theme) {
    const selectedTheme = theme === "glass" ? "glass" : "odoo";
    document.documentElement.classList.toggle("sb-theme-glass", selectedTheme === "glass");
    document.documentElement.dataset.sbTheme = selectedTheme;
    session.sb_backend_theme = selectedTheme;
}

if (document.documentElement) {
    applyTheme(session.sb_backend_theme || "odoo");
}

function superBajaarThemeItem() {
    const orm = usePlugin(ORM);
    const currentTheme = session.sb_backend_theme || "odoo";
    const nextTheme = currentTheme === "glass" ? "odoo" : "glass";

    return {
        type: "item",
        id: "sb_backend_theme",
        description:
            nextTheme === "glass"
                ? _t("Switch to Super Bajaar Glassmorphism")
                : _t("Switch to Odoo Classic Theme"),
        callback: async () => {
            const savedTheme = await orm.call("res.users", "sb_set_backend_theme", [nextTheme]);
            applyTheme(savedTheme);
        },
        sequence: 45,
    };
}

registry.category("user_menuitems").add("sb_backend_theme", superBajaarThemeItem);
