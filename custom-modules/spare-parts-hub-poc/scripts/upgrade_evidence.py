"""Derive upgrade assertions from measured probe fields, never canned PASS flags."""

def upgrade_checks(before,after):
    groups=after['group_observations']
    return {
        'one_xmlid':before['xmlid_count']==after['xmlid_count']==1,
        'same_rule_id':before['rule_id']==after['rule_id'],
        'no_duplicate_picking_rules':before['all_picking_rule_ids']==after['all_picking_rule_ids'],
        'picking_not_po_grant':before['grant_tokens']==['group_sph_po_hub'] and after['grant_tokens']==['group_sph_picking_hub'],
        'no_seeded_grants':set(groups)=={'group_sph_po_hub','group_sph_picking_hub'} and
            all(row['implied_count']==row['assignee_count']==0 for row in groups.values()),
        'post_upgrade_grant_isolation':after['visibility_counts']=={'none':0,'po_hub':0,'picking_hub':1,'revoked':0},
        'global_picking_rule':before['is_global'] is True and after['is_global'] is True,
        'stock_picking_model':before['rule_model']==after['rule_model']=='stock.picking',
        'clean_business_transactions':all(probe['business_counts']=={'sales':0,'purchases':0,'pickings':0,'reservations':0}
            for probe in (before,after)),
    }
