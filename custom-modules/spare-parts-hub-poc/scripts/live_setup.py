"""Executed only by the harness's local Odoo shell; stdout is memory-only IPC.
No password/API key is created. Ephemeral sessions stay in the disposable filestore.
"""
import json
from odoo import Command
from odoo.http import root
from odoo.addons.sph_core.tests.test_center_isolation import prepare

assert env.cr.dbname == 'sph_poc'
if globals().get('revoke'):
    user = env.ref('sph_core.fixture_user_sph_center_requester')
    user.sph_center_ids = [Command.clear()]
    env.cr.commit()
    env.registry.clear_cache()
    env.registry.signal_changes()
    print(json.dumps({'revoked': True}))
else:
    users, orders, lists, pickings = prepare(env)
    bot = env.ref('sph_core.fixture_user_sph_bot')
    bot.sph_center_ids = [Command.set(orders[0].sph_center_id.ids)]
    # Deliberately union native broad grants: global center/raw-stock rules must win.
    bot.group_ids = [Command.link(env.ref('sales_team.group_sale_manager').id),
                     Command.link(env.ref('stock.group_stock_manager').id)]
    attachment = env['ir.attachment'].create({'name': 'FIXTURE G1 document',
        'raw': b'FIXTURE protected payload', 'res_model': 'sale.order', 'res_id': orders[1].id})
    attachment.generate_access_token()
    roles = ('sph_hub_operator', 'sph_warehouse_picker', 'sph_purchasing_approver',
             'sph_center_requester', 'sph_center_receiver', 'sph_bot')
    sessions = {}
    for role in roles:
        user = env.ref('sph_core.fixture_user_' + role)
        session = root.session_store.new()
        session.update({'db': 'sph_poc', 'uid': user.id, 'login': user.login,
            'context': dict(user.with_user(user).context_get()),
            'session_token': user._compute_session_token(session.sid)})
        root.session_store.save(session)
        sessions[role] = session.sid
    result = {'sessions': sessions, 'orders': [x.id for x in orders],
        'names': [x.name for x in orders], 'prices': [123,124],
        'lines': [x.order_line.id for x in orders], 'lists': [x.id for x in lists],
        'items': [x.item_ids.id for x in lists], 'pickings': [x.id for x in pickings],
        'tokens': [x._portal_ensure_token() for x in orders],
        'attachment': attachment.id, 'attachment_token': attachment.access_token,
        'products': [env.ref('sph_core.fixture_part_' + key).product_variant_id.id
                     for key in ('01','02','03','04')]}
    env.cr.commit()
    env.registry.clear_cache()
    env.registry.signal_changes()
    print(json.dumps(result))
