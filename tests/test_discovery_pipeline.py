import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from backend.discovery_pipeline import verify, save, normalize

NOW=datetime(2026,10,27,4,tzinfo=timezone.utc)
BASE={"title":"Office supplies","reference":"ABC-2026","source_url":"https://www.sc.com.my/procurement",
      "closing_at":"2026-11-10T12:00:00+08:00"}
class DiscoveryTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize("  A   B  "),"a b")
    def test_matching_source_does_not_claim_open(self):
        r=verify(BASE,fetch=lambda url:("ABC-2026 Office supplies","sha256"),now=NOW)
        self.assertEqual(r["verification_status"],"source_matched")
        self.assertEqual(r["issuer_status"],"unknown")
        self.assertIsNone(r["last_verified_at"])
    def test_missing_title_fails_closed(self):
        r=verify(BASE,fetch=lambda url:("ABC-2026 only","sha256"),now=NOW)
        self.assertEqual(r["verification_status"],"unverified")
    def test_network_failure_fails_closed(self):
        def broken(url): raise TimeoutError("offline")
        r=verify(BASE,fetch=broken,now=NOW)
        self.assertEqual(r["verification_status"],"unverified")
    def test_sqlite_audit(self):
        r=verify(BASE,fetch=lambda url:("ABC-2026 Office supplies","hash"),now=NOW)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"research.db"
            save(path,[r])
            import sqlite3
            with sqlite3.connect(path) as c:
                self.assertEqual(c.execute("SELECT count(*) FROM research_records").fetchone()[0],1)
if __name__=="__main__":unittest.main()
