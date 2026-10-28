"""SQLite-backed Telegram update inbox. Persist on a mounted durable volume."""
import json
import sqlite3
import time
from pathlib import Path


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS telegram_inbox (
        update_id INTEGER PRIMARY KEY,
        payload TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        available_at REAL NOT NULL DEFAULT 0,
        leased_at REAL,
        last_error TEXT
    )""")
    return conn


def enqueue(path, update):
    if not isinstance(update, dict) or type(update.get("update_id")) is not int:
        raise ValueError("Invalid update_id")
    with connect(path) as db:
        cur = db.execute(
            "INSERT OR IGNORE INTO telegram_inbox(update_id,payload) VALUES (?,?)",
            (update["update_id"], json.dumps(update, separators=(",", ":"))))
        return cur.rowcount == 1


def claim(path, lease_seconds=900):
    now = time.time()
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            """SELECT update_id,payload FROM telegram_inbox
               WHERE (state='pending' AND available_at<=?)
                  OR (state='processing' AND leased_at<=?)
               ORDER BY update_id LIMIT 1""", (now, now-lease_seconds)).fetchone()
        if not row:
            db.commit()
            return None
        db.execute(
            """UPDATE telegram_inbox SET state='processing',leased_at=?,attempts=attempts+1
               WHERE update_id=?""", (now, row[0]))
        db.commit()
        return row[0], json.loads(row[1])


def finish(path, update_id):
    with connect(path) as db:
        db.execute("UPDATE telegram_inbox SET state='done',leased_at=NULL WHERE update_id=?", (update_id,))


def retry(path, update_id, error, max_attempts=5):
    with connect(path) as db:
        row = db.execute("SELECT attempts FROM telegram_inbox WHERE update_id=?", (update_id,)).fetchone()
        attempts = row[0] if row else max_attempts
        state = "failed" if attempts >= max_attempts else "pending"
        delay = min(300, 2 ** min(attempts, 8))
        db.execute(
            """UPDATE telegram_inbox SET state=?,available_at=?,leased_at=NULL,last_error=?
               WHERE update_id=?""",
            (state, time.time()+delay, type(error).__name__, update_id))
