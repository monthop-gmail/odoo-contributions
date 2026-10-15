from odoo import api, models
from odoo.exceptions import AccessError
from .authority import approver, audit, internal_stock, _INTERNAL, _DRAFT


PROTECTED_PRICE_FIELDS=('price_unit','discount','pricelist_id')


def price_write(records, values, parent):
    protected=[key for key in PROTECTED_PRICE_FIELDS if key in values]
    if not protected or records.env.uid == 1:
        return parent(records).write(values)
    for key in protected:
        approver(records,records._name+'.'+key)
    result=parent(records.sudo()).write(values)
    for key in protected:
        audit(records,records._name+'.'+key,'allow')
    return result


def price_create(records, values_list, parent, internal=False):
    protected=[key for key in PROTECTED_PRICE_FIELDS if any(key in values for values in values_list)]
    guarded=records.env.uid != 1 and not internal
    if guarded:
        for key in protected: approver(records,records._name+'.'+key)
    created=parent(records).create(values_list)
    if guarded:
        for key in protected: audit(created,records._name+'.'+key,'allow')
    return created


class SalePrice(models.Model):
    _inherit='sale.order.line'
    @api.model_create_multi
    def create(self, values_list):
        return price_create(self,values_list,lambda record:super(SalePrice,record))
    def write(self, values):
        return price_write(self,values,lambda record:super(SalePrice,record))


class PurchasePrice(models.Model):
    _inherit='purchase.order.line'
    @api.model_create_multi
    def create(self, values_list):
        return price_create(self,values_list,lambda record:super(PurchasePrice,record),internal=_DRAFT.get())
    def write(self, values):
        if self.env.uid != 1 and self.env.user.has_group('sph_core.group_sph_bot') and any(line.sudo().order_id.state != 'draft' for line in self):
            audit(self,'po.line.write','deny');raise AccessError('Unavailable')
        return price_write(self,values,lambda record:super(PurchasePrice,record))


class SalePricelist(models.Model):
    _inherit='sale.order'
    def write(self, values):
        return price_write(self,values,lambda record:super(SalePricelist,record))


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
