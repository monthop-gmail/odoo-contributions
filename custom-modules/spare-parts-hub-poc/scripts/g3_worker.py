"""Committed live HTTP approval matrix; sole deny-row assertions live here."""
import http.client
import json
from odoo import api, SUPERUSER_ID
from odoo.http import root
from odoo.addons.sph_core.tests.test_purchase_authority import prepare

assert env.cr.dbname=='sph_poc'
assert env.company.po_double_validation=='two_step' and env.company.po_double_validation_amount==0
fx=prepare(env)
maker_id=env['purchase.order'].with_user(fx['approver']).sph_prepare(fx['supplier'].id,fx['product'].id)
fx['maker_po']=env['purchase.order'].browse(maker_id)
sessions={}
for role in ('bot','approver'):
    user=fx[role];session=root.session_store.new()
    session.update({'db':'sph_poc','uid':user.id,'login':user.login,
        'context':dict(user.with_user(user).context_get()),'session_token':user._compute_session_token(session.sid)})
    root.session_store.save(session);sessions[role]=session.sid
env.cr.commit()
rows=[]


def rpc(role,record,method,args=None,kwargs=None):
    connection=http.client.HTTPConnection('127.0.0.1',8069,timeout=20)
    try:
        body=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':{
            'model':record._name,'method':method,'args':[record.ids]+(args or []),'kwargs':kwargs or {}}})
        connection.request('POST','/web/dataset/call_kw',body,{
            'Content-Type':'application/json','Cookie':'session_id='+sessions[role]})
        response=connection.getresponse();return json.loads(response.read())
    finally: connection.close()


def audit_count(record,role,action,outcome):
    with env.registry.cursor() as cursor:
        observer=api.Environment(cursor,SUPERUSER_ID,{})
        count=observer['sph.authority.audit'].search_count([('res_model','=',record._name),
            ('res_id','=',record.id),('actor_uid','=',fx[role].id),('action','=',action),('outcome','=',outcome)])
        return count


def observed(record,role,action,outcome,before=0):
    assert audit_count(record,role,action,outcome)>before
    rows.append({'model':record._name,'action':action,'role':role,'outcome':outcome,'audit_seen':True})


def deny(record,method,action,args=None,kwargs=None):
    before=audit_count(record,'bot',action,'deny')
    response=rpc('bot',record,method,args,kwargs)
    assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
    observed(record,'bot',action,'deny',before)


def allow(record,method,action,args=None,kwargs=None):
    before=audit_count(record,'approver',action,'allow')
    assert 'result' in rpc('approver',record,method,args,kwargs)
    observed(record,'approver',action,'allow',before)


# The native-style approval refusal is tested by committed state, not exception.
assert 'result' in rpc('bot',fx['po'],'button_approve',[],{'force':True})
with env.registry.cursor() as cursor:
    observer=api.Environment(cursor,SUPERUSER_ID,{})
    assert observer['purchase.order'].browse(fx['po'].id).state=='draft'
observed(fx['po'],'bot','po.approve','deny')
deny(fx['po'],'write','po.approve',[{'state':'purchase'}])
deny(fx['po'],'button_confirm','po.approve')
deny(fx['po'],'action_rfq_send','po.send')
for key,method,action,args in (
    ('so_line','write','sale.order.line.price_unit',[{'price_unit':109}]),
    ('po_line','write','purchase.order.line.price_unit',[{'price_unit':109}]),
    ('scrap','action_validate','scrap.validate',[]),
    ('quant','action_apply_inventory','inventory.apply',[]),
    ('quant','write','quant.write',[{'quantity':5}])):
    deny(fx[key],method,action,args)
    if action=='inventory.apply':
        assert 'result' in rpc('approver',fx['quant'],'write',[{'inventory_quantity':6}])
    allow(fx[key],method,action,args)
allow(fx['po'],'sph_review','po.review')
allow(fx['po'],'button_confirm','po.confirm')
with env.registry.cursor() as cursor:
    observer=api.Environment(cursor,SUPERUSER_ID,{})
    po=observer['purchase.order'].browse(fx['po'].id)
    assert po.state=='purchase' and po.sph_maker_uid==fx['bot'].id
    assert observer['stock.scrap'].browse(fx['scrap'].id).state=='done'
# Independently committed deny rows remain visible after failed RPC rollback.
response=rpc('approver',fx['maker_po'],'sph_review')
assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
observed(fx['maker_po'],'approver','po.review','deny')
print('SPH_G3_RESULT '+json.dumps({'matrix':rows,'deny_rows_observed':sum(r['outcome']=='deny' for r in rows),
    'allow_rows_observed':sum(r['outcome']=='allow' for r in rows),'po_state':'purchase',
    'maker_checker_distinct':True,'settings':{'validation':'two_step','amount':0}}),flush=True)
