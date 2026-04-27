# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import MagicMock, patch
from odoo.tests.common import TransactionCase


class WahaTestCommon(TransactionCase):
    """
    Base class with shared fixtures for all WAHA tests.

    Creates a connected waha.account plus a res.partner with a mobile number
    so individual tests don't need to repeat that boilerplate.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.admin_user = cls.env.ref('base.user_admin')

        cls.test_partner = cls.env['res.partner'].create({
            'name': 'Test WA Contact',
            'mobile': '+5491112345678',
        })

        cls.account = cls.env['waha.account'].create({
            'name': 'Test WAHA Account',
            'waha_url': 'http://localhost:3000',
            'session_name': 'test_session',
            'status': 'connected',
            'notify_user_ids': [(4, cls.admin_user.id)],
        })

    # ------------------------------------------------------------------ helpers

    def make_api_mock(self, target, **method_returns):
        """
        Return a context-manager that patches *target* with a MagicMock whose
        instance methods return the values supplied in *method_returns*.

        Usage::

            with self.make_api_mock('odoo.addons.waha.models.waha_message.WahaApi',
                                    send_text={'id': 'wa_123'}):
                msg = self.env['waha.message'].create(...)
        """
        mock_instance = MagicMock()
        for name, retval in method_returns.items():
            getattr(mock_instance, name).return_value = retval
        mock_class = MagicMock(return_value=mock_instance)
        return patch(target, mock_class)

    def make_waha_chat(self, chat_id='5491112345678@c.us', account=None, **kwargs):
        """Create a waha.chat (and its discuss.channel) for use in tests."""
        account = account or self.account
        with patch('odoo.addons.waha.models.waha_chat.WahaApi'):
            return self.env['waha.chat'].create({
                'name': 'Test Chat',
                'wa_chat_id': chat_id,
                'wa_account_id': account.id,
                **kwargs,
            })

    def make_waha_partner(self, phone='5491112345678', lid=None, partner=None):
        """Create a waha.partner linked to *self.account*."""
        partner = partner or self.test_partner
        vals = {
            'partner_id': partner.id,
            'wa_account_id': self.account.id,
            'phone_number': phone,
        }
        if lid:
            vals['lid'] = lid
        return self.env['waha.partner'].create(vals)

    def make_inbound_payload(self, **overrides):
        """Return a minimal valid WAHA inbound message payload dict."""
        data = {
            'id': 'test_msg_001',
            'from': '5491112345678@c.us',
            'fromMe': False,
            'body': 'Hello from test',
            'timestamp': 0,
            'type': 'chat',
        }
        data.update(overrides)
        return data
