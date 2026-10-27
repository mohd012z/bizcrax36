"""360-degree opportunity dossier: deterministic sections from verified research output.

Every section is labeled verified / estimated / assumed / unavailable so a reader
never mistakes a heuristic for evidence. No network access, no LLM.
"""
import re
from datetime import datetime, timezone

SECTIONS = (
    ("executive_summary", "Executive summary"),
    ("market_evidence", "Live market evidence"),
    ("industry_intelligence", "Industry intelligence"),
    ("customer_demand", "Customer demand"),
    ("competition", "Competition"),
    ("business_model", "Business model"),
    ("startup_capital", "Startup capital"),
    ("financial_forecast", "Financial forecast"),
    ("funding_investment", "Funding and investment"),
    ("supply_chain", "Supply chain"),
    ("legal_regulatory", "Legal and regulatory"),
    ("risk_assessment", "Risk assessment"),
    ("growth_strategy", "Growth strategy"),
    ("opportunity_ranking", "Opportunity ranking"),
    ("source_verification", "Source verification"),
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


def _label(kind):
    return {"verified": "VERIFIED", "estimated": "ESTIMATED",
            "assumed": "ASSUMED", "unavailable": "UNAVAILABLE"}[kind]


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
    sections["funding_investment"] = {
        "label": "estimated",
        "content": ["%s — %s" % (name, note) for name, _, note in FUNDING_CANDIDATES][:6],
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
    for c in candidates[:15]:
        v = c.get("verification") or {}
        if v.get("verified"):
            src_lines.append("[source-verified %s] %s (%s)" % (v.get("retrieved_at", "n/a"), c["source_url"], c["title"][:80]))
        else:
            src_lines.append("[review-required] %s (%s)" % (c.get("source_url", "no link"), c["title"][:80]))
    sections["source_verification"] = {
        "label": "verified",
        "content": src_lines or ["No source URLs recorded."],
    }

    return {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "topic": plan["query"],
        "country": plan["country"],
        "capital_band": capital,
        "top_candidate_id": top["id"] if top else None,
        "sections": {key: {"title": title, **sections[key]} for key, title in SECTIONS if key in sections},
        "notice": ("Sections are labeled by evidence quality: VERIFIED = fetched and matched; "
                   "ESTIMATED = derived from retrieved data; ASSUMED = neutral heuristic; "
                   "UNAVAILABLE = not collected yet. Labels describe evidence, not truth."),
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
