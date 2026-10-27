"""Unified domestic/international search with fail-closed eligibility screening."""
from datetime import datetime, timezone
from backend.opportunity_filter import status as tender_status
from backend.global_opportunities import assess as global_assess

KINDS=("tender","supplier_registration","partnership","investment","subcontract")
def search_global(records, *, query="", country="", kind="", status="live", now=None):
    if status not in ("live","review","all"):
        raise ValueError("invalid status")
    if kind and kind not in KINDS:
        raise ValueError("invalid type")
    now=now or datetime.now(timezone.utc)
    results=[]
    for record in records:
        if not isinstance(record,dict):
            continue
        record_kind=record.get("type","tender")
        if kind and record_kind!=kind:
            continue
        if country and str(record.get("country","")).casefold()!=country.casefold():
            continue
        haystack=" ".join(str(record.get(k,"")) for k in
            ("title","issuer","reference","description","country","sector")).casefold()
        if query.casefold().strip() not in haystack:
            continue
        assessment=global_assess(record,now=now)
        # Only time-limited, independently issuer-verified tenders can be live.
        is_live=(record_kind=="tender" and tender_status(record,now)=="live" and
            assessment["shortlist_status"]=="eligible_for_commercial_review")
        if status=="live" and not is_live:
            continue
        if status=="review" and is_live:
            continue
        allowed=("title","issuer","reference","source_url","country","region","sector",
                 "currency","contract_value","type","closing_at","last_verified_at")
        row={k:record.get(k) for k in allowed}
        row["display_status"]="live" if is_live else "review_required"
        row["entry_barriers"]=assessment["entry_barriers"]
        row["missing_fields"]=assessment["missing_fields"]
        results.append(row)
    return {"count":len(results),"results":results,"generated_at":now.isoformat(),
        "notice":"International live listings require current issuer status and cleared entry checks. Other opportunity types remain in review."}
