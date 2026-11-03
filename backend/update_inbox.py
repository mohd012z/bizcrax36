"""Recoverable SQLite Telegram update inbox with fenced worker ownership."""
import json
import sqlite3
import time
import uuid


class UpdateInbox:
    def __init__(self, filename):
        self.db = sqlite3.connect(str(filename), timeout=10, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("""CREATE TABLE IF NOT EXISTS incoming_updates (
            update_id INTEGER PRIMARY KEY,
            payload TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            owner TEXT,
            lease_until REAL NOT NULL DEFAULT 0,
            due REAL NOT NULL DEFAULT 0
        )""")

    def receive(self, update):
        uid = int(update["update_id"])
        payload = json.dumps(update, ensure_ascii=False)
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO incoming_updates(update_id,payload) VALUES (?,?)",
                (uid, payload),
            )

    def claim(self, now=None, lease_seconds=60, max_attempts=5):
        now = time.time() if now is None else float(now)
        if lease_seconds <= 0 or max_attempts < 1:
            raise ValueError("invalid retry policy")
        owner = uuid.uuid4().hex
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                """SELECT update_id,payload,attempts FROM incoming_updates
                   WHERE attempts < ? AND due <= ?
                   AND (state='pending' OR (state='leased' AND lease_until <= ?))
                   ORDER BY update_id LIMIT 1""",
                (max_attempts, now, now),
            ).fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            self.db.execute(
                """UPDATE incoming_updates SET state='leased',owner=?,
                   lease_until=?,attempts=attempts+1 WHERE update_id=?""",
                (owner, now + lease_seconds, row[0]),
            )
            self.db.execute("COMMIT")
            return {"update_id": row[0], "update": json.loads(row[1]),
                    "owner": owner, "attempt": row[2] + 1}
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def finish(self, item, success, now=None):
        now = time.time() if now is None else float(now)
        delay = min(300, 2 ** min(item["attempt"], 8))
        with self.db:
            result = self.db.execute(
                """UPDATE incoming_updates SET state=?,owner=NULL,
                   lease_until=0,due=? WHERE update_id=? AND owner=? AND state='leased'""",
                ("done" if success else "pending",
                 now if success else now + delay, item["update_id"], item["owner"]),
            )
            return result.rowcount == 1

    def complete_with_replies(self, item, replies, now=None):
        """Atomically persist queued replies and complete a fenced inbox claim.

        Requires DeliveryOutbox to use the same SQLite database file.
        Returns False for a stale claim without enqueuing any reply.
        """
        now = time.time() if now is None else float(now)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            owned = self.db.execute(
                """SELECT 1 FROM incoming_updates WHERE update_id=? AND
                   owner=? AND state='leased' AND lease_until>?""",
                (item["update_id"], item["owner"], now),
            ).fetchone()
            if not owned:
                self.db.execute("ROLLBACK")
                return False
            for index, (method, payload) in enumerate(replies, 1):
                if method not in ("sendMessage", "answerCallbackQuery"):
                    raise ValueError("unsupported transactional reply method")
                self.db.execute(
                    """INSERT OR IGNORE INTO deliveries(delivery_key,method,payload)
                       VALUES (?,?,?)""",
                    (f'{item["update_id"]}:{index}', method,
                     json.dumps(payload, ensure_ascii=False)),
                )
            self.db.execute(
                """UPDATE incoming_updates SET state='done',owner=NULL,
                   lease_until=0,due=? WHERE update_id=? AND owner=?""",
                (now, item["update_id"], item["owner"]),
            )
            self.db.execute("COMMIT")
            return True
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def close(self):
        self.db.close()
