"""Original SPH wrapper. HTTP owns the commit/retry; no inner commit here."""
from datetime import timedelta
import logging
from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError

_logger = logging.getLogger(__name__)
LOCK_NAMESPACE = 194556264


def lock_stock(env, product, location):
    # Product key serializes participating operations; existing quant rows lock below.
    # REPEATABLE READ conflicts still require the HTTP whole-request retry.
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
            raise UserError('Unavailable')
        try:
            self.check_access('read')
            if not self.exists():
                raise AccessError('Unavailable')
        except (AccessError, MissingError):
            from .authority import audit
            # No resource lookup or foreign identifier in scope-denial evidence.
            audit(self.browse(),'sale.reserve.scope','deny')
            raise UserError('Unavailable') from None
        if not self.sph_center_id or not isinstance(request_key,str) or not request_key or len(request_key)>80:
            raise UserError('Unavailable')
        self.env.cr.execute('SELECT id FROM sale_order WHERE id=%s FOR UPDATE', [self.id])
        order = self.sudo()
        warehouse = self.env.ref('sph_core.fixture_wh_central').sudo()
        # Reservation authority is not Sales confirmation/warehouse-edit authority.
        if order.state != 'sale' or order.warehouse_id != warehouse:
            from .authority import audit
            audit(self,'sale.reserve.confirm','deny')
            raise UserError('Unavailable')
        previous = self.env['sph.reservation'].sudo().search([
            ('order_id','=',self.id),('request_key','=',request_key)])
        if previous:
            status = previous[0].state
            if status == 'active':
                status = 'partial' if any(previous.mapped('backorder_qty')) else 'reserved'
            return {'status':status, 'reservation_ids':previous.ids}
        if self.env['sph.reservation'].sudo().search_count([('order_id','=',self.id),('state','=','active')]):
            raise UserError('Unavailable')
        warehouse = self.env.ref('sph_core.fixture_wh_central').sudo()
        lines = order.order_line.filtered(lambda line:not line.display_type)
        if not lines:
            raise UserError('Unavailable')
        for product in lines.product_id.sorted('id'):
            if not product.sph_fixture or product.tracking != 'none':
                raise UserError('Unavailable')
            lock_stock(self.env, product, warehouse.lot_stock_id)
        # Require all-or-nothing unless the human explicitly elects partial allocation.
        for product in lines.product_id:
            demand = sum(lines.filtered(lambda line:line.product_id == product).mapped('product_uom_qty'))
            if order.state == 'sale':
                demand = sum(order.picking_ids.move_ids.filtered(lambda m:m.product_id == product and m.state not in ('done','cancel')).mapped('product_uom_qty'))
            quants = lock_stock(self.env, product, warehouse.lot_stock_id)
            free = sum(q.quantity-q.reserved_quantity for q in quants)
            if demand <= 0 or free <= 0 or (not allow_partial and demand > free):
                raise UserError('Unavailable')
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


class Quant(models.Model):
    _inherit = 'stock.quant'

    @api.model
    def _update_available_quantity(self, product_id, location_id, quantity=False,
                                   reserved_quantity=False, **kwargs):
        # Native assignments/mutations participate too, including missing-quant cases.
        if product_id.sph_fixture and location_id.usage == 'internal':
            lock_stock(self.env, product_id, location_id)
        return super()._update_available_quantity(product_id, location_id,
            quantity=quantity, reserved_quantity=reserved_quantity, **kwargs)

    @api.constrains('quantity','reserved_quantity','product_id','location_id')
    def _sph_no_negative(self):
        for quant in self:
            if quant.product_id.sph_fixture and quant.location_id.usage == 'internal' and (
                quant.quantity < -0.000001 or quant.reserved_quantity < -0.000001 or
                quant.reserved_quantity > quant.quantity+0.000001):
                raise UserError('Unavailable')


class Move(models.Model):
    _inherit = 'stock.move'

    sph_reserved_limit = fields.Float(copy=False)
    sph_reservation_id = fields.Many2one('sph.reservation', copy=False, ondelete='restrict')

    def _action_done(self, cancel_backorder=False):
        protected = self.filtered(lambda m:m.picking_id.sph_center_id and m.location_id.usage == 'internal')
        for move in protected:
            reservation = move.sph_reservation_id
            if (not reservation or reservation.state != 'active' or
                reservation.expires_at <= fields.Datetime.now() or
                move.quantity > move.sph_reserved_limit+0.000001):
                raise UserError('Unavailable')
        result = super()._action_done(cancel_backorder=cancel_backorder)
        protected.filtered(lambda m:m.state == 'done').sph_reservation_id.write({'state':'done'})
        return result
