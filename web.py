from __future__ import annotations

import os
import socket
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import load_config, build_firefly_config, build_source_definitions
import database
from firefly_client import FireflyClient
import sync_worker

# Create FastAPI app
app = FastAPI(title="Mail2Firefly Dashboard")

# Serve the Vite-built frontend (static/dist/) — populated by `npm run build` in frontend/
DIST_DIR = os.path.join(os.path.dirname(__file__), "static", "dist")
ASSETS_DIR = os.path.join(DIST_DIR, "assets")
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="vite-assets")

# Legacy static mount (CSS, old JS files still reachable if needed)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup_event():
    # Initialize the SQLite database tables
    database.init_db()


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    index = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return HTMLResponse(
        '<p style="font-family:monospace;padding:2rem">'
        'Frontend not built. Run: <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>'
        '</p>',
        status_code=503,
    )


@app.get("/api/status")
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
            client = FireflyClient(
                base_url=firefly_cfg["base_url"],
                token=firefly_cfg["token"],
                timeout=3
            )
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


@app.post("/api/sync")
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


@app.get("/api/logs")
def get_logs(limit: int = 100):
    """Fetches recent execution logs."""
    logs = database.get_recent_logs(limit)
    return {"logs": logs}


@app.get("/api/transactions")
def get_transactions(limit: int = 50, status: str | None = None):
    """Fetches recent parsed transactions, optionally filtered by status."""
    transactions = database.get_recent_transactions(limit)
    if status:
        transactions = [t for t in transactions if t.get("status") == status]
    return {"transactions": transactions}


@app.get("/api/rules")
def get_rules():
    """Fetches defined parsing rules and sources."""
    try:
        config = load_config()
        sources = build_source_definitions(config)
        
        rules_list = []
        for src in sources:
            patterns = src.get("transaction_patterns") or []
            if isinstance(patterns, dict):
                patterns = [patterns]
                
            for pat in patterns:
                rules_list.append({
                    "source_name": src.get("name") or "Unnamed Source",
                    "rule_name": pat.get("name") or "Unnamed Rule",
                    "regex": pat.get("regex") or pat.get("pattern"),
                    "transaction_type": pat.get("transaction_type") or "withdrawal",
                    "card_last4": pat.get("defaults", {}).get("card_last4")
                })
        return {"rules": rules_list}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to retrieve rules: {e}"}
        )
