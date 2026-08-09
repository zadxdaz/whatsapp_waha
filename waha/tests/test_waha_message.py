# Part of Odoo. See LICENSE file for full copyright and licensing details.

from unittest.mock import patch, MagicMock

from odoo.exceptions import UserError
from .common import WahaTestCommon

_MSG_API = 'odoo.addons.waha.models.waha_message.WahaApi'
_PARTNER_API = 'odoo.addons.waha.models.waha_partner.WahaApi'

# Patch both APIs at once to prevent real HTTP calls in create() chains
ALL_APIS = [_MSG_API, _PARTNER_API]


def _patch_all_apis(**msg_methods):
    """Patch WahaApi in both model modules simultaneously."""
    from contextlib import ExitStack
    from unittest.mock import patch, MagicMock

    stack = ExitStack()
    msg_instance = MagicMock()
    for name, retval in msg_methods.items():
        getattr(msg_instance, name).return_value = retval
    msg_mock = stack.enter_context(patch(_MSG_API, return_value=msg_instance))
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


class TestComputeDiscussChannelId(WahaTestCommon):
    """_compute_discuss_channel_id — pure lookup, never creates records."""

    def test_finds_existing_channel(self):
        channel = self.make_waha_channel('5491100001000@c.us')
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'test',
            'message_type': 'inbound',
            'raw_chat_id': '5491100001000@c.us',
        })
        msg._compute_discuss_channel_id()
        self.assertEqual(msg.discuss_channel_id, channel)

    def test_returns_false_when_channel_missing(self):
        """Must not create a new discuss.channel record."""
        count_before = self.env['discuss.channel'].search_count([
            ('is_whatsapp', '=', True),
        ])
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'test',
            'message_type': 'inbound',
            'raw_chat_id': '99999000001@c.us',
        })
        msg._compute_discuss_channel_id()
        count_after = self.env['discuss.channel'].search_count([
            ('is_whatsapp', '=', True),
        ])
        self.assertFalse(msg.discuss_channel_id)
        self.assertEqual(count_before, count_after)

    def test_returns_false_when_raw_chat_id_empty(self):
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'test',
            'message_type': 'inbound',
            'raw_chat_id': False,
        })
        msg._compute_discuss_channel_id()
        self.assertFalse(msg.discuss_channel_id)


class TestComputeWahaPartnerId(WahaTestCommon):
    """_compute_waha_partner_id — lookup by LID then phone, auto-creates as side-effect."""

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

    def test_auto_creates_when_not_found(self):
        """Not found → partner is auto-created (find_or_create_by_lid_or_phone)."""
        count_before = self.env['waha.partner'].search_count([])
        msg = self.env['waha.message'].new({
            'wa_account_id': self.account.id,
            'body': 'x', 'message_type': 'inbound',
            'raw_sender_phone': '99999000002',
        })
        msg._compute_waha_partner_id()
        count_after = self.env['waha.partner'].search_count([])
        self.assertTrue(msg.waha_partner_id)
        self.assertEqual(count_after, count_before + 1)

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
    """create() — channel is pure lookup, partner auto-created as side-effect."""

    def test_create_links_explicit_channel(self):
        channel = self.make_waha_channel('5491100003001@c.us')
        with patch(_MSG_API), patch(_PARTNER_API):
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'discuss_channel_id': channel.id,
                'body': 'Hello',
                'message_type': 'inbound',
                'state': 'received',
                'raw_chat_id': '5491100003001@c.us',
                'raw_sender_phone': '5491100003001',
            })
        self.assertTrue(msg.discuss_channel_id)
        self.assertEqual(msg.discuss_channel_id.wa_chat_id, '5491100003001@c.us')

    def test_create_does_not_auto_create_channel(self):
        """create() must not fabricate a discuss.channel — callers do that."""
        count_before = self.env['discuss.channel'].search_count([
            ('is_whatsapp', '=', True),
        ])
        with patch(_MSG_API), patch(_PARTNER_API):
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Hello',
                'message_type': 'inbound',
                'state': 'received',
                'raw_chat_id': '5491100003001@c.us',
                'raw_sender_phone': '5491100003001',
            })
        count_after = self.env['discuss.channel'].search_count([
            ('is_whatsapp', '=', True),
        ])
        self.assertFalse(msg.discuss_channel_id)
        self.assertEqual(count_before, count_after)

    def test_create_builds_waha_partner_when_missing(self):
        with patch(_MSG_API), patch(_PARTNER_API):
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'body': 'Hello',
                'message_type': 'inbound',
                'state': 'received',
                'raw_chat_id': '5491100003002@c.us',
                'raw_sender_phone': '5491100003002',
            })
        self.assertTrue(msg.waha_partner_id)

    def test_create_reuses_existing_channel(self):
        channel = self.make_waha_channel('5491100003003@c.us')
        chat_count_before = self.env['discuss.channel'].search_count([
            ('wa_chat_id', '=', '5491100003003@c.us')
        ])
        with patch(_MSG_API), patch(_PARTNER_API):
            msg = self.env['waha.message'].create({
                'wa_account_id': self.account.id,
                'discuss_channel_id': channel.id,
                'body': 'Hello',
                'message_type': 'inbound',
                'state': 'received',
                'raw_chat_id': '5491100003003@c.us',
                'raw_sender_phone': '5491100003003',
            })
        chat_count_after = self.env['discuss.channel'].search_count([
            ('wa_chat_id', '=', '5491100003003@c.us')
        ])
        self.assertEqual(msg.discuss_channel_id, channel)
        self.assertEqual(chat_count_before, chat_count_after)

    def test_create_skips_partner_for_group_sender(self):
        partner_count_before = self.env['waha.partner'].search_count([])
        with patch(_MSG_API), patch(_PARTNER_API):
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
        # Pre-create a channel so _compute_discuss_channel_id finds it
        channel = self.make_waha_channel(chat_id)
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
        channel = self.make_waha_channel('5491100004010@c.us')
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
        channel = self.make_waha_channel('5491100004011@c.us')
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
        channel = self.make_waha_channel('5491100004020@c.us')
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
        channel = self.make_waha_channel('5491100004021@c.us')
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
        channel = self.make_waha_channel('5491100004022@c.us')
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
        channel = self.make_waha_channel('5491100005001@c.us')
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
        channel = self.make_waha_channel('5491100005002@c.us')
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


class TestDiscussMessagePostBridge(WahaTestCommon):
    """mail.thread bridge — keep Odoo mail.message linked to waha.message."""

    def test_outbound_without_mail_message_is_not_duplicated_in_discuss(self):
        channel = self.make_waha_channel('5491100006000@c.us')
        count_before = self.env['mail.message'].search_count([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
        ])
        self.env['waha.message'].create({
            'wa_account_id': self.account.id,
            'msg_uid': 'true_5491100006000@c.us_unlinked_outbound',
            'body': 'Unlinked outbound must not be reposted',
            'message_type': 'outbound',
            'state': 'sent',
            'raw_chat_id': '5491100006000@c.us',
            'raw_sender_phone': '5491100006000',
        })
        count_after = self.env['mail.message'].search_count([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
        ])
        self.assertEqual(count_after, count_before)

    def test_outbound_discuss_post_links_existing_mail_message(self):
        channel = self.make_waha_channel('5491100006001@c.us')
        with patch(_MSG_API) as MockApi:
            MockApi.return_value.send_text.return_value = {
                'id': 'true_5491100006001@c.us_outbound_linked'
            }
            mail_message = channel.message_post(
                body='Message from Odoo',
                author_id=self.env.user.partner_id.id,
            )
        waha_message = self.env['waha.message'].search([
            ('mail_message_id', '=', mail_message.id),
            ('msg_uid', '=', 'true_5491100006001@c.us_outbound_linked'),
        ])
        self.assertEqual(len(waha_message), 1)
        self.assertEqual(waha_message.mail_message_id, mail_message)

    def test_outbound_discuss_reply_sets_waha_parent(self):
        channel = self.make_waha_channel('5491100006002@c.us')
        with patch(_MSG_API) as MockApi:
            MockApi.return_value.send_text.side_effect = [
                {'id': 'true_5491100006002@c.us_parent'},
                {'id': 'true_5491100006002@c.us_child'},
            ]
            parent_mail = channel.message_post(
                body='Parent from Odoo',
                author_id=self.env.user.partner_id.id,
            )
            child_mail = channel.message_post(
                body='Child from Odoo',
                author_id=self.env.user.partner_id.id,
                parent_id=parent_mail.id,
            )
        parent_waha = self.env['waha.message'].search([
            ('mail_message_id', '=', parent_mail.id),
        ], limit=1)
        child_waha = self.env['waha.message'].search([
            ('mail_message_id', '=', child_mail.id),
        ], limit=1)
        self.assertEqual(child_waha.reply_to_message_id, parent_waha)
        self.assertEqual(child_waha.reply_to_msg_uid, parent_waha.msg_uid)


    def test_inbound_reply_uses_existing_unlinked_outbound_parent_mail(self):
        channel = self.make_waha_channel('5491100006003@c.us')
        self.make_waha_partner(phone='5491100006003')
        parent_mail = channel.with_context(skip_whatsapp_send=True).message_post(
            body='Parent from Odoo without link',
            author_id=self.env.user.partner_id.id,
        )
        parent_waha = self.env['waha.message'].create({
            'wa_account_id': self.account.id,
            'msg_uid': 'true_5491100006003@c.us_parent_unlinked',
            'body': 'Parent from Odoo without link',
            'message_type': 'outbound',
            'state': 'sent',
            'raw_chat_id': '5491100006003@c.us',
            'raw_sender_phone': '5491100006003',
        })
        self.assertFalse(parent_waha.mail_message_id)

        reply = self.env['waha.message'].create({
            'wa_account_id': self.account.id,
            'msg_uid': 'false_5491100006003@c.us_reply_child',
            'body': 'Customer reply',
            'message_type': 'inbound',
            'state': 'received',
            'raw_chat_id': '5491100006003@c.us',
            'raw_sender_phone': '5491100006003',
            'reply_to_message_id': parent_waha.id,
            'reply_to_msg_uid': parent_waha.msg_uid,
        })

        self.assertEqual(parent_waha.mail_message_id, parent_mail)
        self.assertEqual(reply.mail_message_id.parent_id, parent_mail)

    def test_backfill_missing_mail_message_id_ignores_ambiguous_matches(self):
        channel = self.make_waha_channel('5491100006004@c.us')
        for _idx in range(2):
            channel.with_context(skip_whatsapp_send=True).message_post(
                body='Ambiguous parent',
                author_id=self.env.user.partner_id.id,
            )
        parent_waha = self.env['waha.message'].create({
            'wa_account_id': self.account.id,
            'msg_uid': 'true_5491100006004@c.us_parent_ambiguous',
            'body': 'Ambiguous parent',
            'message_type': 'outbound',
            'state': 'sent',
            'raw_chat_id': '5491100006004@c.us',
            'raw_sender_phone': '5491100006004',
        })

        repaired = parent_waha._backfill_missing_mail_message_id()

        self.assertFalse(repaired)
        self.assertFalse(parent_waha.mail_message_id)
