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
    body = fields.Html('Message', required=True, sanitize=False)
    
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
    preview_body = fields.Html('Preview', compute='_compute_preview_body')

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
        
        # Clean HTML tags from body
        import re
        clean_body = re.sub(r'<[^>]+>', '', (self.preview_body or self.body)).strip()
        
        # Prepare message data
        message_vals = {
            'wa_account_id': self.wa_account_id.id,
            'mobile_number': self.mobile_number,
            'body': clean_body,
            'message_type': 'outbound',
        }
        
        if self.wa_template_id:
            message_vals['wa_template_id'] = self.wa_template_id.id
        
        # Create message
        message = self.env['waha.message'].create(message_vals)
        
        # Link to mail.message if we have a related record
        if self.res_model and self.res_id:
            try:
                record = self.env[self.res_model].browse(self.res_id)
                mail_message = record.message_post(
                    body=clean_body,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                    author_id=self.env.user.partner_id.id,
                )
                message.mail_message_id = mail_message.id
            except Exception:
                pass
        
        # Handle attachments
        if self.attachment_ids:
            for attachment in self.attachment_ids:
                # Send file message for each attachment
                try:
                    message.wa_account_id._send_waha_message(
                        self.mobile_number,
                        body=self.preview_body or self.body,
                        attachment=attachment
                    )
                except Exception as e:
                    message.write({
                        'state': 'error',
                        'failure_reason': str(e)
                    })
        
        # Send message
        try:
            message.action_send()
            
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
        except Exception as e:
            raise ValidationError(_('Failed to send message: %s') % str(e))

    def action_schedule_message(self):
        """Schedule message to be sent later"""
        self.ensure_one()
        
        # Create message in outgoing state
        message_vals = {
            'wa_account_id': self.wa_account_id.id,
            'mobile_number': self.mobile_number,
            'body': self.preview_body or self.body,
            'message_type': 'outbound',
            'state': 'outgoing',
        }
        
        if self.wa_template_id:
            message_vals['wa_template_id'] = self.wa_template_id.id
        
        message = self.env['waha.message'].create(message_vals)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Scheduled'),
                'message': _('Message scheduled to be sent'),
                'type': 'info',
                'sticky': False,
            }
        }
