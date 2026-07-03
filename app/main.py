from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.db import session as database
from app.api.v1.endpoints import status, sync, logs, transactions, rules, mailboxes
from app.api.v1.endpoints import firefly

# Create FastAPI app
app = FastAPI(title="Mail2Firefly Dashboard")


def _get_dist_dir() -> str:
    """Get the path to the built frontend distribution directory."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "dist")


# Serve the Vite-built frontend (static/dist/) — populated by `npm run build` in frontend/
DIST_DIR = _get_dist_dir()
ASSETS_DIR = os.path.join(DIST_DIR, "assets")
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="vite-assets")

# Legacy static mount (CSS, old JS files still reachable if needed)
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup_event():
    """Initialize the SQLite database tables."""
    database.init_db()


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    """Serve the Vue 3 frontend built by Vite."""
    index = os.path.join(DIST_DIR, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return HTMLResponse(
        '<p style="font-family:monospace;padding:2rem">'
        'Frontend not built. Run: <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>'
        '</p>',
        status_code=503,
    )


# Include all API routers
app.include_router(status.router)
app.include_router(sync.router)
app.include_router(logs.router)
app.include_router(transactions.router)
app.include_router(rules.router)
app.include_router(mailboxes.router)
app.include_router(firefly.router)


# Keep legacy /api/* routes for backward compatibility
@app.get("/api/status")
def get_status_legacy():
    """Legacy endpoint - use /api/v1/status instead."""
    return status.get_status()


@app.post("/api/sync")
def trigger_sync_legacy():
    """Legacy endpoint - use /api/v1/sync instead."""
    return sync.trigger_sync()


@app.get("/api/logs")
def get_logs_legacy(limit: int = 100):
    """Legacy endpoint - use /api/v1/logs instead."""
    return logs.get_logs(limit)


@app.get("/api/transactions")
def get_transactions_legacy(limit: int = 50, status_filter: str | None = None):
    """Legacy endpoint - use /api/v1/transactions instead."""
    return transactions.get_transactions(limit, status_filter)


@app.get("/api/rules")
def get_rules_legacy():
    """Legacy endpoint - use /api/v1/rules instead."""
    return rules.get_rules()
