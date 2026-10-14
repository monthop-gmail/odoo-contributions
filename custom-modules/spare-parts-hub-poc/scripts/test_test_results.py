import unittest

from test_results import validate_test_log


class TestOdooLogGuard(unittest.TestCase):
    expected = ["TestSPHSkeleton.test_odoo19_community_dependency_registry"]
    start = "INFO Starting TestSPHSkeleton.test_odoo19_community_dependency_registry ...\n"

    def test_valid_run(self):
        validate_test_log(self.start + "0 failed, 0 error(s) of 1 tests", self.expected)

    def test_false_pass_controls(self):
        for log in (
            self.start + "10 failed, 0 error(s)",
            self.start + "0 failed, 0 error(s)\n1 failed, 0 error(s)",
            self.start + "0 failed, 1 error(s)",
            self.start + "ERROR test broke\n0 failed, 0 error(s)",
            self.start + "FAIL: test broke\n0 failed, 0 error(s)",
            self.start,
            "0 failed, 0 error(s)",
        ):
            with self.subTest(log=log), self.assertRaises(ValueError):
                validate_test_log(log, self.expected)


if __name__ == "__main__":
    unittest.main()
