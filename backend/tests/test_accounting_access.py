from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.accounting import require_accounting_reader


def test_super_admin_can_read_accounting():
    request = SimpleNamespace(state=SimpleNamespace(role="super_admin"))
    require_accounting_reader(request, None)


def test_accounting_denial_message_lists_super_admin():
    request = SimpleNamespace(state=SimpleNamespace(role="staff"))
    with pytest.raises(HTTPException) as caught:
        require_accounting_reader(request, None)

    assert caught.value.status_code == 403
    assert "Super Admin" in caught.value.detail
