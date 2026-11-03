import tempfile
import unittest
from pathlib import Path
from backend.delivery_outbox import DeliveryOutbox


class DeliveryOutboxTests(unittest.TestCase):
    def test_deduplication_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.sqlite3"
            a = DeliveryOutbox(path)
            a.enqueue("update:1:reply", "sendMessage", {"chat_id": 5, "text": "hello"})
            a.enqueue("update:1:reply", "sendMessage", {"chat_id": 5, "text": "hello"})
            a.close()
            b = DeliveryOutbox(path)
            try:
                item = b.claim(now=10)
                self.assertEqual(item["attempt"], 1)
                self.assertEqual(item["payload"]["text"], "hello")
                self.assertIsNone(b.claim(now=10))
                self.assertTrue(b.finish(item, True, now=10))
                self.assertIsNone(b.claim(now=100))
            finally:
                b.close()

    def test_lease_expiry_and_fencing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.sqlite3"
            first, second = DeliveryOutbox(path), DeliveryOutbox(path)
            try:
                first.enqueue("k", "sendMessage", {"chat_id": 7, "text": "x"})
                old = first.claim(now=10, lease_seconds=5)
                self.assertIsNone(second.claim(now=14))
                new = second.claim(now=16, lease_seconds=5)
                self.assertNotEqual(old["owner"], new["owner"])
                self.assertFalse(first.finish(old, True, now=16))
                self.assertTrue(second.finish(new, True, now=16))
                self.assertIsNone(first.claim(now=100))
            finally:
                first.close()
                second.close()

    def test_uncertain_receipt_persists_across_restart_without_resend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "outbox.sqlite3"
            first = DeliveryOutbox(path)
            first.enqueue("ambiguous", "sendMessage", {"chat_id": 7})
            item = first.claim(now=10)
            self.assertTrue(first.finish(item, None, now=10))
            first.close()
            second = DeliveryOutbox(path)
            try:
                self.assertEqual(second.db.execute(
                    "SELECT state FROM deliveries WHERE delivery_key='ambiguous'"
                ).fetchone()[0], "uncertain")
                self.assertIsNone(second.claim(now=10000))
            finally:
                second.close()

    def test_retry_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = DeliveryOutbox(Path(directory) / "outbox.sqlite3")
            try:
                outbox.enqueue("k", "sendMessage", {"chat_id": 1})
                first = outbox.claim(now=10, max_attempts=2)
                self.assertTrue(outbox.finish(first, False, now=10))
                self.assertIsNone(outbox.claim(now=11, max_attempts=2))
                second = outbox.claim(now=12, max_attempts=2)
                self.assertEqual(second["attempt"], 2)
                self.assertTrue(outbox.finish(second, False, now=12))
                self.assertIsNone(outbox.claim(now=1000, max_attempts=2))
            finally:
                outbox.close()


if __name__ == "__main__":
    unittest.main()
