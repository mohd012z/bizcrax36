"""Regression checks for read-only operations snapshot WSGI app."""
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from backend.ops_snapshot_wsgi import application

class SnapshotTests(unittest.TestCase):
    def call(self, method="GET", token="", path="/api/ops/snapshot"):
        result = {}
        def start(status, headers):
            result["status"] = status
            result["headers"] = dict(headers)
        environ = {"REQUEST_METHOD":method,"PATH_INFO":path,"HTTP_AUTHORIZATION":token}
        result["body"] = b"".join(application(environ, start))
        return result

    def test_fail_closed_without_token(self):
        with patch.dict(os.environ, {"OPS_SNAPSHOT_TOKEN":""}):
            self.assertTrue(self.call()["status"].startswith("401"))

    def test_rejects_invalid_token(self):
        with patch.dict(os.environ, {"OPS_SNAPSHOT_TOKEN":"secret"}):
            self.assertTrue(self.call(token="Bearer incorrect")["status"].startswith("401"))

    def test_rejects_mutations(self):
        with patch.dict(os.environ, {"OPS_SNAPSHOT_TOKEN":"secret"}):
            self.assertTrue(self.call(method="POST", token="Bearer secret")["status"].startswith("405"))

    def test_missing_snapshot(self):
        with patch.dict(os.environ, {"OPS_SNAPSHOT_TOKEN":"secret","OPS_SNAPSHOT_PATH":""}):
            self.assertTrue(self.call(token="Bearer secret")["status"].startswith("503"))

    def test_allowlisted_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            p = os.path.join(folder, "snapshot.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"counts":{"queued":2},"jobs":[{"id":"j1","status":"queued","secret":"do-not-leak"}],"logs":[],"quotas":[]},f)
            with patch.dict(os.environ, {"OPS_SNAPSHOT_TOKEN":"secret","OPS_SNAPSHOT_PATH":p}):
                r = self.call(token="Bearer secret")
            self.assertTrue(r["status"].startswith("200"))
            self.assertNotIn(b"do-not-leak",r["body"])
            self.assertEqual(json.loads(r["body"])["counts"]["queued"],2)

if __name__ == "__main__":
    unittest.main()
