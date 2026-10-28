"""On-demand Telegram webhook receiver. Run on a persistent HTTPS-capable host.

Reverse proxy must terminate TLS; expose only POST /telegram/webhook.
Set TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (or TELEGRAM_ALLOWED_CHAT_IDS),
TELEGRAM_WEBHOOK_SECRET (random string), and optionally PORT.
Register the URL using Telegram setWebhook with secret_token separately.
Do NOT run getUpdates polling while webhook is enabled.
Long research jobs currently execute synchronously: production deployment needs
a durable background queue before enabling expensive commands.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.telegram_queue import enqueue

MAX_BODY = 256 * 1024


def validate_request(path, headers, secret):
    if path != "/telegram/webhook":
        return 404
    if not secret or headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        return 403
    return 200


def process_payload(payload, *, queue_path):
    return 'queued' if enqueue(queue_path, payload) else 'duplicate'


def make_handler(secret, queue_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_error(404)

        def do_POST(self):
            code = validate_request(self.path, self.headers, secret)
            if code != 200:
                self.send_error(code)
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                self.send_error(400)
                return
            if length < 0 or length > MAX_BODY:
                self.send_error(413)
                return
            try:
                payload = json.loads(self.rfile.read(length))
                result = process_payload(payload, queue_path=queue_path)
            except (ValueError, UnicodeError):
                self.send_error(400)
                return
            except Exception as exc:
                # No tokens, URLs or update contents in logs.
                print("webhook processing failed:", type(exc).__name__, flush=True)
                self.send_error(503)
                return
            print("webhook outcome:", result, flush=True)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
    return Handler


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    ids = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS") or os.getenv("TELEGRAM_CHAT_ID", "")
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    queue_path = os.getenv("TELEGRAM_QUEUE_DB", "")
    if not secret or not queue_path:
        raise SystemExit("Missing TELEGRAM_WEBHOOK_SECRET or TELEGRAM_QUEUE_DB")
    if not (1 <= len(secret) <= 256) or any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for c in secret
    ):
        raise SystemExit("Invalid webhook secret format")
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        make_handler(secret, queue_path))
    print("Telegram webhook receiver listening", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
