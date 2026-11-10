from app.core.auth_middleware import permission_granted


def test_permission_requires_assigned_module_and_action():
    permissions = {"inventory": {"read": True, "create": False, "edit": True}}
    assert permission_granted(permissions, "inventory", "read")
    assert not permission_granted(permissions, "inventory", "create")
    assert permission_granted(permissions, "inventory", "edit")


def test_unassigned_module_is_denied_by_default():
    assert not permission_granted({}, "accounting", "read")


def test_admin_cannot_grant_permissions_outside_own_authority():
    from app.api.auth import permissions_within_authority

    granted = {"inventory": {"read": True, "edit": True}}
    authority = {"inventory": {"read": True}}
    assert not permissions_within_authority(granted, authority)


def test_owner_is_not_a_supported_role():
    from app.api.auth import USER_ROLES
    assert "owner" not in USER_ROLES
    assert "super_admin" in USER_ROLES


def test_super_admin_can_manage_all_permissions():
    from app.api.auth import can_manage_all_permissions

    assert can_manage_all_permissions("super_admin")
    assert not can_manage_all_permissions("admin")


def test_module_mapping_uses_configured_prefix_and_covers_split_routers():
    from app.core.auth_middleware import _module_for_path

    assert _module_for_path("/v2/inventory-locations/warehouses", "/v2") == "inventory"
    assert _module_for_path("/v2/purchasing-lifecycle/rfqs/1/award", "/v2") == "purchasing"
    assert _module_for_path("/api/orders", "/v2") is None


def test_unmapped_routes_do_not_receive_legacy_role_fallback():
    from app.core.auth_middleware import _module_for_path

    assert _module_for_path("/api/unregistered-admin-route", "/api") is None


def test_workflow_endpoints_use_approve_and_export_actions():
    from app.core.auth_middleware import _action_for_request

    assert _action_for_request("POST", "/api/purchasing/rfqs/12/award") == "approve"
    assert _action_for_request("POST", "/api/accounting/vouchers/12/post") == "approve"
    assert _action_for_request("GET", "/api/reports/orders/export") == "export"
    assert _action_for_request("POST", "/api/orders") == "create"


def test_admin_cannot_manage_admin_or_super_admin_accounts():
    from app.api.auth import _can_manage_target_user

    assert _can_manage_target_user("admin", "staff")
    assert not _can_manage_target_user("admin", "admin")
    assert not _can_manage_target_user("admin", "super_admin")
    assert _can_manage_target_user("super_admin", "admin")
    assert _can_manage_target_user("super_admin", "super_admin")
