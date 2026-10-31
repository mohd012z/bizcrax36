"""Fail-closed legacy queue guard before starting the unified Telegram worker.

Legacy inbox/outbox databases are never silently discarded. A nonempty legacy
queue requires an explicit, offline reconciliation before the worker starts.
"""
import sqlite3
from pathlib import Path


class LegacyQueuePending(RuntimeError):
    pass


def check_legacy_queues(directory, *, unified_name="telegram_queue.sqlite3"):
    directory = Path(directory)
    sources = (
        ("telegram_inbox.sqlite3", "incoming_updates"),
        ("telegram_outbox.sqlite3", "deliveries"),
    )
    pending = {}
    for filename, table in sources:
        path = directory / filename
        if not path.exists():
            continue
        # Read-only mode avoids creating or modifying legacy databases.
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE state NOT IN ('done','sent')"
            ).fetchone()[0]
            if count:
                pending[filename] = count
        except sqlite3.Error as exc:
            raise LegacyQueuePending(
                f"Cannot safely inspect legacy queue {filename}: {type(exc).__name__}"
            ) from exc
        finally:
            connection.close()
    if pending:
        summary = ", ".join(f"{name}={count}" for name, count in sorted(pending.items()))
        raise LegacyQueuePending(
            "Legacy Telegram queue contains unresolved work (" + summary +
            "). Stop consumers, back up databases and reconcile before starting unified queue."
        )
    return True
