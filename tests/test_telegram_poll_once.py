import json
import tempfile
import unittest
from pathlib import Path
from backend.telegram_poll_once import poll_once,process_update

class PollOnceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.db=Path(self.tmp.name)/"empty.sqlite3"
 def test_start_delivers_inline_menu(self):
  calls=[]
  result=process_update({"message":{"chat":{"id":123},"text":"/start"}},
    send=lambda method,payload:calls.append((method,payload)),
    allowed_ids="123",database=self.db,ideas=[])
  self.assertEqual(result,"sent")
  self.assertIn("inline_keyboard",calls[0][1]["reply_markup"])
 def test_callback_sector_menu(self):
  calls=[]
  result=process_update({"callback_query":{"id":"abc","data":"bc:sectors",
      "message":{"chat":{"id":123}}}},
    send=lambda method,payload:calls.append((method,payload)),
    allowed_ids="123",database=self.db,ideas=[])
  self.assertEqual(result,"sent")
  self.assertEqual([x[0] for x in calls],["sendMessage","answerCallbackQuery"])
  self.assertIn("bc:sector:1",calls[0][1]["reply_markup"])
 def test_unauthorized_denied(self):
  calls=[]
  result=process_update({"message":{"chat":{"id":999},"text":"/start"}},
    send=lambda method,payload:calls.append(method),
    allowed_ids="123",database=self.db,ideas=[])
  self.assertEqual(result,"denied")
  self.assertEqual(calls,[])
 def test_ack_after_success(self):
  methods=[]
  def fake(token,method,payload):
   methods.append(method)
   if method=="getUpdates":
    if "offset" in payload:return []
    return [{"update_id":3,"message":{"chat":{"id":123},"text":"/start"}}]
   return {}
  self.assertEqual(poll_once("token","123",self.db,[],telegram_api=fake),1)
  self.assertEqual(methods,["getUpdates","sendMessage","getUpdates"])
 def test_failed_delivery_not_acked(self):
  methods=[]
  def fake(token,method,payload):
   methods.append(method)
   if method=="getUpdates":
    return [{"update_id":3,"message":{"chat":{"id":123},"text":"/start"}}]
   raise RuntimeError("delivery failed")
  with self.assertRaises(RuntimeError):
   poll_once("token","123",self.db,[],telegram_api=fake)
  self.assertEqual(methods,["getUpdates","sendMessage"])
if __name__=="__main__":unittest.main()
