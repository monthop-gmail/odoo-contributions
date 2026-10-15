"""Reject stale evidence and distinguish unmet demand from native backorders."""
import unittest
from dashboard import calculate


class TestDashboard(unittest.TestCase):
    def source(self,requested=2,reserved=1):
        return {'A':{'commit':'fixture-sha','measurements':{'existing_sales_before':0,
            'orders':[{'so_id':1,'state':'sale','requested_qty':requested,'reserved_qty':reserved}],
            'stockout_so_ids':[1],'backorder_picking_ids':[]}}}

    def test_rejects_mixed_commit(self):
        with self.assertRaisesRegex(ValueError,'mixed commit'):
            calculate(self.source(),'different-sha')

    def test_rejects_unclean_epoch(self):
        source=self.source();source['A']['measurements']['existing_sales_before']=3
        with self.assertRaisesRegex(ValueError,'clean scenario'):
            calculate(source,'fixture-sha')

    def test_zero_demand_is_unknown(self):
        data=calculate(self.source(0,0),'fixture-sha')
        self.assertIsNone(data['metrics']['fill_rate'])

    def test_unmet_demand_is_not_native_backorder(self):
        data=calculate(self.source(),'fixture-sha')
        self.assertEqual(data['metrics']['open_blockers'],1)
        self.assertEqual(data['metrics']['backorders'],0)
