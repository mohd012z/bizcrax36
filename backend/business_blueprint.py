"""Evidence-led business project blueprint builder (stdlib, no AI or invented research)."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import argparse
import json
from pathlib import Path

STAGES = [
 ("Discovery", "Define buyer, pain point, geographic market and existing alternatives"),
 ("Evidence", "Collect dated original sources, customer interviews and supplier quotations"),
 ("Legal", "Confirm entity eligibility, licensing, insurance and professional obligations"),
 ("Offer", "Define scope, deliverables, acceptance criteria, support and price"),
 ("Pilot", "Obtain consent and run a limited paid pilot; record actual delivery costs"),
 ("Sales", "Create outreach, qualification, proposal and follow-up process"),
 ("Operations", "Document suppliers, staffing, quality control, privacy and contingency plans"),
 ("Finance", "Reconcile setup cost, variable cost, fixed cost, cash runway and break-even"),
 ("Review", "Compare measured results to thresholds; scale, pivot or stop"),
]
REQUIRED = ("id","name","sector","horizon","target_customers","problem","solution","region",
            "evidence","competitors","suppliers","legal_requirements","marketing_channels",
            "operating_steps","risks","assumptions","financials")

def money(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not money")
    try:
        number=Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError("invalid financial number")
    if not number.is_finite() or number < 0:
        raise ValueError("financial numbers must be finite and nonnegative")
    return number

def financial_model(f):
    required=("startup_cost","price_per_sale","variable_cost_per_sale","monthly_fixed_cost","sales_per_month","cash_available")
    missing=[k for k in required if k not in f or f[k] is None]
    if missing:
        return {"status":"insufficient_inputs","missing":missing}
    startup,price,variable,fixed,volume,cash=(money(f[k]) for k in required)
    if volume != volume.to_integral_value():
        raise ValueError("sales_per_month must be a whole number")
    contribution=price-variable
    revenue=price*volume
    monthly_profit=contribution*volume-fixed
    breakeven=None if contribution<=0 else int((fixed/contribution).to_integral_value(rounding="ROUND_CEILING"))
    return {"status":"scenario_only","currency":"MYR",
        "monthly_revenue":str(revenue),"monthly_operating_profit":str(monthly_profit),
        "contribution_per_sale":str(contribution),"break_even_sales_per_month":breakeven,
        "startup_funding_gap":str(max(Decimal(0),startup-cash)),
        "cash_after_startup":str(cash-startup),
        "note":"Illustrative scenario, not a forecast. Taxes, debt, capex depreciation and timing excluded."}

def build_plan(project):
    if not isinstance(project,dict):
        raise ValueError("project must be an object")
    missing=[k for k in REQUIRED if k not in project or project[k] in (None,"",[])]
    if project.get("horizon") not in ("short","long"):
        missing.append("horizon must be short or long")
    evidence=project.get("evidence",[])
    if not isinstance(evidence,list):
        raise ValueError("evidence must be an array")
    valid=[e for e in evidence if isinstance(e,dict) and all(e.get(k) for k in
           ("claim","source_url","retrieved_at","source_type"))]
    buyer_count=sum(1 for e in valid if e.get("source_type")=="customer_interview")
    supplier_count=sum(1 for e in valid if e.get("source_type")=="supplier_quote")
    model=financial_model(project.get("financials") or {})
    gates={
      "input_complete":not missing,
      "has_traceable_evidence":len(valid)>0,
      "customer_validation":buyer_count>=3,
      "supplier_validation":supplier_count>=2,
      "financial_scenario_calculated":model["status"]=="scenario_only",
      "legal_requirements_reviewed":False,
      "commercially_validated":False,
    }
    tasks=[{"stage":name,"action":action,"state":"pending","owner":"unassigned",
            "evidence_required":True} for name,action in STAGES]
    return {"schema_version":1,"generated_at":datetime.now(timezone.utc).isoformat(),
      "project_id":project.get("id"),"project_name":project.get("name"),
      "horizon":project.get("horizon"),"missing_inputs":sorted(set(missing)),
      "evidence_count":len(valid),"evidence_unvalidated_count":len(valid),
      "evidence":valid,"gates":gates,"financial_model":model,
      "research_sections":{k:project.get(k) for k in ("sector","region","target_customers","problem",
          "solution","competitors","suppliers","legal_requirements","marketing_channels",
          "operating_steps","risks","assumptions")},
      "execution_plan":tasks,"ready_to_launch":False,
      "disclaimer":"Evidence metadata not independently authenticated; verify with issuers, customers, suppliers and qualified advisers."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("input",type=Path)
    p.add_argument("--output",type=Path,default=Path("data/business-blueprint.json"))
    args=p.parse_args()
    report=build_plan(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("ready_to_launch=false; missing_inputs="+str(len(report["missing_inputs"])))
if __name__=="__main__":
    main()
