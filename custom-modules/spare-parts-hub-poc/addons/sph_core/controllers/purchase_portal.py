"""An Odoo purchase share token never substitutes for SPH center membership."""
from odoo.http import request
from odoo.addons.purchase.controllers.portal import CustomerPortal


class SphPurchasePortal(CustomerPortal):
    def _document_check_access(self,model_name,document_id,access_token=None):
        if model_name=='purchase.order':
            request.env[model_name].browse(document_id)._sph_po_scope(action='po.portal')
        return super()._document_check_access(model_name,document_id,access_token)
