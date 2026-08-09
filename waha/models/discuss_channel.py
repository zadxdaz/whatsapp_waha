# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.addons.waha.tools.waha_api import WahaApi

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    channel_type = fields.Selection(
        selection_add=[('waha', 'WhatsApp (WAHA)')],
        ondelete={'waha': 'cascade'}
    )

    is_whatsapp = fields.Boolean(
        string='Is WhatsApp Channel',
        default=False,
        help='Whether this is a WhatsApp conversation channel'
    )

    wa_chat_id = fields.Char(
        string='WhatsApp Chat ID',
        help='WAHA chat ID (e.g., 5491121928204@c.us or group@g.us)'
    )

    whatsapp_group_id = fields.Many2one(
        'waha.group',
        string='WhatsApp Group',
        help='Associated WhatsApp group (if this is a group channel)',
        ondelete='set null'
    )

    whatsapp_account_id = fields.Many2one(
        'waha.account',
        string='WhatsApp Account',
        help='WhatsApp account this channel belongs to',
        ondelete='set null'
    )

    whatsapp_partner_id = fields.Many2one(
        'res.partner',
        string='WhatsApp Contact',
        help='Contact this WhatsApp channel belongs to (for 1-1 chats)',
        ondelete='set null'
    )

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @api.model
    def find_or_create_wa(self, wa_account, chat_id, partner=None):
        """Get or create the WhatsApp discuss.channel for a WAHA chat id."""
        channel = self.sudo().search([
            ('is_whatsapp', '=', True),
            ('wa_chat_id', '=', chat_id),
            ('whatsapp_account_id', '=', wa_account.id),
        ], limit=1)

        if channel:
            return channel

        is_group = '@g.us' in chat_id
        if is_group:
            channel_name = self._get_wa_group_name_from_waha(wa_account, chat_id)
        else:
            channel_name = partner.name if partner else chat_id

        channel = self.sudo().create({
            'channel_type': 'waha',
            'is_whatsapp': True,
            'name': channel_name,
            'wa_chat_id': chat_id,
            'whatsapp_account_id': wa_account.id,
            'whatsapp_partner_id': partner.id if partner else False,
        })
        _logger.info('Created waha channel %s for chat_id %s (group=%s)',
                     channel.id, chat_id, is_group)

        channel._sync_wa_members()
        return channel

    @api.model
    def _get_wa_group_name_from_waha(self, wa_account, chat_id):
        """Get a group name from the WAHA API."""
        try:
            api = WahaApi(wa_account)
            group_info = api.get_group_info(chat_id)
            if group_info:
                return group_info.get('name', chat_id)
        except Exception as e:
            _logger.warning('Could not get group name from WAHA: %s', str(e))
        return chat_id

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    def _sync_wa_members(self):
        """Ensure internal (notify) users and the account partner are members."""
        self.ensure_one()

        if self.channel_type != 'waha':
            return

        notify_partners = []
        if self.whatsapp_account_id.notify_user_ids:
            notify_partners = self.whatsapp_account_id.notify_user_ids.mapped('partner_id').ids

        if not notify_partners:
            admin = self.env.ref('base.user_admin').sudo()
            notify_partners = [admin.partner_id.id]
            _logger.warning('No notify_user_ids configured for account %s, using admin as fallback',
                            self.whatsapp_account_id.name)

        members_to_add = list(notify_partners)

        if self.whatsapp_account_id.account_partner_id:
            account_partner_id = self.whatsapp_account_id.account_partner_id.id
            if account_partner_id not in members_to_add:
                members_to_add.append(account_partner_id)

        current_members = self.channel_partner_ids.ids
        new_members = [m for m in members_to_add if m not in current_members]
        if new_members:
            self.write({'channel_partner_ids': [(4, mid) for mid in new_members]})
            _logger.info('Added %d members to waha channel %s',
                         len(new_members), self.id)

    def _sync_wa_group_participants(self, participants_data):
        """Replace group participants from WAHA participant dicts."""
        WahaPartner = self.env['waha.partner']

        participant_partners = []

        for participant in participants_data:
            participant_id = participant.get('id', {})

            lid = None
            phone = None

            if isinstance(participant_id, dict):
                user = participant_id.get('user', '')
                server = participant_id.get('server', '')
                if server == 'lid':
                    lid = user
                else:
                    phone = user
            else:
                participant_str = str(participant_id)
                if '@lid' in participant_str:
                    lid = participant_str.split('@')[0]
                elif '@c.us' in participant_str:
                    phone = participant_str.split('@')[0]
                else:
                    phone = participant_str.split('@')[0] if '@' in participant_str else participant_str

            if not lid and not phone:
                _logger.warning('Could not extract LID or phone from participant: %s', participant_id)
                continue

            waha_partner = WahaPartner.find_or_create_by_lid_or_phone(
                lid=lid,
                phone=phone,
                wa_account=self.whatsapp_account_id,
                auto_enrich=True,
            )

            if waha_partner and waha_partner.partner_id:
                participant_partners.append(waha_partner.partner_id.id)

        if participant_partners:
            self.write({'channel_partner_ids': [(6, 0, participant_partners)]})
            _logger.info('Updated %d participants for group channel %s',
                         len(participant_partners), self.id)
            self._sync_wa_members()

        return len(participant_partners)

    def sync_wa_group_info_from_waha(self):
        """Sync group information from WAHA (name, description, participants)."""
        self.ensure_one()

        if self.channel_type != 'waha' or '@g.us' not in (self.wa_chat_id or ''):
            _logger.warning('Cannot sync group info for non-group channel %s', self.id)
            return

        try:
            api = WahaApi(self.whatsapp_account_id)
            group_info = api.get_group_info(self.wa_chat_id)

            if not group_info:
                _logger.warning('No group info returned from WAHA for %s', self.wa_chat_id)
                return

            group_metadata = group_info.get('groupMetadata', group_info)

            vals = {}
            name = group_info.get('name') or group_metadata.get('subject')
            if name:
                vals['name'] = name

            if group_metadata.get('desc'):
                vals['description'] = group_metadata['desc']

            participants_data = group_metadata.get('participants', [])
            if participants_data:
                self._sync_wa_group_participants(participants_data)

            if vals:
                self.write(vals)
                _logger.info('Synced group info for channel %s', self.id)

        except Exception as e:
            _logger.error('Failed to sync group info for channel %s: %s', self.id, str(e))

    def action_sync_wa_group_participants(self):
        """Fetch and sync group participants from the WAHA API (UI button)."""
        self.ensure_one()

        if self.channel_type != 'waha' or '@g.us' not in (self.wa_chat_id or ''):
            raise UserError('This action is only available for WhatsApp group chats')

        try:
            api = WahaApi(self.whatsapp_account_id)
            group_info = api.get_group_info(self.wa_chat_id)

            if not group_info:
                raise UserError('Could not fetch group information from WhatsApp')

            group_metadata = group_info.get('groupMetadata', group_info)
            participants_data = group_metadata.get('participants', [])

            if not participants_data:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'No Participants',
                        'message': 'No participants found in this group',
                        'type': 'warning',
                        'sticky': False,
                    },
                }

            count = self._sync_wa_group_participants(participants_data)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Participants Synced',
                    'message': '%d participants synced successfully from WhatsApp' % count,
                    'type': 'success',
                    'sticky': False,
                },
            }

        except UserError:
            raise
        except Exception as e:
            _logger.error('Failed to sync group participants: %s', str(e))
            raise UserError('Failed to sync participants: %s' % str(e))

    # ------------------------------------------------------------------
    # Activity tracking
    # ------------------------------------------------------------------

    def _touch_wa_activity(self, message_time=None):
        """Bump the channel's last-activity timestamp (drives sidebar ordering)."""
        self.ensure_one()
        self.write({'last_interest_dt': message_time or fields.Datetime.now()})

    # ------------------------------------------------------------------
    # Notification preference filtering for WhatsApp channels
    # ------------------------------------------------------------------
    # Odoo only applies channel notification preferences (Todos / Solo
    # menciones / Nada) for channel_type='channel'.  Our WhatsApp channels
    # use channel_type='waha', which falls into the "notify everyone" branch
    # of _notify_get_recipients.  We override here to replicate the same
    # preference logic so each user's config is respected.
    # ------------------------------------------------------------------

    def _notify_get_recipients(self, message, msg_vals, **kwargs):
        recipients_data = super()._notify_get_recipients(message, msg_vals, **kwargs)

        if self.channel_type != 'waha':
            return recipients_data

        # Partner IDs that are explicitly @mentioned in this message.
        # For 'mentions only' preference, a recipient is notified only when
        # they appear in this list.
        pids = set(
            msg_vals.get('partner_ids', []) if msg_vals else message.partner_ids.ids
        )

        # Fetch every member's per-channel custom_notifications preference and
        # their global channel_notifications fallback in one query.
        members = self.env['discuss.channel.member'].sudo().search([
            ('channel_id', '=', self.id),
        ])
        # Map partner_id → (custom, global_pref)
        pref_map = {}
        for m in members:
            custom = m.custom_notifications  # 'all' | 'mentions' | 'no_notif' | False
            settings = (
                m.partner_id.user_ids[:1].res_users_settings_ids[:1]
                if m.partner_id.user_ids else self.env['res.users.settings']
            )
            global_pref = settings.channel_notifications if settings else False
            pref_map[m.partner_id.id] = (custom, global_pref)

        def _should_notify(partner_id):
            custom, global_pref = pref_map.get(partner_id, (False, False))
            # Per-channel override takes priority
            if custom == 'all':
                return True
            if custom == 'no_notif':
                return False
            if custom == 'mentions':
                return partner_id in pids
            # custom is False → fall back to global setting
            # global 'all'     → notify always
            # global 'no_notif'→ never notify
            # global False     → default = "mentions only"
            if global_pref == 'all':
                return True
            if global_pref == 'no_notif':
                return False
            # default (False / unset) = Solo menciones
            return partner_id in pids

        return [r for r in recipients_data if _should_notify(r['id'])]
