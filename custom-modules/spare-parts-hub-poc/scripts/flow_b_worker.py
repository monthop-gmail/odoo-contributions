"""SYNTHETIC shortage -> bot draft -> human review/confirmation over live HTTP."""
import http.client
import sys
import json
from odoo import api, Command, SUPERUSER_ID
from odoo.http import root

sessions={}
try:
    assert env.cr.dbname=='sph_poc'
    assert env.company.po_double_validation=='two_step' and env.company.po_double_validation_amount==0
    seed=env['sph.center']._seed_flow_b(profile='disposable-test-harness')
    center=env['sph.center'].browse(seed['center_id'])
    order=env['sale.order'].create({'partner_id':center.partner_id.id,'sph_center_id':center.id,
        'warehouse_id':seed['warehouse_id'],'order_line':[Command.create({'product_id':seed['product_id'],
            'product_uom_qty':1,'price_unit':101})]})
    order.action_confirm()  # Synthetic authorized setup, not bot Sales authority.
    for role in ('reservist','bot','approver'):
        user=env['res.users'].browse(seed[role+'_uid'])
        session=root.session_store.new()
        session.update({'db':'sph_poc','uid':user.id,'login':user.login,
            'context':dict(user.with_user(user).context_get()),'session_token':user._compute_session_token(session.sid)})
        root.session_store.save(session);sessions[role]=session.sid
    env.cr.commit();env.registry.clear_cache();env.registry.signal_changes()

    def rpc(role,model,method,args):
        connection=http.client.HTTPConnection('127.0.0.1',8069,timeout=30)
        try:
            body=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':{
                'model':model,'method':method,'args':args,'kwargs':{}}})
            connection.request('POST','/web/dataset/call_kw',body,{
                'Content-Type':'application/json','Cookie':'session_id='+sessions[role]})
            return json.loads(connection.getresponse().read())
        finally: connection.close()

    shortage=rpc('reservist','sale.order','sph_reserve',[[order.id],'FIXTURE FLOW B shortage'])
    assert shortage.get('error',{}).get('data',{}).get('message')=='Unavailable'
    assert shortage['error']['data']['name']=='odoo.exceptions.UserError'
    with env.registry.cursor() as cursor:
        observer=api.Environment(cursor,SUPERUSER_ID,{})
        quants=observer['stock.quant'].search([('product_id','=',seed['product_id']),('location_id','=',seed['location_id'])])
        assert sum(q.quantity-q.reserved_quantity for q in quants)==0
        assert not observer['sph.reservation'].search_count([('order_id','=',order.id)])
    drafted=rpc('bot','purchase.order','sph_prepare',[seed['supplier_id'],seed['product_id'],1])
    assert 'error' not in drafted
    po_id=drafted['result']
    with env.registry.cursor() as cursor:
        po=api.Environment(cursor,SUPERUSER_ID,{})['purchase.order'].browse(po_id)
        assert po.state=='draft' and po.sph_maker_uid==seed['bot_uid'] and not po.picking_ids
    denied=rpc('bot','purchase.order','button_confirm',[[po_id]])
    assert denied.get('error',{}).get('data',{}).get('message')=='Unavailable'
    with env.registry.cursor() as cursor:
        observer=api.Environment(cursor,SUPERUSER_ID,{})
        po=observer['purchase.order'].browse(po_id)
        assert po.state=='draft' and not po.picking_ids
        deny_count=observer['sph.authority.audit'].search_count([('res_model','=','purchase.order'),
            ('res_id','=',po_id),('actor_uid','=',seed['bot_uid']),('action','=','po.approve'),('outcome','=','deny')])
        assert deny_count>=1
    for method in ('sph_review','button_confirm'):
        response=rpc('approver','purchase.order',method,[[po_id]])
        assert 'error' not in response and response.get('jsonrpc')=='2.0'
    with env.registry.cursor() as cursor:
        observer=api.Environment(cursor,SUPERUSER_ID,{})
        po=observer['purchase.order'].browse(po_id)
        assert po.state=='purchase' and po.picking_ids
        assert po.sph_maker_uid==seed['bot_uid']!=po.sph_reviewer_uid==seed['approver_uid']
        assert observer['sph.authority.audit'].search_count([('res_model','=','purchase.order'),
            ('res_id','=',po_id),('actor_uid','=',seed['approver_uid']),('action','=','po.confirm'),('outcome','=','allow')])
        result={'scope':'SYNTHETIC ASSUMPTION: Flow B disposable harness only','seed':seed,
            'shortage_so_id':order.id,'initial_free':0,'shortage_message':'Unavailable','po_id':po.id,
            'bot_drafted_state':'draft','bot_confirm':'DENIED','durable_bot_deny_audit':True,
            'state_after_bot_denial':'draft','final_po_state':po.state,'receipt_ids':po.picking_ids.ids,
            'maker_uid':po.sph_maker_uid,'checker_uid':po.sph_reviewer_uid,'maker_checker_distinct':True,
            'human_confirm_allow_audit':True}
finally:
    scenario_failed=sys.exc_info()[0] is not None
    cleanup_failed=False
    for sid in sessions.values():
        try:
            root.session_store.delete(root.session_store.get(sid))
        except Exception:
            cleanup_failed=True
            print('SPH_SESSION_CLEANUP_FAILURE: Flow B',file=sys.stderr,flush=True)
    if cleanup_failed and not scenario_failed:
        raise RuntimeError('Flow B session cleanup failed')
result['sessions_cleaned']=True
print('SPH_FLOW_B_RESULT '+json.dumps(result),flush=True)
