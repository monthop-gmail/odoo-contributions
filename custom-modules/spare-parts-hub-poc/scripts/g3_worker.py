"""Committed live HTTP approval matrix; sole deny-row assertions live here."""
import http.client
import json
from odoo import api, SUPERUSER_ID
from odoo.http import root
from odoo.addons.sph_core.tests.test_purchase_authority import prepare

assert env.cr.dbname=='sph_poc'
assert env.company.po_double_validation=='two_step' and env.company.po_double_validation_amount==0
env.ref('sph_core.fixture_user_sph_purchasing_approver').sph_center_ids=[(6,0,env.ref('sph_core.fixture_user_sph_bot').sph_center_ids.ids)]
fx=prepare(env)
fx['operator']=env.ref('sph_core.fixture_user_sph_hub_operator')
maker_id=env['purchase.order'].with_user(fx['approver']).sph_prepare(fx['supplier'].id,fx['product'].id)
fx['maker_po']=env['purchase.order'].browse(maker_id)
sessions={}
for role in ('bot','approver','operator'):
    user=fx[role];session=root.session_store.new()
    session.update({'db':'sph_poc','uid':user.id,'login':user.login,
        'context':dict(user.with_user(user).context_get()),'session_token':user._compute_session_token(session.sid)})
    root.session_store.save(session);sessions[role]=session.sid
env.cr.commit()
rows=[]


def rpc(role,record,method,args=None,kwargs=None,model_call=False):
    connection=http.client.HTTPConnection('127.0.0.1',8069,timeout=20)
    try:
        body=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':{
            'model':record._name,'method':method,'args':(args or []) if model_call else [record.ids]+(args or []),'kwargs':kwargs or {}}})
        connection.request('POST','/web/dataset/call_kw',body,{
            'Content-Type':'application/json','Cookie':'session_id='+sessions[role]})
        response=connection.getresponse();return json.loads(response.read())
    finally: connection.close()


def audit_count(record,role,action,outcome):
    with env.registry.cursor() as cursor:
        observer=api.Environment(cursor,SUPERUSER_ID,{})
        count=observer['sph.authority.audit'].search_count([('res_model','=',record._name),
            ('res_id','=',record.id or 0),('actor_uid','=',fx[role].id),('action','=',action),('outcome','=',outcome)])
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
    response=rpc('approver',record,method,args,kwargs)
    if 'error' in response:
        error=response['error'].get('data',{})
        print('SPH_G3_CHECK '+json.dumps({'action':action,'error_type':error.get('name'),'message':error.get('message')}),flush=True)
    assert 'error' not in response and response.get('jsonrpc')=='2.0'
    observed(record,'approver',action,'allow',before)


# B5b: exercise public lower-level mutation entrypoints over committed HTTP.
deny(fx['scrap'],'do_scrap','scrap.validate')
rows[-1]['path']='do_scrap'
quant_model=env['stock.quant']
before=audit_count(quant_model,'bot','quant.create','deny')
response=rpc('bot',quant_model,'create',[{
    'product_id':fx['product'].id,'location_id':fx['quant'].location_id.id,
    'quantity':1}],model_call=True)
assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
# A denied create has no resource ID: its plain audit res_id is zero.
observed(quant_model,'bot','quant.create','deny',before)
rows[-1]['path']='create'
with env.registry.cursor() as cursor:
    observer=api.Environment(cursor,SUPERUSER_ID,{})
    assert observer['stock.scrap'].browse(fx['scrap'].id).state=='draft'
    assert observer['stock.quant'].browse(fx['quant'].id).quantity==fx['quant'].quantity

# F3: a read-only reservation role cannot convert a draft SO to a commitment.
draft=fx['so_line'].order_id
response=rpc('operator',draft,'sph_reserve',['FIXTURE must-not-confirm'])
assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
observed(draft,'operator','sale.reserve.confirm','deny')
with env.registry.cursor() as cursor:
    original=api.Environment(cursor,SUPERUSER_ID,{})['sale.order'].browse(draft.id)
    assert original.state=='draft' and not original.picking_ids

# Scope and nonexistent IDs have identical public errors and durable ID-free audit.
fx['operator'].sph_center_ids=[(6,0,env.ref('sph_core.fixture_center_shared_b').ids)]
env.cr.commit()
env.registry.clear_cache()
env.registry.signal_changes()
for target in (fx['so'],env['sale.order'].browse(2147483647)):
    before=audit_count(env['sale.order'],'operator','sale.reserve.scope','deny')
    response=rpc('operator',target,'sph_reserve',['FIXTURE scope denial'])
    assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
    observed(env['sale.order'],'operator','sale.reserve.scope','deny',before)
    rows[-1]['path']='foreign' if target==fx['so'] else 'missing'

# SO action_lock/unlock and PO button_lock/unlock both reach the locked guard.
for key,methods in (('so',('action_lock','action_unlock')),('po',('button_lock','button_unlock'))):
    for method in methods:
        deny(fx[key],method,fx[key]._name+'.locked')
        rows[-1]['path']=method
        allow(fx[key],method,fx[key]._name+'.locked')
        rows[-1]['path']=method
    deny(fx[key],'write',fx[key]._name+'.locked',[{'locked':True}])
    rows[-1]['path']='write'
    with env.registry.cursor() as cursor:
        assert not api.Environment(cursor,SUPERUSER_ID,{})[fx[key]._name].browse(fx[key].id).locked

# I7: real failed HTTP writes roll back, but the separate-cursor bundle audit survives.
for key in ('so','po'):
    record=fx[key];action=record._name+'.locked.bundle'
    before=audit_count(record,'approver',action,'deny')
    response=rpc('approver',record,'write',[{'locked':True,'partner_id':env.ref('sph_core.fixture_supplier_2').id}])
    assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
    observed(record,'approver',action,'deny',before)
    with env.registry.cursor() as cursor:
        checked=api.Environment(cursor,SUPERUSER_ID,{})[record._name].browse(record.id)
        assert not checked.locked and checked.partner_id.id==record.partner_id.id

# Opaque references are metadata only; bot deny and human allow use real HTTP.
for key in ('so','po'):
    value='fixture:incident:g3-'+key
    deny(fx[key],'write','incident.reference',[{'sph_incident_ref':value}])
    rows[-1]['path']=key
    allow(fx[key],'write','incident.reference',[{'sph_incident_ref':value}])
    rows[-1]['path']=key
    with env.registry.cursor() as cursor:
        observer=api.Environment(cursor,SUPERUSER_ID,{})
        assert observer[fx[key]._name].browse(fx[key].id).sph_incident_ref==value
        assert observer['sph.authority.audit'].search_count([('res_model','=',fx[key]._name),
            ('res_id','=',fx[key].id),('actor_uid','=',fx['approver'].id),
            ('action','=','incident.reference'),('outcome','=','allow'),('incident_ref','=',value)])

response=rpc('bot',fx['so'],'sph_reserve',['FIXTURE bot role denied'])
assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
assert response['error']['data']['name']=='odoo.exceptions.UserError'

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
    ('so_line','write','sale.order.line.discount',[{'discount':7}]),
    ('po_line','write','purchase.order.line.discount',[{'discount':7}]),
    ('so','write','sale.order.pricelist_id',[{'pricelist_id':fx['pricelist'].id}]),
    ('scrap','action_validate','scrap.validate',[]),
    ('quant','action_apply_inventory','inventory.apply',[]),
    ('quant','write','quant.write',[{'quantity':5}])):
    deny(fx[key],method,action,args)
    if action=='inventory.apply':
        assert 'result' in rpc('approver',fx['quant'],'write',[{'inventory_quantity':6}])
    allow(fx[key],method,action,args)
    if action=='inventory.apply':
        with env.registry.cursor() as cursor:
            assert api.Environment(cursor,SUPERUSER_ID,{})['stock.quant'].browse(fx['quant'].id).quantity==6
allow(fx['po'],'sph_review','po.review')
before=audit_count(fx['po'],'approver','po.transition','deny')
response=rpc('approver',fx['po'],'write',[{'state':'purchase'}],{'context':{'sph_purchase_transition':True}})
assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
observed(fx['po'],'approver','po.transition','deny',before)
with env.registry.cursor() as cursor:
    checked=api.Environment(cursor,SUPERUSER_ID,{})['purchase.order'].browse(fx['po'].id)
    assert checked.state=='draft' and not checked.picking_ids
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
for method in ('button_approve','button_confirm'):
    before=audit_count(fx['maker_po'],'approver','po.approve','deny')
    response=rpc('approver',fx['maker_po'],method,[],{'force':True} if method=='button_approve' else {})
    assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
    observed(fx['maker_po'],'approver','po.approve','deny',before)
with env.registry.cursor() as cursor:
    assert api.Environment(cursor,SUPERUSER_ID,{})['purchase.order'].browse(fx['maker_po'].id).state=='draft'
# B7a: committed ownership/scope checks. No native Purchase ACL is granted here.
original_centers=fx['approver'].sph_center_ids.ids
prepared=rpc('approver',env['purchase.order'],'sph_prepare',
    [fx['supplier'].id,fx['product'].id],model_call=True)
assert 'error' not in prepared
owned_po=env['purchase.order'].browse(prepared['result'])
with env.registry.cursor() as cursor:
    checked=api.Environment(cursor,SUPERUSER_ID,{})['purchase.order'].browse(owned_po.id)
    assert checked.sph_center_id.id==original_centers[0] and checked.sph_maker_uid==fx['approver'].id
for kwargs,action in (({'sph_center_id':env.ref('sph_core.fixture_center_shared_b').id},'po.prepare'),
        ({'context':{'default_sph_center_id':env.ref('sph_core.fixture_center_shared_b').id}},'po.owner')):
    before=audit_count(env['purchase.order'],'approver',action,'deny')
    response=rpc('approver',env['purchase.order'],'sph_prepare',
        [fx['supplier'].id,fx['product'].id],kwargs,model_call=True)
    assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
    observed(env['purchase.order'],'approver',action,'deny',before)
fx['approver'].sph_center_ids=[(5,0,0)]
env.cr.commit();env.registry.clear_cache();env.registry.signal_changes()
for record,method,args,model_call,action in (
        (env['purchase.order'],'create',[{'partner_id':fx['supplier'].id}],True,'po.owner'),
        (env['purchase.order'],'sph_prepare',[fx['supplier'].id,fx['product'].id],True,'po.owner'),
        (owned_po,'read',[['name']],False,'po.scope'),
        (env['purchase.order'],'search',[[]],True,'po.scope'),
        (owned_po,'export_data',[['name']],False,'po.scope')):
    before=audit_count(env['purchase.order'],'approver',action,'deny')
    response=rpc('approver',record,method,args,model_call=model_call)
    assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
    observed(env['purchase.order'],'approver',action,'deny',before)
    rows[-1]['path']='no_membership_'+method
# Test-only exception: it grants scope, not a native ACL or business approval.
grant=env.ref('sph_core.group_sph_po_hub')
fx['approver'].group_ids=[(4,grant.id)]
env.cr.commit();env.registry.clear_cache();env.registry.signal_changes()
allow(owned_po,'write','incident.reference',[{'sph_incident_ref':'fixture:incident:explicit-hub'}])
rows[-1]['path']='explicit_hub'
fx['approver'].group_ids=[(3,grant.id)]
env.cr.commit();env.registry.clear_cache();env.registry.signal_changes()
before=audit_count(env['purchase.order'],'approver','incident.reference','deny')
response=rpc('approver',owned_po,'write',[{'sph_incident_ref':'fixture:incident:revoked'}])
assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
observed(env['purchase.order'],'approver','incident.reference','deny',before)
rows[-1]['path']='revoked_hub'
fx['approver'].sph_center_ids=[(6,0,original_centers)]
env.cr.commit();env.registry.clear_cache();env.registry.signal_changes()
assert not env['res.users'].search_count([('group_ids','in',grant.id)])
exec(compile(open('/opt/sph/scripts/po_scope_live.py').read(),'po_scope_live.py','exec'))
execute(env,fx,rpc,audit_count,observed,rows)
print('SPH_G3_RESULT '+json.dumps({'matrix':rows,'deny_rows_observed':sum(r['outcome']=='deny' for r in rows),
    'allow_rows_observed':sum(r['outcome']=='allow' for r in rows),'po_state':'purchase',
    'maker_checker_distinct':True,'settings':{'validation':'two_step','amount':0}}),flush=True)
