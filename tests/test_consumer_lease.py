import tempfile
import unittest
from pathlib import Path
from backend.consumer_lease import ConsumerBusy, ConsumerLease


class ConsumerLeaseTests(unittest.TestCase):
    def test_exclusive_ownership_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            first, second = ConsumerLease(path), ConsumerLease(path)
            try:
                self.assertTrue(first.acquire(now=10, seconds=5))
                with self.assertRaises(ConsumerBusy):
                    second.acquire(now=11, seconds=5)
                self.assertTrue(second.acquire(now=16, seconds=5))
                self.assertFalse(first.release())
                with self.assertRaises(ConsumerBusy):
                    first.acquire(now=17, seconds=5)
                self.assertTrue(second.release())
                self.assertTrue(first.acquire(now=18, seconds=5))
            finally:
                first.close()
                second.close()

    def test_reacquire_renews_owner_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            first, second = ConsumerLease(path), ConsumerLease(path)
            try:
                first.acquire(now=10, seconds=5)
                first.acquire(now=14, seconds=5)
                with self.assertRaises(ConsumerBusy):
                    second.acquire(now=16, seconds=5)
                self.assertTrue(second.acquire(now=20, seconds=5))
            finally:
                first.close()
                second.close()


if __name__ == "__main__":
    unittest.main()
