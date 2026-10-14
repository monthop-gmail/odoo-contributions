from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SphCenter(models.Model):
    _name = "sph.center"
    _description = "SPH center (provisional organization mapping)"
    _check_company_auto = True

    name = fields.Char(required=True)
    center_type = fields.Selection([("owned", "Owned"), ("independent", "Independent")], required=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict", check_company=True)
    warehouse_id = fields.Many2one("stock.warehouse", ondelete="restrict", check_company=True)
    sph_fixture = fields.Boolean(default=False, readonly=True)

    @api.constrains("center_type", "warehouse_id", "company_id")
    def _check_warehouse_mapping(self):
        for center in self:
            if center.center_type == "owned" and not center.warehouse_id:
                raise ValidationError("Owned centers require a warehouse mapping.")
            if center.center_type == "independent" and center.warehouse_id:
                raise ValidationError("Independent centers do not own a demo warehouse.")


class ResPartner(models.Model):
    _inherit = "res.partner"

    sph_center_id = fields.Many2one("sph.center", ondelete="restrict", check_company=True)
    sph_fixture = fields.Boolean(default=False, readonly=True)


class ResUsers(models.Model):
    _inherit = "res.users"

    sph_center_ids = fields.Many2many("sph.center", string="Explicit SPH center memberships")
