import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import backend.migrate_legacy_queues as migration_module
from backend.legacy_queue_guard import LegacyQueuePending, check_legacy_queues
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

    def test_second_backup_collision_leaves_first_source_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            inbox = UpdateInbox(folder / "telegram_inbox.sqlite3")
            inbox.receive({"update_id": 51})
            inbox.close()
            outbox = DeliveryOutbox(folder / "telegram_outbox.sqlite3")
            outbox.enqueue("51:1", "sendMessage", {"chat_id": 1})
            outbox.close()
            second_backup = folder / "telegram_outbox.sqlite3.pre-migration.bak"
            second_backup.write_bytes(b"preexisting-backup")
            with self.assertRaisesRegex(RuntimeError, "Backup already exists"):
                migrate_legacy_queues(folder, dry_run=False)
            self.assertFalse((folder / "telegram_inbox.sqlite3.pre-migration.bak").exists())
            self.assertFalse((folder / "telegram_queue.sqlite3").exists())
            self.assertEqual(second_backup.read_bytes(), b"preexisting-backup")

    def test_snapshot_is_authoritative_when_legacy_changes_during_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            inbox_path = folder / "telegram_inbox.sqlite3"
            inbox = UpdateInbox(inbox_path)
            inbox.receive({"update_id": 52, "message": {"text": "original"}})
            inbox.close()
            original_connect = sqlite3.connect
            changed = [False]

            def connect_with_interleaved_write(database, *args, **kwargs):
                if str(database) == str(folder / "telegram_queue.sqlite3") and not changed[0]:
                    changed[0] = True
                    writer = original_connect(inbox_path)
                    try:
                        writer.execute(
                            "UPDATE incoming_updates SET payload=? WHERE update_id=52",
                            ('{"update_id":52,"message":{"text":"changed"}}',),
                        )
                        writer.commit()
                    finally:
                        writer.close()
                return original_connect(database, *args, **kwargs)

            with patch.object(migration_module.sqlite3, "connect",
                              side_effect=connect_with_interleaved_write):
                migrate_legacy_queues(folder, dry_run=False)
            self.assertTrue(changed[0])
            unified = original_connect(folder / "telegram_queue.sqlite3")
            try:
                payload = unified.execute(
                    "SELECT payload FROM incoming_updates WHERE update_id=52"
                ).fetchone()[0]
                self.assertIn("original", payload)
                self.assertNotIn("changed", payload)
            finally:
                unified.close()
            with self.assertRaises(LegacyQueuePending):
                check_legacy_queues(folder)



if __name__ == "__main__":
    unittest.main()
