"""Private SQLite outbox: local menus stay responsive while Actions runs jobs."""
import json
import base64
import hashlib
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.request import Request, urlopen

WORKFLOW = 'hybrid-telegram-job.yml'
HEAVY = {'/research', '/report', '/ai', '/biz', '/news', '/newsplan', '/plan'}


def is_heavy(update):
    callback = update.get('callback_query') or {}
    data = str(callback.get('data', ''))
    if data:
        return (data.startswith(('bc:report:', 'bc:ai:')) and data != 'bc:ai:ask'
                or data in {'bc:news:scan', 'bc:news:plan'})
    text = str((update.get('message') or {}).get('text', '')).strip()
    parts = text.split(maxsplit=1)
    command = parts[0].split('@')[0].lower() if parts else ''
    return (text.startswith(('https://', 'http://')) or command in HEAVY
            and (command not in {'/ai', '/biz'} or len(parts) > 1))


def minimal_update(update):
    uid = update.get('update_id')
    if type(uid) is not int or uid < 0:
        raise ValueError('Invalid Telegram update ID')
    callback = update.get('callback_query')
    message = (callback.get('message') if isinstance(callback, dict) else update.get('message')) or {}
    chat = (message.get('chat') or {}).get('id')
    if type(chat) is not int:
        raise ValueError('Invalid Telegram chat ID')
    out = {'update_id': uid}
    clean_message = {'chat': {'id': chat}}
    if isinstance(callback, dict):
        data, callback_id = callback.get('data'), callback.get('id')
        if not isinstance(data, str) or len(data.encode()) > 64 or not isinstance(callback_id, str):
            raise ValueError('Invalid Telegram callback')
        if type(message.get('message_id')) is int:
            clean_message['message_id'] = message['message_id']
        out['callback_query'] = {'id': callback_id, 'data': data, 'message': clean_message}
    else:
        text = message.get('text')
        if not isinstance(text, str) or not 1 <= len(text) <= 4096:
            raise ValueError('Invalid Telegram command')
        clean_message['text'] = text
        out['message'] = clean_message
    return out


def update_chat(update):
    callback = update.get('callback_query') or {}
    message = callback.get('message') or update.get('message') or {}
    return (message.get('chat') or {}).get('id')


def cipher(bot_token):
    from cryptography.fernet import Fernet
    if not bot_token:
        raise ValueError('Telegram bot secret required for encrypted jobs')
    key = hashlib.sha256(b'bizcrax36-hybrid-update-v1:' + bot_token.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_update(bot_token, update):
    return cipher(bot_token).encrypt(json.dumps(minimal_update(update)).encode()).decode()


def decrypt_update(bot_token, encrypted):
    if len(encrypted) > 32000:
        raise ValueError('Hybrid envelope too large')
    return minimal_update(json.loads(cipher(bot_token).decrypt(encrypted.encode(), ttl=86400)))


def dispatch_job(repository, token, ref, job, *, bot_token, opener=urlopen):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) or not token or not ref:
        raise ValueError('Hybrid dispatch requires a repository, approved ref, and scoped token')
    payload = {'ref': ref, 'inputs': {'request_id': job['request_id'],
                                    'update_encrypted': encrypt_update(bot_token, job['update'])}}
    request = Request('https://api.github.com/repos/%s/actions/workflows/%s/dispatches' % (repository, WORKFLOW),
        data=json.dumps(payload).encode(), method='POST', headers={
            'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2022-11-28',
            'User-Agent': 'bizcrax36-hybrid'})
    with opener(request, timeout=20) as response:
        if response.status != 204:
            raise RuntimeError('GitHub dispatch was not accepted')


class HybridQueue:
    def __init__(self, path, *, clock=time.time, max_daily=20, max_pending=3):
        if not 1 <= max_daily <= 200 or not 1 <= max_pending <= 20:
            raise ValueError('Hybrid queue limits out of range')
        self.path, self.clock = Path(path), clock
        self.max_daily, self.max_pending = max_daily, max_pending
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS hybrid_jobs (
                request_id TEXT PRIMARY KEY, chat_id INTEGER NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
                available REAL NOT NULL, lease_until REAL NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0, error_class TEXT)''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def enqueue(self, update):
        clean = minimal_update(update)
        if not is_heavy(clean):
            raise ValueError('Not a background job')
        chat, now = update_chat(clean), self.clock()
        request_id = 'tg-' + str(clean['update_id'])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM hybrid_jobs WHERE request_id=?', (request_id,)).fetchone():
                return request_id
            daily = db.execute('SELECT count(*) FROM hybrid_jobs WHERE created>=?', (now-86400,)).fetchone()[0]
            pending = db.execute("SELECT count(*) FROM hybrid_jobs WHERE chat_id=? AND state IN ('QUEUED','DISPATCHING')", (chat,)).fetchone()[0]
            if daily >= self.max_daily or pending >= self.max_pending:
                raise ValueError('Hybrid job limit reached; request was not queued')
            db.execute('INSERT INTO hybrid_jobs (request_id,chat_id,payload,state,created,available) VALUES (?,?,?,?,?,?)',
                       (request_id, chat, json.dumps(clean), 'QUEUED', now, now))
        return request_id

    def stats(self, chat):
        with self.connect() as db:
            return dict(db.execute('SELECT state,count(*) FROM hybrid_jobs WHERE chat_id=? GROUP BY state', (chat,)))

    def handle(self, update, send, allowed_ids):
        text = str((update.get('message') or {}).get('text', '')).strip()
        status = text.split('@')[0] == '/hybrid'
        if not status and not is_heavy(update):
            return None
        chat = update_chat(update)
        if str(chat) not in {x.strip() for x in allowed_ids.split(',') if x.strip()}:
            return 'denied'
        if status:
            counts = self.stats(chat)
            summary = ', '.join('%s=%d' % pair for pair in sorted(counts.items())) or 'No queued requests'
            text = ('Hybrid listener active. %s. DISPATCHED means GitHub accepted the job, '
                    'not that research completed. Results arrive separately in Telegram.') % summary
        else:
            callback = update.get('callback_query') or {}
            if callback.get('id'):
                # Same stale-callback handling as the existing synchronous router.
                from backend.telegram_poll_once import safe_callback_answer
                safe_callback_answer(send, callback['id'], text='Queueing background work')
            try:
                request_id = self.enqueue(update)
            except ValueError:
                text = 'Hybrid queue limit or invalid request. Request was not queued; try again later.'
            else:
                with self.connect() as db:
                    state = db.execute('SELECT state FROM hybrid_jobs WHERE request_id=?', (request_id,)).fetchone()[0]
                if state == 'FAILED':
                    text = 'Background dispatch failed for %s. Resend the command as a new request after checking /hybrid.' % request_id
                elif state == 'DISPATCHED':
                    text = 'GitHub already accepted %s. Results and completion are reported separately.' % request_id
                else:
                    text = ('Background request saved: %s. Awaiting GitHub processing; '
                            'menus and /status remain available. Use /hybrid for queue status.') % request_id
        send('sendMessage', {'chat_id': chat, 'text': text, 'disable_web_page_preview': 'true'})
        return 'sent'

    def work_once(self, dispatch):
        now = self.clock()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE hybrid_jobs SET state=CASE WHEN attempts>=5 THEN 'FAILED' ELSE 'QUEUED' END WHERE state='DISPATCHING' AND lease_until<=?", (now,))
            row = db.execute("SELECT request_id,payload,attempts FROM hybrid_jobs WHERE state='QUEUED' AND available<=? ORDER BY created,request_id LIMIT 1", (now,)).fetchone()
            if row is None:
                return False
            request_id, payload, attempts = row
            db.execute("UPDATE hybrid_jobs SET state='DISPATCHING',lease_until=?,attempts=attempts+1 WHERE request_id=?", (now+60, request_id))
        try:
            dispatch({'request_id': request_id, 'update': json.loads(payload)})
        except Exception as exc:
            attempts += 1
            error_class = type(exc).__name__
            code = getattr(exc, 'code', None)
            if type(code) is int:
                error_class += ':' + str(code)
            print('Hybrid dispatch %s: %s (%s)' % (
                request_id, 'FAILED' if attempts >= 5 else 'retry scheduled', error_class), flush=True)
            with self.connect() as db:
                db.execute('UPDATE hybrid_jobs SET state=?,available=?,lease_until=0,error_class=? WHERE request_id=?',
                    ('FAILED' if attempts >= 5 else 'QUEUED', self.clock()+min(300, 5*2**attempts), error_class, request_id))
        else:
            with self.connect() as db:
                db.execute("UPDATE hybrid_jobs SET state='DISPATCHED',lease_until=0,error_class=NULL WHERE request_id=?", (request_id,))
        return True
