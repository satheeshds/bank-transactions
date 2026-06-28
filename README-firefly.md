# Firefly client

The repository now includes a small client for posting transactions to Firefly III over the REST API using a bearer token.

## Usage

```python
from firefly_client import FireflyClient

client = FireflyClient(
    base_url="http://localhost:8080",
    token="your-bearer-token",
)

payload = {
    "type": "withdrawal",
    "date": "2026-06-26",
    "description": "Coffee shop",
    "amount": "12.50",
    "currency_code": "USD",
    "source_name": "Cash",
    "destination_name": "Food",
}

response = client.create_transaction(payload)
print(response)
```

## Notes

- The client sends `Authorization: Bearer <token>`.
- The Firefly API shape can vary by version, so adjust the payload fields to match your installation.
