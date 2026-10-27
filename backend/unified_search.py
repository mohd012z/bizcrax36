"""Single-search federation of audited tenders and business hypotheses.

No network calls are performed at search time. The API reports freshness explicitly.
"""
from datetime import datetime, timezone
from backend.opportunity_filter import status as tender_status
from backend.global_opportunities import assess as entry_assess

def one_search(records, ideas, query="", country="", sector="", mode="all", now=None):
    if mode not in ("all","live","review","ideas"):
        raise ValueError("invalid mode")
    now=now or datetime.now(timezone.utc)
    q=query.casefold().strip()
    results=[]
    for r in records:
        if not isinstance(r,dict):
            continue
        if country and str(r.get("country","")).casefold()!=country.casefold():
            continue
        if sector and str(r.get("sector","")).casefold()!=sector.casefold():
            continue
        text=" ".join(str(r.get(k,"")) for k in ("title","description","issuer","reference","sector","country")).casefold()
        if q not in text:
            continue
        kind=r.get("type","tender")
        state=tender_status(r,now) if kind=="tender" else "review_required"
        if kind=="tender" and r.get("country") and r.get("country")!="Malaysia":
            assessment=entry_assess(r,now)
            if assessment["shortlist_status"]!="eligible_for_commercial_review":
                state="review_required"
        if mode=="live" and state!="live":
            continue
        if mode in ("review","ideas") and (state=="live" or mode=="ideas"):
            continue
        keys=("title","issuer","reference","source_url","description","country","sector",
              "currency","contract_value","closing_at","last_verified_at","type")
        row={k:r.get(k) for k in keys}
        row.update(category="procurement",status=state,verified=(state=="live"),
                   next_steps=["Check the original issuer notice and amendments",
                               "Verify eligibility, specifications, costs and deadlines",
                               "Obtain supplier quotes and prepare bid/no-bid decision"])
        results.append(row)
    if mode in ("all","ideas"):
        for idea in ideas:
            if not isinstance(idea,dict):
                continue
            if country and str(idea.get("country","Malaysia")).casefold()!=country.casefold():
                continue
            if sector and str(idea.get("sector","")).casefold()!=sector.casefold():
                continue
            if q not in " ".join(str(idea.get(k,"")) for k in ("title","sector","description","customers")).casefold():
                continue
            results.append({"category":"business_idea","title":idea.get("title"),
                "sector":idea.get("sector"),"country":idea.get("country","Malaysia"),
                "description":idea.get("description"),"status":"research_hypothesis",
                "verified":False,"capital_min":idea.get("capital_min"),
                "capital_max":idea.get("capital_max"),
                "next_steps":idea.get("next_steps",[
                    "Interview potential customers and validate willingness to pay",
                    "Research competitors, supplier quotations and compliance",
                    "Calculate unit economics and run a small pilot"])})
    return {"count":len(results),"results":results,"generated_at":now.isoformat(),
        "disclaimer":"Results mix audited notice records and explicitly unverified business ideas. Live is a freshness/status classification, not an investment recommendation."}
