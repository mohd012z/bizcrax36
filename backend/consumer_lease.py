"""Exclusive Telegram polling lease with ownership fencing and expiry."""
import sqlite3
import time
import uuid


class ConsumerBusy(RuntimeError):
    pass


class ConsumerLease:
    def __init__(self, filename):
        self.db = sqlite3.connect(str(filename), timeout=10, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("""CREATE TABLE IF NOT EXISTS consumer_lease (
            lease_name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires REAL NOT NULL
        )""")
        self.owner = uuid.uuid4().hex

    def acquire(self, name="telegram-poller", *, now=None, seconds=90):
        now = time.time() if now is None else float(now)
        if seconds <= 0:
            raise ValueError("lease must be positive")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self.db.execute(
                "SELECT owner,expires FROM consumer_lease WHERE lease_name=?", (name,)
            ).fetchone()
            if current and current[1] > now and current[0] != self.owner:
                raise ConsumerBusy("another Telegram consumer owns the lease")
            self.db.execute(
                """INSERT INTO consumer_lease(lease_name,owner,expires) VALUES(?,?,?)
                   ON CONFLICT(lease_name) DO UPDATE SET owner=excluded.owner,
                   expires=excluded.expires""",
                (name, self.owner, now + seconds),
            )
            self.db.execute("COMMIT")
            return True
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def release(self, name="telegram-poller"):
        with self.db:
            return self.db.execute(
                "DELETE FROM consumer_lease WHERE lease_name=? AND owner=?",
                (name, self.owner),
            ).rowcount == 1

    def close(self):
        self.db.close()
