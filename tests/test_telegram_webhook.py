import tempfile
import unittest
from pathlib import Path

from backend.telegram_webhook import validate_request, process_payload
from backend.telegram_queue import claim, enqueue, finish


class WebhookTests(unittest.TestCase):
    def test_auth_and_route(self):
        self.assertEqual(validate_request("/telegram/webhook", {"X-Telegram-Bot-Api-Secret-Token": "correct"}, "correct"), 200)
        self.assertEqual(validate_request("/telegram/webhook", {}, "correct"), 403)
        self.assertEqual(validate_request("/telegram/webhook", {"X-Telegram-Bot-Api-Secret-Token": "wrong"}, "correct"), 403)
        self.assertEqual(validate_request("/wrong", {}, "correct"), 404)
        self.assertEqual(validate_request("/telegram/webhook", {}, ""), 403)

    def test_durable_enqueue_and_dedupe(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inbox.sqlite3"
            update = {"update_id": 123, "message": {"text": "/start"}}
            self.assertEqual(process_payload(update, queue_path=path), "queued")
            self.assertEqual(process_payload(update, queue_path=path), "duplicate")
            self.assertEqual(claim(path), (123, update))
            finish(path, 123)
            self.assertIsNone(claim(path))

    def test_invalid_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                process_payload({"message": {}}, queue_path=Path(directory) / "db")
