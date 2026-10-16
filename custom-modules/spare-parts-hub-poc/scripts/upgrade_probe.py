"""Empty-business-DB addon upgrade probe; NOT a business-data migration."""
import json
import re
assert env.cr.dbname=='sph_poc'
assert phase in ('before','after')
metadata=env['ir.model.data'].search([('module','=','sph_core'),('name','=','scope_stock_picking')])
assert len(metadata)==1 and metadata.model=='ir.rule'
rule=env['ir.rule'].browse(metadata.res_id).exists()
assert len(rule)==1 and rule.model_id.model=='stock.picking' and rule['global']
all_rule_ids=env['ir.rule'].search([('model_id','=',rule.model_id.id)]).ids
business_counts={key:env[model].search_count([]) for key,model in (
    ('sales','sale.order'),('purchases','purchase.order'),('pickings','stock.picking'),('reservations','sph.reservation'))}
assert not any(business_counts.values())
grant_tokens=re.findall(r'sph_core\.(group_sph_\w+)',rule.domain_force)
expected='group_sph_po_hub' if phase=='before' else 'group_sph_picking_hub'
assert grant_tokens==[expected]
groups={};visibility={}
if phase=='after':
    for key in ('group_sph_po_hub','group_sph_picking_hub'):
        group=env.ref('sph_core.'+key)
        groups[key]={'implied_count':len(group.implied_ids),
            'assignee_count':env['res.users'].search_count([('group_ids','in',group.id)])}
        assert groups[key]['implied_count']==groups[key]['assignee_count']==0
    user=env.ref('sph_core.fixture_user_native_actor')
    original=user.group_ids.ids
    assert not user.sph_center_ids
    warehouse=env.ref('sph_core.fixture_wh_central')
    picking=env['stock.picking'].create({'picking_type_id':warehouse.int_type_id.id,
        'location_id':warehouse.lot_stock_id.id,'location_dest_id':warehouse.lot_stock_id.id})
    def visible():return env['stock.picking'].with_user(user).search_count([('id','=',picking.id)])
    visibility['none']=visible()
    user.group_ids=[(4,env.ref('sph_core.group_sph_po_hub').id)]
    visibility['po_hub']=visible()
    user.group_ids=[(6,0,original),(4,env.ref('sph_core.group_sph_picking_hub').id)]
    visibility['picking_hub']=visible()
    user.group_ids=[(6,0,original)]
    visibility['revoked']=visible()
    assert visibility=={'none':0,'po_hub':0,'picking_hub':1,'revoked':0}
    # No commit: the probe-only picking and grant writes roll back at shell exit.
print('SPH_UPGRADE_PROBE '+json.dumps({'phase':phase,'rule_id':rule.id,
    'xmlid_count':len(metadata),'all_picking_rule_ids':sorted(all_rule_ids),
    'rule_model':rule.model_id.model,'is_global':rule['global'],'grant_tokens':grant_tokens,
    'group_observations':groups,'visibility_counts':visibility,'business_counts':business_counts}),flush=True)
