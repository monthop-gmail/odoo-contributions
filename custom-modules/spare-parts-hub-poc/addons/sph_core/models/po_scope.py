"""PO ownership gate; no empty-membership fallthrough or native ACL grant."""
from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError
from .authority import audit

CENTER_CONTEXT={'sph_center_id','center_id','default_sph_center_id','default_center_id'}


class PurchaseScope(models.Model):
    _inherit='purchase.order'
    sph_center_id=fields.Many2one('sph.center',required=True,readonly=True,copy=False,
        check_company=True,index=True,ondelete='restrict')

    def _sph_po_deny(self,action='po.scope'):
        audit(self.browse(),action,'deny')
        raise AccessError('Unavailable') from None

    def _sph_po_scope(self,creating=False,company_id=None,action='po.scope'):
        """Central center/company hook; remaining capabilities are B7b/B7c."""
        actor=self.env.user
        centers=actor.sudo().sph_center_ids
        try:
            companies=set(self.env.companies.ids)&set(actor.sudo().company_ids.ids)
        except AccessError:
            return self._sph_po_deny(action)
        if not companies:return self._sph_po_deny(action)
        if creating:
            if CENTER_CONTEXT.intersection(self.env.context) or len(centers)!=1:
                return self._sph_po_deny('po.owner')
            company_id=company_id or self.env.company.id
            if company_id not in companies or centers.company_id.id!=company_id:
                return self._sph_po_deny('po.owner')
            return centers
        if CENTER_CONTEXT.intersection(self.env.context):return self._sph_po_deny(action)
        hub=actor.has_group('sph_core.group_sph_po_hub')
        if not hub and not centers:return self._sph_po_deny(action)
        if self.ids:
            domain=[('id','in',self.ids),('company_id','in',list(companies))]
            if not hub:domain.append(('sph_center_id','in',centers.ids))
            if len(self.sudo().search(domain))!=len(self):return self._sph_po_deny(action)
        return True

    @api.model_create_multi
    def create(self,values_list):
        prepared=[]
        for values in values_list:
            if 'sph_center_id' in values:return self._sph_po_deny('po.owner')
            center=self._sph_po_scope(creating=True,company_id=values.get('company_id'))
            prepared.append(dict(values,sph_center_id=center.id))
        try:return super().create(prepared)
        except (AccessError,MissingError):return self._sph_po_deny('po.create')

    def write(self,values):
        if 'sph_center_id' in values:return self._sph_po_deny('po.owner')
        # Scope before outer bundle/role guards can inspect or audit any record.
        if 'locked' in values:self._sph_po_scope(action='purchase.order.locked')
        if 'sph_incident_ref' in values:self._sph_po_scope(action='incident.reference')
        return super().write(values)

    def read(self,*args,**kwargs):
        if self.env.su:return super().read(*args,**kwargs)
        self._sph_po_scope()
        try:return super().read(*args,**kwargs)
        except (AccessError,MissingError):return self._sph_po_deny('po.read')

    def _search(self,domain,*args,**kwargs):
        if self.env.su:return super()._search(domain,*args,**kwargs)
        self._sph_po_scope()
        try:return super()._search(domain,*args,**kwargs)
        except (AccessError,MissingError):return self._sph_po_deny('po.search')

    def export_data(self,*args,**kwargs):
        if self.env.su:return super().export_data(*args,**kwargs)
        self._sph_po_scope()
        try:return super().export_data(*args,**kwargs)
        except (UserError,MissingError):return self._sph_po_deny('po.export')
