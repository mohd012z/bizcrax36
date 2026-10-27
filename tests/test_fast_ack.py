"""Regression tests for the fast button-ack behavior (fix for the 'freezing' report)."""
import unittest
from pathlib import Path
from urllib.error import HTTPError

import backend.telegram_poll_once as tp


class FastAckTests(unittest.TestCase):
    def _send(self, calls):
        def send(method, payload):
            calls.append((method, payload))
            if method == "answerCallbackQuery" and self.raise_expired:
                raise HTTPError("https://example.org", 400, "expired", {}, None)
        return send

    def test_callback_answered_before_any_other_call(self):
        self.raise_expired = False
        calls = []
        out = tp.process_update(
            {"callback_query": {"id": "c1", "data": "bc:home",
                                "message": {"chat": {"id": 1}, "message_id": 5}}},
            send=self._send(calls), allowed_ids="1", database=Path("missing.db"), ideas=[])
        self.assertEqual(out, "sent")
        self.assertEqual(calls[0][0], "answerCallbackQuery")
        self.assertEqual(calls[0][1].get("text"), "⏳ Working…")
        # exactly one answer per callback
        self.assertEqual([m for m, _ in calls if m == "answerCallbackQuery"], ["answerCallbackQuery"])

    def test_expired_fast_ack_does_not_block_message(self):
        self.raise_expired = True
        calls = []
        out = tp.process_update(
            {"callback_query": {"id": "c1", "data": "bc:home",
                                "message": {"chat": {"id": 1}, "message_id": 5}}},
            send=self._send(calls), allowed_ids="1", database=Path("missing.db"), ideas=[])
        self.assertEqual(out, "sent")
        self.assertEqual(calls[1][0], "editMessageText")

    def test_ai_shortcut_button_ack_first_then_research(self):
        # bc:ai:hot must ack the button before the AI parse starts.
        self.raise_expired = False
        calls = []
        original_ask = tp.ai_bizcollector.ask_intent
        original_rr = tp.run_research
        tp.ai_bizcollector.ask_intent = lambda text, **k: None
        tp.run_research = lambda *a, **k: calls.append(("run_research", a[3]))
        try:
            tp.process_update(
                {"callback_query": {"id": "c1", "data": "bc:ai:hot",
                                    "message": {"chat": {"id": 1}}}},
                send=self._send(calls), allowed_ids="1", database=None, ideas=[], token="tok")
        finally:
            tp.ai_bizcollector.ask_intent = original_ask
            tp.run_research = original_rr
        methods = [m for m, _ in calls]
        self.assertEqual(methods[0], "answerCallbackQuery")
        self.assertIn("run_research", methods)


if __name__ == "__main__":
    unittest.main()
