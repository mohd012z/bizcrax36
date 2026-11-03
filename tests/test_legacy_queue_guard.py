import sqlite3
import tempfile
import unittest
from pathlib import Path
from backend.legacy_queue_guard import check_legacy_queues, LegacyQueuePending


class LegacyQueueGuardTests(unittest.TestCase):
    def test_no_legacy_queue_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(check_legacy_queues(directory))

    def test_pending_legacy_outbox_blocks_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telegram_outbox.sqlite3"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE deliveries (state TEXT)")
            db.execute("INSERT INTO deliveries VALUES ('pending')")
            db.commit()
            db.close()
            with self.assertRaisesRegex(LegacyQueuePending, "unresolved work"):
                check_legacy_queues(directory)

    def test_completed_legacy_queues_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telegram_inbox.sqlite3"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE incoming_updates (state TEXT)")
            db.execute("INSERT INTO incoming_updates VALUES ('done')")
            db.commit()
            db.close()
            self.assertTrue(check_legacy_queues(directory))

    def test_corrupt_or_unknown_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telegram_outbox.sqlite3"
            db = sqlite3.connect(path)
            db.execute("CREATE TABLE unrelated (id INTEGER)")
            db.commit()
            db.close()
            with self.assertRaises(LegacyQueuePending):
                check_legacy_queues(directory)


if __name__ == "__main__":
    unittest.main()
