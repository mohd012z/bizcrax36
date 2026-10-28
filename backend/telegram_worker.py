"""Dedicated Telegram worker. Requires the same durable DB volume as webhook."""
import os
import time
from pathlib import Path

from backend.telegram_bot import BASE, api
from backend.telegram_poll_once import load_ideas, process_update
from backend.telegram_queue import claim, finish, retry


def work_once(queue_path, token, allowed_ids, database, ideas, send=None):
    item = claim(queue_path)
    if item is None:
        return False
    update_id, update = item
    if send is None:
        send = lambda method, payload: api(token, method, payload)
    try:
        result = process_update(update, send=send, allowed_ids=allowed_ids,
                                database=database, ideas=ideas, token=token)
        finish(queue_path, update_id)
        print("telegram worker outcome:", result, flush=True)
    except Exception as exc:
        retry(queue_path, update_id, exc)
        print("telegram worker retry:", type(exc).__name__, flush=True)
    return True


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ids = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_ID", "")
    path = os.getenv("TELEGRAM_QUEUE_DB", "")
    if not token or not ids or not path:
        raise SystemExit("Missing token, chat ID, or TELEGRAM_QUEUE_DB")
    ideas = load_ideas()
    while True:
        if not work_once(path, token, ids, BASE / "data" / "research.sqlite3", ideas):
            time.sleep(0.5)


if __name__ == "__main__":
    main()
