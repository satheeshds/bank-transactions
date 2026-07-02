from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Any

from app.db import session as database

router = APIRouter(prefix="/api/v1", tags=["mailboxes"])


@router.get("/mailboxes")
def list_mailboxes() -> dict[str, Any]:
    try:
        boxes = database.list_mailboxes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # strip any internal-only fields (none left) and return
    return {"mailboxes": boxes}


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
