"""Evidence-first, no-paid-API opportunity research (candidate discovery, not tender verification)."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

TOPICS = {
    "digital": ("SME automation", "AI services", "cybersecurity"),
    "energy": ("energy efficiency", "solar maintenance", "green technology"),
    "aerospace": ("aviation training", "aircraft maintenance", "aerospace supply chain"),
    "manufacturing": ("industrial automation", "semiconductor suppliers", "equipment maintenance"),
    "tourism": ("tourism services", "hospitality technology", "visitor experience"),
    "agriculture": ("agritech", "food processing", "cold chain"),
}
WEIGHTS = {"demand": 25, "feasibility": 20, "evidence": 25, "freshness": 15, "competition": 15}
STOP = {"the", "and", "for", "with", "from", "business", "opportunities", "opportunity", "find", "search", "research", "high", "potential"}

def plan(query, country="Malaysia", max_queries=5):
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2 and w not in STOP]
    if not words:
        raise ValueError("A specific research topic is required")
    topic = " ".join(words[:8])
    sector = next((key for key, terms in TOPICS.items() if key in words or any(set(term.lower().split()) & set(words) for term in terms)), "general")
    variants = [f"{topic} {country} market demand", f"{topic} {country} SME supplier opportunities",
                f"{topic} {country} government programme", f"{topic} {country} procurement"]
    if sector in TOPICS:
        variants.append(f"{TOPICS[sector][0]} {country} business")
    return {"query": query, "country": country, "sector": sector, "subqueries": variants[:max_queries]}

def normalize_link(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if host.endswith(".local") or host in {"localhost", "127.0.0.1"}:
        return None
    return url.split("#", 1)[0]

def discover(subquery, fetch=None, limit=10):
    """Fetch public Google News RSS headlines. Headline discovery is NOT verification."""
    url = "https://news.google.com/rss/search?" + urlencode({"q": subquery, "hl": "en-MY", "gl": "MY", "ceid": "MY:en"})
    if fetch is None:
        def fetch(target):
            req = Request(target, headers={"User-Agent": "BizCrax36Research/1.0"})
            with urlopen(req, timeout=12) as response:
                return response.read(1_000_000)
    root = ElementTree.fromstring(fetch(url))
    items = []
    for item in root.findall(".//channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = normalize_link((item.findtext("link") or "").strip())
        if title and link:
            items.append({"title": title[:240], "source_url": link,
                          "published_at": item.findtext("pubDate"), "discovery_query": subquery,
                          "source_type": "news_rss", "status": "review_required"})
    return items

def score(candidate, terms):
    title = candidate["title"].lower()
    matches = sum(1 for term in terms if term in title)
    demand = min(25, matches * 8)
    evidence = 10 if candidate.get("source_url") else 0
    freshness = 5 if candidate.get("published_at") else 0
    feasibility = 10  # Neutral until business costs and requirements are researched.
    competition = 5  # Unknown: never imply competition has been measured.
    total = demand + evidence + freshness + feasibility + competition
    return {"total": total, "demand": demand, "evidence": evidence, "freshness": freshness,
            "feasibility": feasibility, "competition": competition, "score_type": "preliminary_heuristic"}

def research(query, country="Malaysia", fetch=None, max_queries=5):
    task = plan(query, country, max_queries)
    seen, candidates, errors = set(), [], []
    terms = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP and len(w) > 2]
    for subquery in task["subqueries"]:
        try:
            records = discover(subquery, fetch=fetch)
        except (OSError, ValueError, ElementTree.ParseError) as exc:
            errors.append({"subquery": subquery, "error": type(exc).__name__})
            continue
        for record in records:
            fingerprint = hashlib.sha256((record["title"].casefold().strip()).encode()).hexdigest()[:20]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            record["id"] = fingerprint
            record["score"] = score(record, terms)
            record["verification"] = {"issuer_confirmed": False, "commercial_demand_confirmed": False,
                                      "costs_confirmed": False, "deadline_confirmed": False}
            candidates.append(record)
    candidates.sort(key=lambda x: (-x["score"]["total"], x["title"]))
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
            "plan": task, "candidates": candidates, "errors": errors,
            "notice": "Research leads only. Headlines and heuristic scores do not prove business viability, open tenders, or verified demand."}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--country", default="Malaysia")
    parser.add_argument("--output", default="data/agentic_research.json")
    args = parser.parse_args()
    from pathlib import Path
    result = research(args.query, args.country)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"candidates": len(result["candidates"]), "errors": len(result["errors"]), "output": str(path)}))

if __name__ == "__main__":
    main()
