from __future__ import annotations

from fastapi import APIRouter, HTTPException
import logging
from pydantic import BaseModel

from app.db.session import get_db_connection

router = APIRouter(prefix="/api/v1", tags=["ai"])
logger = logging.getLogger(__name__)


class AIGenIn(BaseModel):
    sample_text: str


def get_setting(key: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    return row[0] if row else None


@router.post('/ai/regex')
def generate_regex(req: AIGenIn):
    """Generate a regex suggestion for the provided sample text using Gemini via google.genai.
    Requires a stored API key in settings under 'gemini_api_key'.
    """
    logger.info('AI regex request received')
    logger.debug('sample_text: %s', (req.sample_text or '')[:1000])
    api_key = get_setting('gemini_api_key')
    if not api_key:
        logger.warning('Gemini API key not configured')
        raise HTTPException(status_code=400, detail='Gemini API key not configured')

    # few-shot prompt asking for a single regex with named capture groups
    prompt = r"""
You are a helpful assistant that returns exactly one single-line regular expression (no explanation, no surrounding quotes) that captures all relevant transaction fields from a bank/UPI alert email.
The regex MUST use Python-style named capture groups with these canonical names when present: `currency`, `amount`, `account_ending`, `vpa`, `merchant`, `date`, `reference`.
Only include groups that make sense for the input, but prefer to include all if possible. Return only the regex string. Examples:

Sample: 'Rs.160.00 is debited from your account ending 8367 towards VPA kavithasanal1985@oksbi (KAVITHA B) on 09-07-26.'
Regex: (?P<currency>Rs\.?|INR)?\s*(?P<amount>[0-9,]+\.?[0-9]{0,2}).*?account ending\s*(?P<account_ending>\d{2,4}).*?VPA\s*(?P<vpa>[\w@._+-]+).*?\((?P<merchant>[^)]+)\).*?(?P<date>\d{2}-\d{2}-\d{2})

Sample: 'UPI transaction reference no.: 310031548786. Rs.160.00 is debited from your account ending 8367 on 09-07-26.'
Regex: (?P<reference>\d{6,})[\s\S]*?(?P<currency>Rs\.?|INR)?\s*(?P<amount>[0-9,]+\.?[0-9]{0,2}).*?account ending\s*(?P<account_ending>\d{2,4}).*?(?P<date>\d{2}-\d{2}-\d{2})
"""
    prompt += "\nInput: " + req.sample_text + "\nRegex:"

    # Use google.genai client if available
    try:
        from google import genai
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'genai client not installed: {e}')

    client = genai.Client(api_key=api_key)
    # try to import a specific RateLimitError type from genai if available
    RateLimitError = None
    try:
        from google.genai._gaos.lib.compat_errors import RateLimitError as _RLE
        RateLimitError = _RLE
    except Exception:
        try:
            # fallback path/name variations
            from google.genai._gaos import lib as _lib
            RateLimitError = getattr(_lib, 'RateLimitError', None)
        except Exception:
            RateLimitError = None
    # Preferred model fallback order (try lighter / cheaper models first when hitting quota limits)
    models_to_try = [
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3-flash",
        "gemini-2.5-flash",
    ]

    last_exc = None
    for model in models_to_try:
        try:
            logger.info('Calling AI model: %s', model)
            interaction = client.interactions.create(model=model, input=prompt)
            text = getattr(interaction, 'output_text', None) or (interaction.output[0].content[0].text if getattr(interaction, 'output', None) else None)
            if not text:
                logger.error('AI returned empty response for model %s, input: %s', model, (req.sample_text or '')[:1000])
                continue
            return {'regex': text.strip()}
        except Exception as e:
            # inspect exception to decide whether to retry with another model
            msg = str(e)
            logger.warning('AI model %s failed: %s', model, msg)
            # prefer class-based detection if available
            is_rate = False
            try:
                if RateLimitError and isinstance(e, RateLimitError):
                    is_rate = True
            except Exception:
                is_rate = False
            # fallback to string-based detection
            if not is_rate:
                if ('quota' in msg.lower()) or ('rate limit' in msg.lower()) or ('too_many_requests' in msg.lower()) or ('quota exceeded' in msg.lower()):
                    is_rate = True

            if is_rate:
                last_exc = e
                # try next model
                continue
            else:
                logger.exception('AI call failed with non-retryable error')
                raise HTTPException(status_code=500, detail=f'Failed to call AI service: {e}')

    # if we exhausted models
    if last_exc:
        logger.exception('All AI models failed due to rate/quota limits')
        raise HTTPException(status_code=502, detail=f'AI quota/rate limits exceeded: {last_exc}')
    else:
        logger.exception('AI call failed for unknown reasons')
        raise HTTPException(status_code=500, detail='Failed to call AI service')
