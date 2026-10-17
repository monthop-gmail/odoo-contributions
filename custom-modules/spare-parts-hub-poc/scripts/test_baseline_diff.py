import unittest
from baseline_diff import validate_paths


class TestBaselineDiff(unittest.TestCase):
    def test_cochange_requires_review(self):
        with self.assertRaisesRegex(ValueError, 'baseline\+registry co-change requires independent hub review'):
            validate_paths(['folder/p0-evidence-baseline.json', 'folder/p0-baseline-reviews.json'])

    def test_current_or_single_file_change_not_cochange(self):
        for paths in ([], ['p0-evidence-baseline.json'], ['p0-baseline-reviews.json']):
            validate_paths(paths)


if __name__ == '__main__': unittest.main()
