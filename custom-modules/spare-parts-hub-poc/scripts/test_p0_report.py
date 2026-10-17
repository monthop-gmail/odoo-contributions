"""P0 evidence must fail closed on skipped cases, stale upgrades or duplicate rules."""
import json
import copy
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from p0_report import case_statuses, validate_upgrade, validate_live_evidence, validate_baseline, validate_retained, execute
from upgrade_evidence import upgrade_checks, retained_checks
from unittest.mock import patch
from dashboard import calculate
from upgrade_path import PREVIOUS, RETAINED_PREVIOUS


class TestP0Report(unittest.TestCase):
    def upgrade(self):
        business={'sales':0,'purchases':0,'pickings':0,'reservations':0}
        before={'xmlid_count':1,'rule_id':7,'all_picking_rule_ids':[1,7],
            'grant_tokens':['group_sph_po_hub'],'rule_model':'stock.picking','is_global':True,
            'business_counts':business}
        after=dict(before,grant_tokens=['group_sph_picking_hub'],
            visibility_counts={'none':0,'po_hub':0,'picking_hub':1,'revoked':0},
            group_observations={key:{'implied_count':0,'assignee_count':0}
                for key in ('group_sph_po_hub','group_sph_picking_hub')})
        return {'status':'PASS','previous_sha':PREVIOUS,'final_sha':'fixture-tip','teardown':'PASS',
            'before':before,'after':after,'assertions':upgrade_checks(before,after)}

    def test_rejects_recreated_or_duplicate_rule(self):
        for key,value in (('rule_id',8),('xmlid_count',2),('all_picking_rule_ids',[1,7,8])):
            data=self.upgrade();data['after'][key]=value
            with self.assertRaises(ValueError):validate_upgrade(data,'fixture-tip')

    def test_rejects_old_grant_or_stale_tip(self):
        data=self.upgrade();data['after']['grant_tokens']=['group_sph_po_hub']
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


    def live_data(self):
        baseline=json.loads((Path(__file__).resolve().parents[1]/'p0-evidence-baseline.json').read_text())
        matrix=[{'audit_seen':True,'outcome':outcome} for outcome,count in
            (('deny',baseline['g3']['deny']),('allow',baseline['g3']['allow'])) for _ in range(count)]
        g3={'matrix':matrix,'deny_rows_observed':140,'allow_rows_observed':22}
        g2={'round_count':4,'lock_wait_rounds':4,'double_allocations':0,'rounds':[
            {'round':index,'observed_lock_waiters':2,'double_allocations':0,'negative_stock':False} for index in range(4)]}
        return g2,g3,baseline

    def test_reduced_consistent_g3_matrix_rejected(self):
        g2,g3,baseline=self.live_data();g3['matrix'].pop();g3['allow_rows_observed']-=1
        with self.assertRaises(ValueError):validate_live_evidence(g2,g3,baseline)

    def test_zero_or_fabricated_g2_contention_rejected(self):
        g2,g3,baseline=self.live_data()
        g2['lock_wait_rounds']=0
        for row in g2['rounds']:row['observed_lock_waiters']=0
        with self.assertRaises(ValueError):validate_live_evidence(g2,g3,baseline)
        g2['lock_wait_rounds']=1
        with self.assertRaises(ValueError):validate_live_evidence(g2,g3,baseline)

    def test_upgrade_flags_mirror_failed_measurement(self):
        data=self.upgrade();data['after']['visibility_counts']['po_hub']=1
        checks=upgrade_checks(data['before'],data['after'])
        self.assertFalse(checks['post_upgrade_grant_isolation'])
        data['assertions']=checks
        with self.assertRaises(ValueError):validate_upgrade(data,'fixture-tip')
        data['assertions']['post_upgrade_grant_isolation']=True
        with self.assertRaises(ValueError):validate_upgrade(data,'fixture-tip')

    def report_fixture(self,root):
        g2,g3,baseline=self.live_data()
        (root/'docs').mkdir();(root/'docs/dashboard-formulas.md').write_text('FIXTURE formulas')
        (root/'Dashboard-formulas.md').write_text('FIXTURE formulas')
        def save(name,value):(root/name).write_text(json.dumps(value))
        save('expected-tests.json',['Fixture.test_smoke']);save('p0-evidence-baseline.json',baseline)
        save('p0-baseline-reviews.json',json.loads((Path(__file__).resolve().parents[1]/'p0-baseline-reviews.json').read_text()))
        mail={'synthetic':True,'captured_messages':1,'real_smtp_calls':0,'bot_rfq_denied':True,'human_rfq_state':'sent'}
        perf={'synthetic':True,'samples':[{'model':model,'own_documents':count,'foreign_candidates':1,
            'returned':count,'sql_queries':3,'seconds':0.001} for model in ('mail.message','ir.attachment') for count in (2,10,30)]}
        (root/'odoo-tests.log').write_text('Starting Fixture.test_smoke ...\n0 failed, 0 error(s)\n'+
            'SPH_RFQ_CAPTURE '+json.dumps(mail)+'\nSPH_RULE_PERFORMANCE '+json.dumps(perf)+'\n')
        suite=ET.Element('testsuite',failures='0',errors='0',skipped='0')
        for name in ('g1_http','g2_race','g3_authority','flow_a','flow_b'):ET.SubElement(suite,'testcase',name=name)
        ET.ElementTree(suite).write(root/'live-suite.xml')
        save('Fresh-live-start.json',{'commit':'fixture-tip','companies':1,'sales':0,'purchases':0,'reservations':0})
        save('manifest.json',{'commit':'fixture-tip'})
        from test_demo import sources
        from demo import build, markdown
        from baseline_diff import REVIEWED
        demos=sources()
        for key,source in demos.items():
            rows=source['measurements']['orders'] if key=='A' else [{'so_id':1,'state':'sale','reserved_qty':0}]
            for row in rows:row['requested_qty']=1
            shortage=2 if key=='A' else 1
            source['measurements'].update(orders=rows,stockout_so_ids=[shortage],
                stockout_audits=[{'audit_id':1,'so_id':shortage,'action':'sale.reserve.stockout','outcome':'deny'}],backorder_picking_ids=[])
            save('Flow-'+key+'-results.json',source)
        save('version-pins.json',{'fixture':'pinned'})
        save('Baseline-diff-review.json',{'reviewed_sha':REVIEWED,'commit':'fixture-tip','status':'PASS','changed_paths':[]})
        demo=build(demos,'fixture-tip',{'fixture':'pinned'});save('Demo-results.json',demo)
        (root/'Demo-walkthrough.md').write_text(markdown(demo))
        from dashboard import reconcile, render
        dashboard=reconcile(demos,'fixture-tip',demo,markdown(demo),{'fixture':'pinned'},baseline['g3'],
            {'tests':5,'failures':0,'errors':0,'skipped':0})
        save('Dashboard-results.json',dashboard);(root/'Dashboard.html').write_text(render(dashboard))
        save('G2-request-results.json',g2);save('G3-authority-results.json',g3);save('Upgrade-results.json',self.upgrade());save('Retained-upgrade-results.json',self.retained())

    def test_report_fails_on_probe_mutation_shrink_or_no_contention(self):
        for mutation in ('probe','g3','g2'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);self.report_fixture(root)
                if mutation=='probe':
                    name='Upgrade-results.json';data=json.loads((root/name).read_text())
                    data['after']['visibility_counts']['po_hub']=1
                    data['assertions']=upgrade_checks(data['before'],data['after'])
                elif mutation=='g3':
                    name='G3-authority-results.json';data=json.loads((root/name).read_text())
                    data['matrix'].pop();data['allow_rows_observed']-=1
                else:
                    name='G2-request-results.json';data=json.loads((root/name).read_text());data['lock_wait_rounds']=0
                    for row in data['rounds']:row['observed_lock_waiters']=0
                (root/name).write_text(json.dumps(data))
                with patch('p0_report.ROOT',root),patch('p0_report.subprocess.check_output',return_value='fixture-tip\n'),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(execute(root)['status'],'FAIL')
                self.assertEqual(json.loads((root/'P0-report.json').read_text())['status'],'FAIL')

    def test_current_baseline_and_measured_probe_pass_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.report_fixture(root)
            with patch('p0_report.ROOT',root),patch('p0_report.subprocess.check_output',return_value='fixture-tip\n'),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(execute(root)['status'],'PASS')

    def test_report_rejects_stale_failed_or_tampered_demo(self):
        for mutation in ('sha', 'missing', 'failed', 'expected', 'markdown'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);self.report_fixture(root)
                path=root/'Demo-results.json';data=json.loads(path.read_text())
                if mutation=='sha':data['commit']='stale'
                elif mutation=='missing':data['steps'].pop()
                elif mutation=='failed':data['steps'][0]['status']='FAIL'
                elif mutation=='expected':data['steps'][0]['expected']['company_count']=2
                else:(root/'Demo-walkthrough.md').write_text('tampered walkthrough')
                path.write_text(json.dumps(data))
                with patch('p0_report.ROOT',root),patch('p0_report.subprocess.check_output',return_value='fixture-tip\n'),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(execute(root)['status'],'FAIL')

    def test_report_rejects_dashboard_json_html_and_epoch_tampering(self):
        for mutation in ('json','html','epoch'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);self.report_fixture(root)
                if mutation=='html':(root/'Dashboard.html').write_text('tampered')
                else:
                    path=root/'Dashboard-results.json';data=json.loads(path.read_text())
                    if mutation=='json':data['metrics']['stockouts']=99
                    else:data['epochs']['B']=data['epochs']['A']
                    path.write_text(json.dumps(data))
                with patch('p0_report.ROOT',root),patch('p0_report.subprocess.check_output',return_value='fixture-tip\n'),contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(execute(root)['status'],'FAIL')

    def retained(self):
        before={'snapshot':{'xmlids':list(range(5)),'orders':[{'id':7,'state':'purchase'}]},
            'xmlid_count':1,'rule_id':192,'all_picking_rule_ids':[128,185,192],
            'rule_domain':'picking_hub else memberships','is_global':True,
            'groups':{'po':{'implied':0,'assignees':0}},
            'visibility_counts':{'none':0,'center_a':2,'center_b':1,'revoked':0}}
        after=copy.deepcopy(before)
        return {'status':'PASS','previous_sha':RETAINED_PREVIOUS,'final_sha':'fixture-tip','teardown':'PASS',
            'before':before,'after':after,'assertions':retained_checks(before,after)}

    def test_retained_loss_or_visibility_change_rejected(self):
        for field in ('snapshot','visibility_counts'):
            data=self.retained()
            if field=='snapshot':data['after']['snapshot']['orders']=[]
            else:data['after']['visibility_counts']['none']=1
            data['assertions']=retained_checks(data['before'],data['after'])
            with self.assertRaises(ValueError):validate_retained(data,'fixture-tip')

    def test_baseline_bump_needs_review_registration(self):
        baseline=self.live_data()[2]
        for field,value in (('baseline_version',2),('reviewer','unreviewed'),('review_source_ref','')):
            changed=copy.deepcopy(baseline);changed[field]=value
            with self.assertRaisesRegex(ValueError,'baseline bump requires review'):validate_baseline(changed)
        changed=copy.deepcopy(baseline);changed['g3']['deny']+=1;changed['g3']['observations']+=1
        with self.assertRaisesRegex(ValueError,'baseline bump requires review'):validate_baseline(changed)

    def test_report_clearly_explains_unreviewed_bump(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.report_fixture(root)
            file=root/'p0-evidence-baseline.json';data=json.loads(file.read_text());data['baseline_version']=2
            file.write_text(json.dumps(data))
            with patch('p0_report.ROOT',root),patch('p0_report.subprocess.check_output',return_value='fixture-tip\n'),contextlib.redirect_stdout(io.StringIO()):
                result=execute(root)
            self.assertEqual(result['status'],'FAIL')
            self.assertIn('baseline bump requires review',result['error_message'])


if __name__=='__main__':unittest.main()
