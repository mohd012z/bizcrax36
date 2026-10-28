import json
import tempfile
import unittest
from unittest.mock import patch
import os
from pathlib import Path

from test_hybrid_queue import message


class CloudTests(unittest.TestCase):
    def setUp(self):
        from backend import hybrid_cloud
        self.cloud = hybrid_cloud

    def test_valid_job_preserves_request_identity(self):
        update, chat = self.cloud.validate_request('tg-1', json.dumps(message()), '123')
        self.assertEqual(chat, 123)
        self.assertNotIn('from', update['message'])

    def test_forged_request_id_and_unauthorized_chat_fail_before_sending(self):
        for request_id, allowed in [('tg-9', '123'), ('tg-1', '999')]:
            with self.assertRaises(ValueError):
                self.cloud.validate_request(request_id, json.dumps(message()), allowed)

    def test_workflow_cannot_run_light_commands_as_background_jobs(self):
        with self.assertRaises(ValueError):
            self.cloud.validate_request('tg-1', json.dumps(message('/start')), '123')

    def test_prior_success_suppresses_completed_duplicate_but_not_current_run(self):
        runs = {'workflow_runs': [
            {'id': 10, 'display_title': 'hybrid-tg-1', 'conclusion': 'success'},
            {'id': 11, 'display_title': 'hybrid-tg-2', 'conclusion': 'success'}]}
        fetch = lambda *a: runs
        self.assertTrue(self.cloud.prior_success('owner/repo', 'key', 'tg-1', '12', fetch=fetch))
        self.assertFalse(self.cloud.prior_success('owner/repo', 'key', 'tg-1', '10', fetch=fetch))
        self.assertFalse(self.cloud.prior_success('owner/repo', 'key', 'tg-3', '12', fetch=fetch))

    def test_existing_engine_receives_job_and_new_docx_is_delivered(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def handler(update, **kwargs):
                calls.append(('handler', update['update_id']))
                kwargs['send']('sendMessage', {'chat_id': 123, 'text': 'real handler output'})
                report = root / 'one' / 'report.docx'
                report.parent.mkdir()
                report.write_bytes(b'report fixture')
                return 'sent'
            def send(token, method, payload):
                calls.append((method, payload['chat_id']))
            def doc(*args):
                calls.append(('document', Path(args[-1]).name))
            self.cloud.execute_update(message(), 'token', '123', 'owner/repo', 'job-key',
                jobs_dir=root, handler=handler, sender=send, document_sender=doc,
                persist=lambda *args: calls.append(('persist', args[0])))
        self.assertEqual(calls, [('handler', 1), ('sendMessage', 123),
                                ('document', 'report.docx'), ('persist', 'owner/repo')])

    def test_artifact_or_history_failure_is_not_claimed_as_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            def broken(*args, **kwargs):
                raise OSError('secret request URL')
            with self.assertRaises(OSError):
                self.cloud.execute_update(message(), 'token', '123', '', '',
                    jobs_dir=Path(temp), handler=broken)

    def test_feature_branch_never_pushes_history_or_code_into_main(self):
        from backend.hybrid_queue import encrypt_update
        env = {'TELEGRAM_BOT_TOKEN': 'secret', 'TELEGRAM_CHAT_ID': '123',
            'HYBRID_REQUEST_ID': 'tg-1', 'HYBRID_UPDATE_ENCRYPTED': encrypt_update('secret', message()),
            'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_TOKEN': 'private',
            'GITHUB_REF': 'refs/heads/feature', 'GITHUB_RUN_ID': '12'}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(self.cloud, 'prior_success', return_value=False), \
                patch.object(self.cloud, 'execute_update') as execute:
            self.assertEqual(self.cloud.main(), 0)
            self.assertEqual(execute.call_args.args[3:], ('', ''))

    def test_completed_duplicate_never_calls_the_telegram_engine(self):
        from backend.hybrid_queue import encrypt_update
        env = {'TELEGRAM_BOT_TOKEN': 'secret', 'TELEGRAM_CHAT_ID': '123',
            'HYBRID_REQUEST_ID': 'tg-1', 'HYBRID_UPDATE_ENCRYPTED': encrypt_update('secret', message()),
            'GITHUB_REPOSITORY': 'owner/repo', 'GITHUB_TOKEN': 'private'}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(self.cloud, 'prior_success', return_value=True), \
                patch.object(self.cloud, 'execute_update', side_effect=AssertionError('duplicate send')):
            self.assertEqual(self.cloud.main(), 0)

    def test_dispatch_payload_matches_workflow_declared_inputs(self):
        path = Path(__file__).resolve().parent.parent / '.github/workflows/hybrid-telegram-job.yml'
        content = path.read_text()
        for field in ['request_id', 'update_encrypted']:
            self.assertIn('      ' + field + ':', content)
        self.assertIn('group: hybrid-${{ inputs.request_id }}', content)
        self.assertNotIn('schedule:', content)
        self.assertNotIn('MINDA_API_KEY', content)


if __name__ == '__main__':
    unittest.main()
