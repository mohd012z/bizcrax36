"""Minimal free-first Telegram reliability and document exchange helpers."""
import csv
import io
import json
import re
import sqlite3
from pathlib import Path

COMMANDS = [
    ("start", "Open main menu"), ("help", "Show commands"),
    ("research", "Research a business topic"), ("deepdive", "Investigate a lead"),
    ("verify", "Check evidence"), ("compare", "Compare leads"),
    ("status", "Check research status"), ("sources", "List research sources"),
    ("documents", "List research documents"), ("import", "Import JSON or CSV"),
    ("export", "Export JSON or CSV"), ("report", "Generate a report"),
]
FIELDS = ("id", "title", "source_url", "status")
ALLOWED_STATUS = {"research_hypothesis", "review_required", "source_verified", "rejected"}

def command_payload():
    return [{"command": c, "description": d} for c, d in COMMANDS]

def parse_command(text):
    match = re.match(r"^/([a-z][a-z0-9_]*)(?:@[A-Za-z0-9_]+)?(?:\s+(.*))?$", text.strip(), re.S)
    return (match.group(1), (match.group(2) or "").strip()) if match else (None, "")

def validate_record(row):
    if not isinstance(row, dict):
        raise ValueError("record must be an object")
    record = {key: str(row.get(key) or "").strip() for key in FIELDS}
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", record["id"]):
        raise ValueError("invalid id")
    if not 1 <= len(record["title"]) <= 240:
        raise ValueError("invalid title")
    if record["source_url"] and not re.fullmatch(r"https://[^\s/]+(?:/[^\s]*)?", record["source_url"]):
        raise ValueError("invalid HTTPS source URL")
    if record["status"] not in ALLOWED_STATUS:
        raise ValueError("invalid status")
    return record

def validate_rows(rows):
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("expected at most 1000 records")
    seen, output = set(), []
    for row in rows:
        item = validate_record(row)
        if item["id"] in seen:
            raise ValueError("duplicate id")
        seen.add(item["id"])
        output.append(item)
    return output

def import_data(content, extension):
    if len(content) > 2_000_000:
        raise ValueError("file too large")
    text = content.decode("utf-8-sig")
    if extension == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported JSON schema")
        return validate_rows(payload.get("records"))
    if extension == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or set(reader.fieldnames) != set(FIELDS):
            raise ValueError("CSV columns must match schema")
        return validate_rows(list(reader))
    raise ValueError("supported imports: .json and .csv")

def export_data(rows, extension):
    rows = validate_rows(rows)
    if extension == ".json":
        return (json.dumps({"schema_version": 1, "records": rows}, ensure_ascii=False, indent=2) + "\n").encode()
    if extension == ".csv":
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            # Prevent spreadsheet software interpreting imported text as formulas.
            writer.writerow({k: ("'" + v if v.lstrip().startswith(("=", "+", "-", "@")) else v)
                             for k, v in row.items()})
        return out.getvalue().encode()
    raise ValueError("supported exports: .json and .csv")

class UpdateLedger:
    """Durable update deduplication for a single polling/webhook consumer."""
    def __init__(self, filename):
        self.db = sqlite3.connect(str(filename), timeout=10)
        self.db.execute("CREATE TABLE IF NOT EXISTS processed_updates (update_id INTEGER PRIMARY KEY)")
        self.db.commit()

    def seen(self, update_id):
        return self.db.execute("SELECT 1 FROM processed_updates WHERE update_id=?", (int(update_id),)).fetchone() is not None

    def mark(self, update_id):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO processed_updates VALUES (?)", (int(update_id),))

    def close(self):
        self.db.close()
