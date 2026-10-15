"""Synthetic committed HTTP probe of existing price authority, before/after fix."""
import http.client
import json
from odoo import api, Command, SUPERUSER_ID
from odoo.http import root

assert env.cr.dbname=='sph_poc'
bot=env.ref('sph_core.fixture_user_sph_bot')
center=env.ref('sph_core.fixture_center_shared_a')
assert center in bot.sph_center_ids
# Existing G1 union fixture, not new grants: scope must still enforce authority.
assert bot.has_group('sales_team.group_sale_manager')
product=env.ref('sph_core.fixture_part_05').product_variant_id
current=env['product.pricelist'].search([('sph_center_id','=',center.id)],limit=1)
alternate=env['product.pricelist'].create({'name':'FIXTURE alternate own-center probe price',
    'sph_center_id':center.id,'currency_id':env.company.currency_id.id})
order=env['sale.order'].create({'partner_id':center.partner_id.id,'sph_center_id':center.id,
    'pricelist_id':current.id,'order_line':[Command.create({'product_id':product.id,
        'product_uom_qty':1,'price_unit':105,'discount':0})]})
line=order.order_line
session=root.session_store.new()
session.update({'db':'sph_poc','uid':bot.id,'login':bot.login,
    'context':dict(bot.with_user(bot).context_get()),'session_token':bot._compute_session_token(session.sid)})
root.session_store.save(session)
env.cr.commit()
rows=[]
for record,field,value in ((line,'discount',7),(order,'pricelist_id',alternate.id)):
    connection=http.client.HTTPConnection('127.0.0.1',8069,timeout=20)
    try:
        body=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':{
            'model':record._name,'method':'write','args':[record.ids,{field:value}],'kwargs':{}}})
        connection.request('POST','/web/dataset/call_kw',body,{
            'Content-Type':'application/json','Cookie':'session_id='+session.sid})
        response=json.loads(connection.getresponse().read())
    finally: connection.close()
    with env.registry.cursor() as cursor:
        observer=api.Environment(cursor,SUPERUSER_ID,{})
        stored=observer[record._name].browse(record.id)[field]
        stored=stored.id if hasattr(stored,'id') else stored
        changed=stored==value
    outcome='SUCCEEDED' if changed and 'error' not in response else 'DENIED'
    rows.append({'model':record._name,'field':field,'outcome':outcome,'committed_target_value':changed,
        'error_type':response.get('error',{}).get('data',{}).get('name')})
if globals().get('require_denied'):
    assert all(row['outcome']=='DENIED' and not row['committed_target_value'] for row in rows)
print('SPH_PRICE_PROBE '+json.dumps({'phase':'guarded' if globals().get('require_denied') else 'unpatched',
    'principal':'FIXTURE sph_bot','existing_sales_manager_union':True,'scope':'own center; own-center alternate pricelist',
    'results':rows}),flush=True)
