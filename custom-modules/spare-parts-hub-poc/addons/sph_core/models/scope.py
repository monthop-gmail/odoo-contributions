"""Global scope rules remain restrictive when native group grants are unioned."""
from odoo import fields, models


class Users(models.Model):
    _inherit = "res.users"

    def write(self, values):
        result = super().write(values)
        if "sph_center_ids" in values:
            self.env.registry.clear_cache()
        return result

    def _sph_scoped(self):
        self.ensure_one()
        return bool(self.sph_center_ids) or self.has_group("base.group_portal") or self.has_group("sph_core.group_sph_bot")


class SaleOrder(models.Model):
    _inherit = "sale.order"

    sph_center_id = fields.Many2one("sph.center", check_company=True, index=True)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    sph_center_id = fields.Many2one(related="order_id.sph_center_id", store=True, index=True)


class Pricelist(models.Model):
    _inherit = "product.pricelist"

    sph_center_id = fields.Many2one("sph.center", check_company=True, index=True)


class Picking(models.Model):
    _inherit = "stock.picking"

    sph_center_id = fields.Many2one("sph.center", check_company=True, index=True)


class Binary(models.AbstractModel):
    _inherit = "ir.binary"

    def _find_record(self, xmlid=None, res_model='ir.attachment', res_id=None,
                     access_token=None, field=None):
        # Check linked SPH order before native attachment/share tokens can sudo it.
        from odoo.exceptions import AccessError
        record = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else (
            self.env[res_model].sudo().browse(res_id).exists() if res_id and res_model in self.env else None)
        document = record
        if record and record._name == 'ir.attachment' and record.res_model == 'sale.order':
            document = self.env['sale.order'].sudo().browse(record.res_id).exists()
        if document and document._name == 'sale.order' and document.sudo().sph_center_id:
            if self.env.user._is_public() or not self.env.user.active:
                raise AccessError('Unavailable')
            document.with_env(self.env).check_access('read')
        return super()._find_record(xmlid, res_model, res_id, access_token, field)
