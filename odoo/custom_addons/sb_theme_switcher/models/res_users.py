from odoo import fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    sb_backend_theme = fields.Selection(
        selection=[
            ("odoo", "Odoo Classic"),
            ("glass", "Super Bajaar Glassmorphism"),
        ],
        string="Backend Theme",
        default="odoo",
        required=True,
        help="The visual theme used by this user in the Odoo backend.",
    )

    def sb_get_backend_theme(self):
        """Return the current session user's saved backend theme."""
        return self.env.user.sb_backend_theme or "odoo"

    def sb_set_backend_theme(self, theme):
        """Save a theme for the current user only."""
        if theme not in ("odoo", "glass"):
            raise ValidationError("Unsupported Super Bajaar backend theme.")
        self.env.user.write({"sb_backend_theme": theme})
        return theme
