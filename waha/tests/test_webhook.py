# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from unittest.mock import patch, MagicMock

from odoo import fields
from .common import WahaTestCommon

_CHAT_API = 'odoo.addons.waha.models.waha_chat.WahaApi'
_PARTNER_API = 'odoo.addons.waha.models.waha_partner.WahaApi'
_MSG_API = 'odoo.addons.waha.models.waha_message.WahaApi'


def _make_controller():
    from odoo.addons.waha.controller.webhook import WahaWebhookController
    return WahaWebhookController()


def _mock_request(env):
    """Return a MagicMock that looks enough like odoo.http.request."""
    mock = MagicMock()
    mock.env = env
    return mock


class TestExtractMessageContext(WahaTestCommon):
    """
    _extract_message_context — pure payload parsing (no DB access).
    Tested directly on the controller instance.
    """

    def setUp(self):
        super().setUp()
        self.controller = _make_controller()

    # ------------------------------------------------------------------ sender

    def test_c_us_sets_sender_phone(self):
        payload = self.make_inbound_payload(**{'from': '5491112345678@c.us'})
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['sender_phone'], '5491112345678')
        self.assertIsNone(ctx['sender_lid'])

    def test_lid_sets_sender_lid(self):
        payload = self.make_inbound_payload(**{'from': '987654321@lid'})
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['sender_lid'], '987654321')
        self.assertIsNone(ctx['sender_phone'])

    def test_group_message_uses_participant(self):
        payload = self.make_inbound_payload(**{
            'from': '120363000001@g.us',
            'participant': '5491112345678@c.us',
        })
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['sender_phone'], '5491112345678')
        self.assertTrue(ctx['is_group'])

    def test_group_message_without_participant(self):
        """Group message with no participant must not fabricate a sender."""
        payload = self.make_inbound_payload(**{
            'from': '120363000002@g.us',
            'participant': '',
        })
        ctx = self.controller._extract_message_context(payload)
        self.assertIsNone(ctx['sender_phone'])
        self.assertIsNone(ctx['sender_lid'])

    def test_from_me_flag(self):
        payload = self.make_inbound_payload(**{'fromMe': True})
        ctx = self.controller._extract_message_context(payload)
        self.assertTrue(ctx['from_me'])

    # ---------------------------------------------------------------- chat_id

    def test_chat_id_equals_from_field(self):
        payload = self.make_inbound_payload(**{'from': '5491112345678@c.us'})
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['chat_id'], '5491112345678@c.us')

    def test_group_chat_id(self):
        payload = self.make_inbound_payload(**{
            'from': '120363000003@g.us',
            'participant': '5491112345678@c.us',
        })
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['chat_id'], '120363000003@g.us')

    # ------------------------------------------------------------- timestamps

    def test_epoch_zero_is_utc(self):
        payload = self.make_inbound_payload(timestamp=0)
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['wa_timestamp'], datetime(1970, 1, 1, 0, 0, 0))

    def test_known_timestamp_is_utc(self):
        """1700000000 → 2023-11-14 22:13:20 UTC."""
        payload = self.make_inbound_payload(timestamp=1700000000)
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['wa_timestamp'], datetime(2023, 11, 14, 22, 13, 20))

    def test_no_timezone_info_on_result(self):
        """Odoo expects naive UTC datetimes — no tzinfo."""
        payload = self.make_inbound_payload(timestamp=1700000000)
        ctx = self.controller._extract_message_context(payload)
        self.assertIsNone(ctx['wa_timestamp'].tzinfo)

    def test_missing_timestamp_falls_back_to_now(self):
        payload = self.make_inbound_payload(timestamp=None)
        del payload['timestamp']
        ctx = self.controller._extract_message_context(payload)
        self.assertIsNotNone(ctx['wa_timestamp'])

    # ------------------------------------------------------------------- body

    def test_string_body(self):
        payload = self.make_inbound_payload(body='Hello World')
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['body'], 'Hello World')

    def test_dict_body_extracts_text(self):
        payload = self.make_inbound_payload(body={'text': 'From dict'})
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['body'], 'From dict')

    def test_none_body_becomes_empty_string(self):
        payload = self.make_inbound_payload(body=None)
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['body'], '')

    # ----------------------------------------------------------------- reply

    def test_quoted_stanza_id_extracted(self):
        payload = self.make_inbound_payload(**{
            '_data': {'quotedStanzaID': 'original_msg_uid_001'},
        })
        ctx = self.controller._extract_message_context(payload)
        self.assertEqual(ctx['reply_to_stanza_id'], 'original_msg_uid_001')

    def test_no_quoted_stanza_is_none(self):
        payload = self.make_inbound_payload()
        ctx = self.controller._extract_message_context(payload)
        self.assertIsNone(ctx['reply_to_stanza_id'])


class TestHandleIncomingMessage(WahaTestCommon):
    """_handle_incoming_message — DB-level behaviour."""

    def _call(self, data, msg_uid=None):
        """Call the handler with request.env = self.env."""
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        data.setdefault('session', self.account.session_name)
        if msg_uid:
            data.setdefault('payload', {})['id'] = msg_uid
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
                controller._handle_incoming_message(data)

    def _build_data(self, msg_uid='webhook_msg_001', **payload_overrides):
        payload = {
            'id': msg_uid,
            'from': '5491112345678@c.us',
            'fromMe': False,
            'body': 'Webhook test',
            'timestamp': 1700000000,
            'type': 'chat',
        }
        payload.update(payload_overrides)
        return {'session': self.account.session_name, 'payload': payload}

    def test_creates_waha_message(self):
        data = self._build_data('webhook_001')
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
                controller._handle_incoming_message(data)
        msg = self.env['waha.message'].search([
            ('msg_uid', '=', 'webhook_001'),
            ('wa_account_id', '=', self.account.id),
        ])
        self.assertTrue(msg)

    def test_inbound_message_type(self):
        data = self._build_data('webhook_002', fromMe=False)
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
                controller._handle_incoming_message(data)
        msg = self.env['waha.message'].search([('msg_uid', '=', 'webhook_002')])
        self.assertEqual(msg.message_type, 'inbound')
        self.assertEqual(msg.state, 'received')

    def test_outbound_message_type(self):
        data = self._build_data('webhook_003', fromMe=True)
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
                controller._handle_incoming_message(data)
        msg = self.env['waha.message'].search([('msg_uid', '=', 'webhook_003')])
        self.assertEqual(msg.message_type, 'outbound')

    def test_duplicate_message_not_created(self):
        data = self._build_data('webhook_dedup_001')
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
                controller._handle_incoming_message(data)
                controller._handle_incoming_message(data)  # second call
        count = self.env['waha.message'].search_count([
            ('msg_uid', '=', 'webhook_dedup_001'),
            ('wa_account_id', '=', self.account.id),
        ])
        self.assertEqual(count, 1)

    def test_payload_without_id_is_skipped(self):
        data = {'session': self.account.session_name, 'payload': {'from': '5491112345678@c.us'}}
        count_before = self.env['waha.message'].search_count([])
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
                controller._handle_incoming_message(data)
        count_after = self.env['waha.message'].search_count([])
        self.assertEqual(count_before, count_after)

    def test_raw_chat_id_stored(self):
        data = self._build_data('webhook_chat_id_001', **{'from': '5491112345678@c.us'})
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            with patch(_CHAT_API), patch(_PARTNER_API), patch(_MSG_API):
                controller._handle_incoming_message(data)
        msg = self.env['waha.message'].search([('msg_uid', '=', 'webhook_chat_id_001')])
        self.assertEqual(msg.raw_chat_id, '5491112345678@c.us')


class TestHandleMessageAck(WahaTestCommon):
    """_handle_message_ack — delegates to update_status_from_webhook."""

    def _make_saved_msg(self, uid='ack_hook_msg_001'):
        chat = self.make_waha_chat('5491100009001@c.us')
        return self.env['waha.message'].create({
            'wa_account_id': self.account.id,
            'msg_uid': uid,
            'body': 'ACK hook test',
            'message_type': 'outbound',
            'state': 'sent',
            'raw_chat_id': '5491100009001@c.us',
            'raw_sender_phone': '5491100009001',
        })

    def test_ack_updates_state(self):
        msg = self._make_saved_msg()
        data = {
            'session': self.account.session_name,
            'payload': {'id': msg.msg_uid, 'ack': 3},
        }
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            controller._handle_message_ack(data)
        self.assertEqual(msg.state, 'delivered')

    def test_unknown_msg_uid_logs_warning_no_error(self):
        data = {
            'session': self.account.session_name,
            'payload': {'id': 'definitely_unknown_uid', 'ack': 3},
        }
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            # Must not raise any exception
            controller._handle_message_ack(data)

    def test_missing_id_field_logs_warning_no_error(self):
        data = {
            'session': self.account.session_name,
            'payload': {'ack': 3},  # no 'id'
        }
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            controller._handle_message_ack(data)


class TestHandleSessionStatus(WahaTestCommon):
    """_handle_session_status — maps WAHA status → account status."""

    def _call(self, waha_status):
        data = {
            'session': self.account.session_name,
            'payload': {'status': waha_status},
        }
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            controller._handle_session_status(data)

    def test_working_maps_to_connected(self):
        self.account.status = 'connecting'
        self._call('WORKING')
        self.assertEqual(self.account.status, 'connected')

    def test_stopped_maps_to_disconnected(self):
        self.account.status = 'connected'
        self._call('STOPPED')
        self.assertEqual(self.account.status, 'disconnected')

    def test_failed_maps_to_error(self):
        self.account.status = 'connected'
        self._call('FAILED')
        self.assertEqual(self.account.status, 'error')

    def test_starting_maps_to_connecting(self):
        self.account.status = 'disconnected'
        self._call('STARTING')
        self.assertEqual(self.account.status, 'connecting')

    def test_scan_qr_maps_to_connecting(self):
        self.account.status = 'disconnected'
        self._call('SCAN_QR_CODE')
        self.assertEqual(self.account.status, 'connecting')

    def test_unknown_session_does_not_raise(self):
        data = {
            'session': 'nonexistent_session_xyz',
            'payload': {'status': 'WORKING'},
        }
        controller = _make_controller()
        mock_req = _mock_request(self.env)
        with patch('odoo.addons.waha.controller.webhook.request', mock_req):
            controller._handle_session_status(data)  # must not raise
