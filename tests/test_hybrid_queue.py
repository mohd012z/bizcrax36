"""Offline behavior tests for the listener/Actions boundary."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def message(text='/research solar small', update_id=1, chat=123):
    return {'update_id': update_id, 'message': {'text': text, 'chat': {'id': chat},
        'from': {'id': 42, 'first_name': 'private name'}, 'unneeded': 'private metadata'}}


class QueueTests(unittest.TestCase):
    def setUp(self):
        from backend import hybrid_queue
        self.mod = hybrid_queue
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = [100000.0]
        self.path = Path(self.temp.name) / 'queue.sqlite3'
        self.queue = hybrid_queue.HybridQueue(self.path, clock=lambda: self.clock[0])

    def test_heavy_work_is_classified_without_running_engine(self):
        for text in ['/research solar', '/report solar', '/ai solar', '/biz solar', '/news', '/newsplan', 'https://example.org/article']:
            self.assertTrue(self.mod.is_heavy(message(text)), text)
        for text in ['/start', '/status', '/sector', '/help', '/ai']:
            self.assertFalse(self.mod.is_heavy(message(text)), text)

    def test_payload_omits_sender_names_and_unneeded_message_metadata(self):
        result = self.mod.minimal_update(message())
        self.assertEqual(result, {'update_id': 1, 'message': {'chat': {'id': 123}, 'text': '/research solar small'}})
        self.assertNotIn('private', json.dumps(result))

    def test_encrypted_dispatch_payload_requires_the_same_bot_secret(self):
        from cryptography.fernet import InvalidToken
        clean = self.mod.minimal_update(message())
        encrypted = self.mod.encrypt_update('bot-secret', clean)
        self.assertNotIn('/research', encrypted)
        self.assertEqual(self.mod.decrypt_update('bot-secret', encrypted), clean)
        with self.assertRaises(InvalidToken):
            self.mod.decrypt_update('other-secret', encrypted)

    def test_duplicate_update_is_one_durable_job_across_restarts(self):
        first = self.queue.enqueue(message())
        second = self.mod.HybridQueue(self.path).enqueue(message())
        self.assertEqual(first, second)
        self.assertEqual(first, 'tg-1')
        self.assertEqual(self.queue.stats(123)['QUEUED'], 1)

    def test_enqueues_before_acknowledgement(self):
        seen = []
        def send(method, payload):
            seen.append(self.queue.stats(123)['QUEUED'])
        self.assertEqual(self.queue.handle(message(), send, '123'), 'sent')
        self.assertEqual(seen, [1])

    def test_unauthorized_job_never_enqueues(self):
        self.assertEqual(self.queue.handle(message(chat=999), lambda *a: None, '123'), 'denied')
        self.assertEqual(self.queue.stats(999), {})

    def test_light_command_bypasses_queue(self):
        self.assertIsNone(self.queue.handle(message('/start'), lambda *a: self.fail('sent'), '123'))

    def test_lost_ack_is_retried_without_creating_a_second_cloud_job(self):
        def broken_send(*args):
            raise OSError('transient send failure')
        with self.assertRaises(OSError):
            self.queue.handle(message(), broken_send, '123')
        self.queue.handle(message(), lambda *args: None, '123')
        self.assertEqual(self.queue.stats(123), {'QUEUED': 1})

    def test_ai_menu_does_not_call_an_llm_on_the_polling_path(self):
        from backend import telegram_poll_once as once
        with patch.object(once.ai_bizcollector, 'ask_intent', side_effect=AssertionError('slow API')):
            self.assertEqual(once.process_update(message('/ai'), send=lambda *a: None,
                allowed_ids='123', database=self.path, ideas=[], token='secret', hybrid_queue=self.queue.handle), 'sent')
        self.assertEqual(self.queue.stats(123), {})

    def test_per_chat_limit_is_explicit(self):
        queue = self.mod.HybridQueue(self.path, clock=lambda: self.clock[0], max_pending=1)
        queue.enqueue(message())
        with self.assertRaisesRegex(ValueError, 'limit'):
            queue.enqueue(message(update_id=2))

    def test_rolling_daily_limit_survives_dispatch(self):
        queue = self.mod.HybridQueue(self.path, clock=lambda: self.clock[0], max_daily=1)
        queue.enqueue(message())
        queue.work_once(lambda job: None)
        with self.assertRaisesRegex(ValueError, 'limit'):
            queue.enqueue(message(update_id=2))
        self.clock[0] += 86401
        self.assertEqual(queue.enqueue(message(update_id=2)), 'tg-2')

    def test_successful_dispatch_runs_once(self):
        self.queue.enqueue(message())
        sent = []
        self.assertTrue(self.queue.work_once(sent.append))
        self.assertFalse(self.queue.work_once(sent.append))
        self.assertEqual(sent[0]['request_id'], 'tg-1')
        self.assertEqual(sent[0]['update']['message']['text'], '/research solar small')
        self.assertEqual(self.queue.stats(123), {'DISPATCHED': 1})

    def test_failed_dispatch_backs_off_then_retries(self):
        self.queue.enqueue(message())
        def fail(job):
            raise OSError('secret transport URL')
        self.queue.work_once(fail)
        sent = []
        self.assertFalse(self.queue.work_once(sent.append))
        self.clock[0] += 60
        self.assertTrue(self.queue.work_once(sent.append))
        self.assertEqual(len(sent), 1)

    def test_crashed_dispatch_lease_is_recovered(self):
        self.queue.enqueue(message())
        with self.queue.connect() as db:
            db.execute("UPDATE hybrid_jobs SET state='DISPATCHING', lease_until=?, attempts=1", (self.clock[0]+60,))
        self.assertFalse(self.queue.work_once(lambda job: None))
        self.clock[0] += 61
        self.assertTrue(self.queue.work_once(lambda job: None))

    def test_retry_exhaustion_stays_visible(self):
        self.queue.enqueue(message())
        def fail(job):
            raise OSError('private')
        for _ in range(5):
            self.queue.work_once(fail)
            self.clock[0] += 400
        self.assertEqual(self.queue.stats(123), {'FAILED': 1})
        self.assertFalse(self.queue.work_once(fail))
        replies = []
        self.queue.handle(message(), lambda method, payload: replies.append(payload['text']), '123')
        self.assertIn('failed', replies[-1].lower())
        self.assertNotIn('Awaiting GitHub', replies[-1])

    def test_dispatch_contract_uses_only_declared_workflow_inputs(self):
        requests = []
        class Response:
            status = 204
            def __enter__(self): return self
            def __exit__(self, *args): pass
        def opener(request, timeout):
            requests.append(request)
            return Response()
        self.mod.dispatch_job('owner/repo', 'private-key', 'main',
            {'request_id': 'tg-1', 'update': self.mod.minimal_update(message())},
            bot_token='bot-secret', opener=opener)
        payload = json.loads(requests[0].data)
        self.assertEqual(set(payload['inputs']), {'request_id', 'update_encrypted'})
        self.assertNotIn('private-key', requests[0].data.decode())
        self.assertNotIn('/research', requests[0].data.decode())
        self.assertTrue(requests[0].full_url.endswith('/hybrid-telegram-job.yml/dispatches'))

    def test_polling_path_queues_heavy_work_without_calling_research(self):
        from backend import telegram_poll_once as once
        calls = []
        with patch.object(once, 'run_research', side_effect=AssertionError('blocked polling thread')):
            result = once.process_update(message(), send=lambda *a: calls.append(a),
                allowed_ids='123', database=self.path, ideas=[], token='secret', hybrid_queue=self.queue.handle)
        self.assertEqual(result, 'sent')
        self.assertEqual(self.queue.stats(123), {'QUEUED': 1})


if __name__ == '__main__':
    unittest.main()
