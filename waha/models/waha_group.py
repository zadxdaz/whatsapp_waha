# -*- coding: utf-8 -*-
from odoo import fields, models, _


class WahaGroup(models.Model):
    _name = 'waha.group'
    _description = 'WhatsApp Group'
    _rec_name = 'name'

    name = fields.Char(
        string='Group Name',
        required=True,
        help='Name of the WhatsApp group'
    )
    
    group_id = fields.Char(
        string='Group ID',
        required=True,
        unique=True,
        help='Unique WhatsApp group ID (e.g., 123456789-1234567890@g.us)'
    )
    
    wa_account_id = fields.Many2one(
        'waha.account',
        string='WhatsApp Account',
        required=True,
        help='WhatsApp account this group belongs to'
    )
    
    member_ids = fields.Many2many(
        'res.partner',
        'waha_group_member_rel',
        'group_id',
        'partner_id',
        string='Members',
        help='Partners who are members of this group'
    )
    
    discuss_channel_id = fields.Many2one(
        'discuss.channel',
        string='Discussion Channel',
        help='Odoo discussion channel linked to this WhatsApp group'
    )
    
    active = fields.Boolean(
        default=True,
        help='Whether this group is still active'
    )
    
    created_date = fields.Datetime(
        string='Created',
        default=lambda self: fields.Datetime.now()
    )
    
    updated_date = fields.Datetime(
        string='Updated',
        default=lambda self: fields.Datetime.now()
    )
