"""360-degree opportunity dossier: deterministic sections from verified research output.

Every section is labeled verified / estimated / assumed / unavailable so a reader
never mistakes a heuristic for evidence. No network access, no LLM.
"""
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

SECTIONS = (
    ("executive_summary", "Executive summary"),
    ("project_overview", "Project proposal — title · value · timeline · costing"),
    ("classification", "Play categorisation (micro/macro · short/long · fast/slow)"),
    ("market_evidence", "Live market evidence"),
    ("industry_intelligence", "Industry intelligence"),
    ("customer_demand", "Customer demand"),
    ("competition", "Competition"),
    ("named_businesses", "Named potential businesses (all capital ranges)"),
    ("business_model", "Business model"),
    ("startup_capital", "Startup capital"),
    ("tender_project", "Tender, project & new-build entry"),
    ("funding_investment", "Funding, loan & grant finder"),
    ("financial_forecast", "Financial forecast"),
    ("supply_chain", "Supply chain"),
    ("legal_regulatory", "Legal and regulatory"),
    ("risk_assessment", "Risk assessment"),
    ("growth_strategy", "Growth strategy"),
    ("opportunity_ranking", "Opportunity ranking"),
    ("source_verification", "References — where each fact came from"),
)

CAPITAL_BAND_HINTS = {
    "micro": ("Micro-capital band (RM0-10k). Typical route: service-based start, own equipment, "
              "self-funded. Check SME Bank microloans and local cooperative financing for top-ups."),
    "small": ("Small-capital band (RM10k-250k). Typical route: SME Bank financing facilities, "
              "MIDA/SMI registration, grant programmes (check eligibility, not assumed)."),
    "medium": ("Medium-capital band (RM250k-2M). Typical route: bank term financing with collateral, "
              "government grant stacking, angel or strategic co-investment."),
    "large": ("Large-capital band (RM2M+). Typical route: project financing, strategic partners, "
              "venture or institutional capital; expect formal due diligence."),
}

FUNDING_CANDIDATES = (
    ("SME Bank financing facilities", "smebank.com.my", "Verify participating-bank routes, collateral and rates; do not assume approval."),
    ("MIDA / SMI investment incentives", "mida.gov.my", "Check scheme eligibility by sector, location and ownership structure."),
    ("SME Corp (SMI) development grants", "smecorp.gov.my", "Grant schemes change; confirm open windows and permitted costs."),
    ("SEDA energy efficiency schemes", "seda.gov.my", "Relevant when the opportunity includes energy audits or efficiency retrofits."),
    ("MATRADE export support", "matrade.gov.my", "Relevant only if the business model exports goods or services."),
    ("World Bank / ADB procurement (UNGM)", "ungm.org", "For tenders: verify notice reference, deadline and bidder eligibility."),
)

# Funding sources with a REAL portal URL + how to find + how to apply + typical
# requirements. (label, url, how_to_find, how_to_apply, requirements).
FUNDING_SOURCES = (
    ("SME Bank Financing (Malaysia)", "https://www.smebank.com.my/",
     "Register on SME Bank online; list facilities by type (working capital, equipment, project).",
     "Apply online or via a participating bank with company docs + financials.",
     "Registered company (SSM), 1-12 months operation, financial statements, collateral/guarantee may be required."),
    ("SME Corp Malaysia (grants & soft loans)", "https://smecorp.gov.my/",
     "Browse open programmes on the SME Corp portal; filter by sector/region.",
     "Submit a project proposal through the online portal during the open window.",
     "SME definition (ownership + revenue cap), project feasibility, matching funds for some grants."),
    ("SEDA energy-efficiency financing (Malaysia)", "https://www.seda.gov.my/",
     "Check open SEDA schemes (energy audits, efficiency retrofits, green SME support).",
     "Apply per scheme via the SEDA portal with company docs + the project case.",
     "Registered company, eligible sector, project scope approved by SEDA for the scheme."),
    ("MIDA / investment incentives", "https://www.mida.gov.my/",
     "Check sector-specific incentives (tax, capital allowance) on the MIDA site.",
     "Apply for an Investment Approval Certificate (IAC) with project details.",
     "Minimum capital commitment, local content/jobs targets, sector eligibility."),
    ("Global Grants Index (find grants anywhere)", "https://globalgrantsindex.com/",
     "Search by country/sector/category for open grants; filter by deadline.",
     "Follow the listed funder's application link; most are free to apply.",
     "Varies by funder; check eligibility + required documents before applying."),
    ("UN Global Marketplace (UNGM — tenders & contracts)", "https://ungm.org/",
     "Register a free UNGM account; browse open UN tenders/contracts by category.",
     "Submit a bid through the portal before the deadline (e-procurement).",
     "UNGM membership, valid business registration, sometimes past-performance evidence."),
    ("Bank Negara / SME financing (Malaysia macro)", "https://www.bnm.gov.my/",
     "Check national SME financing schemes and credit conditions on BNM.",
     "Usually via your bank under the stated scheme; confirm current terms.",
     "SME eligibility, credit standing, scheme-specific conditions."),
    ("Angel / VC / grant platforms (global)", "https://www.startupgrants.org/",
     "Use curated grant/angel databases; match by stage and geography.",
     "Apply per investor/funder; prepare pitch deck + one-pager.",
     "Stage-appropriate traction, business model clarity, team credentials."),
)

# Tender / project / new-build entry portals with REAL URLs.
TENDER_PORTALS = (
    ("UNGM — UN global tenders & contracts", "https://ungm.org/",
     "Register free, browse open tenders worldwide by sector/category.",
     "Download the tender docs, prepare bid, submit via e-procurement before deadline."),
    ("Malaysia e-Perolehan (eProcurement, government tenders)", "https://eproc3.mfi.gov.my/",
     "Register as a supplier on e-Perolehan; subscribe to tenders in your sector.",
     "Log in, download BOP (bid), submit documents and prices online before close."),
    ("TendersInfo (aggregator of public tenders, any field)", "https://www.tendersinfo.com/",
     "Search by keyword/region; many public tenders across countries.",
     "Open the linked source tender and apply per the issuer's instructions."),
    ("Malaysia MATRADE / e-Perolehan export tenders", "https://www.matrade.gov.my/",
     "MATRADE lists trade opportunities and export tenders for SMEs.",
     "Register as a MATRADE member; apply to listed opportunities."),
)


def classify_play(capital, sector):
    """Deterministic play categorisation: micro/macro, short/long-term, fast/slow.

    No LLM, no invention. Capital band drives micro vs macro; sector drives
    long-horizon (capex/regulatory-heavy) vs fast-to-launch; combined into a
    short/long + fast/slow label. When the band is 'all' (a high-potential
    request across capital levels) BOTH micro and macro plays are reported,
    because a single label would hide the other half of the opportunity.
    """
    cap = (capital or "all").lower()
    long_sectors = {"energy", "manufacturing", "infrastructure", "aerospace", "finance"}
    micro_scope = "micro (single site / service-led)"
    macro_scope = "macro (multi-site / industrial / export scale)"
    if cap in ("micro", "small"):
        scope = micro_scope
    elif cap in ("medium", "large"):
        scope = macro_scope
    else:  # 'all' — present both plays so the reader sees the full spectrum
        scope = "both — micro AND macro (pick the capital band that fits)"
    if sector in long_sectors:
        horizon = "long-term (12-36 months to scale)"
        speed = "slow (permits/capex gate the timeline)"
    else:
        horizon = "short-term (0-12 months to revenue)"
        speed = "fast (launch in weeks-to-months, minimal permits)"
    if cap in ("micro", "small"):
        combined = "%s · %s · %s" % (scope.split(" ")[0], horizon.split(" ")[0], speed.split(" ")[0])
    elif cap in ("medium", "large"):
        combined = "%s · %s · %s" % (scope.split(" ")[0], horizon.split(" ")[0], speed.split(" ")[0])
    else:
        combined = "micro & macro · %s · %s" % (horizon.split(" ")[0], speed.split(" ")[0])
    return {"scope": scope, "horizon": horizon, "speed": speed, "combined": combined}


def _label(kind):
    return {"verified": "VERIFIED", "estimated": "ESTIMATED",
            "assumed": "ASSUMED", "unavailable": "UNAVAILABLE"}[kind]


def _short_date(raw):
    """Normalise an RFC-822 / ISO timestamp to 'YYYY-MM-DD' (best effort)."""
    if not raw:
        return "n/a"
    try:
        d = parsedate_to_datetime(raw)
        return d.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    try:
        return str(raw)[:10]
    except Exception:
        return str(raw)[:10]


def _host(url):
    try:
        return (urlparse(url or "").hostname or "unknown").lower()
    except Exception:
        return "unknown"


def _free_route(candidate, siblings=()):
    """A free/openable route for a paid or Google-redirected lead.
    1) a sibling direct publisher URL from the same research run, else
    2) a Google News search URL for the exact headline (free, opens in browser)."""
    from urllib.parse import quote_plus
    title = (candidate.get("title") or "").strip()
    if not title:
        return "(no alternative recorded)"
    for sib in siblings:
        if sib is candidate:
            continue
        sib_url = (sib.get("source_url") or "")
        if sib_url and "news.google.com" not in sib_url and _host(sib_url) != _host(candidate.get("source_url")):
            return sib_url + "  (same run, direct publisher link)"
    return "https://news.google.com/search?q=%s" % quote_plus('"%s"' % title[:120])


def _evidence_url(m):
    """Reconstruct the API/DOI URL an evidence row came from (for the reference)."""
    src = (m.get("source") or "").lower()
    code = m.get("country") or "MYS"
    if src == "world_bank":
        ind = {"GDP growth (annual %)": "NY.GDP.MKTP.KD.ZG",
               "Inflation, CPI (annual %)": "FP.CPI.TOTL.ZG",
               "Unemployment (% of labor force)": "SL.UEM.TOTL.ZS"}.get(m.get("label"), "")
        if ind:
            return "https://api.worldbank.org/v2/country/%s/indicator/%s" % (code, ind)
    if src in ("frankfurter_fx", "currency_api_fx"):
        return "https://api.frankfurter.dev/v1/latest"
    if src == "crossref" and m.get("doi"):
        return "https://doi.org/%s" % m["doi"]
    if src == "crossref":
        return "https://api.crossref.org/works"
    return ""


# Concrete, NAMED business concepts across every capital range. Each is a real
# archetypes operators can act on; the engine links the one(s) most supported by
# the leads THIS run found (keyword match), so a named idea always has a
# free/openable reference attached when evidence exists.
NAMED_BUSINESSES = [
    # (name, capital_band, one_liner, match_keywords)
    ("On-demand home & office cleaning service", "micro",
     "App/WhatsApp booking, own vans & supplies, revenue in weeks, low capex.",
     ["cleaning", "housekeeping", "janitorial", "on demand"]),
    ("Vending / coffee kiosk network", "micro",
     "Low-cost machines in high-traffic sites, near-passive once placed.",
     ["coffee", "kiosk", "vending", "beverage"]),
    ("Social-commerce reseller (TikTok/IG/WhatsApp)", "micro",
     "Curate a niche product line, sell via short video + DMs, ship via 3PL.",
     ["e-commerce", "ecommerce", "social commerce", "reseller", "dropship"]),
    ("AI content & chatbot agency for SMBs", "micro",
     "Sell done-for-you chatbots/ads/SEO retainers; near-zero equipment cost.",
     ["ai", "chatbot", "agency", "digital marketing", "seo"]),
    ("Home-based tutoring / upskilling studio", "micro",
     "Exam or career coaching, online + in-person, subscription pricing.",
     ["tutoring", "education", "e-learning", "course", "online learning"]),
    ("Last-mile courier / delivery micro-hub", "small",
     "Own e-bikes or van, local delivery contracts with online stores.",
     ["delivery", "courier", "logistics", "last mile", "freight"]),
    ("Food franchise (halal F&B, kiosk or outlet)", "small",
     "Licensed brand outlet — proven menu, lower risk than own concept.",
     ["franchise", "food", "f and b", "restaurant", "kitchen", "caf"]),
    ("Specialty coffee / bakehouse brand", "small",
     "Own-brand café or bakery with retail bags for margin beyond foot traffic.",
     ["coffee", "bakery", "beverage", "food"]),
    ("E-commerce D2C brand (niche product)", "small",
     "Own SKU, paid + organic social, 3PL fulfilment, subscription attach.",
     ["e-commerce", "ecommerce", "d2c", "brand", "retail"]),
    ("Micro-SaaS tool (single painful workflow)", "small",
     "Niche B2B software; low CAC via integrations/marketplaces, recurring.",
     ["saas", "micro-saas", "b2b software", "bootstrapped"]),
    ("Home services marketplace (plumbing/electrical)", "small",
     "Curated tradespeople, booking + warranty layer, take-rate per job.",
     ["home services", "home improvement", "plumbing", "electrician", "maintenance"]),
    ("Agri-processing / value-added food factory", "medium",
     "Process raw local produce into branded packaged goods for retail/export.",
     ["agri", "food processing", "manufacturing", "cold chain", "farming"]),
    ("B2B SaaS / AI platform (scale)", "medium",
     "Horizontal platform with usage pricing; venture or grant funded.",
     ["b2b saas", "ai platform", "saaas", "enterprise software"]),
    ("F&B QSR chain (multi-outlet, own brand)", "medium",
     "Own-brand fast-casual chain with central kitchen + licensing model.",
     ["qsr", "fast casual", "restaurant chain", "franchise"]),
    ("EV charging / energy services network", "medium",
     "Charging bays + solar + demand-side services; infra + recurring fees.",
     ["ev", "energy", "solar", "charging", "efficiency"]),
    ("Industrial manufacturing / contract fab", "large",
     "Capital-intensive production for export or local OEM contracts.",
     ["manufacturing", "factory", "production", "industrial"]),
    ("Cold-chain & distribution logistics park", "large",
     "Reefer warehouses + fleet; B2B contracts, high switching costs.",
     ["cold chain", "logistics", "distribution", "supply chain"]),
    ("Data centre / digital infrastructure", "large",
     "Hyperscale-adjacent DC or edge sites; long payback, sticky contracts.",
     ["data centre", "infrastructure", "digital", "cloud"]),
    ("Renewable power plant (solar/wind IPP)", "macro",
     "Utility-scale generation + offtake PPA; financing-led, multi-year.",
     ["renewable", "solar", "wind", "power", "energy", "ipp"]),
    ("Real estate / proptech development", "macro",
     "Mixed-use or vertical living; development + management + tech layers.",
     ["real estate", "property", "development", "proptech", "construction"]),
]


def _named_business_lines(result):
    """Named potential businesses across every capital range, each grounded in
    the leads this run found (keyword match). Returns section content lines."""
    candidates = result.get("candidates", [])
    titles = [(c.get("title") or "").lower() for c in candidates]
    lines = [
        "Named potential businesses (concrete archetypes, low -> high capital).",
        "For each, the engine links the strongest matching lead from THIS run so",
        "you have a free/openable reference. All are REVIEW_REQUIRED — validate",
        "unit economics, licensing and local demand before committing capital.",
        "",
    ]
    band_order = ["micro", "small", "medium", "large", "macro"]
    for band in band_order:
        entries = [e for e in NAMED_BUSINESSES if e[1] == band]
        if not entries:
            continue
        lines.append("--- %s capital ---" % band.upper())
        for name, _band, one_liner, kws in entries:
            # find best matching lead: prefer multi-keyword (specific) hits, then
            # direct publisher links (openable) over Google News redirects.
            best = None
            for c, t in zip(candidates, titles):
                hit = sum(1 for kw in kws if kw in t)
                if not hit:
                    continue
                direct = 1 if "news.google.com" not in (c.get("source_url") or "") else 0
                rank = (hit, direct, c.get("score", {}).get("total", 0))
                if best is None or rank > best[0]:
                    best = (rank, c)
            if best is not None:
                c = best[1]
                v = c.get("verification") or {}
                paid = " (paid — see free route)" if v.get("paywall") else ""
                lines.append("• %s — %s" % (name, one_liner))
                lines.append("   evidence this run: %s [%s]%s"
                             % (c["title"][:70], c.get("score", {}).get("total", "?"), paid))
                if v.get("paywall"):
                    lines.append("   ref: %s" % (c.get("source_url") or _free_route(c, candidates)))
                    lines.append("   free route: %s" % _free_route(c, candidates))
                else:
                    lines.append("   ref: %s" % (c.get("source_url") or _free_route(c, candidates)))
            else:
                lines.append("• %s — %s (no matching lead this run; treat as assumed)"
                             % (name, one_liner))
    lines.append("")
    lines.append("Capital range key: micro (<RM10k) · small (RM10k–250k) · "
                 "medium (RM250k–2M) · large (RM2M+) · macro (RM100M+, financing-led). "
                 "Bands are indicative; confirm real quotes per play.")
    return lines


def _candidate_lines(result, limit=8):
    lines = []
    for i, c in enumerate(result["candidates"][:limit], 1):
        v = c.get("verification") or {}
        mark = "source-verified" if v.get("verified") else "review-required"
        score = c.get("score") or {}
        lines.append("%d. %s — score %s/100 [%s]" % (i, c["title"], score.get("total", "?"), mark))
        if c.get("source_url"):
            lines.append("   %s" % c["source_url"])
    return lines


def _tender_lines(country="Malaysia"):
    """How to open/submit a tender, project or new build. Concrete + clickable."""
    my = "malaysia" in (country or "").lower()
    lines = [
        "To win a tender / project / new-build, you need a registered entity + a "
        "tender account on the right portal. Steps below are a standard path (assumed); "
        "confirm each portal's current rules before bidding.",
        "1. Register the business (SSM in MY; company registry elsewhere) and get a tax "
        "ID + bank account in the company name.",
        "2. Prepare a company profile + 2-3 past-performance references (or a pilot if "
        "new) — most tenders require proof you can deliver.",
        "3. Register on the tender portal(s) below; subscribe to your sector/keywords so "
        "new notices arrive automatically.",
        "4. When a notice fits: download the full tender documents, study eligibility + "
        "scoring, prepare the technical + commercial response, and submit before the "
        "deadline (late = rejected).",
        "5. New-build / own-project route (no tender): secure the site/tenant, get the "
        "sector licences/permits, line up 3 supplier quotes, then build to the "
        "implementation-flow stages in this document.",
        "Tender & project entry portals (click to open):",
    ]
    for name, url, find, apply in TENDER_PORTALS:
        lines.append("• %s — %s" % (name, url))
        lines.append("   find: %s" % find)
        lines.append("   apply: %s" % apply)
    if my:
        lines.append("Malaysia-specific: e-Perolehan (eproc3.mfi.gov.my) is the main government "
                     "e-tendering system; SMEs should also check MATRADE and sector ministries.")
    return lines


def _funding_lines(country="Malaysia", capital="all"):
    """How to find + apply for funding/loan/grant. Concrete + clickable."""
    my = "malaysia" in (country or "").lower()
    lines = [
        "Funding is one route among many — build/operate is the goal, financing is a tool. "
        "Pick by real cost-of-capital, not by which is easiest to apply for.",
        "How to find the right funding:",
        "   a. List 2-3 sources below that fit your capital band + sector + country.",
        "   b. Read each portal's eligibility + required documents BEFORE applying.",
        "   c. Prepare once: company docs, 12-month model, cash-flow forecast, one-pager "
        "      (reused across every application).",
        "   d. Apply to 2-3 in parallel (do not serialise) and track deadlines.",
        "How to apply (common to all):",
        "   1. Register/verify on the portal, 2. Complete the online form with real "
        "      figures (not placeholders), 3. Upload documents, 4. Submit + follow up, "
        "   5. If shortlisted, be ready for a call/visit and a faster, deeper model.",
        "Funding, loan & grant sources (click to open):",
    ]
    for label, url, find, apply, req in FUNDING_SOURCES:
        lines.append("• %s — %s" % (label, url))
        lines.append("   find: %s" % find)
        lines.append("   apply: %s" % apply)
        lines.append("   requires: %s" % req)
    lines.append("Band guidance (%s): %s" % (
        capital, CAPITAL_BAND_HINTS.get(capital, "see the startup-capital section")))
    lines.append("Always label approval as review_required — eligibility-gated, not assumed.")
    return lines


def _project_overview(plan, capital, top, top_score, candidates):
    """Presentation-style project proposal: title, value, description,
    timeline, costing, advice. Deterministic — budget/timeline are the
    engine's illustrative plan data, every figure labeled estimated."""
    from backend import news_agent  # no circular import (verified)
    topic = plan.get("query", "business opportunity")
    country = plan.get("country", "Global")
    sector = plan.get("sector", "general")
    band = capital if capital in ("micro", "small", "medium", "large") else "small"
    title = "%s — %s" % (topic.title()[:60], country)
    lines = [
        "PROJECT TITLE: %s" % title,
        "",
        "1. PROJECT VALUE (why this play)",
        "   Opportunity score: %s/100 (weighted, preliminary — not a profitability claim)." % top_score,
        "   Evidence base: %d candidate leads collected this run; top lead: '%s'."
        % (len(candidates), (top or {}).get("title", "n/a")[:90]),
        "   Value logic: demand signals from live news + literature, scored against "
        "competition, capital fit, regulatory readiness and operational feasibility.",
        "   Classification: see the Play categorisation section (micro/macro · short/long · fast/slow).",
        "   All figures below are ESTIMATED (illustrative) until replaced with real quotes.",
        "",
        "2. DESCRIPTION / SUMMARY (what to build)",
    ]
    try:
        b = news_agent.budget_for(band)
        lines.append("   A %s-scale %s venture in %s. Capital plan: startup %s %s + "
                     "working capital %s %s (total indicative %s %s)."
                     % (band, sector, country, b["items"].get("startup", 0), b["currency"],
                        b["items"].get("working_capital", 0), b["currency"],
                        b["total"], b["currency"]))
    except Exception:
        lines.append("   A %s-scale %s venture in %s (budget table unavailable this run)."
                     % (band, sector, country))
    lines += [
        "   Model: start with a paid pilot (1 real customer, written consent), measure "
        "actual delivery cost, then scale only if unit economics hold at 0.5x/1x/1.5x "
        "volume scenarios (see Financial forecast).",
        "   Revenue focus: %s — price from customer interviews (min 5), not from guesswork." % sector,
        "",
        "3. PROJECT TIMELINE (phased, with go/no-go gates)",
    ]
    try:
        for step in news_agent.implementation_plan(
                {"title": topic, "body": ""}, topic=topic, band=band,
                country=country, with_macro=False)["steps"]:
            lines.append("   Phase %s — %s:" % (step["phase"], step["goal"]))
            for a in step["actions"]:
                lines.append("     • %s" % a)
    except Exception:
        lines.append("   0-30d verify demand/licensing → 31-90d fund+build → "
                     "3-6m pilot/launch → 6-12m scale (gates at each phase).")
    lines += [
        "",
        "4. COSTING (indicative budget — replace with real quotes before committing)",
    ]
    try:
        b = news_agent.budget_for(band)
        for k, v in b["items"].items():
            lines.append("   • %s: %s %s" % (k.replace("_", " ").title(), v, b["currency"]))
        lines.append("   TOTAL INDICATIVE: %s %s  (basis: %s)" % (b["total"], b["currency"], b["basis"]))
        lines.append("   %s" % b["note"])
    except Exception:
        lines.append("   (budget table unavailable this run — see Startup capital section)")
    lines += [
        "",
        "5. ADVICE (what to do first)",
        "   1. Verify the top lead against its source (open the reference link) — do not build on an unverified headline.",
        "   2. Interview 5 prospective customers on price and must-have features BEFORE spending capital.",
        "   3. Confirm licensing/registration for %s in %s (see Legal & regulatory section).",
        "   4. Apply to 2-3 funding sources in parallel (see Funding, loan & grant finder).",
        "   5. Keep 15-20% contingency; phase spend behind the go/no-go gates above.",
        "   Status: REVIEW_REQUIRED — this is a proposal framework, not investment advice.",
    ]
    return {"label": "estimated", "content": lines}


def build(result, now=None):
    now = now or datetime.now(timezone.utc)
    plan = result["plan"]
    candidates = result["candidates"]
    verified = [c for c in candidates if (c.get("verification") or {}).get("verified")]
    errors = result.get("errors", [])
    top = candidates[0] if candidates else None
    top_score = (top.get("score") or {}).get("total") if top else None

    capital = plan.get("capital", "all")
    sections = {}
    evidence = result.get("evidence") or []
    ev_lines = []
    for m in evidence:
        if m.get("basis") == "evidence":
            detail = m.get("detail") or (("%.2f %s" % (m.get("value"), m.get("year", ""))).strip() if "value" in m else "")
            ev_lines.append("• [%s] %s — %s" % (m.get("source"), m.get("label"), detail))
        else:
            ev_lines.append("• [%s] %s — %s (UNAVAILABLE)" % (m.get("source"), m.get("label"), m.get("detail")))
    have_evidence = any(m.get("basis") == "evidence" for m in evidence)
    sections["market_evidence"] = {
        "label": "verified" if have_evidence else "unavailable",
        "content": ev_lines or [
            "Live macro/evidence sources not retrieved this run (offline or rate-limited).",
            "Typical no-auth sources: World Bank (MYS GDP/inflation/unemployment), Frankfurter FX, Crossref literature."],
    }
    sections["executive_summary"] = {
        "label": "estimated",
        "content": [
            "Topic: %s | Country: %s | Capital band: %s" % (plan["query"], plan["country"], capital),
            "Candidate leads discovered: %d | source pages independently fetched: %d | source errors: %d"
            % (len(candidates), len(verified), len(errors)),
            "Top preliminary score: %s/100 (weighted, preliminary — not a profitability claim)" % top_score,
            "All leads remain review_required until issuer, demand and cost evidence is independently confirmed.",
        ],
    }
    sections["project_overview"] = _project_overview(plan, capital, top, top_score, candidates)
    play = classify_play(capital, plan.get("sector", "general"))
    sections["classification"] = {
        "label": "estimated",
        "content": [
            "Scope: %s" % play["scope"],
            "Timeline: %s" % play["horizon"],
            "Pace: %s" % play["speed"],
            "One-line: %s — this is a categorisation to frame the plan, derived from the requested "
            "capital band + detected sector; confirm the real timeline with the operator." % play["combined"],
            "Micro plays: own equipment/service, single site, self-funded, revenue in months.",
            "Macro plays: multi-site/industrial/export, financing-led, longer payback, bigger upside.",
        ],
    }
    sections["industry_intelligence"] = {
        "label": "estimated" if have_evidence else "unavailable",
        "content": ([
            "Macro context retrieved live this run — see the 'Live market evidence' section above (basis: evidence).",
        ] if have_evidence else [
            "Market size and growth: not retrieved by this engine (requires open-data/statistics connectors).",
        ]) + [
            "Sector detected: %s" % plan.get("sector", "general"),
            "For dated market statistics before acting, use DOSM (open.dosm.gov.my), Bank Negara and MDEC releases.",
        ],
    }
    sections["customer_demand"] = {
        "label": "assumed",
        "content": [
            "Demand signals: %d headlines matched query terms; %d sources fetched and title-matched."
            % (len(candidates), len(verified)),
            "Willingness-to-pay and buyer budget: NOT measured — interview at least 5 prospective customers.",
        ] + _candidate_lines(result, 5),
    }
    sections["competition"] = {
        "label": "assumed" if not result.get("gap_hits", {}).get("competition") else "estimated",
        "content": [
            "Round-2 competition/pricing headlines found: %d" % result.get("gap_hits", {}).get("competition", 0),
            "Direct competitor list, prices and weaknesses: not retrieved; build the competitor table before pricing.",
        ],
    }
    sections["named_businesses"] = {
        "label": "estimated",
        "content": _named_business_lines(result),
    }
    sections["business_model"] = {
        "label": "unavailable",
        "content": [
            "Products/services, revenue streams and pricing: define from the top candidate and customer interviews.",
            "Run backend.business_blueprint financial_model with real quotes to produce a scenario model.",
        ],
    }
    sections["startup_capital"] = {
        "label": "assumed",
        "content": [CAPITAL_BAND_HINTS.get(capital, "Capital band not specified.")],
    }
    sections["financial_forecast"] = {
        "label": "unavailable",
        "content": [
            "No forecast is generated without real inputs (startup cost, price, variable cost, fixed cost, volume, cash).",
            "Formula: break-even sales = monthly fixed cost / (price - variable cost per sale).",
            "Scenario multipliers supported: 0.5x / 1x / 1.5x of base volume.",
        ],
    }
    sections["tender_project"] = {
        "label": "estimated",
        "content": _tender_lines(plan.get("country", "Malaysia")),
    }
    sections["funding_investment"] = {
        "label": "estimated",
        "content": _funding_lines(plan.get("country", "Malaysia"), capital),
    }
    sections["supply_chain"] = {
        "label": "unavailable",
        "content": [
            "Suppliers, lead times, minimum orders and backup sources: collect at least 3 written quotations.",
        ],
    }
    sections["legal_regulatory"] = {
        "label": "assumed" if result.get("gap_hits", {}).get("regulation") else "unavailable",
        "content": [
            "Round-2 licence/registration headlines found: %d" % result.get("gap_hits", {}).get("regulation", 0),
            "Register with SSM (ssm.com.my) and confirm sector licences before signing supplier or customer contracts.",
        ],
    }
    sections["risk_assessment"] = {
        "label": "estimated",
        "content": [
            "Evidence risk: %d source(s) could not be fetched (%s)"
            % (len(errors), ", ".join(sorted({e["error"] for e in errors})) or "none"),
            "Demand risk: headlines are not confirmed paying customers.",
            "Capital risk: funding programmes are eligibility-gated; approval is not assumed.",
            "Operational risk: staffing, equipment and quality processes are unverified.",
        ],
    }
    sections["growth_strategy"] = {
        "label": "assumed",
        "content": [
            "Suggested path: paid pilot (1 customer, written consent) -> measure actual delivery cost -> "
            "scale only if unit economics hold at 0.5x/1x/1.5x scenarios -> expand geography or sector.",
        ],
    }
    sections["opportunity_ranking"] = {
        "label": "estimated",
        "content": ["Ranking by weighted preliminary score (high value first within requested capital band):"]
                   + _candidate_lines(result, 10),
    }
    src_lines = []
    for i, c in enumerate(candidates[:15], 1):
        v = c.get("verification") or {}
        mark = "SOURCE-VERIFIED" if v.get("verified") else "REVIEW-REQUIRED"
        pub = _short_date(c.get("published_at"))
        ret = _short_date(v.get("retrieved_at"))
        ratio = ("match %.0f%%" % (100 * v.get("match_ratio", 0))) if v.get("match_ratio") is not None else ""
        src_lines.append("%d. [%s] %s" % (i, mark, c["title"][:110]))
        if c.get("source_url"):
            src_lines.append("   URL: %s" % c["source_url"])
        src_lines.append("   publisher/page: %s | published: %s | retrieved: %s %s"
                         % (_host(c.get("source_url")), pub, ret, ("(%s)" % ratio if ratio else "")))
        # Access notes: paid content and Google-redirected links need a free route.
        if v.get("paywall"):
            src_lines.append("   access: PAID CONTENT — open the free route below instead")
            src_lines.append("   free route: %s" % _free_route(c, candidates))
        elif c.get("google_news_link"):
            src_lines.append("   access: opens via Google News redirect (article body may be paywalled)")
            src_lines.append("   free route: %s" % _free_route(c, candidates))
    # Live macro/evidence sources (World Bank / FX / Crossref) with their API URL.
    live = [m for m in (result.get("evidence") or []) if m.get("basis") == "evidence"]
    if live:
        src_lines.append("")
        src_lines.append("Live evidence fetched this run (basis=evidence):")
        for m in live[:8]:
            doi = (" | DOI: %s" % m["doi"]) if m.get("doi") else ""
            url = _evidence_url(m)
            src_lines.append("• [%s] %s — %s%s | fetched %s" % (
                m.get("source"), m.get("label"),
                (m.get("detail") or (("%.2f %s" % (m.get("value"), m.get("year", ""))).strip() if "value" in m else "")),
                doi, _short_date(m.get("fetched_at"))))
            if url:
                src_lines.append("   %s" % url)
    sections["source_verification"] = {
        "label": "verified",
        "content": src_lines or ["No source URLs recorded."],
    }

    topic = (plan.get("query") or "").strip()
    return {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "title": "Proposal for Business Plan — %s" % (topic[:70] or "Business Opportunity"),
        "topic": topic,
        "scope": plan.get("country", "Global"),
        "country": plan.get("country", "Global"),
        "capital_band": capital,
        "top_candidate_id": top["id"] if top else None,
        "sections": {key: {"title": title, **sections[key]} for key, title in SECTIONS if key in sections},
        "notice": ("Sections are labeled by evidence quality: VERIFIED = fetched and matched; "
                   "ESTIMATED = derived from retrieved data; ASSUMED = neutral heuristic; "
                   "UNAVAILABLE = not collected yet. Labels describe evidence, not truth. "
                   "This is a proposal for review — not investment advice."),
    }


def summary_text(dossier, result, max_chars=3900):
    """Compact Telegram-friendly summary with real data and labeled sections."""
    plan = result["plan"]
    candidates = result["candidates"]
    verified = [c for c in candidates if (c.get("verification") or {}).get("verified")]
    top = candidates[:5]
    lines = []
    lines.append("📊 360° RESEARCH — %s" % plan["query"].upper()[:70])
    lines.append("%s | capital: %s | %d leads | %d source-verified | %d errors"
                 % (plan["country"], plan["capital"], len(candidates), len(verified), len(result.get("errors", []))))
    lines.append("")
    lines.append("TOP LEADS (preliminary score /100):")
    for i, c in enumerate(top, 1):
        s = c.get("score") or {}
        v = "✅" if (c.get("verification") or {}).get("verified") else "🔎"
        lines.append("%d. %s %s" % (i, c["title"][:95], v))
        lines.append("   score %s/100 %s" % (s.get("total", "?"),
                                              "| verified" if (c.get("verification") or {}).get("verified") else "| review required"))
        if c.get("source_url"):
            lines.append("   %s" % c["source_url"])
    gap = result.get("gap_hits", {})
    lines.append("")
    lines.append("📈 SIGNALS: competition headlines %s | licence/registration headlines %s | %s"
                 % (gap.get("competition", 0), gap.get("regulation", 0), plan.get("sector", "general")))
    evidence = result.get("evidence") or []
    live = [m for m in evidence if m.get("basis") == "evidence"]
    if live:
        bits = []
        for m in live[:3]:
            label = (m.get("label") or "?")[:30]
            if "value" in m:
                bits.append("%s %s%%" % (label, m.get("value")))
            elif m.get("detail") and m.get("detail") != label:
                bits.append(m.get("detail")[:40])
            else:
                bits.append(label)
        lines.append("🌐 LIVE EVIDENCE (fetched now): " + "; ".join(bits))
    lines.append("")
    lines.append("§ Executive: %s" % _label(dossier["sections"]["executive_summary"]["label"]))
    lines.append("§ Customer demand: %s" % _label(dossier["sections"]["customer_demand"]["label"]))
    lines.append("§ Competition: %s" % _label(dossier["sections"]["competition"]["label"]))
    lines.append("§ Financial forecast: %s" % _label(dossier["sections"]["financial_forecast"]["label"]))
    lines.append("§ Funding: %s | § Risk: %s"
                 % (_label(dossier["sections"]["funding_investment"]["label"]),
                    _label(dossier["sections"]["risk_assessment"]["label"])))
    lines.append("")
    lines.append("Tap 📄 Report (DOCX) for the full 15-section dossier.")
    lines.append(result["notice"][:220])
    return "\n".join(lines)[:max_chars]
