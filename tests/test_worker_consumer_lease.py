"""Regression checks for consumer ownership enforcement in the live worker."""
import inspect
import tempfile
import unittest
from pathlib import Path

from backend.consumer_lease import ConsumerBusy, ConsumerLease
from backend import telegram_live_free


class WorkerConsumerLeaseTests(unittest.TestCase):
    def test_worker_acquires_and_renews_before_polling(self):
        source = inspect.getsource(telegram_live_free.main)
        self.assertIn("consumer=ConsumerLease(queue_path)", source)
        self.assertIn("consumer.acquire(seconds=90)", source)
        self.assertIn('updates=api(token,"getUpdates",payload)', source)
        self.assertLess(source.index("consumer.acquire(seconds=90)"),
                        source.index('updates=api(token,"getUpdates",payload)'))
        self.assertIn("except ConsumerBusy:", source)
        self.assertIn("raise SystemExit", source)

    def test_competing_consumer_cannot_renew_after_takeover(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            old = ConsumerLease(path)
            new = ConsumerLease(path)
            try:
                old.acquire(now=10, seconds=5)
                new.acquire(now=16, seconds=90)
                with self.assertRaises(ConsumerBusy):
                    old.acquire(now=17, seconds=90)
            finally:
                old.close()
                new.close()


if __name__ == "__main__":
    unittest.main()
