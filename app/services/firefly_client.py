from __future__ import annotations

import json
from typing import Any
from urllib import error, request


def build_firefly_client(config: dict[str, Any] | None = None) -> "FireflyClient":
    if not config:
        raise ValueError("Firefly configuration is required")

    base_url = str(config.get("base_url", "")).strip()
    token = str(config.get("token", "")).strip()
    if not base_url or not token:
        raise ValueError("Firefly configuration must include base_url and token")

    timeout = int(config.get("timeout", 15))
    return FireflyClient(base_url=base_url, token=token, timeout=timeout)


class FireflyClientError(Exception):
    """Raised when a Firefly API request fails."""


class FireflyClient:
    def __init__(self, base_url: str, token: str, timeout: int = 15) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        body = None if payload is None else json.dumps(payload).encode("utf-8")

        req = request.Request(url, data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return {}
                return json.loads(raw)
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            raise FireflyClientError(f"Firefly API request failed: {exc.code} {details}") from exc
        except error.URLError as exc:
            raise FireflyClientError(f"Firefly API connection failed: {exc.reason}") from exc

    def create_transaction(self, transaction: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/transactions", payload=transaction)
