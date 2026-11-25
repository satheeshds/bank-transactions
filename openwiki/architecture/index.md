# Files

- [Configuration, credentials and runtime overrides](configuration-and-secrets.md) - Every configuration surface of Mail2Firefly — config.toml defaults, the MySQL settings table used for Firefly connection values and custom keys, mailbox credentials, database and log-level environment variables — plus which surfaces still fall back to static config and which do not.
- [System overview and runtime topology](system-overview.md) - The runnable surfaces of Mail2Firefly — a FastAPI dashboard that also serves the built Vue 3 SPA, and a background sync worker (in-process thread, CLI, or cron sidecar) that reads rules and mailboxes from MySQL, parses emails and posts transactions to Firefly III.
