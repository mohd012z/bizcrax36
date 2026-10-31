"""Regression tests for startup after backup-first legacy queue migration."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.delivery_outbox import DeliveryOutbox
from backend.legacy_queue_guard import LegacyQueuePending, check_legacy_queues
from backend.migrate_legacy_queues import migrate_legacy_queues
from backend.update_inbox import UpdateInbox


class MigrationStartupGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        inbox = UpdateInbox(self.folder / "telegram_inbox.sqlite3")
        inbox.receive({"update_id": 41, "message": {"text": "hello"}})
        inbox.close()
        outbox = DeliveryOutbox(self.folder / "telegram_outbox.sqlite3")
        outbox.enqueue("41:1", "sendMessage",
                       {"chat_id": 123, "text": "hello"})
        outbox.close()

    def migrate(self):
        result = migrate_legacy_queues(self.folder, dry_run=False)
        self.assertEqual(result["migrated"], 2)

    def test_pending_legacy_records_block_before_migration(self):
        with self.assertRaises(LegacyQueuePending):
            check_legacy_queues(self.folder)

    def test_verified_migration_allows_startup_and_state_progression(self):
        self.migrate()
        self.assertTrue(check_legacy_queues(self.folder))
        with sqlite3.connect(self.folder / "telegram_queue.sqlite3") as db:
            db.execute("UPDATE incoming_updates SET state='done' WHERE update_id=41")
            db.execute("UPDATE deliveries SET state='sent' WHERE delivery_key='41:1'")
        self.assertTrue(check_legacy_queues(self.folder))

    def test_partial_copy_fails_closed(self):
        self.migrate()
        with sqlite3.connect(self.folder / "telegram_queue.sqlite3") as db:
            db.execute("DELETE FROM deliveries WHERE delivery_key='41:1'")
        with self.assertRaisesRegex(LegacyQueuePending, "missing or changed"):
            check_legacy_queues(self.folder)

    def test_payload_mismatch_fails_closed(self):
        self.migrate()
        with sqlite3.connect(self.folder / "telegram_queue.sqlite3") as db:
            db.execute("UPDATE incoming_updates SET payload='{}' WHERE update_id=41")
        with self.assertRaisesRegex(LegacyQueuePending, "missing or changed"):
            check_legacy_queues(self.folder)

    def test_missing_backup_fails_closed(self):
        self.migrate()
        (self.folder / "telegram_outbox.sqlite3.pre-migration.bak").unlink()
        with self.assertRaisesRegex(LegacyQueuePending, "unresolved work"):
            check_legacy_queues(self.folder)

    def test_legacy_writer_after_migration_fails_closed(self):
        self.migrate()
        inbox = UpdateInbox(self.folder / "telegram_inbox.sqlite3")
        inbox.receive({"update_id": 42, "message": {"text": "new"}})
        inbox.close()
        with self.assertRaisesRegex(LegacyQueuePending, "backup differs"):
            check_legacy_queues(self.folder)


if __name__ == "__main__":
    unittest.main()
