"""Staged research job runner: queued → researching → verifying → scoring → completed.

Diagnostics (stage timings, source errors, coverage) are explicit output so a
research run is auditable. No network access happens here; the research engine
and its fetch are injected.
"""
import hashlib
import re
import time
from datetime import datetime, timezone

from backend import research_v2
from backend.dossier import build as build_dossier


def job_id(query, capital, country):
    key = "%s|%s|%s" % (query.casefold().strip(), capital, country.casefold().strip())
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def is_duplicate(jobs, query, capital="all", country="Malaysia", window_minutes=15, now=None):
    """Return a recent job dict if the same research ran inside the window."""
    now = now or datetime.now(timezone.utc)
    want = job_id(query, capital, country)
    for job in jobs:
        if job.get("id") != want or job.get("status") != "completed":
            continue
        try:
            finished = datetime.fromisoformat(job["finished_at"])
        except (KeyError, ValueError):
            continue
        if (now - finished).total_seconds() <= window_minutes * 60:
            return job
    return None


def run_job(query, country="Malaysia", capital="all", fetch=None, verify_fetch=None,
            on_stage=None, max_queries=6, verify_top=3, workers=4):
    """Execute a full V2 research job and return (job, result, dossier)."""
    started = time.monotonic()
    job = {
        "id": job_id(query, capital, country),
        "query": query, "country": country, "capital": capital,
        "status": "queued", "stages": [], "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state = {"t0": started}

    def track(stage):
        state["last"] = time.monotonic()
        if job["stages"] and job["stages"][-1]["name"] == stage:
            return
        job["stages"].append({"name": stage, "at": state["last"] - state["t0"]})
        if stage == "researching":
            job["status"] = "researching"
        elif stage == "verifying":
            job["status"] = "verifying"
        elif stage == "scoring":
            job["status"] = "scoring"
        if on_stage:
            on_stage(stage)

    try:
        result = research_v2.research(query, country, capital, fetch=fetch,
                                      max_queries=max_queries, verify_top=verify_top,
                                      workers=workers, on_stage=track,
                                      verify_fetch=verify_fetch)
        dossier = build_dossier(result)
        track("completed")
        job["status"] = "completed"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        job["duration_seconds"] = round(time.monotonic() - started, 2)
        job["diagnostics"] = {
            "candidates": len(result["candidates"]),
            "source_verified": sum(1 for c in result["candidates"]
                                   if (c.get("verification") or {}).get("verified")),
            "source_errors": len(result.get("errors", [])),
            "gap_hits": result.get("gap_hits", {}),
            "top_score": result["candidates"][0]["score"]["total"] if result["candidates"] else None,
            "stages": [{"name": s["name"], "seconds": round(s["at"], 2)} for s in job["stages"]],
        }
        return job, result, dossier
    except (OSError, ValueError) as exc:
        job["status"] = "failed"
        job["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:160])
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        job["duration_seconds"] = round(time.monotonic() - started, 2)
        return job, None, None


def diagnostics_line(job):
    """One-line Telegram footer: stage timings + evidence counts."""
    d = job.get("diagnostics") or {}
    parts = ["⏱ %ss" % d.get("duration_seconds", "?")]
    if d.get("stages"):
        parts.append(" · ".join("%s %ss" % (s["name"], s["seconds"]) for s in d["stages"]))
    parts.append("%d leads" % d.get("candidates", 0))
    parts.append("%d source-verified" % d.get("source_verified", 0))
    if d.get("source_errors"):
        parts.append("%d source errors" % d.get("source_errors"))
    return " | ".join(parts)


def validate_topic(text):
    """Split a /research or /report command body into (topic, capital)."""
    text = (text or "").strip()
    tokens = text.split()
    if not tokens:
        return None, None
    last = tokens[-1].lower()
    if len(tokens) > 1 and last in research_v2.BAND_NAMES:
        topic, capital = " ".join(tokens[:-1]).strip(), last
    else:
        topic, capital = text, "all"
    topic = re.sub(r"\s+", " ", topic)
    if not topic or len(topic) > 120:
        return None, None
    return topic, capital
