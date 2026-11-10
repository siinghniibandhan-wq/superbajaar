from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.customers import _build_customer_360
from app.main import app

client = TestClient(app)


def test_customer_360_counts_orders_and_only_open_cases():
    customer = {"id": 7, "name": "A Customer", "phone": "9876543210", "email": "a@example.com"}
    orders = [
        {"order_number": "SB-100", "status": "delivered", "total": 1200, "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc)},
        {"order_number": "SB-101", "status": "processing", "total": 500, "created_at": datetime(2026, 10, 2, tzinfo=timezone.utc)},
    ]
    cases = [
        {"case_number": "SUP-1", "status": "open", "priority": "normal"},
        {"case_number": "SUP-2", "status": "in_progress", "priority": "high"},
        {"case_number": "SUP-3", "status": "resolved", "priority": "low"},
        {"case_number": "SUP-4", "status": "closed", "priority": "urgent"},
    ]

    result = _build_customer_360(customer, orders, cases)

    assert result["customer"] == customer
    assert result["summary"]["order_count"] == 2
    assert result["summary"]["open_case_count"] == 2
    assert result["summary"]["total_case_count"] == 4
    assert result["summary"]["latest_order_at"] == orders[1]["created_at"]


def test_customer_360_handles_customer_without_orders_or_cases():
    customer = {"id": 8, "name": "New Customer", "phone": None, "email": None}

    result = _build_customer_360(customer, [], [])

    assert result["orders"] == []
    assert result["support_cases"] == []
    assert result["summary"] == {
        "order_count": 0,
        "open_case_count": 0,
        "total_case_count": 0,
        "latest_order_at": None,
    }


def test_customer_360_rejects_non_positive_customer_id():
    response = client.get("/api/customers/0/360")
    assert response.status_code == 422
    assert response.json()["detail"] == "Customer ID must be positive"


def test_support_portal_rejects_unauthenticated_ticket_creation(monkeypatch):
    from app.core import auth_middleware

    monkeypatch.setattr(auth_middleware.settings, "database_url", "postgresql://test.invalid/sb_app")
    response = client.post("/api/customers/support-portal/tickets", json={
        "name": "Test Customer", "phone": "9876543210", "email": "customer@example.com",
        "subject": "Order help", "description": "Please help with my order",
    })
    assert response.status_code == 401


def test_customer_session_cannot_access_staff_customer_directory(monkeypatch):
    from app.core import auth_middleware

    monkeypatch.setattr(auth_middleware.settings, "database_url", "postgresql://test.invalid/sb_app")
    monkeypatch.setattr(
        auth_middleware, "_decode",
        lambda token: {"typ": "customer", "sub": "42", "jti": "test-session"},
    )
    response = client.get(
        "/api/customers",
        headers={"Authorization": "Bearer customer-test-token"},
    )
    assert response.status_code == 403


def test_customer_account_link_requires_explicit_verification_method():
    from app.api.customers import CustomerAccountLinkIn
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CustomerAccountLinkIn(customer_account_id=42)


def test_customer_support_ticket_payload_does_not_require_contact_details():
    from app.api.customers import CustomerSupportTicketIn

    payload = CustomerSupportTicketIn(subject="Order status", description="Please check my order")
    assert payload.subject == "Order status"
    assert payload.description == "Please check my order"


def test_support_message_trims_body_and_rejects_blank_content():
    import pytest
    from pydantic import ValidationError
    from app.api.customers import SupportMessageIn

    assert SupportMessageIn(body="  Need an update  ").body == "Need an update"
    with pytest.raises(ValidationError):
        SupportMessageIn(body="   ")


def test_sla_policy_rejects_business_hours_until_schedule_support_exists():
    import pytest
    from pydantic import ValidationError
    from app.api.customers import SupportSlaPolicyIn

    with pytest.raises(ValidationError):
        SupportSlaPolicyIn(
            priority="high",
            first_response_minutes=60,
            resolution_minutes=1440,
            calendar_minutes=False,
        )

def test_staff_created_case_records_description_as_first_public_message(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from app.api import customers

    created_case = {
        "id": 91,
        "case_number": "SUP-TEST91",
        "customer_id": 7,
        "order_id": None,
        "subject": "Order assistance",
        "description": "The original issue",
        "priority": "normal",
        "status": "open",
        "assigned_to": None,
        "resolution": None,
        "created_at": datetime(2026, 11, 2, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 11, 2, tzinfo=timezone.utc),
        "first_response_due_at": None,
        "resolution_due_at": None,
    }

    class Cursor:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def transaction(self):
            return nullcontext()

        def execute(self, query, params=()):
            self.calls.append((query, params))
            if "FROM support_sla_policies" in query:
                return Cursor(None)
            if "INSERT INTO support_cases" in query:
                return Cursor(created_case)
            return Cursor(None)

    connection = Connection()
    monkeypatch.setattr(customers, "_connect", lambda: connection)

    result = customers.create_case(
        customers.CaseIn(
            customer_id=7,
            subject="Order assistance",
            description="The original issue",
        ),
        SimpleNamespace(state=SimpleNamespace(user_id=12)),
    )

    assert result["case_number"] == "SUP-TEST91"
    case_insert = next(
        query for query, _ in connection.calls
        if "INSERT INTO support_cases" in query
    )
    insert_statement = case_insert.split("RETURNING", 1)[0]
    assert "first_response_at" not in insert_statement
    assert "now()" not in insert_statement
    message_insert = next(
        (query, params)
        for query, params in connection.calls
        if "INSERT INTO support_case_messages" in query
    )
    assert message_insert[1] == (91, 12, "The original issue")

def test_customer_cannot_reply_to_resolved_ticket(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import pytest
    from fastapi import HTTPException
    from app.api import customers

    class Cursor:
        def fetchone(self):
            return {"id": 91, "status": "resolved"}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def transaction(self):
            return nullcontext()

        def execute(self, query, params=()):
            assert "SELECT id,status FROM support_cases" in query
            return Cursor()

    monkeypatch.setattr(customers, "_connect", lambda: Connection())
    monkeypatch.setattr(customers, "_linked_customer_id", lambda conn, account_id: 7)

    with pytest.raises(HTTPException) as error:
        customers.reply_to_customer_support_ticket(
            "SUP-TEST91",
            customers.SupportMessageIn(body="Please reopen this"),
            SimpleNamespace(state=SimpleNamespace(customer_id=42)),
        )

    assert error.value.status_code == 409

def test_sla_policy_rejects_unknown_timezone():
    import pytest
    from pydantic import ValidationError
    from app.api.customers import SupportSlaPolicyIn

    with pytest.raises(ValidationError):
        SupportSlaPolicyIn(
            priority="high",
            first_response_minutes=60,
            resolution_minutes=1440,
            timezone="Not/A_Real_Zone",
        )



def test_sla_policy_mutation_requires_owner_or_admin():
    from types import SimpleNamespace
    import pytest
    from fastapi import HTTPException
    from app.api import customers

    payload = customers.SupportSlaPolicyIn(
        priority="high",
        first_response_minutes=60,
        resolution_minutes=1440,
    )
    request = SimpleNamespace(state=SimpleNamespace(role="manager"))

    for mutation in (
        lambda: customers.create_support_sla_policy(payload, request),
        lambda: customers.update_support_sla_policy(1, payload, request),
    ):
        with pytest.raises(HTTPException) as error:
            mutation()
        assert error.value.status_code == 403


def test_customer_storage_errors_are_logged_with_original_exception(monkeypatch, caplog):
    import logging
    import psycopg
    import pytest
    from fastapi import HTTPException
    from app.api import customers

    class BrokenConnection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            raise psycopg.OperationalError("simulated database failure")

    monkeypatch.setattr(customers, "_connect", lambda: BrokenConnection())

    with caplog.at_level(logging.ERROR, logger=customers.__name__):
        with pytest.raises(HTTPException) as error:
            customers.list_customers(search=None, limit=100, offset=0)

    assert error.value.status_code == 503
    matching = [record for record in caplog.records if "Customer storage operation failed" in record.getMessage()]
    assert matching
    assert matching[-1].exc_info is not None
    assert matching[-1].exc_info[0] is psycopg.OperationalError



def test_super_admin_and_admin_can_create_sla_policies_for_every_priority(monkeypatch):
    from types import SimpleNamespace
    from app.api import customers

    class Cursor:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self, row):
            self.row = row
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params=()):
            self.calls.append((query, params))
            return Cursor(self.row)

    for role in ("super_admin", "admin"):
        for priority in ("urgent", "high", "normal", "low"):
            row = {
                "id": 1,
                "priority": priority,
                "first_response_minutes": 30,
                "resolution_minutes": 240,
                "calendar_minutes": True,
                "timezone": "Asia/Kolkata",
                "is_active": True,
            }
            connection = Connection(row)
            monkeypatch.setattr(customers, "_connect", lambda connection=connection: connection)
            payload = customers.SupportSlaPolicyIn(
                priority=priority,
                first_response_minutes=30,
                resolution_minutes=240,
            )

            result = customers.create_support_sla_policy(
                payload,
                SimpleNamespace(state=SimpleNamespace(role=role)),
            )

            assert result["priority"] == priority
            assert len(connection.calls) == 1
            assert "INSERT INTO support_sla_policies" in connection.calls[0][0]
            assert connection.calls[0][1][0] == priority
