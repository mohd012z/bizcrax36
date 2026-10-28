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
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlparse, parse_qs
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
    "food": ("food franchise", "franchise", "restaurant", "cafe", "bakery",
            "catering", "food and beverage", "f and b", "food service"),
    "agriculture": ("agritech", "food processing", "cold chain", "agriculture",
                   "farming", "crop", "livestock"),
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


PAYWALL_MARKERS = (
    "one membership. limitless possibilities", "subscribe to continue",
    "subscription required", "sign in to continue", "you have 0 of 5 free",
    "free article this month", "paywall", "content is locked",
    "register and continue your reading", "log in to access this article",
)
# Hosts that are paywalled even when marker text is absent (checked via page).
PAYWALL_HOSTS = {"forbes.com", "ft.com", "economist.com", "wsj.com",
                 "bloomberg.com", "nytimes.com", "financialtimes.com"}


def _paywall_check(html, host):
    """Best-effort paywall detection on a fetched page. Never raises."""
    low = html[:400000].lower()
    if any(m in low for m in PAYWALL_MARKERS):
        return True
    return any(host == h or host.endswith("." + h) for h in PAYWALL_HOSTS)


def resolve_link(url):
    """Best-effort: turn an opaque news.google.com wrapper into a direct
    publisher URL. Returns the original URL when it is already direct or
    resolution fails (the caller then marks it google_news_link)."""
    if not url or "news.google.com" not in url:
        return url
    m = re.search(r"/articles/([^?]+)", url)
    if not m:
        return url
    try:
        import base64
        raw = base64.urlsafe_b64decode(m.group(1) + "=" * (-len(m.group(1)) % 4))
        inner = re.findall(r"https?://[^\x00-\x1f\x7f-\x9f\"\\ ]+",
                           raw.decode("utf-8", "ignore"))
        if inner:
            return inner[0]
        au = raw[raw.index(b"AU_"):].decode("utf-8", "ignore")
        au = au[:au.rfind("\x00")].strip()
        payload = json.dumps([[[1, au]]], separators=(",", ":"))
        req = Request("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                      data=("f.req=" + urlencode(payload)).encode(),
                      headers={"User-Agent": "Mozilla/5.0",
                               "Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=8) as r:
            data = r.read(8000).decode("utf-8", "ignore")
        urls = re.findall(r'https?://(?!news\.google\.com)[^"\\ ]+', data)
        if urls:
            return urls[0]
    except Exception:
        pass
    return url


def discover_bing(subquery, fetch=None, limit=5):
    """Secondary discovery: Bing News RSS. Unwraps apiclick.aspx redirects to
    the real publisher URL, so leads get direct (often open) links."""
    import xml.etree.ElementTree as ET
    params = urlencode({"q": subquery}) + "&format=rss"
    url = "https://www.bing.com/news/search?" + params
    getter = fetch

    def default_get(target):
        req = Request(target, headers={"User-Agent": "BizCrax36ResearchV2/1.0 (bing)"})
        with urlopen(req, timeout=12) as response:
            return response.read(1_000_000)

    if getter is None:
        getter = default_get
    root = ET.fromstring(getter(url))
    items = []
    for item in root.findall(".//channel/item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if "apiclick.aspx" in link:
            qs = parse_qs(urlparse(link).query)
            direct = (qs.get("url") or [""])[0]
            if direct:
                link = direct
        link = normalize_link(link)
        if title and link:
            items.append({
                "title": title[:240], "source_url": link,
                "published_at": item.findtext("pubDate"),
                "discovery_query": subquery, "source_type": "bing_rss",
                "status": "review_required",
            })
    return items


def _visible_words(html):
    text = re.sub(r"(?is)<(script|style|noscript|head)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def verify(candidate, fetch=None):
    """Fetch the source page; verify = a meaningful share of the headline's words is present.
    Also detects paywalls so the report can say 'paid content' and offer a free route."""
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
    try:
        page_html = getter(url)
    except (OSError, ValueError) as exc:
        return {"verified": False, "reason": type(exc).__name__}
    page = _visible_words(page_html)
    host = (urlparse(url).hostname or "").lower()
    paywalled = _paywall_check(page_html, host)
    matched = sum(1 for w in head if w in page)
    ratio = matched / float(len(head))
    verified = ratio >= 0.6 and not paywalled
    out = {
        "verified": verified,
        "match_ratio": round(ratio, 3),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(url.encode()).hexdigest()[:20],
        "paywall": paywalled,
        "reason": ("paywalled_content" if paywalled else
                   "title_words_present" if verified else "insufficient_title_match"),
    }
    return out


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
             when="30d", with_evidence=True):
    def stage(name):
        if on_stage:
            on_stage(name)
    task = plan(query, country, capital, max_queries)
    terms = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP and len(w) > 2]
    seen, candidates, errors = set(), [], []
    stage("researching")
    # Skip sources that have repeatedly failed verification (DEAD_ENDS pattern).
    skip_hosts = set()
    try:
        from backend import agent_skill
        skip_hosts = agent_skill.blacklisted_hosts()
    except Exception:
        skip_hosts = set()
    round1, round1_errors = discover_round(task["rounds"][0], fetch=fetch, workers=workers, when=when)
    errors.extend(round1_errors)
    round2, round2_errors = discover_round(task["rounds"][1], fetch=fetch, workers=workers, when=when)
    errors.extend(round2_errors)
    # Always contribute a few direct publisher links from Bing News RSS, so every
    # report carries openable (often free) URLs alongside the Google News leads.
    # Dedup by title-fingerprint below removes near-duplicates automatically.
    bing_used = 0
    q2 = "%s %s" % (task.get("query") or query, country if country and country != "Global" else "")
    q2 = q2.strip()
    try:
        bing_extra = discover_bing(q2, fetch=fetch, limit=6)
        bing_used = len(bing_extra)
        round2 = list(round2) + bing_extra
    except (OSError, ValueError, ElementTree.ParseError):
        pass  # fail-open: Google News leads still stand; direct links are a bonus.
    gap_hits = {
        "competition": sum(1 for r in round2 if r["discovery_query"] == task["rounds"][1][0]),
        "regulation": sum(1 for r in round2 if r["discovery_query"] == task["rounds"][1][1]),
    }
    for record in round1 + round2:
        if "gap_query" in record or record["discovery_query"] in task["rounds"][1]:
            record["gap_query"] = True
        if skip_hosts and (urlparse(record.get("source_url") or "").hostname or "").lower() in skip_hosts:
            continue
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
    # Resolve opaque Google News wrapper URLs to direct publisher links, and
    # record which leads carry Google-redirected (possibly paywalled) URLs.
    for record in candidates:
        original = record.get("source_url") or ""
        resolved = resolve_link(original)
        record["source_url_resolved"] = resolved
        if resolved != original:
            record["source_url"] = resolved
            record["resolved_from_google"] = True
        elif "news.google.com" in original:
            record["google_news_link"] = True
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
    # Live macro/evidence context (fail-open; labeled evidence vs unavailable).
    evidence, evidence_errors = [], []
    if with_evidence:
        try:
            from backend import evidence_sources
            evidence, evidence_errors = evidence_sources.fetch_all(
                " ".join(terms[:6]), country, fetch=fetch, workers=4)
        except Exception:
            evidence, evidence_errors = [], [{"source": "macro", "error": "fetch failed"}]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan": task,
        "candidates": candidates,
        "errors": errors,
        "gap_hits": gap_hits,
        "evidence": evidence,
        "evidence_errors": evidence_errors,
        "link_stats": {
            "total": len(candidates),
            "resolved_from_google": sum(1 for c in candidates if c.get("resolved_from_google")),
            "google_redirect": sum(1 for c in candidates if c.get("google_news_link")),
            "direct_publisher": sum(1 for c in candidates
                                     if "news.google.com" not in (c.get("source_url") or "")
                                     and c.get("source_url")),
            "paywalled": sum(1 for c in candidates
                             if (c.get("verification") or {}).get("paywall")),
        },
        "notice": "Research leads only. Headlines and heuristic scores do not prove business "
                  "viability, open tenders, or verified demand. Every lead stays review_required "
                  "until issuer and commercial evidence is independently confirmed.",
    }
