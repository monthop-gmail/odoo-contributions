from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestSPHFixtures(TransactionCase):
    def fixture(self, key):
        return self.env.ref("sph_core.fixture_" + key)

    def test_oem_alternate_search(self):
        template = self.fixture("part_01")
        for model in ("product.template", "product.product"):
            expected = template if model == "product.template" else template.product_variant_id
            for token in ("FIXTURE-OEM-001", "FIXTURE-ALT-001", "FIXTURE-XREF-001"):
                found = self.env[model].search([("display_name", "ilike", token)])
                self.assertEqual(found, expected)
            excluded = self.env[model].search([("display_name", "not ilike", "FIXTURE-ALT-001")])
            self.assertNotIn(expected, excluded)
        self.assertEqual(template.sph_fitment_tag_ids.name, "FIXTURE-MODEL-A")

    def test_seed_organization_and_roles(self):
        self.assertEqual(self.env["res.company"].search_count([]), 1)
        self.assertEqual(self.env["stock.warehouse"].search_count([]), 2)
        self.assertEqual(self.env["sph.center"].search_count([("sph_fixture", "=", True)]), 5)
        a, b = self.fixture("center_shared_a"), self.fixture("center_shared_b")
        self.assertNotEqual(a, b)
        self.assertNotEqual(a.partner_id, b.partner_id)
        self.assertEqual(a.partner_id.commercial_partner_id, b.partner_id.commercial_partner_id)
        self.assertEqual(self.fixture("center_owned").warehouse_id, self.fixture("wh_owned"))
        self.assertFalse(a.warehouse_id)
        self.assertEqual(self.env["res.partner"].search_count([
            ("sph_fixture", "=", True), ("supplier_rank", ">", 0)]), 2)
        roles = ("sph_hub_operator", "sph_warehouse_picker", "sph_purchasing_approver",
                 "sph_center_requester", "sph_center_receiver", "sph_bot")
        self.assertEqual(self.env["res.users"].search_count([("login", "=like", "fixture_sph_%")]), 6)
        for role in roles:
            user = self.fixture("user_" + role)
            self.assertTrue(user.has_group("sph_core.group_" + role))
            self.assertFalse(user.has_group("base.group_system"))
            if role in ("sph_center_requester", "sph_center_receiver"):
                self.assertTrue(user.has_group("base.group_portal"))
                self.assertEqual(user.sph_center_ids, user.partner_id.sph_center_id)
        self.assertFalse(self.fixture("user_sph_bot").has_group("purchase.group_purchase_manager"))

    def test_seed_purchase_and_stock(self):
        company = self.fixture("company")
        self.assertEqual(company.po_double_validation, "two_step")
        self.assertEqual(company.po_double_validation_amount, 0)
        parts = self.env["product.template"].search([("sph_fixture", "=", True)])
        self.assertEqual(len(parts), 30)
        self.assertTrue(all(p.name.startswith("FIXTURE ") and p.tracking == "none" for p in parts))
        central = self.fixture("wh_central").lot_stock_id
        for number, quantity in ((1, 8), (2, 3), (3, 0), (4, 1)):
            variant = self.fixture(f"part_{number:02}").product_variant_id
            quants = self.env["stock.quant"].search([
                ("product_id", "=", variant.id), ("location_id", "=", central.id)])
            self.assertEqual(sum(quants.mapped("quantity")), quantity)
            self.assertFalse(any(quants.mapped("reserved_quantity")))

    def test_center_mapping_validation(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.fixture("center_owned").warehouse_id = False
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.fixture("center_independent_a").warehouse_id = self.fixture("wh_owned")

    def test_fixture_reseed_is_idempotent(self):
        references = [self.fixture(key).id for key in ("part_01", "center_owned", "user_sph_bot")]
        self.env["sph.center"]._seed_fixtures(profile="disposable-test-harness")
        self.assertEqual(references, [self.fixture(key).id for key in (
            "part_01", "center_owned", "user_sph_bot")])
        self.test_seed_purchase_and_stock()

    def test_native_actor_does_not_expand_picker(self):
        native=self.fixture('user_native_actor')
        picker=self.fixture('user_sph_warehouse_picker')
        self.assertNotEqual(native,picker)
        self.assertTrue(native.has_group('stock.group_stock_manager'))
        self.assertFalse(native.has_group('sph_core.group_sph_reader'))
        self.assertFalse(picker.has_group('stock.group_stock_manager'))

    def test_native_actor_seed_rejects_demo_pilot(self):
        seed=self.env['sph.center']
        before=self.env['res.users'].search_count([])
        for profile in (None,'demo','pilot'):
            with self.assertRaisesRegex(ValidationError,'harness-only'):
                seed._seed_fixtures(profile=profile)
        self.assertEqual(self.env['res.users'].search_count([]),before)
        self.assertTrue(self.fixture('user_native_actor').has_group('stock.group_stock_manager'))
