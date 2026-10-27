"""BizCrax36: auditable 36-role research workflow.

Roles are executable validation/planning stages, not 36 independently running LLMs.
All input opportunities remain unverified until issuer evidence passes.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from pathlib import Path

GROUPS = {
 "discovery": ["sector_scan","demand_signals","government_tenders","private_rfqs","microbusiness","partnership_leads"],
 "deep_research": ["market_sizing","customer_segments","competitors","suppliers","pricing","source_crosscheck"],
 "financial": ["startup_costs","working_capital","revenue_scenarios","break_even","funding","cash_flow"],
 "risk": ["entity_identity","licensing","legal","operational","technical","evidence_quality"],
 "business_design": ["business_model","marketing","sales","delivery","collaboration","implementation_blueprint"],
 "reporting": ["executive_summary","evidence_appendix","financial_tables","risk_register","action_plan","dashboard_record"],
}
assert len(GROUPS) == 6 and all(len(v) == 6 for v in GROUPS.values())

@dataclass
class AgentResult:
    group: str
    agent: str
    status: str
    findings: list
    missing_evidence: list

def assess(record, now=None):
    """Deterministic baseline. No claim of AI reasoning or live external verification."""
    from backend.opportunity_filter import status as opportunity_status
    now = now or datetime.now(timezone.utc)
    state = opportunity_status(record, now=now)
    evidence = record.get("evidence", [])
    evidence = evidence if isinstance(evidence, list) else []
    valid_evidence = [e for e in evidence if isinstance(e, dict) and
                      e.get("source_url") and e.get("retrieved_at") and e.get("claim")]
    missing = []
    if state != "live":
        missing.append("issuer-confirmed open status, deadline, or fresh verification")
    if not valid_evidence:
        missing.append("claim-level evidence with source URL and retrieval date")
    return state, missing, valid_evidence

def run_workflow(record, now=None):
    if not isinstance(record, dict):
        raise TypeError("opportunity must be an object")
    state, missing, evidence = assess(record, now)
    results = []
    for group, agents in GROUPS.items():
        for agent in agents:
            results.append(asdict(AgentResult(
                group=group, agent=agent,
                status="needs_evidence" if missing else "ready_for_specialist_analysis",
                findings=[], missing_evidence=missing.copy())))
    return {
        "schema_version": 1, "title": str(record.get("title", "")),
        "source_url": record.get("source_url"),
        "opportunity_status": state, "investment_ready": False,
        "agent_count": len(results), "agents": results,
        "verified_claim_count": 0,
        "evidence_items_present": len(evidence),
        "missing_evidence": missing,
        "note": "Planning workflow only. No autonomous LLM agent, financial forecast, or source verification executed.",
    }

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/workflow-report.json"))
    args = parser.parse_args()
    result = run_workflow(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"36 stages planned; opportunity={result['opportunity_status']}; output={args.output}")

if __name__ == "__main__":
    main()
