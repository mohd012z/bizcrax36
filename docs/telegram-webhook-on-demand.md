# Telegram on-demand webhook (review-only)

This branch adds an authenticated HTTP receiver at `POST /telegram/webhook`. It reuses the existing BizCollector update router and existing chat-ID allowlist. It is **not deployed**.

## Configuration

On a persistent host, set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (or `TELEGRAM_ALLOWED_CHAT_IDS`), `TELEGRAM_WEBHOOK_SECRET` (random 1–256 ASCII letters, digits, underscore, hyphen), and `PORT` (default 8080). Run `python3 -m backend.telegram_webhook`. The host or reverse proxy must provide HTTPS and route `https://YOUR_HOST/telegram/webhook` to the app. Never commit credentials.

Once HTTPS is live, register the webhook with Telegram's official `setWebhook` method, specifying `url` and the same `secret_token`. Verify with `getWebhookInfo`. **Disable the scheduled GitHub Actions polling workflow first**, because `getUpdates` and webhooks cannot coexist.

## Validation

Run `python3 -m unittest tests.test_telegram_webhook -v`. Verify incorrect secret returns 403, wrong path returns 404, valid /start produces a reply, and unauthorized chat IDs produce no reply. Test actual delivery only after provisioning the host.

## Known limitations / deployment gate

The existing router performs research and DOCX generation synchronously. A slow job may exceed Telegram's webhook delivery timeout and trigger duplicate deliveries. **Do not deploy this receiver to production for /research or /newsplan until those commands enqueue jobs durably and return promptly.** Use a persistent database/queue with idempotency by update_id and job ID. This branch does not include a durable queue, TLS endpoint, hosting provisioning, webhook registration, or proof of a live response. Keep the current bot unchanged until these gates are met.
