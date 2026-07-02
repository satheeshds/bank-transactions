from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import load_config, build_source_definitions

router = APIRouter(prefix="/api/v1", tags=["rules"])


@router.get("/rules")
def get_rules():
    """Fetches defined parsing rules and sources."""
    try:
        config = load_config()
        sources = build_source_definitions(config)
        
        rules_list = []
        for src in sources:
            patterns = src.get("transaction_patterns") or []
            if isinstance(patterns, dict):
                patterns = [patterns]
                
            for pat in patterns:
                rules_list.append({
                    "source_name": src.get("name") or "Unnamed Source",
                    "rule_name": pat.get("name") or "Unnamed Rule",
                    "regex": pat.get("regex") or pat.get("pattern"),
                    "transaction_type": pat.get("transaction_type") or "withdrawal",
                    "card_last4": pat.get("defaults", {}).get("card_last4")
                })
        return {"rules": rules_list}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to retrieve rules: {e}"}
        )
