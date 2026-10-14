"""Original SPH wrapper. HTTP owns the commit/retry; no inner commit here."""
from datetime import timedelta
import logging
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)
LOCK_NAMESPACE = 194556264


def lock_stock(env, product, location):
    # One advisory key per fixture product also covers absent/duplicate quant rows.
    env.cr.execute('SELECT pg_try_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, product.id])
    if not env.cr.fetchone()[0]:
        _logger.info('SPH_LOCK_WAIT: fixture stock serialization')
        env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', [LOCK_NAMESPACE, product.id])
    env['stock.quant'].flush_model(['quantity', 'reserved_quantity'])
    env.cr.execute('SELECT id FROM stock_quant WHERE product_id=%s AND location_id=%s ORDER BY id FOR UPDATE',
                   [product.id, location.id])
    ids = [row[0] for row in env.cr.fetchall()]
    quants = env['stock.quant'].sudo().browse(ids)
    quants.invalidate_recordset(['quantity', 'reserved_quantity'])
    return quants


class Reservation(models.Model):
    _name = 'sph.reservation'
    _description = 'SPH synthetic reservation ledger'

    order_id = fields.Many2one('sale.order', required=True, ondelete='restrict')
    move_id = fields.Many2one('stock.move', required=True, ondelete='restrict')
    request_key = fields.Char(required=True)
    requested_qty = fields.Float(required=True)
    reserved_qty = fields.Float(required=True)
    backorder_qty = fields.Float(required=True)
    expires_at = fields.Datetime(required=True)
    state = fields.Selection([('active','Active'),('expired','Expired'),('done','Done')], default='active', required=True)

    @api.model
    def _cron_expire(self):
        expired = self.sudo().search([('state','=','active'),('expires_at','<=',fields.Datetime.now())])
        for reservation in expired:
            move = reservation.move_id
            if move.state not in ('done','cancel'):
                lock_stock(self.env, move.product_id, move.location_id)
                move._do_unreserve()
                move.sph_reserved_limit = 0
                reservation.state = 'expired'
            else:
                reservation.state = 'done'
        return len(expired)


class Order(models.Model):
    _inherit = 'sale.order'

    sph_reservation_ids = fields.One2many('sph.reservation','order_id', groups='base.group_system')

    def sph_reserve(self, request_key, allow_partial=False):
        self.ensure_one()
        user = self.env.user
        if user.has_group('sph_core.group_sph_bot') or not (
            user.has_group('sph_core.group_sph_hub_operator') or
            user.has_group('sph_core.group_sph_warehouse_picker')):
            raise AccessError('Unavailable')
        self.check_access('read')
        if not self.sph_center_id or not isinstance(request_key,str) or not request_key or len(request_key)>80:
            raise UserError('Unavailable')
        self.env.cr.execute('SELECT id FROM sale_order WHERE id=%s FOR UPDATE', [self.id])
        order = self.sudo()
        existing = self.env['sph.reservation'].sudo().search([('order_id','=',self.id)])
        if existing:
            if all(r.request_key == request_key and r.state == 'active' for r in existing):
                return {'status':'reserved', 'reservation_ids':existing.ids}
            raise UserError('Unavailable')
        warehouse = self.env.ref('sph_core.fixture_wh_central').sudo()
        lines = order.order_line.filtered(lambda line:not line.display_type)
        if not lines or order.state not in ('draft','sent','sale'):
            raise UserError('Unavailable')
        for product in lines.product_id.sorted('id'):
            if not product.sph_fixture or product.tracking != 'none':
                raise UserError('Unavailable')
            lock_stock(self.env, product, warehouse.lot_stock_id)
        # Require all-or-nothing unless the human explicitly elects partial allocation.
        for product in lines.product_id:
            demand = sum(lines.filtered(lambda line:line.product_id == product).mapped('product_uom_qty'))
            quants = lock_stock(self.env, product, warehouse.lot_stock_id)
            free = sum(q.quantity-q.reserved_quantity for q in quants)
            if demand <= 0 or free <= 0 or (not allow_partial and demand > free):
                raise UserError('Unavailable')
        order.warehouse_id = warehouse
        if order.state != 'sale':
            order.action_confirm()
        pickings = order.picking_ids.filtered(lambda p:p.state not in ('done','cancel'))
        pickings.sph_center_id = order.sph_center_id
        moves = pickings.move_ids.filtered(lambda m:m.state not in ('done','cancel'))
        if not moves:
            raise UserError('Unavailable')
        moves._action_assign()
        reservations = self.env['sph.reservation'].sudo()
        for move in moves:
            reserved = move.quantity
            if reserved <= 0 or (not allow_partial and reserved < move.product_uom_qty):
                raise UserError('Unavailable')
            move.sph_reserved_limit = reserved
            reservation = reservations.create({'order_id':order.id,'move_id':move.id,
                'request_key':request_key,'requested_qty':move.product_uom_qty,'reserved_qty':reserved,
                'backorder_qty':max(0,move.product_uom_qty-reserved),
                'expires_at':fields.Datetime.now()+timedelta(hours=48)})
            move.sph_reservation_id = reservation
            reservations |= reservation
        return {'status':'partial' if any(reservations.mapped('backorder_qty')) else 'reserved',
                'reservation_ids':reservations.ids}
