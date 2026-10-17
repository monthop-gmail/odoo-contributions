"""Synthetic RFQ capture and rule characterization; no SMTP and no SLA claim."""
import json
import time
from email.message import Message
from unittest.mock import MagicMock, patch
from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase
from .test_purchase_authority import prepare


class TestP0Leftovers(TransactionCase):
    def setUp(self):
        super().setUp()
        self.fx=prepare(self.env)
        # Existing native permissions only on rollback test actor, never seeded.
        self.fx['approver'].group_ids=[Command.link(self.env.ref('purchase.group_purchase_user').id)]

    def test_rfq_send_captured_no_smtp(self):
        fx=self.fx;po=fx['po'];human=fx['approver']
        fx['supplier'].email='fixture-supplier@example.invalid'
        human.partner_id.email='fixture-checker@example.invalid'
        self.env.company.email='fixture-hub@example.invalid'
        with self.assertRaisesRegex(AccessError,'^Unavailable$'):
            po.with_user(fx['bot']).action_rfq_send()
        po.with_user(human).sph_review()
        action=po.with_user(human).action_rfq_send()
        context=dict(action['context'],mail_notify_force_send=False,mail_notify_send_after_commit=False)
        captured=[]
        def capture(*args,**kwargs):
            message=next((arg for arg in args if isinstance(arg,Message)),kwargs.get('message'))
            self.assertIsInstance(message,Message);captured.append(message)
            return '<fixture-captured@example.invalid>'
        server=type(self.env['ir.mail_server'])
        with patch('smtplib.SMTP',side_effect=AssertionError('Real SMTP forbidden')) as smtp,\
                patch('smtplib.SMTP_SSL',side_effect=AssertionError('Real SMTP forbidden')) as ssl,\
                patch.object(server,'connect',return_value=MagicMock(name='fixture_transport')),\
                patch.object(server,'send_email',side_effect=capture):
            wizard=self.env['mail.compose.message'].with_user(human).with_context(context).create({})
            wizard.action_send_mail()
            queued=self.env['mail.mail'].sudo().search([
                ('mail_message_id.model','=','purchase.order'),('mail_message_id.res_id','=',po.id)])
            if not captured:queued.send()
            smtp.assert_not_called();ssl.assert_not_called()
        self.assertTrue(captured)
        self.assertTrue(any('fixture-supplier@example.invalid' in str(message.get('To','')) for message in captured))
        self.assertEqual(po.state,'sent')
        self.assertFalse(po.picking_ids)
        print('SPH_RFQ_CAPTURE '+json.dumps({'synthetic':True,'captured_messages':len(captured),
            'real_smtp_calls':0,'bot_rfq_denied':True,'human_rfq_state':po.state}),flush=True)

    def test_rule_performance_characterization(self):
        fx=self.fx;bot=fx['bot'];human=fx['approver'];center=bot.sph_center_ids
        documents=[]
        for _ in range(30):
            documents.append(self.env['purchase.order'].browse(self.env['purchase.order'].with_user(bot).sph_prepare(fx['supplier'].id,fx['product'].id)))
        bot.sph_center_ids=[Command.set(self.env.ref('sph_core.fixture_center_independent_b').ids)]
        foreign=self.env['purchase.order'].browse(self.env['purchase.order'].with_user(bot).sph_prepare(fx['supplier'].id,fx['product'].id))
        bot.sph_center_ids=[Command.set(center.ids)]
        messages=[];attachments=[]
        for po in documents+[foreign]:
            messages.append(self.env['mail.message'].create({'model':'purchase.order','res_id':po.id,
                'body':'FIXTURE benchmark','message_type':'comment'}))
            attachments.append(self.env['ir.attachment'].create({'name':'FIXTURE benchmark',
                'raw':b'FIXTURE benchmark','res_model':'purchase.order','res_id':po.id}))
        samples=[]
        for count in (2,10,30):
            for model,rows in (('mail.message',messages),('ir.attachment',attachments)):
                ids=[row.id for row in rows[:count]]+[rows[-1].id]
                actor=self.env[model].with_user(human)
                actor.search([('id','in',ids)]).read(['id'])  # Warm metadata before measuring.
                before=self.env.cr.sql_log_count;started=time.perf_counter()
                result=actor.search([('id','in',ids)]);result.read(['id'])
                elapsed=time.perf_counter()-started;queries=self.env.cr.sql_log_count-before
                self.assertEqual(set(result.ids),set(ids[:-1]))
                self.assertGreater(queries,0)
                samples.append({'model':model,'own_documents':count,'foreign_candidates':1,
                    'returned':len(result),'sql_queries':queries,'seconds':elapsed})
        print('SPH_RULE_PERFORMANCE '+json.dumps({'synthetic':True,'samples':samples,
            'interpretation':'Warm-cache query/time characterization only; no numeric SLA or production capacity claim.'}),flush=True)
