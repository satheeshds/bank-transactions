from __future__ import annotations

from fastapi import APIRouter

from app.db import session as database

router = APIRouter(prefix="/api/v1", tags=["transactions"])


@router.get("/transactions")
def get_transactions(limit: int = 50, status: str | None = None):
    """Fetches recent parsed transactions, optionally filtered by status."""
    transactions = database.get_recent_transactions(limit)
    if status:
        transactions = [t for t in transactions if t.get("status") == status]
    return {"transactions": transactions}
