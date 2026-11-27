import asyncio
import logging
from contextlib import asynccontextmanager

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.catalogue import router as catalogue_router
from app.api.health import router as health_router
from app.api.inventory import router as inventory_router
from app.api.inventory_locations import router as inventory_locations_router
from app.api.orders import router as orders_router
from app.api.payments import router as payments_router, razorpay_router
from app.api.delivery import router as delivery_router
from app.api.fulfilment import router as fulfilment_router
from app.api.customers import router as customers_router
from app.api.identity import router as identity_router
from app.api.purchasing import router as purchasing_router
from app.api.purchasing_lifecycle import router as purchasing_lifecycle_router
from app.api.hr import router as hr_router
from app.api.auth import router as auth_router
from app.api.portal_invitations import router as portal_invitations_router
from app.api.vendor_portal import router as vendor_portal_router
from app.api.employee_portal import router as employee_portal_router
from app.api.customer_auth import router as customer_auth_router
from app.api.customer_oauth import router as customer_oauth_router
from app.api.customer_identity_verification import router as customer_identity_verification_router
from app.api.loyalty import router as loyalty_router
from app.api.reviews import router as reviews_router
from app.api.purchase_modes import router as purchase_modes_router
from app.api.accounting import router as accounting_router
from app.api.organisation_policies import router as organisation_policies_router
from app.api.pricing import router as pricing_router
from app.api.pos import router as pos_router
from app.api.pos_registers import router as pos_registers_router
from app.api.reports import router as reports_router
from app.core.config import settings
from app.services.loyalty_redemption import expire_due_coins

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """Add conservative browser security headers to every HTTP response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                if scope.get("path") in {"/docs", "/redoc", "/docs/oauth2-redirect"}:
                    csp = b"default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
                else:
                    csp = b"default-src 'none'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'"
                security_headers = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"content-security-policy", csp),
                ]
                headers.extend((key, value) for key, value in security_headers if key not in existing)
                if settings.app_env.lower() == "production" and b"strict-transport-security" not in existing:
                    headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


def _run_scheduled_loyalty_expiry() -> None:
    """Run expiry once across all API workers, with an accounting-safe transaction."""
    if not settings.database_url:
        return
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        with conn.transaction():
            lock = conn.execute(
                "SELECT pg_try_advisory_xact_lock(173528915, 28) AS acquired"
            ).fetchone()
            if not lock["acquired"]:
                return
            result = expire_due_coins(conn, limit=1000)
    if result["expired_lots"]:
        logger.info("Super Coins scheduled expiry posted %s coins across %s lots",
                    result["expired_coins"], result["expired_lots"])


async def _loyalty_expiry_worker() -> None:
    # A transaction-scoped PostgreSQL advisory lock prevents duplicate work
    # when Gunicorn runs multiple application workers or EC2 instances.
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(_run_scheduled_loyalty_expiry)
        except Exception:
            logger.exception("Scheduled Super Coins expiry failed; it will retry next hour")


@asynccontextmanager
async def lifespan(_app):
    worker = asyncio.create_task(_loyalty_expiry_worker())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
from app.core.auth_middleware import require_active_session

app = FastAPI(title=settings.app_name, dependencies=[Depends(require_active_session)], lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)

allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # Amplify URLs can have multiple labels, e.g. main.<app-id>.amplifyapp.com.
    # Keep explicit configured origins and allow only this Amplify app (any branch).
    allow_origin_regex=r"https://(?:[a-zA-Z0-9-]+[.])*d334sr8jkx3zux[.]amplifyapp[.]com",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(catalogue_router, prefix=settings.api_prefix)
app.include_router(inventory_router, prefix=settings.api_prefix)
app.include_router(inventory_locations_router, prefix=settings.api_prefix)
app.include_router(orders_router, prefix=settings.api_prefix)
app.include_router(payments_router, prefix=settings.api_prefix)
app.include_router(razorpay_router, prefix=settings.api_prefix)
app.include_router(delivery_router, prefix=settings.api_prefix)
app.include_router(fulfilment_router, prefix=settings.api_prefix)
app.include_router(customers_router, prefix=settings.api_prefix)
app.include_router(identity_router, prefix=settings.api_prefix)
app.include_router(purchasing_router, prefix=settings.api_prefix)
app.include_router(purchasing_lifecycle_router, prefix=settings.api_prefix)
app.include_router(hr_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(portal_invitations_router, prefix=settings.api_prefix)
app.include_router(vendor_portal_router, prefix=settings.api_prefix)
app.include_router(employee_portal_router, prefix=settings.api_prefix)
app.include_router(customer_auth_router, prefix=settings.api_prefix)
app.include_router(customer_oauth_router, prefix=settings.api_prefix)
app.include_router(customer_identity_verification_router, prefix=settings.api_prefix)
app.include_router(loyalty_router, prefix=settings.api_prefix)
app.include_router(reviews_router, prefix=settings.api_prefix)
app.include_router(purchase_modes_router, prefix=settings.api_prefix)
app.include_router(accounting_router, prefix=settings.api_prefix)
app.include_router(organisation_policies_router, prefix=settings.api_prefix)
app.include_router(pricing_router, prefix=settings.api_prefix)
app.include_router(pos_router, prefix=settings.api_prefix)
app.include_router(pos_registers_router, prefix=settings.api_prefix)
app.include_router(reports_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str | int]:
    return {"name": settings.app_name, "status": "running", "port": settings.port}
