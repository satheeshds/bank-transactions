from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SourceDefinition:
    name: str | None
    mailbox: dict[str, Any]
    query: list[dict[str, Any]]
    transaction_patterns: list[dict[str, Any]] | dict[str, Any] | None
    firefly: dict[str, Any]
    processed_tag: str | None


@dataclass(slots=True)
class TransactionDetails:
    amount: float
    currency: str
    merchant: str
    description: str
    card_last4: str | None
    transaction_date: str
    reference_no: str | None
    channel: str
    firefly: dict[str, Any]
    vpa: str | None = None
    transaction_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "amount": self.amount,
            "currency": self.currency,
            "merchant": self.merchant,
            "description": self.description,
            "card_last4": self.card_last4,
            "transaction_date": self.transaction_date,
            "reference_no": self.reference_no,
            "channel": self.channel,
            "firefly": self.firefly,
        }
        if self.vpa:
            payload["vpa"] = self.vpa
        if self.transaction_type:
            payload["transaction_type"] = self.transaction_type
        return payload
