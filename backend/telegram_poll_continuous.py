"""Persistent polling on an always-on host, never alongside another consumer.

Set repository variable TELEGRAM_RUNTIME=persistent before starting this
process. A Telegram 409 is a configuration failure, not safe load balancing.
"""
import os
import signal
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError

from backend.telegram_bot import BASE, api
from backend.telegram_poll_once import load_ideas, poll_once
from backend.runtime_guard import polling_lock


def run(stopped, *, poll=poll_once, telegram_api=api):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    allowed = os.environ.get('TELEGRAM_ALLOWED_CHAT_IDS') or os.environ.get('TELEGRAM_CHAT_ID', '')
    if not token or not allowed or any(
        not item.strip().lstrip('-').isdigit() for item in allowed.split(',')
    ):
        raise ValueError('A bot token and numeric Telegram chat allowlist are required')
    max_updates = int(os.environ.get('MAX_UPDATES', '50'))
    poll_seconds = float(os.environ.get('POLL_SECONDS', '1'))
    if not 1 <= max_updates <= 100 or not 0.1 <= poll_seconds <= 30:
        raise ValueError('MAX_UPDATES must be 1..100; POLL_SECONDS must be 0.1..30')
    database = Path(os.environ.get('BIZCRAX_DATABASE', str(BASE / 'data/research.sqlite3')))
    lock_path = Path(os.environ.get('TELEGRAM_LOCK_PATH', str(BASE / 'data/telegram-poller.lock')))
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    job_token = os.environ.get('GITHUB_TOKEN', '')
    with polling_lock(lock_path):
        webhook = telegram_api(token, 'getWebhookInfo', {})
        if webhook.get('url'):
            raise RuntimeError('Active Telegram webhook: stop; do not start a second consumer')
        print('Telegram persistent listener starting; single-consumer mode', flush=True)
        failures = 0
        while not stopped.is_set():
            try:
                poll(token, allowed, database, load_ideas(), max_updates=max_updates,
                     repository=repository, job_token=job_token, poll_timeout=25,
                     telegram_api=telegram_api)
            except HTTPError as exc:
                if exc.code in (400, 401, 403, 409):
                    raise RuntimeError('Telegram configuration failure HTTP %d; listener stopped' % exc.code) from None
                failures += 1
                print('Telegram transport failure HTTP %d; retrying' % exc.code, flush=True)
            except (OSError, RuntimeError) as exc:
                failures += 1
                print('Telegram transient failure: %s; retrying' % type(exc).__name__, flush=True)
            else:
                failures = 0
            stopped.wait(min(30, 2 ** min(failures, 5)) if failures else poll_seconds)


def main():
    stopped = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopped.set())
    try:
        run(stopped)
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 78
    except HTTPError as exc:
        print('Telegram startup HTTP %d' % exc.code, file=sys.stderr, flush=True)
        return 78 if exc.code in (400, 401, 403, 409) else 1
    except OSError:
        print('Telegram startup transport/storage failure', file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
