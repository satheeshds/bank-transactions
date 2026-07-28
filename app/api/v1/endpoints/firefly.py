from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json

from app.db import session as database

router = APIRouter(prefix="/api/v1", tags=["firefly"])


class FireflyPayload(BaseModel):
    base_url: str | None = None
    token: str | None = None
    timeout: int | None = None
    custom_keys: dict[str, str] | None = None


@router.get('/firefly')
def get_firefly():
    base = database.get_setting('firefly.base_url') or ''
    token = database.get_setting('firefly.token') or ''
    timeout = database.get_setting('firefly.timeout') or ''
    custom = database.get_setting('firefly.custom_keys') or ''
    try:
        timeout_int = int(timeout) if timeout != '' else None
    except Exception:
        timeout_int = None
    try:
        custom_obj = json.loads(custom) if custom else {}
    except Exception:
        custom_obj = {}
    return {
        'base_url': base,
        'token': token,
        'timeout': timeout_int,
        'custom_keys': custom_obj,
    }


@router.put('/firefly')
def put_firefly(payload: FireflyPayload):
    try:
        database.set_setting('firefly.base_url', payload.base_url or None)
        database.set_setting('firefly.token', payload.token or None)
        database.set_setting('firefly.timeout', str(payload.timeout) if payload.timeout is not None else None)
        # persist custom key/value pairs as JSON
        if payload.custom_keys is None:
            database.set_setting('firefly.custom_keys', None)
        else:
            database.set_setting('firefly.custom_keys', json.dumps(payload.custom_keys))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {'status': 'ok'}
