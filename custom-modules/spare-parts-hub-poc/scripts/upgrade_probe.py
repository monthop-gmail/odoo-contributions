"""Executed inside the isolated synthetic upgrade DB, never an API endpoint."""
import json
assert env.cr.dbname=='sph_poc'
assert phase in ('before','after')
metadata=env['ir.model.data'].search([('module','=','sph_core'),('name','=','scope_stock_picking')])
assert len(metadata)==1 and metadata.model=='ir.rule'
rule=env['ir.rule'].browse(metadata.res_id).exists()
assert len(rule)==1 and rule.model_id.model=='stock.picking' and rule['global']
all_rule_ids=env['ir.rule'].search([('model_id','=',rule.model_id.id)]).ids
expected='group_sph_po_hub' if phase=='before' else 'group_sph_picking_hub'
assert expected in rule.domain_force
if phase=='after':
    assert 'group_sph_po_hub' not in rule.domain_force
    for xmlid in ('sph_core.group_sph_po_hub','sph_core.group_sph_picking_hub'):
        group=env.ref(xmlid)
        assert not group.implied_ids
        assert not env['res.users'].search_count([('group_ids','in',group.id)])
    user=env.ref('sph_core.fixture_user_native_actor')
    original=user.group_ids.ids
    assert not user.sph_center_ids
    warehouse=env.ref('sph_core.fixture_wh_central')
    picking=env['stock.picking'].create({'picking_type_id':warehouse.int_type_id.id,
        'location_id':warehouse.lot_stock_id.id,'location_dest_id':warehouse.lot_stock_id.id})
    def visible():return env['stock.picking'].with_user(user).search_count([('id','=',picking.id)])
    assert visible()==0
    user.group_ids=[(4,env.ref('sph_core.group_sph_po_hub').id)]
    assert visible()==0
    user.group_ids=[(6,0,original),(4,env.ref('sph_core.group_sph_picking_hub').id)]
    assert visible()==1
    user.group_ids=[(6,0,original)]
    assert visible()==0
    # No commit: test-only records and grants roll back when the shell exits.
print('SPH_UPGRADE_PROBE '+json.dumps({'phase':phase,'rule_id':rule.id,
    'xmlid_count':len(metadata),'all_picking_rule_ids':sorted(all_rule_ids),
    'grant':expected,'grant_isolation_checked':phase=='after'}),flush=True)
