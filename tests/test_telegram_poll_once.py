import json
from urllib.error import HTTPError
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path
from backend.telegram_poll_once import poll_once,process_update

class PollOnceTests(unittest.TestCase):
 def _mock(self, target, attribute, new):
  return mock.patch.object(target, attribute, new)
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
  self.assertEqual([x[0] for x in calls],["answerCallbackQuery","sendMessage"])
  self.assertIn("bc:sector:1",calls[1][1]["reply_markup"])
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
  self.assertEqual(calls[0][0],"answerCallbackQuery")
  self.assertEqual(calls[1][0],"editMessageText")
  self.assertEqual(calls[1][1]["message_id"],77)
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
  self.assertEqual(calls,["answerCallbackQuery","editMessageText","sendMessage"])
 def test_home_menu_has_news_button(self):
  calls=[]
  result=process_update({"message":{"chat":{"id":123},"text":"/start"}},
    send=lambda method,payload:calls.append((method,payload)),
    allowed_ids="123",database=self.db,ideas=[])
  self.assertEqual(result,"sent")
  self.assertIn("bc:news",calls[0][1]["reply_markup"])
 def test_news_command_no_arg_scans(self):
  import backend.telegram_poll_once as tpo
  calls=[]
  scanned={}
  def fake_scan(limit,workers,topic=None):
   scanned["yes"]=1
   scanned["topic"]=topic
   return [{"source":"FMT","title":"A headline","body_readable":True}],[]
  with self._mock(tpo,"news_agent",mock.Mock(scan=fake_scan,TOPIC_FEEDS={},FEEDS=[])):
   result=process_update({"message":{"chat":{"id":123},"text":"/news"}},
     send=lambda method,payload:calls.append((method,payload)),
     allowed_ids="123",database=self.db,ideas=[],token="tok")
  self.assertEqual(result,"sent")
  self.assertEqual(scanned.get("yes"),1)
  self.assertTrue(any("business feeds" in c[1].get("text","") or "sources" in c[1].get("text","") for c in calls))
 def test_news_command_with_url_builds_plan(self):
  import backend.telegram_poll_once as tpo
  calls=[]
  sent_docx=[]
  plan={"topic":"data centre hub","sector":"technology","horizon":"long",
    "potential_class":"high","signals":{"growth_score":9},"budget":{"total":400000,"band":"medium"},
    "risks":[{"score":6,"risk":"top risk"}]}
  def fake_plan(token,send,chat_id,url=None,job_id=None):
   plan["called_url"]=url
  def fake_docx(token,method,fields,field,path):
   sent_docx.append(path)
  with self._mock(tpo,"run_news_plan",mock.MagicMock(side_effect=fake_plan)), \
       self._mock(tpo,"_news_docx_send",mock.MagicMock(side_effect=fake_docx)):
   result=process_update({"message":{"chat":{"id":123},
     "text":"https://example.com/article"}},
     send=lambda method,payload:calls.append((method,payload)),
     allowed_ids="123",database=self.db,ideas=[],token="tok")
  self.assertEqual(result,"sent")
  self.assertEqual(plan.get("called_url"),"https://example.com/article")
 def test_newsplan_command_routes(self):
  import backend.telegram_poll_once as tpo
  calls=[]
  called={}
  def fake_plan(token,send,chat_id,url=None,job_id=None):
   called["yes"]=1
  with self._mock(tpo,"run_news_plan",mock.MagicMock(side_effect=fake_plan)):
   result=process_update({"message":{"chat":{"id":123},"text":"/newsplan"}},
     send=lambda method,payload:calls.append((method,payload)),
     allowed_ids="123",database=self.db,ideas=[],token="tok")
  self.assertEqual(result,"sent")
  self.assertEqual(called.get("yes"),1)
 def test_news_callback_help(self):
  calls=[]
  result=process_update({"callback_query":{"id":"cb","data":"bc:news",
    "message":{"chat":{"id":123}}}},
    send=lambda method,payload:calls.append((method,payload)),
    allowed_ids="123",database=self.db,ideas=[],token="tok")
  self.assertEqual(result,"sent")
  self.assertIn("News agent",calls[1][1]["text"])
  self.assertIn("bc:news:scan",calls[1][1]["reply_markup"])
if __name__=="__main__":unittest.main()
