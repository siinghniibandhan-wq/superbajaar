"""Catalogue endpoints backed by PostgreSQL.

These routes require DATABASE_URL and the reviewed target schema. They do not
connect to or migrate a database during import/startup.
"""
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter(prefix="/catalogue", tags=["catalogue"])


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    parent_id: int | None = Field(default=None, gt=0)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=260, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category_id: int | None = Field(default=None, gt=0)
    description: str | None = None
    brand: str | None = Field(default=None, max_length=160)
    tax_code: str | None = Field(default=None, max_length=32)
    tax_rate: float | None = Field(default=None, ge=0, le=100)


def _connection():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Catalogue database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Catalogue database is unavailable") from exc


def _duplicate_or_database_error(exc: psycopg.Error) -> HTTPException:
    if getattr(exc, "sqlstate", None) == "23505":
        return HTTPException(status_code=409, detail="A record with this slug or unique value already exists")
    if getattr(exc, "sqlstate", None) == "23503":
        return HTTPException(status_code=422, detail="The referenced category or parent does not exist")
    return HTTPException(status_code=503, detail="Catalogue database operation failed")


@router.get("/categories")
def list_categories(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, parent_id, name, slug, description, is_active, created_at, updated_at "
            "FROM categories ORDER BY name LIMIT %s OFFSET %s", (limit, offset)
        ).fetchall()
    return {"items": rows, "limit": limit, "offset": offset}


@router.post("/categories", status_code=201)
def create_category(payload: CategoryCreate) -> dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Category name cannot be blank")
    try:
        with _connection() as conn:
            row = conn.execute(
                "INSERT INTO categories (parent_id, name, slug, description) "
                "VALUES (%s, %s, %s, %s) "
                "RETURNING id, parent_id, name, slug, description, is_active, created_at, updated_at",
                (payload.parent_id, name, payload.slug, payload.description),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        raise _duplicate_or_database_error(exc) from exc


@router.get("/products")
def list_products(
    category_id: int | None = Query(default=None, gt=0),
    status: str = Query(default="active", pattern="^(draft|active|archived|all)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if category_id is not None:
        clauses.append("category_id = %s")
        params.append(category_id)
    if status != "all":
        clauses.append("status = %s")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, category_id, name, slug, description, brand, status, tax_code, tax_rate, created_at, updated_at "
            f"FROM products {where} ORDER BY name LIMIT %s OFFSET %s", tuple(params)
        ).fetchall()
    return {"items": rows, "limit": limit, "offset": offset}


@router.post("/products", status_code=201)
def create_product(payload: ProductCreate) -> dict[str, Any]:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Product name cannot be blank")
    try:
        with _connection() as conn:
            row = conn.execute(
                "INSERT INTO products (category_id, name, slug, description, brand, tax_code, tax_rate) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id, category_id, name, slug, description, brand, status, tax_code, tax_rate, created_at, updated_at",
                (payload.category_id, name, payload.slug, payload.description, payload.brand, payload.tax_code, payload.tax_rate),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        raise _duplicate_or_database_error(exc) from exc
