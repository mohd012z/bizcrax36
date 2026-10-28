# Telegram webhook + durable worker (draft, not deployed)

The webhook receiver and worker are separate processes sharing a persistent SQLite inbox.

## Requirements

- HTTPS reverse proxy forwarding POST /telegram/webhook to `python3 -m backend.telegram_webhook`.
- `TELEGRAM_WEBHOOK_SECRET`: strong random URL-safe secret (A-Z, a-z, 0-9, underscore, hyphen).
- `TELEGRAM_QUEUE_DB`: **same persistent mounted absolute file path** in both receiver and worker (e.g. /data/telegram-inbox.sqlite3). Never use ephemeral container filesystem.
- Worker environment: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (or `TELEGRAM_ALLOWED_CHAT_IDS`), `TELEGRAM_QUEUE_DB`.
- Start worker separately: `python3 -m backend.telegram_worker`.

The webhook writes each Telegram update durably and returns HTTP 200. Duplicate update IDs are ignored. Worker handles messages via the existing router, including /start and /research.

## Migration

1. Provision HTTPS host and durable shared volume, receiver and worker processes.
2. Test `python3 -m unittest tests.test_telegram_webhook -v` and existing regression tests.
3. Disable the scheduled `telegram-interactive.yml` polling workflow. Webhook and getUpdates cannot run simultaneously.
4. Register the HTTPS URL with Telegram `setWebhook` and `secret_token`; verify with `getWebhookInfo`.
5. Send /start and a button tap; inspect worker outcome, then test /research and DOCX.
6. Keep rollback procedure to deleteWebhook and re-enable polling if needed.

## Limitations and gates

- Delivery is **at least once**, not exactly once: a crash after send but before marking done may cause a duplicate reply. Telegram update ID deduplication prevents duplicate enqueues but not all duplicate sends.
- Worker processes one update at a time. Long research can delay subsequent messages; separate quick-command and research workers/queues are recommended before production.
- Retry uses a lease and capped attempts; failed items remain in SQLite for inspection. Monitor failed count and volume usage.
- Only one worker should consume the queue until long-running job semantics are validated.
- A publicly reachable HTTPS endpoint, host deployment, secrets, real Telegram webhook registration, and end-to-end tests are **not yet completed**.
- Do not merge or deploy until those gates are verified. No GitHub billing changes required by this branch.
