"""Verified-buyer product reviews.

Public: approved reviews and rating summaries.
Customer: check eligibility and post one review per delivered product.
Staff: approve or reject reviews (catalogue module permissions apply).
"""
import logging

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter(prefix="/reviews", tags=["reviews"])
logger = logging.getLogger(__name__)

STAFF_ROLES = {"super_admin", "admin", "manager", "staff"}


def _connection():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Reviews database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Reviews database is unavailable") from exc


def _customer(request: Request) -> tuple[int, str]:
    if getattr(request.state, "role", "") != "customer" or not getattr(request.state, "customer_id", None):
        raise HTTPException(status_code=401, detail="Sign in to write a review")
    return int(request.state.customer_id), str(request.state.customer_email or "").strip().lower()


def _staff(request: Request) -> str:
    if getattr(request.state, "role", "") not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="Staff access required")
    return str(getattr(request.state, "user_email", "") or "staff")


def _public_name(full_name: str) -> str:
    parts = str(full_name or "").strip().split()
    if not parts:
        return "Customer"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0].upper()}."


def _delivered_order_id(conn, email: str, product_id: int):
    """Most recent delivered order of this customer that contains the product."""
    row = conn.execute(
        "SELECT o.id FROM orders o "
        "JOIN order_lines ol ON ol.order_id=o.id "
        "JOIN product_variants v ON v.id=ol.variant_id "
        "WHERE lower(o.customer_email)=%s AND o.status='delivered' AND v.product_id=%s "
        "ORDER BY o.created_at DESC, o.id DESC LIMIT 1",
        (email, product_id),
    ).fetchone()
    return int(row["id"]) if row else None


class ReviewCreate(BaseModel):
    product_id: int = Field(gt=0)
    rating: int = Field(ge=1, le=5)
    title: str = Field(default="", max_length=120)
    body: str = Field(default="", max_length=2000)


class ReviewDecision(BaseModel):
    decision: str = Field(pattern=r"^(approved|rejected)$")
    note: str = Field(default="", max_length=500)


@router.get("/summary")
def rating_summary():
    """Approved rating average and count per product, for shop cards."""
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT product_id, round(avg(rating)::numeric, 1) AS rating_average, count(*) AS review_count "
                "FROM product_reviews WHERE status='approved' GROUP BY product_id"
            ).fetchall()
    except psycopg.Error as exc:
        logger.warning("Review summary unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Reviews are unavailable; verify migration 051") from exc
    return {"items": [
        {"product_id": int(r["product_id"]), "rating_average": float(r["rating_average"]), "review_count": int(r["review_count"])}
        for r in rows
    ]}


@router.get("/product/{product_id}")
def product_reviews(product_id: int, limit: int = Query(default=20, ge=1, le=50), offset: int = Query(default=0, ge=0)):
    try:
        with _connection() as conn:
            summary = conn.execute(
                "SELECT round(avg(rating)::numeric, 1) AS avg, count(*) AS n FROM product_reviews "
                "WHERE product_id=%s AND status='approved'", (product_id,),
            ).fetchone()
            rows = conn.execute(
                "SELECT r.id, r.rating, r.title, r.body, r.created_at, c.full_name "
                "FROM product_reviews r JOIN customer_accounts c ON c.id=r.customer_id "
                "WHERE r.product_id=%s AND r.status='approved' "
                "ORDER BY r.created_at DESC, r.id DESC LIMIT %s OFFSET %s",
                (product_id, limit, offset),
            ).fetchall()
    except psycopg.Error as exc:
        logger.warning("Product reviews unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Reviews are unavailable; verify migration 051") from exc
    count = int(summary["n"] or 0)
    return {
        "product_id": product_id,
        "rating_average": float(summary["avg"]) if count else 0,
        "review_count": count,
        "items": [
            {"id": int(r["id"]), "rating": int(r["rating"]), "title": r["title"], "body": r["body"],
             "created_at": r["created_at"], "author": _public_name(r["full_name"]), "verified_buyer": True}
            for r in rows
        ],
    }


@router.get("/eligibility")
def review_eligibility(request: Request, product_id: int = Query(gt=0)):
    customer_id, email = _customer(request)
    try:
        with _connection() as conn:
            existing = conn.execute(
                "SELECT id, rating, title, body, status FROM product_reviews WHERE product_id=%s AND customer_id=%s",
                (product_id, customer_id),
            ).fetchone()
            if existing:
                return {"can_review": False, "reason": "already_reviewed", "existing": existing}
            if _delivered_order_id(conn, email, product_id) is None:
                return {"can_review": False, "reason": "not_delivered", "existing": None}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Reviews are unavailable; verify migration 051") from exc
    return {"can_review": True, "reason": "ok", "existing": None}


@router.post("", status_code=201)
def create_review(payload: ReviewCreate, request: Request):
    customer_id, email = _customer(request)
    title, body = payload.title.strip(), payload.body.strip()
    try:
        with _connection() as conn:
            with conn.transaction():
                order_id = _delivered_order_id(conn, email, payload.product_id)
                if order_id is None:
                    raise HTTPException(status_code=403, detail="You can review a product only after your order with it is delivered")
                try:
                    row = conn.execute(
                        "INSERT INTO product_reviews (product_id, customer_id, order_id, rating, title, body, status) "
                        "VALUES (%s,%s,%s,%s,%s,%s,'approved') RETURNING id, status",
                        (payload.product_id, customer_id, order_id, payload.rating, title, body),
                    ).fetchone()
                except psycopg.errors.UniqueViolation as exc:
                    raise HTTPException(status_code=409, detail="You have already reviewed this product") from exc
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.warning("Review save failed: %s", exc)
        raise HTTPException(status_code=503, detail="Could not save the review; verify migration 051") from exc
    return {"id": int(row["id"]), "status": row["status"], "message": "Thank you. Your review is now live."}


@router.get("/admin")
def admin_list(request: Request, status: str = Query(default="pending", pattern=r"^(pending|approved|rejected|all)$"), limit: int = Query(default=100, ge=1, le=200)):
    _staff(request)
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT r.id, r.product_id, p.name AS product_name, r.rating, r.title, r.body, r.status, "
                "r.moderation_note, r.moderated_by, r.moderated_at, r.created_at, "
                "c.full_name AS customer_name, c.email AS customer_email, o.order_number "
                "FROM product_reviews r JOIN products p ON p.id=r.product_id "
                "JOIN customer_accounts c ON c.id=r.customer_id LEFT JOIN orders o ON o.id=r.order_id "
                "WHERE (%s='all' OR r.status=%s) ORDER BY r.created_at DESC, r.id DESC LIMIT %s",
                (status, status, limit),
            ).fetchall()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Reviews are unavailable; verify migration 051") from exc
    return {"items": rows}


@router.post("/admin/{review_id}/approve")
def admin_decide(review_id: int, payload: ReviewDecision, request: Request):
    staff = _staff(request)
    try:
        with _connection() as conn:
            row = conn.execute(
                "UPDATE product_reviews SET status=%s, moderation_note=%s, moderated_by=%s, moderated_at=now(), updated_at=now() "
                "WHERE id=%s RETURNING id, status",
                (payload.decision, payload.note.strip(), staff, review_id),
            ).fetchone()
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Reviews are unavailable; verify migration 051") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"id": int(row["id"]), "status": row["status"]}
