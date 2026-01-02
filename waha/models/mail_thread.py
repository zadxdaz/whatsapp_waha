# -*- coding: utf-8 -*-
import logging
from odoo import api, models, _

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def message_post(self, **kwargs):
        """Override message_post to capture WhatsApp channel messages"""
        result = super().message_post(**kwargs)
        
        # Skip WhatsApp processing if flag is set (prevent recursion)
        if self.env.context.get('skip_whatsapp_send'):
            return result
        
        # Check if this is a WhatsApp channel
        if self._name == 'discuss.channel' and self.is_whatsapp:
            _logger.info('=== WhatsApp message_post() STARTED ===')
            _logger.info('Channel: %s (ID: %s)', self.name, self.id)
            
            try:
                # Don't send if author is a contact (incoming message)
                # Only send if author is a user (outgoing message)
                author_id = kwargs.get('author_id')
                current_user_partner = self.env.user.partner_id
                
                if author_id and author_id != current_user_partner.id:
                    _logger.info('Skipping WhatsApp send for incoming message from contact %s', author_id)
                    return result
                
                # Get account
                wa_account = self.whatsapp_account_id
                if not wa_account or wa_account.status != 'connected':
                    _logger.warning('WhatsApp account not available or not connected')
                    return result
                
                # Check if group (not supported yet)
                if self.whatsapp_group_id:
                    _logger.info('Group message - skipping (not yet implemented)')
                    return result
                
                # Get partner (contact) from channel
                admin_partner = self.env.ref('base.user_admin').sudo().partner_id
                partner = self.env['res.partner'].search(
                    [('id', 'in', self.channel_partner_ids.ids),
                     ('id', '!=', admin_partner.id)],
                    limit=1
                )
                
                if not partner:
                    _logger.warning('No partner found in channel %s', self.id)
                    return result
                
                # Get message body
                message_body = kwargs.get('body', '')
                
                # Get waha.chat for this channel
                waha_chat = self.env['waha.chat'].sudo().search([
                    ('discuss_channel_id', '=', self.id)
                ], limit=1)
                
                if not waha_chat:
                    _logger.warning('No waha.chat found for channel %s', self.id)
                    return result
                
                # Delegate to waha.message.send_message
                try:
                    _logger.info('Delegating to waha.message.send_message')
                    
                    # Create waha.message with mail_message_id already set to prevent duplication
                    waha_message = self.env['waha.message'].sudo().send_message(
                        chat=waha_chat,
                        partner=partner,
                        body=message_body,
                        reply_to=None,
                        attachments=None
                    )
                    
                    # Link the mail.message to waha.message to prevent auto-creation
                    if result and isinstance(result, int):
                        waha_message.sudo().write({
                            'mail_message_id': result
                        })
                        _logger.info('Linked mail.message %s to waha.message %s', 
                                    result, waha_message.id)
                    
                    _logger.info('Message created and sent: %s (msg_uid: %s)', 
                                waha_message.id, waha_message.msg_uid)
                except Exception as e:
                    _logger.warning('Error sending message: %s', str(e))
                    # Don't fail the post, just warn
                
                _logger.info('=== WhatsApp message_post() COMPLETED ===')
                    
            except Exception as e:
                _logger.exception('Error in WhatsApp message_post: %s', str(e))
        
        return result

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
