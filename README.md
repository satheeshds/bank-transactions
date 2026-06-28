## Configuration

The script reads mailbox, query, and transaction-pattern settings from `config.toml` in the project root.

Use `config.example.toml` as the starting point:

```toml
[mailbox]
host = "imap.gmail.com"
username = "you@example.com"
password = "app-password"

[[queries]]
name = "sbi_statements"
from_ = "ELITE.card@sbicard.com"
subject = "Your SBI Card ELITE Monthly Statement"
gmail_label = "Statement"

[[transaction_patterns]]
name = "sbi_card"
regex = "(?P<currency>Rs\\.|₹)\\s*(?P<amount>[\\d,]+(?:\\.\\d+)?)\\s*spent on your\\s+SBI Credit Card\\s+ending with\\s+(?P<card_last4>\\d{4})\\s+at\\s+(?P<merchant>.+?)\\s+on\\s+(?P<date>\\d{1,2}-\\d{1,2}-\\d{2,4})\\s+via\\s+(?P<channel>.+?)\\s*\\(Ref No\\.\\s*(?P<reference_no>\\d+)\\)"
flags = ["IGNORECASE"]

[fetch]
reverse = true
limit = 15
```

You can now:
- define multiple mailbox queries using `[[queries]]`
- add multiple transaction parsers with `[[transaction_patterns]]`
- keep the old single-query format working via `query` as a fallback
- set a `processed_tag` to mark emails after a successful Firefly import so they are skipped on later runs

Run the script with:

```bash
uv run python main.py
```
