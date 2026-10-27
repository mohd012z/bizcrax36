import tempfile
import unittest
from pathlib import Path
from backend.telegram_bot import allowed,search_text
class TelegramTests(unittest.TestCase):
 def test_denies_unlisted_chat(self):
  self.assertFalse(allowed(42,""))
  self.assertFalse(allowed(42,"13,99"))
  self.assertTrue(allowed(42,"13,42"))
 def test_help_without_db(self):
  self.assertIn("/search",search_text("/help",Path("/nonexistent"),[]))
 def test_ideas_search(self):
  with tempfile.TemporaryDirectory() as d:
   result=search_text("/ideas energy",Path(d)/"missing.sqlite3",
       [{"title":"Energy monitoring","sector":"Energy","country":"Malaysia"}])
   self.assertIn("Energy monitoring",result)
   self.assertIn("research_hypothesis",result)
 def test_live_excludes_ideas(self):
  with tempfile.TemporaryDirectory() as d:
   result=search_text("/live energy",Path(d)/"missing.sqlite3",
       [{"title":"Energy monitoring","sector":"Energy"}])
   self.assertIn("No matching",result)
 def test_rejects_empty_query(self):
  self.assertIn("keyword",search_text("/search",Path("/nonexistent"),[]))
if __name__=="__main__":unittest.main()
