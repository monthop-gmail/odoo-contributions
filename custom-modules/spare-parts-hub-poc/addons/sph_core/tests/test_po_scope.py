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
                    self.env.ref('purchase.group_purchase_user').id,
                    self.env.ref('base.group_allow_export').id])],
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

    def snapshot(self,orders):
        return [(po.id,po.state,po.sph_review_digest,po.sph_reviewer_uid,
            po.sph_incident_ref,po.picking_ids.ids,po.order_line.mapped('product_qty')) for po in orders.sudo()]

    def entrypoints(self,record):
        return {
            'draft':lambda:record.sph_draft(quantity=2),
            'review':lambda:record.sph_review(),
            'check':lambda:record._sph_check_review(),
            'allowed':lambda:record._approval_allowed(),
            'confirm':lambda:record.button_confirm(),
            'approve':lambda:record.button_approve(force=True),
            'state':lambda:record.write({'state':'purchase'}),
            'ordinary_write':lambda:record.write({'notes':'FIXTURE unauthorized edit'}),
            'date':lambda:record.write({'date_approve':False}),
            'identity':lambda:record.write({'sph_reviewer_uid':record.env.uid}),
            'rfq':lambda:record.action_rfq_send(),
            'digest':lambda:record._sph_digest(),
            'incident':lambda:record.write({'sph_incident_ref':'fixture:scope'}),
            'locked':lambda:record.write({'locked':True}),
            'locked_bundle':lambda:record.write({'locked':True,'notes':'FIXTURE scope bundle'}),
        }

    def deny_matrix(self,record):
        all_orders=self.orders[0]|self.orders[1]
        before=self.snapshot(all_orders)
        for name,operation in self.entrypoints(record).items():
            with self.subTest(path=name):self.denied(operation)
            self.assertEqual(self.snapshot(all_orders),before)

    def test_remaining_entrypoints_bidirectional_scope(self):
        for index,user in enumerate(self.users):
            self.deny_matrix(self.orders[1-index].with_user(user))

    def test_remaining_entrypoints_empty_membership(self):
        user=self.users[0];user.sph_center_ids=[Command.clear()]
        self.deny_matrix(self.orders[0].with_user(user))
        self.denied(lambda:self.env['purchase.order'].with_user(user).create({
            'partner_id':self.supplier.id,'sph_incident_ref':'fixture:scope'}))

    def test_unknown_unassigned_and_revoked_scope(self):
        user=self.users[0]
        self.deny_matrix(self.env['purchase.order'].browse(2147483647).with_user(user))
        # Only emulate an impossible-on-create legacy row inside this rollback test.
        self.env.cr.execute('ALTER TABLE purchase_order ALTER COLUMN sph_center_id DROP NOT NULL')
        self.env.cr.execute('UPDATE purchase_order SET sph_center_id=NULL WHERE id=%s',[self.orders[1].id])
        self.orders[1].invalidate_recordset(['sph_center_id'])
        self.deny_matrix(self.orders[1].with_user(user))
        self.orders[0].with_user(user).sph_review()
        user.sph_center_ids=[Command.clear()]
        self.deny_matrix(self.orders[0].with_user(user))

    def test_mixed_batch_atomic_and_center_context_spoof(self):
        user=self.users[0]
        self.deny_matrix((self.orders[0]|self.orders[1]).with_user(user))
        for key in ('center_id','sph_center_id','default_center_id','default_sph_center_id'):
            self.deny_matrix(self.orders[1].with_user(user).with_context(**{key:self.centers[1].id}))

    def test_same_center_review_rfq_confirm_and_draft(self):
        for index,user in enumerate(self.users):
            po=self.orders[index]
            self.assertEqual(po.with_user(self.bots[index]).sph_draft(quantity=2)['lines'][0]['quantity'],2)
            human=po.with_user(user)
            self.assertTrue(human.sph_review())
            self.assertEqual(human._sph_digest(),po.sph_review_digest)
            self.assertTrue(human.action_rfq_send())
            self.assertTrue(human._approval_allowed())
            human.write({'sph_incident_ref':'fixture:own'})
            human.write({'locked':True});human.write({'locked':False})
            human.button_confirm()
            self.assertEqual(po.state,'purchase')
            self.assertTrue(po.picking_ids)

    def test_hub_grant_revoke_remaining_capabilities(self):
        user=self.users[0];foreign=self.orders[1].with_user(user)
        grant=self.env.ref('sph_core.group_sph_po_hub')
        self.denied(lambda:foreign.sph_review())
        user.group_ids=[Command.link(grant.id)]
        self.assertTrue(foreign.sph_review())
        self.assertTrue(foreign._sph_digest())
        foreign.write({'sph_incident_ref':'fixture:grant'})
        user.group_ids=[Command.unlink(grant.id)]
        self.deny_matrix(foreign)

    def test_po_lines_mail_attachments_authorized_only(self):
        messages=[];attachments=[]
        for po in self.orders:
            messages.append(self.env['mail.message'].create({'model':'purchase.order','res_id':po.id,
                'body':'FIXTURE PO thread','message_type':'comment'}))
            attachments.append(self.env['ir.attachment'].create({'name':'FIXTURE PO attachment',
                'raw':b'FIXTURE PO contents','res_model':'purchase.order','res_id':po.id}))
        for index,user in enumerate(self.users):
            foreign=1-index
            for records,field in ((self.orders[index].order_line,'id'),(messages[index],'body'),(attachments[index],'raw')):
                self.assertTrue(records.with_user(user).read([field]))
            for records,field in ((self.orders[foreign].order_line,'id'),(messages[foreign],'body'),(attachments[foreign],'raw')):
                self.denied(lambda:records.with_user(user).read([field]))
            for model,records in (('purchase.order',self.orders),('purchase.order.line',[p.order_line for p in self.orders]),
                    ('mail.message',messages),('ir.attachment',attachments)):
                ids=[r.id for r in records];actor=self.env[model].with_user(user)
                visible=actor.search([('id','in',ids)])
                self.assertEqual(visible.ids,[ids[index]])
                self.assertEqual(actor.search_count([('id','in',ids)]),1)
            user.sph_center_ids=[Command.clear()]
            for records,field in ((self.orders[index].order_line,'id'),(messages[index],'body'),(attachments[index],'raw')):
                self.denied(lambda:records.with_user(user).read([field]))
            for model,records in (('mail.message',messages),('ir.attachment',attachments)):
                self.assertFalse(self.env[model].with_user(user).search([('id','in',[r.id for r in records])]))

    def test_attachment_token_cannot_replace_center(self):
        po=self.orders[1]
        attachment=self.env['ir.attachment'].create({'name':'FIXTURE binary token',
            'raw':b'FIXTURE token protected','res_model':'purchase.order','res_id':po.id,
            'access_token':'fixture-po-test-token'})
        binary=self.env['ir.binary'].with_user(self.users[0])
        self.denied(lambda:binary._find_record(res_id=attachment.id,access_token='fixture-po-test-token'))
        self.denied(lambda:binary._find_record(res_id=2147483647,access_token='fixture-po-test-token'))
        self.assertEqual(self.env['ir.binary'].with_user(self.users[1])._find_record(
            res_id=attachment.id,access_token='fixture-po-test-token').id,attachment.id)

    def test_native_access_and_thread_checks_fail_closed(self):
        for index,user in enumerate(self.users):
            self.orders[index].with_user(user).check_access('read')
            for po in (self.orders[1-index],self.env['purchase.order'].browse(2147483647)):
                self.denied(lambda:po.with_user(user).check_access('read'))
            user.sph_center_ids=[Command.clear()]
            self.denied(lambda:self.orders[index].with_user(user).check_access('read'))

    def test_link_projection_grant_revoke_cached_reads(self):
        po=self.orders[1];user=self.users[0]
        msg=self.env['mail.message'].create({'model':'purchase.order','res_id':po.id,
            'body':'FIXTURE shared thread','message_type':'comment'})
        attachment=self.env['ir.attachment'].create({'name':'FIXTURE shared attachment',
            'raw':b'FIXTURE protected','res_model':'purchase.order','res_id':po.id})
        for row in (msg,attachment):self.assertFalse(row.with_user(user).sph_po_visible)
        grant=self.env.ref('sph_core.group_sph_po_hub')
        user.group_ids=[Command.link(grant.id)]
        for row in (msg,attachment):
            self.assertTrue(row.with_user(user).sph_po_visible)
            self.assertTrue(row.with_user(user).read(['id']))
        user.group_ids=[Command.unlink(grant.id)]
        for row in (msg,attachment):
            self.assertFalse(row.with_user(user).sph_po_visible)
            self.denied(lambda:row.with_user(user).read(['id']))

    def test_system_sudo_without_membership_denied(self):
        root=self.env.ref('base.user_root')
        root.sph_center_ids=[Command.clear()]
        cron_actor=self.env['res.users'].with_context(no_reset_password=True).create({
            'name':'FIXTURE cron-like approver','login':'fixture_cron_approver',
            'group_ids':[Command.set(self.env.ref('sph_core.group_sph_purchasing_approver').ids)],
            'sph_center_ids':[Command.clear()]})
        before=self.snapshot(self.orders[0]|self.orders[1])
        for actor in (root,cron_actor):
            self.assertFalse(actor.sph_center_ids)
            for values in ({'state':'purchase'},{'date_approve':False},{'locked':True}):
                self.denied(lambda:self.orders[0].with_user(actor).sudo().write(values))
        self.assertEqual(self.snapshot(self.orders[0]|self.orders[1]),before)

    def test_approval_predicate_denies_by_exception(self):
        # Native predicate callers must handle a denial, not expect False.
        self.denied(lambda:self.orders[0].with_user(self.bots[0])._approval_allowed())
        self.users[0].sph_center_ids=[Command.clear()]
        self.denied(lambda:self.orders[0].with_user(self.users[0])._approval_allowed())

    def test_receipt_rule_explicit_membership(self):
        receipts=[]
        for user,po in zip(self.users,self.orders):
            po.with_user(user).sph_review();po.with_user(user).button_confirm()
            self.assertTrue(po.picking_ids)
            self.assertEqual(po.picking_ids.sph_center_id,po.sph_center_id)
            receipts.append(po.picking_ids.ensure_one())
        actor=self.env.ref('sph_core.fixture_user_native_actor')
        self.assertFalse(actor.sph_center_ids)
        self.assertFalse(actor.has_group('sph_core.group_sph_po_hub'))
        rule=self.env.ref('sph_core.scope_stock_picking')
        self.assertNotIn('_sph_scoped',rule.domain_force)
        for receipt in receipts:
            with self.assertRaises(AccessError):receipt.with_user(actor).read(['name'])
        self.assertFalse(self.env['stock.picking'].with_user(actor).search([('id','in',[r.id for r in receipts])]))
        actor.sph_center_ids=[Command.set(self.centers[0].ids)]
        self.assertTrue(receipts[0].with_user(actor).read(['name']))
        with self.assertRaises(AccessError):receipts[1].with_user(actor).read(['name'])
        self.assertEqual(self.env['stock.picking'].with_user(actor).search_count([('id','in',[r.id for r in receipts])]),1)
        actor.sph_center_ids=[Command.clear()]
        actor.group_ids=[Command.link(self.env.ref('sph_core.group_sph_picking_hub').id)]
        self.assertEqual(self.env['stock.picking'].with_user(actor).search_count([('id','in',[r.id for r in receipts])]),2)
        actor.group_ids=[Command.unlink(self.env.ref('sph_core.group_sph_picking_hub').id)]
        self.assertFalse(self.env['stock.picking'].with_user(actor).search([('id','in',[r.id for r in receipts])]))

    def company_probe(self):
        other=self.env['res.company'].create({'name':'FIXTURE company boundary B',
            'po_double_validation':'two_step','po_double_validation_amount':0})
        partner=self.env['res.partner'].create({'name':'FIXTURE company B center partner','company_id':other.id})
        center=self.env['sph.center'].create({'name':'FIXTURE company B center','company_id':other.id,
            'center_type':'independent','partner_id':partner.id})
        maker=self.env['res.users'].with_context(no_reset_password=True).create({
            'name':'FIXTURE company B maker','login':'fixture_company_b_maker','company_id':other.id,
            'company_ids':[Command.set(other.ids)],'sph_center_ids':[Command.set(center.ids)],
            'group_ids':[Command.set(self.env.ref('sph_core.group_sph_bot').ids)]})
        po=self.env['purchase.order'].browse(self.env['purchase.order'].with_user(maker).with_context(
            allowed_company_ids=other.ids).sph_prepare(self.supplier.id,self.product.id))
        return other,center,po

    def test_legitimate_company_context_review_confirm(self):
        human=self.orders[0].with_user(self.users[0]).with_context(
            allowed_company_ids=self.env.company.ids,force_company=self.env.company.id)
        self.assertTrue(human.sph_review());human.button_confirm()
        self.assertEqual(self.orders[0].state,'purchase')
        self.assertTrue(self.orders[0].picking_ids)

    def test_forged_company_context_denied_even_under_sudo(self):
        other,center,foreign=self.company_probe()
        po=self.orders[0];user=self.users[0]
        po.with_user(user).sph_review()  # Every other confirm predicate is valid.
        before=self.snapshot(po|foreign)
        for context in ({'allowed_company_ids':other.ids},
                {'allowed_company_ids':[self.env.company.id,other.id]},
                {'allowed_company_ids':self.env.company.ids,'force_company':other.id},
                {'force_company':other.id}):
            for elevated in (False,True):
                record=po.with_user(user).with_context(**context)
                if elevated:record=record.sudo()
                self.denied(lambda:record.sph_review())
                self.denied(lambda:record.button_confirm())
                self.denied(lambda:record.button_approve(force=True))
                self.assertEqual(self.snapshot(po|foreign),before)

    def test_active_company_not_union_and_mixed_batch_atomic(self):
        other,center,foreign=self.company_probe();user=self.users[0];own=self.orders[0]
        user.company_ids=[Command.link(other.id)]
        user.sph_center_ids=[Command.link(center.id)]  # Prevent center mismatch masking company denial.
        own.with_user(user).with_context(allowed_company_ids=self.env.company.ids).sph_review()
        foreign.with_user(user).with_context(allowed_company_ids=other.ids).sph_review()
        self.assertEqual(foreign.sph_reviewer_uid,user.id)
        self.assertEqual(foreign.sph_review_digest,foreign._sph_digest_value())
        before=self.snapshot(own|foreign)
        for context in ({'allowed_company_ids':self.env.company.ids},
                {'allowed_company_ids':[self.env.company.id,other.id]},
                {'allowed_company_ids':self.env.company.ids,'force_company':other.id}):
            for record in (foreign,own|foreign):
                self.denied(lambda:record.with_user(user).with_context(**context).sph_review())
                self.denied(lambda:record.with_user(user).with_context(**context).button_confirm())
            self.assertEqual(self.snapshot(own|foreign),before)
        user.group_ids=[Command.link(self.env.ref('sph_core.group_sph_po_hub').id)]
        self.denied(lambda:foreign.with_user(user).with_context(allowed_company_ids=self.env.company.ids).button_confirm())
        user.company_ids=[Command.set(self.env.company.ids)]
        self.denied(lambda:foreign.with_user(user).with_context(allowed_company_ids=other.ids).sph_review())
        self.assertEqual(self.snapshot(own|foreign),before)

    def test_company_write_cannot_redirect_reviewed_order(self):
        other,center,foreign=self.company_probe();po=self.orders[0];user=self.users[0]
        po.with_user(user).sph_review();before=self.snapshot(po|foreign)
        self.denied(lambda:po.with_user(user).write({'company_id':other.id}))
        self.assertEqual(po.company_id,self.env.company)
        self.assertEqual(self.snapshot(po|foreign),before)

    def test_malformed_company_context_fails_closed(self):
        po=self.orders[0].with_user(self.users[0])
        for value in ([],[True],['1'],False):
            self.denied(lambda:po.with_context(allowed_company_ids=value).sph_review())
        for value in (True,False,'1'):
            self.denied(lambda:po.with_context(force_company=value).sph_review())
