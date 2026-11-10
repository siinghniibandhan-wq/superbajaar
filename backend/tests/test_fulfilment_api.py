from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.main import app

client = TestClient(app)


def test_fulfilment_pick_line_requires_reason_for_short_pick():
    from app.api.fulfilment import PickLineUpdate

    with pytest.raises(ValidationError, match="short_reason"):
        PickLineUpdate(picked_quantity="2", short_quantity="1")


def test_fulfilment_package_rejects_duplicate_order_lines():
    from app.api.fulfilment import PackageCreate

    with pytest.raises(ValidationError, match="unique"):
        PackageCreate(package_number="PKG-TEST", lines=[
            {"pick_task_line_id": 1, "order_line_id": 10, "quantity": "1"},
            {"pick_task_line_id": 2, "order_line_id": 10, "quantity": "1"},
        ])


def test_fulfilment_package_rejects_non_positive_quantities():
    from app.api.fulfilment import PackageLineInput

    with pytest.raises(ValidationError):
        PackageLineInput(pick_task_line_id=1, order_line_id=10, quantity="0")


def test_fulfilment_pick_task_endpoint_requires_active_staff_session():
    response = client.post("/api/fulfilment/shipments/1/pick-task")
    assert response.status_code == 401


def test_fulfilment_return_requires_reason_and_unique_order_lines():
    from app.api.fulfilment import ReturnCreate

    with pytest.raises(ValidationError):
        ReturnCreate(reason="  ", lines=[{"order_line_id": 1, "quantity": "1"}])
    with pytest.raises(ValidationError, match="unique"):
        ReturnCreate(reason="Customer return", lines=[
            {"order_line_id": 1, "quantity": "1"},
            {"order_line_id": 1, "quantity": "2"},
        ])


def test_fulfilment_return_inspection_rejects_unknown_disposition_state():
    from app.api.fulfilment import ReturnLineInspection

    with pytest.raises(ValidationError, match="Unsupported"):
        ReturnLineInspection(received_quantity="1", inspection_status="restock")
