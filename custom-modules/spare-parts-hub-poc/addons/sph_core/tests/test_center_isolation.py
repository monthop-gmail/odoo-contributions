"""G1 ORM evidence; real sessions and token routes belong in the live suite."""
from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase


def prepare(env):
    """SYNTHETIC ASSUMPTION: distinct same-parent prices, no fulfilment action."""
    centers = [env.ref('sph_core.fixture_center_shared_' + key) for key in ('a', 'b')]
    users = [env.ref('sph_core.fixture_user_sph_center_' + key) for key in ('requester', 'receiver')]
    product = env.ref('sph_core.fixture_part_01').product_variant_id
    orders, lists, pickings = [], [], []
    for number, (center, user) in enumerate(zip(centers, users)):
        user.sph_center_ids = [Command.set(center.ids)]
        user.partner_id.write({'parent_id': center.partner_id.id, 'sph_center_id': center.id})
        price = env['product.pricelist'].create({'name': 'FIXTURE scoped price ' + str(number),
            'sph_center_id': center.id, 'currency_id': env.company.currency_id.id,
            'item_ids': [Command.create({'applied_on': '3_global', 'fixed_price': 123 + number})]})
        order = env['sale.order'].create({'partner_id': center.partner_id.id,
            'sph_center_id': center.id, 'pricelist_id': price.id,
            'order_line': [Command.create({'product_id': product.id, 'product_uom_qty': 1,
                                          'price_unit': 123 + number})]})
        picking = env['stock.picking'].create({'partner_id': user.partner_id.id,
            'sph_center_id': center.id, 'picking_type_id': env.ref('sph_core.fixture_wh_central').out_type_id.id,
            'location_id': env.ref('sph_core.fixture_wh_central').lot_stock_id.id,
            'location_dest_id': env.ref('stock.stock_location_customers').id})
        orders.append(order); lists.append(price); pickings.append(picking)
    return users, orders, lists, pickings


class TestCenterIsolation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users, cls.orders, cls.lists, cls.pickings = prepare(cls.env)

    def test_own_projection(self):
        for i, user in enumerate(self.users):
            for record in (self.orders[i], self.orders[i].order_line, self.lists[i], self.pickings[i]):
                record.with_user(user).check_access('read')

    def test_bidirectional_id_denial(self):
        for i, user in enumerate(self.users):
            for record in (self.orders[1-i], self.orders[1-i].order_line, self.lists[1-i],
                           self.lists[1-i].item_ids, self.pickings[1-i]):
                with self.assertRaises(AccessError):
                    record.with_user(user).read(['id'])

    def test_partner_pricelist_location_spoof(self):
        for i, user in enumerate(self.users):
            model = self.env['sale.order'].with_user(user).with_context(
                sph_center_id=self.orders[1-i].sph_center_id.id, allowed_company_ids=self.env.company.ids,
                partner_id=self.orders[1-i].partner_id.id, pricelist=self.lists[1-i].id,
                location=self.env.ref('sph_core.fixture_wh_owned').lot_stock_id.id)
            self.assertFalse(model.search([('id', '=', self.orders[1-i].id)]))

    def test_search_count_group_export_report(self):
        for i, user in enumerate(self.users):
            model = self.env['sale.order'].with_user(user)
            self.assertEqual(model.search_count([('id', 'in', [x.id for x in self.orders])]), 1)
            grouped = model._read_group([('id', 'in', [x.id for x in self.orders])], ['sph_center_id'], ['__count'])
            self.assertEqual(sum(row[1] for row in grouped), 1)
            with self.assertRaises(UserError):
                self.orders[1-i].with_user(user).export_data(['name'])
            with self.assertRaises(UserError):
                self.orders[i].with_user(user).export_data(['name'])

    def test_lines_attachments_no_leak(self):
        attachment = self.env['ir.attachment'].create({'name': 'FIXTURE scoped attachment',
            'raw': b'FIXTURE protected payload', 'res_model': 'sale.order', 'res_id': self.orders[1].id})
        with self.assertRaises(AccessError):
            attachment.with_user(self.users[0]).read(['raw'])
        self.assertFalse(self.env['sale.order.line'].with_user(self.users[0]).search([
            ('order_id', '=', self.orders[1].id)]))

    def test_cross_center_share_token(self):
        # ORM token/context cannot bypass global scope; actual URL tokens tested live.
        token = self.orders[1]._portal_ensure_token()
        with self.assertRaises(AccessError):
            self.orders[1].with_user(self.users[0]).with_context(access_token=token).read(['name'])

    def test_anonymous_revoke_denial(self):
        with self.assertRaises(AccessError):
            self.orders[0].with_user(self.env.ref('base.public_user')).read(['name'])
        self.users[0].sph_center_ids = [Command.clear()]
        self.assertFalse(self.env['sale.order'].with_user(self.users[0]).search([
            ('id', '=', self.orders[0].id)]))

    def test_ai_scope_and_group_union(self):
        bot = self.env.ref('sph_core.fixture_user_sph_bot')
        bot.write({'sph_center_ids': [Command.set(self.orders[0].sph_center_id.ids)],
            'group_ids': [Command.link(self.env.ref('sales_team.group_sale_manager').id),
                          Command.link(self.env.ref('stock.group_stock_manager').id)]})
        self.orders[0].with_user(bot).check_access('read')
        with self.assertRaises(AccessError):
            self.orders[1].with_user(bot).read(['name'])
        self.assertFalse(self.env['stock.quant'].with_user(bot).search([]))

        for field in ('qty_available', 'free_qty', 'standard_price'):
            with self.assertRaises(AccessError):
                self.env.ref('sph_core.fixture_part_01').product_variant_id.with_user(bot).read([field])
