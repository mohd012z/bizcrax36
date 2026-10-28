import contextlib
import io
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from backend import telegram_poll_continuous as runtime
from backend.telegram_poll_once import poll_once
from backend.runtime_guard import polling_lock


class RuntimeTests(unittest.TestCase):
    def test_hybrid_configuration_requires_a_scoped_dispatch_token(self):
        with patch.dict('os.environ', {'HYBRID_EXECUTION': 'github'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'dispatch'):
                runtime.configure_hybrid(threading.Event(), Path('/tmp/unused.db'))

    def test_hybrid_dispatcher_is_separate_from_polling_and_uses_private_queue(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'HYBRID_EXECUTION': 'github', 'GITHUB_DISPATCH_TOKEN': 'private',
            'TELEGRAM_BOT_TOKEN': 'bot-secret',
            'GITHUB_REPOSITORY': 'owner/repo', 'HYBRID_QUEUE_PATH': temp + '/outbox.sqlite3',
        }, clear=True):
            queue, worker = runtime.configure_hybrid(threading.Event(), Path(temp) / 'sessions.db')
            self.assertFalse(worker.is_alive())
            self.assertEqual(worker.name, 'telegram-github-dispatch')
            self.assertEqual(queue.path, Path(temp) / 'outbox.sqlite3')

    def test_dispatch_worker_stops_after_sending_one_queued_job(self):
        stopped = threading.Event()
        sent = []
        def dispatch(*args, **kwargs):
            sent.append(args[3]['request_id'])
            stopped.set()
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'HYBRID_EXECUTION': 'github', 'GITHUB_DISPATCH_TOKEN': 'private',
            'TELEGRAM_BOT_TOKEN': 'secret', 'GITHUB_REPOSITORY': 'owner/repo',
            'HYBRID_QUEUE_PATH': temp + '/outbox.sqlite3',
        }, clear=True), patch.object(runtime, 'dispatch_job', side_effect=dispatch):
            queue, worker = runtime.configure_hybrid(stopped, Path(temp) / 'sessions.db')
            queue.enqueue({'update_id': 1, 'message': {'chat': {'id': 123}, 'text': '/research solar'}})
            worker.start()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(sent, ['tg-1'])
            self.assertEqual(queue.stats(123), {'DISPATCHED': 1})

    def test_real_poller_delivers_then_acknowledges_and_stops(self):
        stopped = threading.Event()
        calls = []
        def api(token, method, payload):
            calls.append(method)
            if method == 'getWebhookInfo':
                return {'url': ''}
            if method == 'getUpdates' and 'offset' not in payload:
                return [{'update_id': 1, 'message': {'chat': {'id': 123}, 'text': '/start'}}]
            if method == 'getUpdates':
                stopped.set()
                return []
            return {}
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'secret', 'TELEGRAM_CHAT_ID': '123',
            'TELEGRAM_LOCK_PATH': temp + '/poller.lock',
            'BIZCRAX_DATABASE': temp + '/db.sqlite3',
        }, clear=True):
            runtime.run(stopped, telegram_api=api)
        self.assertEqual(calls, ['getWebhookInfo', 'getUpdates', 'sendMessage', 'getUpdates'])

    def test_local_lock_blocks_second_consumer_and_releases_after_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'poller.lock'
            with self.assertRaisesRegex(ValueError, 'simulated crash'):
                with polling_lock(path):
                    with self.assertRaisesRegex(RuntimeError, 'already running'):
                        with polling_lock(path):
                            self.fail('second consumer started')
                    raise ValueError('simulated crash')
            with polling_lock(path):
                pass

    def test_external_runtime_skips_actions_before_credentials_or_api_calls(self):
        from backend import telegram_poll_once as once
        with patch.dict('os.environ', {'TELEGRAM_RUNTIME': 'persistent'}, clear=True), \
                patch.object(once, 'api', side_effect=AssertionError('unexpected network')):
            once.main()

    def test_rejects_timeout_that_exceeds_transport_budget(self):
        with self.assertRaises(ValueError):
            poll_once('token', '123', Path('unused'), [], poll_timeout=35)

    def test_long_poll_uses_configured_timeout_without_changing_ack(self):
        calls = []
        def api(token, method, payload):
            calls.append((method, payload))
            return []
        self.assertEqual(poll_once('token', '123', Path('unused'), [],
                                   telegram_api=api, poll_timeout=25), 0)
        self.assertEqual(calls[0][1]['timeout'], 25)

    def test_stop_after_success_and_preserve_repository_configuration(self):
        stopped = threading.Event()
        calls = []
        def poll(*args, **kwargs):
            calls.append((args, kwargs))
            stopped.set()
            return 0
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'secret', 'TELEGRAM_CHAT_ID': '123',
            'BIZCRAX_DATABASE': temp + '/sessions.db',
            'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_TOKEN': 'private',
            'TELEGRAM_LOCK_PATH': temp + '/poller.lock',
        }, clear=True):
            runtime.run(stopped, poll=poll, telegram_api=lambda *a: {'url': ''})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][2], Path(temp) / 'sessions.db')
        self.assertEqual(calls[0][1]['repository'], 'owner/repo')
        self.assertEqual(calls[0][1]['job_token'], 'private')
        self.assertEqual(calls[0][1]['poll_timeout'], 25)

    def test_active_webhook_does_not_get_deleted_or_polled(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'secret', 'TELEGRAM_CHAT_ID': '123',
            'TELEGRAM_LOCK_PATH': temp + '/poller.lock',
        }, clear=True):
            methods = []
            def api(token, method, payload):
                methods.append(method)
                return {'url': 'https://existing.example/webhook'}
            with self.assertRaisesRegex(RuntimeError, 'webhook'):
                runtime.run(threading.Event(), poll=lambda *a, **k: self.fail('polled'),
                            telegram_api=api)
            self.assertEqual(methods, ['getWebhookInfo'])

    def test_conflict_stops_instead_of_retrying_forever_without_leaking_token(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'secret', 'TELEGRAM_CHAT_ID': '123',
            'TELEGRAM_LOCK_PATH': temp + '/poller.lock',
        }, clear=True):
            def fail(*a, **k):
                raise HTTPError('https://api.telegram.org/botsecret/getUpdates', 409,
                                'contains secret', {}, None)
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaisesRegex(RuntimeError, '409'):
                runtime.run(threading.Event(), poll=fail, telegram_api=lambda *a: {'url': ''})
            self.assertNotIn('secret', output.getvalue())

    def test_transient_network_failure_retries_and_can_stop(self):
        stopped = threading.Event()
        attempts = []
        def poll(*a, **k):
            attempts.append(1)
            if len(attempts) == 1:
                raise OSError('sensitive request URL')
            stopped.set()
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {
            'TELEGRAM_BOT_TOKEN': 'secret', 'TELEGRAM_CHAT_ID': '123',
            'TELEGRAM_LOCK_PATH': temp + '/poller.lock',
        }, clear=True), patch.object(stopped, 'wait', return_value=False):
            runtime.run(stopped, poll=poll, telegram_api=lambda *a: {'url': ''})
        self.assertEqual(len(attempts), 2)


if __name__ == '__main__':
    unittest.main()
