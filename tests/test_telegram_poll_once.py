import json
from urllib.error import HTTPError
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
 def test_callback_edits_existing_menu(self):
  calls=[]
  result=process_update({"callback_query":{"id":"cb","data":"bc:sectors",
    "message":{"message_id":77,"chat":{"id":123}}}},
    send=lambda method,payload:calls.append((method,payload)),
    allowed_ids="123",database=self.db,ideas=[])
  self.assertEqual(result,"sent")
  self.assertEqual(calls[0][0],"editMessageText")
  self.assertEqual(calls[0][1]["message_id"],77)
  self.assertEqual(calls[1][0],"answerCallbackQuery")
 def test_repeated_start_collapsed(self):
  calls=[]
  def fake(token,method,payload):
   calls.append((method,payload))
   if method=="getUpdates":
    if "offset" in payload:return []
    return [{"update_id":1,"message":{"chat":{"id":123},"text":"/start"}},
      {"update_id":2,"message":{"chat":{"id":123},"text":"/start"}},
      {"update_id":3,"message":{"chat":{"id":123},"text":"/search energy"}}]
   return {}
  self.assertEqual(poll_once("token","123",self.db,[],telegram_api=fake),3)
  self.assertEqual(sum(1 for m,_ in calls if m=="sendMessage"),2)
 def test_stale_menu_edit_falls_back(self):
  calls=[]
  def send(method,payload):
   calls.append(method)
   if method=="editMessageText":
    raise HTTPError("https://example.invalid",400,"not editable",{},None)
  result=process_update({"callback_query":{"id":"cb","data":"bc:sectors",
    "message":{"message_id":77,"chat":{"id":123}}}},
    send=send,allowed_ids="123",database=self.db,ideas=[])
  self.assertEqual(result,"sent")
  self.assertEqual(calls,["editMessageText","sendMessage","answerCallbackQuery"])
if __name__=="__main__":unittest.main()
