# Files

- [Deployment, containers and scheduling](deployment-and-scheduling.md) - How Mail2Firefly is packaged and run — a two-stage Dockerfile that builds the Vue bundle and installs the Python app, a compose topology of MariaDB, Firefly III, the web service and an fcron scheduler sidecar, and the static crontab that triggers sync and database backups.
- [Tests, logging and diagnosing failed parses](testing-and-diagnostics.md) - How to verify a change and debug a bad import in Mail2Firefly — which unit tests exist and what they pin, the log-level environment variable and per-module loggers, the sync log versus transaction log, and the Failed Parse detail view that renders the stored parser input.
