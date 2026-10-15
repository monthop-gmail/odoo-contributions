"""Committed I9 context probes: synthetic company IDs, no native ACL grants."""
from odoo import api, SUPERUSER_ID


def execute_company_scope(env,fx,rpc,audit_count,observed,rows):
    assert env.cr.dbname=='sph_poc'
    company=env.ref('sph_core.fixture_company')
    other=env['res.company'].create({'name':'FIXTURE I9 context probe company',
        'po_double_validation':'two_step','po_double_validation_amount':0})
    po=env['purchase.order'].browse(env['purchase.order'].with_user(fx['bot']).sph_prepare(
        fx['supplier'].id,fx['product'].id))
    env.cr.commit();env.registry.clear_cache();env.registry.signal_changes()
    legitimate={'allowed_company_ids':company.ids,'force_company':company.id}
    response=rpc('approver',po,'sph_review',kwargs={'context':legitimate})
    assert 'error' not in response
    observed(po,'approver','po.review','allow');rows[-1]['path']='b7c_legitimate_review'
    def snapshot():
        with env.registry.cursor() as cr:
            record=api.Environment(cr,SUPERUSER_ID,{})['purchase.order'].browse(po.id)
            assert record.sph_maker_uid!=fx['approver'].id
            assert record.sph_reviewer_uid==fx['approver'].id
            assert record.sph_review_digest==record._sph_digest_value()
            return (record.state,record.sph_review_digest,record.sph_reviewer_uid,record.picking_ids.ids)
    before_state=snapshot()
    for label,context in (
            ('foreign_allowed',{'allowed_company_ids':other.ids}),
            ('appended_foreign',{'allowed_company_ids':[company.id,other.id]}),
            ('force_foreign',{'allowed_company_ids':company.ids,'force_company':other.id}),
            ('force_only',{'force_company':other.id})):
        for method,action in (('sph_review','po.review'),('button_confirm','po.approve')):
            before=audit_count(env['purchase.order'],'approver',action,'deny')
            response=rpc('approver',po,method,kwargs={'context':context})
            data=response.get('error',{}).get('data',{})
            assert data.get('message')=='Unavailable' and data.get('name')=='odoo.exceptions.AccessError'
            observed(env['purchase.order'],'approver',action,'deny',before)
            rows[-1]['path']='b7c_'+label+'_'+method
            assert snapshot()==before_state
    response=rpc('approver',po,'button_confirm',kwargs={'context':legitimate})
    assert 'error' not in response
    observed(po,'approver','po.confirm','allow');rows[-1]['path']='b7c_legitimate_confirm'
    with env.registry.cursor() as cr:
        record=api.Environment(cr,SUPERUSER_ID,{})['purchase.order'].browse(po.id)
        assert record.state=='purchase' and record.picking_ids
        assert record.picking_ids.sph_center_id==record.sph_center_id
