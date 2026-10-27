import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from backend.discovery_pipeline import save
from backend.search_api import load_records, query_records

NOW=datetime(2026,10,27,4,tzinfo=timezone.utc)
def record(**updates):
    base={"title":"Facility maintenance","issuer":"Sample Authority","reference":"R-1",
          "source_url":"https://example.org/notice","closing_at":"2026-11-03T12:00:00+08:00",
          "last_verified_at":"2026-10-27T03:00:00Z","verification_status":"issuer_verified",
          "issuer_status":"open","sector":"Facilities","region":"Sarawak",
          "checked_at":"2026-10-27T03:00:00Z"}
    base.update(updates)
    return base

class SearchApiTests(unittest.TestCase):
    def test_verified_live_and_search(self):
        result=query_records([record()],{"q":["maintenance"],"status":["live"]},NOW)
        self.assertEqual(result["count"],1)
        self.assertEqual(result["results"][0]["display_status"],"live")
    def test_expired_not_live(self):
        result=query_records([record(closing_at="2026-10-26T10:00:00Z")],{"status":["live"]},NOW)
        self.assertEqual(result["count"],0)
    def test_unverified_not_live(self):
        result=query_records([record(verification_status="source_matched")],{"status":["live"]},NOW)
        self.assertEqual(result["count"],0)
    def test_review_shows_unverified(self):
        result=query_records([record(verification_status="source_matched")],{"status":["review"]},NOW)
        self.assertEqual(result["count"],1)
    def test_db_deduplicates_latest(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"audit.db"
            save(path,[record(checked_at="2026-10-26T03:00:00Z",title="old")])
            save(path,[record(checked_at="2026-10-27T03:00:00Z",title="new")])
            records=load_records(path)
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]["title"],"new")
    def test_bad_status_rejected(self):
        with self.assertRaises(ValueError):
            query_records([],{"status":["nonsense"]},NOW)
if __name__=="__main__":
    unittest.main()
