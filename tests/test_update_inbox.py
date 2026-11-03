import tempfile
import unittest
from pathlib import Path
from backend.update_inbox import UpdateInbox


class UpdateInboxTests(unittest.TestCase):
    def test_receive_deduplicates_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inbox.sqlite3"
            first = UpdateInbox(path)
            update = {"update_id": 10, "message": {"text": "/start"}}
            first.receive(update)
            first.receive(update)
            first.close()
            second = UpdateInbox(path)
            try:
                item = second.claim(now=10)
                self.assertEqual(item["update"], update)
                self.assertIsNone(second.claim(now=10))
                self.assertTrue(second.finish(item, True, now=10))
                self.assertIsNone(second.claim(now=100))
            finally:
                second.close()

    def test_expired_lease_recovery_and_stale_owner_fencing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inbox.sqlite3"
            first, second = UpdateInbox(path), UpdateInbox(path)
            try:
                first.receive({"update_id": 11})
                stale = first.claim(now=10, lease_seconds=5)
                self.assertIsNone(second.claim(now=14))
                fresh = second.claim(now=16, lease_seconds=5)
                self.assertNotEqual(stale["owner"], fresh["owner"])
                self.assertFalse(first.finish(stale, True, now=16))
                self.assertTrue(second.finish(fresh, True, now=16))
            finally:
                first.close()
                second.close()

    def test_failed_update_is_retried_with_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            inbox = UpdateInbox(Path(directory) / "inbox.sqlite3")
            try:
                inbox.receive({"update_id": 12})
                first = inbox.claim(now=10, max_attempts=2)
                self.assertTrue(inbox.finish(first, False, now=10))
                self.assertIsNone(inbox.claim(now=11, max_attempts=2))
                second = inbox.claim(now=12, max_attempts=2)
                self.assertEqual(second["attempt"], 2)
                self.assertTrue(inbox.finish(second, False, now=12))
                self.assertIsNone(inbox.claim(now=1000, max_attempts=2))
            finally:
                inbox.close()


if __name__ == "__main__":
    unittest.main()
