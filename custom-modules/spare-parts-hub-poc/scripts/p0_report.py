"""Consolidate measured, same-tip CI evidence; never turn missing/skipped into PASS."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from dashboard import calculate, validate as validate_dashboard, gate_summary
from demo import validate as validate_demo
from baseline_diff import REVIEWED, validate_paths
from harness import ROOT
from test_results import validate_test_log
from upgrade_path import PREVIOUS, RETAINED_PREVIOUS
from upgrade_evidence import upgrade_checks, retained_checks

BASE='0e2f64e08a2c24b900c7c77f2d71231975298f50'
BASE_ARTIFACT={'run_id':38796314664,'artifact_id':12002955569,
    'sha256':'61e66867a8a01b5eef1032ea5d3316c9954e589fd44c46293d2f3c05ef8d4f94'}


def case_statuses(path):
    suite=ET.parse(path).getroot()
    cases={case.get('name'):('FAIL' if any(case.find(tag) is not None for tag in ('failure','error'))
        else 'SKIP' if case.find('skipped') is not None else 'PASS') for case in suite.findall('testcase')}
    if len(suite.findall('testcase'))!=5 or len(cases)!=5 or set(cases)!={'g1_http','g2_race','g3_authority','flow_a','flow_b'}:
        raise ValueError('Incomplete or duplicate live cases')
    if any(int(suite.get(key,'0')) for key in ('failures','errors','skipped')):
        raise ValueError('Nonzero live summary')
    return cases


def validate_upgrade(data,commit):
    if data['status']!='PASS' or data['previous_sha']!=PREVIOUS or data['final_sha']!=commit or data['teardown']!='PASS':
        raise ValueError('Upgrade incomplete or stale')
    measured=upgrade_checks(data['before'],data['after'])
    if data['assertions']!=measured or not all(measured.values()):
        raise ValueError('Upgrade measured checks failed or reported flags disagree')


class BaselineReviewRequired(ValueError):
    pass


def validate_baseline(baseline):
    try:reviews=json.loads((ROOT/'p0-baseline-reviews.json').read_text())
    except (OSError,ValueError):raise BaselineReviewRequired('baseline bump requires review: reviewed registration unavailable') from None
    version=baseline.get('baseline_version')
    entry=reviews.get('reviews',{}).get(str(version))
    digest=hashlib.sha256(json.dumps(baseline,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if (reviews.get('schema_version')!=1 or type(version) is not int or not entry or not baseline.get('reviewer') or
            not baseline.get('review_source_ref') or entry['baseline_sha256']!=digest or
            entry['reviewer']!=baseline['reviewer'] or entry['source_ref']!=baseline['review_source_ref']):
        raise BaselineReviewRequired('baseline bump requires review: missing or mismatched reviewed baseline registration')
    return entry


def validate_retained(data,commit):
    checks=retained_checks(data['before'],data['after'])
    if (data['status']!='PASS' or data['previous_sha']!=RETAINED_PREVIOUS or data['final_sha']!=commit or
            data['teardown']!='PASS' or data['assertions']!=checks or not all(checks.values())):
        raise ValueError('Retained synthetic upgrade failed or stale')


def validate_live_evidence(g2,g3,baseline):
    validate_baseline(baseline)
    if baseline['schema_version']!=1:raise ValueError('Unknown evidence baseline schema')
    matrix=g3['matrix']
    if not matrix or not all(row['audit_seen'] is True for row in matrix):
        raise ValueError('Missing durable audit observation')
    if any(row['outcome'] not in ('deny','allow') for row in matrix):raise ValueError('Unknown G3 outcome')
    counts={'deny':sum(row['outcome']=='deny' for row in matrix),
        'allow':sum(row['outcome']=='allow' for row in matrix),'observations':len(matrix)}
    if counts!=baseline['g3']:raise BaselineReviewRequired('baseline bump requires review: G3 coverage differs from reviewed 140/22/162 pin')
    if (counts['deny'],counts['allow'])!=(g3['deny_rows_observed'],g3['allow_rows_observed']):
        raise ValueError('G3 counts disagree')
    rounds=g2['round_count'];waits=g2['lock_wait_rounds']
    if (g2['double_allocations']!=0 or rounds<baseline['g2']['min_rounds'] or
            len(g2['rounds'])!=rounds or not baseline['g2']['min_lock_wait_rounds']<=waits<=rounds):
        raise ValueError('G2 coverage/contention below reviewed baseline')
    if sorted(row['round'] for row in g2['rounds'])!=list(range(rounds)) or any(
            row['double_allocations']!=0 or row['negative_stock'] is not False for row in g2['rounds']):
        raise ValueError('G2 rounds duplicate, missing or unsafe')
    if sum(row['observed_lock_waiters']>=2 for row in g2['rounds'])!=waits:
        raise ValueError('G2 contention summary differs from measured rounds')
    return counts


def leftover_evidence(log):
    def measured(marker):
        rows=[json.loads(line.split(marker+' ',1)[1]) for line in log.splitlines() if marker+' ' in line]
        if len(rows)!=1:raise ValueError('Missing/duplicate '+marker)
        return rows[0]
    mail=measured('SPH_RFQ_CAPTURE');performance=measured('SPH_RULE_PERFORMANCE')
    if (mail.get('synthetic') is not True or mail.get('captured_messages',0)<1 or
            mail.get('real_smtp_calls')!=0 or mail.get('bot_rfq_denied') is not True or mail.get('human_rfq_state')!='sent'):
        raise ValueError('Unsafe/incomplete captured RFQ evidence')
    samples=performance['samples']
    expected={(model,count) for model in ('mail.message','ir.attachment') for count in (2,10,30)}
    if (performance.get('synthetic') is not True or len(samples)!=6 or
            {(row['model'],row['own_documents']) for row in samples}!=expected or
            any(row['returned']!=row['own_documents'] or row['foreign_candidates']!=1 or
                row['sql_queries']<=0 or row['seconds']<0 for row in samples)):
        raise ValueError('Incomplete/foreign-visible rule characterization')
    return {'INFO-B7b-4':mail,'INFO-B7b-5':performance}


def execute(directory=None):
    directory=Path(directory or ROOT/'evidence');directory.mkdir(exist_ok=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report={'scope':'P0 SYNTHETIC CI/disposable rehearsal; NOT pilot-ready',
        'upgrade_limit':'Empty and retained-SYNTHETIC addon upgrade fixtures only; NOT a production/business-data migration approval',
        'base_sha':BASE,'final_tip_sha':commit,'status':'FAIL',
        'ci_run_url':'https://github.com/'+os.environ.get('GITHUB_REPOSITORY','monthop-gmail/odoo-contributions')+
            '/actions/runs/'+os.environ.get('GITHUB_RUN_ID','local'),
        'open_items':[{'id':'DN-B8-1','status':'OWNER DECISION NEEDED BEFORE P1',
            'detail':'Picking ownership classification/narrowing for native warehouse; unchanged here.'}],
        'boundary':'No staging/main/PR/merge/deploy/spend/credentials/real data; independent review still required.'}
    load=lambda name:json.loads((directory/name).read_text())
    try:
        expected=json.loads((ROOT/'expected-tests.json').read_text())
        validate_test_log((directory/'odoo-tests.log').read_text(),expected)
        report['bound']={'status':'PASS','executed_bindings':len(expected)}
        report['leftover_findings']=leftover_evidence((directory/'odoo-tests.log').read_text())
        report['checks']=case_statuses(directory/'live-suite.xml')
        if set(report['checks'].values())!={'PASS'}:raise ValueError('A live case did not pass')
        fresh=load('Fresh-live-start.json')
        if fresh['commit']!=commit or fresh['companies']!=1 or any(fresh[key]!=0 for key in ('sales','purchases','reservations')):
            raise ValueError('Live suite did not start clean')
        report['fresh_live_start']=fresh
        manifest=load('manifest.json')
        if manifest['commit']!=commit:raise ValueError('Stale live manifest')
        sources={key:load('Flow-'+key+'-results.json') for key in ('A','B')}
        baseline_diff=load('Baseline-diff-review.json')
        if baseline_diff['status']!='PASS' or baseline_diff['reviewed_sha']!=REVIEWED or baseline_diff['commit']!=commit:
            raise ValueError('Missing/stale baseline co-change check')
        validate_paths(baseline_diff['changed_paths'])
        report['baseline_diff_review']=baseline_diff
        report['demo']=validate_demo(load('Demo-results.json'),sources,commit,
            json.loads((ROOT/'version-pins.json').read_text()),(directory/'Demo-walkthrough.md').read_text())
        if (directory/'Dashboard-formulas.md').read_bytes()!=(ROOT/'docs/dashboard-formulas.md').read_bytes():
            raise ValueError('Dashboard formula copy differs from reviewed source')
        dashboard=validate_dashboard(load('Dashboard-results.json'),(directory/'Dashboard.html').read_text(),
            sources,commit,report['demo'],(directory/'Demo-walkthrough.md').read_text(),
            json.loads((ROOT/'version-pins.json').read_text()),json.loads((ROOT/'p0-evidence-baseline.json').read_text())['g3'],
            gate_summary(directory/'live-suite.xml'))
        report['dashboard']={'metrics':dashboard['metrics'],'units':dashboard['units'],'epochs':dashboard['epochs'],
            'demo':dashboard['demo'],'derivations':dashboard['derivations'],
            'formulas':'docs/dashboard-formulas.md','definition':'Reserved/requested units; not delivered fill. Blockers = unfilled confirmed demo orders.'}
        report['fresh_epochs']={key:source['measurements']['existing_sales_before'] for key,source in sources.items()}
        baseline=json.loads((ROOT/'p0-evidence-baseline.json').read_text())
        report['evidence_baseline']=baseline
        report['baseline_review']=validate_baseline(baseline)
        g3=load('G3-authority-results.json');report['g2']=load('G2-request-results.json')
        report['g3']=validate_live_evidence(report['g2'],g3,baseline)
        report['upgrade']=load('Upgrade-results.json');validate_upgrade(report['upgrade'],commit)
        report['retained_upgrade']=load('Retained-upgrade-results.json')
        validate_retained(report['retained_upgrade'],commit)
        report['status']='PASS'
    except Exception as error:
        report['error_type']=type(error).__name__
        if isinstance(error,BaselineReviewRequired):report['error_message']=str(error)
    files={str(path.relative_to(directory)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob('*')) if path.is_file() and not path.name.startswith('P0-')}
    manifest_bytes=json.dumps(files,sort_keys=True,separators=(',',':')).encode()
    report['artifact_digests']={'base_ci_archive':BASE_ARTIFACT,'evidence_files_sha256':files,
        'evidence_manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
        'current_ci_archive':'Assigned by upload-artifact after report creation; recorded in hub result (self-hash cannot be embedded).'}
    target=directory/'P0-report.json';target.write_text(json.dumps(report,indent=2)+'\n')
    (directory/'P0-report.sha256').write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  P0-report.json\n')
    checks=report.get('checks',{});metrics=report.get('dashboard',{}).get('metrics',{})
    text='# SPH P0 synthetic rehearsal — '+report['status']+'\n\nBase: `'+BASE+'`\n\nFinal: `'+commit+'`\n\n'
    text+='| Check | Result |\n|---|---|\n'+''.join('| '+key+' | '+checks.get(key,'UNKNOWN')+' |\n' for key in ('flow_a','flow_b','g1_http','g2_race','g3_authority'))
    text+='| INFO-B8-2 upgrade | '+report.get('upgrade',{}).get('status','UNKNOWN')+' |\n\n'
    text+='Measured dashboard: `'+json.dumps(metrics,sort_keys=True)+'`. Units: `'+json.dumps(report.get('dashboard',{}).get('units',{}))+'`.\n\n'
    text+='G3: `'+json.dumps(report.get('g3',{}))+'`. Bound: `'+json.dumps(report.get('bound',{}))+'`.\n\n'
    text+='Demo walkthrough: **'+report.get('demo',{}).get('status','UNKNOWN')+'**; see Demo-walkthrough.md for ordered expected/observed steps.\n\n'
    text+='Retained synthetic transaction upgrade: '+report.get('retained_upgrade',{}).get('status','UNKNOWN')+'. PO/picking/reservation/membership snapshots compared on the same isolated DB.\n\n'
    text+='INFO-B8P0-3: **NOT production/business-data migration approval**. Both empty and retained-SYNTHETIC fixtures are tested, never real data.\n\n'
    text+='Upgrade acceptance requires: previous B7c installed, same DB updated to final tip; exactly one XMLID, same rule ID, unchanged total picking-rule IDs, picking-only grant and post-upgrade isolation. See JSON/logs for the actual result; missing/failed checks do not pass.\n\n'
    text+='Evidence-files digest SHA256: `'+report['artifact_digests']['evidence_manifest_sha256']+'`. Per-file/base-archive hashes in P0-report.json; report hash in P0-report.sha256. Final upload archive digest is recorded in hub after upload.\n\n'
    text+='DN-B8-1: **owner decision needed before P1**; global picking scope unchanged. INFO-B7b-4/5 synthetic mail capture and performance characterization are in module-test logs; production capacity remains unvalidated. Synthetic harness only; NOT pilot-ready. No staging/merge/deploy/spend/credentials/real data.\n'
    (directory/'P0-report.md').write_text(text)
    print('SPH_P0_RESULT '+json.dumps({'status':report['status'],'commit':commit,'checks':checks,'reason':report.get('error_message')}))
    return report


if __name__=='__main__':raise SystemExit(0 if execute()['status']=='PASS' else 1)
