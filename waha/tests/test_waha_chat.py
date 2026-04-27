# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from unittest.mock import patch

from odoo.exceptions import UserError
from .common import WahaTestCommon

_API = 'odoo.addons.waha.models.waha_chat.WahaApi'


class TestComputeChatType(WahaTestCommon):
    """_compute_chat_type — derive type from wa_chat_id suffix."""

    def _new_chat(self, chat_id):
        return self.env['waha.chat'].new({'wa_chat_id': chat_id})

    def test_g_us_suffix_is_group(self):
        chat = self._new_chat('123456789@g.us')
        chat._compute_chat_type()
        self.assertEqual(chat.chat_type, 'group')

    def test_c_us_suffix_is_individual(self):
        chat = self._new_chat('5491112345678@c.us')
        chat._compute_chat_type()
        self.assertEqual(chat.chat_type, 'individual')

    def test_no_chat_id_defaults_individual(self):
        chat = self.env['waha.chat'].new({'wa_chat_id': False})
        chat._compute_chat_type()
        self.assertEqual(chat.chat_type, 'individual')


class TestComputeDiscussChannelId(WahaTestCommon):
    """_compute_discuss_channel_id — pure lookup only, no side-effects."""

    def test_finds_existing_channel(self):
        channel = self.env['discuss.channel'].sudo().create({
            'name': 'Existing WA Channel',
            'channel_type': 'whatsapp',
            'is_whatsapp': True,
            'whatsapp_account_id': self.account.id,
            'wa_chat_id': '5491112345678@c.us',
        })
        chat = self.env['waha.chat'].new({
            'wa_chat_id': '5491112345678@c.us',
            'wa_account_id': self.account.id,
            'name': 'Existing',
        })
        chat._compute_discuss_channel_id()
        self.assertEqual(chat.discuss_channel_id, channel)

    def test_returns_false_when_channel_missing(self):
        """Compute must NOT create a channel — just return False."""
        chat = self.env['waha.chat'].new({
            'wa_chat_id': '99999999999@c.us',
            'wa_account_id': self.account.id,
            'name': 'No Channel',
        })
        channel_count_before = self.env['discuss.channel'].search_count([
            ('wa_chat_id', '=', '99999999999@c.us')
        ])
        chat._compute_discuss_channel_id()
        channel_count_after = self.env['discuss.channel'].search_count([
            ('wa_chat_id', '=', '99999999999@c.us')
        ])
        self.assertFalse(chat.discuss_channel_id)
        self.assertEqual(channel_count_before, channel_count_after)


class TestComputePartnerId(WahaTestCommon):
    """_compute_partner_id — find partner from individual chat_id."""

    def test_individual_chat_finds_partner_by_mobile(self):
        # self.test_partner has mobile='+5491112345678'
        chat = self.env['waha.chat'].new({
            'wa_chat_id': '5491112345678@c.us',
            'wa_account_id': self.account.id,
            'name': 'Test',
            'chat_type': 'individual',
        })
        chat._compute_partner_id()
        self.assertEqual(chat.partner_id, self.test_partner)

    def test_individual_chat_no_partner_returns_false(self):
        chat = self.env['waha.chat'].new({
            'wa_chat_id': '99000000001@c.us',
            'wa_account_id': self.account.id,
            'name': 'Unknown',
            'chat_type': 'individual',
        })
        chat._compute_partner_id()
        self.assertFalse(chat.partner_id)

    def test_group_chat_always_false(self):
        chat = self.env['waha.chat'].new({
            'wa_chat_id': '120363000000@g.us',
            'wa_account_id': self.account.id,
            'name': 'Group',
            'chat_type': 'group',
        })
        chat._compute_partner_id()
        self.assertFalse(chat.partner_id)


class TestCreateOverride(WahaTestCommon):
    """create() — discuss.channel created as side-effect."""

    def test_create_generates_discuss_channel(self):
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'New Individual Chat',
                'wa_chat_id': '5491100000001@c.us',
                'wa_account_id': self.account.id,
            })
        self.assertTrue(chat.discuss_channel_id)
        self.assertEqual(chat.discuss_channel_id.channel_type, 'whatsapp')
        self.assertTrue(chat.discuss_channel_id.is_whatsapp)

    def test_channel_has_correct_wa_chat_id(self):
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'WA ID Check',
                'wa_chat_id': '5491100000002@c.us',
                'wa_account_id': self.account.id,
            })
        self.assertEqual(chat.discuss_channel_id.wa_chat_id, '5491100000002@c.us')

    def test_channel_not_duplicated_on_second_create(self):
        """Creating a second chat with the same wa_chat_id must reuse the channel."""
        with patch(_API):
            chat1 = self.env['waha.chat'].create({
                'name': 'First',
                'wa_chat_id': '5491100000003@c.us',
                'wa_account_id': self.account.id,
            })
        channel_id = chat1.discuss_channel_id.id
        # Simulate a second attempt (e.g. after a rollback/retry)
        chat1._ensure_discuss_channel()
        self.assertEqual(chat1.discuss_channel_id.id, channel_id)

    def test_ensure_discuss_channel_idempotent(self):
        """_ensure_discuss_channel() called twice must not duplicate channels."""
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'Idempotent',
                'wa_chat_id': '5491100000004@c.us',
                'wa_account_id': self.account.id,
            })
        count_before = self.env['discuss.channel'].search_count([
            ('wa_chat_id', '=', '5491100000004@c.us')
        ])
        chat._ensure_discuss_channel()
        count_after = self.env['discuss.channel'].search_count([
            ('wa_chat_id', '=', '5491100000004@c.us')
        ])
        self.assertEqual(count_before, count_after)


class TestSyncChannelMembers(WahaTestCommon):
    """_sync_channel_members — correct partners added to channel."""

    def test_individual_adds_contact_and_notify_users(self):
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'Sync Members Test',
                'wa_chat_id': '5491112345678@c.us',
                'wa_account_id': self.account.id,
            })
        channel = chat.discuss_channel_id
        member_partner_ids = channel.channel_partner_ids.ids
        # The admin (notify_user) must be a member
        self.assertIn(self.admin_user.partner_id.id, member_partner_ids)

    def test_fallback_to_admin_when_no_notify_users(self):
        acc_no_notify = self.env['waha.account'].create({
            'name': 'No Notify Acc',
            'waha_url': 'http://localhost:3000',
            'session_name': 'no_notify_members',
            'status': 'connected',
            'notify_user_ids': [(4, self.admin_user.id)],
        })
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'Fallback Members',
                'wa_chat_id': '5491100000010@c.us',
                'wa_account_id': acc_no_notify.id,
            })
        channel = chat.discuss_channel_id
        admin_partner = self.env.ref('base.user_admin').partner_id
        self.assertIn(admin_partner.id, channel.channel_partner_ids.ids)


class TestFindOrCreate(WahaTestCommon):
    """find_or_create — idempotency and creation."""

    def test_returns_existing_chat(self):
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'FindOrCreate Base',
                'wa_chat_id': '5491100000020@c.us',
                'wa_account_id': self.account.id,
            })
        with patch(_API):
            result = self.env['waha.chat'].find_or_create(
                wa_account=self.account,
                chat_id='5491100000020@c.us',
            )
        self.assertEqual(result.id, chat.id)

    def test_creates_new_individual_chat_with_channel(self):
        with patch(_API):
            chat = self.env['waha.chat'].find_or_create(
                wa_account=self.account,
                chat_id='5491100000021@c.us',
            )
        self.assertTrue(chat.id)
        self.assertEqual(chat.chat_type, 'individual')
        self.assertTrue(chat.discuss_channel_id)

    def test_creates_new_group_chat(self):
        with patch(_API) as MockApi:
            MockApi.return_value.get_group_info.return_value = {'name': 'Test Group'}
            chat = self.env['waha.chat'].find_or_create(
                wa_account=self.account,
                chat_id='120363000000001@g.us',
            )
        self.assertEqual(chat.chat_type, 'group')


class TestUpdateLastMessage(WahaTestCommon):
    """update_last_message — counter and timestamp updates."""

    def test_increments_message_count(self):
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'Counter Test',
                'wa_chat_id': '5491100000030@c.us',
                'wa_account_id': self.account.id,
            })
        original_count = chat.message_count
        chat.update_last_message()
        self.assertEqual(chat.message_count, original_count + 1)

    def test_uses_provided_timestamp(self):
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'Timestamp Test',
                'wa_chat_id': '5491100000031@c.us',
                'wa_account_id': self.account.id,
            })
        ts = datetime(2024, 6, 15, 12, 0, 0)
        chat.update_last_message(message_time=ts)
        self.assertEqual(chat.last_message_time, ts)

    def test_uses_now_without_arg(self):
        with patch(_API):
            chat = self.env['waha.chat'].create({
                'name': 'Now Test',
                'wa_chat_id': '5491100000032@c.us',
                'wa_account_id': self.account.id,
            })
        chat.update_last_message()
        self.assertTrue(chat.last_message_time)
