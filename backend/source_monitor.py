"""BizCrax36 official-source monitor. Python 3.10+, stdlib only.
Does not claim that a changed page contains a new tender. Never bypasses access controls.
"""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import urllib.error
import urllib.request
from html.parser import HTMLParser

SOURCES = {
    "myprocurement_tender": "https://myprocurement.treasury.gov.my/advertisements/tender",
    "myprocurement_quotation": "https://myprocurement.treasury.gov.my/advertisements/quotation",
    "mbip_procurement": "https://eperolehan2.mbip.gov.my/",
    "pdn_procurement": "https://pdn.gov.my/v2/tender/",
    "marii_procurement": "https://eproc.marii.my/eproc/tender/list",
}
class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(" ".join(data.split()))

def fetch(name, url, timeout=20):
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    record = {"source_id": name, "source_url": url, "retrieved_at_utc": now,
              "status": "fetch_failed", "verified_opportunities": 0}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BizCrax36-ResearchMonitor/0.1 (public-source audit)"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            mime = response.headers.get_content_type()
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("response exceeded 2MB limit")
            if mime not in ("text/html", "text/plain"):
                raise ValueError("unexpected content type: " + mime)
            charset = response.headers.get_content_charset() or "utf-8"
            decoded = raw.decode(charset, errors="replace")
            parser = Text()
            parser.feed(decoded)
            visible = " ".join(parser.parts)
            if len(visible) < 100:
                raise ValueError("too little visible content for verification")
            record.update(status="page_retrieved_unverified", http_status=response.status,
                          sha256=hashlib.sha256(raw).hexdigest(),
                          page_excerpt=visible[:1200], bytes=len(raw))
    except (urllib.error.URLError, TimeoutError, ValueError, UnicodeError, OSError) as exc:
        record["error"] = str(exc)[:300]
    return record

def run(output):
    previous = {}
    if output.exists():
        try:
            previous = {r["source_id"]: r for r in json.loads(output.read_text(encoding="utf-8"))["sources"]}
        except (ValueError, KeyError, TypeError):
            previous = {}
    rows = []
    for name, url in SOURCES.items():
        r = fetch(name, url)
        prior = previous.get(name, {})
        r["changed_since_last_successful_snapshot"] = (
            r.get("sha256") != prior.get("sha256")
            if r.get("sha256") and prior.get("sha256") else None
        )
        rows.append(r)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema_version": 1, "sources": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"retrieved": sum(r["status"] == "page_retrieved_unverified" for r in rows),
                      "failed": sum(r["status"] == "fetch_failed" for r in rows),
                      "verified_opportunities": 0, "output": str(output)}))
    return 0 if all(r["status"] == "page_retrieved_unverified" for r in rows) else 1

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=pathlib.Path, default=pathlib.Path("data/source-monitor.json"))
    args = p.parse_args()
    raise SystemExit(run(args.output))
