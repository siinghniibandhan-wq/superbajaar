from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.catalogue import router as catalogue_router
from app.api.v1.health import router as health_router
from app.api.v1.inventory import router as inventory_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)

allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(catalogue_router, prefix=settings.api_v1_prefix)
app.include_router(inventory_router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict[str, str | int]:
    return {"name": settings.app_name, "status": "running", "port": settings.port}
