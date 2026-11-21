from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBackendThemePreference(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = cls.env["res.users"].create({
            "name": "Theme Preference User",
            "login": "theme-preference-user",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
        })

    def test_user_can_save_and_read_glass_theme(self):
        users = self.env["res.users"].with_user(self.test_user)

        users.sb_set_backend_theme("glass")

        self.assertEqual(users.sb_get_backend_theme(), "glass")
        self.assertEqual(self.test_user.sb_backend_theme, "glass")

    def test_user_can_switch_back_to_odoo_theme(self):
        self.test_user.sb_backend_theme = "glass"
        users = self.env["res.users"].with_user(self.test_user)

        users.sb_set_backend_theme("odoo")

        self.assertEqual(users.sb_get_backend_theme(), "odoo")

    def test_invalid_theme_is_rejected(self):
        users = self.env["res.users"].with_user(self.test_user)

        with self.assertRaises(ValidationError):
            users.sb_set_backend_theme("unknown")

    def test_theme_preference_is_per_user(self):
        other_user = self.env["res.users"].create({
            "name": "Other Theme User",
            "login": "other-theme-user",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self.env["res.users"].with_user(self.test_user).sb_set_backend_theme("glass")

        self.assertEqual(
            self.env["res.users"].with_user(other_user).sb_get_backend_theme(),
            "odoo",
        )
