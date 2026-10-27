"""BizCrax36 360 Command Center — local API + static web UI.

Start: python -m backend.web_api --port 8765
Serves:
  GET /                     → web/index.html (360° Command Center)
  GET /api/health           → liveness + version
  GET /api/research?topic=&capital=&country= → full V2 pipeline (same engine as Telegram)
  GET /api/jobs             → stored completed jobs
  GET /api/job/<id>         → stored job (result + dossier)
  GET /api/job/<id>/report  → stored DOCX report

Stdlib only. Optional WEB_API_TOKEN env adds a shared-secret header check
(X-BizCrax-Token) on /api/research so a public deployment is not open-ended.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from backend import research_v2
from backend.dossier import build as build_dossier, summary_text
from backend.research_queue import run_job, is_duplicate, validate_topic
from backend.reports import generate_report

BASE = Path(__file__).resolve().parent.parent
WEB_DIR = BASE / "web"
JOBS_DIR = BASE / "data" / "research-jobs"
SCHEMA_VERSION = research_v2.SCHEMA_VERSION


def load_job(job_id):
    if not job_id or len(job_id) != 12 or not all(c in "0123456789abcdef" for c in job_id.lower()):
        return None
    path = JOBS_DIR / job_id / "job.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def list_jobs(limit=20):
    jobs = []
    if not JOBS_DIR.exists():
        return jobs
    for path in sorted(JOBS_DIR.glob("*/job.json"), reverse=True):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if job.get("status") == "completed":
            jobs.append({k: job.get(k) for k in
                         ("id", "query", "country", "capital", "finished_at",
                          "duration_seconds", "diagnostics")})
        if len(jobs) >= limit:
            break
    return jobs


def run_research(topic, capital, country):
    """One V2 research run, persisted. Returns (job, result, dossier, report)."""
    clean_topic, _ = validate_topic(topic)
    if clean_topic is None:
        raise ValueError("topic required (1-120 chars)")
    if capital not in ("all",) + research_v2.BAND_NAMES:
        raise ValueError("invalid capital band")
    recent = is_duplicate(list_jobs(), clean_topic, capital, country=country, window_minutes=15)
    if recent is not None:
        result = recent.get("result") or _empty_result(clean_topic, capital, country)
        return recent, result, build_dossier(result), recent.get("report")
    job, result, dossier = run_job(clean_topic, country=country, capital=capital)
    if job["status"] != "completed" or result is None:
        raise OSError(job.get("error", "research_failed"))
    report = generate_report(dossier, result, JOBS_DIR / job["id"])
    _save_job(job, result, report, dossier)
    return job, result, dossier, report


def _empty_result(topic, capital, country):
    return {"schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "plan": {"query": topic, "country": country, "capital": capital, "sector": "general"},
            "candidates": [], "errors": [], "gap_hits": {}, "notice": ""}


def _save_job(job, result, report, dossier=None):
    d = JOBS_DIR / job["id"]
    d.mkdir(parents=True, exist_ok=True)
    payload = {"id": job["id"], "query": job["query"], "country": job["country"],
               "capital": job["capital"], "status": job["status"],
               "created_at": job["created_at"], "finished_at": job.get("finished_at"),
               "duration_seconds": job.get("duration_seconds"),
               "diagnostics": job.get("diagnostics"), "result": result, "report": report,
               "dossier": dossier}
    (d / "job.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def make_handler(database=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BizCrax36Web/2.0"

        def log_message(self, format, *args):
            pass  # keep the API quiet; errors surface in JSON

        def _send(self, code, payload, content_type="application/json; charset=utf-8", body=None):
            data = body if body is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self):
            token = os.environ.get("WEB_API_TOKEN", "")
            if not token:
                return True
            return self.headers.get("X-BizCrax-Token", "") == token

        def do_GET(self):
            path = urlsplit(self.path)
            seg = path.path
            if seg in ("/", "/index.html"):
                index = WEB_DIR / "index.html"
                if not index.exists():
                    return self._send(404, {"error": "web_ui_missing"})
                return self._send(200, None, "text/html; charset=utf-8", index.read_bytes())
            if seg.startswith("/assets/"):
                f = (WEB_DIR / seg.lstrip("/")).resolve()
                if WEB_DIR.resolve() in f.parents and f.exists():
                    ctype = {"png": "image/png", "svg": "image/svg+xml",
                             "css": "text/css; charset=utf-8",
                             "js": "application/javascript; charset=utf-8"}.get(f.suffix.lstrip("."), "application/octet-stream")
                    return self._send(200, None, ctype, f.read_bytes())
                return self._send(404, {"error": "not_found"})
            if seg == "/api/health":
                return self._send(200, {"status": "ok", "engine": "agentic-research-v2",
                                        "schema_version": SCHEMA_VERSION,
                                        "jobs_stored": len(list_jobs(999))})
            if seg == "/api/research":
                if not self._authorized():
                    return self._send(401, {"error": "token_required"})
                params = parse_qs(path.query, keep_blank_values=True)
                topic = (params.get("topic", [""])[0]).strip()
                capital = (params.get("capital", ["all"])[0]).strip().lower() or "all"
                country = (params.get("country", ["Malaysia"])[0]).strip() or "Malaysia"
                if capital not in ("all",) + research_v2.BAND_NAMES:
                    return self._send(400, {"error": "invalid_capital"})
                try:
                    job, result, dossier, report = run_research(topic, capital, country)
                except ValueError as exc:
                    return self._send(400, {"error": "bad_request", "detail": str(exc)})
                except (OSError, RuntimeError) as exc:
                    return self._send(502, {"error": "research_failed", "detail": str(exc)[:200]})
                return self._send(200, {"job": job, "result": result, "dossier": dossier,
                                        "report": report, "summary": summary_text(dossier, result)})
            if seg == "/api/jobs":
                return self._send(200, {"count": len(list_jobs()), "jobs": list_jobs()})
            if seg.startswith("/api/job/"):
                rest = seg[len("/api/job/"):]
                parts = rest.split("/")
                job_id = parts[0] if parts else ""
                job = load_job(job_id)
                if not job:
                    return self._send(404, {"error": "job_not_found"})
                if len(parts) == 2 and parts[1] == "report":
                    docx = JOBS_DIR / job_id / "report.docx"
                    if not docx.exists():
                        return self._send(404, {"error": "report_not_stored"})
                    return self._send(200, None,
                                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                      docx.read_bytes())
                if len(parts) == 3 and parts[1] == "chart":
                    name = parts[2]
                    if name not in ("scores.png", "metrics.png", "scenarios.png"):
                        return self._send(400, {"error": "invalid_chart"})
                    png = JOBS_DIR / job_id / "charts" / name
                    if not png.exists():
                        return self._send(404, {"error": "chart_not_stored"})
                    return self._send(200, None, "image/png", png.read_bytes())
                return self._send(200, job)
            return self._send(404, {"error": "not_found"})

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print("BizCrax36 360 Command Center: http://%s:%d/" % (args.host, args.port), flush=True)
    ThreadingHTTPServer((args.host, args.port), make_handler()).serve_forever()
