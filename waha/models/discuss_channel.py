# -*- coding: utf-8 -*-
from odoo import models, fields, api


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    # Extend channel_type selection to add WhatsApp
    channel_type = fields.Selection(
        selection_add=[('whatsapp', 'WhatsApp')],
        ondelete={'whatsapp': 'cascade'}
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
    
    @api.model
    def channel_get(self, partners_to=None, pin=True):
        """Override to handle WhatsApp channel creation"""
        # For WhatsApp channels, we don't want auto-creation through this method
        if self.env.context.get('default_channel_type') == 'whatsapp':
            return False
        return super().channel_get(partners_to=partners_to, pin=pin)
    
    def _channel_format(self, fields=None):
        """Ensure WhatsApp channels are properly formatted for frontend"""
        res = super()._channel_format(fields=fields)
        # WhatsApp channels should be treated as 'channel' type for sidebar display
        for channel_data in res:
            if channel_data.get('channel_type') == 'whatsapp':
                # Keep the whatsapp type but ensure it displays in CHANNELS section
                channel_data['is_whatsapp'] = True
        return res
