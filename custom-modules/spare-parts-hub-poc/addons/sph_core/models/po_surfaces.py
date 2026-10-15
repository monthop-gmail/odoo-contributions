"""PO-linked read surfaces: global rules intersect native ACLs, never grant them."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError


def visible_links(records,operator,value):
    # Evaluated at each ORM search, not an ID list frozen in ir.rule's cache.
    user=records.env.user
    domain=[('company_id','in',list(set(records.env.companies.ids)&set(user.sudo().company_ids.ids)))]
    if not user.has_group('sph_core.group_sph_po_hub'):
        domain.append(('sph_center_id','in',user.sudo().sph_center_ids.ids))
    ids=records.env['purchase.order'].sudo().search(domain).ids
    return [('res_id','in' if (operator=='=' and value) or (operator=='!=' and not value) else 'not in',ids)]


def link_read(records,model_field,parent,*args,**kwargs):
    if records.env.su:return parent(*args,**kwargs)
    linked=records.sudo().exists().filtered(lambda row:row[model_field]=='purchase.order')
    if linked:
        records.env['purchase.order'].browse(linked.mapped('res_id'))._sph_po_scope(action='po.link.read')
    try:return parent(*args,**kwargs)
    except (AccessError,MissingError):
        if linked:return records.env['purchase.order']._sph_po_deny('po.link.read')
        raise


class POLineScope(models.Model):
    _inherit='purchase.order.line'

    @api.model_create_multi
    def create(self,values_list):
        ids=list({values['order_id'] for values in values_list if values.get('order_id')})
        self.env['purchase.order'].browse(ids)._sph_po_scope(action='po.line.create')
        return super().create(values_list)

    def read(self,*args,**kwargs):
        if not self.env.su:
            self.sudo().order_id._sph_po_scope(action='po.line.read')
        return super().read(*args,**kwargs)

    def _search(self,domain,*args,**kwargs):
        if not self.env.su:self.env['purchase.order']._sph_po_scope(action='po.line.search')
        return super()._search(domain,*args,**kwargs)


class POMailScope(models.Model):
    _inherit='mail.message'
    sph_po_visible=fields.Boolean(compute='_compute_sph_po_visible',search='_search_sph_po_visible')

    def _compute_sph_po_visible(self):
        for row in self:row.sph_po_visible=False  # Search-only rule projection.

    def _search_sph_po_visible(self,operator,value):
        return visible_links(self,operator,value)

    def read(self,*args,**kwargs):
        return link_read(self,'model',super().read,*args,**kwargs)


class POAttachmentScope(models.Model):
    _inherit='ir.attachment'
    sph_po_visible=fields.Boolean(compute='_compute_sph_po_visible',search='_search_sph_po_visible')

    def _compute_sph_po_visible(self):
        for row in self:row.sph_po_visible=False

    def _search_sph_po_visible(self,operator,value):
        return visible_links(self,operator,value)

    def read(self,*args,**kwargs):
        return link_read(self,'res_model',super().read,*args,**kwargs)
