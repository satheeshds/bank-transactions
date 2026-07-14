from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from typing import List
import logging

from app.db import session as database
from app.services.firefly_client import build_firefly_client, FireflyClientError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["autocomplete"])


@router.get('/autocomplete/{kind}')
def autocomplete(kind: str, query: str = Query('', alias='query'), limit: int = 10, date: str | None = None):
    """Autocomplete that proxies to Firefly endpoints using stored settings.

    Supported kinds: accounts, tags, categories, currencies, transaction_types
    Returns an array of candidate objects (may be empty).
    """
    kind = kind.lower()
    if kind not in ('accounts', 'tags', 'categories', 'currencies', 'transaction_types'):
        raise HTTPException(status_code=404, detail='Unknown autocomplete kind')

    logger.debug('autocomplete request: kind=%s query=%s limit=%s date=%s', kind, query, limit, date)
    base = database.get_setting('firefly.base_url') or ''
    token = database.get_setting('firefly.token') or ''
    timeout = database.get_setting('firefly.timeout') or None
    if not base or not token:
        logger.debug('firefly not configured: base=%s token=%s', bool(base), bool(token))
        # Firefly not configured
        return []

    # Map our kind to Firefly autocomplete endpoints (use Firefly's /v1/autocomplete/{kind})
    valid_kinds = ('accounts', 'tags', 'categories', 'currencies', 'transaction_types')
    endpoint = kind
    # Build params (Firefly expects `query`, `limit`, optional `date`)
    params = {}
    if query:
        params['query'] = query
    params['limit'] = limit
    if date:
        params['date'] = date

    # Use Firefly client service to make the request
    try:
        cfg = { 'base_url': base, 'token': token }
        if timeout is not None:
            try:
                cfg['timeout'] = int(timeout)
            except Exception:
                pass
        logger.debug('building Firefly client with base=%s timeout=%s', base, cfg.get('timeout'))
        client = build_firefly_client(cfg)
    except Exception as e:
        logger.exception('failed to build Firefly client: %s', e)
        return []

    # create path with query string; Firefly autocomplete path is /v1/autocomplete/{endpoint}
    qs = '&'.join([f"{k}={str(v)}" for k,v in params.items()])
    path = f"/api/v1/autocomplete/{endpoint}"
    if qs:
        path = f"{path}?{qs}"
    try:
        logger.debug('calling Firefly path=%s', path)
        data = client._request('GET', path)
        logger.debug('firefly response received: %s', type(data))
    except FireflyClientError as e:
        logger.exception('firefly request failed: %s', e)
        return []
    except Exception as e:
        logger.exception('unexpected error calling firefly: %s', e)
        return []
# Firefly responses vary; normalize into [{id,label}, ...]
    if isinstance(data, dict) and 'data' in data:
        items = data['data']
    elif isinstance(data, list):
        items = data
    else:
        items = []

    out = []
    logger.debug('normalizing %d items', len(items) if hasattr(items, '__len__') else 0)
    for it in items:
        if not isinstance(it, dict):
            continue
        # try common fields; prefer `name_with_balance` for accounts
        label = None
        label = it.get('name') or it.get('title') or it.get('label')
        if not label and isinstance(it.get('attributes'), dict):
            label = it['attributes'].get('name')
        if not label:
            # fallback to id or stringified object
            label = str(it.get('id') or it)
        # include some useful metadata for frontend display
        out.append({
            'id': it.get('id') or (it.get('attributes', {}) or {}).get('id'),
            'label': label,
            'name': it.get('name'),
            'name_with_balance': it.get('name_with_balance'),
            'raw': it,
        })
    return out
