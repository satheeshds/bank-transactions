from __future__ import annotations

from pydantic import BaseModel
from typing import Any, Optional


class StatusResponse(BaseModel):
    is_running: bool
    current_run_id: int | None
    imap: dict[str, Any]
    firefly: dict[str, Any]
    stats: dict[str, Any]
    latest_run: dict[str, Any] | None


class SyncResponse(BaseModel):
    message: str
    run_id: int | None = None


class LogEntry(BaseModel):
    id: int
    run_id: int | None
    timestamp: str
    level: str
    message: str


class LogsResponse(BaseModel):
    logs: list[dict[str, Any]]


class Transaction(BaseModel):
    id: int
    timestamp: str
    transaction_date: str | None
    merchant: str | None
    amount: float | None
    currency: str | None
    status: str
    error_message: str | None = None
    source_name: str | None = None
    email_subject: str | None = None
    reference_no: str | None = None


class TransactionsResponse(BaseModel):
    transactions: list[dict[str, Any]]


class Rule(BaseModel):
    source_name: str
    rule_name: str
    regex: str
    transaction_type: str
    card_last4: str | None = None


class RulesResponse(BaseModel):
    rules: list[dict[str, Any]]
