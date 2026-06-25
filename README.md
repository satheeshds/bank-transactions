## Configuration

The script reads mailbox and query settings from `config.toml` in the project root.

Use `config.example.toml` as the starting point:

```toml
[mailbox]
host = "imap.gmail.com"
username = "you@example.com"
password = "app-password"

[query]
from_ = "ELITE.card@sbicard.com"
subject = "Your SBI Card ELITE Monthly Statement"
gmail_label = "Statement"

[fetch]
reverse = true
limit = 15
```

Run the script with:

```bash
uv run python main.py
```
