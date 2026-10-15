"""Original authority/audit primitives. Client context never grants authority."""
from contextvars import ContextVar
from contextlib import contextmanager
from odoo import api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessError
from odoo.tools import config

_TRANSITION = ContextVar('sph_purchase_transition', default=False)


@contextmanager
def purchase_transition():
    token=_TRANSITION.set(True)
    try: yield
    finally: _TRANSITION.reset(token)


_DRAFT = ContextVar('sph_preparing_draft', default=False)


@contextmanager
def preparing_draft():
    token=_DRAFT.set(True)
    try: yield
    finally: _DRAFT.reset(token)


_INTERNAL = ContextVar('sph_internal_stock', default=False)


@contextmanager
def internal_stock():
    token = _INTERNAL.set(True)
    try: yield
    finally: _INTERNAL.reset(token)


def audit(records, action, outcome, before_state=None):
    kind='bot' if records.env.uid != 1 and records.env.user.has_group('sph_core.group_sph_bot') else 'human'
    values=[]
    for record in records:
        current=record.sudo()
        state=current.state if 'state' in current._fields else False
        digest=current._sph_digest() if current._name=='purchase.order' else False
        values.append({'res_model':records._name,'res_id':record.id,'actor_uid':records.env.uid,
            'actor_kind':kind,'action':action,'outcome':outcome,'revision_digest':digest,
            'before_state':before_state if before_state is not None else state,'after_state':state,
            'incident_ref':current.sph_incident_ref if 'sph_incident_ref' in current._fields else False})
    if not values:
        values=[{'res_model':records._name,'res_id':0,'actor_uid':records.env.uid,'action':action,'outcome':outcome,'actor_kind':kind}]
    if outcome == 'deny':
        # Uncommitted unit fixtures/DDL are invisible to another cursor. Deny rows
        # are asserted only by the committed live suite, never TransactionCase.
        if config['test_enable']:
            # Bundle regression tests inspect only same-cursor, rollback-only rows.
            # Durable separate-cursor denials remain live-suite-only.
            if action.endswith('.bundle'):
                records.env['sph.authority.audit'].sudo().create(values)
            return
        with records.env.registry.cursor() as cursor:
            api.Environment(cursor,SUPERUSER_ID,{})['sph.authority.audit'].create(values)
            cursor.commit()
    else:
        records.env['sph.authority.audit'].sudo().create(values)


def approver(records, action, maker=False):
    # No uid-1, sudo or cron exception: the actual actor must have this role.
    user=records.env.user
    allowed=user.active and not user.has_group('sph_core.group_sph_bot') and user.has_group('sph_core.group_sph_purchasing_approver')
    if maker:
        allowed=allowed and all(record.sudo().sph_maker_uid != user.id for record in records)
    if not allowed:
        audit(records,action,'deny')
        raise AccessError('Unavailable')


class AuthorityAudit(models.Model):
    _name='sph.authority.audit'
    _description='SPH independent authority evidence (plain object identifiers)'
    _order='id'
    res_model=fields.Char(required=True)
    res_id=fields.Integer(required=True)
    actor_uid=fields.Integer(required=True)
    actor_kind=fields.Selection([('bot','Bot'),('human','Human')],required=True)
    incident_ref=fields.Char(size=128)
    revision_digest=fields.Char()
    before_state=fields.Char()
    after_state=fields.Char()
    action=fields.Char(required=True)
    outcome=fields.Selection([('allow','Allow'),('deny','Deny')],required=True)
