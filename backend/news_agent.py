"""News agent worker — reads business-development news and turns it into an
implementation plan (flow, budget, risk) with evidence labels.

Capabilities (all stdlib, fail-open):
- scan()       read every configured business feed in parallel (full text where
               the publisher feed exposes a direct link; title-only for the
               Google News wrapper feed, which is a JS shell server-side).
- fetch_article() read ANY news URL the user pastes -> title + body.
- classify()     deterministic growth / horizon (short|long|both) / sector /
               business-development signal scoring from the text.
- implementation_plan() build a business implementation plan from one article:
               opportunity, market evidence (live macro via evidence_sources),
               flow stages, an ILLUSTRATIVE budget (labeled estimated/assumed),
               a risk register (evidence + assumed), and phased steps.
- news_dossier() shape the plan into the same sectioned dossier the report
               engine consumes, so it renders to PNG flow/budget/risk charts +
               a strict-OOXML DOCX.

Nothing is invented: macro facts carry basis "evidence" (fetched now); budget
and risk figures are labeled "estimated"/"assumed" and stated as illustrative.
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree
from urllib.parse import urlparse
from urllib.request import Request, urlopen

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "Chrome/120 Safari/537.36 BizCrax36NewsAgent/1.0")

# (name, url, region, body_readable) — only feeds verified reachable from this
# host. Google News items are title-only (wrapper is a JS shell).
FEEDS = (
    ("Free Malaysia Today (biz)", "https://www.freemalaysiatoday.com/category/business/feed", "my", True),
    ("Free Malaysia Today (nation)", "https://www.freemalaysiatoday.com/feed", "my", True),
    ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss", "global", True),
    ("Bloomberg Economics", "https://feeds.bloomberg.com/economics/news.rss", "global", True),
    ("Tech in Asia", "https://www.techinasia.com/feed", "asia", True),
    ("Economic Times", "https://economictimes.indiatimes.com/rssfeedstopstories.cms", "asia", True),
    ("SCMP Business", "https://www.scmp.com/rss/4/feed", "asia", True),
    ("Google News (MY biz)", "https://news.google.com/rss/search?q=business+OR+economy+OR+startup+OR+investment+when:7d&hl=en-MY&gl=MY&ceid=MY:en", "my", False),
)

ATOM = "{http://www.w3.org/2005/Atom}"

# ------------------------------------------------------------------ fetching

def _get(url, timeout=20, size=2_500_000):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read(size).decode("utf-8", errors="replace"), resp.geturl()


def _parse_feed(raw, name):
    root = ElementTree.fromstring(raw)
    items = root.findall(".//item")
    ns = ""
    if not items:
        items = root.findall(ATOM + "entry")
        ns = ATOM
    out = []
    for it in items:
        def f(tag):
            v = it.findtext(ns + tag) if ns else it.findtext(tag)
            return (v or "").strip()
        title = f("title")
        link = f("link") or f("url")
        if not link and not ns:
            le = it.find("link")
            if le is not None:
                link = le.get("href", "") or ""
        if not title:
            continue
        out.append({
            "title": title[:300],
            "link": link,
            "source": name,
            "region": None,
            "published": f("pubDate") or f("published") or f("updated"),
            "body": f("description") or f("summary") or f("content")[:1200],
        })
    return out


def fetch_feed(name, url, region, body_readable, fetch=None, limit=40):
    getter = fetch or (lambda u: _get(u)[0])
    try:
        raw = getter(url)
    except (OSError, ValueError, ElementTree.ParseError) as exc:
        return [], {"feed": name, "error": type(exc).__name__}
    try:
        items = _parse_feed(raw, name)[:limit]
    except ElementTree.ParseError as exc:
        return [], {"feed": name, "error": type(exc).__name__}
    for it in items:
        it["region"] = region
        it["body_readable"] = body_readable
    return items, None


def scan(fetch=None, workers=6, limit=40, only=None):
    """Read every feed in parallel. only = set of feed names to restrict to."""
    results, errors = [], []

    def run(job):
        name, url, region, body = job
        items, err = fetch_feed(name, url, region, body, fetch=fetch, limit=limit)
        return items, err

    jobs = [f for f in FEEDS if only is None or f[0] in only]
    if len(jobs) == 1:
        outcomes = [run(jobs[0])]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(run, jobs))
    for items, err in outcomes:
        if err:
            errors.append(err)
        results.extend(items)
    return results, errors


def _visible_text(html):
    text = re.sub(r"(?is)<(script|style|noscript|head|svg|nav|footer|form)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_article(url, fetch=None, timeout=25):
    """Read any news URL -> {title, body, source, url, paragraphs, basis}."""
    getter = fetch or (lambda u: _get(u, timeout=timeout))
    try:
        html, final = getter(url)
    except (OSError, ValueError) as exc:
        return {"title": "", "body": "", "source": "", "url": url,
                "paragraphs": [], "basis": "unavailable", "error": type(exc).__name__}
    if isinstance(html, (bytes, bytearray)):
        html = html.decode("utf-8", errors="replace")
    og = re.search(r'property="og:title"\s+content="([^"]*)"', html)
    tg = re.search(r'name="twitter:title"\s+content="([^"]*)"', html)
    ttag = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
    title = (og or tg or ttag)
    title = re.sub(r"\s+", " ", title.group(1)).strip() if title else ""
    desc = re.search(r'property="og:description"\s+content="([^"]*)"', html) \
        or re.search(r'name="twitter:description"\s+content="([^"]*)"', html)
    description = re.sub(r"\s+", " ", desc.group(1)).strip() if desc else ""
    src = re.search(r'(?:name|property)="og:site_name"\s+content="([^"]*)"', html)
    host = (urlparse(final).hostname or "").removeprefix("www.")
    paras_raw = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    paragraphs = []
    for raw in paras_raw:
        clean = re.sub(r"(?s)<[^>]+>", " ", raw)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) > 40:
            paragraphs.append(clean)
        if len(paragraphs) >= 40:
            break
    body = " ".join(paragraphs) or _visible_text(html)[:4000]
    if len(body) < 120:
        return {"title": title, "body": body, "description": description,
                "source": (src.group(1) if src else host),
                "url": final, "paragraphs": paragraphs, "basis": "thin",
                "error": "insufficient_text"}
    return {"title": title, "body": body, "description": description,
            "source": (src.group(1) if src else host),
            "url": final, "paragraphs": paragraphs, "basis": "evidence"}


# ------------------------------------------------------------------ classify

GROWTH = {
    "growth": 2, "expand": 2, "expansion": 2, "launch": 2, "investment": 2,
    "invest": 2, "funding": 2, "raise": 2, "raised": 2, "revenue": 2,
    "profit": 2, "boom": 3, "surge": 2, "scale": 2, "opportunity": 2,
    "demand": 2, "startup": 2, "venture": 2, "capital": 2, "project": 1,
    "tender": 2, "contract": 2, "market": 1, "develop": 2, "build": 1,
    "open": 1, "new": 1, "record": 2, "increase": 1, "boost": 2, "grow": 2,
}
SHORT = {
    "q1": 2, "q2": 2, "q3": 2, "q4": 2, "quarter": 2, "this week": 2,
    "this month": 2, "immediate": 2, "now": 1, "earnings": 2, "dividend": 2,
    "price": 1, "rate": 1, "launch": 1, "days": 1, "week": 1, "month": 1,
}
LONG = {
    "2030": 3, "2031": 3, "2032": 3, "2035": 3, "2040": 3, "decade": 3,
    "long-term": 3, "long term": 3, "strategic": 2, "infrastructure": 2,
    "5-year": 3, "10-year": 3, "policy": 2, "regulation": 2,
    "transformation": 2, "national": 2, "roadmap": 2, "target": 1,
    "plan": 1, "masterplan": 3, "master plan": 3,
}
BIZ_DEV = {
    "merger": 3, "acquisition": 3, "acquire": 3, "mergers": 3,
    "partnership": 2, "joint venture": 3, "jv": 3, "expansion": 2,
    "new plant": 3, "factory": 2, "capacity": 2, "greenfield": 3,
    "brownfield": 2, "privatization": 2, "deregulation": 2, "subsidy": 2,
    "grant": 2, "incentive": 2, "tariff": 2, "import": 1, "export": 2,
    "trade": 1, "supply chain": 2, "data center": 3, "datacentre": 3,
}

SECTOR_TERMS = {
    "energy": ("energy", "solar", "battery", "renewable", "gas", "power",
               "electricity", "hydrogen", "grid", "oil", "petroleum", "ev charging"),
    "manufacturing": ("manufactur", "factory", "plant", "semiconductor", "electronic",
                      "industrial", "automation", "machinery", "steel", "chemical"),
    "agriculture": ("agri", "food", "crop", "farm", "palm", "plantation", "aqua",
                    "livestock", "poultry", "frut", "halal"),
    "technology": ("tech", "ai ", "artificial intelligence", "software", "data",
                   "cyber", "digital", "startup", "saas", "platform", "cloud", "robot"),
    "tourism": ("tourism", "tourist", "hospitality", "hotel", "resort", "travel",
                "aviation", "airline"),
    "finance": ("bank", "finance", "insurance", "investment fund", "venture",
                "fintech", "lending", "capital market", "bursa"),
    "infrastructure": ("infrastructure", "construction", "highway", "rail", "port",
                       "transit", "metro", "airport", "housing", "property"),
    "healthcare": ("health", "medical", "hospital", "pharma", "biotech", "clinic",
                   "vaccine", "wellness"),
}


def _count_hits(text, table):
    hits, score = [], 0
    for term, w in table.items():
        if term in text:
            score += w
            hits.append(term)
    return score, hits


def classify(text):
    """Deterministic growth/horizon/sector/business-development signals."""
    t = " " + re.sub(r"\s+", " ", (text or "")).lower() + " "
    g_score, g_hits = _count_hits(t, GROWTH)
    s_score, s_hits = _count_hits(t, SHORT)
    l_score, l_hits = _count_hits(t, LONG)
    b_score, b_hits = _count_hits(t, BIZ_DEV)
    if s_score and l_score:
        horizon = "both"
    elif l_score > s_score:
        horizon = "long"
    elif s_score:
        horizon = "short"
    else:
        horizon = "neutral"
    sector, best = "general", 0
    for key, terms in SECTOR_TERMS.items():
        hit = sum(1 for term in terms if term in t)
        if hit > best:
            best, sector = hit, key
    potential = g_score + b_score
    if potential >= 6 and (g_score >= 4 or b_score >= 3):
        potential_class = "high"
    elif potential >= 3:
        potential_class = "moderate"
    else:
        potential_class = "low"
    return {
        "growth_score": g_score, "growth_signals": g_hits[:8],
        "horizon": horizon, "short_signals": s_hits[:6], "long_signals": l_hits[:6],
        "business_dev_score": b_score, "business_dev_signals": b_hits[:8],
        "sector": sector, "potential_class": potential_class,
    }


# ------------------------------------------------------------------ planning

def budget_for(band):
    """ILLUSTRATIVE MYR cost breakdown per capital band (estimated, not a quote)."""
    table = {
        "micro": {"startup": 8000, "working_capital": 5000, "equipment": 6000,
                  "staff": 12000, "marketing": 4000, "licensing": 1500, "contingency": 4500},
        "small": {"startup": 60000, "working_capital": 40000, "equipment": 90000,
                  "staff": 80000, "marketing": 30000, "licensing": 8000, "contingency": 40000},
        "medium": {"startup": 400000, "working_capital": 300000, "equipment": 900000,
                   "staff": 600000, "marketing": 250000, "licensing": 60000, "contingency": 400000},
        "large": {"startup": 3000000, "working_capital": 2500000, "equipment": 6000000,
                  "staff": 4000000, "marketing": 1500000, "licensing": 500000, "contingency": 3500000},
    }
    b = table.get(band, table["small"])
    total = sum(b.values())
    return {"band": band, "currency": "MYR", "basis": "estimated",
            "note": "Illustrative budget bands, not a quote. Replace with supplier "
                    "and salary research before committing capital.",
            "total": total, "items": b}


def risks_for(sector, horizon, macro):
    """Risk register. Macro-derived risks carry evidence basis; the rest assumed."""
    risks = [
        {"risk": "Market demand weaker than headline suggests", "severity": "high",
         "likelihood": "medium", "mitigation": "Pre-sell / pilot before capex; "
         "track 90-day demand leading indicators.", "basis": "assumed"},
        {"risk": "Cost overrun vs illustrative budget", "severity": "high",
         "likelihood": "medium", "mitigation": "Hold 15-20% contingency; phase "
         "spend with go/no-go gates.", "basis": "assumed"},
        {"risk": "Regulatory / licensing delay", "severity": "medium",
         "likelihood": "medium", "mitigation": "Confirm licence requirements up "
         "front; sequence permits before build.", "basis": "assumed"},
        {"risk": "Talent and operational capacity gap", "severity": "medium",
         "likelihood": "medium", "mitigation": "Hire or contract core capability "
         "early; SOP + training plan.", "basis": "assumed"},
    ]
    gdp = next((m for m in macro if m.get("label") == "GDP growth (annual %)"
                and m.get("basis") == "evidence"), None)
    if gdp is not None:
        val = gdp.get("value", 0)
        risks.append({
            "risk": "Macro growth %s (%.1f%% last year) may not sustain demand" % (
                "slowdown" if val < 3 else "shift", val),
            "severity": "medium" if val < 3 else "low", "likelihood": "medium",
            "mitigation": "Stress-test revenue at lower growth; keep flexible "
                          "cost base.", "basis": "evidence",
            "evidence": "%s GDP growth %s%% (%s)" % (gdp.get("country"), val, gdp.get("year"))})
    if horizon in ("long", "both"):
        risks.append({"risk": "Long horizon: policy/technology change before payback",
                      "severity": "medium", "likelihood": "high",
                      "mitigation": "Modular investment; revisit at each gate.",
                      "basis": "assumed"})
    if sector in ("energy", "manufacturing"):
        risks.append({"risk": "Capex-heavy: equipment lead times & FX on imports",
                      "severity": "high", "likelihood": "medium",
                      "mitigation": "Early ordering; hedge FX; local suppliers.",
                      "basis": "assumed"})
    if sector == "finance":
        risks.append({"risk": "Regulatory capital & compliance intensity",
                      "severity": "high", "likelihood": "medium",
                      "mitigation": "Liaise with regulator pre-launch; compliance budget.",
                      "basis": "assumed"})
    sev = {"high": 3, "medium": 2, "low": 1}
    for r in risks:
        r["score"] = sev[r["severity"]] * sev[r["likelihood"]]
    risks.sort(key=lambda r: -r["score"])
    return risks


FLOW_STAGES = (
    ("Discover", "confirm opportunity + market evidence"),
    ("Verify", "demand, cost, licence, counterparty checks"),
    ("Fund", "choose capital band, line up budget + financing"),
    ("Build", "set up entity, team, equipment, permits"),
    ("Launch", "pilot / pre-sell, open operations"),
    ("Scale", "grow volume, optimize, expand"),
)


def flow_diagram():
    return [{"stage": s, "note": n} for s, n in FLOW_STAGES]


def merge_options_for(sector, horizon, macro):
    """Merger / acquisition routes into the opportunity (assumed framework)."""
    options = [
        {"route": "Acquire an existing operator", "detail": "Buy a small incumbent "
         "with customers and licences; skip the slowest start-up phase. Look for "
         "owners retiring or under-invested operators.",
         "when": "sector has fragmented incumbents; licence is slow to obtain",
         "basis": "assumed"},
        {"route": "Asset purchase (no debt)", "detail": "Buy equipment, contracts "
         "and inventory only, not the whole company. Cleaner liability profile.",
         "when": "target is profitable but the owner carries debt",
         "basis": "assumed"},
        {"route": "Strategic M&A with an established player", "detail": "Partner "
         "with or be acquired by a larger firm entering your niche; you bring "
         "local execution, they bring capital and distribution.",
         "when": "you have a proven pilot and the buyer is expanding regionally",
         "basis": "assumed"},
    ]
    steps = [
        "Map 10-20 potential acquisition targets (registry + news scan); score by size, licence, health",
        "Run initial due diligence: financials, licences, contracts, liabilities, staff",
        "Negotiate a term sheet (valuation multiple, earnout, non-compete, key-man clauses)",
        "Complete legal + tax + operational due diligence; confirm the headline opportunity is real",
        "Sign & close; integrate operations, staff, customers in a 90-day plan",
    ]
    return {"options": options, "steps": steps,
            "note": "M&A accelerates market entry at the cost of valuation risk. "
                    "Every figure here is a framework, not a valuation."}


def jv_options_for(sector, band, horizon):
    """Joint-venture structures to share capital and risk (assumed framework)."""
    structures = [
        {"structure": "50/50 JV with a local operator", "detail": "You bring capital "
         "or technology, partner brings licences, sites and customers. Shared P&L.",
         "use_when": "local licence/land/customer base is the bottleneck", "basis": "assumed"},
        {"structure": "Minority stake JV (20-40% you)", "detail": "A stronger partner "
         "leads; you invest a smaller share for exposure and upside. Lower control, lower risk.",
         "use_when": "you lack scale or sector credibility yet", "basis": "assumed"},
        {"structure": "Contractual JV (no new entity)", "detail": "Revenue-share or "
         "co-investment contract between two existing companies. Fastest and cheapest "
         "form; no company registration, but less protection.",
         "use_when": "one-off project or short horizon", "basis": "assumed"},
        {"structure": "Takaful / cooperative model (for micro-small bands)",
         "detail": "Small group of contributors pools capital and shares profit "
         "under a cooperative or Takaful structure; suits community-based businesses.",
         "use_when": "band is micro/small and the model is community-facing",
         "basis": "assumed"},
    ]
    steps = [
        "Define what you contribute (capital, tech, land, licence, brand) vs the partner's contribution",
        "Choose structure; agree profit split, loss cap, decision rights, exit/put-call terms",
        "Draft JV agreement: IP ownership, deadlock resolution, anti-dilution, transfer restrictions",
        "Register the JV entity (if any) and open joint accounts",
        "Run quarterly JV reviews with audited joint financials",
    ]
    return {"structures": structures, "steps": steps,
            "note": "A good JV splits what each side uniquely owns. Misaligned "
                    "incentives fail more often than capital gaps."}


def investment_routes_for(band, sector, macro):
    """How to fund the venture (assumed routes; macro facts labeled evidence)."""
    routes = [
        {"route": "Own cash / retained earnings", "detail": "Fastest, no dilution. "
         "Only viable when band <= small and personal cash is protected.",
         "fit": "micro/small", "basis": "assumed"},
        {"route": "Bank / SME financing (e.g. SME bank lines, SME Corp programmes)",
         "detail": "Debt for working capital or equipment; keeps equity. Requires "
         "a viable model and collateral or guarantees.",
         "fit": "small/medium", "basis": "assumed"},
        {"route": "Government grant / incentive (e.g. GRANT, MDEC, MITI programmes)",
         "detail": "Non-dilutive funding tied to conditions (jobs, local content, "
         "export targets). Longer lead time; check eligibility early.",
         "fit": "all bands (condition-dependent)", "basis": "assumed"},
        {"route": "Angel investor", "detail": "Equity from 1-3 individuals for an "
         "early stage; expect 10-25% dilution for a meaningful round. Pick angels "
         "with sector expertise, not just capital.",
         "fit": "small/medium", "basis": "assumed"},
        {"route": "Venture capital", "detail": "Institutional equity for scale-up; "
         "typically 15-30% per round, board seats, KPIs. Requires a growth story "
         "and traction.", "fit": "medium/large", "basis": "assumed"},
        {"route": "Strategic investor / corporate partnership",
         "detail": "A customer or supplier invests for access. Aligns incentives "
         "but can lock you into one counterparty.", "fit": "medium/large",
         "basis": "assumed"},
        {"route": "Revenue-based financing", "detail": "Lender takes a % of revenue "
         "until repaid; no equity. Good for businesses with predictable revenue.",
         "fit": "small/medium", "basis": "assumed"},
    ]
    routes = [r for r in routes if r["fit"].split("/")[0] in band or "all" in r["fit"]
              or band in r["fit"].split("/")]
    steps = [
        "Build the 12-month financial model (revenue, cost, cash); decide the gap",
        "Pick 2-3 funding routes that fit the band and sector; rank by cost of capital",
        "Prepare a data room: model, licences, traction, team, risk register",
        "Approach investors / apply for grants in parallel (don't serialize)",
        "Negotiate terms; protect control with staged dilution and anti-dilution caps",
    ]
    gdp = next((m for m in macro if m.get("label") == "GDP growth (annual %)"
                and m.get("basis") == "evidence"), None)
    note = "Funding routes are illustrative; choose by real cost-of-capital " \
        "comparison. "
    if gdp is not None:
        note += "Macro context: %s GDP growth %s%% (%s) [evidence]." % (
            gdp.get("country"), gdp.get("value"), gdp.get("year"))
    return {"routes": routes, "steps": steps, "note": note}


def marketing_plan_for(topic, sector, band, horizon):
    """Sector-tuned marketing plan (assumed; tactics are standard playbooks)."""
    channels = []
    if sector in ("technology", "finance"):
        channels += [
            {"channel": "Content / SEO + product-led growth", "detail": "Blog, "
             "technical proof, free tier or pilot; inbound leads", "cost": "low"},
            {"channel": "Partnerships with enterprises / banks", "detail": "Channel "
             "sales via integrators and corporate partners", "cost": "medium"},
        ]
    if sector in ("manufacturing", "energy", "infrastructure"):
        channels += [
            {"channel": "B2B trade shows + association networks", "detail": "MIAP, "
             "MIMOS, PERKIM, sector association events; direct outreach", "cost": "medium"},
            {"channel": "LinkedIn + email to decision-makers", "detail": "Targeted "
             "campaigns to procurement / engineering leads", "cost": "low"},
        ]
    if sector in ("tourism", "healthcare", "agriculture", "general"):
        channels += [
            {"channel": "Local social (TikTok/IG) + review sites", "detail": "Short "
             "video + Google Maps reviews; local community posts", "cost": "low"},
            {"channel": "Referral programme", "detail": "Reward existing customers "
             "for bringing new ones", "cost": "low"},
        ]
    channels += [
        {"channel": "Pricing & offers", "detail": "Introductory pricing for first "
         "cohort; bundles for margin", "cost": "low"},
        {"channel": "Public-relations story", "detail": "One compelling angle "
         "(local, green, tech, job-creating) to earn earned media", "cost": "low"},
    ]
    steps = [
        "Define the target customer in one sentence (who, where, what they buy)",
        "Choose the 2 channels that reach that customer at the lowest cost",
        "Set 90-day KPIs: cost per lead, conversion rate, CAC vs LTV",
        "Run a small paid pilot (RM 1-5k) to validate channel before scaling",
        "Double down on the channel with the best CAC/LTV; cut the rest",
    ]
    if horizon in ("long", "both"):
        steps.append("Build brand equity early (name, story, community) for the long run")
    return {"channels": channels, "steps": steps,
            "note": "Marketing plan is a standard playbook, not a forecast. "
                    "Validate channel cost with a small paid pilot before scaling."}


def _nav_like(p):
    """Heuristic: paragraphs that are site navigation / boilerplate, not article text."""
    low = p.lower()
    nav_terms = ("sign in", "newsletter", "home news", "berita", "lifestyle",
                 "sports", "videos", "accelerator", "menu", "privacy policy",
                 "cookie", "subscribe", "follow us")
    hits = sum(1 for t in nav_terms if t in low)
    # Many short capitalized nav words back-to-back = a menu bar.
    words = p.split()
    caps = sum(1 for w in words if w[:1].isupper() and w.isalpha())
    return hits >= 2 or (len(words) >= 6 and caps / len(words) > 0.7)


def summarize(article, max_chars=600):
    """Evidence-based summary: prefer the site's own og:description, then the
    lead paragraph + top signal sentences. No invention, nav text skipped."""
    desc = (article.get("description") or "").strip()
    paras = [p for p in (article.get("paragraphs") or []) if not _nav_like(p)]
    text = article.get("body") or ""
    if desc and len(desc) >= 60:
        lead = desc
    elif paras:
        lead = paras[0]
    else:
        lead = text[:280]
    sig_words = ("invest", "growth", "launch", "fund", "expand", "market",
                 "revenue", "profit", "build", "open", "target", "million", "billion",
                 "ringgit", "jobs", "phase", "hub", "capacity")
    picked = []
    for p in paras:
        if p == lead:
            continue
        low = p.lower()
        if any(w in low for w in sig_words) and p not in picked:
            picked.append(p)
        if len(picked) >= 3:
            break
    parts = [lead.strip()] + [p.strip() for p in picked]
    summary = " ".join(parts)[:max_chars]
    return summary or (text[:max_chars] or "(no extractable text)")


def implementation_plan(article, topic=None, band=None, fetch=None,
                        country="Malaysia", with_macro=True):
    """Build a business implementation plan from one article (stdlib + macro)."""
    text = (article.get("title") or "") + " " + (article.get("body") or "")
    sig = classify(text)
    topic = (topic or article.get("title") or "business opportunity")[:120]
    band = band if band in ("micro", "small", "medium", "large") else (
        "micro" if sig["potential_class"] == "low"
        else "small" if sig["growth_score"] < 6
        else "medium")
    macro, src_err = [], []
    if with_macro:
        from backend import evidence_sources
        try:
            macro, src_err = evidence_sources.fetch_all(topic, country,
                                                        fetch=fetch, workers=4)
        except Exception:  # macro is optional context
            macro, src_err = [], [{"source": "macro", "error": "fetch failed"}]
    budget = budget_for(band)
    risks = risks_for(sig["sector"], sig["horizon"], macro)
    m_and_a = merge_options_for(sig["sector"], sig["horizon"], macro)
    jv = jv_options_for(sig["sector"], band, sig["horizon"])
    investment = investment_routes_for(band, sig["sector"], macro)
    marketing = marketing_plan_for(topic, sig["sector"], band, sig["horizon"])
    steps = [
        {"phase": "0-30d", "goal": "Verify", "actions": [
            "Confirm the specific demand and target customer from the article + 2 independent sources",
            "Check licence/registration requirements for the %s sector in %s" % (sig["sector"], country),
            "Interview 5 potential customers; validate price point"]},
        {"phase": "31-90d", "goal": "Fund + Build", "actions": [
            "Finalize %s-band budget with real quotes (replace illustrative figures)" % band,
            "Register entity; secure funding; sign key supplier/tenancy contracts",
            "Hire or contract core capability; set SOPs"]},
        {"phase": "3-6m", "goal": "Launch", "actions": [
            "Run a pilot or pre-sell to prove demand before full capex",
            "Open operations; set 90-day KPIs (revenue, margin, customer count)"]},
        {"phase": "6-12m", "goal": "Scale", "actions": [
            "Review KPIs at go/no-go gates; scale volume or pivot",
            "Document what worked; feed learnings back into the research agent"]},
    ]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_url": article.get("url"),
        "source_name": article.get("source") or "",
        "article_title": article.get("title") or "",
        "read_basis": article.get("basis", "evidence"),
        "topic": topic,
        "country": country,
        "sector": sig["sector"],
        "horizon": sig["horizon"],
        "potential_class": sig["potential_class"],
        "signals": sig,
        "summary": summarize(article),
        "evidence": {
            "macro": macro,
            "source_errors": src_err,
            "basis_note": "Macro facts fetched live (basis=evidence). Budget and "
                          "risk figures are illustrative (estimated/assumed), "
                          "not quotes or forecasts.",
        },
        "flow": flow_diagram(),
        "budget": budget,
        "risks": risks,
        "steps": steps,
        "m_and_a": m_and_a,
        "joint_venture": jv,
        "investment": investment,
        "marketing": marketing,
        "review_required": True,
    }


def plan_from_result(result, band=None, fetch=None, with_macro=True, topic=None):
    """Build an implementation plan from a research() result (top candidate).

    Same plan shape as implementation_plan() but sourced from the deterministic
    research result instead of a single news article. The top candidate's
    headline + verified sources form the evidence base.
    """
    candidates = result.get("candidates") or []
    if not candidates:
        raise ValueError("no research candidates to plan from")
    top = candidates[0]
    text = " ".join(
        [str(top.get("title", ""))]
        + [str(c.get("title", "")) for c in candidates[:6]]
        + [str(v) for v in (result.get("gap_hits") or {})])
    article = {
        "title": str(top.get("title", ""))[:300],
        "body": text,
        "source": (top.get("source_url") or "")[:80],
        "url": top.get("source_url"),
        "paragraphs": [str(top.get("title", ""))[:300]],
        "basis": "evidence",
    }
    topic = topic or (result.get("plan") or {}).get("query") or top.get("title", "")
    country = (result.get("plan") or {}).get("country", "Malaysia")
    band = band or (result.get("plan") or {}).get("capital") or None
    return implementation_plan(article, topic=topic, band=band, fetch=fetch,
                               country=country, with_macro=with_macro)


def news_dossier(plan, items):
    """Shape a plan into the sectioned dossier reports.build_docx consumes."""
    macro_lines = []
    for m in plan["evidence"]["macro"]:
        if m.get("basis") == "evidence":
            macro_lines.append("• [%s] %s — %s" % (m.get("source"), m.get("label"),
                                                   m.get("detail") or ("%.2f" % m.get("value", 0) if "value" in m else "")))
        else:
            macro_lines.append("• [%s] %s — %s (UNAVAILABLE)" % (m.get("source"), m.get("label"), m.get("detail")))
    b = plan["budget"]
    budget_lines = ["Total illustrative budget: RM %s (band: %s) — %s" % (
        "{:,}".format(b["total"]), b["band"], b["note"])]
    for k, v in b["items"].items():
        budget_lines.append("• %s: RM %s (ESTIMATED)" % (k.replace("_", " ").title(), "{:,}".format(v)))
    risk_lines = []
    for r in plan["risks"]:
        risk_lines.append("• [%d/9 %s] %s (S:%s L:%s) — %s [%s]" % (
            r["score"], "high" if r["score"] >= 6 else "med" if r["score"] >= 3 else "low",
            r["risk"], r["severity"], r["likelihood"], r["mitigation"], r["basis"]))
    step_lines = []
    for s in plan["steps"]:
        step_lines.append("%s — %s" % (s["phase"], s["goal"]))
        for a in s["actions"]:
            step_lines.append("   • " + a)
    sig = plan["signals"]
    signal_lines = [
        "Growth score: %d (class %s) · Horizon: %s · Sector: %s" % (
            sig["growth_score"], plan["potential_class"], plan["horizon"], plan["sector"]),
        "Growth signals: %s" % (", ".join(sig["growth_signals"][:8]) or "none"),
        "Business-development signals: %s" % (", ".join(sig["business_dev_signals"][:8]) or "none"),
    ]
    ma_lines = ["M&A note: %s" % plan["m_and_a"]["note"]]
    for o in plan["m_and_a"]["options"]:
        ma_lines.append("• %s — %s (use when: %s) [%s]" % (
            o["route"], o["detail"], o["when"], o["basis"]))
    ma_lines.append("M&A steps:")
    for s in plan["m_and_a"]["steps"]:
        ma_lines.append("   1. " + s)
    jv_lines = ["JV note: %s" % plan["joint_venture"]["note"]]
    for s in plan["joint_venture"]["structures"]:
        jv_lines.append("• %s — %s (use when: %s) [%s]" % (
            s["structure"], s["detail"], s["use_when"], s["basis"]))
    jv_lines.append("JV steps:")
    for st in plan["joint_venture"]["steps"]:
        jv_lines.append("   1. " + st)
    inv_lines = ["Investment note: %s" % plan["investment"]["note"]]
    for r in plan["investment"]["routes"]:
        inv_lines.append("• %s — %s (fit: %s) [%s]" % (
            r["route"], r["detail"], r["fit"], r["basis"]))
    inv_lines.append("Funding steps:")
    for st in plan["investment"]["steps"]:
        inv_lines.append("   1. " + st)
    mkt_lines = ["Marketing note: %s" % plan["marketing"]["note"]]
    for c in plan["marketing"]["channels"]:
        mkt_lines.append("• %s — %s (cost: %s)" % (c["channel"], c["detail"], c["cost"]))
    mkt_lines.append("Marketing steps:")
    for st in plan["marketing"]["steps"]:
        mkt_lines.append("   1. " + st)
    news_lines = []
    if items:
        news_lines.append("Headlines scanned: %d (across %d feeds)" % (
            len(items), len({i.get("source") for i in items})))
        for it in items[:12]:
            news_lines.append("• [%s] %s" % (it.get("source", "?"), it.get("title", "")[:120]))
    else:
        news_lines.append("Sourced from a research run (top candidate + peer leads), "
                          "not a single news article.")
    return {
        "schema_version": 1,
        "generated_at": plan["generated_at"],
        "title": "Proposal for Business Plan — %s" % (plan["topic"][:70] or "Business Opportunity"),
        "topic": plan["topic"],
        "scope": plan["country"],
        "country": plan["country"],
        "capital_band": plan["budget"]["band"],
        "notice": "Business setup & implementation plan. Evidence labels show "
                  "what was fetched live (evidence) vs. illustrative (estimated/"
                  "assumed). REVIEW_REQUIRED until each assumption is confirmed "
                  "with primary sources. This is a proposal for review — not "
                  "investment advice.",
        "sections": {
            "opportunity": {"title": "Opportunity & Summary", "label": "verified",
                            "content": [plan["summary"],
                                        "Source: %s — %s" % (plan["source_name"], plan["source_url"]),
                                        "Evidence basis: %s" % plan["read_basis"]]},
            "signals": {"title": "Growth & Business-Development Signals", "label": "estimated",
                        "content": signal_lines},
            "news_scan": {"title": "Sources Scanned", "label": "verified",
                          "content": news_lines},
            "market_evidence": {"title": "Live Market Evidence (Macro)", "label": "verified",
                                "content": macro_lines or ["• (no macro retrieved)"]},
            "flow": {"title": "Implementation Flow", "label": "assumed",
                     "content": ["%s — %s" % (s["stage"], s["note"]) for s in plan["flow"]]},
            "financial_forecast": {"title": "Budget (Illustrative)", "label": "estimated",
                                   "content": budget_lines},
            "investment": {"title": "Investment & Funding Routes", "label": "assumed",
                           "content": inv_lines},
            "merger_jv": {"title": "Merger (M&A) & Joint-Venture Routes", "label": "assumed",
                          "content": ma_lines + [""] + jv_lines},
            "marketing": {"title": "Marketing & Go-To-Market", "label": "assumed",
                          "content": mkt_lines},
            "risk": {"title": "Risk Register", "label": "estimated", "content": risk_lines},
            "plan": {"title": "Phased Implementation Plan", "label": "assumed",
                     "content": step_lines},
        },
    }
