"""Static safety checks for the isolated operations dashboard shell."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "ops-dashboard" / "index.html"
MANIFEST = ROOT / "ops-dashboard" / "manifest.webmanifest"

class OperationsDashboardStaticTests(unittest.TestCase):
    def test_files_exist(self):
        self.assertTrue(HTML.is_file())
        self.assertTrue(MANIFEST.is_file())

    def test_read_only_and_bounded_refresh(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("/api/ops/snapshot", html)
        self.assertIn("credentials:'same-origin'", html)
        self.assertIn("document.hidden", html)
        self.assertIn("60000", html)
        self.assertIn("<button disabled>Retry</button>", html)
        self.assertIn("<button disabled>Resume</button>", html)
        self.assertIn("<button disabled>Reclaim</button>", html)
        self.assertNotIn("TELEGRAM_BOT_TOKEN", html)
        self.assertNotIn("OPS_DATABASE_URL", html)

    def test_manifest_valid(self):
        import json
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["start_url"], "./index.html")

if __name__ == "__main__":
    unittest.main()
