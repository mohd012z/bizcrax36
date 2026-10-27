import unittest
from backend.telegram_result_utils import deduplicate_ideas,page

class ResultUtilsTests(unittest.TestCase):
    def test_dedupe_by_title_and_country(self):
        data=[{"title":"Solar","country":"Malaysia"},
              {"title":"SOLAR","country":"malaysia"},
              {"title":"Solar","country":"Singapore"}]
        self.assertEqual(len(deduplicate_ideas(data)),2)

    def test_ignores_invalid_entries(self):
        self.assertEqual(deduplicate_ideas([None,{},{"title":"  "}]),[])

    def test_page_bounds(self):
        values=list(range(12))
        self.assertEqual(page(values,1)["items"],[5,6,7,8,9])
        self.assertEqual(page(values,99)["items"],[10,11])
        self.assertEqual(page(values,-2)["page"],0)

    def test_empty_page(self):
        self.assertEqual(page([])["pages"],1)
        self.assertEqual(page([])["items"],[])

    def test_rejects_invalid_page_size(self):
        with self.assertRaises(ValueError):
            page([1],size=0)

if __name__=="__main__":
    unittest.main()
