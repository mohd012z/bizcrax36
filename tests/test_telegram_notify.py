import json
import tempfile
import unittest
from pathlib import Path
from backend.telegram_notify import build_digest,send
class TelegramNotifyTests(unittest.TestCase):
 def test_digest_from_ideas(self):
  with tempfile.TemporaryDirectory() as temp:
   msg=build_digest(Path(temp)/"missing.sqlite3",[{"title":"Solar monitoring","sector":"Energy"}])
   self.assertIn("Solar monitoring",msg)
   self.assertIn("unverified",msg)
 def test_send_uses_configured_chat(self):
  captured=[]
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self,n):return json.dumps({"ok":True,"result":{}}).encode()
  def fake_open(req,timeout):
   captured.append(req.data.decode())
   return Response()
  self.assertTrue(send("test-token","123","Hello",opener=fake_open))
  self.assertIn("chat_id=123",captured[0])
 def test_missing_secret_rejected(self):
  with self.assertRaises(ValueError):send("","123","Hello")
if __name__=="__main__":unittest.main()
