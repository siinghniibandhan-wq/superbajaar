from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        result = super().session_info()
        if self.env.user and self.env.user._is_internal():
            result["sb_backend_theme"] = self.env.user.sb_backend_theme or "odoo"
        return result
