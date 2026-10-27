import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from backend.telegram_poll_once import poll_once

class DiagnosticTests(unittest.TestCase):
    def test_denied_chat_counted_without_identifier(self):
        calls=[]
        def fake(token,method,payload):
            calls.append(method)
            if method=="getUpdates":
                if "offset" in payload:
                    return []
                return [{"update_id":10,"message":{"chat":{"id":999},"text":"/start"}}]
            return {}
        with tempfile.TemporaryDirectory() as folder:
            output=io.StringIO()
            with redirect_stdout(output):
                count=poll_once("fake","123",Path(folder)/"missing.db",[],telegram_api=fake)
        self.assertEqual(count,1)
        self.assertIn('"denied": 1',output.getvalue())
        self.assertNotIn("999",output.getvalue())
        self.assertNotIn("fake",output.getvalue())
        self.assertNotIn("sendMessage",calls)

if __name__=="__main__":
    unittest.main()
