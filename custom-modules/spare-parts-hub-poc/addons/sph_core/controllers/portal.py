"""Original narrow projections: authorize first, elevate only the stock read."""
import json
from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError
from odoo.addons.sale.controllers.portal import CustomerPortal, PaymentPortal


def protected_document(controller, model_name, document_id, access_token=None):
    document = request.env[model_name].browse(document_id)
    if model_name == "sale.order" and document.sudo().sph_center_id:
        if request.env.user._is_public() or not request.env.user.active:
            raise AccessError("Unavailable")
        document.check_access("read")  # Tokens never substitute for SPH membership.
    return super(type(controller), controller)._document_check_access(
        model_name, document_id, access_token=access_token)


class SphSalePortal(CustomerPortal):
    def _document_check_access(self, model_name, document_id, access_token=None):
        return protected_document(self, model_name, document_id, access_token)


class SphPaymentPortal(PaymentPortal):
    def _document_check_access(self, model_name, document_id, access_token=None):
        return protected_document(self, model_name, document_id, access_token)


class SphPortal(http.Controller):
    @http.route('/sph/band/<int:product_id>', type='http', auth='public', methods=['GET'])
    def band(self, product_id, format='html', **ignored):
        user = request.env.user
        allowed = not user._is_public() and user.active and (
            bool(user.sph_center_ids) or (not user._sph_scoped() and
            user.has_group('sph_core.group_sph_reader')))
        if not allowed:
            return request.make_response('Unavailable', status=403)
        product = request.env['product.product'].sudo().browse(product_id).exists()
        if not product or not product.sph_fixture:
            return request.make_response('Unavailable', status=404)
        # Fixed central location; client center/company/location/context cannot select it.
        location = request.env.ref('sph_core.fixture_wh_central').sudo().lot_stock_id
        quants = request.env['stock.quant'].sudo().search([
            ('product_id', '=', product.id), ('location_id', '=', location.id)])
        free = sum(q.quantity - q.reserved_quantity for q in quants)
        band = 'In stock' if free >= 5 else 'Low' if free > 0 else 'Out'
        if format == 'json':
            return request.make_response(json.dumps({'band': band}),
                headers=[('Content-Type', 'application/json'), ('Cache-Control', 'no-store')])
        return request.make_response('<span>' + band + '</span>',
            headers=[('Content-Type', 'text/html'), ('Cache-Control', 'no-store')])
