import hashlib
import json
from odoo import api, fields, models
from odoo.exceptions import AccessError
from .authority import approver, audit


class PurchaseAuthority(models.Model):
    _inherit='purchase.order'
    sph_maker_uid=fields.Integer(readonly=True,copy=False)
    sph_reviewer_uid=fields.Integer(readonly=True,copy=False)
    sph_review_digest=fields.Char(readonly=True,copy=False)

    def _sph_digest(self):
        self.ensure_one()
        order=self.sudo()
        payload=[order.partner_id.id,order.currency_id.id,order.company_id.id,
            [(line.product_id.id,line.product_qty,line.price_unit) for line in order.order_line.sorted('id')]]
        return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

    @api.model_create_multi
    def create(self, values_list):
        for values in values_list:
            if values.get('state','draft') != 'draft' or any(key in values for key in ('sph_maker_uid','sph_review_digest','sph_reviewer_uid')):
                raise AccessError('Unavailable')
            values['sph_maker_uid']=self.env.uid
        return super().create(values_list)

    @api.model
    def sph_prepare(self, supplier_id, product_id, quantity=1):
        user=self.env.user
        if not (user.has_group('sph_core.group_sph_bot') or user.has_group('sph_core.group_sph_purchasing_approver') or user.has_group('sph_core.group_sph_hub_operator')):
            raise AccessError('Unavailable')
        supplier=self.env['res.partner'].sudo().browse(supplier_id).exists()
        product=self.env['product.product'].sudo().browse(product_id).exists()
        if not supplier or not supplier.sph_fixture or not product or not product.sph_fixture or quantity<=0:
            raise AccessError('Unavailable')
        order=self.sudo().create({'partner_id':supplier.id,'order_line':[(0,0,{
            'product_id':product.id,'product_qty':quantity,'price_unit':101})]})
        return order.id

    def sph_review(self):
        approver(self,'po.review',maker=True)
        for order in self.sudo():
            order.write({'sph_review_digest':order._sph_digest(),'sph_reviewer_uid':self.env.uid})
        audit(self,'po.review','allow')
        return True

    def _sph_check_review(self):
        approver(self,'po.approve',maker=True)
        for order in self.sudo():
            if (order.company_id.po_double_validation != 'two_step' or order.company_id.po_double_validation_amount != 0 or
                order.sph_reviewer_uid != self.env.uid or order.sph_review_digest != order._sph_digest()):
                audit(self,'po.approve','deny')
                raise AccessError('Unavailable')

    def _approval_allowed(self):
        if self.env.user.has_group('sph_core.group_sph_purchasing_approver') and not self.env.user.has_group('sph_core.group_sph_bot'):
            self._sph_check_review()
            return True
        return super()._approval_allowed()

    def button_confirm(self):
        self._sph_check_review()
        result=super(PurchaseAuthority,self.sudo()).button_confirm()
        audit(self,'po.confirm','allow')
        return result

    def button_approve(self, force=False):
        if self.env.user.has_group('sph_core.group_sph_bot'):
            audit(self,'po.approve','deny')
            return {}  # Assert unchanged state; a silent native-style refusal.
        self._sph_check_review()
        result=super(PurchaseAuthority,self.sudo()).button_approve(force=force)
        audit(self,'po.approve','allow')
        return result

    def write(self, values):
        if {'sph_maker_uid'} & values.keys():
            audit(self,'po.identity','deny');raise AccessError('Unavailable')
        if {'sph_review_digest','sph_reviewer_uid'} & values.keys():
            approver(self,'po.review',maker=True)
            if not self.env.su: raise AccessError('Unavailable')
        if values.get('state') in ('purchase','done') or 'date_approve' in values:
            self._sph_check_review()
        if self.env.user.has_group('sph_core.group_sph_bot') and (
            any(order.sudo().state != 'draft' for order in self) or values.get('state','draft') != 'draft'):
            audit(self,'po.write','deny');raise AccessError('Unavailable')
        result=super().write(values)
        if values.get('state') == 'purchase': audit(self,'po.state','allow')
        return result

    def action_rfq_send(self):
        approver(self,'po.send',maker=True)
        return super().action_rfq_send()
