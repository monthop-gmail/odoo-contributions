"""Measured artifact dashboard; no Odoo endpoint, ACL or external dependency."""
import html
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

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
        if not set(measured['stockout_so_ids'])<=known:
            raise ValueError('Stockout references an unknown scenario order')
        stockouts.extend({'scenario':scenario,'so_id':oid} for oid in set(measured['stockout_so_ids']))
        backorders.extend({'scenario':scenario,'picking_id':pid} for pid in set(measured['backorder_picking_ids']))
        inputs[scenario]=measured
    return {'scope':'SYNTHETIC measured Flow A+B snapshots; independent clean DB epochs',
        'commit':commit,'metrics':{'fill_rate':reserved/requested if requested else None,
        'backorders':len(backorders),'stockouts':len(stockouts),'open_blockers':len(blockers)},
        'units':{'requested':requested,'reserved':reserved},'inputs':inputs,
        'backorder_pickings':backorders,'stockout_orders':stockouts,'open_fulfillment_blockers':blockers,
        'definitions_file':'../docs/dashboard-formulas.md'}


def execute(directory=None):
    directory=Path(directory or ROOT/'evidence')
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,text=True,capture_output=True,check=True).stdout.strip()
    sources={label:json.loads((directory/f'Flow-{label}-results.json').read_text()) for label in ('A','B')}
    result=calculate(sources,commit)
    suite=ET.parse(directory/'live-suite.xml').getroot()
    result['ci_gate_blockers']=sum(int(suite.get(key,'0')) for key in ('failures','errors','skipped'))
    (directory/'Dashboard-results.json').write_text(json.dumps(result,indent=2)+'\n')
    labels={'fill_rate':'Reservation fill rate','backorders':'Native backorder pickings',
        'stockouts':'Stockout attempts','open_blockers':'Open fulfillment blockers'}
    rows=''.join('<tr><th>'+labels[key]+'</th><td>'+html.escape(str(value))+'</td></tr>' for key,value in result['metrics'].items())
    page='<!doctype html><meta charset="utf-8"><title>SPH synthetic dashboard</title><style>body{font:18px system-ui;max-width:850px;margin:3rem auto}th,td{text-align:left;padding:.6rem;border-bottom:1px solid #ddd}</style><h1>SPH Flow A+B</h1><p>Synthetic measured snapshots; no SLA targets. Separate clean database per scenario.</p><table>'+rows+'</table><p>Fill rate is reserved units / requested units, not delivery fill rate. Blockers are unfilled confirmed demo orders, not hub tasks or pilot governance blockers.</p><p>Commit: '+html.escape(commit)+'</p><p><a href="Dashboard-results.json">Inputs, units and record references</a> · <a href="Flow-A-results.json">Flow A</a> · <a href="Flow-B-results.json">Flow B</a></p>'
    (directory/'Dashboard.html').write_text(page)
    print('SPH_DASHBOARD_RESULT '+json.dumps({'commit':commit,'metrics':result['metrics'],'units':result['units']}))
    return result


if __name__=='__main__':execute()
