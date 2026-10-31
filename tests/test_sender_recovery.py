import tempfile
import unittest
from pathlib import Path
from backend.delivery_outbox import DeliveryOutbox
from backend.telegram_live_free import deliver_pending


class SenderRecoveryTests(unittest.TestCase):
    def test_transport_failure_retries_and_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = DeliveryOutbox(Path(directory) / "outbox.sqlite3")
            try:
                outbox.enqueue("1:1", "sendMessage", {"chat_id": 1, "text": "test"})
                calls = []
                def transport(token, method, payload):
                    calls.append(method)
                    if len(calls) == 1:
                        raise ConnectionError("temporary failure")
                    return {"ok": True}
                self.assertEqual(deliver_pending(outbox, "test", transport, now=10), 0)
                self.assertEqual(deliver_pending(outbox, "test", transport, now=11), 0)
                self.assertEqual(deliver_pending(outbox, "test", transport, now=12), 1)
                self.assertEqual(deliver_pending(outbox, "test", transport, now=100), 0)
                self.assertEqual(len(calls), 2)
            finally:
                outbox.close()

    def test_negative_api_result_is_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = DeliveryOutbox(Path(directory) / "outbox.sqlite3")
            try:
                outbox.enqueue("2:1", "answerCallbackQuery", {"callback_query_id": "x"})
                self.assertEqual(deliver_pending(outbox, "test",
                    lambda *args: {"ok": False}, now=10), 0)
                self.assertEqual(deliver_pending(outbox, "test",
                    lambda *args: {"ok": True}, now=12), 1)
            finally:
                outbox.close()


if __name__ == "__main__":
    unittest.main()
