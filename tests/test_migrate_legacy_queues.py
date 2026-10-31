import sqlite3
import tempfile
import unittest
from pathlib import Path
from backend.migrate_legacy_queues import migrate_legacy_queues
from backend.update_inbox import UpdateInbox
from backend.delivery_outbox import DeliveryOutbox


class MigrationTests(unittest.TestCase):
    def test_dry_run_and_backup_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            inbox = UpdateInbox(folder / "telegram_inbox.sqlite3")
            inbox.receive({"update_id": 42, "message": {"text": "hello"}})
            inbox.close()
            outbox = DeliveryOutbox(folder / "telegram_outbox.sqlite3")
            outbox.enqueue("42:1", "sendMessage", {"chat_id": 7, "text": "hello"})
            outbox.close()
            plan = migrate_legacy_queues(folder)
            self.assertEqual(sum(plan["sources"].values()), 2)
            self.assertFalse((folder / "telegram_queue.sqlite3").exists())
            result = migrate_legacy_queues(folder, dry_run=False)
            self.assertEqual(result["migrated"], 2)
            self.assertEqual(len(result["backups"]), 2)
            unified_inbox = UpdateInbox(folder / "telegram_queue.sqlite3")
            unified_outbox = DeliveryOutbox(folder / "telegram_queue.sqlite3")
            try:
                self.assertEqual(unified_inbox.claim(now=10)["update_id"], 42)
                self.assertEqual(unified_outbox.claim(now=10)["payload"]["text"], "hello")
            finally:
                unified_inbox.close()
                unified_outbox.close()

    def test_refuses_to_overwrite_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            old = UpdateInbox(folder / "telegram_inbox.sqlite3")
            old.receive({"update_id": 5})
            old.close()
            new = UpdateInbox(folder / "telegram_queue.sqlite3")
            new.close()
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                migrate_legacy_queues(folder, dry_run=False)


if __name__ == "__main__":
    unittest.main()
