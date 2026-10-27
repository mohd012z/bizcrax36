# Automatic Telegram replies (Cloudflare Worker, free-tier compatible)

The Worker at `worker/telegram-webhook.mjs` receives Telegram updates automatically. GitHub Actions remains responsible for tests and scheduled business research. **No manual workflow run is needed after webhook activation.**

## One-time setup
1. Create a free Cloudflare account and Worker named `bizcrax36-telegram`. Deploy the Worker source in `worker/telegram-webhook.mjs` using the Cloudflare dashboard or Wrangler.
2. Add **encrypted Worker secrets** `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (generate a long random value using only A-Z, a-z, 0-9, underscore or hyphen), and `TELEGRAM_ALLOWED_CHAT_IDS` (comma-separated numeric IDs). Never commit values.
3. Optional: bind a KV namespace named `UPDATES` for best-effort duplicate suppression. KV is not an atomic exactly-once queue.
4. Check `https://YOUR-WORKER.workers.dev/health` returns status ok.
5. Register the webhook with Telegram **once**, from a secure terminal. Do not put tokens in public logs:
   ```bash
   read -rsp "Bot token: " BOT_TOKEN; echo
   read -rsp "Webhook secret: " HOOK_SECRET; echo
   read -rp "Worker URL (https://...workers.dev): " WORKER_URL
   curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
     --data-urlencode "url=${WORKER_URL}/telegram" \
     --data-urlencode "secret_token=${HOOK_SECRET}" \
     --data-urlencode 'allowed_updates=["message","callback_query"]'
   unset BOT_TOKEN HOOK_SECRET
   ```
6. Send `/status`, `/start`, and `/research aviation training Malaysia` to the bot. Inspect Worker logs if replies do not arrive.

## Operational safety
- The existing GitHub poller checks `getWebhookInfo`. Once webhook is active it exits without polling, so it cannot consume updates concurrently.
- Telegram webhook deliveries are acknowledged quickly; Worker background delivery is **best effort**. For guaranteed retries and deep research, add a durable queue (Cloudflare Queues/D1) and explicit completion tracking.
- `/research` searches public news headlines. It is not a fully autonomous LLM agent, nor does it verify business profitability.
- Cloudflare free-tier limits and quotas apply. Do not assume unbounded traffic.
- Only `/health` is public; Telegram events require the secret header and authorized chat ID.
- Avoid setting `drop_pending_updates=true` unless deliberately discarding queued user messages.
