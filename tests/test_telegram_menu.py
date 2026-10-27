import json
import tempfile
import unittest
from pathlib import Path
from backend.telegram_menu import home,sectors,resolve,paged_menu
from backend.telegram_bot import handle_callback

class MenuTests(unittest.TestCase):
 def test_home_has_inline_buttons(self):
  data=json.loads(home())
  self.assertTrue(data["inline_keyboard"])
  self.assertIn("bc:mode:ideas",str(data))
 def test_sector_submenu(self):
  self.assertIn("bc:sector:3",sectors())
 def test_rejects_untrusted_callback(self):
  self.assertIsNone(resolve("bc:mode:admin"))
  self.assertIsNone(resolve("bc:sector:999"))
 def test_ideas_button(self):
  with tempfile.TemporaryDirectory() as temp:
   text,markup=handle_callback("bc:mode:ideas",Path(temp)/"empty.db",
      [{"title":"Solar maintenance","sector":"Energy"}])
   self.assertIn("Solar maintenance",text)
   self.assertIn("inline_keyboard",markup)
 def test_start_menu(self):
  with tempfile.TemporaryDirectory() as temp:
   text,markup=handle_callback("bc:home",Path(temp)/"empty.db",[])
   self.assertIn("choose",text)
   self.assertIn("bc:sectors",markup)
 def test_next_previous_callbacks(self):
  markup=json.loads(paged_menu("mode","ideas",1,3))
  data=[b["callback_data"] for row in markup["inline_keyboard"] for b in row]
  self.assertIn("bc:page:mode:ideas:0",data)
  self.assertIn("bc:page:mode:ideas:2",data)
  self.assertEqual(resolve("bc:page:mode:ideas:2"),"bc:page:mode:ideas:2")
  self.assertIsNone(resolve("bc:page:mode:admin:2"))
 def test_pagination_reaches_second_page(self):
  with tempfile.TemporaryDirectory() as temp:
   ideas=[{"title":f"Energy idea {i}","sector":"Energy","country":"Malaysia"} for i in range(12)]
   text,markup=handle_callback("bc:page:mode:ideas:1",Path(temp)/"empty.db",ideas)
   self.assertIn("Page 2/3",text)
   self.assertIn("Energy idea",text)
   self.assertIn("Previous",markup)
if __name__=="__main__":unittest.main()
