"""Check JUnit/failure semantics; these are runner tests, not G1/G2 tests."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from live_suite import run_suite


class TestLiveSuite(unittest.TestCase):
    def test_readiness_and_explicit_unrunnable_race(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.xml"
            with patch("live_suite.g1_http"), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_suite(path), 0)
            suite = ET.parse(path).getroot()
            self.assertEqual(suite.get("tests"), "2")
            self.assertEqual(suite.get("failures"), "0")
            self.assertEqual(suite.get("skipped"), "1")
            self.assertIsNone(suite.find("testcase[@name='g1_http']/failure"))
            skipped = suite.find("testcase[@name='g2_race']/skipped")
            self.assertEqual(skipped.get("message"), "UNRUNNABLE: not implemented")

    def test_unavailable_harness_fails_and_still_writes_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.xml"
            with patch("live_suite.g1_http", side_effect=ConnectionError("not evidence")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_suite(path), 1)
            suite = ET.parse(path).getroot()
            self.assertEqual(suite.get("failures"), "1")
            self.assertIsNotNone(suite.find("testcase[@name='g1_http']/failure"))
            self.assertIsNotNone(suite.find("testcase[@name='g2_race']/skipped"))
            self.assertNotIn("not evidence", path.read_text())


if __name__ == "__main__":
    unittest.main()
