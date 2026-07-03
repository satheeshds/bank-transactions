from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Any
import socket

from app.services import imap as imap_service

from app.db import session as database

router = APIRouter(prefix="/api/v1", tags=["mailboxes"])


@router.get("/mailboxes")
def list_mailboxes() -> dict[str, Any]:
    try:
        boxes = database.list_mailboxes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Attach a quick connectivity check per mailbox (socket-level)
    enhanced = []
    for b in boxes:
        host = b.get("host")
        port = b.get("port") or 993
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

        nb = dict(b)
        nb["connected"] = connected
        nb["error"] = error
        enhanced.append(nb)

    return {"mailboxes": enhanced}



@router.post("/mailboxes/test")
def test_mailbox_connection(payload: dict) -> JSONResponse:
    """Test IMAP connectivity for a mailbox payload.

    Expects same fields as adding a mailbox. Returns JSON with connected/error.
    """
    host = payload.get("host")
    port = payload.get("port") or 993
    username = payload.get("username")
    password = payload.get("password")

    if not host:
        raise HTTPException(status_code=400, detail="`host` is required for test")

    try:
        # First quick socket check
        with socket.create_connection((host, int(port)), timeout=3.0):
            pass
    except Exception as e:
        return JSONResponse(status_code=200, content={"connected": False, "error": f"socket: {e}"})

    # Try a full IMAP login if imap_tools is available and credentials provided
    try:
        try:
            MailBox = imap_service.MailBox
        except Exception:
            MailBox = None

        if MailBox is None:
            return JSONResponse(status_code=200, content={"connected": True, "warning": "imap_tools not installed; socket check passed"})

        if not username or not password:
            return JSONResponse(status_code=200, content={"connected": True, "warning": "Socket ok; credentials not provided for full IMAP login"})

        # perform login attempt
        mb = imap_service.MailBox(host).login(username, password)
        try:
            mb.logout()
        except Exception:
            pass
        return JSONResponse(status_code=200, content={"connected": True})
    except Exception as e:
        return JSONResponse(status_code=200, content={"connected": False, "error": str(e)})


@router.post("/mailboxes")
def add_mailbox(payload: dict) -> JSONResponse:
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="`name` is required")

    # mailbox fields
    host = payload.get("host")
    port = payload.get("port")
    username = payload.get("username")
    password = payload.get("password")
    encryption = payload.get("encryption")
    smtp_host = payload.get("smtp_host")
    smtp_port = payload.get("smtp_port")

    try:
        new_id = database.add_mailbox(
            name=name,
            host=host,
            port=int(port) if port is not None and str(port).isdigit() else None,
            username=username,
            password=password,
            encryption=encryption,
            smtp_host=smtp_host,
            smtp_port=int(smtp_port) if smtp_port is not None and str(smtp_port).isdigit() else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(status_code=201, content={"status": "ok", "id": new_id, "name": name})


@router.put("/mailboxes/{mailbox_id}")
def update_mailbox_endpoint(mailbox_id: int, payload: dict) -> JSONResponse:
    try:
        database.update_mailbox(
            mailbox_id=mailbox_id,
            name=payload.get('name'),
            host=payload.get('host'),
            port=int(payload.get('port')) if payload.get('port') is not None and str(payload.get('port')).isdigit() else None,
            username=payload.get('username'),
            password=payload.get('password'),
            encryption=payload.get('encryption'),
            smtp_host=payload.get('smtp_host'),
            smtp_port=int(payload.get('smtp_port')) if payload.get('smtp_port') is not None and str(payload.get('smtp_port')).isdigit() else None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(status_code=200, content={"status": "ok", "id": mailbox_id})


@router.delete("/mailboxes/{mailbox_id}")
def delete_mailbox_endpoint(mailbox_id: int) -> JSONResponse:
    try:
        database.delete_mailbox(mailbox_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse(status_code=200, content={"status": "deleted", "id": mailbox_id})
