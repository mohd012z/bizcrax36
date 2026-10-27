"""Fail-closed filtering for public opportunity records.
Only records with issuer-confirmed open status and a future timezone-aware deadline
may appear in the default live results. Unknown or undated records are review-only.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def parse_deadline(value, timezone_name="Asia/Kuala_Lumpur"):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, KeyError):
        return None

def status(record, now=None, max_age_hours=24):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    deadline = parse_deadline(record.get("closing_at"), record.get("timezone", "Asia/Kuala_Lumpur"))
    if deadline is None:
        return "review_required"
    if now >= deadline:
        return "expired"
    verified = record.get("verification_status") == "issuer_verified"
    observed = parse_deadline(record.get("last_verified_at"), "UTC")
    if not verified or observed is None or observed > now:
        return "review_required"
    if (now - observed).total_seconds() > max_age_hours * 3600:
        return "stale"
    if record.get("issuer_status") != "open":
        return "review_required"
    if not record.get("source_url") or not record.get("reference"):
        return "review_required"
    return "live"

def search(records, query="", sector="", region="", min_value=None, max_value=None, now=None):
    result = []
    query = query.casefold().strip()
    for record in records:
        if status(record, now) != "live":
            continue
        haystack = " ".join(str(record.get(k, "")) for k in ("title", "issuer", "reference", "description")).casefold()
        if query and query not in haystack:
            continue
        if sector and record.get("sector") != sector:
            continue
        if region and record.get("region") != region:
            continue
        value = record.get("value")
        if min_value is not None or max_value is not None:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            if min_value is not None and value < min_value:
                continue
            if max_value is not None and value > max_value:
                continue
        result.append(record)
    return sorted(result, key=lambda r: parse_deadline(r["closing_at"], r.get("timezone", "Asia/Kuala_Lumpur")))
