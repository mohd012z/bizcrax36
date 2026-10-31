"""Authenticated read-only operations snapshot API.

Runs as a standalone WSGI application. Configure OPS_SNAPSHOT_TOKEN in the
server environment; never expose it in a browser bundle. No mutation endpoints.
Optional OPS_SNAPSHOT_PATH points to a trusted JSON snapshot produced by a
separate server-side collector. Missing data is reported as unavailable.
"""
import hmac
import json
import os
from pathlib import Path
from urllib.parse import parse_qs

MAX_BYTES = 256 * 1024

def _response(start_response, code, payload, method="GET"):
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    start_response(code, [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Cache-Control", "no-store, private"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Security-Policy", "default-src 'none'"),
        ("Content-Length", str(len(body))),
    ])
    return [] if method == "HEAD" else [body]

def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "")
    if path != "/api/ops/snapshot":
        return _response(start_response, "404 Not Found", {"error":"not_found"}, method)
    if method not in ("GET", "HEAD"):
        return _response(start_response, "405 Method Not Allowed", {"error":"method_not_allowed"}, method)
    expected = os.environ.get("OPS_SNAPSHOT_TOKEN", "")
    auth = environ.get("HTTP_AUTHORIZATION", "")
    prefix = "Bearer "
    if not expected or not auth.startswith(prefix) or not hmac.compare_digest(auth[len(prefix):], expected):
        return _response(start_response, "401 Unauthorized", {"error":"unauthorized"}, method)
    file_path = os.environ.get("OPS_SNAPSHOT_PATH", "")
    if not file_path:
        return _response(start_response, "503 Service Unavailable", {"error":"snapshot_not_configured"}, method)
    try:
        source = Path(file_path)
        if not source.is_file() or source.stat().st_size > MAX_BYTES:
            raise ValueError("snapshot_unavailable")
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or any(not isinstance(data.get(k), list) for k in ("jobs", "logs", "quotas")):
            raise ValueError("invalid_snapshot")
        counts = data.get("counts", {})
        if not isinstance(counts, dict):
            raise ValueError("invalid_counts")
        # Explicit allowlist prevents accidental disclosure of internal fields.
        clean = {
            "counts": {k:counts[k] for k in ("queued","running","failed","completed") if type(counts.get(k)) is int and counts[k] >= 0},
            "jobs": [{k:v for k,v in j.items() if k in ("id","status","stage","attempts","updated_at") and isinstance(v,(str,int)) and type(v) is not bool} for j in data["jobs"][:50] if isinstance(j,dict)],
            "logs": [{k:v for k,v in j.items() if k in ("level","code","timestamp","job_id") and isinstance(v,str)} for j in data["logs"][:50] if isinstance(j,dict)],
            "quotas": [{k:v for k,v in j.items() if k in ("name","used","limit","reset_at") and isinstance(v,(str,int,float)) and type(v) is not bool} for j in data["quotas"][:50] if isinstance(j,dict)]
        }
        return _response(start_response, "200 OK", clean, method)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return _response(start_response, "503 Service Unavailable", {"error":"snapshot_unavailable"}, method)
