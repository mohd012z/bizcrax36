# Railway deployment — BizCrax36 Telegram polling
# Deploy as a worker process, not a sleeping web service.
# Start command: python3 hosting/telegram_polling.py
#
# Required environment variables (set in Railway UI, never commit values):
# TELEGRAM_BOT_TOKEN — Telegram bot token
# TELEGRAM_ALLOWED_CHAT_IDS — comma-separated permitted chat IDs
# GITHUB_DISPATCH_TOKEN — fine-grained token with Actions:write for this repo
# GITHUB_REPOSITORY_NAME — mohd012z/bizcrax36
#
# Required GitHub Actions secret:
# TELEGRAM_BOT_TOKEN — delivers completed research.
#
# Only one Telegram getUpdates consumer may run for the same bot token.
# Disable the legacy scheduled polling workflow before starting Railway.
# This worker calls deleteWebhook at startup; do not run alongside Cloudflare webhook.
# Research workflow must exist on the main branch for workflow_dispatch.
# Keep the Cloudflare draft PR unmerged.
# Note: Railway service costs/credits and availability depend on current plan.
