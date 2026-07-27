from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.session import get_db_connection

router = APIRouter(prefix="/api/v1", tags=["settings"])


class SettingsIn(BaseModel):
    key: str
    value: str | None = None


@router.get('/settings/{key}')
def get_setting(key: str):
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT value FROM settings WHERE key = ?', (key,))
        row = c.fetchone()

    # Avoid returning secrets to the client
    if key.lower().endswith(('api_key', 'token')):
        return {'value': None, 'configured': bool(row and row[0])}

    return {'value': row[0] if row else None}


@router.post('/settings')
def set_setting(s: SettingsIn):
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (s.key, s.value))
            conn.commit()
        return {'saved': True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
