"""One command for the existing fresh Flow A/B CLIs, or render their evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from harness import ROOT


def build(sources, commit, pins):
    if set(sources) != {'A', 'B'}:
        raise ValueError('Both scenario sources required')
    epochs = {}
    for key, source in sources.items():
        if source['commit'] != commit or source['pins'] != pins:
            raise ValueError('Stale/mixed SHA or pins')
        epoch = source['epoch_id']
        if not isinstance(epoch, str) or len(epoch) != 32 or any(c not in '0123456789abcdef' for c in epoch):
            raise ValueError('Missing scenario epoch')
        epochs[key] = epoch
    if epochs['A'] == epochs['B']:
        raise ValueError('Scenarios must use different fresh epochs')
    a, b = sources['A'], sources['B']
    steps = []

    def step(key, persona, center, action, expected, observed):
        steps.append({'id': key, 'persona': persona, 'center': center, 'action': action,
            'expected': expected, 'observed': observed,
            'status': 'PASS' if expected == observed else 'FAIL'})

    for key, source in sources.items():
        step(key + '0', 'FIXTURE harness operator', 'epoch ' + key,
            'Start fresh single-company disposable scenario; clean up sessions',
            {'database': 'sph_poc', 'profile': 'disposable-test-harness', 'company_count': 1,
                'existing_sales_before': 0, 'sessions_cleaned': True},
            {field: source[field] for field in ('database', 'profile', 'company_count', 'sessions_cleaned')} |
                {'existing_sales_before': source['measurements']['existing_sales_before']})
    # Keep the owner walkthrough in execution order: all A steps, then all B steps.
    b_setup = steps.pop()
    step('A1', 'FIXTURE reservists ' + str(a['seed']['reservists']), a['seed']['centers'],
        'Two centers concurrently reserve the last unit',
        {'two_distinct_centers': True, 'initial_free': 1, 'winners': 1, 'losers': 1, 'contention': True},
        {'two_distinct_centers': len(set(a['seed']['centers'])) == len(a['seed']['centers']) == 2,
            'initial_free': a['initial_free'], 'winners': a['winners'], 'losers': a['losers'],
            'contention': a['observed_lock_waiters'] >= 2})
    step('A2', 'FIXTURE losing reservist', a['seed']['centers'], 'Observe generic shortage denial',
        {'message': 'Unavailable'}, {'message': a['loser_message']})
    reservation = a['winning_reservation']
    step('A3', 'FIXTURE winning reservist', a['winner_center_id'], 'Inspect reservation → confirmed SO link',
        {'active': True, 'linked_sale': True, 'reserved_total': 1, 'double_allocations': 0, 'negative_stock': False},
        {'active': reservation['state'] == 'active',
            'linked_sale': reservation['so_id'] in a['orders'] and any(
                row['so_id'] == reservation['so_id'] and row['state'] == 'sale' and row['reserved_qty'] == 1
                for row in a['measurements']['orders']),
            'reserved_total': a['reserved_total'], 'double_allocations': a['double_allocations'],
            'negative_stock': a['negative_stock']})
    steps.append(b_setup)
    center = b['seed']['center_id']
    step('B1', 'FIXTURE requester ' + str(b['seed']['reservist_uid']), center, 'Request unavailable part',
        {'initial_free': 0, 'message': 'Unavailable', 'stockout_audited': True},
        {'initial_free': b['initial_free'], 'message': b['shortage_message'],
            'stockout_audited': b['shortage_so_id'] in b['measurements']['stockout_so_ids']})
    step('B2', 'FIXTURE bot ' + str(b['seed']['bot_uid']), center, 'Draft RFQ only',
        {'state': 'draft', 'maker_is_bot': True},
        {'state': b['bot_drafted_state'], 'maker_is_bot': b['maker_uid'] == b['seed']['bot_uid']})
    step('B3', 'FIXTURE bot ' + str(b['seed']['bot_uid']), center, 'Attempt purchase confirmation',
        {'outcome': 'DENIED', 'state': 'draft', 'durable_deny_audit': True, 'receipts': []},
        {'outcome': b['bot_confirm'], 'state': b['state_after_bot_denial'],
            'durable_deny_audit': b['durable_bot_deny_audit'], 'receipts': b['receipt_ids_after_bot_denial']})
    step('B4', 'FIXTURE human approver ' + str(b['seed']['approver_uid']), center, 'Review and confirm RFQ',
        {'state': 'purchase', 'different_human_checker': True, 'allow_audit': True},
        {'state': b['final_po_state'], 'different_human_checker': b['maker_uid'] != b['checker_uid'] == b['seed']['approver_uid']
            and b['maker_checker_distinct'] is True, 'allow_audit': b['human_confirm_allow_audit']})
    step('B5', 'FIXTURE human observer', center, 'Inspect receipt without validating it; inspect stock/finance',
        {'receipt_created': True, 'unvalidated_receipts': True, 'completed_stock_moves': 0, 'invoice_ids': [], 'on_hand_quantity': 0},
        {'receipt_created': bool(b['receipt_ids']), 'unvalidated_receipts':
            sorted(row['id'] for row in b['receipt_states']) == sorted(b['receipt_ids']) and
            all(row['state'] not in ('done', 'cancel') for row in b['receipt_states']),
            'completed_stock_moves': b['completed_stock_moves'], 'invoice_ids': b['invoice_ids'], 'on_hand_quantity': b['on_hand_quantity']})
    details = {'A1': {'so_ids': a['orders']}, 'A3': {'reservation': reservation},
        'B2': {'po_id': b['po_id']}, 'B3': {'po_id': b['po_id']},
        'B4': {'po_id': b['po_id'], 'maker_uid': b['maker_uid'], 'checker_uid': b['checker_uid']},
        'B5': {'receipt_states': b['receipt_states']}}
    for row in steps:
        row['evidence'] = details.get(row['id'], {})
    return {'schema_version': 1, 'scope': 'Synthetic P0 demo, not pilot sign-off',
        'commit': commit, 'pins': pins, 'epochs': epochs,
        'epoch_boundary': 'A and B are separate fresh disposable databases. Record IDs are NOT joinable across epochs.',
        'sources_sha256': {key: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            for key, value in sources.items()},
        'status': 'PASS' if all(row['status'] == 'PASS' for row in steps) else 'FAIL', 'steps': steps}


def markdown(result):
    text = '# Synthetic P0 demo, not pilot sign-off\n\nCommit: `' + result['commit'] + '`\n\n'
    text += 'Pins: `' + json.dumps(result['pins'], sort_keys=True) + '`\n\n'
    text += 'Epochs: `' + json.dumps(result['epochs'], sort_keys=True) + '`. ' + result['epoch_boundary'] + '\n\n'
    text += '| Step | Synthetic persona / center | Action | Expected | Observed | Result |\n|---|---|---|---|---|---|\n'
    for row in result['steps']:
        values = [row['id'], row['persona'] + ' / ' + str(row['center']), row['action'],
            json.dumps(row['expected'], sort_keys=True), json.dumps(row['observed'], sort_keys=True) +
                ('; evidence=' + json.dumps(row['evidence'], sort_keys=True) if row['evidence'] else ''), row['status']]
        text += '| ' + ' | '.join(value.replace('|', '\\|').replace('\n', ' ') for value in values) + ' |\n'
    text += '\nOverall: **' + result['status'] + '**. Receipt creation is not receipt validation; no delivery/receipt is validated and no invoice is created by Flow B.\n'
    return text


def validate(result, sources, commit, pins, walkthrough):
    rebuilt = build(sources, commit, pins)
    if rebuilt['status'] != 'PASS' or result != rebuilt or walkthrough != markdown(rebuilt):
        raise ValueError('Missing/failed/tampered demo step or walkthrough')
    return rebuilt


def execute(directory=None):
    directory = Path(directory or ROOT / 'evidence'); directory.mkdir(exist_ok=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    pins = json.loads((ROOT / 'version-pins.json').read_text())
    try:
        sources = {key: json.loads((directory / ('Flow-' + key + '-results.json')).read_text()) for key in ('A', 'B')}
        result = build(sources, commit, pins)
        walkthrough = markdown(result)
    except Exception as error:
        result = {'status': 'FAIL', 'commit': commit, 'pins': pins, 'error_type': type(error).__name__, 'steps': []}
        walkthrough = '# Synthetic P0 demo, not pilot sign-off — FAIL\n\nCommit: `' + commit + '`\n\nPins: `' + json.dumps(pins, sort_keys=True) + '`\n\nMissing, stale or malformed scenario evidence; epochs unverified.\n'
    (directory / 'Demo-results.json').write_text(json.dumps(result, indent=2) + '\n')
    (directory / 'Demo-walkthrough.md').write_text(walkthrough)
    print('SPH_DEMO_RESULT ' + json.dumps({'commit': commit, 'status': result['status'], 'steps': len(result['steps'])}))
    return result


def run_scenarios():
    print('WARNING: wipes this checkout disposable harness volumes. NEVER point at a non-disposable DB.', file=sys.stderr, flush=True)
    try:
        for key in ('a', 'b'):
            subprocess.run([sys.executable, str(ROOT / ('scripts/flow_' + key + '.py'))], check=True)
    finally:
        failed = sys.exc_info()[0] is not None
        try:
            subprocess.run([sys.executable, str(ROOT / 'scripts/harness.py'), 'down'], check=True)
        except Exception:
            print('SPH_DEMO_CLEANUP_FAILURE', file=sys.stderr, flush=True)
            if not failed:
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-evidence', action='store_true', help='Render same-tip evidence only; do not start/wipe a harness.')
    args = parser.parse_args()
    if not args.from_evidence:
        evidence = ROOT / 'evidence'
        for name in ('Demo-results.json', 'Demo-walkthrough.md', 'Flow-A-results.json', 'Flow-B-results.json'):
            (evidence / name).unlink(missing_ok=True)
        run_scenarios()
    return 0 if execute()['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
