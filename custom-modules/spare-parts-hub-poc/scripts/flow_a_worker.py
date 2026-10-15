"""SYNTHETIC Flow A: committed setup, two HTTP reservists, fresh observer."""
import concurrent.futures
import http.client
import sys
import json
import time
from odoo import api, Command, SUPERUSER_ID
from odoo.http import root
from odoo.addons.sph_core.models.reservation import LOCK_NAMESPACE

sessions=[]
try:
    assert env.cr.dbname=='sph_poc'
    existing_sales_before=env['sale.order'].search_count([])
    seed=env['sph.center']._seed_flow_a(profile='disposable-test-harness')
    product=env['product.product'].browse(seed['product_id'])
    orders=[];sessions=[]
    for center_id,uid in zip(seed['centers'],seed['reservists']):
        center=env['sph.center'].browse(center_id)
        order=env['sale.order'].create({'partner_id':center.partner_id.id,'sph_center_id':center.id,
            'warehouse_id':seed['warehouse_id'],'order_line':[Command.create({
                'product_id':product.id,'product_uom_qty':1,'price_unit':101})]})
        # Human-authorized synthetic setup confirms Sales first. Reservation cannot confirm SOs.
        order.action_confirm();orders.append(order.id)
        actor=env['res.users'].browse(uid)
        assert not actor.has_group('stock.group_stock_manager')
        session=root.session_store.new()
        session.update({'db':'sph_poc','uid':uid,'login':actor.login,
            'context':dict(actor.with_user(actor).context_get()),'session_token':actor._compute_session_token(session.sid)})
        root.session_store.save(session);sessions.append(session.sid)
    env.cr.commit();env.registry.clear_cache();env.registry.signal_changes()


    def reserve(index):
        connection=http.client.HTTPConnection('127.0.0.1',8069,timeout=40)
        try:
            body=json.dumps({'jsonrpc':'2.0','id':index,'method':'call','params':{
                'model':'sale.order','method':'sph_reserve','args':[[orders[index]],'FIXTURE FLOW A '+str(index)],'kwargs':{}}})
            connection.request('POST','/web/dataset/call_kw',body,{
                'Content-Type':'application/json','Cookie':'session_id='+sessions[index]})
            return json.loads(connection.getresponse().read())
        finally: connection.close()


    with env.registry.cursor() as gate:
        gate.execute('SELECT pg_advisory_xact_lock(%s,%s)',[LOCK_NAMESPACE,product.id])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(reserve,index) for index in range(2)]
            deadline=time.monotonic()+12
            waiters=0
            while time.monotonic()<deadline:
                gate.execute("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND classid=%s AND objid=%s AND NOT granted",[LOCK_NAMESPACE,product.id])
                waiters=gate.fetchone()[0]
                if waiters>=2: break
                time.sleep(0.02)
            gate.commit()
            responses=[future.result() for future in futures]
    assert waiters>=2,'Flow A requires two concurrent waiting reservists'
    winners=[i for i,response in enumerate(responses) if 'result' in response]
    losers=[i for i,response in enumerate(responses) if 'error' in response]
    assert len(winners)==len(losers)==1
    assert responses[losers[0]]['error']['data']['message']=='Unavailable'
    with env.registry.cursor() as cursor:
        observer=api.Environment(cursor,SUPERUSER_ID,{})
        ledger=observer['sph.reservation'].search([('order_id','in',orders)])
        quants=observer['stock.quant'].search([('product_id','=',product.id),('location_id','=',seed['location_id'])])
        assert len(ledger)==1 and ledger.state=='active'
        assert ledger.order_id.id==orders[winners[0]] and ledger.order_id.state=='sale'
        assert ledger.order_id.sph_center_id.id==seed['centers'][winners[0]]
        assert ledger.move_id.quantity==ledger.reserved_qty==1
        assert responses[winners[0]]['result']['reservation_ids']==ledger.ids
        assert sum(quants.mapped('reserved_quantity'))==sum(quants.mapped('quantity'))==1
        assert all(q.quantity>=0 for q in quants)
        loser=observer['sale.order'].browse(orders[losers[0]])
        assert not any(loser.picking_ids.move_ids.mapped('quantity'))
        result={'scope':'SYNTHETIC ASSUMPTION: Flow A disposable harness only',
            'seed':seed,'orders':orders,'winner_center_id':ledger.order_id.sph_center_id.id,
            'winning_reservation':{'id':ledger.id,'so_id':ledger.order_id.id,'move_id':ledger.move_id.id,'state':ledger.state},
            'winners':1,'losers':1,'loser_message':'Unavailable','initial_free':1,
            'reserved_total':1,'double_allocations':0,'negative_stock':False,'observed_lock_waiters':waiters,
            'sales_confirmation':'authorized synthetic setup before reservation'}
        measured_orders=observer['sale.order'].browse(orders)
        result['measurements']={'existing_sales_before':existing_sales_before,
            'orders':[{'so_id':so.id,'state':so.state,
                'requested_qty':sum(so.order_line.filtered(lambda line:not line.display_type).mapped('product_uom_qty')),
                'reserved_qty':sum(so.picking_ids.move_ids.filtered(lambda move:move.state not in ('done','cancel')).mapped('quantity'))}
                for so in measured_orders],
            'backorder_picking_ids':measured_orders.picking_ids.filtered(lambda picking:bool(picking.backorder_id)).ids,
            'stockout_so_ids':[orders[losers[0]]]}
finally:
    scenario_failed=sys.exc_info()[0] is not None
    cleanup_failed=False
    for sid in sessions:
        try:
            root.session_store.delete(root.session_store.get(sid))
        except Exception:
            cleanup_failed=True
            print('SPH_SESSION_CLEANUP_FAILURE: Flow A',file=sys.stderr,flush=True)
    if cleanup_failed and not scenario_failed:
        raise RuntimeError('Flow A session cleanup failed')
result['sessions_cleaned']=True
print('SPH_FLOW_A_RESULT '+json.dumps(result),flush=True)
