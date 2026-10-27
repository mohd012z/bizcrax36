"""Global opportunity eligibility and commercial triage.

Does not assert that external tenders are live, genuine or accessible.
No arbitrary contract-value threshold; zero and undisclosed values are accepted.
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from backend.opportunity_filter import status as tender_status

REGIONS = {
 "asean": ("Singapore","Indonesia","Thailand","Vietnam","Philippines","Brunei","Cambodia","Laos","Myanmar","Timor-Leste","Malaysia"),
 "middle_east": ("United Arab Emirates","Saudi Arabia","Qatar","Oman","Bahrain","Kuwait"),
 "europe": ("United Kingdom","Germany","France","Netherlands","Spain","Italy","Poland"),
 "north_america": ("United States","Canada","Mexico"),
 "oceania": ("Australia","New Zealand"),
 "africa": ("South Africa","Kenya","Nigeria","Egypt","Morocco"),
 "south_asia": ("India","Bangladesh","Sri Lanka","Pakistan"),
 "east_asia": ("Japan","South Korea","Taiwan","China"),
 "latin_america": ("Brazil","Chile","Colombia","Peru"),
}
SOURCES = [
 {"id":"ungm","url":"https://www.ungm.org/Public/Notice","coverage":"UN procurement"},
 {"id":"ted","url":"https://ted.europa.eu/","coverage":"European public procurement"},
 {"id":"worldbank","url":"https://projects.worldbank.org/en/projects-operations/opportunities","coverage":"World Bank project opportunities"},
 {"id":"adb","url":"https://www.adb.org/projects/tenders","coverage":"Asian Development Bank procurement"},
 {"id":"sam","url":"https://sam.gov/","coverage":"United States federal contracting"},
 {"id":"austender","url":"https://www.tenders.gov.au/","coverage":"Australian government procurement"},
 {"id":"gebiz","url":"https://www.gebiz.gov.sg/","coverage":"Singapore public procurement"},
]
REQUIRED = ("country","issuer","title","source_url","reference","entry_mode",
            "eligibility","deadline_or_ongoing","currency","contract_value")

def value_class(raw):
    if raw is None or raw == "":
        return "undisclosed"
    try:
        amount=Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return "invalid"
    if not amount.is_finite() or amount < 0:
        return "invalid"
    return "disclosed"

def assess(project, now=None):
    if not isinstance(project,dict):
        raise ValueError("project must be an object")
    missing=[k for k in REQUIRED if k not in project or project[k] in ("",None)]
    # Undisclosed value is a legitimate state and is not a disqualifier.
    if "contract_value" in missing and "contract_value" in project and project["contract_value"] is None:
        missing.remove("contract_value")
    kind=project.get("type","tender")
    if kind not in ("tender","supplier_registration","partnership","investment","subcontract"):
        missing.append("supported opportunity type")
    value=value_class(project.get("contract_value"))
    if value=="invalid":
        missing.append("valid contract_value")
    tender_state=tender_status(project,now=now) if kind=="tender" else "not_applicable"
    barriers=[]
    if not project.get("foreign_bidder_eligible"):
        barriers.append("foreign bidder eligibility unconfirmed")
    if not project.get("local_partner_confirmed"):
        barriers.append("local partner or direct-entry feasibility unconfirmed")
    if not project.get("licensing_checked"):
        barriers.append("country and sector licensing unconfirmed")
    if not project.get("tax_and_currency_checked"):
        barriers.append("tax, FX and payment terms unconfirmed")
    if not project.get("bonding_checked"):
        barriers.append("bid/performance bonds and working capital unconfirmed")
    if not project.get("sanctions_checked"):
        barriers.append("sanctions and counterparty checks unconfirmed")
    return {
      "title":project.get("title"),"country":project.get("country"),
      "type":kind,"contract_value_class":value,"currency":project.get("currency"),
      "missing_fields":sorted(set(missing)),"entry_barriers":barriers,
      "tender_status":tender_state,
      "shortlist_status":"review_required" if missing or barriers or (kind=="tender" and tender_state!="live") else "eligible_for_commercial_review",
      "investment_ready":False,
      "note":"Eligibility for commercial review does not imply issuer validation, award probability or investment suitability."
    }

def rank_for_research(projects,now=None):
    rows=[assess(p,now) for p in projects]
    return sorted(rows,key=lambda r:(len(r["missing_fields"])+len(r["entry_barriers"]),
      r["title"] or ""))
