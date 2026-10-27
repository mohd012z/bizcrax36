import json
import tempfile
import unittest
from pathlib import Path
from backend.telegram_menu import home,sectors,resolve
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
if __name__=="__main__":unittest.main()
