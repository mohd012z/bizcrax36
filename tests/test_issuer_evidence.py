import unittest
from datetime import datetime,timezone
from backend.issuer_evidence import verify_issuer_notice
NOW=datetime(2026,10,27,12,tzinfo=timezone.utc)
C={"title":"School software","reference":"X-2","source_url":"https://issuer.example/notice",
   "closing_at":"2026-11-01T12:00:00+00:00","timezone":"UTC"}
E={"adapter":"issuer_structured_notice_v1","issuer_url":C["source_url"],"reference":"X-2",
   "title":"School software","status":"open","closing_at":C["closing_at"],
   "retrieved_at":"2026-10-27T11:00:00Z","evidence_sha256":"a"*64}
class EvidenceTests(unittest.TestCase):
 def test_explicit_evidence(self):
  self.assertEqual(verify_issuer_notice(C,E,NOW)["display_status"],"live")
 def test_html_match_is_not_enough(self):
  self.assertEqual(verify_issuer_notice(C,{},NOW)["verification_status"],"unverified")
 def test_closed_is_not_live(self):
  self.assertNotEqual(verify_issuer_notice(C,{**E,"status":"closed"},NOW)["display_status"],"live")
 def test_mismatch_fails(self):
  self.assertEqual(verify_issuer_notice(C,{**E,"reference":"other"},NOW)["verification_status"],"unverified")
 def test_stale_fails(self):
  self.assertEqual(verify_issuer_notice(C,{**E,"retrieved_at":"2026-10-25T11:00:00Z"},NOW)["verification_status"],"unverified")
if __name__=="__main__":unittest.main()
