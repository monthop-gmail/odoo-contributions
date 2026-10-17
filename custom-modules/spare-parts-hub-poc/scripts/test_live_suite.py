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
    def run_control(self,g1=None,g2=None,flow_b=None):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'live.xml'
            with patch('live_suite.g1_http',side_effect=g1),patch('live_suite.g2_race',side_effect=g2),patch('live_suite.g3_authority'),patch('live_suite.flow_a'),patch('live_suite.flow_b',side_effect=flow_b),contextlib.redirect_stdout(io.StringIO()):
                code=run_suite(path)
            return code,ET.parse(path).getroot()

    def test_both_real_stages_required(self):
        code,suite=self.run_control()
        self.assertEqual(code,0);self.assertEqual(suite.get('skipped'),'0')
        self.assertEqual(suite.get('tests'),'5')
        self.assertEqual(suite.find("properties/property[@name='gate_acceptance']").get('value'),'G1-G3 PASS; G4 PENDING')
        self.assertEqual(suite.find("testcase[@name='g1_http']").get('classname'),'sph_live.g1_http')

    def test_unrunnable_is_skip_and_nonzero(self):
        code,suite=self.run_control(g2=Unrunnable())
        self.assertEqual(code,1);self.assertEqual(suite.get('skipped'),'1')
        self.assertIn('INCOMPLETE',suite.find("properties/property[@name='gate_acceptance']").get('value'))
        self.assertIsNotNone(suite.find("testcase[@name='g2_race']/skipped"))

    def test_failed_gate_is_nonzero(self):
        code,suite=self.run_control(g1=ConnectionError())
        self.assertEqual(code,1);self.assertEqual(suite.get('failures'),'1')

    def test_flow_b_failure_has_dedicated_case(self):
        code,suite=self.run_control(flow_b=RuntimeError())
        self.assertEqual(code,1)
        self.assertIsNotNone(suite.find("testcase[@name='flow_b']/failure"))
        self.assertIsNone(suite.find("testcase[@name='g3_authority']/failure"))


if __name__=='__main__':
    from test_demo import TestDemo
    from test_baseline_diff import TestBaselineDiff
    from test_dashboard import TestDashboard
    from test_p0_report import TestP0Report
    unittest.main()
