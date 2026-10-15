"""Consolidate measured, same-tip CI evidence; never turn missing/skipped into PASS."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from dashboard import calculate
from harness import ROOT
from test_results import validate_test_log
from upgrade_path import PREVIOUS

BASE='0e2f64e08a2c24b900c7c77f2d71231975298f50'
BASE_ARTIFACT={'run_id':38796314664,'artifact_id':12002955569,
    'sha256':'61e66867a8a01b5eef1032ea5d3316c9954e589fd44c46293d2f3c05ef8d4f94'}


def case_statuses(path):
    suite=ET.parse(path).getroot()
    cases={case.get('name'):('FAIL' if any(case.find(tag) is not None for tag in ('failure','error'))
        else 'SKIP' if case.find('skipped') is not None else 'PASS') for case in suite.findall('testcase')}
    if len(cases)!=5 or set(cases)!={'g1_http','g2_race','g3_authority','flow_a','flow_b'}:
        raise ValueError('Incomplete or duplicate live cases')
    if any(int(suite.get(key,'0')) for key in ('failures','errors','skipped')):
        raise ValueError('Nonzero live summary')
    return cases


def validate_upgrade(data,commit):
    if data['status']!='PASS' or data['previous_sha']!=PREVIOUS or data['final_sha']!=commit or data['teardown']!='PASS':
        raise ValueError('Upgrade incomplete or stale')
    before,after=data['before'],data['after']
    if (before['xmlid_count']!=1 or after['xmlid_count']!=1 or before['rule_id']!=after['rule_id'] or
            before['all_picking_rule_ids']!=after['all_picking_rule_ids'] or
            before['grant']!='group_sph_po_hub' or after['grant']!='group_sph_picking_hub' or
            not after['grant_isolation_checked'] or not data['assertions'] or not all(data['assertions'].values())):
        raise ValueError('Upgrade identity/grant assertions failed')


def execute(directory=None):
    directory=Path(directory or ROOT/'evidence');directory.mkdir(exist_ok=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    report={'scope':'P0 SYNTHETIC CI/disposable rehearsal; NOT pilot-ready',
        'base_sha':BASE,'final_tip_sha':commit,'status':'FAIL',
        'ci_run_url':'https://github.com/'+os.environ.get('GITHUB_REPOSITORY','monthop-gmail/odoo-contributions')+
            '/actions/runs/'+os.environ.get('GITHUB_RUN_ID','local'),
        'open_items':[{'id':'DN-B8-1','status':'OWNER DECISION NEEDED BEFORE P1',
            'detail':'Picking ownership classification/narrowing for native warehouse; unchanged here.'},
            {'id':'INFO-B7b-4/5','status':'BACKLOG','detail':'RFQ actual mail-send / rule performance.'}],
        'boundary':'No staging/main/PR/merge/deploy/spend/credentials/real data; independent review still required.'}
    load=lambda name:json.loads((directory/name).read_text())
    try:
        expected=json.loads((ROOT/'expected-tests.json').read_text())
        validate_test_log((directory/'odoo-tests.log').read_text(),expected)
        report['bound']={'status':'PASS','executed_bindings':len(expected)}
        report['checks']=case_statuses(directory/'live-suite.xml')
        if set(report['checks'].values())!={'PASS'}:raise ValueError('A live case did not pass')
        manifest=load('manifest.json')
        if manifest['commit']!=commit:raise ValueError('Stale live manifest')
        sources={key:load('Flow-'+key+'-results.json') for key in ('A','B')}
        measured=calculate(sources,commit);dashboard=load('Dashboard-results.json')
        if dashboard['commit']!=commit or dashboard['metrics']!=measured['metrics'] or dashboard['units']!=measured['units']:
            raise ValueError('Dashboard differs from measured flows')
        report['dashboard']={'metrics':measured['metrics'],'units':measured['units'],
            'formulas':'docs/dashboard-formulas.md','definition':'Reserved/requested units; not delivered fill. Blockers = unfilled confirmed demo orders.'}
        report['fresh_epochs']={key:source['measurements']['existing_sales_before'] for key,source in sources.items()}
        g3=load('G3-authority-results.json');matrix=g3['matrix']
        if not matrix or not all(row['audit_seen'] for row in matrix):raise ValueError('Missing durable audit observation')
        denies=sum(row['outcome']=='deny' for row in matrix);allows=sum(row['outcome']=='allow' for row in matrix)
        if (denies,allows)!=(g3['deny_rows_observed'],g3['allow_rows_observed']):raise ValueError('G3 counts disagree')
        report['g3']={'deny':denies,'allow':allows,'observations':len(matrix)}
        report['g2']=load('G2-request-results.json')
        if report['g2']['double_allocations']!=0:raise ValueError('Double allocation')
        report['upgrade']=load('Upgrade-results.json');validate_upgrade(report['upgrade'],commit)
        report['status']='PASS'
    except Exception as error:
        report['error_type']=type(error).__name__
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
    text+='Upgrade: previous B7c installed, same DB updated to final tip; exactly one XMLID, same rule ID, unchanged total picking-rule IDs, picking-only grant and post-upgrade isolation. See JSON/logs for actual assertions.\n\n'
    text+='Evidence manifest SHA256: `'+report['artifact_digests']['evidence_manifest_sha256']+'`. Per-file/base-archive hashes in P0-report.json; report hash in P0-report.sha256. Final upload archive digest is recorded in hub after upload.\n\n'
    text+='DN-B8-1: **owner decision needed before P1**; global picking scope unchanged. INFO-B7b-4/5 remain backlog. Synthetic harness only; NOT pilot-ready. No staging/merge/deploy/spend/credentials/real data.\n'
    (directory/'P0-report.md').write_text(text)
    print('SPH_P0_RESULT '+json.dumps({'status':report['status'],'commit':commit,'checks':checks}))
    return report


if __name__=='__main__':raise SystemExit(0 if execute()['status']=='PASS' else 1)
