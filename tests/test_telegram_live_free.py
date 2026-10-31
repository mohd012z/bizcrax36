import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from backend.telegram_live_free import process_live

class LiveMenuTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.sent_files=[]
        self.records={}
        self.send=lambda method,payload: self.calls.append((method,payload)) or {"ok":True}
        self.upload=lambda chat,name,data,caption: self.sent_files.append((chat,name,data,caption))

    def run_update(self,update):
        return process_live(update,token="test-token",allowed_ids="42",
            database="unused.sqlite3",ideas=[],send=self.send,
            download=lambda file_id: b'{"schema_version":1,"records":[{"id":"a","title":"Test","source_url":"https://example.org","status":"review_required"}]}',
            upload=self.upload,store=self.records)

    def test_worker_initializes_nested_update_ledger(self):
        from backend.telegram_live_free import main
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "nested" / "updates.sqlite3"
            env = {"TELEGRAM_BOT_TOKEN": "test-token",
                   "TELEGRAM_ALLOWED_CHAT_IDS": "42",
                   "BIZCRAX_UPDATE_DB": str(ledger)}
            def fake_api(token, method, payload):
                if method == "getWebhookInfo":
                    return {}
                if method == "getUpdates":
                    raise KeyboardInterrupt
                raise AssertionError(method)
            with patch.dict(os.environ, env), \
                 patch("backend.telegram_live_free.api", side_effect=fake_api), \
                 patch("backend.telegram_live_free.register", return_value=[]), \
                 patch("backend.telegram_live_free.load_ideas", return_value=[]):
                with self.assertRaises(KeyboardInterrupt):
                    main()
            self.assertTrue(ledger.is_file())

    def test_start_shows_aligned_menu(self):
        self.run_update({"message":{"chat":{"id":42},"text":"/start"}})
        markup=self.calls[-1][1]["reply_markup"]
        import json
        rows=json.loads(markup)["inline_keyboard"]
        self.assertEqual([len(row) for row in rows],[2,2,2,2,1])

    def test_upload_export_roundtrip(self):
        self.run_update({"message":{"chat":{"id":42},"document":{"file_id":"f1","file_name":"leads.json","file_size":100}}})
        self.assertEqual(len(self.records[42]),1)
        self.run_update({"message":{"chat":{"id":42},"text":"/export csv"}})
        self.assertEqual(self.sent_files[0][1],"bizcrax-export.csv")
        self.assertIn(b"review_required",self.sent_files[0][2])

    def test_unauthorized_upload_rejected(self):
        result=self.run_update({"message":{"chat":{"id":99},"document":{"file_id":"f1","file_name":"leads.json"}}})
        self.assertEqual(result,"denied")
        self.assertEqual(self.records,{})

    def test_bad_extension(self):
        self.run_update({"message":{"chat":{"id":42},"document":{"file_id":"f1","file_name":"malware.exe"}}})
        self.assertIn("JSON and CSV",self.calls[-1][1]["text"])

if __name__=="__main__":
    unittest.main()
