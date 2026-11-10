from app.core.auth_middleware import _role_can_write


def test_viewer_cannot_write_any_module():
    assert not _role_can_write("viewer", "/api/orders")
    assert not _role_can_write("viewer", "/api/inventory/adjustments")
    assert not _role_can_write("viewer", "/api/auth/users")


def test_staff_is_limited_to_order_delivery_and_support_operations():
    assert _role_can_write("staff", "/api/orders")
    assert _role_can_write("staff", "/api/orders/12/status")
    assert _role_can_write("staff", "/api/delivery/shipments")
    assert _role_can_write("staff", "/api/customers/support-cases")
    assert not _role_can_write("staff", "/api/catalogue/products")
    assert not _role_can_write("staff", "/api/inventory/adjustments")
    assert not _role_can_write("staff", "/api/payments/3/status")
    assert not _role_can_write("staff", "/api/auth/users")


def test_manager_can_manage_operations_but_not_users_or_catalogue():
    assert _role_can_write("manager", "/api/inventory/adjustments")
    assert _role_can_write("manager", "/api/purchasing/orders")
    assert _role_can_write("manager", "/api/orders/12/status")
    assert not _role_can_write("manager", "/api/catalogue/products")
    assert not _role_can_write("manager", "/api/auth/users")


def test_admin_and_owner_can_write_all_modules():
    for role in ("owner", "admin", "super_admin"):
        assert _role_can_write(role, "/api/catalogue/products")
        assert _role_can_write(role, "/api/auth/users")


def test_super_admin_is_the_only_role_that_can_manage_privileged_roles():
    from app.api.auth import _can_manage_privileged_roles

    assert _can_manage_privileged_roles("super_admin")
    assert not _can_manage_privileged_roles("owner")
    assert not _can_manage_privileged_roles("admin")


def test_product_deletion_is_not_allowed_for_manager_staff_or_viewer():
    for role in ("manager", "staff", "viewer"):
        assert not _role_can_write(role, "/api/catalogue/products/42")


def test_super_admin_has_accounting_read_access():
    from app.api.accounting import READ_ROLES

    assert "super_admin" in READ_ROLES


def test_super_admin_has_hr_management_access():
    from types import SimpleNamespace
    from app.api.hr import _manager

    assert _manager(SimpleNamespace(state=SimpleNamespace(user_id=1, role="super_admin"))) == 1


def test_super_admin_has_organisation_policy_administration_access():
    from types import SimpleNamespace
    from app.api.organisation_policies import _policy_admin

    request = SimpleNamespace(state=SimpleNamespace(user_id=1, user_email="root@example.test", role="super_admin"))
    assert _policy_admin(request) == (1, "root@example.test", "super_admin")


def test_super_admin_has_loyalty_administration_access():
    from types import SimpleNamespace
    from app.api.loyalty import _admin

    assert _admin(SimpleNamespace(state=SimpleNamespace(role="super_admin"))) is None
