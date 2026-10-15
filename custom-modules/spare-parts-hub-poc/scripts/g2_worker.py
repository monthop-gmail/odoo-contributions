"""Standalone Odoo-shell race against the LIVE HTTP server, never a test case.
SYNTHETIC ASSUMPTION: untracked central last unit; round count is a test parameter.
"""
import concurrent.futures
import http.client
import json
import time
from odoo import api, Command, SUPERUSER_ID
from odoo.http import root
from odoo.addons.sph_core.models.reservation import LOCK_NAMESPACE

assert env.cr.dbname == 'sph_poc'
rounds = int(globals().get('round_count', 4))
assert 2 <= rounds <= 20
product = env.ref('sph_core.fixture_part_04').product_variant_id
warehouse = env.ref('sph_core.fixture_wh_central')
env.cr.execute('SHOW transaction_isolation')
isolation=env.cr.fetchone()[0]
roles = ('sph_hub_operator','sph_warehouse_picker')
sessions = []
for role in roles:
    user = env.ref('sph_core.fixture_user_'+role)
    if role == 'sph_warehouse_picker':
        user.group_ids = [Command.link(env.ref('stock.group_stock_manager').id)]
    session = root.session_store.new()
    session.update({'db':'sph_poc','uid':user.id,'login':user.login,
        'context':dict(user.with_user(user).context_get()),
        'session_token':user._compute_session_token(session.sid)})
    root.session_store.save(session); sessions.append(session.sid)
env.cr.commit()


def request(index, order, key, native=False):
    connection = http.client.HTTPConnection('127.0.0.1',8069,timeout=40)
    try:
        body=json.dumps({'jsonrpc':'2.0','id':1,'method':'call','params':{
            'model':'stock.picking' if native else 'sale.order',
            'method':'action_assign' if native else 'sph_reserve',
            'args':[[order]] if native else [[order],key],'kwargs':{}}})
        connection.request('POST','/web/dataset/call_kw',body,{
            'Content-Type':'application/json','Cookie':'session_id='+sessions[index]})
        response=connection.getresponse()
        return json.loads(response.read())
    finally: connection.close()


results = []
for number in range(rounds):
    # Reset through native unreserve/update APIs in a committed setup transaction.
    env.invalidate_all()
    old=env['sph.reservation'].search([('move_id.product_id','=',product.id),('state','=','active')])
    old.move_id._do_unreserve(); old.write({'state':'expired'})
    quants=env['stock.quant'].search([('product_id','=',product.id),('location_id','=',warehouse.lot_stock_id.id)])
    assert not any(quants.mapped('reserved_quantity'))
    delta=1-sum(quants.mapped('quantity'))
    if delta:
        env['stock.quant']._update_available_quantity(product,warehouse.lot_stock_id,delta)
    orders=[]
    for index in range(2):
        center=env.ref('sph_core.fixture_center_independent_'+('a' if index==0 else 'b'))
        order=env['sale.order'].create({'partner_id':center.partner_id.id,'sph_center_id':center.id,
            'warehouse_id':warehouse.id,'order_line':[Command.create({'product_id':product.id,
                'product_uom_qty':1,'price_unit':104})]})
        order.action_confirm()  # Synthetic setup uses existing superuser authority.
        orders.append(order.id)
    native = number == rounds-1
    native_picking = None
    if native:
        native_picking=env['stock.picking'].create({'picking_type_id':warehouse.out_type_id.id,
            'location_id':warehouse.lot_stock_id.id,'location_dest_id':env.ref('stock.stock_location_customers').id,
            'move_ids':[Command.create({'product_id':product.id,
                'product_uom_qty':1,'product_uom':product.uom_id.id,
                'location_id':warehouse.lot_stock_id.id,'location_dest_id':env.ref('stock.stock_location_customers').id})]})
        native_picking.action_confirm()
    env.cr.commit()
    # A third connection gates both clients until PostgreSQL observes both waiting.
    with env.registry.cursor() as gate:
        gate.execute('SELECT pg_advisory_xact_lock(%s,%s)',[LOCK_NAMESPACE,product.id])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            launch=(0,1) if number%2==0 else (1,0)
            futures={index:pool.submit(request,index,native_picking.id if native and index==1 else orders[index],
                f'FIXTURE-race-{number}-{index}',native and index==1) for index in launch}
            deadline=time.monotonic()+12
            waiters=0
            while time.monotonic()<deadline:
                # pg_locks is a live view, independent of MVCC snapshots.
                gate.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=%s AND objid=%s AND NOT granted",[LOCK_NAMESPACE,product.id])
                waiters=gate.fetchone()[0]
                if waiters>=2: break
                time.sleep(0.02)
            gate.commit()  # Standalone gate only. Never a business method/TransactionCase commit.
            responses={index:future.result() for index,future in futures.items()}
    if not native:
        winners=[index for index,value in responses.items() if 'result' in value]
        losers=[index for index,value in responses.items() if 'error' in value]
        assert len(winners)==1 and len(losers)==1
        message=responses[losers[0]]['error'].get('data',{}).get('message','')
        assert message=='Unavailable' and all(str(value) not in message for value in (0,1,2))
    # Fresh observer connection sees committed native moves/quants, not client caches.
    with env.registry.cursor() as observer:
        observed=api.Environment(observer,SUPERUSER_ID,{})
        q=observed['stock.quant'].search([('product_id','=',product.id),('location_id','=',warehouse.lot_stock_id.id)])
        ledger=observed['sph.reservation'].search([('order_id','in',orders)])
        assert sum(q.mapped('reserved_quantity'))==1
        assert sum(q.mapped('quantity'))==1 and all(x.quantity>=0 for x in q)
        if native:
            assigned=observed['stock.picking'].browse(native_picking.id).move_ids.quantity
            assert len(ledger)+assigned == 1
            winners=[0] if ledger else [1]
            losers=[1-winners[0]]
            if not ledger:
                assert responses[0].get('error',{}).get('data',{}).get('message')=='Unavailable'
        else:
            assert len(ledger)==1 and ledger.order_id.id==orders[winners[0]]
        if ledger:
            assert ledger.move_id.quantity==1
        loser=observed['sale.order'].browse(orders[losers[0]])
        assert loser.state=='sale' and loser.picking_ids
        assert not any(loser.picking_ids.move_ids.mapped('quantity'))
        assert not observed['sph.reservation'].search_count([('order_id','=',loser.id)])
        before=ledger.ids
    if winners[0]==0 or not native:
        replay=request(winners[0],orders[winners[0]],f'FIXTURE-race-{number}-{winners[0]}')
        assert replay.get('result',{}).get('reservation_ids')==before
    if native:
        # Release the native allocation before the next independent evidence stage.
        env.invalidate_all();native_picking.move_ids._do_unreserve();env.cr.commit()
    results.append({'round':number,'mode':'sph_vs_native_assign' if native else 'two_http_reservations','launch_order':list(launch),'winners':1,'losers':1,
        'double_allocations':0,'reserved_total':1,'negative_stock':False,'observed_lock_waiters':waiters,
        'loser_message':'native no allocation' if native and winners[0]==0 else 'Unavailable',
        'replay_duplicate':False})
    print('SPH_G2_LOCK_WITNESS '+json.dumps({'round':number,'waiters':waiters}),flush=True)
# Exercise the installed cron action against committed native reservations.
# Scheduler threads stay disabled for deterministic CI; this invokes its real entrypoint.
from datetime import timedelta
from odoo import fields
env.invalidate_all()
active=env['sph.reservation'].search([('move_id.product_id','=',product.id),('state','=','active')])
active.write({'expires_at':fields.Datetime.now()-timedelta(seconds=1)})
env.cr.commit()
cron=env.ref('sph_core.ir_cron_expire_reservations')
assert cron.active
cron.method_direct_trigger()
env.invalidate_all()
center=env.ref('sph_core.fixture_center_independent_a')
expiry_order=env['sale.order'].create({'partner_id':center.partner_id.id,'sph_center_id':center.id,
    'warehouse_id':warehouse.id,'order_line':[Command.create({'product_id':product.id,
        'product_uom_qty':1,'price_unit':104})]})
expiry_order.action_confirm()
env.cr.commit()
assert 'result' in request(0,expiry_order.id,'FIXTURE cron expiry')
env.invalidate_all()
expiry=env['sph.reservation'].search([('order_id','=',expiry_order.id)])
assert len(expiry)==1 and expiry.move_id.quantity==1
assert expiry.expires_at>fields.Datetime.now()+timedelta(hours=47)
expiry.write({'expires_at':fields.Datetime.now()-timedelta(seconds=1)})
expiry_id=expiry.id
env.cr.commit()
cron.method_direct_trigger()
with env.registry.cursor() as observer:
    observed=api.Environment(observer,SUPERUSER_ID,{})
    expired=observed['sph.reservation'].browse(expiry_id)
    quants=observed['stock.quant'].search([('product_id','=',product.id),('location_id','=',warehouse.lot_stock_id.id)])
    assert expired.state=='expired' and expired.move_id.quantity==0
    assert sum(quants.mapped('reserved_quantity'))==0
expiry_evidence={'cron_active':True,'entrypoint':'ir.cron.method_direct_trigger',
    'expired_state':'expired','native_move_quantity':0,'native_quant_reserved':0}
assert any(row['observed_lock_waiters']>=2 for row in results), 'UNRUNNABLE: no witnessed contention'
print('SPH_G2_RESULT '+json.dumps({'round_count':rounds,'double_allocations':0,
    'expiry':expiry_evidence,'isolation':isolation,'lock_wait_rounds':sum(row['observed_lock_waiters']>=2 for row in results),'rounds':results}),flush=True)
