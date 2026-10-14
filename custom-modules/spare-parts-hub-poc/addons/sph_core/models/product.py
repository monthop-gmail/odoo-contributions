from odoo import api, fields, models
from odoo.fields import Domain


def identifier_domain(base, operator, value):
    if not isinstance(value, str) or not value:
        return base
    terms = [base, [("sph_oem_number", operator, value)], [("sph_alternate_numbers", operator, value)]]
    return Domain.AND(terms) if operator in Domain.NEGATIVE_OPERATORS else Domain.OR(terms)


class SphFitmentTag(models.Model):
    _name = "sph.fitment.tag"
    _description = "SPH illustrative fitment tag"

    name = fields.Char(required=True, index=True)
    sph_fixture = fields.Boolean(default=False, readonly=True)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    sph_oem_number = fields.Char(string="OEM number", index=True)
    sph_alternate_numbers = fields.Char(string="Alternate numbers", index=True)
    sph_fitment_tag_ids = fields.Many2many("sph.fitment.tag", string="Illustrative fitment tags")
    sph_fixture = fields.Boolean(default=False, readonly=True)

    @api.model
    def _search_display_name(self, operator, value):
        return identifier_domain(super()._search_display_name(operator, value), operator, value)


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _search_display_name(self, operator, value):
        return identifier_domain(super()._search_display_name(operator, value), operator, value)


# Product aggregate computations can sudo quants internally. Protect these fields
# even if an SPH-scoped principal acquires a native inventory/sales group.
PROTECTED_CONTEXT_FIELDS = frozenset({
    'standard_price', 'list_price', 'qty_available', 'virtual_available', 'free_qty',
    'incoming_qty', 'outgoing_qty', 'stock_quant_ids', 'stock_move_ids', 'orderpoint_ids',
})


class ScopedProductTemplate(models.Model):
    _inherit = 'product.template'

    def _has_field_access(self, field, operation):
        if not self.env.su and self.env.user._sph_scoped() and field.name in PROTECTED_CONTEXT_FIELDS:
            return False
        return super()._has_field_access(field, operation)


class ScopedProductProduct(models.Model):
    _inherit = 'product.product'

    def _has_field_access(self, field, operation):
        if not self.env.su and self.env.user._sph_scoped() and field.name in PROTECTED_CONTEXT_FIELDS:
            return False
        return super()._has_field_access(field, operation)
