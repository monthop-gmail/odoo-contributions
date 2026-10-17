"""Retained SYNTHETIC transactions only; never a production migration."""
import json
from odoo import Command
assert env.cr.dbname=='sph_poc' and phase in ('before','after')
ref=lambda key:env.ref('sph_core.'+key)
centers=[ref('fixture_center_independent_'+key) for key in ('a','b')]
bot=ref('fixture_user_sph_bot');human=ref('fixture_user_sph_purchasing_approver')
operator=ref('fixture_user_sph_hub_operator');native=ref('fixture_user_native_actor')
warehouse=ref('fixture_wh_central');product=ref('fixture_part_05').product_variant_id
supplier=ref('fixture_supplier_1')

def identify(key,record):
    env['ir.model.data'].create({'module':'sph_core','name':'retained_'+key,
        'model':record._name,'res_id':record.id,'noupdate':True})

if phase=='before':
    assert not env.ref('sph_core.retained_po_draft',raise_if_not_found=False)
    operator.sph_center_ids=[Command.set(centers[0].ids)]
    for key in ('po_draft','po_confirmed'):
        po=env['purchase.order'].browse(env['purchase.order'].with_user(bot).sph_prepare(supplier.id,product.id))
        identify(key,po)
        if key=='po_confirmed':
            po.with_user(human).sph_review();po.with_user(human).button_confirm()
    sale=env['sale.order'].create({'partner_id':centers[0].partner_id.id,'sph_center_id':centers[0].id,
        'warehouse_id':warehouse.id,'order_line':[Command.create({'product_id':product.id,'product_uom_qty':1,'price_unit':105})]})
    sale.action_confirm();identify('sale',sale)
    result=sale.with_user(operator).sph_reserve('FIXTURE-retained-upgrade')
    reservation=env['sph.reservation'].browse(result['reservation_ids']).ensure_one();identify('reservation',reservation)
    picking=env['stock.picking'].create({'sph_center_id':centers[1].id,'picking_type_id':warehouse.int_type_id.id,
        'location_id':warehouse.lot_stock_id.id,'location_dest_id':warehouse.lot_stock_id.id})
    identify('picking_b',picking)
    # Test setup boundary only: persist old-revision fixtures before -u. No business method commits added.
    env.cr.commit()

orders=[ref('retained_'+key) for key in ('po_draft','po_confirmed')]
sale=ref('retained_sale');reservation=ref('retained_reservation');foreign=ref('retained_picking_b')
assert orders[0].state=='draft' and orders[1].state=='purchase'
assert reservation.state=='active' and reservation.reserved_qty==1
pickings=orders[1].picking_ids|sale.picking_ids|foreign
snapshot={
    'orders':[{'id':po.id,'state':po.state,'center':po.sph_center_id.id,'company':po.company_id.id,
        'maker':po.sph_maker_uid,'reviewer':po.sph_reviewer_uid,'digest':po.sph_review_digest,
        'picking_ids':sorted(po.picking_ids.ids),'lines':[(line.id,line.product_id.id,line.product_qty,line.price_unit) for line in po.order_line]} for po in orders],
    'sale':{'id':sale.id,'state':sale.state,'center':sale.sph_center_id.id,'picking_ids':sorted(sale.picking_ids.ids)},
    'reservation':{'id':reservation.id,'order':reservation.order_id.id,'move':reservation.move_id.id,
        'state':reservation.state,'requested':reservation.requested_qty,'reserved':reservation.reserved_qty,
        'backorder':reservation.backorder_qty,'expires_at':str(reservation.expires_at),
        'native_move_quantity':reservation.move_id.quantity},
    'pickings':[(p.id,p.state,p.sph_center_id.id,p.company_id.id,sorted(p.move_ids.ids)) for p in pickings.sorted('id')],
    'memberships':{role:ref('fixture_user_'+role).sph_center_ids.ids for role in
        ('sph_bot','sph_purchasing_approver','sph_hub_operator','sph_warehouse_picker','native_actor')},
    'xmlids':[(row.name,row.model,row.res_id) for row in env['ir.model.data'].search([
        ('module','=','sph_core'),('name','=like','retained_%')],order='name')],
}
assert len(snapshot['xmlids'])==5
metadata=env['ir.model.data'].search([('module','=','sph_core'),('name','=','scope_stock_picking')])
rule=env['ir.rule'].browse(metadata.res_id)
groups={key:{'implied':len(ref(key).implied_ids),'assignees':env['res.users'].search_count([('group_ids','in',ref(key).id)])}
    for key in ('group_sph_po_hub','group_sph_picking_hub')}
assert all(row=={'implied':0,'assignees':0} for row in groups.values())
visibility={}
for label,members in (('none',[]),('center_a',centers[0].ids),('center_b',centers[1].ids),('revoked',[])):
    native.sph_center_ids=[Command.set(members)]
    visibility[label]=env['stock.picking'].with_user(native).search_count([('id','in',pickings.ids)])
assert visibility=={'none':0,'center_a':1,'center_b':1,'revoked':0}
# Visibility probe membership writes roll back at shell exit, not part of retained fixture state.
print('SPH_UPGRADE_PROBE '+json.dumps({'phase':phase,'snapshot':snapshot,'xmlid_count':len(metadata),
    'rule_id':rule.id,'all_picking_rule_ids':sorted(env['ir.rule'].search([('model_id','=',rule.model_id.id)]).ids),
    'rule_domain':rule.domain_force,'is_global':rule['global'],'groups':groups,'visibility_counts':visibility}),flush=True)
