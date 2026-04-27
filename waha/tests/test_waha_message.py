# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError
from .common import WahaTestCommon

_MSG_API = 'odoo.addons.waha.models.waha_message.WahaApi'
_CHAT_API = 'odoo.addons.waha.models.waha_chat.WahaApi'
_PARTNER_API = 'odoo.addons.waha.models.waha_partner.WahaApi'

# Patch all three APIs at once to prevent real HTTP calls in create() chains
ALL_APIS = [_MSG_API, _CHAT_API, _PARTNER_API]


def _patch_all_apis(**msg_methods):
    """Patch WahaApi in all three model modules simultaneously."""
    from contextlib import ExitStack
    from unittest.mock import patch, MagicMock

    stack = ExitStack()
    msg_instance = MagicMock()
    for name, retval in msg_methods.items():
        getattr(msg_instance, name).return_value = retval
    msg_mock = stack.enter_context(patch(_MSG_API, return_value=msg_instance))
    stack.enter_context(patch(_CHAT_API))
    stack.enter_context(patch(_PARTNER_API))
    return stack, msg_instance


class TestComputeContentType(WahaTestCommon):
    """_compute_content_type — payload-driven media type detection."""

    def _content_type(self, payload):
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x',
            'message_type': 'inbound',
            'raw_payload': payload,
        })
        msg._compute_content_type()
        return msg.content_type

    def test_empty_payload_is_text(self):
        self.assertEqual(self._content_type({}), 'text')

    def test_has_media_image(self):
        self.assertEqual(self._content_type({'hasMedia': True, 'type': 'image'}), 'image')

    def test_has_media_video(self):
        self.assertEqual(self._content_type({'hasMedia': True, 'type': 'video'}), 'video')

    def test_has_media_audio(self):
        self.assertEqual(self._content_type({'hasMedia': True, 'type': 'audio'}), 'audio')

    def test_has_media_document(self):
        self.assertEqual(self._content_type({'hasMedia': True, 'type': 'document'}), 'document')

    def test_has_media_sticker(self):
        self.assertEqual(self._content_type({'hasMedia': True, 'type': 'sticker'}), 'sticker')

    def test_ptt_maps_to_audio(self):
        self.assertEqual(self._content_type({'hasMedia': True, 'type': 'ptt'}), 'audio')

    def test_unknown_media_type_maps_to_document(self):
        self.assertEqual(self._content_type({'hasMedia': True, 'type': 'unknownXYZ'}), 'document')

    def test_location_field_maps_to_location(self):
        self.assertEqual(self._content_type({'location': {'lat': 0, 'lon': 0}}), 'location')

    def test_no_media_flag_is_text(self):
        self.assertEqual(self._content_type({'type': 'chat', 'body': 'hi'}), 'text')


class TestComputeWahaChatId(WahaTestCommon):
    """_compute_waha_chat_id — pure lookup, never creates records."""

    def test_finds_existing_chat(self):
        chat = self.make_waha_chat('5491100001000@c.us')
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'test',
            'message_type': 'inbound',
            'raw_chat_id': '5491100001000@c.us',
        })
        msg._compute_waha_chat_id()
        self.assertEqual(msg.waha_chat_id, chat)

    def test_returns_false_when_chat_missing(self):
        """Must not create a new waha.chat record."""
        count_before = self.env['waha.chat'].search_count([])
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'test',
            'message_type': 'inbound',
            'raw_chat_id': '99999000001@c.us',
        })
        msg._compute_waha_chat_id()
        count_after = self.env['waha.chat'].search_count([])
        self.assertFalse(msg.waha_chat_id)
        self.assertEqual(count_before, count_after)

    def test_returns_false_when_raw_chat_id_empty(self):
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'test',
            'message_type': 'inbound',
            'raw_chat_id': False,
        })
        msg._compute_waha_chat_id()
        self.assertFalse(msg.waha_chat_id)


class TestComputeWahaPartnerId(WahaTestCommon):
    """_compute_waha_partner_id — pure lookup by LID then phone, never creates."""

    def test_finds_by_lid(self):
        partner = self.make_waha_partner(phone='5491100002001', lid='lid_001')
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x', 'message_type': 'inbound',
            'raw_sender_lid': 'lid_001',
        })
        msg._compute_waha_partner_id()
        self.assertEqual(msg.waha_partner_id, partner)

    def test_lid_has_priority_over_phone(self):
        partner_lid = self.make_waha_partner(phone='5491100002010', lid='lid_prio')
        other_partner = self.env['res.partner'].create({'name': 'Other'})
        partner_phone = self.make_waha_partner(phone='5491100002011', partner=other_partner)
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x', 'message_type': 'inbound',
            'raw_sender_lid': 'lid_prio',
            'raw_sender_phone': '5491100002011',
        })
        msg._compute_waha_partner_id()
        self.assertEqual(msg.waha_partner_id, partner_lid)

    def test_falls_back_to_phone(self):
        partner = self.make_waha_partner(phone='5491100002002')
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x', 'message_type': 'inbound',
            'raw_sender_phone': '5491100002002',
        })
        msg._compute_waha_partner_id()
        self.assertEqual(msg.waha_partner_id, partner)

    def test_returns_false_when_not_found(self):
        """Must not call find_or_create — just return False."""
        count_before = self.env['waha.partner'].search_count([])
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x', 'message_type': 'inbound',
            'raw_sender_phone': '99999000002',
        })
        msg._compute_waha_partner_id()
        count_after = self.env['waha.partner'].search_count([])
        self.assertFalse(msg.waha_partner_id)
        self.assertEqual(count_before, count_after)

    def test_skips_group_phone(self):
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x', 'message_type': 'inbound',
            'raw_sender_phone': '120363000000@g.us',
        })
        msg._compute_waha_partner_id()
        self.assertFalse(msg.waha_partner_id)

    def test_skips_zero_phone_without_lid(self):
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x', 'message_type': 'inbound',
            'raw_sender_phone': '0',
        })
        msg._compute_waha_partner_id()
        self.assertFalse(msg.waha_partner_id)

    def test_returns_false_without_any_identifier(self):
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x', 'message_type': 'inbound',
        })
        msg._compute_waha_partner_id()
        self.assertFalse(msg.waha_partner_id)


class TestCreateOverride(WahaTestCommon):
    """create() — chat and partner created as side-effects."""

    def test_create_builds_waha_chat_when_missing(self):
        with patch(_MSG_API), patch(_CHAT_API), patch(_PARTNER_API):
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Hello',
                'message_type': 'inbound',
                'state': 'received',
                'raw_chat_id': '5491100003001@c.us',
                'raw_sender_phone': '5491100003001',
            })
        self.assertTrue(msg.waha_chat_id)
        self.assertEqual(msg.waha_chat_id.wa_chat_id, '5491100003001@c.us')

    def test_create_builds_waha_partner_when_missing(self):
        with patch(_MSG_API), patch(_CHAT_API), patch(_PARTNER_API):
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Hello',
                'message_type': 'inbound',
                'state': 'received',
                'raw_chat_id': '5491100003002@c.us',
                'raw_sender_phone': '5491100003002',
            })
        self.assertTrue(msg.waha_partner_id)

    def test_create_reuses_existing_chat(self):
        chat = self.make_waha_chat('5491100003003@c.us')
        chat_count_before = self.env['waha.chat'].search_count([
            ('wa_chat_id', '=', '5491100003003@c.us')
        ])
        with patch(_MSG_API), patch(_CHAT_API), patch(_PARTNER_API):
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Hello',
                'message_type': 'inbound',
                'state': 'received',
                'raw_chat_id': '5491100003003@c.us',
                'raw_sender_phone': '5491100003003',
            })
        chat_count_after = self.env['waha.chat'].search_count([
            ('wa_chat_id', '=', '5491100003003@c.us')
        ])
        self.assertEqual(msg.waha_chat_id, chat)
        self.assertEqual(chat_count_before, chat_count_after)

    def test_create_skips_partner_for_group_sender(self):
        partner_count_before = self.env['waha.partner'].search_count([])
        with patch(_MSG_API), patch(_CHAT_API), patch(_PARTNER_API):
            self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Group msg',
                'message_type': 'inbound',
                'state': 'received',
                'raw_chat_id': '120363000001@g.us',
                'raw_sender_phone': '120363000001@g.us',
            })
        partner_count_after = self.env['waha.partner'].search_count([])
        self.assertEqual(partner_count_before, partner_count_after)


class TestComputeMsgUid(WahaTestCommon):
    """_compute_msg_uid — auto-send outgoing messages via WAHA API."""

    def _create_outgoing(self, chat_id='5491100004001@c.us', phone='5491100004001',
                         api_response=None):
        """Helper to create an outgoing message with mocked WAHA API."""
        api_response = api_response or {'id': 'waha_auto_001'}
        # Pre-create a chat so _compute_waha_chat_id finds it (avoiding the
        # waha_chat.WahaApi patch interfering with the message API mock)
        chat = self.make_waha_chat(chat_id)
        waha_partner = self.make_waha_partner(phone=phone)

        with patch(_MSG_API) as MockMsgApi, patch(_PARTNER_API):
            MockMsgApi.return_value.send_text.return_value = api_response
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Auto send test',
                'message_type': 'outbound',
                'state': 'outgoing',
                'raw_chat_id': chat_id,
                'raw_sender_phone': phone,
            })
        return msg

    def test_outgoing_message_gets_msg_uid(self):
        msg = self._create_outgoing()
        self.assertEqual(msg.msg_uid, 'waha_auto_001')

    def test_outgoing_message_becomes_sent(self):
        msg = self._create_outgoing()
        self.assertEqual(msg.state, 'sent')

    def test_outgoing_message_gets_sent_date(self):
        msg = self._create_outgoing()
        self.assertTrue(msg.sent_date)

    def test_inbound_never_calls_api(self):
        chat = self.make_waha_chat('5491100004010@c.us')
        waha_partner = self.make_waha_partner(phone='5491100004010')
        with patch(_MSG_API) as MockMsgApi, patch(_PARTNER_API):
            self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Inbound',
                'message_type': 'inbound',
                'state': 'received',
                'msg_uid': 'already_set_uid',
                'raw_chat_id': '5491100004010@c.us',
                'raw_sender_phone': '5491100004010',
            })
            MockMsgApi.return_value.send_text.assert_not_called()

    def test_draft_never_sends(self):
        chat = self.make_waha_chat('5491100004011@c.us')
        with patch(_MSG_API) as MockMsgApi, patch(_PARTNER_API):
            self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Draft',
                'message_type': 'outbound',
                'state': 'draft',
                'raw_chat_id': '5491100004011@c.us',
                'raw_sender_phone': '5491100004011',
            })
            MockMsgApi.return_value.send_text.assert_not_called()

    def test_api_error_sets_error_state(self):
        chat = self.make_waha_chat('5491100004020@c.us')
        waha_partner = self.make_waha_partner(phone='5491100004020')
        with patch(_MSG_API) as MockMsgApi, patch(_PARTNER_API):
            MockMsgApi.return_value.send_text.side_effect = Exception('network fail')
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Will fail',
                'message_type': 'outbound',
                'state': 'outgoing',
                'raw_chat_id': '5491100004020@c.us',
                'raw_sender_phone': '5491100004020',
            })
        self.assertEqual(msg.state, 'error')
        self.assertTrue(msg.failure_reason)

    def test_no_lid_for_user_error_maps_to_contact_not_found(self):
        chat = self.make_waha_chat('5491100004021@c.us')
        waha_partner = self.make_waha_partner(phone='5491100004021')
        with patch(_MSG_API) as MockMsgApi, patch(_PARTNER_API):
            MockMsgApi.return_value.send_text.side_effect = Exception('No LID for user')
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'No LID',
                'message_type': 'outbound',
                'state': 'outgoing',
                'raw_chat_id': '5491100004021@c.us',
                'raw_sender_phone': '5491100004021',
            })
        self.assertEqual(msg.failure_type, 'contact_not_found')

    def test_invalid_session_error_maps_to_account(self):
        chat = self.make_waha_chat('5491100004022@c.us')
        waha_partner = self.make_waha_partner(phone='5491100004022')
        with patch(_MSG_API) as MockMsgApi, patch(_PARTNER_API):
            MockMsgApi.return_value.send_text.side_effect = Exception('Invalid session')
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Bad session',
                'message_type': 'outbound',
                'state': 'outgoing',
                'raw_chat_id': '5491100004022@c.us',
                'raw_sender_phone': '5491100004022',
            })
        self.assertEqual(msg.failure_type, 'account')


class TestUpdateStatusFromWebhook(WahaTestCommon):
    """update_status_from_webhook — ACK-to-state mapping and no rollback."""

    def _make_sent_msg(self):
        chat = self.make_waha_chat('5491100005001@c.us')
        return self.env['waha.message'].create({
            'wa_account_id': self.account.id,
            'msg_uid': 'ack_test_msg',
            'body': 'ACK test',
            'message_type': 'outbound',
            'state': 'sent',
            'raw_chat_id': '5491100005001@c.us',
            'raw_sender_phone': '5491100005001',
        })

    def test_ack_0_sets_error(self):
        msg = self._make_sent_msg()
        msg.update_status_from_webhook({'ack': 0})
        self.assertEqual(msg.state, 'error')

    def test_ack_2_sets_sent_with_date(self):
        chat = self.make_waha_chat('5491100005002@c.us')
        msg = self.env['waha.message'].create({
            'wa_account_id': self.account.id,
            'msg_uid': 'ack_2_msg',
            'body': 'test',
            'message_type': 'outbound',
            'state': 'outgoing',
            'raw_chat_id': '5491100005002@c.us',
            'raw_sender_phone': '5491100005002',
        })
        msg.update_status_from_webhook({'ack': 2})
        self.assertEqual(msg.state, 'sent')
        self.assertTrue(msg.sent_date)

    def test_ack_3_sets_delivered_with_date(self):
        msg = self._make_sent_msg()
        msg.update_status_from_webhook({'ack': 3})
        self.assertEqual(msg.state, 'delivered')
        self.assertTrue(msg.delivered_date)

    def test_ack_4_sets_read_with_date(self):
        msg = self._make_sent_msg()
        msg.update_status_from_webhook({'ack': 4})
        self.assertEqual(msg.state, 'read')
        self.assertTrue(msg.read_date)

    def test_ack_5_also_sets_read(self):
        msg = self._make_sent_msg()
        msg.update_status_from_webhook({'ack': 5})
        self.assertEqual(msg.state, 'read')

    def test_out_of_order_ack_does_not_rollback(self):
        """A 'delivered' ACK after 'read' must not revert the state."""
        msg = self._make_sent_msg()
        msg.update_status_from_webhook({'ack': 4})  # read
        msg.update_status_from_webhook({'ack': 3})  # delivered (late)
        self.assertEqual(msg.state, 'read')

    def test_timestamps_not_overwritten(self):
        """If sent_date is already set, a second ACK 2 must not overwrite it."""
        from odoo import fields
        msg = self._make_sent_msg()
        msg.update_status_from_webhook({'ack': 2})
        first_sent_date = msg.sent_date
        msg.update_status_from_webhook({'ack': 2})
        self.assertEqual(msg.sent_date, first_sent_date)
