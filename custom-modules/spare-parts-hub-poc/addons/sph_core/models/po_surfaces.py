"""PO-linked read surfaces: global rules intersect native ACLs, never grant them."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError


def visible_po_ids(records):
    user=records.env.user
    domain=[('company_id','=',records.env['purchase.order']._sph_po_company('po.scope'))]
    if not user.has_group('sph_core.group_sph_po_hub'):
        domain.append(('sph_center_id','in',user.sudo().sph_center_ids.ids))
    return records.env['purchase.order'].sudo().search(domain).ids


def visible_links(records,operator,value):
    # Evaluated at each ORM search, not an ID list frozen in ir.rule's cache.
    ids=visible_po_ids(records)
    # Odoo 19 normalizes Boolean comparisons to in/not in lists.
    positive=bool(value) if operator in ('=','!=') else True in value
    if operator in ('!=','not in'):positive=not positive
    return [('res_id','in' if positive else 'not in',ids)]


def compute_visibility(records,model_field):
    allowed=set(visible_po_ids(records))
    for row in records:
        linked=row.sudo()
        row.sph_po_visible=linked[model_field]!='purchase.order' or linked.res_id in allowed


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
        if not self.env.su:
            self.env['purchase.order']._sph_po_scope(action='po.line.search')
            domain=[('order_id.company_id','=',self.env['purchase.order']._sph_po_company('po.line.search'))]+list(domain)
        return super()._search(domain,*args,**kwargs)


class POMailScope(models.Model):
    _inherit='mail.message'
    sph_po_visible=fields.Boolean(compute='_compute_sph_po_visible',search='_search_sph_po_visible')

    @api.depends_context('uid','allowed_company_ids')
    def _compute_sph_po_visible(self):
        compute_visibility(self,'model')

    def _search_sph_po_visible(self,operator,value):
        return visible_links(self,operator,value)

    def read(self,*args,**kwargs):
        return link_read(self,'model',super().read,*args,**kwargs)


class POAttachmentScope(models.Model):
    _inherit='ir.attachment'
    sph_po_visible=fields.Boolean(compute='_compute_sph_po_visible',search='_search_sph_po_visible')

    @api.depends_context('uid','allowed_company_ids')
    def _compute_sph_po_visible(self):
        compute_visibility(self,'res_model')

    def _search_sph_po_visible(self,operator,value):
        return visible_links(self,operator,value)

    def read(self,*args,**kwargs):
        return link_read(self,'res_model',super().read,*args,**kwargs)


class POBinaryScope(models.AbstractModel):
    _inherit='ir.binary'

    def _find_record(self,xmlid=None,res_model='ir.attachment',res_id=None,access_token=None,field=None):
        candidate=self.env.ref(xmlid,raise_if_not_found=False) if xmlid else (
            self.env[res_model].browse(res_id) if res_model in self.env and res_id else None)
        if candidate and candidate._name=='purchase.order':
            candidate._sph_po_scope(action='po.binary')
        elif candidate and candidate._name=='ir.attachment':
            attachment=candidate.sudo().exists()
            if not attachment:return self.env['purchase.order']._sph_po_deny('po.binary')
            if attachment.res_model=='purchase.order':
                self.env['purchase.order'].browse(attachment.res_id)._sph_po_scope(action='po.binary')
        return super()._find_record(xmlid=xmlid,res_model=res_model,res_id=res_id,
            access_token=access_token,field=field)


class POProjectionUsers(models.Model):
    _inherit='res.users'

    def write(self,values):
        result=super().write(values)
        if {'sph_center_ids','group_ids','company_ids','company_id'} & values.keys():
            # A field cache must not retain visibility after membership/grant revoke.
            for name in ('mail.message','ir.attachment'):
                self.env[name].invalidate_model(['sph_po_visible'])
        return result
