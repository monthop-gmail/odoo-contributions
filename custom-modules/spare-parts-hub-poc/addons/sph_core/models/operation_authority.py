from odoo import api, models
from odoo.exceptions import AccessError
from .authority import approver, audit, internal_stock, _INTERNAL, _DRAFT


def price_write(records, values, parent):
    if 'price_unit' not in values or records.env.uid == 1:
        return parent(records).write(values)
    approver(records,records._name+'.price_unit')
    result=parent(records.sudo()).write(values)
    audit(records,records._name+'.price_unit','allow')
    return result


class SalePrice(models.Model):
    _inherit='sale.order.line'
    @api.model_create_multi
    def create(self, values_list):
        if self.env.uid != 1 and any('price_unit' in values for values in values_list):
            approver(self,'sale.order.line.price_unit')
        records=super().create(values_list)
        if self.env.uid != 1 and any('price_unit' in values for values in values_list):
            audit(records,'sale.order.line.price_unit','allow')
        return records
    def write(self, values):
        return price_write(self,values,lambda record:super(SalePrice,record))


class PurchasePrice(models.Model):
    _inherit='purchase.order.line'
    @api.model_create_multi
    def create(self, values_list):
        if self.env.uid != 1 and not _DRAFT.get() and any('price_unit' in values for values in values_list):
            approver(self,'purchase.order.line.price_unit')
        records=super().create(values_list)
        if self.env.uid != 1 and not _DRAFT.get() and any('price_unit' in values for values in values_list):
            audit(records,'purchase.order.line.price_unit','allow')
        return records
    def write(self, values):
        if self.env.uid != 1 and self.env.user.has_group('sph_core.group_sph_bot') and any(line.sudo().order_id.state != 'draft' for line in self):
            audit(self,'po.line.write','deny');raise AccessError('Unavailable')
        return price_write(self,values,lambda record:super(PurchasePrice,record))


class ScrapAuthority(models.Model):
    _inherit='stock.scrap'
    def action_validate(self):
        approver(self,'scrap.validate')
        with internal_stock(): result=super(ScrapAuthority,self.sudo()).action_validate()
        audit(self,'scrap.validate','allow')
        return result
    def do_scrap(self):
        approver(self,'scrap.validate')
        with internal_stock(): result=super(ScrapAuthority,self.sudo()).do_scrap()
        audit(self,'scrap.validate','allow')
        return result
    def write(self, values):
        if values.get('state') == 'done': approver(self,'scrap.validate')
        return super().write(values)


class QuantAuthority(models.Model):
    _inherit='stock.quant'
    @api.model
    def _update_available_quantity(self, product_id, location_id, quantity=False, reserved_quantity=False, **kwargs):
        if self.env.uid != 1 and self.env.user.has_group('sph_core.group_sph_bot'):
            audit(self,'quant.native','deny');raise AccessError('Unavailable')
        with internal_stock():
            return super()._update_available_quantity(product_id,location_id,quantity=quantity,
                reserved_quantity=reserved_quantity,**kwargs)
    def write(self, values):
        protected={'quantity','reserved_quantity','inventory_quantity','inventory_diff_quantity'} & values.keys()
        if protected and self.env.uid != 1 and not _INTERNAL.get():
            approver(self,'quant.write')
            result=super(QuantAuthority,self.sudo()).write(values)
            audit(self,'quant.write','allow')
            return result
        return super().write(values)
    @api.model_create_multi
    def create(self, values_list):
        if self.env.uid != 1 and self.env.user.has_group('sph_core.group_sph_bot'):
            audit(self,'quant.create','deny');raise AccessError('Unavailable')
        return super().create(values_list)
    def action_apply_inventory(self, date=None):
        approver(self,'inventory.apply')
        with internal_stock(): result=super(QuantAuthority,self.sudo()).action_apply_inventory(date=date)
        audit(self,'inventory.apply','allow')
        return result


class BotPicking(models.Model):
    _inherit='stock.picking'
    def action_assign(self):
        if self.env.uid != 1 and self.env.user.has_group('sph_core.group_sph_bot'):
            audit(self,'stock.assign','deny');raise AccessError('Unavailable')
        return super().action_assign()
    def button_validate(self):
        if self.env.uid != 1 and self.env.user.has_group('sph_core.group_sph_bot'):
            audit(self,'stock.validate','deny');raise AccessError('Unavailable')
        return super().button_validate()
