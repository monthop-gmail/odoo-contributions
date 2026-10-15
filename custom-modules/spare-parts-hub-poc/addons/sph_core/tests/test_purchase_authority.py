"""G3 transaction tests never inspect independently committed deny rows."""
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


def prepare(env):
    bot=env.ref('sph_core.fixture_user_sph_bot')
    approver=env.ref('sph_core.fixture_user_sph_purchasing_approver')
    product=env.ref('sph_core.fixture_part_05').product_variant_id
    supplier=env.ref('sph_core.fixture_supplier_1')
    po_id=env['purchase.order'].with_user(bot).sph_prepare(supplier.id,product.id)
    po=env['purchase.order'].browse(po_id)
    center=bot.sph_center_ids.ensure_one()
    sale=env['sale.order'].create({'partner_id':center.partner_id.id,'sph_center_id':center.id,
        'order_line':[Command.create({'product_id':product.id,'product_uom_qty':1,'price_unit':105})]})
    location=env.ref('sph_core.fixture_wh_central').lot_stock_id
    quant=env['stock.quant'].search([('product_id','=',product.id),('location_id','=',location.id)],limit=1)
    scrap=env['stock.scrap'].create({'product_id':product.id,'scrap_qty':1,'location_id':location.id})
    pricelist=env['product.pricelist'].create({'name':'FIXTURE alternate authority price','sph_center_id':center.id,'currency_id':env.company.currency_id.id})
    return {'so':sale,'pricelist':pricelist,'bot':bot,'approver':approver,'po':po,'so_line':sale.order_line,'po_line':po.order_line,
            'quant':quant,'scrap':scrap,'supplier':supplier,'product':product}


class TestPurchaseAuthority(TransactionCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.env.company.po_double_validation,'two_step')
        self.assertEqual(self.env.company.po_double_validation_amount,0)
        self.fx=prepare(self.env)

    def deny(self,key,method,*args,**kwargs):
        with self.assertRaisesRegex(AccessError, 'Unavailable'):
            getattr(self.fx[key].with_user(self.fx['bot']),method)(*args,**kwargs)

    def allow(self,key,method,*args,**kwargs):
        record=self.fx[key].with_user(self.fx['approver'])
        result=getattr(record,method)(*args,**kwargs)
        self.assertTrue(self.env['sph.authority.audit'].search_count([
            ('res_model','=',record._name),('res_id','=',record.id),('outcome','=','allow')]))
        return result

    def test_ai_prepare_only(self):
        self.assertEqual(self.fx['bot'].sph_center_ids,self.fx['po'].sph_center_id)
        self.assertEqual(self.fx['approver'].sph_center_ids,self.fx['po'].sph_center_id)
        self.assertEqual(self.fx['po'].state,'draft')
        self.assertEqual(self.fx['po'].sph_maker_uid,self.fx['bot'].id)
        self.assertEqual(self.fx['po'].with_user(self.fx['bot']).sph_draft(quantity=2)['lines'][0]['quantity'],2)

    def test_ai_confirm_approve_force_denied(self):
        self.deny('po','button_confirm')
        self.fx['po'].with_user(self.fx['bot']).button_approve(force=True)
        self.assertEqual(self.fx['po'].state,'draft')

    def test_nonapprover_denied(self):
        with self.assertRaises(AccessError):
            self.fx['po'].with_user(self.env.ref('sph_core.fixture_user_sph_hub_operator')).button_confirm()

    def test_human_confirms_reviewed_revision(self):
        self.allow('po','sph_review')
        self.allow('po','button_confirm')
        self.assertEqual(self.fx['po'].state,'purchase')
        evidence=self.env['sph.authority.audit'].search([('res_model','=','purchase.order'),('res_id','=',self.fx['po'].id),('action','=','po.state')],limit=1)
        self.assertEqual(evidence.revision_digest,self.fx['po'].with_user(self.fx['approver'])._sph_digest())
        self.assertEqual((evidence.before_state,evidence.after_state),('draft','purchase'))

    def test_direct_state_write_and_create_denied(self):
        self.deny('po','write',{'state':'purchase'})
        with self.assertRaises(AccessError):
            self.env['purchase.order'].with_user(self.fx['bot']).create({'partner_id':self.fx['supplier'].id,'state':'purchase'})

    def test_context_actor_cannot_elevate(self):
        with self.assertRaises(AccessError):
            self.fx['po'].with_user(self.fx['bot']).with_context(is_human=True,force=True,sph_internal_stock=True).write({'state':'purchase'})

    def test_ai_group_policy_send_rfq_denied(self):
        self.fx['bot'].group_ids=[Command.link(self.env.ref('purchase.group_purchase_manager').id)]
        self.deny('po','action_rfq_send')
        self.fx['po'].with_user(self.fx['bot']).button_approve(force=True)
        self.assertEqual(self.fx['po'].state,'draft')

    def test_changed_draft_reapproval(self):
        self.allow('po','sph_review')
        self.allow('po_line','write',{'price_unit':109})
        with self.assertRaises(AccessError): self.fx['po'].with_user(self.fx['approver']).button_confirm()
        self.allow('po','sph_review');self.allow('po','button_confirm')

    def test_replay_no_duplicate(self):
        self.allow('po','sph_review');self.allow('po','button_confirm')
        before=self.fx['po'].picking_ids.ids
        self.allow('po','button_confirm')
        self.assertEqual(self.fx['po'].picking_ids.ids,before)

    def test_role_revoke(self):
        self.allow('po','sph_review')
        self.fx['approver'].group_ids=[Command.unlink(self.env.ref('sph_core.group_sph_purchasing_approver').id)]
        with self.assertRaises(AccessError): self.fx['po'].with_user(self.fx['approver']).button_confirm()

    def test_maker_cannot_check(self):
        actor=self.fx['approver']
        po_id=self.env['purchase.order'].with_user(actor).sph_prepare(self.fx['supplier'].id,self.fx['product'].id)
        own=self.env['purchase.order'].browse(po_id).with_user(actor)
        with self.assertRaises(AccessError): own.sph_review()
        with self.assertRaises(AccessError): own.button_approve(force=True)
        with self.assertRaises(AccessError): own.button_confirm()
        self.assertEqual(own.sudo().state,'draft')

    def test_bot_so_price_denied(self): self.deny('so_line','write',{'price_unit':99})
    def test_approver_so_price_allowed(self): self.allow('so_line','write',{'price_unit':99})
    def test_bot_po_price_denied(self): self.deny('po_line','write',{'price_unit':99})
    def test_approver_po_price_allowed(self): self.allow('po_line','write',{'price_unit':99})
    def test_bot_scrap_denied(self): self.deny('scrap','action_validate')
    def test_approver_scrap_allowed(self):
        self.allow('scrap','action_validate');self.assertEqual(self.fx['scrap'].state,'done')
    def test_bot_inventory_denied(self): self.deny('quant','action_apply_inventory')
    def test_approver_inventory_allowed(self):
        self.fx['quant'].with_context(inventory_mode=True).inventory_quantity=7
        self.allow('quant','action_apply_inventory');self.assertEqual(self.fx['quant'].quantity,7)
    def test_bot_quant_write_denied(self): self.deny('quant','write',{'quantity':7})
    def test_approver_quant_write_allowed(self): self.allow('quant','write',{'quantity':7})

    def test_allow_audit_rolls_back_with_action(self):
        before=self.env['sph.authority.audit'].search_count([])
        class RollbackProbe(Exception): pass
        with self.assertRaises(RollbackProbe), self.env.cr.savepoint():
            self.allow('so_line','write',{'price_unit':113})
            raise RollbackProbe()
        self.assertEqual(self.env['sph.authority.audit'].search_count([]),before)

    def price_bot_scope(self):
        # Deliberate native capability union: denial must come from SPH authority,
        # not from a missing ACL or a mismatched center. Rolled back per test.
        bot=self.fx['bot']
        bot.write({'group_ids':[Command.link(self.env.ref('sales_team.group_sale_manager').id)],
            'sph_center_ids':[Command.set(self.fx['so'].sph_center_id.ids)]})
        self.fx['so'].with_user(bot).check_access('write')
        self.fx['so_line'].with_user(bot).check_access('write')

    def test_bot_so_discount_denied(self):
        self.price_bot_scope();self.deny('so_line','write',{'discount':7})
        self.assertEqual(self.fx['so_line'].discount,0)

    def test_approver_so_discount_allowed(self):
        self.allow('so_line','write',{'discount':7})
        self.assertEqual(self.fx['so_line'].discount,7)

    def test_bot_po_discount_denied(self):
        self.deny('po_line','write',{'discount':7})
        self.assertEqual(self.fx['po_line'].discount,0)

    def test_approver_po_discount_allowed(self):
        self.allow('po_line','write',{'discount':7})
        self.assertEqual(self.fx['po_line'].discount,7)

    def test_bot_so_pricelist_denied(self):
        self.price_bot_scope();before=self.fx['so'].pricelist_id
        self.deny('so','write',{'pricelist_id':self.fx['pricelist'].id})
        self.assertEqual(self.fx['so'].pricelist_id,before)

    def test_approver_so_pricelist_allowed(self):
        self.allow('so','write',{'pricelist_id':self.fx['pricelist'].id})
        self.assertEqual(self.fx['so'].pricelist_id,self.fx['pricelist'])

    def test_bot_so_line_create_price_denied(self):
        self.price_bot_scope()
        before=self.env['sale.order.line'].search_count([])
        with self.assertRaisesRegex(AccessError, 'Unavailable'):
            self.env['sale.order.line'].with_user(self.fx['bot']).create({
                'order_id':self.fx['so'].id,'product_id':self.fx['product'].id,
                'product_uom_qty':1,'price_unit':99})
        self.assertEqual(self.env['sale.order.line'].search_count([]),before)

    def test_bot_po_line_create_outside_draft_denied(self):
        before=self.env['purchase.order.line'].search_count([])
        # RPC context flags cannot forge the private server-side draft capability.
        with self.assertRaisesRegex(AccessError, 'Unavailable'):
            self.env['purchase.order.line'].with_user(self.fx['bot']).with_context(
                sph_preparing_draft=True).create({'order_id':self.fx['po'].id,
                'product_id':self.fx['product'].id,'product_qty':1,'price_unit':99})
        self.assertEqual(self.env['purchase.order.line'].search_count([]),before)

    def test_bot_do_scrap_denied(self):
        before=self.fx['quant'].quantity
        self.deny('scrap','do_scrap')
        self.assertEqual(self.fx['scrap'].state,'draft')
        self.assertEqual(self.fx['quant'].quantity,before)

    def test_bot_scrap_done_write_denied(self):
        self.deny('scrap','write',{'state':'done'})
        self.assertEqual(self.fx['scrap'].state,'draft')

    def test_bot_quant_create_denied(self):
        before=self.env['stock.quant'].search_count([])
        with self.assertRaisesRegex(AccessError, 'Unavailable'):
            self.env['stock.quant'].with_user(self.fx['bot']).create({
                'product_id':self.fx['product'].id,
                'location_id':self.fx['quant'].location_id.id,'quantity':1})
        self.assertEqual(self.env['stock.quant'].search_count([]),before)

    def test_bot_update_available_quantity_denied(self):
        before=(self.fx['quant'].quantity,self.fx['quant'].reserved_quantity)
        with self.assertRaisesRegex(AccessError, 'Unavailable'):
            self.env['stock.quant'].with_user(self.fx['bot'])._update_available_quantity(
                self.fx['product'],self.fx['quant'].location_id,quantity=1)
        self.assertEqual((self.fx['quant'].quantity,self.fx['quant'].reserved_quantity),before)

    def test_approver_direct_state_transition_denied(self):
        self.allow('po','sph_review')
        for values in ({'state':'purchase'},{'state':'done'},{'date_approve':'2026-01-01 00:00:00'}):
            with self.assertRaisesRegex(AccessError,'Unavailable'):
                self.fx['po'].with_user(self.fx['approver']).with_context(
                    sph_purchase_transition=True).write(values)
        self.assertEqual(self.fx['po'].state,'draft')
        self.assertFalse(self.fx['po'].picking_ids)
        self.allow('po','button_confirm')
        self.assertEqual(self.fx['po'].state,'purchase')
        self.assertTrue(self.fx['po'].picking_ids)

    def lock_denied(self,key,method,values=None):
        record=self.fx[key]
        before=method in ('action_unlock','button_unlock')
        record.with_user(self.fx['approver']).locked=before
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            getattr(record.with_user(self.fx['bot']),method)(*([values] if values else []))
        self.assertEqual(record.locked,before)

    def lock_allowed(self,key,method,values=None):
        record=self.fx[key]
        record.with_user(self.fx['approver']).locked=method in ('action_unlock','button_unlock')
        self.allow(key,method,*([values] if values else []))
        self.assertEqual(record.locked,method not in ('action_unlock','button_unlock'))

    def test_bot_so_action_lock_locked(self):
        self.lock_denied('so','action_lock')

    def test_approver_so_action_lock_locked(self):
        self.lock_allowed('so','action_lock')

    def test_bot_so_action_unlock_locked(self):
        self.lock_denied('so','action_unlock')

    def test_approver_so_action_unlock_locked(self):
        self.lock_allowed('so','action_unlock')

    def test_bot_so_write_locked(self):
        self.lock_denied('so','write',{'locked':True})

    def test_approver_so_write_locked(self):
        self.lock_allowed('so','write',{'locked':True})

    def test_bot_po_button_lock_locked(self):
        self.lock_denied('po','button_lock')

    def test_approver_po_button_lock_locked(self):
        self.lock_allowed('po','button_lock')

    def test_bot_po_button_unlock_locked(self):
        self.lock_denied('po','button_unlock')

    def test_approver_po_button_unlock_locked(self):
        self.lock_allowed('po','button_unlock')

    def test_bot_po_write_locked(self):
        self.lock_denied('po','write',{'locked':True})

    def test_approver_po_write_locked(self):
        self.lock_allowed('po','write',{'locked':True})

    def test_approver_so_locked_bundle_denied(self):
        record=self.fx['so']
        before=record.partner_id
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            try:
                record.with_user(self.fx['approver']).write({'locked':True,'partner_id':self.fx['supplier'].id})
            except AccessError:
                self.assertTrue(self.env['sph.authority.audit'].search_count([
                    ('res_model','=',record._name),('res_id','=',record.id),
                    ('actor_uid','=',self.fx['approver'].id),
                    ('action','=',record._name+'.locked.bundle'),('outcome','=','deny')]))
                raise
        self.assertFalse(record.locked)
        self.assertEqual(record.partner_id,before)

    def test_approver_po_locked_bundle_denied(self):
        record=self.fx['po']
        before=record.partner_id
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            try:
                record.with_user(self.fx['approver']).write({'locked':True,'partner_id':self.fx['supplier'].id})
            except AccessError:
                self.assertTrue(self.env['sph.authority.audit'].search_count([
                    ('res_model','=',record._name),('res_id','=',record.id),
                    ('actor_uid','=',self.fx['approver'].id),
                    ('action','=',record._name+'.locked.bundle'),('outcome','=','deny')]))
                raise
        self.assertFalse(record.locked)
        self.assertEqual(record.partner_id,before)

    def test_incident_so_field(self):
        self.assertEqual(self.env['sale.order']._fields['sph_incident_ref'].type,'char')
        self.assertFalse(self.env['sale.order']._fields['sph_incident_ref'].copy)

    def test_incident_so_human_allowed(self):
        self.allow('so','write',{'sph_incident_ref':'fixture:incident:001'})
        self.assertEqual(self.fx['so'].sph_incident_ref,'fixture:incident:001')
        self.assertTrue(self.env['sph.authority.audit'].search_count([('res_model','=','sale.order'),('res_id','=',self.fx['so'].id),('action','=','incident.reference'),('outcome','=','allow'),('incident_ref','=','fixture:incident:001')]))

    def test_incident_so_bot_denied(self):
        self.deny('so','write',{'sph_incident_ref':'fixture:incident:bot'})
        self.assertFalse(self.fx['so'].sph_incident_ref)

    def test_incident_so_bundle_denied(self):
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            self.fx['so'].with_user(self.fx['approver']).write({'sph_incident_ref':'fixture:incident:001','partner_id':self.fx['supplier'].id})
        self.assertFalse(self.fx['so'].sph_incident_ref)

    def test_incident_so_create_denied(self):
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            self.env['sale.order'].with_user(self.fx['bot']).create({'partner_id':self.fx['supplier'].id,'sph_incident_ref':'fixture:incident:bot'})

    def test_incident_po_field(self):
        self.assertEqual(self.env['purchase.order']._fields['sph_incident_ref'].type,'char')
        self.assertFalse(self.env['purchase.order']._fields['sph_incident_ref'].copy)

    def test_incident_po_human_allowed(self):
        self.allow('po','write',{'sph_incident_ref':'fixture:incident:001'})
        self.assertEqual(self.fx['po'].sph_incident_ref,'fixture:incident:001')
        self.assertTrue(self.env['sph.authority.audit'].search_count([('res_model','=','purchase.order'),('res_id','=',self.fx['po'].id),('action','=','incident.reference'),('outcome','=','allow'),('incident_ref','=','fixture:incident:001')]))

    def test_incident_po_bot_denied(self):
        self.deny('po','write',{'sph_incident_ref':'fixture:incident:bot'})
        self.assertFalse(self.fx['po'].sph_incident_ref)

    def test_incident_po_bundle_denied(self):
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            self.fx['po'].with_user(self.fx['approver']).write({'sph_incident_ref':'fixture:incident:001','partner_id':self.fx['supplier'].id})
        self.assertFalse(self.fx['po'].sph_incident_ref)

    def test_incident_po_create_denied(self):
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            self.env['purchase.order'].with_user(self.fx['bot']).create({'partner_id':self.fx['supplier'].id,'sph_incident_ref':'fixture:incident:bot'})

    def test_incident_scope_and_clear(self):
        self.allow('so','write',{'sph_incident_ref':'fixture:incident:clear'})
        self.allow('so','write',{'sph_incident_ref':False})
        self.assertFalse(self.fx['so'].sph_incident_ref)
        self.fx['approver'].sph_center_ids=[Command.set(self.env.ref('sph_core.fixture_center_shared_b').ids)]
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            self.fx['so'].with_user(self.fx['approver']).write({'sph_incident_ref':'fixture:incident:foreign'})
        self.assertFalse(self.fx['so'].sph_incident_ref)

    def test_incident_rejects_urls_and_free_text(self):
        from odoo.exceptions import UserError
        for value in ('https://invalid.example/incident','FIXTURE incident text','x'*129):
            with self.assertRaisesRegex(UserError,'^Unavailable$'):
                self.fx['po'].with_user(self.fx['approver']).write({'sph_incident_ref':value})
        self.assertFalse(self.fx['po'].sph_incident_ref)

    def test_incident_po_company_denied(self):
        other=self.env['res.company'].create({'name':'FIXTURE foreign incident company'})
        foreign_center=self.env['sph.center'].create({'name':'FIXTURE foreign PO center',
            'center_type':'independent','company_id':other.id,'partner_id':self.env['res.partner'].create({
                'name':'FIXTURE foreign PO partner','company_id':other.id}).id})
        self.env.user.company_ids=[Command.link(other.id)]
        self.env.user.sph_center_ids=[Command.set(foreign_center.ids)]
        po=self.env['purchase.order'].with_company(other).create({
            'partner_id':self.fx['supplier'].id,'company_id':other.id})
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            po.with_user(self.fx['approver']).with_context(allowed_company_ids=self.fx['approver'].company_ids.ids).write({
                'sph_incident_ref':'fixture:incident:foreign-company'})
        self.assertFalse(po.sph_incident_ref)

    def test_bot_hub_and_native_group_union_denied(self):
        bot=self.fx['bot']
        bot.group_ids=[Command.link(self.env.ref(xmlid).id) for xmlid in (
            'sph_core.group_sph_po_hub','sph_core.group_sph_purchasing_approver',
            'purchase.group_purchase_manager','stock.group_stock_manager')]
        self.assertEqual(bot.sph_center_ids,self.fx['po'].sph_center_id)
        self.fx['po'].with_user(bot).check_access('read')
        for method in ('sph_review','button_confirm','action_rfq_send'):
            self.deny('po',method)
        self.deny('po','write',{'state':'purchase'})
        self.deny('po','write',{'sph_incident_ref':'fixture:union'})
        self.fx['po'].with_user(bot).button_approve(force=True)
        self.assertEqual(self.fx['po'].state,'draft')
        self.assertFalse(self.fx['po'].sph_review_digest)
        self.assertFalse(self.fx['po'].picking_ids)
