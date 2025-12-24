# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # WhatsApp fields
    wa_account_id = fields.Many2one(
        'waha.account',
        string='WhatsApp Account',
        help='Default WhatsApp account for this contact'
    )
    
    # Statistics
    waha_message_ids = fields.One2many(
        'waha.message',
        'mobile_number',
        string='WhatsApp Messages',
        compute='_compute_waha_message_ids',
        store=False
    )
    waha_messages_count = fields.Integer(
        'WhatsApp Messages',
        compute='_compute_waha_messages_count'
    )

    @api.depends('mobile', 'phone')
    def _compute_waha_message_ids(self):
        """Get WhatsApp messages for this partner"""
        for partner in self:
            numbers = []
            if partner.mobile:
                numbers.append(partner.mobile)
            if partner.phone:
                numbers.append(partner.phone)
            
            if numbers:
                partner.waha_message_ids = self.env['waha.message'].search([
                    ('mobile_number', 'in', numbers)
                ])
            else:
                partner.waha_message_ids = self.env['waha.message']

    @api.depends('waha_message_ids')
    def _compute_waha_messages_count(self):
        """Count WhatsApp messages"""
        for partner in self:
            numbers = []
            if partner.mobile:
                numbers.append(partner.mobile)
            if partner.phone:
                numbers.append(partner.phone)
            
            if numbers:
                partner.waha_messages_count = self.env['waha.message'].search_count([
                    ('mobile_number', 'in', numbers)
                ])
            else:
                partner.waha_messages_count = 0

    def action_send_whatsapp_message(self):
        """Open WhatsApp composer"""
        self.ensure_one()
        
        if not self.mobile and not self.phone:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Phone Number'),
                    'message': _('This contact does not have a phone number.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        return {
            'name': _('Send WhatsApp Message'),
            'type': 'ir.actions.act_window',
            'res_model': 'waha.composer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': 'res.partner',
                'default_res_id': self.id,
                'default_mobile_number': self.mobile or self.phone,
                'default_wa_account_id': self.wa_account_id.id if self.wa_account_id else False,
            }
        }

    def action_view_whatsapp_messages(self):
        """View WhatsApp messages for this partner"""
        self.ensure_one()
        
        numbers = []
        if self.mobile:
            numbers.append(self.mobile)
        if self.phone:
            numbers.append(self.phone)
        
        return {
            'name': _('WhatsApp Messages'),
            'type': 'ir.actions.act_window',
            'res_model': 'waha.message',
            'view_mode': 'list,form',
            'domain': [('mobile_number', 'in', numbers)],
            'context': {'default_mobile_number': self.mobile or self.phone}
        }
