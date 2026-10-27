import unittest
from unittest.mock import patch
import io
from backend.source_monitor import Text, fetch

class MonitorTests(unittest.TestCase):
    def test_visible_text_ignores_scripts(self):
        p = Text()
        p.feed("<html><style>secret</style><p>Public notice</p><script>hidden</script></html>")
        self.assertEqual(p.parts, ["Public notice"])

    def test_failed_fetch_is_not_verified(self):
        with patch("backend.source_monitor.urllib.request.urlopen", side_effect=OSError("offline")):
            r = fetch("test", "https://example.org")
        self.assertEqual(r["status"], "fetch_failed")
        self.assertEqual(r["verified_opportunities"], 0)

    def test_success_is_still_unverified(self):
        class Response:
            status = 200
            headers = type("Headers", (), {"get_content_type": lambda self: "text/html", "get_content_charset": lambda self: "utf-8"})()
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, n): return ("<p>" + "Public tender notice " * 20 + "</p>").encode()
        with patch("backend.source_monitor.urllib.request.urlopen", return_value=Response()):
            r = fetch("test", "https://example.org")
        self.assertEqual(r["status"], "page_retrieved_unverified")
        self.assertEqual(r["verified_opportunities"], 0)
        self.assertEqual(len(r["sha256"]), 64)

if __name__ == "__main__":
    unittest.main()
