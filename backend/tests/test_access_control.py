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
    for role in ("owner", "admin"):
        assert _role_can_write(role, "/api/catalogue/products")
        assert _role_can_write(role, "/api/auth/users")
