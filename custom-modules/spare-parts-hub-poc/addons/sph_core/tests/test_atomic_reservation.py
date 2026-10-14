"""Transactional invariants only: these tests do NOT simulate a race."""
from datetime import timedelta
from unittest.mock import patch
from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


class TestAtomicReservation(TransactionCase):
    def order(self, quantity=1, part='04'):
        product = self.env.ref('sph_core.fixture_part_'+part).product_variant_id
        center = self.env.ref('sph_core.fixture_center_independent_a')
        return self.env['sale.order'].create({'partner_id':center.partner_id.id,
            'sph_center_id':center.id,'warehouse_id':self.env.ref('sph_core.fixture_wh_central').id,
            'order_line':[Command.create({'product_id':product.id,'product_uom_qty':quantity,'price_unit':101})]})

    def reserve(self, order, key='FIXTURE request', **kwargs):
        return order.with_user(self.env.ref('sph_core.fixture_user_sph_hub_operator')).sph_reserve(key, **kwargs)

    def test_scope_and_ai_denial(self):
        order = self.order()
        for role in ('sph_bot','sph_center_requester','sph_purchasing_approver'):
            with self.assertRaises(AccessError):
                order.with_user(self.env.ref('sph_core.fixture_user_'+role)).sph_reserve('FIXTURE denied')

    def test_reserve_readback(self):
        order = self.order(); result = self.reserve(order)
        self.assertEqual(result['status'],'reserved')
        reservation = order.sph_reservation_ids
        self.assertEqual(reservation.reserved_qty,1)
        self.assertEqual(reservation.move_id.quantity,1)
        self.assertEqual(order.state,'sale')
        self.assertEqual(reservation.move_id.picking_id.sph_center_id,order.sph_center_id)

    def test_failure_rolls_back(self):
        order = self.order()
        class Injected(Exception): pass
        with self.assertRaises(Injected), self.env.cr.savepoint():
            self.reserve(order)
            raise Injected()
        order.invalidate_recordset()
        self.assertEqual(order.state,'draft')
        self.assertFalse(order.sph_reservation_ids)
        self.assertFalse(order.picking_ids)

    def test_request_replay(self):
        order = self.order(); first = self.reserve(order)
        self.assertEqual(first,self.reserve(order))
        self.assertEqual(len(order.sph_reservation_ids),1)

    def test_reserve_beyond_free_denied(self):
        order = self.order(2)
        with self.assertRaises(UserError): self.reserve(order)
        self.assertEqual(order.state,'draft')
        self.assertFalse(order.sph_reservation_ids)

    def test_delivery_over_reserved_denied(self):
        order = self.order(1,part='01'); self.reserve(order)
        move = order.sph_reservation_ids.move_id
        move.quantity = 2
        move.picked = True
        with self.assertRaises(UserError): move.picking_id.button_validate()
        self.assertNotEqual(move.state,'done')

    def test_partial_and_backorder(self):
        order = self.order(10,part='01'); result = self.reserve(order,allow_partial=True)
        self.assertEqual(result['status'],'partial')
        reservation = order.sph_reservation_ids
        self.assertEqual((reservation.reserved_qty,reservation.backorder_qty),(8,2))
        move = reservation.move_id
        move.picked = True
        move._action_done()
        self.assertEqual(reservation.state,'done')
        remaining = order.picking_ids.move_ids.filtered(lambda m:m.state not in ('done','cancel'))
        self.assertEqual(sum(remaining.mapped('product_uom_qty')),2)
        self.assertFalse(remaining.sph_reservation_id)

    def test_expiry_frozen_clock(self):
        order = self.order(); self.reserve(order)
        reservation = order.sph_reservation_ids
        before = reservation.expires_at-timedelta(seconds=1)
        with patch.object(fields.Datetime,'now',return_value=before):
            self.assertEqual(self.env['sph.reservation']._cron_expire(),0)
        with patch.object(fields.Datetime,'now',return_value=reservation.expires_at+timedelta(seconds=1)):
            self.assertEqual(self.env['sph.reservation']._cron_expire(),1)
        self.assertEqual(reservation.state,'expired')
        self.assertEqual(reservation.move_id.quantity,0)
        self.assertEqual(self.reserve(order)['status'],'expired')

    def test_native_negative_quant_denied(self):
        product = self.env.ref('sph_core.fixture_part_04').product_variant_id
        location = self.env.ref('sph_core.fixture_wh_central').lot_stock_id
        with self.assertRaises(UserError):
            self.env['stock.quant']._update_available_quantity(product,location,-2)
