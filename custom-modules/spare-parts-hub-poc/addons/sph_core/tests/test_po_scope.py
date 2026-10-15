"""B7a creator ownership and native read visibility; no seeded hub exception."""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestPOCenterScope(TransactionCase):
    def setUp(self):
        super().setUp()
        self.centers=[self.env.ref('sph_core.fixture_center_shared_'+key) for key in ('a','b')]
        self.supplier=self.env.ref('sph_core.fixture_supplier_1')
        self.product=self.env.ref('sph_core.fixture_part_05').product_variant_id
        self.users=[];self.bots=[];self.orders=[]
        for index,center in enumerate(self.centers):
            # Deliberately include native Purchase ACLs ONLY in rollback-only tests.
            # The global PO rule must restrict an otherwise broadly capable user.
            user=self.env['res.users'].with_context(no_reset_password=True).create({
                'name':'FIXTURE PO reviewer '+str(index),'login':'fixture_po_reviewer_'+str(index),
                'group_ids':[Command.set([self.env.ref('sph_core.group_sph_purchasing_approver').id,
                    self.env.ref('purchase.group_purchase_user').id])],
                'sph_center_ids':[Command.set(center.ids)]})
            bot=self.env['res.users'].with_context(no_reset_password=True).create({
                'name':'FIXTURE PO bot '+str(index),'login':'fixture_po_bot_'+str(index),
                'group_ids':[Command.set(self.env.ref('sph_core.group_sph_bot').ids)],
                'sph_center_ids':[Command.set(center.ids)]})
            self.users.append(user);self.bots.append(bot)
            self.orders.append(self.env['purchase.order'].browse(self.prepare(bot)))

    def prepare(self,user,**kwargs):
        return self.env['purchase.order'].with_user(user).sph_prepare(self.supplier.id,self.product.id,**kwargs)

    def denied(self,operation):
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            operation()

    def test_creator_center_server_assigned(self):
        for center,user,bot,po in zip(self.centers,self.users,self.bots,self.orders):
            self.assertEqual(po.sph_center_id,center)
            self.assertEqual(po.sph_maker_uid,bot.id)
            direct=self.env['purchase.order'].with_user(user).create({'partner_id':self.supplier.id})
            self.assertEqual(direct.sph_center_id,center)
            self.assertEqual(direct.sph_maker_uid,user.id)

    def test_same_center_read_search_export(self):
        for user,po in zip(self.users,self.orders):
            self.assertEqual(po.with_user(user).read(['name'])[0]['id'],po.id)
            self.assertIn(po,self.env['purchase.order'].with_user(user).search([]))
            self.assertEqual(len(po.with_user(user).export_data(['name'])['datas']),1)

    def test_cross_center_same_commercial_partner(self):
        self.assertEqual(self.centers[0].partner_id.commercial_partner_id,self.centers[1].partner_id.commercial_partner_id)
        for index,user in enumerate(self.users):
            foreign=self.orders[1-index]
            self.denied(lambda:foreign.with_user(user).read(['name']))
            self.denied(lambda:foreign.with_user(user).export_data(['name']))
            self.assertNotIn(foreign,self.env['purchase.order'].with_user(user).search([]))
            missing=self.env['purchase.order'].browse(2147483647).with_user(user)
            self.denied(lambda:missing.read(['name']))

    def test_no_membership_denies_all_b7a_paths(self):
        user=self.users[0];user.sph_center_ids=[Command.clear()]
        model=self.env['purchase.order'].with_user(user)
        for operation in (lambda:model.create({'partner_id':self.supplier.id}),
                lambda:self.prepare(user),lambda:self.orders[0].with_user(user).read(['name']),
                lambda:model.search([]),lambda:model.search_count([]),
                lambda:self.orders[0].with_user(user).export_data(['name'])):
            self.denied(operation)

    def test_ambiguous_creator_denied(self):
        user=self.users[0];user.sph_center_ids=[Command.set((self.centers[0]|self.centers[1]).ids)]
        self.denied(lambda:self.prepare(user))
        self.denied(lambda:self.env['purchase.order'].with_user(user).create({'partner_id':self.supplier.id}))

    def test_client_center_kwargs_and_context_denied(self):
        user=self.users[0]
        for key in ('center_id','sph_center_id'):
            self.denied(lambda:self.prepare(user,**{key:self.centers[1].id}))
        for key in ('center_id','sph_center_id','default_sph_center_id','default_center_id'):
            model=self.env['purchase.order'].with_user(user).with_context(**{key:self.centers[1].id})
            self.denied(lambda:model.sph_prepare(self.supplier.id,self.product.id))
            self.denied(lambda:model.create({'partner_id':self.supplier.id}))
        self.denied(lambda:self.env['purchase.order'].with_user(user).create({
            'partner_id':self.supplier.id,'sph_center_id':self.centers[0].id}))

    def test_explicit_hub_grant_and_revoke(self):
        user=self.users[0];user.sph_center_ids=[Command.clear()]
        grant=self.env.ref('sph_core.group_sph_po_hub')
        user.group_ids=[Command.link(grant.id)]
        for po in self.orders:self.assertTrue(po.with_user(user).read(['name']))
        self.assertEqual(len(self.env['purchase.order'].with_user(user).search([('id','in',[po.id for po in self.orders])])),2)
        # Hub visibility does not select an ambiguous/missing creator center.
        self.denied(lambda:self.prepare(user))
        user.group_ids=[Command.unlink(grant.id)]
        self.denied(lambda:self.env['purchase.order'].with_user(user).search([]))
        self.denied(lambda:self.orders[0].with_user(user).read(['name']))

    def test_no_seeded_hub_grants_or_acl_implication(self):
        grant=self.env.ref('sph_core.group_sph_po_hub')
        self.assertFalse(self.env['res.users'].search([('group_ids','in',grant.id)]))
        self.assertFalse(grant.implied_ids)
        rule=self.env.ref('sph_core.scope_purchase_order')
        self.assertTrue(rule['global'])
        self.assertNotIn('_sph_scoped',rule.domain_force)

    def test_owner_immutable(self):
        po=self.orders[0]
        self.denied(lambda:po.with_user(self.users[0]).write({'sph_center_id':self.centers[1].id}))
        self.assertEqual(po.sph_center_id,self.centers[0])
