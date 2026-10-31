import tempfile
import unittest
from pathlib import Path
from backend.delivery_outbox import DeliveryOutbox
from backend.consumer_lease import ConsumerBusy, ConsumerLease
from backend.telegram_live_free import deliver_pending


class SenderRecoveryTests(unittest.TestCase):
    def test_transport_failure_retries_and_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = DeliveryOutbox(Path(directory) / "outbox.sqlite3")
            try:
                outbox.enqueue("1:1", "sendMessage", {"chat_id": 1, "text": "test"})
                calls = []
                def transport(token, method, payload):
                    calls.append(method)
                    if len(calls) == 1:
                        raise ConnectionError("temporary failure")
                    return {"ok": True}
                self.assertEqual(deliver_pending(outbox, "test", transport, now=10), 0)
                self.assertEqual(deliver_pending(outbox, "test", transport, now=11), 0)
                self.assertEqual(deliver_pending(outbox, "test", transport, now=12), 1)
                self.assertEqual(deliver_pending(outbox, "test", transport, now=100), 0)
                self.assertEqual(len(calls), 2)
            finally:
                outbox.close()

    def test_negative_api_result_is_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = DeliveryOutbox(Path(directory) / "outbox.sqlite3")
            try:
                outbox.enqueue("2:1", "answerCallbackQuery", {"callback_query_id": "x"})
                self.assertEqual(deliver_pending(outbox, "test",
                    lambda *args: {"ok": False}, now=10), 0)
                self.assertEqual(deliver_pending(outbox, "test",
                    lambda *args: {"ok": True}, now=12), 1)
            finally:
                outbox.close()


    def test_long_batch_stops_after_consumer_takeover(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "queue.sqlite3"
            outbox = DeliveryOutbox(path)
            old, new = ConsumerLease(path), ConsumerLease(path)
            try:
                outbox.enqueue("a", "sendMessage", {"chat_id": 1, "text": "first"})
                outbox.enqueue("b", "sendMessage", {"chat_id": 1, "text": "second"})
                times = iter((10, 11, 17))
                sent = []

                def renew():
                    old.acquire(now=next(times), seconds=5)

                def transport(token, method, payload):
                    sent.append(payload["text"])
                    new.acquire(now=16, seconds=30)
                    return {"ok": True}

                with self.assertRaises(ConsumerBusy):
                    deliver_pending(outbox, "test", transport, now=10,
                                    before_send=renew)
                self.assertEqual(sent, ["first"])
                remaining = outbox.claim(now=20)
                self.assertIsNotNone(remaining)
                self.assertEqual(remaining["payload"]["text"], "second")
            finally:
                old.close()
                new.close()
                outbox.close()

    def test_ownership_loss_after_claim_is_not_swallowed(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = DeliveryOutbox(Path(directory) / "queue.sqlite3")
            try:
                outbox.enqueue("a", "sendMessage", {"chat_id": 1})
                calls = []

                def renew():
                    calls.append(1)
                    if len(calls) == 2:
                        raise ConsumerBusy("lease lost")

                with self.assertRaises(ConsumerBusy):
                    deliver_pending(outbox, "test",
                                    lambda *_: self.fail("must not send"),
                                    now=10, before_send=renew)
                self.assertIsNone(outbox.claim(now=11))
                self.assertIsNotNone(outbox.claim(now=71))
            finally:
                outbox.close()


if __name__ == "__main__":
    unittest.main()
