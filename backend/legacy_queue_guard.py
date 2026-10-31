"""Fail-closed guard for pending legacy Telegram queues.

A completed, backup-first migration leaves the legacy databases in place.
Allow startup only when every legacy row is preserved in the unified queue
and its pre-migration backup matches the original byte-for-byte at row level.
Unified processing state may advance after migration, so compare immutable
message identity and payload rather than mutable lease/status columns.
"""
import sqlite3
from pathlib import Path


class LegacyQueuePending(RuntimeError):
    pass


_SOURCES = (
    ("telegram_inbox.sqlite3", "incoming_updates", "update_id",
     ("update_id", "payload")),
    ("telegram_outbox.sqlite3", "deliveries", "delivery_key",
     ("delivery_key", "method", "payload")),
)


def _readonly(path):
    try:
        return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise LegacyQueuePending(
            f"Cannot open queue {path.name}: {type(exc).__name__}"
        ) from exc


def _verify_migration(source, backup, unified, table, key, identity):
    """Check complete legacy backup and identity-preserving unified copy."""
    with _readonly(backup) as saved, _readonly(unified) as target:
        old_rows = source.execute(f"SELECT * FROM {table} ORDER BY {key}")
        backup_rows = saved.execute(f"SELECT * FROM {table} ORDER BY {key}")
        old_columns = tuple(column[0] for column in old_rows.description)
        backup_columns = tuple(column[0] for column in backup_rows.description)
        if old_columns != backup_columns:
            raise LegacyQueuePending(f"Legacy backup schema differs: {table}")
        identity_indexes = tuple(old_columns.index(column) for column in identity)
        lookup = (f"SELECT {','.join(identity)} FROM {table} "
                  f"WHERE {key}=?")
        key_index = old_columns.index(key)
        for row in old_rows:
            if backup_rows.fetchone() != row:
                raise LegacyQueuePending(f"Legacy backup differs: {table}")
            actual = target.execute(lookup, (row[key_index],)).fetchone()
            expected = tuple(row[index] for index in identity_indexes)
            if actual != expected:
                raise LegacyQueuePending(
                    f"Unified queue missing or changed legacy record: {table}"
                )
        if backup_rows.fetchone() is not None:
            raise LegacyQueuePending(f"Legacy backup has extra records: {table}")


def check_legacy_queues(directory, *, unified_name="telegram_queue.sqlite3"):
    directory = Path(directory)
    unified = directory / unified_name
    pending = {}
    for filename, table, key, identity in _SOURCES:
        path = directory / filename
        if not path.exists():
            continue
        try:
            with _readonly(path) as source:
                count = source.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    "WHERE state NOT IN ('done','sent')"
                ).fetchone()[0]
                if not count:
                    continue
                backup = path.with_suffix(path.suffix + ".pre-migration.bak")
                if not unified.is_file() or not backup.is_file():
                    pending[filename] = count
                    continue
                _verify_migration(source, backup, unified, table, key, identity)
        except sqlite3.Error as exc:
            raise LegacyQueuePending(
                f"Cannot safely inspect legacy queue {filename}: "
                f"{type(exc).__name__}"
            ) from exc
        except (IndexError, ValueError) as exc:
            raise LegacyQueuePending(
                f"Legacy queue schema mismatch: {filename}"
            ) from exc
    if pending:
        summary = ", ".join(
            f"{name}={count}" for name, count in sorted(pending.items())
        )
        raise LegacyQueuePending(
            "Legacy Telegram queue contains unresolved work (" + summary +
            "). Stop consumers, back up and reconcile before starting unified queue."
        )
    return True
