"""Original deterministic fixtures, restricted to the disposable sph_poc DB."""
from odoo import api, Command, models
from odoo.exceptions import ValidationError


class SphCenterFixtures(models.Model):
    _inherit = "sph.center"

    @api.model
    def _seed_fixtures(self):
        if self.env.cr.dbname != "sph_poc" or self.env["res.company"].search_count([]) != 1:
            raise ValidationError("FIXTURE seed requires the single-company disposable sph_poc database.")

        def ensure(key, model, values, existing=None):
            record = self.env.ref("sph_core." + key, raise_if_not_found=False)
            if not record:
                record = existing or self.env[model].with_context(no_reset_password=True).create(values)
                self.env["ir.model.data"].create({
                    "module": "sph_core", "name": key, "model": model,
                    "res_id": record.id, "noupdate": True,
                })
            record.write(values)
            return record

        company = ensure("fixture_company", "res.company", {
            "name": "FIXTURE SPH Company", "po_double_validation": "two_step",
            "po_double_validation_amount": 0,
        }, self.env.company)
        central = self.env["stock.warehouse"].search([("company_id", "=", company.id)], limit=1)
        central = ensure("fixture_wh_central", "stock.warehouse", {
            "name": "FIXTURE Central Warehouse", "code": "FXC", "company_id": company.id,
        }, central)
        central.out_type_id.reservation_method = "manual"  # FIXTURE: reserve only through the explicit human operation.
        owned_wh = ensure("fixture_wh_owned", "stock.warehouse", {
            "name": "FIXTURE Owned Warehouse", "code": "FXO", "company_id": company.id,
        })
        shared = ensure("fixture_shared_parent", "res.partner", {
            "name": "FIXTURE Shared Commercial Partner", "is_company": True, "sph_fixture": True,
        })
        centers = {}
        for key, kind, parent in [
            ("owned", "owned", False), ("independent_a", "independent", False),
            ("independent_b", "independent", False), ("shared_a", "independent", shared.id),
            ("shared_b", "independent", shared.id),
        ]:
            partner = ensure("fixture_partner_" + key, "res.partner", {
                "name": "FIXTURE Center " + key, "is_company": not bool(parent),
                "parent_id": parent, "sph_fixture": True, "company_id": company.id,
            })
            center = ensure("fixture_center_" + key, "sph.center", {
                "name": "FIXTURE Center " + key, "center_type": kind,
                "company_id": company.id, "partner_id": partner.id,
                "warehouse_id": owned_wh.id if kind == "owned" else False, "sph_fixture": True,
            })
            partner.sph_center_id = center
            centers[key] = center
        for number in (1, 2):
            ensure(f"fixture_supplier_{number}", "res.partner", {
                "name": f"FIXTURE Supplier {number}", "is_company": True,
                "supplier_rank": 1, "sph_fixture": True,
            })
        tags = [ensure(f"fixture_fitment_{letter}", "sph.fitment.tag", {
            "name": "FIXTURE-MODEL-" + letter, "sph_fixture": True,
        }) for letter in ("A", "B")]
        for number in range(1, 31):
            product = ensure(f"fixture_part_{number:02}", "product.template", {
                "name": f"FIXTURE Part {number:02}", "default_code": f"FIXTURE-PART-{number:02}",
                "type": "consu", "is_storable": True, "tracking": "none",
                "sph_oem_number": f"FIXTURE-OEM-{number:03}",
                "sph_alternate_numbers": f"FIXTURE-ALT-{number:03}; FIXTURE-XREF-{number:03}",
                "sph_fitment_tag_ids": [Command.set([tags[(number - 1) % 2].id])],
                "list_price": 100 + number, "standard_price": 50 + number, "sph_fixture": True,
            })
            variant = product.product_variant_id
            quants = self.env["stock.quant"].search([
                ("product_id", "=", variant.id), ("location_id", "=", central.lot_stock_id.id),
            ])
            if any(quants.mapped("reserved_quantity")):
                raise ValidationError("FIXTURE reseed refuses existing reservations.")
            target = (8, 3, 0, 1)[(number - 1) % 4]
            delta = target - sum(quants.mapped("quantity"))
            if delta:
                self.env["stock.quant"]._update_available_quantity(variant, central.lot_stock_id, delta)
        roles = ("sph_hub_operator", "sph_warehouse_picker", "sph_purchasing_approver",
                 "sph_center_requester", "sph_center_receiver", "sph_bot")
        for role in roles:
            portal = role in ("sph_center_requester", "sph_center_receiver")
            base_group = self.env.ref("base.group_portal" if portal else "base.group_user")
            group = ensure("group_" + role, "res.groups", {
                "name": "FIXTURE " + role, "implied_ids": [Command.set([base_group.id] + ([] if portal else [self.env.ref("sph_core.group_sph_reader").id]))],
            })
            member = centers["independent_a" if role == "sph_center_requester" else "independent_b"]
            user = ensure("fixture_user_" + role, "res.users", {
                "name": "FIXTURE " + role, "login": "fixture_" + role,
                "company_id": company.id, "company_ids": [Command.set([company.id])],
                "group_ids": [Command.set([group.id, base_group.id])],
                "sph_center_ids": [Command.set([member.id] if portal else [])],
            })
            user.partner_id.write({"sph_fixture": True, "company_id": company.id,
                                   "sph_center_id": member.id if portal else False})
