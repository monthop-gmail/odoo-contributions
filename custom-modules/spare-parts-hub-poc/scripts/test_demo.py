"""Walkthrough provenance, step integrity and fail-closed orchestration."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from demo import build, markdown, validate, run_scenarios


def sources():
    shared = {'commit': 'fixture-tip', 'pins': {'fixture': 'pinned'}, 'database': 'sph_poc',
        'profile': 'disposable-test-harness', 'company_count': 1, 'sessions_cleaned': True}
    a = dict(shared, epoch_id='a' * 32, seed={'centers': [6, 7], 'reservists': [12, 14]},
        initial_free=1, winners=1, losers=1, observed_lock_waiters=2, loser_message='Unavailable',
        winner_center_id=6, orders=[1, 2], reserved_total=1, double_allocations=0, negative_stock=False,
        winning_reservation={'id': 1, 'so_id': 1, 'move_id': 1, 'state': 'active'},
        measurements={'existing_sales_before': 0, 'orders': [{'so_id': 1, 'state': 'sale', 'reserved_qty': 1}]})
    b = dict(shared, epoch_id='b' * 32, seed={'center_id': 6, 'reservist_uid': 12, 'bot_uid': 13, 'approver_uid': 7},
        po_id=1, initial_free=0, shortage_message='Unavailable', shortage_so_id=1, bot_drafted_state='draft', maker_uid=13,
        checker_uid=7, bot_confirm='DENIED', state_after_bot_denial='draft', durable_bot_deny_audit=True,
        receipt_ids_after_bot_denial=[], final_po_state='purchase', maker_checker_distinct=True,
        human_confirm_allow_audit=True, receipt_ids=[2], receipt_states=[{'id': 2, 'state': 'confirmed'}],
        completed_stock_moves=0, invoice_ids=[], on_hand_quantity=0,
        measurements={'existing_sales_before': 0, 'stockout_so_ids': [1]})
    a['measurements'].update(orders=[{'so_id':1,'state':'sale','requested_qty':1,'reserved_qty':1},
        {'so_id':2,'state':'sale','requested_qty':1,'reserved_qty':0}],stockout_so_ids=[2],
        stockout_audits=[{'audit_id':1,'so_id':2,'action':'sale.reserve.stockout','outcome':'deny'}],backorder_picking_ids=[])
    b['measurements'].update(orders=[{'so_id':1,'state':'sale','requested_qty':1,'reserved_qty':0}],
        stockout_audits=[{'audit_id':1,'so_id':1,'action':'sale.reserve.stockout','outcome':'deny'}],backorder_picking_ids=[])
    return {'A': a, 'B': b}


class TestDemo(unittest.TestCase):
    def test_complete_ordered_walkthrough(self):
        data = sources(); result = build(data, 'fixture-tip', {'fixture': 'pinned'})
        self.assertEqual([row['id'] for row in result['steps']], ['A0', 'A1', 'A2', 'A3', 'B0', 'B1', 'B2', 'B3', 'B4', 'B5'])
        self.assertEqual(validate(result, data, 'fixture-tip', {'fixture': 'pinned'}, markdown(result)), result)
        self.assertIn('NOT joinable', markdown(result))

    def test_stale_sha_pins_and_shared_epoch_rejected(self):
        for field, value in (('commit', 'stale'), ('pins', {}), ('epoch_id', 'a' * 32)):
            data = sources(); data['B'][field] = value
            with self.assertRaises(ValueError): build(data, 'fixture-tip', {'fixture': 'pinned'})

    def test_missing_step_rejected(self):
        data = sources(); result = build(data, 'fixture-tip', {'fixture': 'pinned'}); result['steps'].pop()
        with self.assertRaises(ValueError): validate(result, data, 'fixture-tip', {'fixture': 'pinned'}, markdown(result))

    def test_cli_evidence_mode_fails_nonzero_and_replaces_stale_artifacts(self):
        from demo import main
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'evidence').mkdir()
            (root/'version-pins.json').write_text(json.dumps({'fixture':'pinned'}))
            for key,source in sources().items():
                source['commit']='stale'
                (root/'evidence'/('Flow-'+key+'-results.json')).write_text(json.dumps(source))
            (root/'evidence/Demo-walkthrough.md').write_text('stale PASS')
            with patch('demo.ROOT',root),patch('demo.subprocess.check_output',return_value='fixture-tip\n'),\
                    patch('sys.argv',['demo.py','--from-evidence']),patch('demo.run_scenarios') as run,\
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(),1)
            run.assert_not_called()
            self.assertEqual(json.loads((root/'evidence/Demo-results.json').read_text())['status'],'FAIL')
            self.assertNotIn('stale PASS',(root/'evidence/Demo-walkthrough.md').read_text())

    def test_failed_step_never_passes(self):
        data = sources(); data['B']['durable_bot_deny_audit'] = False
        result = build(data, 'fixture-tip', {'fixture': 'pinned'})
        self.assertEqual(result['status'], 'FAIL')
        with self.assertRaises(ValueError): validate(result, data, 'fixture-tip', {'fixture': 'pinned'}, markdown(result))

    def test_expected_observed_or_markdown_tampering_rejected(self):
        data = sources(); original = build(data, 'fixture-tip', {'fixture': 'pinned'})
        for field in ('expected', 'observed'):
            result = copy.deepcopy(original); result['steps'][0][field]['company_count'] = 2
            with self.assertRaises(ValueError): validate(result, data, 'fixture-tip', {'fixture': 'pinned'}, markdown(result))
        with self.assertRaises(ValueError): validate(original, data, 'fixture-tip', {'fixture': 'pinned'}, 'tampered')

    def test_reuses_both_clis_and_always_tears_down(self):
        with patch('demo.subprocess.run') as run:
            run_scenarios()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(commands[0][1].endswith('/flow_a.py'))
        self.assertTrue(commands[1][1].endswith('/flow_b.py'))
        self.assertEqual(commands[2][-1], 'down')

    def test_cleanup_failure_does_not_hide_scenario_failure(self):
        original = RuntimeError('fixture scenario failure')
        with patch('demo.subprocess.run', side_effect=[original, ValueError('fixture cleanup failure')]):
            with self.assertRaises(RuntimeError) as caught: run_scenarios()
        self.assertIs(caught.exception, original)
        with patch('demo.subprocess.run', side_effect=[None, None, ValueError('fixture cleanup failure')]):
            with self.assertRaises(ValueError): run_scenarios()


if __name__ == '__main__': unittest.main()
