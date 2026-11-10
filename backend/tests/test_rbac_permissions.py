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


def test_super_admin_can_manage_all_permissions():
    from app.api.auth import can_manage_all_permissions

    assert can_manage_all_permissions("super_admin")
    assert not can_manage_all_permissions("admin")
