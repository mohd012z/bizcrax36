import unittest
from agent_framework_v1 import Evidence, canonical_url, deduplicate, score_opportunity, draft_campaign

class FrameworkTests(unittest.TestCase):
    def test_url(self):
        self.assertEqual(canonical_url('https://example.com/a?utm_source=x'), 'https://example.com/a')
    def test_deduplication(self):
        e = Evidence('Title', 'https://example.com/a', 'Summary')
        self.assertEqual(len(deduplicate([e, e])), 1)
    def test_score(self):
        self.assertEqual(score_opportunity(5, 5, 0, 5), 100)
    def test_draft(self):
        e = Evidence('Title', 'https://example.com/a', 'Summary')
        self.assertFalse(draft_campaign('Product', 'Audience', [e])['publish_allowed'])

if __name__ == '__main__':
    unittest.main()
