from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import sync_worker

router = APIRouter(prefix="/api/v1", tags=["sync"])


@router.post("/sync")
def trigger_sync():
    """Triggers a background synchronization run."""
    if sync_worker.is_sync_running():
        return JSONResponse(
            status_code=409,
            content={"message": "Sync is already in progress.", "run_id": sync_worker.get_current_run_id()}
        )
    
    try:
        run_id = sync_worker.start_sync_background()
        return {"message": "Sync run triggered successfully.", "run_id": run_id}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to start sync: {e}"}
        )
