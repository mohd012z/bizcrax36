import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.telegram_queue import claim, connect, enqueue, finish, retry
from backend.telegram_worker import work_once


class WorkerTests(unittest.TestCase):
    def test_start_delivers_menu_and_marks_done(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inbox.sqlite3"
            update = {"update_id": 314, "message": {
                "chat": {"id": 123456789}, "text": "/start"}}
            enqueue(path, update)
            sent = []
            with patch("backend.telegram_worker.process_update", return_value="sent") as process:
                self.assertTrue(work_once(
                    path, "test-token", "123456789", Path(directory) / "research.sqlite3", [],
                    send=lambda method, payload: sent.append((method, payload))))
                process.assert_called_once()
            self.assertIsNone(claim(path))
            with connect(path) as db:
                self.assertEqual(db.execute(
                    "SELECT state FROM telegram_inbox WHERE update_id=314").fetchone()[0], "done")

    def test_delivery_failure_retries_without_losing_update(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inbox.sqlite3"
            enqueue(path, {"update_id": 315, "message": {
                "chat": {"id": 123456789}, "text": "/start"}})
            with patch("backend.telegram_worker.process_update", side_effect=RuntimeError("temporary")):
                self.assertTrue(work_once(path, "test-token", "123456789", None, [],
                                          send=lambda *args: None))
            with connect(path) as db:
                state, attempts, error = db.execute(
                    "SELECT state,attempts,last_error FROM telegram_inbox WHERE update_id=315"
                ).fetchone()
            self.assertEqual((state, attempts, error), ("pending", 1, "RuntimeError"))

    def test_denied_chat_is_marked_done(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inbox.sqlite3"
            enqueue(path, {"update_id": 316, "message": {
                "chat": {"id": 999}, "text": "/start"}})
            with patch("backend.telegram_worker.process_update", return_value="denied"):
                self.assertTrue(work_once(path, "test-token", "123456789", None, [],
                                          send=lambda *args: None))
            with connect(path) as db:
                self.assertEqual(db.execute(
                    "SELECT state FROM telegram_inbox WHERE update_id=316").fetchone()[0], "done")
