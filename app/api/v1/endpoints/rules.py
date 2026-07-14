from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import load_config, build_source_definitions
from app.db.session import get_db_connection

router = APIRouter(prefix="/api/v1", tags=["rules"])


class RuleIn(BaseModel):
    source_name: str
    rule_name: str
    description: str | None = None
    regex: str
    transaction_type: str = "withdrawal"
    card_last4: str | None = None
    conditions: list | None = None
    condition_mode: str | None = None
    mappings: list | None = None


@router.get("/rules")
def get_rules():
    """Fetches parsing rules from DB; fall back to config.toml if none exist."""
    try:
        # Try DB first
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, source_name, rule_name, regex, description, transaction_type, card_last4 FROM parsing_rules ORDER BY id")
        rows = cursor.fetchall()
        if rows:
            rules_list = [
                {
                    "id": row[0],
                    "source_name": row[1],
                    "rule_name": row[2],
                    "regex": row[3],
                    "description": row[4],
                    "transaction_type": row[5],
                    "card_last4": row[6],
                }
                for row in rows
            ]
            return {"rules": rules_list}

        # Fallback to config.toml
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


@router.post("/rules")
def add_rule(rule: RuleIn):
    """Add a new parsing rule and persist it to the DB."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO parsing_rules (source_name, rule_name, regex, description, transaction_type, card_last4, conditions_json, mappings_json, condition_mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rule.source_name,
                rule.rule_name,
                rule.regex,
                rule.description,
                rule.transaction_type,
                rule.card_last4,
                None if rule.conditions is None else __import__('json').dumps(rule.conditions),
                None if rule.mappings is None else __import__('json').dumps(rule.mappings),
                rule.condition_mode,
            ),
        )
        conn.commit()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add rule: {e}")


@router.get('/rules/{rule_id}')
def get_rule(rule_id: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, source_name, rule_name, regex, description, transaction_type, card_last4, conditions_json, mappings_json, condition_mode FROM parsing_rules WHERE id = ?", (rule_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Rule not found')
        return {
            'id': row[0],
            'source_name': row[1],
            'rule_name': row[2],
            'regex': row[3],
            'description': row[4],
            'transaction_type': row[5],
            'card_last4': row[6],
            'conditions': __import__('json').loads(row[7]) if row[7] else None,
            'mappings': __import__('json').loads(row[8]) if row[8] else None,
            'condition_mode': row[9]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch rule: {e}")


@router.put('/rules/{rule_id}')
def update_rule(rule_id: int, rule: RuleIn):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE parsing_rules SET source_name = ?, rule_name = ?, regex = ?, description = ?, transaction_type = ?, card_last4 = ?, conditions_json = ?, mappings_json = ?, condition_mode = ? WHERE id = ?",
            (
                rule.source_name,
                rule.rule_name,
                rule.regex,
                rule.description,
                rule.transaction_type,
                rule.card_last4,
                None if rule.conditions is None else __import__('json').dumps(rule.conditions),
                None if rule.mappings is None else __import__('json').dumps(rule.mappings),
                rule.condition_mode,
                rule_id,
            ),
        )
        conn.commit()
        return {"updated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update rule: {e}")


@router.delete('/rules/{rule_id}')
def delete_rule(rule_id: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM parsing_rules WHERE id = ?", (rule_id,))
        conn.commit()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete rule: {e}")
