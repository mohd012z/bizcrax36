"""Offline, backup-first migration of legacy Telegram SQLite queues.

Run only with all Telegram consumers stopped. No live deployment is performed.
"""
import shutil
import sqlite3
from pathlib import Path


def migrate_legacy_queues(directory, *, dry_run=True):
    directory = Path(directory)
    target = directory / "telegram_queue.sqlite3"
    sources = [
        (directory / "telegram_inbox.sqlite3", "incoming_updates",
         "update_id,payload,state,attempts,owner,lease_until,due"),
        (directory / "telegram_outbox.sqlite3", "deliveries",
         "id,delivery_key,method,payload,state,attempts,due,owner,lease_until"),
    ]
    plan = {}
    for path, table, columns in sources:
        if not path.exists():
            continue
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            db.execute(f"SELECT {columns} FROM {table} LIMIT 0")
            plan[path.name] = count
        finally:
            db.close()
    if dry_run or not plan:
        return {"dry_run": True, "sources": plan, "migrated": 0}
    if target.exists():
        raise RuntimeError("Unified queue already exists; refusing to overwrite or merge")
    backups = []
    for path, _, _ in sources:
        if path.name not in plan:
            continue
        backup = path.with_suffix(path.suffix + ".pre-migration.bak")
        if backup.exists():
            raise RuntimeError(f"Backup already exists: {backup.name}")
        src = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        dst = sqlite3.connect(backup)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        backups.append(backup)
    from backend.delivery_outbox import DeliveryOutbox
    from backend.update_inbox import UpdateInbox
    outbox = DeliveryOutbox(target)
    inbox = UpdateInbox(target)
    outbox.close()
    inbox.close()
    dest = sqlite3.connect(target)
    try:
        dest.execute("BEGIN IMMEDIATE")
        for path, table, columns in sources:
            if path.name not in plan:
                continue
            source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                rows = source.execute(f"SELECT {columns} FROM {table}").fetchall()
            finally:
                source.close()
            names = columns.split(",")
            placeholders = ",".join("?" for _ in names)
            dest.executemany(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", rows
            )
            copied = dest.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if copied != len(rows):
                raise RuntimeError(f"Count mismatch in {table}")
        dest.commit()
    except BaseException:
        dest.rollback()
        dest.close()
        target.unlink(missing_ok=True)
        raise
    finally:
        try:
            dest.close()
        except Exception:
            pass
    return {"dry_run": False, "sources": plan,
            "migrated": sum(plan.values()), "backups": [str(p) for p in backups]}
