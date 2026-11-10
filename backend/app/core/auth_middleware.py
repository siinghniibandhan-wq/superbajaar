"""Request authentication and role authorization dependency.

FastAPI dependencies run after request parsing/validation, allowing malformed
requests to return 422 while valid protected requests still require a session.
"""
from fastapi import HTTPException, Request
import psycopg
from psycopg.rows import dict_row

from app.api.auth import _decode
from app.core.config import settings


def method_is_public_serviceability(method: str, path: str, prefix: str) -> bool:
    return method == "GET" and path.startswith(prefix + "/delivery/serviceability/")


def _is_public_catalogue_read(method: str, path: str, prefix: str) -> bool:
    return method == "GET" and path in {
        prefix + "/catalogue/categories",
        prefix + "/catalogue/products",
        prefix + "/catalogue/variants",
    }


def permission_granted(permissions: dict, module: str, action: str) -> bool:
    """Return an explicit effective grant; missing module/action is deny-by-default."""
    return bool(permissions.get(module, {}).get(action, False))


def _module_for_path(path: str, prefix: str = "/api") -> str | None:
    """Resolve every staff API router using the configured API prefix."""
    normalized_prefix = prefix.rstrip("/")
    if not path.startswith(normalized_prefix + "/"):
        return None
    remainder = path[len(normalized_prefix) + 1:]
    route = remainder.split("/", 1)[0]
    aliases = {
        "catalogue": "catalogue", "inventory": "inventory", "inventory-locations": "inventory", "purchasing": "purchasing", "purchasing-lifecycle": "purchasing",
        "pos": "pos", "customers": "crm", "orders": "orders", "payments": "payments",
        "razorpay": "payments", "fulfilment": "fulfillment", "delivery": "delivery",
        "pricing": "pricing", "loyalty": "loyalty", "hr": "hr_payroll",
        "accounting": "accounting", "reports": "dashboard", "auth": "user_management", "organisation-policies": "dashboard",
    }
    return aliases.get(route)


def _action_for_request(method: str, path: str) -> str:
    """Translate workflow endpoints to granular actions before HTTP defaults."""
    segments = path.rstrip("/").lower().split("/")
    workflow_actions = {"approve": "approve", "award": "approve", "post": "approve", "dispatch": "approve", "credit": "approve", "export": "export", "configure": "configure", "settings": "configure"}
    if any(segment in workflow_actions for segment in segments):
        return next(workflow_actions[segment] for segment in reversed(segments) if segment in workflow_actions)
    if method in {"GET", "HEAD"}:
        return "read"
    if method == "DELETE":
        return "delete"
    if method == "POST":
        return "create"
    if method in {"PUT", "PATCH"}:
        return "edit"
    return "configure"


def _role_can_write(role: str, path: str) -> bool:
    if role in {"super_admin", "admin"}:
        return True
    if role == "viewer":
        return False
    if role == "manager":
        return path.startswith((
            "/api/inventory/", "/api/orders", "/api/payments",
            "/api/delivery/", "/api/customers", "/api/purchasing/", "/api/hr/",
        ))
    if role == "staff":
        return (
            path == "/api/orders"
            or (path.startswith("/api/orders/") and path.endswith("/status"))
            or path == "/api/delivery/shipments"
            or (path.startswith("/api/delivery/shipments/") and path.endswith("/status"))
            or path in {"/api/hr/attendance/punch", "/api/hr/leave", "/api/hr/expenses"}
            or path == "/api/customers/support-cases"
            or path.startswith("/api/customers/support-cases/")
        )
    return False


async def require_active_session(request: Request) -> None:
    """Authenticate a valid request and enforce role-based write access."""
    path = request.url.path
    prefix = settings.api_prefix.rstrip("/")
    public = {prefix + "/health", prefix + "/auth/login", prefix + "/customer-auth/register", prefix + "/customer-auth/login"}
    if method_is_public_serviceability(request.method, path, prefix):
        return
    # Razorpay authenticates this exact POST route with its raw-body HMAC signature.
    if request.method == "POST" and path == prefix + "/razorpay/webhook":
        return
    # Public partner enquiries remain available. Support tickets require a
    # validated customer session and an explicit customer-account/CRM link;
    # caller-supplied contact details are never used to authorize ticket access.
    if path == prefix + "/loyalty/partner-enquiries" and request.method == "POST":
        return
    if request.method == "GET" and path in {
        prefix + "/loyalty/rules",
        prefix + "/loyalty/quote",
        prefix + "/loyalty/customer/account",
    }:
        return
    if request.method == "OPTIONS" or not path.startswith(prefix + "/") or path in public:
        return

    # When DB configuration is absent, let each database-backed handler return
    # its explicit 503 response. With a configured database, auth remains required.
    if not settings.database_url:
        return

    if _is_public_catalogue_read(request.method, path, prefix):
        request.state.public_catalogue = True
        return

    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue")
    try:
        claims = _decode(authorization.split(" ", 1)[1].strip())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc

    if claims.get("typ") == "customer":
        customer_routes = {
            ("GET", prefix + "/customer-auth/me"),
            ("POST", prefix + "/customer-auth/logout"),
            ("POST", prefix + "/razorpay/orders"),
            ("POST", prefix + "/razorpay/verify"),
            ("GET", prefix + "/customer-auth/referrals"),
            ("GET", prefix + "/customer-auth/orders"),
            ("GET", prefix + "/loyalty/customer/me"),
            ("GET", prefix + "/loyalty/customer/redemption-quote"),
            ("GET", prefix + "/customers/support-portal/tickets"),
            ("POST", prefix + "/customers/support-portal/tickets"),
        }
        is_customer_support_detail = (
            path.startswith(prefix + "/customers/support-portal/tickets/")
            and request.method == "GET"
            and path.count("/") == 5
        )
        is_customer_support_reply = (
            path.startswith(prefix + "/customers/support-portal/tickets/")
            and path.endswith("/messages")
            and request.method == "POST"
            and path.count("/") == 6
        )
        is_customer_order_detail = (
            request.method == "GET"
            and path.startswith(prefix + "/customer-auth/orders/")
            and path.count("/") == 4
        )
        is_website_order = request.method == "POST" and path == prefix + "/orders"
        if (request.method, path) not in customer_routes and not is_customer_support_detail and not is_customer_support_reply and not is_customer_order_detail and not is_website_order:
            raise HTTPException(status_code=403, detail="Customer session cannot access staff resources")
        try:
            with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3) as conn:
                customer = conn.execute(
                    "SELECT c.id, c.email FROM customer_accounts c JOIN customer_sessions s ON s.customer_id=c.id "
                    "WHERE c.id=%s AND s.token_id=%s AND c.is_active=TRUE AND s.revoked_at IS NULL AND s.expires_at>now()",
                    (claims.get("sub"), claims.get("jti")),
                ).fetchone()
        except psycopg.Error as exc:
            raise HTTPException(status_code=503, detail="Customer authentication storage unavailable; verify migration 010") from exc
        if customer is None:
            raise HTTPException(status_code=401, detail="Customer session is no longer active")
        request.state.role = "customer"
        request.state.customer_id = customer["id"]
        request.state.customer_email = customer["email"]
        request.state.customer_token_id = claims.get("jti")
        if is_website_order:
            request.state.customer_checkout = True
        return

    if claims.get("typ"):
        raise HTTPException(status_code=401, detail="Invalid access token type")

    try:
        with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT u.id, u.email, u.role FROM app_users u JOIN app_user_sessions s ON s.user_id=u.id "
                "WHERE u.id=%s AND s.token_id=%s AND u.is_active=TRUE AND s.revoked_at IS NULL AND s.expires_at>now()",
                (claims.get("sub"), claims.get("jti")),
            ).fetchone()
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication storage unavailable; verify database connectivity and the required authentication schema",
        ) from exc
    if row is None:
        raise HTTPException(status_code=401, detail="Session is no longer active")

    role = row["role"]
    request.state.role = role
    request.state.user_id = row["id"]
    request.state.user_email = row["email"]

    module_key = _module_for_path(path, prefix)
    if module_key is None:
        # Every staff router must be represented in the permission catalogue.
        # Unknown routes fail closed instead of inheriting broad role permissions.
        raise HTTPException(status_code=403, detail="This API route has no configured permission mapping")
    action_key = _action_for_request(request.method, path)
    try:
        with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3) as conn:
            rows = conn.execute(
                """
                SELECT p.action_key, COALESCE(up.allowed, rp.allowed, false) AS allowed
                FROM app_modules m
                CROSS JOIN app_permissions p
                JOIN app_roles r ON r.name = %s AND r.is_active = TRUE
                LEFT JOIN app_role_permissions rp
                  ON rp.role_id = r.id AND rp.module_id = m.id AND rp.permission_id = p.id
                LEFT JOIN app_user_module_permissions up
                  ON up.user_id = %s AND up.module_id = m.id AND up.permission_id = p.id
                WHERE m.module_key = %s AND m.is_active = TRUE
                """,
                (role, row["id"], module_key),
            ).fetchall()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Permission storage unavailable; apply the configurable RBAC schema") from exc
    effective = {item["action_key"]: item["allowed"] for item in rows}
    if not effective.get(action_key, False):
        raise HTTPException(status_code=403, detail=f"Missing {action_key} permission for {module_key}")
