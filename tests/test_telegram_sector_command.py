import tempfile
import unittest
from pathlib import Path
from backend.telegram_poll_once import process_update
from backend.telegram_bot import show_page

class SectorCommandTests(unittest.TestCase):
    def test_sector_command_shows_keyboard(self):
        with tempfile.TemporaryDirectory() as folder:
            events=[]
            result=process_update(
                {"message":{"chat":{"id":123},"text":"/sector"}},
                send=lambda method,payload:events.append((method,payload)),
                allowed_ids="123",database=Path(folder)/"missing.sqlite3",ideas=[])
            self.assertEqual(result,"sent")
            self.assertIn("bc:sector:3",events[0][1]["reply_markup"])

    def test_pagination_has_real_newlines(self):
        with tempfile.TemporaryDirectory() as folder:
            msg,_=show_page("mode","ideas",0,Path(folder)/"missing.sqlite3",
                [{"title":"Solar servicing","sector":"Energy"}])
            self.assertIn("\n",msg)
            self.assertNotIn("\\n",msg)

if __name__=="__main__":
    unittest.main()
