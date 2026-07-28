from __future__ import annotations

import socket
import time
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import build_firefly_config
from app.db import session as database
from app.services.firefly_client import build_firefly_client
from cli import sync_worker

router = APIRouter(prefix="/api/v1", tags=["status"])


@router.get("/status")
def get_status():
    """Returns connectivity and stats for the Mail2Firefly dashboard."""
    # Do not load config.toml here; prefer runtime DB settings for overrides

    # 1. Check IMAP Connectivity using configured mailboxes from DB
    imap_connected = False
    imap_error = None
    db_mailboxes = database.list_mailboxes()
    imap_mailboxes = []
    for mb in db_mailboxes:
        host = mb.get("host")
        port = mb.get("port") or 993
        connected = False
        error = None
        if host:
            try:
                with socket.create_connection((host, int(port)), timeout=2.0):
                    connected = True
            except Exception as e:
                error = str(e)
        else:
            error = "host not configured"

        imap_mailboxes.append({
            "id": mb.get("id"),
            "name": mb.get("name"),
            "host": host,
            "username": mb.get("username"),
            "connected": connected,
            "error": error,
        })

    # overall connected if any mailbox is connected
    imap_connected = any(m.get("connected") for m in imap_mailboxes)
    imap_error = None if imap_connected else "No configured mailboxes are reachable"

    # 2. Check Firefly III Connectivity
    firefly_connected = False
    firefly_latency_ms = None
    firefly_error = None

    # Use settings stored in DB (saved via UI). Do not fall back to config.toml.
    db_base = database.get_setting('firefly.base_url')
    db_token = database.get_setting('firefly.token')
    db_timeout = database.get_setting('firefly.timeout')

    if db_base or db_token:
        firefly_cfg = {
            'base_url': db_base or '',
            'token': db_token or '',
            'timeout': int(db_timeout) if db_timeout and db_timeout.isdigit() else 15,
        }
    else:
        firefly_cfg = {}

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
            "mailboxes": imap_mailboxes,
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
