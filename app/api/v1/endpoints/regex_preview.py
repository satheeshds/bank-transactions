from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["regex"])


class RegexPreviewIn(BaseModel):
    regex: str
    sample_text: str


def _run_preview(payload: Dict[str, Any]):
    pattern = payload.get("regex", "") or ""
    text = payload.get("sample_text", "") or ""
    # Convert Python-style named groups (?P<name>) to JS/Python named-group syntax is fine here
    try:
        compiled = re.compile(pattern, re.MULTILINE)
    except Exception as e:
        return {"error": f"compile_error: {e}"}

    m = compiled.search(text)
    if not m:
        return {"groups": [], "named": {}, "groupindex": {}}

    groups = [m.group(i) for i in range(0, len(m.groups()) + 1)]
    named = m.groupdict()
    # groupindex maps group name -> index
    groupindex = getattr(compiled, 'groupindex', {})
    return {"groups": groups, "named": named, "groupindex": groupindex}


@router.post("/regex_preview")
def regex_preview(payload: RegexPreviewIn):
    """Run a regex preview using Python's `re` safely with a short timeout."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_run_preview, payload.dict())
    try:
        result = future.result(timeout=0.5)
    except TimeoutError:
        result = {"error": "timeout"}
    finally:
        executor.shutdown(wait=False)
    return result
