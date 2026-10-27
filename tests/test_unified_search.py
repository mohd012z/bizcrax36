import unittest
from datetime import datetime,timezone
from backend.unified_search import one_search
NOW=datetime(2026,10,27,4,tzinfo=timezone.utc)
class UnifiedTests(unittest.TestCase):
    def test_idea_search(self):
        result=one_search([], [{"title":"OCR service","sector":"Technology","country":"Malaysia"}],query="OCR",now=NOW)
        self.assertEqual(result["count"],1)
        self.assertFalse(result["results"][0]["verified"])
    def test_idea_not_live(self):
        result=one_search([], [{"title":"OCR service"}],mode="live",now=NOW)
        self.assertEqual(result["count"],0)
    def test_expired_notice_hidden_live(self):
        r={"title":"Old tender","reference":"A","source_url":"https://example.org",
           "closing_at":"2026-10-20T12:00:00Z","issuer_status":"open",
           "verification_status":"issuer_verified","last_verified_at":"2026-10-27T03:00:00Z"}
        self.assertEqual(one_search([r],[],mode="live",now=NOW)["count"],0)
    def test_invalid_mode(self):
        with self.assertRaises(ValueError):one_search([],[],mode="bad",now=NOW)
if __name__=="__main__":unittest.main()
