import unittest
from datetime import datetime,timezone
from backend.global_search import search_global
NOW=datetime(2026,10,27,4,tzinfo=timezone.utc)
BASE={"title":"Sample facilities tender","issuer":"Example","reference":"INT-1",
      "source_url":"https://example.org/tender","country":"Singapore","region":"ASEAN",
      "currency":"SGD","contract_value":0,"type":"tender","entry_mode":"direct",
      "eligibility":"international","deadline_or_ongoing":"2026-11-10",
      "closing_at":"2026-11-10T12:00:00+08:00","last_verified_at":"2026-10-27T03:00:00Z",
      "verification_status":"issuer_verified","issuer_status":"open",
      "foreign_bidder_eligible":True,"local_partner_confirmed":True,"licensing_checked":True,
      "tax_and_currency_checked":True,"bonding_checked":True,"sanctions_checked":True}
class GlobalSearchTests(unittest.TestCase):
    def test_eligible_live_tender(self):
        self.assertEqual(search_global([BASE],now=NOW)["count"],1)
    def test_missing_foreign_eligibility_hidden(self):
        r={**BASE,"foreign_bidder_eligible":False}
        self.assertEqual(search_global([r],now=NOW)["count"],0)
        self.assertEqual(search_global([r],status="review",now=NOW)["count"],1)
    def test_expired_hidden(self):
        r={**BASE,"closing_at":"2026-10-26T12:00:00Z"}
        self.assertEqual(search_global([r],now=NOW)["count"],0)
    def test_country_filter(self):
        self.assertEqual(search_global([BASE],country="Australia",now=NOW)["count"],0)
    def test_non_tender_not_live(self):
        r={**BASE,"type":"partnership"}
        self.assertEqual(search_global([r],now=NOW)["count"],0)
if __name__=="__main__":unittest.main()
