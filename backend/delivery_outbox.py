"""Bounded SQLite delivery outbox with fenced leases and restart recovery.

Telegram sends are at-least-once: a crash after delivery but before acknowledgement
can cause a duplicate. Do not claim exactly-once external delivery.
"""
import json
import sqlite3
import time
import uuid


class DeliveryOutbox:
    def __init__(self, filename):
        self.db = sqlite3.connect(str(filename), timeout=10, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("""CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_key TEXT NOT NULL UNIQUE,
            method TEXT NOT NULL,
            payload TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            due REAL NOT NULL DEFAULT 0,
            owner TEXT,
            lease_until REAL NOT NULL DEFAULT 0
        )""")

    def enqueue(self, key, method, payload):
        if not key or not method or not isinstance(payload, dict):
            raise ValueError("invalid delivery")
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO deliveries(delivery_key,method,payload) VALUES (?,?,?)",
                (str(key), str(method), json.dumps(payload, ensure_ascii=False)),
            )

    def claim(self, now=None, lease_seconds=60, max_attempts=5):
        now = time.time() if now is None else float(now)
        if lease_seconds <= 0 or max_attempts < 1:
            raise ValueError("invalid retry policy")
        owner = uuid.uuid4().hex
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                """SELECT id,method,payload,attempts FROM deliveries
                   WHERE attempts < ? AND due <= ?
                   AND (state='pending' OR (state='leased' AND lease_until <= ?))
                   ORDER BY id LIMIT 1""", (max_attempts, now, now)
            ).fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            self.db.execute(
                """UPDATE deliveries SET state='leased',owner=?,lease_until=?,
                   attempts=attempts+1 WHERE id=?""",
                (owner, now + lease_seconds, row[0]),
            )
            self.db.execute("COMMIT")
            return {"id": row[0], "method": row[1], "payload": json.loads(row[2]),
                    "attempt": row[3] + 1, "owner": owner}
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def finish(self, item, success, now=None):
        """True=confirmed, False=retryable failure, None=uncertain/no auto-retry."""
        if success is not None and type(success) is not bool:
            raise ValueError("delivery result must be True, False, or None")
        now = time.time() if now is None else float(now)
        delay = min(300, 2 ** min(item["attempt"], 8))
        state = "uncertain" if success is None else ("sent" if success else "pending")
        due = now + delay if success is False else now
        with self.db:
            cursor = self.db.execute(
                """UPDATE deliveries SET state=?,owner=NULL,lease_until=0,due=?
                   WHERE id=? AND owner=? AND state='leased'""",
                (state, due, item["id"], item["owner"]),
            )
            return cursor.rowcount == 1

    def close(self):
        self.db.close()
