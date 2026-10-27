"""Business research completeness and financial sensitivity without fabricated evidence."""
from decimal import Decimal
from backend.business_blueprint import financial_model, money

DOMAINS = {
 "market": ("market_size","market_growth","customer_segments","geography","demand_sources"),
 "customers": ("interviews","buyer_budget","purchase_frequency","sales_cycle","letters_of_intent"),
 "competition": ("direct_competitors","alternatives","price_benchmarks","differentiation"),
 "supply": ("supplier_quotes","lead_times","minimum_order","backup_supplier"),
 "operations": ("delivery_workflow","staffing","equipment","quality_assurance","data_protection"),
 "compliance": ("registration","permits","tax","insurance","contracts"),
 "commercial": ("pricing","channels","acquisition_cost","conversion_rate","retention"),
 "finance": ("startup_cost","fixed_cost","variable_cost","working_capital","funding","cashflow"),
 "risk": ("regulatory","supplier","demand","cash","technical","mitigation"),
}
def completeness(research):
    if not isinstance(research,dict):
        raise ValueError("research must be an object")
    report={}
    for domain,fields in DOMAINS.items():
        section=research.get(domain,{})
        if not isinstance(section,dict):
            section={}
        present=[field for field in fields if section.get(field) not in (None,"",[],{})]
        report[domain]={"present":present,"missing":[f for f in fields if f not in present],
                        "completeness_percent":round(100*len(present)/len(fields))}
    return {"domains":report,"all_fields_complete":all(not d["missing"] for d in report.values()),
            "note":"Completeness checks supplied fields, not their factual accuracy."}

def sensitivity(financials, multipliers=("0.5","1","1.5")):
    if not isinstance(financials,dict):
        raise ValueError("financials must be an object")
    base=financial_model(financials)
    if base["status"]!="scenario_only":
        return {"status":"insufficient_inputs","missing":base["missing"]}
    rows=[]
    for multiplier in multipliers:
        ratio=Decimal(str(multiplier))
        if not ratio.is_finite() or ratio<0:
            raise ValueError("invalid scenario multiplier")
        f=dict(financials)
        f["sales_per_month"]=int((money(financials["sales_per_month"])*ratio).to_integral_value(rounding="ROUND_FLOOR"))
        result=financial_model(f)
        rows.append({"sales_multiplier":str(ratio),"sales_per_month":f["sales_per_month"],
                     "monthly_revenue":result["monthly_revenue"],
                     "monthly_operating_profit":result["monthly_operating_profit"]})
    return {"status":"scenario_only","scenarios":rows,
            "note":"Illustrative volume sensitivity only; no forecast probability assigned."}
