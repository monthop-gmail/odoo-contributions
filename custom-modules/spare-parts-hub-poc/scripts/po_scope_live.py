"""B7b committed capability matrix, called inside the out-of-process G3 worker."""
import http.client
from odoo import api, SUPERUSER_ID


def execute(env,fx,rpc,audit_count,observed,rows,sessions):
    centers=[env.ref('sph_core.fixture_center_shared_'+key) for key in ('a','b')]
    original={role:fx[role].sph_center_ids.ids for role in ('bot','approver')}
    orders=[]
    for center in centers:
        fx['bot'].sph_center_ids=[(6,0,center.ids)]
        orders.append(env['purchase.order'].browse(env['purchase.order'].with_user(fx['bot']).sph_prepare(fx['supplier'].id,fx['product'].id)))
    def sync():
        env.cr.commit();env.registry.clear_cache();env.registry.signal_changes()
    def snapshot():
        with env.registry.cursor() as cr:
            obs=api.Environment(cr,SUPERUSER_ID,{})
            return [(p.state,p.sph_review_digest,p.sph_reviewer_uid,p.sph_incident_ref,p.picking_ids.ids,
                p.order_line.mapped('product_qty')) for p in obs['purchase.order'].browse([p.id for p in orders])]
    paths=[('sph_draft',[2],{},'po.draft'),('sph_review',[],{},'po.review'),
        ('button_confirm',[],{},'po.approve'),('button_approve',[],{'force':True},'po.approve'),
        ('write',[{'state':'purchase'}],{},'po.write'),('write',[{'date_approve':False}],{},'po.write'),
        ('write',[{'sph_reviewer_uid':fx['approver'].id}],{},'po.write'),
        ('action_rfq_send',[],{},'po.send'),
        ('write',[{'sph_incident_ref':'fixture:matrix'}],{},'incident.reference'),
        ('write',[{'locked':True}],{},'purchase.order.locked')]
    def denied(record,label,kwargs=None,role='approver'):
        before_state=snapshot()
        for method,args,options,action in paths:
            before=audit_count(env['purchase.order'],role,action,'deny')
            response=rpc(role,record,method,args,dict(options,**(kwargs or {})))
            data=response.get('error',{}).get('data',{})
            assert data.get('message')=='Unavailable', (label,method)
            assert data.get('name')=='odoo.exceptions.AccessError'
            observed(env['purchase.order'],role,action,'deny',before)
            rows[-1]['path']='b7b_'+label+'_'+method+('_'+next(iter(args[0])) if args and isinstance(args[0],dict) else '')
            assert snapshot()==before_state
    for index,center in enumerate(centers):
        fx['approver'].sph_center_ids=[(6,0,center.ids)];sync()
        own,foreign=orders[index],orders[1-index]
        response=rpc('approver',own,'sph_review')
        assert 'error' not in response
        observed(own,'approver','po.review','allow');rows[-1]['path']='b7b_same_center_'+str(index)
        response=rpc('approver',own,'action_rfq_send');assert 'error' not in response
        # Returning a checked RFQ wizard action sends no mail in this harness.
        denied(foreign,'cross_'+str(index))
        token=foreign._portal_ensure_token()
        attachment=env['ir.attachment'].create({'name':'FIXTURE PO binary',
            'raw':b'FIXTURE restricted content','res_model':'purchase.order','res_id':foreign.id,
            'access_token':'fixture-po-binary-'+str(index)})
        message=env['mail.message'].create({'model':'purchase.order','res_id':foreign.id,
            'body':'FIXTURE scoped thread','message_type':'comment'})
        sync()
        for linked,field in ((message,'body'),(attachment,'raw'),(foreign.order_line,'id')):
            action='po.line.read' if linked._name=='purchase.order.line' else 'po.link.read'
            before=audit_count(env['purchase.order'],'approver',action,'deny')
            response=rpc('approver',linked,'read',[[field]])
            assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
            observed(env['purchase.order'],'approver',action,'deny',before)
            rows[-1]['path']='b7b_read_'+str(index)+'_'+linked._name
        for path,action in (('/my/purchase/'+str(foreign.id)+'?access_token='+token,'po.portal'),
                ('/my/purchase/2147483647?access_token='+token,'po.portal'),
                ('/web/content/'+str(attachment.id)+'?access_token=fixture-po-binary-'+str(index),'po.binary')):
            before=audit_count(env['purchase.order'],'approver',action,'deny')
            connection=http.client.HTTPConnection('127.0.0.1',8069,timeout=20)
            try:
                connection.request('GET',path,headers={'Cookie':'session_id='+sessions['approver']})
                response=connection.getresponse();payload=response.read()
                assert response.status in (303,403,404)
                assert b'FIXTURE restricted content' not in payload
            finally:connection.close()
            observed(env['purchase.order'],'approver',action,'deny',before)
            rows[-1]['path']='b7b_token_'+str(index)+'_'+action

    fx['approver'].sph_center_ids=[(5,0,0)];sync()
    denied(orders[0],'empty')
    fx['approver'].sph_center_ids=[(6,0,centers[0].ids)];sync()
    denied(env['purchase.order'].browse(2147483647),'missing')
    denied(orders[0]|orders[1],'mixed')
    denied(orders[1],'spoof',{'context':{'sph_center_id':centers[1].id}})
    grant=env.ref('sph_core.group_sph_po_hub')
    fx['approver'].group_ids=[(4,grant.id)];sync()
    response=rpc('approver',orders[1],'sph_review');assert 'error' not in response
    observed(orders[1],'approver','po.review','allow');rows[-1]['path']='b7b_hub_grant'
    fx['approver'].group_ids=[(3,grant.id)];sync()
    denied(orders[1],'hub_revoked')
    # A bot remains nonhuman despite every purchasing union and explicit hub scope.
    union=[env.ref(xmlid).id for xmlid in ('sph_core.group_sph_po_hub',
        'sph_core.group_sph_purchasing_approver','purchase.group_purchase_manager')]
    original_groups=fx['bot'].group_ids.ids
    fx['bot'].group_ids=[(4,g) for g in union];sync()
    for method,action in (('sph_review','po.review'),('button_confirm','po.approve'),('action_rfq_send','po.send')):
        before=audit_count(orders[0],'bot',action,'deny')
        response=rpc('bot',orders[0],method)
        assert response.get('error',{}).get('data',{}).get('message')=='Unavailable'
        observed(orders[0],'bot',action,'deny',before);rows[-1]['path']='b7b_bot_hub_'+method
    before=audit_count(orders[0],'bot','po.approve','deny')
    response=rpc('bot',orders[0],'button_approve',[],{'force':True});assert 'error' not in response
    observed(orders[0],'bot','po.approve','deny',before);rows[-1]['path']='b7b_bot_hub_silent_approve'
    assert snapshot()[0][0]=='draft'
    fx['bot'].group_ids=[(6,0,original_groups)]
    for role in original:fx[role].sph_center_ids=[(6,0,original[role])]
    sync()
    assert not env['res.users'].search_count([('group_ids','in',grant.id)])
