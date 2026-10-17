"""Measured artifact dashboard; no Odoo endpoint, ACL or external dependency."""
import html
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from demo import validate as validate_demo

ROOT=Path(__file__).resolve().parents[1]


def calculate(sources,commit):
    requested=reserved=0
    backorders=[];stockouts=[];blockers=[];inputs={}
    for scenario,data in sources.items():
        if data['commit']!=commit:
            raise ValueError('Dashboard refuses mixed commit evidence')
        measured=data['measurements']
        if measured['existing_sales_before']!=0:
            raise ValueError('Dashboard requires clean scenario databases')
        rows=measured['orders'];known={row['so_id'] for row in rows}
        if len(known)!=len(rows):raise ValueError('Duplicate scenario order')
        for row in rows:
            demand=row['requested_qty'];allocation=row['reserved_qty']
            if not 0<=allocation<=demand:raise ValueError('Invalid measured allocation')
            requested+=demand;reserved+=allocation
            if row['state']=='sale' and allocation<demand:
                blockers.append({'scenario':scenario,'so_id':row['so_id'],'unfilled_qty':demand-allocation})
        audit_orders=set()
        for row in measured['stockout_audits']:
            if row['audit_id']<=0 or row['action']!='sale.reserve.stockout' or row['outcome']!='deny':
                raise ValueError('Invalid stockout audit provenance')
            audit_orders.add(row['so_id'])
        if audit_orders!=set(measured['stockout_so_ids']):
            raise ValueError('Stockout IDs do not match system audit provenance')
        if not set(measured['stockout_so_ids'])<=known:
            raise ValueError('Stockout references an unknown scenario order')
        stockouts.extend({'scenario':scenario,'so_id':oid} for oid in sorted(set(measured['stockout_so_ids'])))
        backorders.extend({'scenario':scenario,'picking_id':pid} for pid in sorted(set(measured['backorder_picking_ids'])))
        inputs[scenario]=measured
    return {'scope':'SYNTHETIC measured Flow A+B snapshots; independent clean DB epochs',
        'commit':commit,'metrics':{'fill_rate':reserved/requested if requested else None,
        'backorders':len(backorders),'stockouts':len(stockouts),'open_blockers':len(blockers)},
        'units':{'requested':requested,'reserved':reserved},'inputs':inputs,
        'backorder_pickings':backorders,'stockout_orders':stockouts,'open_fulfillment_blockers':blockers,
        'definitions_file':'../docs/dashboard-formulas.md'}


FORMULAS={
    'fill_rate':'Observed reserved native move units / requested SO line units (not delivery fill).',
    'backorders':'Count distinct observed sales picking IDs with backorder_id, namespaced by scenario epoch.',
    'stockouts':'Count distinct scenario SOs with durable sale.reserve.stockout deny audit provenance.',
    'open_blockers':'Count confirmed scenario SOs with requested units greater than reserved units.',
    'ci_gate_blockers':'Failure + error + skipped counts in the five-case live suite; separate from fulfillment.'}
STEPS={'fill_rate':['A1','A3','B1','B5'],'backorders':['A3','B5'],
    'stockouts':['A2','B1'],'open_blockers':['A3','B1','B5'],'ci_gate_blockers':[]}
LABELS={'fill_rate':'Reservation fill rate','backorders':'Native backorder pickings',
    'stockouts':'Stockout attempts','open_blockers':'Open fulfillment blockers','ci_gate_blockers':'CI gate blockers (separate)'}


def reconcile(sources,commit,demo,walkthrough,pins,g3,gates):
    validate_demo(demo,sources,commit,pins,walkthrough)
    if g3!={'deny':140,'allow':22,'observations':162}:
        raise ValueError('Unreviewed G3 pin')
    steps={row['id']:row for row in demo['steps']}
    for key,step in (('A','A3'),('B','B5')):
        if steps[step]['evidence']['dashboard_measurements']!=sources[key]['measurements']:
            raise ValueError('Dashboard rows differ from demo step evidence')
    a,b=sources['A'],sources['B']
    arows=a['measurements']['orders'];brows=b['measurements']['orders']
    winner=a['winning_reservation']['so_id']
    if (len(arows)!=2 or {row['so_id'] for row in arows}!=set(a['orders']) or
            any(row['requested_qty']!=1 or row['state']!='sale' or
                row['reserved_qty']!=(1 if row['so_id']==winner else 0) for row in arows) or
            len(brows)!=1 or brows[0]!={'so_id':b['shortage_so_id'],'state':'sale','requested_qty':1,'reserved_qty':0}):
        raise ValueError('Dashboard units differ from the last-unit/shortage demo observations')
    if (set(a['measurements']['stockout_so_ids'])!=set(a['orders'])-{winner} or
            b['measurements']['stockout_so_ids']!=[b['shortage_so_id']]):
        raise ValueError('Dashboard stockouts differ from demo shortage steps')
    result=calculate(sources,commit)
    if result['units']['reserved']!=steps['A3']['observed']['reserved_total']:
        raise ValueError('Dashboard allocation differs from demo')
    if set(gates)!={'tests','failures','errors','skipped'} or gates['tests']!=5 or any(type(v) is not int or v<0 for v in gates.values()):
        raise ValueError('Invalid live gate summary')
    result['definitions_file']='Dashboard-formulas.md'
    result['ci_gate_blockers']=sum(gates[key] for key in ('failures','errors','skipped'))
    result.update(epochs=demo['epochs'],pins=pins,g3_pin=g3,status='PASS',gate_summary=gates,
        demo={'file':'Demo-results.json','walkthrough':'Demo-walkthrough.md',
            'json_sha256':hashlib.sha256((json.dumps(demo,indent=2)+'\n').encode()).hexdigest(),
            'walkthrough_sha256':hashlib.sha256(walkthrough.encode()).hexdigest(),
            'source_sha256':demo['sources_sha256']})
    def namespace(rows,model):
        return [dict(row,epoch=demo['epochs'][row['scenario']],model=model) for row in rows]
    orders=namespace([{'scenario':key,**row} for key in ('A','B') for row in sources[key]['measurements']['orders']],'sale.order')
    total=len(orders)
    result['derivations']={
        'fill_rate':{'numerator':result['units']['reserved'],'denominator':result['units']['requested'],'records':orders},
        'backorders':{'numerator':result['metrics']['backorders'],'denominator':None,'denominator_meaning':'not applicable: distinct picking count, not a rate',
            'records':namespace(result['backorder_pickings'],'stock.picking')},
        'stockouts':{'numerator':result['metrics']['stockouts'],'denominator':total,'denominator_meaning':'observed SO population; metric remains a count',
            'records':namespace(result['stockout_orders'],'sale.order')},
        'open_blockers':{'numerator':result['metrics']['open_blockers'],'denominator':total,'denominator_meaning':'observed SO population; metric remains a count',
            'records':namespace(result['open_fulfillment_blockers'],'sale.order')},
        'ci_gate_blockers':{'numerator':result['ci_gate_blockers'],'denominator':gates['tests'],'denominator_meaning':'live cases, not fulfillment orders',
            'records':[{'file':'live-suite.xml',**gates}]}}
    for key,row in result['derivations'].items():row.update(formula=FORMULAS[key],steps=STEPS[key])
    return result


def render(result):
    esc=lambda value:html.escape(str(value),quote=True)
    dump=lambda value:esc(json.dumps(value,sort_keys=True))
    rows=[]
    for key,row in result['derivations'].items():
        numerator=row['numerator'];denominator=row['denominator']
        display=f'{numerator:g} / {denominator:g} = {100*numerator/denominator:.2f}%' if key=='fill_rate' and denominator else (
            'unknown (zero demand)' if key=='fill_rate' else str(numerator)+' counted / '+(str(denominator) if denominator is not None else 'not applicable'))
        links=' '.join('<a href="Demo-walkthrough.md#'+esc(step.lower())+'">'+esc(step)+'</a>' for step in row['steps'])
        if not links:links='<a href="live-suite.xml">live-suite.xml</a>'
        rows.append('<tr><th>'+esc(LABELS[key])+'</th><td>'+esc(display)+'<br>'+esc(row.get('denominator_meaning','reserved / requested units'))+
            '</td><td>'+esc(row['formula'])+'</td><td><code>'+dump(row['records'])+'</code></td><td>'+links+'</td></tr>')
    meanings=''.join('<li>'+esc(text)+'</li>' for text in (
        'Reservation fill is allocation, not delivery or customer service level.',
        'Unfilled demand is not automatically a native backorder.',
        'Stockouts count audited shortage attempts, not distinct catalog items.',
        'Fulfillment blockers are unfilled confirmed demo orders, not owner/hub tasks.',
        'All definitions remain awaiting owner confirmation (M6.4); nothing is marked confirmed.'))
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>SPH synthetic dashboard</title>'
        '<style>body{font:17px system-ui;margin:2rem;line-height:1.5}table{border-collapse:collapse;width:100%}th,td{padding:.6rem;border:1px solid #ddd;text-align:left;vertical-align:top}code{overflow-wrap:anywhere}header{background:#fff2cc;padding:1rem}</style></head><body>'
        '<header><h1>SPH Flow A+B dashboard</h1><strong>SYNTHETIC P0 - not KPIs, no SLA targets, not pilot sign-off</strong></header>'
        '<p>SHA: <code>'+esc(result['commit'])+'</code></p><p>Pins: <code>'+dump(result['pins'])+'</code></p>'
        '<p>G3 exact pin: <code>'+dump(result['g3_pin'])+'</code></p><p>Scenario epochs: <code>'+dump(result['epochs'])+'</code>. Record IDs are not joinable across epochs.</p>'
        '<table><thead><tr><th>Metric</th><th>Numerator / denominator</th><th>Formula</th><th>Counted records</th><th>Walkthrough</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'
        '<h2>Metric meanings for owner confirmation (M6.4)</h2><ul>'+meanings+'</ul>'
        '<p><a href="Dashboard-formulas.md">Formula definitions</a> · <a href="Demo-walkthrough.md">Matching demo walkthrough</a> · <a href="Demo-results.json">Demo JSON</a> · <a href="Dashboard-results.json">Dashboard evidence</a></p></body></html>\n')


def validate(result,page,sources,commit,demo,walkthrough,pins,g3,gates):
    expected=reconcile(sources,commit,demo,walkthrough,pins,g3,gates)
    if result!=expected or page!=render(expected):
        raise ValueError('Dashboard JSON/HTML differs from validated demo evidence')
    return expected


def gate_summary(path):
    suite=ET.parse(path).getroot()
    return dict(tests=len(suite.findall('testcase')),**{key:int(suite.get(key,'0')) for key in ('failures','errors','skipped')})


def execute(directory=None):
    directory=Path(directory or ROOT/'evidence')
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    load=lambda name:json.loads((directory/name).read_text())
    sources={key:load('Flow-'+key+'-results.json') for key in ('A','B')}
    result=reconcile(sources,commit,load('Demo-results.json'),(directory/'Demo-walkthrough.md').read_text(),
        json.loads((ROOT/'version-pins.json').read_text()),json.loads((ROOT/'p0-evidence-baseline.json').read_text())['g3'],
        gate_summary(directory/'live-suite.xml'))
    (directory/'Dashboard-formulas.md').write_bytes((ROOT/'docs/dashboard-formulas.md').read_bytes())
    (directory/'Dashboard-results.json').write_text(json.dumps(result,indent=2)+'\n')
    (directory/'Dashboard.html').write_text(render(result))
    print('SPH_DASHBOARD_RESULT '+json.dumps({'commit':commit,'metrics':result['metrics'],'units':result['units']}))
    return result


def main():
    parser=argparse.ArgumentParser(description='Render validated demo/dashboard evidence only; never starts a harness.')
    parser.add_argument('--from-evidence',action='store_true',help='Explicit render-only mode (also the default).')
    parser.parse_args()
    execute()
    return 0


if __name__=='__main__':raise SystemExit(main())
