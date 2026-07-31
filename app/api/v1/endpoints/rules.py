from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel


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
    """Fetches parsing rules from the database. Returns an empty list if none exist."""
    try:
        # Try DB first
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, source_name, rule_name, regex, description, transaction_type, card_last4 FROM parsing_rules ORDER BY id")
            rows = cursor.fetchall()
            if rows:
                rules_list = [
                    {
                        "id": row["id"],
                        "source_name": row["source_name"],
                        "rule_name": row["rule_name"],
                        "regex": row["regex"],
                        "description": row["description"],
                        "transaction_type": row["transaction_type"],
                        "card_last4": row["card_last4"],
                    }
                    for row in rows
                ]
                return {"rules": rules_list}

            # No parsing rules found in DB; return empty list (do not fall back to config.toml)
            return {"rules": []}
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
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, source_name, rule_name, regex, description, transaction_type, card_last4, conditions_json, mappings_json, condition_mode FROM parsing_rules WHERE id = ?", (rule_id,))
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='Rule not found')
            return {
                'id': row['id'],
                'source_name': row['source_name'],
                'rule_name': row['rule_name'],
                'regex': row['regex'],
                'description': row['description'],
                'transaction_type': row['transaction_type'],
                'card_last4': row['card_last4'],
                'conditions': __import__('json').loads(row.get('conditions_json')) if row.get('conditions_json') else None,
                'mappings': __import__('json').loads(row.get('mappings_json')) if row.get('mappings_json') else None,
                'condition_mode': row.get('condition_mode')
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
