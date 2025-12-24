# -*- coding: utf-8 -*-
from odoo import api, models, _


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _message_send_whatsapp(self, template_id=None, numbers=None):
        """
        Send WhatsApp message for this record
        
        :param template_id: waha.template record ID
        :param numbers: List of phone numbers to send to
        :return: waha.message records created
        """
        self.ensure_one()
        
        if not numbers and hasattr(self, 'mobile'):
            numbers = [self.mobile] if self.mobile else []
        
        if not numbers:
            return self.env['waha.message']
        
        # Get template
        template = self.env['waha.template'].browse(template_id) if template_id else None
        
        if not template:
            return self.env['waha.message']
        
        # Get account
        wa_account = template.wa_account_id
        if not wa_account or wa_account.status != 'connected':
            return self.env['waha.message']
        
        # Format body
        body = template._get_formatted_body(self)
        
        # Create messages
        messages = self.env['waha.message']
        for number in numbers:
            message = self.env['waha.message'].create({
                'wa_account_id': wa_account.id,
                'mobile_number': number,
                'wa_template_id': template.id,
                'body': body,
                'message_type': 'outbound',
            })
            messages |= message
        
        # Send messages
        messages.action_send()
        
        return messages

    def action_send_whatsapp(self):
        """Open WhatsApp composer wizard"""
        self.ensure_one()
        
        return {
            'name': _('Send WhatsApp Message'),
            'type': 'ir.actions.act_window',
            'res_model': 'waha.composer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            }
        }
