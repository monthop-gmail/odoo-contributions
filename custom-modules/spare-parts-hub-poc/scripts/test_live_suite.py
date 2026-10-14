"""Runner controls: skipped/failed gates cannot produce a green job."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from live_suite import run_suite
from g2_race import Unrunnable


class TestLiveSuite(unittest.TestCase):
    def run_control(self,g1=None,g2=None):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'live.xml'
            with patch('live_suite.g1_http',side_effect=g1),patch('live_suite.g2_race',side_effect=g2),contextlib.redirect_stdout(io.StringIO()):
                code=run_suite(path)
            return code,ET.parse(path).getroot()

    def test_both_real_stages_required(self):
        code,suite=self.run_control()
        self.assertEqual(code,0);self.assertEqual(suite.get('skipped'),'0')

    def test_unrunnable_is_skip_and_nonzero(self):
        code,suite=self.run_control(g2=Unrunnable())
        self.assertEqual(code,1);self.assertEqual(suite.get('skipped'),'1')
        self.assertIsNotNone(suite.find("testcase[@name='g2_race']/skipped"))

    def test_failed_gate_is_nonzero(self):
        code,suite=self.run_control(g1=ConnectionError())
        self.assertEqual(code,1);self.assertEqual(suite.get('failures'),'1')
