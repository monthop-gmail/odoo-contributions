from odoo import release
from odoo.tests.common import TransactionCase


class TestSPHSkeleton(TransactionCase):
    def test_odoo19_community_dependency_registry(self):
        self.assertEqual(release.version_info[0], 19)
        for model in ("stock.quant", "purchase.order", "sale.order", "portal.mixin"):
            self.assertIn(model, self.env.registry.models)
        enterprise = self.env["ir.module.module"].search_count(
            [("name", "=", "web_enterprise"), ("state", "=", "installed")]
        )
        self.assertEqual(enterprise, 0)
