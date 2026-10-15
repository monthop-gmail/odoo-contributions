"""Original authority/audit primitives. Client context never grants authority."""
from contextvars import ContextVar
from contextlib import contextmanager
from odoo import api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessError

_INTERNAL = ContextVar('sph_internal_stock', default=False)


@contextmanager
def internal_stock():
    token = _INTERNAL.set(True)
    try: yield
    finally: _INTERNAL.reset(token)


def audit(records, action, outcome):
    values = [{'res_model':records._name,'res_id':record.id,'actor_uid':records.env.uid,
               'action':action,'outcome':outcome} for record in records]
    if not values: return
    if outcome == 'deny':
        # Uncommitted unit fixtures/DDL are invisible to another cursor. Deny rows
        # are asserted only by the committed live suite, never TransactionCase.
        if records.env.registry.in_test_mode(): return
        with records.env.registry.cursor() as cursor:
            api.Environment(cursor,SUPERUSER_ID,{})['sph.authority.audit'].create(values)
            cursor.commit()
    else:
        records.env['sph.authority.audit'].sudo().create(values)


def approver(records, action, maker=False):
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
    action=fields.Char(required=True)
    outcome=fields.Selection([('allow','Allow'),('deny','Deny')],required=True)
