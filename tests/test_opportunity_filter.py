import unittest
from datetime import datetime, timezone
from backend.opportunity_filter import search, status

NOW = datetime(2026,10,27,4,0,tzinfo=timezone.utc)
def item(**kw):
    d=dict(title="Office ICT supply", issuer="MBIP", reference="MBIP/S/235/2026",
           source_url="https://eperolehan2.mbip.gov.my/", sector="ICT", region="Johor",
           value=None, closing_at="2026-11-03T12:00:00+08:00",
           last_verified_at="2026-10-27T03:00:00+00:00",
           verification_status="issuer_verified", issuer_status="open")
    d.update(kw)
    return d

class LiveFilterTests(unittest.TestCase):
    def test_live_and_keyword(self):
        self.assertEqual(len(search([item()],query="office",now=NOW)),1)
    def test_expired_hidden(self):
        self.assertEqual(status(item(closing_at="2026-10-27T11:00:00+08:00"),NOW),"expired")
        self.assertEqual(search([item(closing_at="2026-10-27T11:00:00+08:00")],now=NOW),[])
    def test_unknown_deadline_hidden(self):
        self.assertEqual(search([item(closing_at=None)],now=NOW),[])
    def test_stale_hidden(self):
        self.assertEqual(status(item(last_verified_at="2026-10-24T00:00:00Z"),NOW),"stale")
    def test_not_issuer_verified_hidden(self):
        self.assertEqual(search([item(verification_status="unverified")],now=NOW),[])
    def test_missing_value_excluded_from_budget_filter(self):
        self.assertEqual(search([item()],min_value=0,now=NOW),[])
    def test_region_filter(self):
        self.assertEqual(search([item()],region="Sabah",now=NOW),[])
if __name__=="__main__":
    unittest.main()
