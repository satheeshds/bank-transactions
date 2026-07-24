from __future__ import annotations
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import Any
import socket
from datetime import datetime, date

from app.services import imap as imap_service

from app.db import session as database
from app import config as app_config
from app.config import load_config

router = APIRouter(prefix="/api/v1", tags=["mailboxes"])

logger = logging.getLogger(__name__)

@router.get("/mailboxes")
def list_mailboxes() -> dict[str, Any]:
    try:
        boxes = database.list_mailboxes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # If no mailboxes are stored in DB, fall back to config.toml definitions
    if not boxes:
        try:
            cfg = load_config()
            defs = app_config.build_source_definitions(cfg)
            boxes = []
            for d in defs:
                mb = d.get('mailbox') or {}
                boxes.append({
                    'id': None,
                    'name': d.get('name') or 'config',
                    'host': mb.get('host'),
                    'port': mb.get('port'),
                    'username': mb.get('username'),
                    'encryption': mb.get('encryption'),
                    'processed_tag': d.get('processed_tag') or mb.get('processed_tag'),
                })
        except Exception:
            # ignore config load errors and proceed with empty list
            boxes = []

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


@router.get("/mailboxes/{mailbox_id}/sample")
def mailbox_sample(mailbox_id: int) -> dict:
    """Fetch a single sample email body from the mailbox (requires imap_tools).

    Returns a JSON dict: { "sample_text": str } or an error message.
    """
    # Prefer mailbox from DB including credentials
    try:
        mb = database.get_mailbox_by_id(mailbox_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # If not in DB, try config sources
    if mb is None:
        try:
            cfg = load_config()
            defs = app_config.build_source_definitions(cfg)
            for d in defs:
                if d.get("id") == mailbox_id or d.get("name") == mailbox_id:
                    mb = d.get("mailbox") or {}
                    break
        except Exception:
            mb = None

    if mb is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    # Validate mailbox config
    if not mb.get("host"):
        return {"error": "mailbox host not configured"}
    if not mb.get("username") or not mb.get("password"):
        return {"error": "mailbox username/password not configured"}

    # Attempt to fetch a sample message using imap_tools
    try:
        MailBox = imap_service.MailBox
        if MailBox is None:
            return {"error": "imap_tools not installed on server"}

        # Build mailbox config structure expected by service
        mb_conf = {
            "host": mb.get("host"),
            "username": mb.get("username"),
            "password": mb.get("password"),
        }
        client = imap_service.get_mailbox_client(mb_conf)
        try:
            # fetch most recent message; imap_tools MailBox.fetch supports reverse=True and limit
            messages = list(client.fetch(limit=1, reverse=True))
            if not messages:
                return {"sample_text": "", "sample_meta": {}}
            msg = messages[0]
            # Message may have text/plain or html; prefer plain
            body = getattr(msg, "text", None) or getattr(msg, "html", None) or ""
            # collect metadata for IMAP field preview
            meta = {
                "subject": getattr(msg, "subject", None) or "",
                "from": getattr(msg, "from_", None) or "",
                "to": getattr(msg, "to", None) or "",
                "cc": getattr(msg, "cc", None) or "",
                "bcc": getattr(msg, "bcc", None) or "",
                "sent_date": getattr(msg, "date", None) or "",
                "message_id": getattr(msg, "message_id", None) or "",
            }
            return {"sample_text": body, "sample_meta": meta}
        finally:
            try:
                client.logout()
            except Exception:
                pass
    except Exception as e:
        return {"error": str(e)}



@router.post("/mailboxes/{mailbox_id}/sample")
def mailbox_sample_with_filter(mailbox_id: int, payload: dict) -> dict:
    """Fetch a sample email matching provided filter conditions.

    Expects JSON payload with optional `conditions` (list) and `condition_mode` ('AND'|'OR').
    """
    logger.debug("getting sample")
    # Reuse the same mailbox resolution as the GET endpoint
    try:
        mb = database.get_mailbox_by_id(mailbox_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if mb is None:
        try:
            cfg = load_config()
            defs = app_config.build_source_definitions(cfg)
            for d in defs:
                if d.get("id") == mailbox_id or d.get("name") == mailbox_id:
                    mb = d.get("mailbox") or {}
                    break
        except Exception:
            mb = None

    if mb is None:
        raise HTTPException(status_code=404, detail="Mailbox not found")

    # Build query filter from payload.conditions
    conditions = payload.get("conditions") or []
    condition_mode = payload.get("condition_mode") or None

    try:
        MailBox = imap_service.MailBox
        if MailBox is None:
            return {"error": "imap_tools not installed on server"}

        mb_conf = {"host": mb.get("host"), "username": mb.get("username"), "password": mb.get("password")}
        client = imap_service.get_mailbox_client(mb_conf)
        try:
            # Build imap_tools query kwargs from conditions: simple mapping
            query_filter = {}
            for c in conditions:
                field = c.get('field')
                value = c.get('value')
                neg = c.get('not')
                if neg is True:
                    query_filter["not"] = True
                if field and value:
                    # map our fields to imap_tools keywords
                    if field == 'from':
                        query_filter['from_'] = value
                    elif field == 'to':
                        query_filter['to'] = value
                    elif field == 'subject':
                        query_filter['subject'] = value
                    elif field == 'text':
                        query_filter['text'] = value
                    elif field == 'sent_date':
                        # imap_tools expects datetime.date for date filters.
                        # Determine operator and map to imap keywords: equals -> date, >= -> since, <= -> before
                        op = (c.get('operator') or '').strip()
                        parsed_date = None
                        if isinstance(value, date):
                            parsed_date = value
                        else:
                            try:
                                parsed_date = datetime.fromisoformat(str(value)).date()
                            except Exception:
                                for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
                                    try:
                                        parsed_date = datetime.strptime(str(value), fmt).date()
                                        break
                                    except Exception:
                                        parsed_date = None
                        if not parsed_date:
                            continue

                        if op in ("equals", "=", "=="):
                            query_filter['sent_date'] = parsed_date
                        elif op in (">=", "greater than or equal", ">"):
                            # use sent_date_gte for on-or-after
                            query_filter['sent_date_gte'] = parsed_date
                        elif op in ("<=", "less than or equal", "<"):
                            # use sent_date_lt for strictly before; caller can adjust to make inclusive if desired
                            query_filter['sent_date_lt'] = parsed_date
                        else:
                            # unknown operator: default to exact date
                            query_filter['sent_date'] = parsed_date

            # build_query will add processed_tag if configured
            logger.debug("building query")
            q = imap_service.build_query(conditions, processed_tag=mb.get('processed_tag'))
            messages = list(client.fetch(q, limit=1, reverse=True))
            logger.debug(f"fetched {len(messages)} messages")
            if not messages:
                return {"sample_text": "", "sample_meta": {}}
            msg = messages[0]
            body = getattr(msg, "text", None) or getattr(msg, "html", None) or ""
            meta = {
                "subject": getattr(msg, "subject", None) or "",
                "from": getattr(msg, "from_", None) or "",
                "to": getattr(msg, "to", None) or "",
                "cc": getattr(msg, "cc", None) or "",
                "bcc": getattr(msg, "bcc", None) or "",
                "date": getattr(msg, "date", None) or "",
                "message_id": getattr(msg, "message_id", None) or "",
            }
            return {"sample_text": body, "sample_meta": meta}
        finally:
            try:
                client.logout()
            except Exception:
                pass
    except Exception as e:
        return {"error": str(e)}
