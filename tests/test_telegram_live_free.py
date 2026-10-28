import unittest
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
