# -*- coding: utf-8 -*-
from odoo import models, fields, api


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
