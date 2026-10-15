"""Original deterministic fixtures, restricted to the disposable sph_poc DB."""
from odoo import api, Command, models
from odoo.exceptions import ValidationError


class SphCenterFixtures(models.Model):
    _inherit = "sph.center"

    @api.model
    def _seed_fixtures(self, profile=None):
        if profile != "disposable-test-harness":
            raise ValidationError("FIXTURE seed is harness-only; demo/pilot seed is forbidden.")
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

        # Dedicated native competitor; never widen any SPH role's groups.
        native=ensure("fixture_user_native_actor", "res.users", {
            "name":"FIXTURE Native Stock Actor", "login":"fixture_native_actor",
            "company_id":company.id, "company_ids":[Command.set([company.id])],
            "group_ids":[Command.set([self.env.ref("base.group_user").id,
                self.env.ref("stock.group_stock_manager").id])],
            "sph_center_ids":[Command.clear()],
        })
        native.partner_id.write({"sph_fixture":True,"company_id":company.id})

    @api.model
    def _seed_flow_a(self, profile=None):
        if profile != 'disposable-test-harness' or self.env.cr.dbname != 'sph_poc':
            raise ValidationError('FIXTURE Flow A requires disposable-test-harness / sph_poc only.')
        if self.env['res.company'].search_count([]) != 1:
            raise ValidationError('FIXTURE Flow A requires a single-company harness.')
        if self.env.ref('sph_core.fixture_flow_a_product',raise_if_not_found=False):
            raise ValidationError('FIXTURE Flow A requires a clean harness.')

        def create(key,model,values):
            record=self.env[model].with_context(no_reset_password=True).create(values)
            self.env['ir.model.data'].create({'module':'sph_core','name':'fixture_flow_a_'+key,
                'model':model,'res_id':record.id,'noupdate':True})
            return record

        warehouse=self.env.ref('sph_core.fixture_wh_central')
        product=create('product','product.product',{'name':'FIXTURE FLOW A LAST UNIT',
            'default_code':'FIXTURE-FLOW-A-ONE','type':'consu','is_storable':True,
            'tracking':'none','sph_fixture':True,'list_price':101})
        self.env['stock.quant']._update_available_quantity(product,warehouse.lot_stock_id,1)
        centers=[];reservists=[];requesters=[]
        for label in ('A','B'):
            partner=create('partner_'+label,'res.partner',{'name':'FIXTURE FLOW A CENTER '+label,
                'is_company':True,'sph_fixture':True,'company_id':self.env.company.id})
            center=create('center_'+label,'sph.center',{'name':'FIXTURE FLOW A CENTER '+label,
                'partner_id':partner.id,'center_type':'independent','company_id':self.env.company.id,
                'sph_fixture':True})
            partner.sph_center_id=center
            centers.append(center.id)
            for kind,group in (('reservist','sph_core.group_sph_hub_operator'),
                               ('requester','sph_core.group_sph_center_requester')):
                actor=create(kind+'_'+label,'res.users',{'name':'FIXTURE FLOW A '+kind+' '+label,
                    'login':'fixture_flow_a_'+kind+'_'+label.lower(),
                    'company_id':self.env.company.id,'company_ids':[Command.set(self.env.company.ids)],
                    'group_ids':[Command.set(self.env.ref(group).ids)],
                    'sph_center_ids':[Command.set(center.ids)]})
                actor.partner_id.write({'sph_fixture':True,'sph_center_id':center.id,'company_id':self.env.company.id})
                if kind=='requester': actor.partner_id.parent_id=partner
                if actor.has_group('stock.group_stock_manager'):
                    raise ValidationError('FIXTURE Flow A actors must not have stock-manager authority.')
                (reservists if kind=='reservist' else requesters).append(actor.id)
        return {'centers':centers,'reservists':reservists,'requesters':requesters,
            'product_id':product.id,'location_id':warehouse.lot_stock_id.id,
            'warehouse_id':warehouse.id,'initial_free':1,
            'bot_uid':self.env.ref('sph_core.fixture_user_sph_bot').id,
            'approver_uid':self.env.ref('sph_core.fixture_user_sph_purchasing_approver').id}

    @api.model
    def _seed_flow_b(self, profile=None):
        if (profile != 'disposable-test-harness' or self.env.cr.dbname != 'sph_poc'
                or self.env['res.company'].search_count([]) != 1):
            raise ValidationError('FIXTURE Flow B requires disposable-test-harness / sph_poc / single company.')
        if self.env.ref('sph_core.fixture_flow_b_product',raise_if_not_found=False):
            raise ValidationError('FIXTURE Flow B requires a clean scenario.')
        product=self.env['product.product'].create({'name':'FIXTURE FLOW B SHORTAGE',
            'default_code':'FIXTURE-FLOW-B-ZERO','type':'consu','is_storable':True,
            'tracking':'none','sph_fixture':True,'list_price':101})
        self.env['ir.model.data'].create({'module':'sph_core','name':'fixture_flow_b_product',
            'model':'product.product','res_id':product.id,'noupdate':True})
        partner=self.env['res.partner'].create({'name':'FIXTURE FLOW B CENTER',
            'is_company':True,'sph_fixture':True,'company_id':self.env.company.id})
        center=self.create({'name':'FIXTURE FLOW B CENTER','partner_id':partner.id,
            'center_type':'independent','company_id':self.env.company.id,'sph_fixture':True})
        partner.sph_center_id=center
        actor=self.env['res.users'].with_context(no_reset_password=True).create({
            'name':'FIXTURE FLOW B RESERVIST','login':'fixture_flow_b_reservist',
            'company_id':self.env.company.id,'company_ids':[Command.set(self.env.company.ids)],
            'group_ids':[Command.set(self.env.ref('sph_core.group_sph_hub_operator').ids)],
            'sph_center_ids':[Command.set(center.ids)]})
        actor.partner_id.write({'sph_fixture':True,'sph_center_id':center.id,'company_id':self.env.company.id})
        bot=self.env.ref('sph_core.fixture_user_sph_bot')
        approver=self.env.ref('sph_core.fixture_user_sph_purchasing_approver')
        if any(user.has_group('stock.group_stock_manager') for user in actor|bot|approver):
            raise ValidationError('FIXTURE Flow B must not grant stock-manager authority.')
        warehouse=self.env.ref('sph_core.fixture_wh_central')
        return {'center_id':center.id,'reservist_uid':actor.id,'product_id':product.id,
            'location_id':warehouse.lot_stock_id.id,'warehouse_id':warehouse.id,
            'bot_uid':bot.id,'approver_uid':approver.id,
            'supplier_id':self.env.ref('sph_core.fixture_supplier_1').id}
