"""Agentic Research V2 — multi-round discovery, source verification, 0-100 scoring.

Evidence-first by design:
- Round 1 discovers candidate leads from public news feeds (headline discovery).
- Round 2 runs deterministic gap queries (competition, pricing, regulation).
- Verification fetches the source page and requires a title/reference match;
  a retrieved page is never treated as proof of commercial demand.
- Every scored metric carries a basis: "evidence" (from retrieved data) or
  "assumed" (neutral heuristic). The weighted total is a preliminary ranking,
  not a profitability claim.
"""
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

CAPITAL_BANDS = (
    ("micro", 0, 10_000),
    ("small", 10_000, 250_000),
    ("medium", 250_000, 2_000_000),
    ("large", 2_000_000, None),
)
BAND_NAMES = tuple(name for name, _, _ in CAPITAL_BANDS)

WEIGHTS = {
    "demand": 25,
    "unit_economics": 15,
    "competition": 15,
    "capital_accessibility": 15,
    "operational_feasibility": 15,
    "regulatory_readiness": 15,
}

TOPICS = {
    "digital": ("SME automation", "AI services", "cybersecurity"),
    "energy": ("energy efficiency", "solar maintenance", "green technology"),
    "aerospace": ("aviation training", "aircraft maintenance", "aerospace supply chain"),
    "manufacturing": ("industrial automation", "semiconductor suppliers", "equipment maintenance"),
    "tourism": ("tourism services", "hospitality technology", "visitor experience"),
    "agriculture": ("agritech", "food processing", "cold chain"),
}
BAND_TERMS = {
    "micro": "low startup cost",
    "small": "affordable startup investment",
    "medium": "small business expansion investment",
    "large": "large scale investment opportunity",
    "all": "",
}
STOP = {"the", "and", "for", "with", "from", "business", "opportunities", "opportunity",
        "find", "search", "research", "high", "potential", "in", "a", "an", "any", "sector"}

SCHEMA_VERSION = 2


def detect_sector(words):
    """Pick the sector whose terms best match the topic words.

    Max-match scoring instead of first-hit: a full multi-word term match
    (e.g. 'cold chain') outweighs a single shared word, so 'agritech cold
    chain' maps to agriculture, not aerospace ('...supply chain'). An exact
    sector name in the topic wins outright. Ties keep the earlier sector.
    """
    word_set = set(words)
    best_key, best_score = "general", 0
    for key, terms in TOPICS.items():
        score = 0
        if key in word_set:
            score += 10
        for term in terms:
            twords = set(term.lower().split())
            hit = len(twords & word_set)
            if hit:
                score += 3 if hit == len(twords) else hit
        if score > best_score:
            best_key, best_score = key, score
    return best_key


def plan(query, country="Malaysia", capital="all", max_queries=6):
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2 and w not in STOP]
    if not words:
        raise ValueError("A specific research topic is required")
    if capital not in BAND_NAMES and capital != "all":
        raise ValueError("capital must be one of %s, all" % (", ".join(BAND_NAMES),))
    topic = " ".join(words[:8])
    sector = detect_sector(words)
    demand = [
        "%s %s market demand" % (topic, country),
        "%s %s SME supplier opportunities" % (topic, country),
        "%s %s government programme" % (topic, country),
        "%s %s procurement tender" % (topic, country),
    ]
    if sector in TOPICS:
        demand.append("%s %s business" % (TOPICS[sector][0], country))
    if BAND_TERMS[capital]:
        demand.append("%s %s %s" % (topic, country, BAND_TERMS[capital]))
    gaps = {
        "competition": "%s %s competitors pricing" % (topic, country),
        "regulation": "%s %s licence registration requirement" % (topic, country),
        "demand_evidence": "%s %s customer demand survey" % (topic, country),
    }
    return {
        "query": query, "country": country, "capital": capital, "sector": sector,
        "rounds": [demand[:max_queries], list(gaps.values())],
    }


def band_of(amount):
    for name, low, high in CAPITAL_BANDS:
        if amount >= low and (high is None or amount < high):
            return name
    return CAPITAL_BANDS[-1][0]


def normalize_link(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    if host.endswith(".local") or host in {"localhost", "127.0.0.1"}:
        return None
    return url.split("#", 1)[0]


def discover(subquery, fetch=None, limit=10, when=None):
    """Fetch public Google News RSS headlines. Headline discovery is NOT verification."""
    params = {"q": subquery, "hl": "en-MY", "gl": "MY", "ceid": "MY:en"}
    if when:
        params["when"] = when
    url = "https://news.google.com/rss/search?" + urlencode(params)
    getter = fetch

    def default_get(target):
        req = Request(target, headers={"User-Agent": "BizCrax36ResearchV2/1.0"})
        with urlopen(req, timeout=12) as response:
            return response.read(1_000_000)

    if getter is None:
        getter = default_get
    root = ElementTree.fromstring(getter(url))
    items = []
    for item in root.findall(".//channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = normalize_link((item.findtext("link") or "").strip())
        if title and link:
            items.append({
                "title": title[:240], "source_url": link,
                "published_at": item.findtext("pubDate"),
                "discovery_query": subquery, "source_type": "news_rss",
                "status": "review_required",
            })
    return items


def discover_round(subqueries, fetch=None, limit=10, workers=4, when=None):
    """Run a discovery round in parallel; per-query failures are recorded, not fatal."""
    if len(subqueries) == 1:
        found, errors = [], []
        for sq in subqueries:
            try:
                found.extend(discover(sq, fetch=fetch, limit=limit, when=when))
            except (OSError, ValueError, ElementTree.ParseError) as exc:
                errors.append({"subquery": sq, "error": type(exc).__name__})
        return found, errors
    found, errors = [], []

    def run(sq):
        try:
            return discover(sq, fetch=fetch, limit=limit, when=when), None
        except (OSError, ValueError, ElementTree.ParseError) as exc:
            return None, {"subquery": sq, "error": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for items, err in pool.map(run, subqueries):
            if err:
                errors.append(err)
            elif items:
                found.extend(items)
    return found, errors


def _visible_words(html):
    text = re.sub(r"(?is)<(script|style|noscript|head)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def verify(candidate, fetch=None):
    """Fetch the source page; verify = a meaningful share of the headline's words is present."""
    url = candidate.get("source_url")
    if not url:
        return {"verified": False, "reason": "no_source_url"}
    getter = fetch

    def default_page(target):
        req = Request(target, headers={"User-Agent": "BizCrax36ResearchV2/1.0"})
        with urlopen(req, timeout=12) as response:
            return response.read(2_000_000).decode("utf-8", errors="replace")

    if getter is None:
        getter = default_page
    head = re.findall(r"[a-z0-9]{4,}", candidate["title"].lower())
    if len(head) < 3:
        return {"verified": False, "reason": "title_too_short_to_verify"}
    page = _visible_words(getter(url))
    matched = sum(1 for w in head if w in page)
    ratio = matched / float(len(head))
    return {
        "verified": ratio >= 0.6,
        "match_ratio": round(ratio, 3),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(url.encode()).hexdigest()[:20],
        "reason": "title_words_present" if ratio >= 0.6 else "insufficient_title_match",
    }


def _age_hours(candidate):
    raw = candidate.get("published_at")
    if not raw:
        return None
    try:
        published = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600.0)


def score(candidate, terms, capital, gap_hits, verified_count):
    """Weighted 0-100. Each metric: value, basis, note. Assumptions are labeled."""
    title = candidate["title"].lower()
    matches = sum(1 for t in terms if t in title)
    demand = min(100, 20 + matches * 18 + verified_count * 10)
    if matches or verified_count:
        demand_basis, demand_note = "evidence", "%d headline term matches, %d verified sources" % (matches, verified_count)
    else:
        demand_basis, demand_note = "assumed", "no demand terms in headline; neutral low score"
        demand = 20
    age = _age_hours(candidate)
    if age is not None:
        demand = int(max(0, min(100, demand + (15 if age <= 72 else 5))))
        demand_note += "; published %.0fh ago" % age
    comp_hits = gap_hits.get("competition", 0)
    if comp_hits:
        competition = max(10, 90 - comp_hits * 15)
        comp_basis = "evidence"
    else:
        competition, comp_basis = 40, "assumed"
    reg_hits = gap_hits.get("regulation", 0)
    if reg_hits:
        regulatory = max(20, 80 - reg_hits * 10) + 10
        reg_basis = "evidence"
    else:
        regulatory, reg_basis = 50, "assumed"
    regulatory = min(100, regulatory)
    if capital in ("micro", "small"):
        capital_score, capital_note = 85, "low capital band accessible to SMEs (assumed fit)"
    elif capital == "medium":
        capital_score, capital_note = 65, "medium band; funding gap likely (assumed)"
    else:
        capital_score, capital_note = 45, "large band; project financing typically required (assumed)"
    capital_basis = "assumed"
    metrics = {
        "demand": {"value": demand, "basis": demand_basis, "note": demand_note},
        "unit_economics": {"value": 40, "basis": "assumed",
                           "note": "no pricing evidence retrieved; run /blueprint financial model with real quotes"},
        "competition": {"value": competition, "basis": comp_basis,
                        "note": "%d competition/pricing headlines in round 2" % comp_hits},
        "capital_accessibility": {"value": capital_score, "basis": capital_basis, "note": capital_note},
        "operational_feasibility": {"value": 50, "basis": "assumed",
                                    "note": "neutral until operations, staffing and equipment are researched"},
        "regulatory_readiness": {"value": regulatory, "basis": reg_basis,
                                 "note": "%d licence/registration headlines in round 2" % reg_hits},
    }
    total = int(round(sum(WEIGHTS[k] * metrics[k]["value"] for k in WEIGHTS) / 100.0))
    total = max(0, min(100, total))
    return {"total": total, "metrics": metrics, "weights": WEIGHTS,
            "score_type": "weighted_preliminary",
            "currency": "MYR",
            "capital_band": capital}


def _fingerprint(title):
    return hashlib.sha256(title.casefold().strip().encode()).hexdigest()[:20]


def research(query, country="Malaysia", capital="all", fetch=None,
             max_queries=6, verify_top=3, workers=4, on_stage=None, verify_fetch=None,
             when="30d"):
    def stage(name):
        if on_stage:
            on_stage(name)
    task = plan(query, country, capital, max_queries)
    terms = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP and len(w) > 2]
    seen, candidates, errors = set(), [], []
    stage("researching")
    round1, round1_errors = discover_round(task["rounds"][0], fetch=fetch, workers=workers, when=when)
    errors.extend(round1_errors)
    round2, round2_errors = discover_round(task["rounds"][1], fetch=fetch, workers=workers, when=when)
    errors.extend(round2_errors)
    gap_hits = {
        "competition": sum(1 for r in round2 if r["discovery_query"] == task["rounds"][1][0]),
        "regulation": sum(1 for r in round2 if r["discovery_query"] == task["rounds"][1][1]),
    }
    for record in round1 + round2:
        if "gap_query" in record or record["discovery_query"] in task["rounds"][1]:
            record["gap_query"] = True
        fingerprint = _fingerprint(record["title"])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        record["id"] = fingerprint
        candidates.append(record)
    candidates.sort(key=lambda x: (
        -sum(1 for t in terms if t in x["title"].lower()),
        x.get("published_at") or "", x["title"]))
    stage("verifying")
    for record in candidates[:verify_top]:
        try:
            record["verification"] = verify(record, fetch=verify_fetch)
        except (OSError, ValueError) as exc:
            record["verification"] = {"verified": False, "reason": type(exc).__name__}
    verified_by_title = {}
    for record in candidates:
        v = record.get("verification") or {}
        if v.get("verified"):
            verified_by_title[record["id"]] = True
    stage("scoring")
    for record in candidates:
        verified_count = sum(1 for other in candidates
                             if other["title"].casefold() in (record["title"].casefold(),)
                             and verified_by_title.get(other["id"]))
        if record.get("verification", {}).get("verified"):
            verified_count = max(verified_count, 1)
        record["score"] = score(record, terms, capital, gap_hits, verified_count)
        record.setdefault("status", "review_required")
    candidates.sort(key=lambda x: (-x["score"]["total"], -(1 if x.get("verification", {}).get("verified") else 0), x["title"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": task,
        "candidates": candidates,
        "errors": errors,
        "gap_hits": gap_hits,
        "notice": "Research leads only. Headlines and heuristic scores do not prove business "
                  "viability, open tenders, or verified demand. Every lead stays review_required "
                  "until issuer and commercial evidence is independently confirmed.",
    }
