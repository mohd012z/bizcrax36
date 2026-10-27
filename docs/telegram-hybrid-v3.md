# BizCrax36 V3: webhook + Cloudflare Queue + GitHub research

## Architecture
Telegram -> Cloudflare webhook Worker -> Cloudflare Queue -> Queue dispatch Worker -> GitHub Actions research -> Telegram sendMessage.

This branch is **not deployed**. No production secrets are present. PR must stay draft until deployment, security and integration gates pass.

## Cloudflare provisioning
Create a Queue named `bizcrax36-research`. Deploy `worker/telegram.js` as an HTTP Worker and bind the Queue producer as `RESEARCH_QUEUE`. Deploy `worker/research-dispatch.js` as a Queue consumer of that same queue.

Webhook Worker secrets:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET` (random URL-safe token)
- `TELEGRAM_ALLOWED_CHAT_IDS` (numeric IDs, comma separated)

Queue consumer secret:
- `GITHUB_DISPATCH_TOKEN`: fine-grained GitHub token restricted to `mohd012z/bizcrax36`, Actions: write. Do not expose in webhook Worker.

GitHub Actions secret:
- `TELEGRAM_BOT_TOKEN` already required for delivery.

## Cutover
1. Verify Workers deployed, Queue bound, consumer active, and all secrets set.
2. Configure Telegram setWebhook to HTTPS Worker /telegram with matching secret_token and allowed_updates message,callback_query.
3. Disable scheduled GitHub `telegram-interactive.yml` polling only after webhook readiness confirmed. Do not run getUpdates when webhook active.
4. Send /status then /research aviation training Malaysia. Confirm immediate queue acknowledgment, GitHub research workflow start and result delivery.
5. Confirm malformed payload 400, missing secret 403, unauthorized chat ignored, Queue failure does not claim success, and GitHub dispatch retries.
6. Test duplicate Telegram update IDs and GitHub dispatch failure recovery before production.

## Known limitations
- Queue delivery is at least once, and GitHub workflow dispatch lacks a native idempotency key. Duplicate research runs are possible. Add D1 unique update_id and job-state table before production.
- The research agent discovers news leads, not primary-source-verified business opportunities. Every lead is marked REVIEW_REQUIRED.
- No durable history UI or result pagination is implemented in this branch.
- Telegram /status reports webhook availability, not end-to-end research health.
- Queued jobs may take time for GitHub Actions to start; fast webhook acknowledgment does not mean instant research completion.
- Free Cloudflare Queues retention is 24 hours; long outages require a longer-lived ledger.
- The Worker must be deployed by an authorized Cloudflare account. No paid services are needed for normal free-tier usage, subject to plan limits.

See Cloudflare Queues docs: https://developers.cloudflare.com/queues/
