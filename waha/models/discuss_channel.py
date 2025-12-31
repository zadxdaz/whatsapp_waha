# -*- coding: utf-8 -*-
from odoo import models, fields


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    is_whatsapp = fields.Boolean(
        string='Is WhatsApp Channel',
        default=False,
        help='Whether this is a WhatsApp conversation channel'
    )
    
    wa_chat_id = fields.Char(
        string='WhatsApp Chat ID',
        unique=True,
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
