# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch, MagicMock

from odoo.exceptions import ValidationError
from .common import WahaTestCommon

_CHAT_API = 'odoo.addons.waha.models.waha_chat.WahaApi'
_PARTNER_API = 'odoo.addons.waha.models.waha_partner.WahaApi'
_MSG_API = 'odoo.addons.waha.models.waha_message.WahaApi'


class TestComputeMobileNumberFormatted(WahaTestCommon):
    """_compute_mobile_number_formatted — with and without optional sanitizer."""

    def _make_composer(self, mobile):
        return self.env['waha.composer'].new({
            'wa_account_id': self.account.id,
            'mobile_number': mobile,
            'body': '<p>Hello</p>',
        })

    def test_formatted_passthrough_without_sanitizer(self):
        """When wa_sanitize_number is None the raw number is returned as-is."""
        with patch('odoo.addons.waha.wizard.waha_composer.wa_sanitize_number', None):
            composer = self._make_composer('+5491112345678')
            composer._compute_mobile_number_formatted()
        self.assertEqual(composer.mobile_number_formatted, '+5491112345678')

    def test_formatted_uses_sanitizer_when_available(self):
        """When wa_sanitize_number is available it should be called."""
        with patch('odoo.addons.waha.wizard.waha_composer.wa_sanitize_number',
                   return_value='5491112345678') as mock_san:
            composer = self._make_composer('+5491112345678')
            composer._compute_mobile_number_formatted()
        mock_san.assert_called_once_with('+5491112345678')
        self.assertEqual(composer.mobile_number_formatted, '5491112345678')

    def test_empty_number_returns_empty_string(self):
        composer = self._make_composer('')
        composer._compute_mobile_number_formatted()
        self.assertEqual(composer.mobile_number_formatted, '')


class TestActionSendMessage(WahaTestCommon):
    """action_send_message — message creation and linking."""

    def _compose_and_send(self, mobile='+5491112345678', body='<p>Hello</p>',
                          res_model=None, res_id=None):
        vals = {
            'wa_account_id': self.account.id,
            'mobile_number': mobile,
            'body': body,
        }
        if res_model:
            vals['res_model'] = res_model
        if res_id:
            vals['res_id'] = res_id

        composer = self.env['waha.composer'].create(vals)
        with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
            result = composer.action_send_message()
        return result

    def test_creates_outgoing_message(self):
        count_before = self.env['waha.message'].search_count([
            ('wa_account_id', '=', self.account.id),
        ])
        self._compose_and_send()
        count_after = self.env['waha.message'].search_count([
            ('wa_account_id', '=', self.account.id),
        ])
        self.assertGreater(count_after, count_before)

    def test_message_is_outbound(self):
        self._compose_and_send()
        msg = self.env['waha.message'].search([
            ('wa_account_id', '=', self.account.id),
            ('message_type', '=', 'outbound'),
        ], order='id desc', limit=1)
        self.assertTrue(msg)
        self.assertEqual(msg.state, 'outgoing')

    def test_chat_created_for_number(self):
        self._compose_and_send(mobile='+5491100020001')
        chat = self.env['waha.chat'].search([
            ('wa_chat_id', '=', '5491100020001@c.us'),
            ('wa_account_id', '=', self.account.id),
        ])
        self.assertTrue(chat)

    def test_html_stripped_from_body(self):
        self._compose_and_send(body='<b>Bold text</b>', mobile='+5491100020002')
        msg = self.env['waha.message'].search([
            ('wa_account_id', '=', self.account.id),
            ('raw_sender_phone', '=', '5491100020002'),
        ], order='id desc', limit=1)
        self.assertEqual(msg.body, 'Bold text')

    def test_links_to_related_record_chatter(self):
        """With res_model/res_id the message should be posted in the chatter."""
        partner = self.test_partner
        self._compose_and_send(
            mobile='+5491100020003',
            res_model='res.partner',
            res_id=partner.id,
        )
        # Verify a mail.message was posted on the partner
        chatter_msg = self.env['mail.message'].search([
            ('model', '=', 'res.partner'),
            ('res_id', '=', partner.id),
            ('message_type', '=', 'comment'),
        ], order='id desc', limit=1)
        self.assertTrue(chatter_msg)

    def test_returns_success_notification(self):
        result = self._compose_and_send()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
        self.assertEqual(result['params']['type'], 'success')

    def test_empty_body_raises_validation_error(self):
        composer = self.env['waha.composer'].new({
            'wa_account_id': self.account.id,
            'mobile_number': '+5491112345678',
            'body': '',
        })
        with self.assertRaises(ValidationError):
            composer.action_send_message()

    def test_missing_mobile_raises_validation_error(self):
        composer = self.env['waha.composer'].new({
            'wa_account_id': self.account.id,
            'mobile_number': '',
            'body': 'Hello',
        })
        with self.assertRaises(ValidationError):
            composer.action_send_message()

    def test_attachment_sets_document_content_type(self):
        attachment = self.env['ir.attachment'].create({
            'name': 'test.pdf',
            'datas': b'fake_pdf_content'.hex(),
            'mimetype': 'application/pdf',
        })
        composer = self.env['waha.composer'].create({
            'wa_account_id': self.account.id,
            'mobile_number': '+5491100020004',
            'body': 'With attachment',
            'attachment_ids': [(4, attachment.id)],
        })
        with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
            composer.action_send_message()
        msg = self.env['waha.message'].search([
            ('raw_sender_phone', '=', '5491100020004'),
            ('wa_account_id', '=', self.account.id),
        ], order='id desc', limit=1)
        self.assertEqual(msg.content_type, 'document')


class TestActionScheduleMessage(WahaTestCommon):
    """action_schedule_message — creates draft without sending."""

    def test_creates_draft_message(self):
        composer = self.env['waha.composer'].create({
            'wa_account_id': self.account.id,
            'mobile_number': '+5491100021001',
            'body': '<p>Scheduled</p>',
        })
        with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API) as MockMsgApi:
            composer.action_schedule_message()
        # The WAHA API must never be called for a draft
        MockMsgApi.return_value.send_text.assert_not_called()

    def test_draft_state(self):
        composer = self.env['waha.composer'].create({
            'wa_account_id': self.account.id,
            'mobile_number': '+5491100021002',
            'body': 'Scheduled body',
        })
        with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
            composer.action_schedule_message()
        msg = self.env['waha.message'].search([
            ('raw_sender_phone', '=', '5491100021002'),
            ('wa_account_id', '=', self.account.id),
        ], order='id desc', limit=1)
        self.assertTrue(msg)
        self.assertEqual(msg.state, 'draft')

    def test_returns_info_notification(self):
        composer = self.env['waha.composer'].create({
            'wa_account_id': self.account.id,
            'mobile_number': '+5491100021003',
            'body': 'Scheduled',
        })
        with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
            result = composer.action_schedule_message()
        self.assertEqual(result['params']['type'], 'info')
