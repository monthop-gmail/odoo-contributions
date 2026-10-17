"""Reject stale evidence and distinguish unmet demand from native backorders."""
import unittest
import copy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from dashboard import calculate, reconcile, render, validate, execute
from demo import build, markdown
from test_demo import sources


class TestDashboard(unittest.TestCase):
    def source(self,requested=2,reserved=1):
        return {'A':{'commit':'fixture-sha','measurements':{'existing_sales_before':0,
            'orders':[{'so_id':1,'state':'sale','requested_qty':requested,'reserved_qty':reserved}],
            'stockout_so_ids':[1],'stockout_audits':[{'audit_id':1,'so_id':1,'action':'sale.reserve.stockout','outcome':'deny'}],'backorder_picking_ids':[]}}}

    def test_rejects_mixed_commit(self):
        with self.assertRaisesRegex(ValueError,'mixed commit'):
            calculate(self.source(),'different-sha')

    def test_rejects_unclean_epoch(self):
        source=self.source();source['A']['measurements']['existing_sales_before']=3
        with self.assertRaisesRegex(ValueError,'clean scenario'):
            calculate(source,'fixture-sha')

    def test_zero_demand_is_unknown(self):
        data=calculate(self.source(0,0),'fixture-sha')
        self.assertIsNone(data['metrics']['fill_rate'])

    def test_unmet_demand_is_not_native_backorder(self):
        data=calculate(self.source(),'fixture-sha')
        self.assertEqual(data['metrics']['open_blockers'],1)
        self.assertEqual(data['metrics']['backorders'],0)

    def test_rejects_stockout_without_system_audit(self):
        source=self.source();source['A']['measurements']['stockout_audits']=[]
        with self.assertRaisesRegex(ValueError,'system audit provenance'):
            calculate(source,'fixture-sha')

    def fixture(self):
        data=sources();pins={'fixture':'pinned'};demo=build(data,'fixture-tip',pins)
        return [data,'fixture-tip',demo,markdown(demo),pins,
            {'deny':140,'allow':22,'observations':162},{'tests':5,'failures':0,'errors':0,'skipped':0}]

    def test_metric_derivations_and_links(self):
        args=self.fixture();result=reconcile(*args);page=render(result)
        self.assertEqual(result['metrics'],{'fill_rate':1/3,'backorders':0,'stockouts':2,'open_blockers':2})
        self.assertEqual(result['epochs'],args[2]['epochs'])
        self.assertEqual(result['derivations']['fill_rate']['denominator'],3)
        self.assertEqual(len(result['derivations']['stockouts']['records']),2)
        self.assertIsNone(result['derivations']['backorders']['denominator'])
        self.assertIn('1 / 3 = 33.33%',page)
        self.assertIn('Demo-walkthrough.md#a3',page)
        self.assertIn('not pilot sign-off',page)
        self.assertIn('awaiting owner confirmation',page)
        validate(result,page,*args)

    def test_stale_shared_swapped_epoch_or_demo_numbers_rejected(self):
        for mutation in ('sha','shared','swapped','demo','source'):
            args=self.fixture();data=args[0]
            if mutation=='sha':data['B']['commit']='stale'
            elif mutation=='shared':data['B']['epoch_id']=data['A']['epoch_id']
            elif mutation=='swapped':data['A']['epoch_id'],data['B']['epoch_id']=data['B']['epoch_id'],data['A']['epoch_id']
            elif mutation=='demo':args[2]['steps'][3]['observed']['reserved_total']=2
            else:data['A']['measurements']['orders'][0]['requested_qty']=2
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):reconcile(*args)

    def test_coherently_rebuilt_demo_with_inconsistent_demand_rejected(self):
        args=self.fixture();args[0]['A']['measurements']['orders'][0]['requested_qty']=2
        args[2]=build(args[0],args[1],args[4]);args[3]=markdown(args[2])
        with self.assertRaisesRegex(ValueError,'units differ'):reconcile(*args)

    def test_json_html_or_walkthrough_tampering_rejected(self):
        args=self.fixture();result=reconcile(*args);page=render(result)
        for field in ('epochs','metrics','derivations'):
            changed=copy.deepcopy(result);changed[field]={}
            with self.subTest(field=field),self.assertRaises(ValueError):validate(changed,page,*args)
        with self.assertRaises(ValueError):validate(result,page+'tampered',*args)
        args[3]+='tampered'
        with self.assertRaises(ValueError):reconcile(*args)

    def test_html_escapes_dynamic_values_and_has_no_external_assets(self):
        result=reconcile(*self.fixture());result['pins']={'fixture':'<script>alert("x")</script>'}
        page=render(result)
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('<script',page)
        self.assertNotIn('src=',page)
        self.assertNotIn('https://',page)

    def test_render_only_cli_is_byte_reproducible(self):
        from dashboard import main
        args=self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);evidence=root/'evidence';evidence.mkdir()
            def save(name,value):(evidence/name).write_text(json.dumps(value))
            for key,value in args[0].items():save('Flow-'+key+'-results.json',value)
            save('Demo-results.json',args[2]);(evidence/'Demo-walkthrough.md').write_text(args[3])
            (evidence/'live-suite.xml').write_text('<testsuite failures="0" errors="0" skipped="0">'+5*'<testcase/>'+'</testsuite>')
            (root/'version-pins.json').write_text(json.dumps(args[4]));(root/'p0-evidence-baseline.json').write_text(json.dumps({'g3':args[5]}))
            with patch('dashboard.ROOT',root),patch('dashboard.subprocess.run') as run,patch('sys.argv',['dashboard.py','--from-evidence']):
                run.return_value.stdout='fixture-tip\n'
                self.assertEqual(main(),0)
                first=[(evidence/name).read_bytes() for name in ('Dashboard-results.json','Dashboard.html')]
                self.assertEqual(main(),0)
                self.assertEqual(first,[(evidence/name).read_bytes() for name in ('Dashboard-results.json','Dashboard.html')])
                self.assertTrue(all(call.args[0]==['git','rev-parse','HEAD'] for call in run.call_args_list))
