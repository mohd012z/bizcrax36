"""Actions executor for validated hybrid jobs; never polls Telegram updates."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from backend.hybrid_queue import WORKFLOW, decrypt_update, is_heavy, minimal_update, update_chat
from backend.telegram_bot import BASE, api
from backend.telegram_poll_once import (JOBS_DIR, _multipart_send, load_ideas,
                                        persist_jobs, process_update)


def validate_request(request_id, raw, allowed_ids):
    if not re.fullmatch(r'tg-\d+', request_id) or len(raw) > 32000:
        raise ValueError('Invalid hybrid request')
    update = minimal_update(json.loads(raw))
    chat = update_chat(update)
    if request_id != 'tg-' + str(update['update_id']) or not is_heavy(update):
        raise ValueError('Hybrid request identity or operation mismatch')
    if str(chat) not in {item.strip() for item in allowed_ids.split(',') if item.strip()}:
        raise ValueError('Hybrid request chat is not authorized')
    return update, chat


def github_json(url, token):
    request = Request(url, headers={'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'bizcrax36-hybrid'})
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read(4_000_000))


def prior_success(repository, token, request_id, current_run_id, *, fetch=github_json):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not token:
        raise ValueError('GitHub receipt verification requires repository credentials')
    data = fetch('https://api.github.com/repos/%s/actions/workflows/%s/runs?event=workflow_dispatch&per_page=100'
                 % (repository, WORKFLOW), token)
    return any(str(run.get('id')) != str(current_run_id)
               and run.get('display_title') == 'hybrid-' + request_id
               and run.get('conclusion') == 'success'
               for run in data.get('workflow_runs', []))


def execute_update(update, token, allowed_ids, repository, job_token, *, jobs_dir=JOBS_DIR,
                   handler=process_update, sender=api, document_sender=_multipart_send,
                   persist=persist_jobs):
    before = {path: path.stat().st_mtime_ns for path in jobs_dir.glob('*/report.docx')}
    outcome = handler(update, send=lambda method, payload: sender(token, method, payload),
                      allowed_ids=allowed_ids, database=BASE/'data/research.sqlite3',
                      ideas=load_ideas(), token=token, repository=repository, job_token=job_token)
    if outcome != 'sent':
        raise ValueError('Hybrid job did not produce an authorized response')
    # Research emits a summary/menu. Attach new research reports now as well,
    # so the user need not wait for another callback/runner to fetch the file.
    for path in sorted(jobs_dir.glob('*/report.docx')):
        if before.get(path) != path.stat().st_mtime_ns:
            document_sender(token, 'sendDocument', {'chat_id': str(update_chat(update)),
                'caption': 'Research report — review assumptions and source evidence'}, 'document', path)
    if repository and job_token:
        # Existing engine history contains research outputs, never the raw update.
        # Caller permits this only when executing approved main code.
        persist(repository, job_token)
    return outcome


def main():
    try:
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        allowed = os.environ.get('TELEGRAM_ALLOWED_CHAT_IDS') or os.environ.get('TELEGRAM_CHAT_ID', '')
        request_id = os.environ.get('HYBRID_REQUEST_ID', '')
        repository, github_token = os.environ.get('GITHUB_REPOSITORY', ''), os.environ.get('GITHUB_TOKEN', '')
        if not token:
            raise ValueError('Telegram credentials missing')
        decrypted = decrypt_update(token, os.environ.get('HYBRID_UPDATE_ENCRYPTED', ''))
        update, _ = validate_request(request_id, json.dumps(decrypted), allowed)
        if prior_success(repository, github_token, request_id, os.environ.get('GITHUB_RUN_ID', '')):
            print('Hybrid completed duplicate suppressed: ' + request_id)
            return 0
        # Never push feature-branch code into main through the history helper.
        archive = os.environ.get('GITHUB_REF') == 'refs/heads/main'
        execute_update(update, token, allowed, repository if archive else '', github_token if archive else '')
        print('Hybrid response delivered: ' + request_id)
        return 0
    except Exception as exc:
        # Transport errors can contain secret-bearing URLs. Never log raw errors.
        print('Hybrid execution failed: ' + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
