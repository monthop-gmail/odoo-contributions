"""Global scope rules remain restrictive when native group grants are unioned."""
from odoo import fields, models


class Users(models.Model):
    _inherit = "res.users"

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
