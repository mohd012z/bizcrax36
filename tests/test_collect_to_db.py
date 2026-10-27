import tempfile
import unittest
from pathlib import Path
from backend.collect_to_db import collect
from backend.search_api import load_records
class CollectionIntegrationTests(unittest.TestCase):
 def test_discovery_persists_but_not_live(self):
  with tempfile.TemporaryDirectory() as temp:
   db=Path(temp)/"audit.sqlite3"
   out=Path(temp)/"snapshot.json"
   def fake_fetch(query,limit):
    return {"notices":[{"publication-number":"123456-2026","notice-title":"Research sample"}]},"f"*64
   result=collect(db,out,fetch=fake_fetch)
   self.assertEqual(result["discovered"],1)
   self.assertEqual(result["verified_live"],0)
   rows=load_records(db)
   self.assertEqual(len(rows),1)
   self.assertEqual(rows[0]["verification_status"],"source_matched")
   self.assertIsNone(rows[0]["last_verified_at"])
   self.assertTrue(out.exists())
if __name__=="__main__":unittest.main()
