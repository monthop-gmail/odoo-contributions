"""Real loopback sessions against committed fixtures; no credentials in evidence."""
import csv
import http.client
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from pathlib import Path
from harness import DC, ODOO_ARGS, ROOT


def setup(revoke=False):
    code = ('revoke=True\n' if revoke else '') + "exec(open('/opt/sph/scripts/live_setup.py').read())\n"
    result = subprocess.run(DC + ['exec', '-T', 'odoo', 'odoo', 'shell'] + ODOO_ARGS +
        ['--no-http', '--log-level=error'], input=code, text=True, capture_output=True)
    if result.returncode:
        # Do not echo IPC stdout: it contains ephemeral session/share tokens.
        locations = re.findall(r'live_setup.py[^\n]*line (\d+)', result.stderr)
        print('G1 setup failure location: ' + (locations[-1] if locations else 'bootstrap'))
        raise RuntimeError('G1 disposable fixture setup failed')
    return json.loads(result.stdout.strip().splitlines()[-1])


def execute():
    fixture = setup()
    rows = []
    def get(path, role=None):
        connection = http.client.HTTPConnection('127.0.0.1',18069,timeout=25)
        headers = {'Cookie': 'session_id='+fixture['sessions'][role]} if role else {}
        try:
            connection.request('GET',path,headers=headers)
            response=connection.getresponse(); body=response.read().decode()
            return response.status,body
        finally: connection.close()
    def rpc(role,model,method,args,kwargs=None):
        connection=http.client.HTTPConnection('127.0.0.1',18069,timeout=25)
        try:
            body=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':{
                'model':model,'method':method,'args':args,'kwargs':kwargs or {}}})
            connection.request('POST','/web/dataset/call_kw',body,{
                'Content-Type':'application/json','Cookie':'session_id='+fixture['sessions'][role]})
            response=connection.getresponse();return json.loads(response.read())
        finally:connection.close()
    def evidence(name,actor,allowed):
        rows.append({'test':name,'actor':actor,'outcome':'ALLOW' if allowed else 'DENY','result':'PASS'})
    # Positive per every named role, exact payload fields and HTML; hostile selectors ignored.
    for role in fixture['sessions']:
        index = 1 if role == 'sph_center_receiver' else 0
        assert 'result' in rpc(role, 'sale.order', 'read', [[fixture['orders'][index]], ['name']])
        for product,band in zip(fixture['products'],('In stock','Low','Out','Low')):
            path='/sph/band/'+str(product)
            status,body=get(path+'?format=json&center_id=999999&location=999999',role)
            assert status==200 and json.loads(body)=={'band':band}
            status,body=get(path,role)
            assert status==200 and body=='<span>'+band+'</span>'
        evidence('test_own_projection',role,True)
    centers=('sph_center_requester','sph_center_receiver')
    for i,role in enumerate(centers):
        own,other=fixture['orders'][i],fixture['orders'][1-i]
        for model,key,fields in (('sale.order','orders',['name']),('sale.order.line','lines',['price_unit']),
            ('product.pricelist','lists',['name']),('product.pricelist.item','items',['fixed_price']),
            ('stock.picking','pickings',['name'])):
            ids=fixture[key]
            assert 'result' in rpc(role,model,'read',[[ids[i]],fields])
            assert 'error' in rpc(role,model,'read',[[ids[1-i]],fields])
            assert rpc(role,model,'search',[[['id','in',ids]]])['result']==[ids[i]]
            assert rpc(role,model,'search_count',[[['id','in',ids]]])['result']==1
            assert 'error' in rpc(role,model,'export_data',[[ids[1-i]],fields])
            assert 'error' in rpc(role,model,'export_data',[[ids[i]],fields])  # Portal export is wholly denied.
        evidence('test_bidirectional_id_denial',role,False)
        grouped=rpc(role,'sale.order','read_group',[[['id','in',fixture['orders']]],['sph_center_id'],['sph_center_id']])
        assert 'result' in grouped and len(grouped['result'])==1
        evidence('test_search_count_group_export_report',role,False)
        spoof=rpc(role,'sale.order','search',[[['id','=',other]]],{'context':{
            'sph_center_id':999999,'partner_id':999999,'pricelist':fixture['lists'][1-i],'location':999999}})
        assert spoof.get('result')==[]
        evidence('test_partner_pricelist_location_spoof',role,False)
        for query in ('', '?'+urlencode({'access_token':fixture['tokens'][1-i]}),
                      '?'+urlencode({'access_token':fixture['tokens'][1-i],'report_type':'html'}),
                      '?'+urlencode({'access_token':fixture['tokens'][1-i],'report_type':'pdf','download':'true'})):
            status,body=get('/my/orders/'+str(other)+query,role)
            assert status in (302,303,403,404) and fixture['names'][1-i] not in body
        status,body=get('/my/orders/'+str(own),role)
        assert status==200 and fixture['names'][i] in body
        evidence('test_cross_center_share_token',role,False)
        assert rpc(role,'stock.quant','search',[[]]).get('result',[])==[]
    # Attachment token cannot turn another center's document into a public download.
    url='/web/content/'+str(fixture['attachment'])+'?'+urlencode({'access_token':fixture['attachment_token']})
    for role in (None,centers[0]):
        status,body=get(url,role)
        assert status in (302,303,403,404) and 'FIXTURE protected payload' not in body
    evidence('test_lines_attachments_no_leak',centers[0],False)
    bot='sph_bot'
    assert 'result' in rpc(bot,'sale.order','read',[[fixture['orders'][0]],['name']])
    assert 'error' in rpc(bot,'sale.order','read',[[fixture['orders'][1]],['name']])
    assert rpc(bot,'stock.quant','search',[[]]).get('result')==[]
    for field in ('qty_available','free_qty','standard_price'):
        assert 'error' in rpc(bot,'product.product','read',[[fixture['products'][0]],[field]])
    evidence('test_ai_scope_and_group_union',bot,False)
    status,body=get('/my/orders/'+str(fixture['orders'][0])+'?'+urlencode({'access_token':fixture['tokens'][0]}))
    assert status in (302,303,403,404) and fixture['names'][0] not in body
    status,body=get('/sph/band/'+str(fixture['products'][0]))
    assert status==403 and body=='Unavailable'
    # Generic denial contains none of the actual product's free qty 8 or ±1.
    assert all(str(number) not in body for number in (7,8,9))
    setup(revoke=True)
    status,body=get('/sph/band/'+str(fixture['products'][0]),centers[0])
    assert status==403 and body=='Unavailable'
    assert 'error' in rpc(centers[0],'sale.order','read',[[fixture['orders'][0]],['name']])
    evidence('test_anonymous_revoke_denial',centers[0],False)
    directory=ROOT/'evidence';directory.mkdir(exist_ok=True)
    (directory/'G1-http-results.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    with (directory/'G1-access-matrix.csv').open('w') as output:
        writer=csv.DictWriter(output,fieldnames=['test','actor','outcome','result']);writer.writeheader();writer.writerows(rows)

    (directory/'G1-effective-acl-rules.json').write_text(json.dumps(fixture['rules'],indent=2)+'\n')
    suite=ET.Element('testsuite',name='G1 live access matrix',tests=str(len(rows)),failures='0',errors='0')
    for row in rows:
        ET.SubElement(suite,'testcase',name=row['test'],classname=row['actor'])
    ET.ElementTree(suite).write(directory/'G1-assertions.xml',encoding='utf-8',xml_declaration=True)
