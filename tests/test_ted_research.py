import unittest
from datetime import datetime,timezone
from backend.ted_research import normalize,request_notices
class TedResearchTests(unittest.TestCase):
 def test_publication_never_marked_live(self):
  r=normalize({"notices":[{"publication-number":"123456-2026","notice-title":"School software"}]},"a"*64,
    datetime(2026,10,27,tzinfo=timezone.utc))
  self.assertEqual(len(r),1)
  self.assertEqual(r[0]["verification_status"],"source_matched")
  self.assertEqual(r[0]["issuer_status"],"unknown")
  self.assertIsNone(r[0]["closing_at"])
 def test_bad_refs_discarded(self):
  self.assertEqual(normalize({"notices":[{"publication-number":"../../etc/passwd"}]},"a"),[])
 def test_query_limits(self):
  with self.assertRaises(ValueError):request_notices("x",limit=0)
 def test_missing_notices(self):
  self.assertEqual(normalize({},"a"),[])
if __name__=="__main__":unittest.main()
