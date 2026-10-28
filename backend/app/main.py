from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.catalogue import router as catalogue_router
from app.api.health import router as health_router
from app.api.inventory import router as inventory_router
from app.api.orders import router as orders_router
from app.api.payments import router as payments_router
from app.api.delivery import router as delivery_router
from app.api.customers import router as customers_router
from app.api.purchasing import router as purchasing_router
from app.api.auth import router as auth_router
from app.api.loyalty import router as loyalty_router
from app.core.config import settings
from app.core.auth_middleware import require_active_session

app = FastAPI(title=settings.app_name, dependencies=[Depends(require_active_session)])

allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # Amplify URLs can have multiple labels, e.g. main.<app-id>.amplifyapp.com.
    # Keep explicit configured origins and allow HTTPS Amplify app hostnames.
    allow_origin_regex=r"https://(?:[a-zA-Z0-9-]+[.])+amplifyapp[.]com",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router, prefix=settings.api_prefix)
app.include_router(catalogue_router, prefix=settings.api_prefix)
app.include_router(inventory_router, prefix=settings.api_prefix)
app.include_router(orders_router, prefix=settings.api_prefix)
app.include_router(payments_router, prefix=settings.api_prefix)
app.include_router(delivery_router, prefix=settings.api_prefix)
app.include_router(customers_router, prefix=settings.api_prefix)
app.include_router(purchasing_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(loyalty_router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict[str, str | int]:
    return {"name": settings.app_name, "status": "running", "port": settings.port}
