"""Evidence-first discovery and verification pipeline, stdlib only.

Imports candidate notices from a JSON file, independently checks the issuer page
when requested, and stores audit results in SQLite. Retrieval is not proof of
the notice: an exact reference and title must appear in the retrieved text.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from html.parser import HTMLParser

from backend.opportunity_filter import status as live_status

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.words = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if not self.skip:
            self.words.append(data)

def normalize(value):
    return " ".join(str(value).casefold().split())

def retrieve(url, timeout=15):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("HTTPS source required")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("embedded credentials or custom ports forbidden")
    # Caller must configure a trusted allowlist; prevents arbitrary URL fetching.
    allowed = {"myprocurement.treasury.gov.my", "www.eperolehan.gov.my",
               "eperolehan2.mbip.gov.my", "www.sc.com.my", "www.petronas.com",
               "www.ungm.org", "ted.europa.eu"}
    if parsed.hostname.lower() not in allowed:
        raise ValueError("source host not allowlisted")
    request = Request(url, headers={"User-Agent": "BizCrax36-Research/0.1"})
    with urlopen(request, timeout=timeout) as response:
        if urlparse(response.geturl()).hostname not in allowed:
            raise ValueError("redirected outside trusted hosts")
        if response.headers.get_content_type() != "text/html":
            raise ValueError("expected HTML source")
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("source too large")
        charset = response.headers.get_content_charset() or "utf-8"
    parser = VisibleText()
    parser.feed(raw.decode(charset, errors="replace"))
    return " ".join(parser.words), hashlib.sha256(raw).hexdigest()

def verify(candidate, fetch=retrieve, now=None):
    now = now or datetime.now(timezone.utc)
    result = dict(candidate)
    result["checked_at"] = now.isoformat()
    result["verification_status"] = "unverified"
    result["issuer_status"] = "unknown"
    result["last_verified_at"] = None
    result["verification_reason"] = ""
    url = candidate.get("source_url", "")
    reference = str(candidate.get("reference", "")).strip()
    title = str(candidate.get("title", "")).strip()
    if not (url and reference and title and candidate.get("closing_at")):
        result["verification_reason"] = "missing required fields"
        return result
    try:
        page, digest = fetch(url)
        result["source_sha256"] = digest
        text = normalize(page)
        if normalize(reference) not in text or normalize(title) not in text:
            result["verification_reason"] = "reference or title absent from source"
            return result
        # Presence alone cannot establish current issuer status.
        result["verification_status"] = "source_matched"
        result["verification_reason"] = "source text matched; issuer open status not independently confirmed"
    except Exception as exc:
        result["verification_reason"] = "source retrieval failed: " + str(exc)[:180]
    return result

def save(dbpath, records):
    dbpath.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(dbpath) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS research_records (
            source_url TEXT NOT NULL, reference TEXT NOT NULL,
            checked_at TEXT NOT NULL, verification_status TEXT NOT NULL,
            record_json TEXT NOT NULL,
            PRIMARY KEY (source_url, reference, checked_at))""")
        conn.executemany(
            "INSERT OR REPLACE INTO research_records VALUES (?,?,?,?,?)",
            [(r.get("source_url",""), str(r.get("reference","")), r["checked_at"],
              r["verification_status"], json.dumps(r, ensure_ascii=False)) for r in records])

def run(input_file, database, output):
    candidates = json.loads(input_file.read_text(encoding="utf-8"))
    if not isinstance(candidates, list):
        raise ValueError("input must be a JSON array")
    if len(candidates) > 500:
        raise ValueError("batch limit 500")
    records = [verify(c) for c in candidates]
    save(database, records)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"records": records, "live": [], "note":
        "No candidates marked live without independent issuer-open confirmation."},
        indent=2, ensure_ascii=False), encoding="utf-8")
    return records

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--database", type=Path, default=Path("data/research.sqlite3"))
    parser.add_argument("--output", type=Path, default=Path("data/discovery.json"))
    args = parser.parse_args()
    rows = run(args.input, args.database, args.output)
    print(f"checked={len(rows)} source_matched={sum(r['verification_status']=='source_matched' for r in rows)} verified_live=0")
