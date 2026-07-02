from __future__ import annotations

from fastapi import APIRouter

from app.db import session as database

router = APIRouter(prefix="/api/v1", tags=["logs"])


@router.get("/logs")
def get_logs(limit: int = 100):
    """Fetches recent execution logs."""
    logs = database.get_recent_logs(limit)
    return {"logs": logs}
