# Files

- [Sync pipeline end to end](sync-pipeline.md) - Traces one sync run of Mail2Firefly from the HTTP trigger or cron sidecar through the lock and sync_runs bookkeeping, per-rule IMAP fetch, parser invocation, Firefly post, processed tagging and transaction logging — including the known gap where rule mappings never reach the payload builder.
