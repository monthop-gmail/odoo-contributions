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
    center=env.ref('sph_core.fixture_center_independent_a')
    sale=env['sale.order'].create({'partner_id':center.partner_id.id,'sph_center_id':center.id,
        'order_line':[Command.create({'product_id':product.id,'product_uom_qty':1,'price_unit':105})]})
    location=env.ref('sph_core.fixture_wh_central').lot_stock_id
    quant=env['stock.quant'].search([('product_id','=',product.id),('location_id','=',location.id)],limit=1)
    scrap=env['stock.scrap'].create({'product_id':product.id,'scrap_qty':1,'location_id':location.id})
    return {'bot':bot,'approver':approver,'po':po,'so_line':sale.order_line,'po_line':po.order_line,
            'quant':quant,'scrap':scrap,'supplier':supplier,'product':product}


class TestPurchaseAuthority(TransactionCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.env.company.po_double_validation,'two_step')
        self.assertEqual(self.env.company.po_double_validation_amount,0)
        self.fx=prepare(self.env)

    def deny(self,key,method,*args,**kwargs):
        with self.assertRaises(AccessError):
            getattr(self.fx[key].with_user(self.fx['bot']),method)(*args,**kwargs)

    def allow(self,key,method,*args,**kwargs):
        record=self.fx[key].with_user(self.fx['approver'])
        result=getattr(record,method)(*args,**kwargs)
        self.assertTrue(self.env['sph.authority.audit'].search_count([
            ('res_model','=',record._name),('res_id','=',record.id),('outcome','=','allow')]))
        return result

    def test_ai_prepare_only(self):
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
        self.assertEqual(evidence.revision_digest,self.fx['po']._sph_digest())
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
        with self.assertRaises(AccessError): self.env['purchase.order'].browse(po_id).with_user(actor).sph_review()

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
