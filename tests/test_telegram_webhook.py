import unittest
from backend.telegram_webhook import validate_request, process_payload

class WebhookTests(unittest.TestCase):
    def test_auth_and_route(self):
        self.assertEqual(validate_request("/telegram/webhook", {"X-Telegram-Bot-Api-Secret-Token": "correct"}, "correct"), 200)
        self.assertEqual(validate_request("/telegram/webhook", {}, "correct"), 403)
        self.assertEqual(validate_request("/telegram/webhook", {"X-Telegram-Bot-Api-Secret-Token": "wrong"}, "correct"), 403)
        self.assertEqual(validate_request("/wrong", {}, "correct"), 404)
        self.assertEqual(validate_request("/telegram/webhook", {}, ""), 403)

    def test_invalid_payload(self):
        with self.assertRaises(ValueError):
            process_payload({"message": {}}, token="x", allowed_ids="1",
                            send=lambda *a: None, database=None, ideas=[])
