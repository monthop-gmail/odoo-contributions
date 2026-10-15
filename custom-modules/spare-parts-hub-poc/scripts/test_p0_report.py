"""P0 evidence must fail closed on skipped cases, stale upgrades or duplicate rules."""
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from p0_report import case_statuses, validate_upgrade
from upgrade_path import PREVIOUS


class TestP0Report(unittest.TestCase):
    def upgrade(self):
        return {'status':'PASS','previous_sha':PREVIOUS,'final_sha':'fixture-tip','teardown':'PASS',
            'before':{'xmlid_count':1,'rule_id':7,'all_picking_rule_ids':[1,7],'grant':'group_sph_po_hub'},
            'after':{'xmlid_count':1,'rule_id':7,'all_picking_rule_ids':[1,7],
                'grant':'group_sph_picking_hub','grant_isolation_checked':True},
            'assertions':{'same_rule_id':True}}

    def test_rejects_recreated_or_duplicate_rule(self):
        for key,value in (('rule_id',8),('xmlid_count',2),('all_picking_rule_ids',[1,7,8])):
            data=self.upgrade();data['after'][key]=value
            with self.assertRaises(ValueError):validate_upgrade(data,'fixture-tip')

    def test_rejects_old_grant_or_stale_tip(self):
        data=self.upgrade();data['after']['grant']='group_sph_po_hub'
        with self.assertRaises(ValueError):validate_upgrade(data,'fixture-tip')
        with self.assertRaises(ValueError):validate_upgrade(self.upgrade(),'different-tip')

    def test_rejects_missing_teardown(self):
        data=self.upgrade();data['teardown']='FAIL'
        with self.assertRaises(ValueError):validate_upgrade(data,'fixture-tip')

    def test_duplicate_case_cannot_hide_missing_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'live.xml';suite=ET.Element('testsuite')
            for name in ('g1_http','g2_race','g3_authority','flow_a','flow_b','flow_b'):
                ET.SubElement(suite,'testcase',name=name)
            ET.ElementTree(suite).write(path)
            with self.assertRaises(ValueError):case_statuses(path)

    def test_skip_is_never_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'live.xml';suite=ET.Element('testsuite')
            for name in ('g1_http','g2_race','g3_authority','flow_a','flow_b'):
                case=ET.SubElement(suite,'testcase',name=name)
                if name=='g2_race':ET.SubElement(case,'skipped')
            ET.ElementTree(suite).write(path)
            self.assertEqual(case_statuses(path)['g2_race'],'SKIP')


if __name__=='__main__':unittest.main()
