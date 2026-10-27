"""Read-only local API for BizCrax36 audited opportunities.

Start: python -m backend.search_api --database data/research.sqlite3
GET /api/health
GET /api/opportunities?q=...&sector=...&region=...&status=live|review|all
No CORS wildcard; intended for same-origin deployment behind an authenticated proxy.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit
from backend.opportunity_filter import status as opportunity_status
from backend.global_search import search_global
from backend.unified_search import one_search

def load_records(dbpath):
    if not dbpath.exists():
        return []
    with sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT record_json FROM research_records ORDER BY checked_at DESC LIMIT 10000"
        ).fetchall()
    unique = {}
    for (payload,) in rows:
        try:
            record = json.loads(payload)
            key = (record.get("source_url"), record.get("reference"))
            if key not in unique:
                unique[key] = record
        except (ValueError, TypeError):
            continue
    return list(unique.values())

def query_records(records, params, now=None):
    now = now or datetime.now(timezone.utc)
    requested = params.get("status", ["live"])[0]
    if requested not in ("live", "review", "all"):
        raise ValueError("invalid status")
    q = params.get("q", [""])[0].casefold().strip()
    sector = params.get("sector", [""])[0].casefold().strip()
    region = params.get("region", [""])[0].casefold().strip()
    output = []
    for record in records:
        state = opportunity_status(record, now)
        if requested == "live" and state != "live":
            continue
        if requested == "review" and state == "live":
            continue
        haystack = " ".join(str(record.get(k,"")) for k in ("title","issuer","reference","description")).casefold()
        if q and q not in haystack:
            continue
        if sector and str(record.get("sector","")).casefold() != sector:
            continue
        if region and str(record.get("region","")).casefold() != region:
            continue
        # Never return untrusted internal notes or raw source HTML.
        fields = ("title","issuer","reference","source_url","closing_at","last_verified_at",
                  "verification_status","issuer_status","sector","region","value","currency")
        item = {k:record.get(k) for k in fields}
        item["display_status"] = state
        output.append(item)
    return {"count":len(output),"results":output,"generated_at":now.isoformat(),
            "notice":"Live means issuer-verified within configured freshness window; not guaranteed real-time."}

def make_handler(database):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path)
            if path.path in ("/", "/index.html"):
                html_path=Path(__file__).resolve().parent.parent / "index.html"
                if not html_path.exists():
                    return self.respond(404, {"error":"dashboard_missing"})
                data=html_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Cache-Control","no-store")
                self.send_header("X-Content-Type-Options","nosniff")
                self.send_header("Content-Length",str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path.path not in ("/api/health", "/api/opportunities", "/api/global-opportunities", "/api/search"):
                return self.respond(404, {"error":"not_found"})
            if path.path == "/api/health":
                return self.respond(200, {"status":"ok","database_exists":database.exists()})
            try:
                params=parse_qs(path.query,keep_blank_values=True)
                if path.path == "/api/search":
                    ideas_path=Path(__file__).resolve().parent.parent / "data/business_ideas.json"
                    ideas=json.loads(ideas_path.read_text(encoding="utf-8")) if ideas_path.exists() else []
                    extra_path=Path(__file__).resolve().parent.parent / "data/web_research_ideas.json"
                    if extra_path.exists():
                        extras=json.loads(extra_path.read_text(encoding="utf-8"))
                        seen={(x.get("title","").casefold(),x.get("country","").casefold()) for x in ideas}
                        ideas.extend(x for x in extras if (x.get("title","").casefold(),x.get("country","").casefold()) not in seen)
                    data=one_search(load_records(database),ideas,query=params.get("q",[""])[0],
                        country=params.get("country",[""])[0],sector=params.get("sector",[""])[0],
                        mode=params.get("mode",["all"])[0])
                elif path.path == "/api/global-opportunities":
                    data=search_global(load_records(database),query=params.get("q",[""])[0],
                        country=params.get("country",[""])[0],kind=params.get("type",[""])[0],
                        status=params.get("status",["live"])[0])
                else:
                    data=query_records(load_records(database),params)
                self.respond(200,data)
            except (ValueError, sqlite3.Error) as exc:
                self.respond(400,{"error":"invalid_query_or_database","detail":str(exc)[:120]})
        def respond(self,code,payload):
            data=json.dumps(payload,ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    return Handler

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--database",type=Path,default=Path("data/research.sqlite3"))
    parser.add_argument("--host",default="127.0.0.1")
    parser.add_argument("--port",type=int,default=8765)
    args=parser.parse_args()
    ThreadingHTTPServer((args.host,args.port),make_handler(args.database)).serve_forever()
