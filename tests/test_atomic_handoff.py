import tempfile
import unittest
from pathlib import Path
from backend.delivery_outbox import DeliveryOutbox
from backend.update_inbox import UpdateInbox


class AtomicHandoffTests(unittest.TestCase):
    def test_reply_and_completion_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            outbox, inbox = DeliveryOutbox(path), UpdateInbox(path)
            inbox.receive({"update_id": 31})
            item = inbox.claim(now=10, lease_seconds=60)
            self.assertTrue(inbox.complete_with_replies(item, [
                ("sendMessage", {"chat_id": 7, "text": "ready"})
            ], now=11))
            inbox.close()
            outbox.close()
            outbox, inbox = DeliveryOutbox(path), UpdateInbox(path)
            try:
                self.assertIsNone(inbox.claim(now=12))
                reply = outbox.claim(now=12)
                self.assertEqual(reply["payload"]["text"], "ready")
                self.assertTrue(outbox.finish(reply, True, now=12))
            finally:
                inbox.close()
                outbox.close()

    def test_stale_claim_cannot_queue_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            outbox, inbox = DeliveryOutbox(path), UpdateInbox(path)
            try:
                inbox.receive({"update_id": 32})
                stale = inbox.claim(now=10, lease_seconds=5)
                fresh = inbox.claim(now=16, lease_seconds=5)
                self.assertFalse(inbox.complete_with_replies(stale, [
                    ("sendMessage", {"chat_id": 1})
                ], now=16))
                self.assertIsNone(outbox.claim(now=16))
                self.assertTrue(inbox.complete_with_replies(fresh, [], now=16))
            finally:
                inbox.close()
                outbox.close()

    def test_invalid_reply_rolls_back_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            outbox, inbox = DeliveryOutbox(path), UpdateInbox(path)
            try:
                inbox.receive({"update_id": 33})
                item = inbox.claim(now=10, lease_seconds=5)
                with self.assertRaises(ValueError):
                    inbox.complete_with_replies(item, [("sendDocument", {})], now=11)
                retry = inbox.claim(now=16, lease_seconds=5)
                self.assertIsNotNone(retry)
                self.assertTrue(inbox.complete_with_replies(retry, [], now=16))
            finally:
                inbox.close()
                outbox.close()


if __name__ == "__main__":
    unittest.main()
