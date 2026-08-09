# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WahaComposer(models.TransientModel):
    _name = 'waha.composer'
    _description = 'WhatsApp Message Composer'

    # Account and recipient
    wa_account_id = fields.Many2one(
        'waha.account',
        string='WhatsApp Account',
        required=True,
        domain=[('status', '=', 'connected')]
    )
    mobile_number = fields.Char('Phone Number', required=True)
    mobile_number_formatted = fields.Char(
        'Formatted Number',
        compute='_compute_mobile_number_formatted'
    )
    
    # Template
    wa_template_id = fields.Many2one('waha.template', string='Template')
    use_template = fields.Boolean('Use Template', default=False)
    
    # Message content
    body = fields.Text('Message', required=True)
    
    # Attachments
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'waha_composer_ir_attachments_rel',
        'composer_id',
        'attachment_id',
        string='Attachments'
    )
    
    # Related record
    res_model = fields.Char('Related Model')
    res_id = fields.Integer('Related Record ID')
    
    # Preview
    preview_body = fields.Text('Preview', compute='_compute_preview_body')

    @api.depends('mobile_number')
    def _compute_mobile_number_formatted(self):
        """Format phone number"""
        for composer in self:
            if composer.mobile_number:
                try:
                    from odoo.addons.waha.tools.phone_validation import format_phone_number
                    composer.mobile_number_formatted = format_phone_number(composer.mobile_number)
                except Exception:
                    composer.mobile_number_formatted = composer.mobile_number
            else:
                composer.mobile_number_formatted = ''

    @api.depends('body', 'wa_template_id', 'res_model', 'res_id')
    def _compute_preview_body(self):
        """Compute preview of message with variables replaced"""
        for composer in self:
            preview = composer.body or ''
            
            # If using template and have a related record, replace variables
            if composer.wa_template_id and composer.res_model and composer.res_id:
                try:
                    record = self.env[composer.res_model].browse(composer.res_id)
                    preview = composer.wa_template_id._get_formatted_body(record)
                except Exception:
                    pass
            
            composer.preview_body = preview

    @api.onchange('wa_template_id')
    def _onchange_wa_template_id(self):
        """Load template body when template is selected"""
        if self.wa_template_id:
            self.body = self.wa_template_id.body
            self.use_template = True
        else:
            self.use_template = False

    @api.onchange('use_template')
    def _onchange_use_template(self):
        """Clear template when use_template is unchecked"""
        if not self.use_template:
            self.wa_template_id = False

    def action_send_message(self):
        """Send WhatsApp message"""
        self.ensure_one()
        
        if not self.mobile_number:
            raise ValidationError(_('Phone number is required'))
        
        if not self.body:
            raise ValidationError(_('Message body is required'))
        
        # Get body content (already plain text)
        clean_body = (self.preview_body or self.body or '').strip()
        
        # Normalize phone number
        normalized_phone = self.mobile_number.replace('+', '').replace(' ', '').replace('-', '')
        chat_id = f"{normalized_phone}@c.us"

        # Resolve/create the WhatsApp channel (source of truth: discuss.channel)
        channel = self.env['discuss.channel'].find_or_create_wa(
            wa_account=self.wa_account_id,
            chat_id=chat_id,
        )
        
        # Prepare message data
        # discuss_channel_id and waha_partner_id will be auto-computed from raw fields
        message_vals = {
            'wa_account_id': self.wa_account_id.id,
            'discuss_channel_id': channel.id,
            'raw_chat_id': chat_id,
            'raw_sender_phone': normalized_phone,
            'body': clean_body,
            'message_type': 'outbound',
            'state': 'outgoing',  # Will trigger auto-send via _compute_msg_uid
        }
        
        if self.wa_template_id:
            message_vals['wa_template_id'] = self.wa_template_id.id
        
        # Create message
        # This will auto-compute: discuss_channel_id, waha_partner_id, mail_message_id, and msg_uid (send)
        message = self.env['waha.message'].create(message_vals)
        
        # Handle attachments - link them to the message
        if self.attachment_ids:
            self.attachment_ids.write({
                'res_model': 'waha.message',
                'res_id': message.id,
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('WhatsApp message sent successfully'),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_schedule_message(self):
        """Schedule message to be sent later"""
        self.ensure_one()
        
        # Get body content (already plain text)
        clean_body = (self.preview_body or self.body or '').strip()
        
        # Normalize phone number
        normalized_phone = self.mobile_number.replace('+', '').replace(' ', '').replace('-', '')
        chat_id = f"{normalized_phone}@c.us"

        # Resolve/create the WhatsApp channel (source of truth: discuss.channel)
        channel = self.env['discuss.channel'].find_or_create_wa(
            wa_account=self.wa_account_id,
            chat_id=chat_id,
        )
        
        # Create message in draft state (won't auto-send)
        message_vals = {
            'wa_account_id': self.wa_account_id.id,
            'discuss_channel_id': channel.id,
            'raw_chat_id': chat_id,
            'raw_sender_phone': normalized_phone,
            'body': clean_body,
            'message_type': 'outbound',
            'state': 'draft',  # Draft state prevents auto-send
        }
        
        if self.wa_template_id:
            message_vals['wa_template_id'] = self.wa_template_id.id
        
        # Create message - discuss_channel_id and waha_partner_id auto-computed
        message = self.env['waha.message'].create(message_vals)
        
        # Handle attachments
        if self.attachment_ids:
            self.attachment_ids.write({
                'res_model': 'waha.message',
                'res_id': message.id,
            })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Scheduled'),
                'message': _('Message scheduled. Change state to "Sending" to send it.'),
                'type': 'info',
                'sticky': False,
            }
        }
