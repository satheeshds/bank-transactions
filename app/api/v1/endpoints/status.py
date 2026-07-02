from __future__ import annotations

import socket
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import load_config, build_firefly_config, build_source_definitions
from app.db import session as database
from app.services.firefly_client import build_firefly_client
from cli import sync_worker

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status")
def get_status():
    """Returns connectivity and stats for the Mail2Firefly dashboard."""
    try:
        config = load_config()
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to load config.toml: {e}"}
        )

    # 1. Check IMAP Connectivity
    imap_connected = False
    imap_error = None
    mailbox_cfg = config.get("mailbox", {})
    imap_host = mailbox_cfg.get("host")
    if imap_host:
        try:
            # Quick socket check on port 993 (IMAPS) with a 2-second timeout
            with socket.create_connection((imap_host, 993), timeout=2.0):
                imap_connected = True
        except Exception as e:
            imap_error = str(e)
    else:
        imap_error = "IMAP host not configured"

    # 2. Check Firefly III Connectivity
    firefly_connected = False
    firefly_latency_ms = None
    firefly_error = None
    firefly_cfg = build_firefly_config(config)
    
    if firefly_cfg.get("base_url") and firefly_cfg.get("token"):
        try:
            client = build_firefly_client(firefly_cfg)
            start_time = time.time()
            # Try to hit the about endpoint to verify API token
            client._request("GET", "/api/v1/about")
            firefly_latency_ms = int((time.time() - start_time) * 1000)
            firefly_connected = True
        except Exception as e:
            firefly_error = str(e)
    else:
        firefly_error = "Firefly III client not configured"

    # 3. Get Stats and Last Run Details from SQLite
    stats = database.get_stats_today()
    is_running = sync_worker.is_sync_running()
    current_run_id = sync_worker.get_current_run_id()

    return {
        "is_running": is_running,
        "current_run_id": current_run_id,
        "imap": {
            "connected": imap_connected,
            "host": imap_host,
            "username": mailbox_cfg.get("username"),
            "error": imap_error
        },
        "firefly": {
            "connected": firefly_connected,
            "base_url": firefly_cfg.get("base_url"),
            "latency_ms": firefly_latency_ms,
            "error": firefly_error
        },
        "stats": {
            "parsed_today": stats["parsed_today"],
            "errors_today": stats["errors_today"],
            "total_runs_today": stats["total_runs_today"]
        },
        "latest_run": stats["latest_run"]
    }
