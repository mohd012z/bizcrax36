"""Deterministic, side-effect-free business research and content draft engine."""
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re

TRACKING = {"fbclid", "gclid", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}

def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError("Only absolute HTTP(S) source URLs are accepted")
    host = parts.hostname.lower()
    port = f":{parts.port}" if parts.port else ""
    path = parts.path.rstrip("/") or "/"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING))
    return urlunsplit((parts.scheme.lower(), host + port, path, query, ""))

@dataclass(frozen=True)
class Evidence:
    title: str
    url: str
    summary: str

    def __post_init__(self):
        if not self.title.strip() or not self.summary.strip():
            raise ValueError("Evidence requires a title and summary")
        canonical_url(self.url)

def deduplicate(items: list[Evidence]) -> list[Evidence]:
    seen = set()
    output = []
    for item in items:
        key = canonical_url(item.url)
        if key not in seen:
            output.append(item)
            seen.add(key)
    return output

def score_opportunity(demand: int, feasibility: int, competition: int, confidence: int) -> int:
    """Four integer inputs 0..5; higher competition reduces the result."""
    values = (demand, feasibility, competition, confidence)
    if any(type(v) is not int or not 0 <= v <= 5 for v in values):
        raise ValueError("Scores must be integers between 0 and 5")
    return 5 * demand + 5 * feasibility + 5 * (5 - competition) + 5 * confidence

def draft_campaign(product: str, audience: str, evidence: list[Evidence]) -> dict:
    product, audience = product.strip(), audience.strip()
    if not product or not audience:
        raise ValueError("Product and audience are required")
    unique = deduplicate(evidence)
    if not unique:
        raise ValueError("At least one source is required")
    source_ids = [sha256(canonical_url(e.url).encode()).hexdigest()[:12] for e in unique]
    return {
        "status": "pending_human_review",
        "publish_allowed": False,
        "headline": f"Explore {product}",
        "body": f"Discover whether {product} fits the needs of {audience}. Review the sources before making any product claims.",
        "source_ids": source_ids,
        "sources": [{"id": i, "title": e.title, "url": canonical_url(e.url), "summary": e.summary} for i, e in zip(source_ids, unique)],
    }
