from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.session import get_db_connection, set_setting as db_set_setting

router = APIRouter(prefix="/api/v1", tags=["settings"])


class SettingsIn(BaseModel):
    key: str
    value: str | None = None


@router.get('/settings/{key}')
def get_setting(key: str):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT value FROM settings WHERE `key` = ?', (key,))
        row = c.fetchone()

    # Avoid returning secrets to the client
    if key.lower().endswith(('api_key', 'token')):
        return {'value': None, 'configured': bool(row and (row.get('value') if isinstance(row, dict) else row[0]))}

    if not row:
        return {'value': None}
    return {'value': row.get('value') if isinstance(row, dict) else row[0]}


@router.post('/settings')
def set_setting(s: SettingsIn):
    try:
        db_set_setting(s.key, s.value)
        return {'saved': True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
