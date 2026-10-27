import unittest
from datetime import datetime, timezone
from backend.orchestrator import GROUPS, run_workflow

NOW=datetime(2026,10,27,4,tzinfo=timezone.utc)
class WorkflowTests(unittest.TestCase):
    def test_exactly_36_roles(self):
        self.assertEqual(sum(map(len,GROUPS.values())),36)
        self.assertEqual(len(set(a for agents in GROUPS.values() for a in agents)),36)
    def test_unverified_is_never_investment_ready(self):
        r=run_workflow({"title":"Unverified offer"},now=NOW)
        self.assertEqual(r["agent_count"],36)
        self.assertFalse(r["investment_ready"])
        self.assertTrue(all(x["status"]=="needs_evidence" for x in r["agents"]))
    def test_evidence_does_not_automatically_verify_claims(self):
        r=run_workflow({"title":"Example","reference":"X","source_url":"https://example.org",
          "closing_at":"2026-11-10T12:00:00+08:00","last_verified_at":"2026-10-27T03:00:00Z",
          "verification_status":"issuer_verified","issuer_status":"open",
          "evidence":[{"claim":"Test","source_url":"https://example.org","retrieved_at":"2026-10-27"}]},now=NOW)
        self.assertEqual(r["opportunity_status"],"live")
        self.assertEqual(r["verified_claim_count"],0)
        self.assertFalse(r["investment_ready"])
if __name__=="__main__":unittest.main()
