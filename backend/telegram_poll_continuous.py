"""Continuous local Telegram poller for the BizCrax36 bot (dev/backup host).

The GitHub Actions scheduler only runs every 5 minutes, so button presses
queue up to ~20-30s (runner spin-up) before the bot answers — it feels frozen.
This process polls continuously on the always-on host, so responses are
sub-second. The CI poller stays as a fallback; getUpdates makes them mutually
exclusive in practice (whoever acks an update wins), and concurrency is kept
low by the Telegram queue itself.

Env (all required unless a default exists):
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (or TELEGRAM_ALLOWED_CHAT_IDS),
  MINDA_BASE_URL, MINDA_API_KEY, MINDA_MODEL (optional — AI layer fail-open),
  POLL_SECONDS (default 1), MAX_UPDATES (default 50).
"""
import os
import sys
import time

from backend.telegram_poll_once import load_ideas, poll_once


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    allowed = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not allowed:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID")
    poll_seconds = float(os.environ.get("POLL_SECONDS", "1"))
    max_updates = int(os.environ.get("MAX_UPDATES", "50"))
    from backend.telegram_bot import BASE
    ideas = load_ideas()
    print("bizcrax36 continuous poller: start (poll every %.1fs, max %d)"
          % (poll_seconds, max_updates), flush=True)
    while True:
        try:
            poll_once(token, allowed, BASE / "data" / "research.sqlite3", ideas,
                      max_updates=max_updates, repository="", job_token="")
        except Exception as exc:  # network blip, expired webhook, 409, etc.
            print("poll cycle error (continuing):", type(exc).__name__,
                  str(exc)[:200], flush=True)
            time.sleep(max(2.0, min(poll_seconds * 5, 15.0)))
        else:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
