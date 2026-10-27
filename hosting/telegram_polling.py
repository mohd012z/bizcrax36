"""Long-poll Telegram commands; research runs in GitHub Actions."""
import json
import logging
import signal
import sqlite3
import os
import time
import urllib.error
import urllib.request

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED = {x.strip() for x in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if x.strip()}
GITHUB_TOKEN = os.getenv("GITHUB_DISPATCH_TOKEN", "")
REPOSITORY = os.getenv("GITHUB_REPOSITORY_NAME", "mohd012z/bizcrax36")
STATE_DB = os.getenv("TELEGRAM_STATE_DB", "/data/bizcrax36-telegram.sqlite3")
TIMEOUT = 30
STOP = False


def stop_requested(signum, frame):
    global STOP
    STOP = True

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def request_json(url, payload=None, timeout=40, headers=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        return json.loads(data) if data else {}


def telegram(method, payload):
    result = request_json(f"https://api.telegram.org/bot{TOKEN}/{method}", payload)
    if not result.get("ok"):
        raise RuntimeError(f"Telegram {method} failed")
    return result.get("result")


def send(chat, message):
    telegram("sendMessage", {"chat_id": chat, "text": message[:3900]})


def dispatch(query, chat, request_id):
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_DISPATCH_TOKEN is missing")
    url = f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/agentic-research.yml/dispatches"
    req = urllib.request.Request(url, data=json.dumps({"ref": "main", "inputs": {"query": query, "chat_id": str(chat), "request_id": request_id}}).encode(), headers={"Authorization": "Bearer " + GITHUB_TOKEN, "Accept": "application/vnd.github+json", "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 204:
            raise RuntimeError("GitHub dispatch returned unexpected HTTP status")


def remember_update(update_id):
    import pathlib
    pathlib.Path(STATE_DB).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(STATE_DB, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS handled_updates (update_id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        result = db.execute('INSERT OR IGNORE INTO handled_updates (update_id) VALUES (?)', (update_id,))
        db.commit()
        return result.rowcount == 1


def process(update):
    message = update.get("message") or {}
    chat = (message.get("chat") or {}).get("id")
    if chat is None or str(chat) not in ALLOWED:
        return
    text = (message.get("text") or "").strip()
    command = text.split(maxsplit=1)[0].split("@")[0].lower() if text else ""
    if command in ("/start", "/help"):
        send(chat, "BizCrax36 online. Commands: /status, /sector, /research <topic>.")
    elif command == "/status":
        send(chat, "BizCrax36 polling bot online. Research runs through GitHub Actions.")
    elif command == "/sector":
        send(chat, "Sectors: Digital, Energy, Aerospace, Manufacturing, Tourism, Agriculture. Use /research <sector and topic>.")
    elif command == "/research":
        query = text.partition(" ")[2].strip()
        if not query:
            send(chat, "Usage: /research aviation training Malaysia")
            return
        if len(query) > 400:
            send(chat, "Please shorten the research topic to 400 characters.")
            return
        request_id = "tg-" + str(update["update_id"])
        try:
            if not remember_update(update["update_id"]):
                return
            dispatch(query, chat, request_id)
        except Exception:
            logging.exception("Research dispatch failed for %s", request_id)
            send(chat, "Research could not be queued. Please try again.")
        else:
            send(chat, f"Research queued: {request_id}. Results will be delivered here.")
    elif command:
        send(chat, "Unknown command. Use /help.")


def main():
    if not TOKEN or not ALLOWED:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_CHAT_IDS before starting")
    # Polling and webhook delivery are mutually exclusive.
    telegram("deleteWebhook", {"drop_pending_updates": False})
    offset = None
    delay = 1
    signal.signal(signal.SIGTERM, stop_requested)
    signal.signal(signal.SIGINT, stop_requested)
    while not STOP:
        try:
            params = {"timeout": TIMEOUT, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            updates = telegram("getUpdates", params) or []
            for update in updates:
                if STOP:
                    break
                offset = update["update_id"] + 1
                try:
                    process(update)
                except Exception:
                    logging.exception("Update processing failed")
            delay = 1
        except (urllib.error.URLError, TimeoutError, RuntimeError):
            logging.exception("Telegram polling failed")
            time.sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == "__main__":
    main()
