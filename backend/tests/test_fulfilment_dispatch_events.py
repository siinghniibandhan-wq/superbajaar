from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.services import fulfilment_dispatch as service


class FakeConnection:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        response = next(self.responses, None)
        if isinstance(response, Exception):
            raise response
        return FakeCursor(response)


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.row or []


def test_dispatch_exact_replay_uses_structured_event_and_skips_stock_issue(monkeypatch):
    lines = [SimpleNamespace(variant_id=12, quantity=2)]
    expected_hash = service.dispatch_payload_hash(lines)
    conn = FakeConnection([{"id": 91, "payload_hash": expected_hash}])
    issue = Mock()
    monkeypatch.setattr(service, "dispatch_order_stock", issue)

    result = service.dispatch_shipment(
        conn, shipment_id=4, order_id=8, order_status="dispatched",
        order_number="SB-8", customer_name="Customer",
        dispatch_id="11111111-1111-4111-8111-111111111111",
        dispatch_lines=lines, note=None, actor_id=2, actor_email="staff@example.com",
    )

    assert result["duplicate"] is True
    issue.assert_not_called()
    assert len(conn.calls) == 1
    assert "fulfilment_dispatch_events" in conn.calls[0][0]


def test_dispatch_identity_reuse_with_changed_payload_is_conflict():
    lines = [SimpleNamespace(variant_id=12, quantity=3)]
    conn = FakeConnection([{"id": 91, "payload_hash": "0" * 64}])

    with pytest.raises(service.FulfilmentDispatchError, match="different payload"):
        service.dispatch_shipment(
            conn, shipment_id=4, order_id=8, order_status="ready_for_dispatch",
            order_number="SB-8", customer_name="Customer",
            dispatch_id="11111111-1111-4111-8111-111111111111",
            dispatch_lines=lines, note=None, actor_id=2, actor_email="staff@example.com",
        )


def test_dispatch_writes_structured_event_and_inventory_movement_links(monkeypatch):
    lines = [SimpleNamespace(variant_id=12, quantity=2)]
    responses = [
        None,                       # no prior dispatch identity
        None,                       # no prior order dispatch event
        {"max_id": 20},             # issue high-water mark
        {"total_cost": 0},          # no COGS journal required
        None,                       # order status update
        None,                       # order status history
        {"id": 92},                 # new dispatch event
        [{"id": 21, "order_line_id": 44, "movement_id": 77, "variant_id": 12, "quantity": 2}],
        None,                       # event line insert
    ]
    conn = FakeConnection(responses)
    monkeypatch.setattr(service, "dispatch_order_stock", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(service, "order_has_reservation", lambda *_args: False)
    monkeypatch.setattr(service, "order_fulfilment_started", lambda *_args: False)

    result = service.dispatch_shipment(
        conn, shipment_id=4, order_id=8, order_status="ready_for_dispatch",
        order_number="SB-8", customer_name="Customer",
        dispatch_id="11111111-1111-4111-8111-111111111111",
        dispatch_lines=lines, note="handover", actor_id=2, actor_email="staff@example.com",
    )

    assert result["duplicate"] is False
    assert any("INSERT INTO fulfilment_dispatch_events" in sql for sql, _ in conn.calls)
    event_line = next((sql, params) for sql, params in conn.calls if "INSERT INTO fulfilment_dispatch_event_lines" in sql)
    assert event_line[1] == (92, 44, 12, 77, 2)
