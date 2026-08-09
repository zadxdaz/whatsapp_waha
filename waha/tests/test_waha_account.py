# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from unittest.mock import patch, MagicMock

import requests as _requests

from odoo.exceptions import UserError, ValidationError
from .common import WahaTestCommon

_API = 'odoo.addons.waha.models.waha_account.WahaApi'


class TestComputeVerifyToken(WahaTestCommon):
    """_compute_verify_token — token generation logic."""

    def test_token_generated_on_create(self):
        """A freshly created account must have a 16-character token."""
        acc = self.env['waha.account'].create({
            'name': 'Token Test',
            'waha_url': 'http://localhost:3000',
            'session_name': 'token_session',
            'notify_user_ids': [(4, self.admin_user.id)],
        })
        self.assertTrue(acc.webhook_verify_token)
        self.assertEqual(len(acc.webhook_verify_token), 16)

    def test_token_alphanumeric(self):
        """Token must contain only letters and digits."""
        acc = self.env['waha.account'].create({
            'name': 'Token Alnum',
            'waha_url': 'http://localhost:3000',
            'session_name': 'alnum_session',
            'notify_user_ids': [(4, self.admin_user.id)],
        })
        self.assertTrue(acc.webhook_verify_token.isalnum())

    def test_token_not_regenerated_if_already_set(self):
        """Changing session_name must not overwrite an existing token."""
        acc = self.env['waha.account'].create({
            'name': 'Immutable Token',
            'waha_url': 'http://localhost:3000',
            'session_name': 'immutable_session',
            'notify_user_ids': [(4, self.admin_user.id)],
        })
        original_token = acc.webhook_verify_token
        acc.write({'session_name': 'immutable_session_v2'})
        self.assertEqual(acc.webhook_verify_token, original_token)

    def test_two_accounts_get_different_tokens(self):
        """Each account should get a unique token (not deterministic)."""
        acc_a = self.env['waha.account'].create({
            'name': 'Acc A', 'waha_url': 'http://localhost:3000',
            'session_name': 'sess_a', 'notify_user_ids': [(4, self.admin_user.id)],
        })
        acc_b = self.env['waha.account'].create({
            'name': 'Acc B', 'waha_url': 'http://localhost:3000',
            'session_name': 'sess_b', 'notify_user_ids': [(4, self.admin_user.id)],
        })
        # Very unlikely to collide with 16 chars from 62-char alphabet
        self.assertNotEqual(acc_a.webhook_verify_token, acc_b.webhook_verify_token)


class TestComputeAccountUid(WahaTestCommon):
    """_compute_account_uid — uid derivation."""

    def test_uid_from_session_name(self):
        self.assertEqual(self.account.account_uid, 'waha_test_session')

    def test_uid_empty_when_no_session_name(self):
        acc = self.env['waha.account'].new({
            'name': 'No Session', 'waha_url': 'http://localhost:3000',
            'session_name': False,
        })
        acc._compute_account_uid()
        self.assertFalse(acc.account_uid)


class TestCheckNotifyUserIds(WahaTestCommon):
    """_check_notify_user_ids — at least one user required."""

    def test_empty_notify_raises(self):
        with self.assertRaises(ValidationError):
            self.env['waha.account'].create({
                'name': 'No Notify',
                'waha_url': 'http://localhost:3000',
                'session_name': 'no_notify_session',
                'notify_user_ids': [(5, 0, 0)],  # clear M2M
            })


class TestActionRefreshStatus(WahaTestCommon):
    """action_refresh_status — WAHA status → account status mapping."""

    def _refresh(self, waha_status, extra=None):
        response = {'status': waha_status, 'statuses': []}
        if extra:
            response.update(extra)
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.return_value = response
            self.account.action_refresh_status()

    def test_working_maps_to_connected(self):
        self._refresh('WORKING', extra={'me': {'id': '5491112345678@c.us'}})
        self.assertEqual(self.account.status, 'connected')

    def test_connected_maps_to_connected(self):
        self._refresh('CONNECTED', extra={'me': {'id': '5491112345678@c.us'}})
        self.assertEqual(self.account.status, 'connected')

    def test_working_extracts_phone_uid(self):
        self._refresh('WORKING', extra={'me': {'id': '5491112345678@c.us'}})
        self.assertEqual(self.account.phone_uid, '5491112345678@c.us')

    def test_working_clears_qr_code(self):
        self.account.qr_code = b'fake_qr'
        self._refresh('WORKING', extra={'me': {'id': '5491112345678@c.us'}})
        self.assertFalse(self.account.qr_code)

    def test_starting_maps_to_connecting(self):
        self.account.status = 'connected'
        self._refresh('STARTING')
        self.assertEqual(self.account.status, 'connecting')

    def test_scan_qr_maps_to_connecting(self):
        self.account.status = 'connected'
        self._refresh('SCAN_QR_CODE')
        self.assertEqual(self.account.status, 'connecting')

    def test_stopped_maps_to_disconnected(self):
        self.account.status = 'connected'
        self._refresh('STOPPED')
        self.assertEqual(self.account.status, 'disconnected')

    def test_unknown_status_maps_to_disconnected(self):
        self.account.status = 'connected'
        self._refresh('TOTALLY_UNKNOWN')
        self.assertEqual(self.account.status, 'disconnected')

    def test_connection_error_raises_user_error(self):
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.side_effect = (
                _requests.exceptions.ConnectionError()
            )
            with self.assertRaises(UserError):
                self.account.action_refresh_status()

    def test_connection_error_sets_error_status(self):
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.side_effect = (
                _requests.exceptions.ConnectionError()
            )
            try:
                self.account.action_refresh_status()
            except UserError:
                pass
        self.assertEqual(self.account.status, 'error')

    def test_status_history_included_in_message(self):
        """Status history lines should appear in the notification message."""
        response = {
            'status': 'SCAN_QR_CODE',
            'statuses': [
                {'status': 'STARTING', 'timestamp': '2024-01-01T00:00:00Z'},
                {'status': 'SCAN_QR_CODE', 'timestamp': '2024-01-01T00:00:01Z'},
            ],
        }
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.return_value = response
            result = self.account.action_refresh_status()
        msg = result['params']['message']
        self.assertIn('STARTING', msg)


class TestActionGetQr(WahaTestCommon):
    """action_get_qr — QR retrieval and state handling."""

    def test_scan_qr_state_saves_qr_data(self):
        qr_b64 = 'aGVsbG8='  # base64 "hello"
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.return_value = {
                'status': 'SCAN_QR_CODE',
            }
            MockApi.return_value.get_qr_code.return_value = {'qr': qr_b64}
            self.account.action_get_qr()
        self.assertEqual(self.account.qr_code, qr_b64)

    def test_scan_qr_strips_data_uri_prefix(self):
        qr_b64 = 'data:image/png;base64,aGVsbG8='
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.return_value = {
                'status': 'SCAN_QR_CODE',
            }
            MockApi.return_value.get_qr_code.return_value = {'qr': qr_b64}
            self.account.action_get_qr()
        self.assertEqual(self.account.qr_code, 'aGVsbG8=')

    def test_scan_qr_sets_expiry(self):
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.return_value = {
                'status': 'SCAN_QR_CODE',
            }
            MockApi.return_value.get_qr_code.return_value = {'qr': 'aGVsbG8='}
            self.account.action_get_qr()
        self.assertTrue(self.account.qr_code_expiry)

    def test_already_connected_returns_warning_notification(self):
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.return_value = {
                'status': 'WORKING',
                'me': {'id': '54911@c.us'},
            }
            result = self.account.action_get_qr()
        self.assertEqual(result['params']['type'], 'warning')

    def test_other_state_returns_info_notification(self):
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.return_value = {
                'status': 'STARTING',
            }
            result = self.account.action_get_qr()
        self.assertEqual(result['params']['type'], 'info')

    def test_no_duplicate_raise_on_exception(self):
        """Regression: the old code had two consecutive raise statements."""
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.side_effect = Exception('boom')
            # Should raise exactly one UserError, not cause a SyntaxError or double raise
            with self.assertRaises(UserError):
                self.account.action_get_qr()


class TestFetchChatsTimestamps(WahaTestCommon):
    """action_fetch_chats_and_messages — UTC timestamp handling."""

    def _build_chat_response(self, chat_id='5491112345678@c.us'):
        return [{'id': {'_serialized': chat_id}, 'name': 'Test', 'timestamp': 1}]

    def _build_message_response(self, timestamp, chat_id='5491112345678@c.us',
                                msg_uid='msg_ts_001', from_me=False):
        return [{
            'id': {'id': msg_uid, '_serialized': msg_uid},
            'from': chat_id,
            'fromMe': from_me,
            'body': 'timestamp test',
            'timestamp': timestamp,
            'type': 'chat',
        }]

    def test_epoch_zero_produces_utc_datetime(self):
        """Unix timestamp 0 must yield 1970-01-01 00:00:00 UTC (naive)."""
        with patch(_API) as MockApi:
            MockApi.return_value.get_chats.return_value = self._build_chat_response()
            MockApi.return_value.get_messages.return_value = self._build_message_response(0)
            with patch('odoo.addons.waha.models.waha_message.WahaApi'):
                self.account.action_fetch_chats_and_messages()

        msg = self.env['waha.message'].search([
            ('msg_uid', '=', 'msg_ts_001'),
            ('wa_account_id', '=', self.account.id),
        ])
        self.assertTrue(msg)
        expected = datetime(1970, 1, 1, 0, 0, 0)
        self.assertEqual(msg.wa_timestamp, expected)

    def test_known_timestamp_is_utc(self):
        """1700000000 → 2023-11-14 22:13:20 UTC (not shifted by local TZ)."""
        with patch(_API) as MockApi:
            MockApi.return_value.get_chats.return_value = self._build_chat_response()
            MockApi.return_value.get_messages.return_value = self._build_message_response(
                1700000000, '5491112345678@c.us'
            )
            with patch('odoo.addons.waha.models.waha_message.WahaApi'):
                self.account.action_fetch_chats_and_messages()

        msg = self.env['waha.message'].search([
            ('msg_uid', '=', 'msg_ts_001'),
            ('wa_account_id', '=', self.account.id),
        ])
        # UTC interpretation: 2023-11-14 22:13:20
        self.assertEqual(msg.wa_timestamp, datetime(2023, 11, 14, 22, 13, 20))

    def test_sync_uses_configured_limits(self):
        self.account.write({
            'sync_chat_limit': 2,
            'sync_message_limit': 25,
        })
        chat_response = [
            {'id': {'_serialized': '5491111111111@c.us'}, 'name': 'Old', 'timestamp': 1},
            {'id': {'_serialized': '5491222222222@c.us'}, 'name': 'Newest', 'timestamp': 3},
            {'id': {'_serialized': '5491333333333@c.us'}, 'name': 'Middle', 'timestamp': 2},
        ]
        with patch(_API) as MockApi:
            MockApi.return_value.get_chats.return_value = chat_response
            MockApi.return_value.get_messages.return_value = []
            with patch('odoo.addons.waha.models.waha_message.WahaApi'):
                self.account.action_fetch_chats_and_messages()

        self.assertEqual(MockApi.return_value.get_messages.call_count, 2)
        for call in MockApi.return_value.get_messages.call_args_list:
            self.assertEqual(call.kwargs['limit'], 25)

    def test_outbound_history_message_uses_user_author(self):
        with patch(_API) as MockApi:
            MockApi.return_value.get_chats.return_value = self._build_chat_response(
                '5491112345678@c.us'
            )
            MockApi.return_value.get_messages.return_value = self._build_message_response(
                1700000000,
                '5491112345678@c.us',
                msg_uid='msg_from_me_001',
                from_me=True,
            )
            with patch('odoo.addons.waha.models.waha_message.WahaApi'):
                self.account.action_fetch_chats_and_messages()

        msg = self.env['waha.message'].search([
            ('msg_uid', '=', 'msg_from_me_001'),
            ('wa_account_id', '=', self.account.id),
        ])
        self.assertEqual(msg.message_type, 'outbound')
        self.assertEqual(msg.mail_message_id.author_id, self.admin_user.partner_id)


class TestCronCheckConnection(WahaTestCommon):
    """_cron_check_connection_status — targets only relevant accounts."""

    def test_cron_skips_disconnected_accounts(self):
        disc_acc = self.env['waha.account'].create({
            'name': 'Disconnected',
            'waha_url': 'http://localhost:3000',
            'session_name': 'disc_session',
            'status': 'disconnected',
            'notify_user_ids': [(4, self.admin_user.id)],
        })
        with patch.object(disc_acc.__class__, 'action_refresh_status') as mock_refresh:
            self.env['waha.account']._cron_check_connection_status()
        # The disconnected account must never be called
        self.assertEqual(mock_refresh.call_count, 0)

    def test_cron_handles_individual_account_error(self):
        """An exception in one account must not abort the whole cron."""
        connecting_acc = self.env['waha.account'].create({
            'name': 'Connecting Err',
            'waha_url': 'http://localhost:3000',
            'session_name': 'conn_err_session',
            'status': 'connecting',
            'notify_user_ids': [(4, self.admin_user.id)],
        })
        with patch(_API) as MockApi:
            MockApi.return_value.get_session_status.side_effect = Exception('timeout')
            # Must not raise
            self.env['waha.account']._cron_check_connection_status()
