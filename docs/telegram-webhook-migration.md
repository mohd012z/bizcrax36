# Telegram webhook migration (not deployed)

The GitHub Actions polling job cannot provide continuous replies. This Cloudflare Worker handles Telegram webhooks quickly with no paid AI dependency.

## Setup
1. Create a Cloudflare Worker using `worker/telegram.js`.
2. Configure **Worker secrets** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (random URL-safe secret), and `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated numeric chat IDs). Never commit these.
3. Deploy the Worker and confirm its HTTPS URL.
4. Configure Telegram using `setWebhook` with URL `https://<worker-host>/telegram`, `secret_token` matching `TELEGRAM_WEBHOOK_SECRET`, and `allowed_updates=["message","callback_query"]`. Perform this via a secure administrative environment; do not put the token in URLs in public logs.
5. Disable the `telegram-interactive.yml` scheduled poller before enabling the webhook. Telegram getUpdates and webhook are mutually exclusive.
6. Verify `/start`, `/status`, `/sector` and callback buttons. `/research` currently only acknowledges receipt: a durable queue/dispatcher is still needed for actual on-demand research.

## Release gates
- Worker deployed with configured secrets and Telegram webhook registration confirmed
- Unauthorized webhook requests return 403
- Authorized /status returns a Telegram message within seconds
- Callback delivery tested, no duplicate consumer
- Durable research dispatch and result delivery tested before advertising autonomous /research

The repository cannot deploy the Worker or set Telegram's webhook without Cloudflare access and secrets. Do not claim the bot is live until these gates pass.
