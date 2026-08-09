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
                # Only forward regular comment messages — not system notifications,
                # channel event messages, or automated bot messages.
                if result.message_type != 'comment':
                    _logger.info('Skipping WhatsApp send: message_type=%s', result.message_type)
                    return result

                # Only forward messages from active internal users.
                # This excludes: OdooBot, portal users, external contacts.
                author = result.author_id
                odoobot = self.env.ref('base.partner_root', raise_if_not_found=False)
                if not author or (odoobot and author == odoobot):
                    _logger.info('Skipping WhatsApp send: system/bot author (%s)', author.display_name if author else 'none')
                    return result
                internal_users = author.user_ids.filtered(lambda u: not u.share and u.active)
                if not internal_users:
                    _logger.info('Skipping WhatsApp send: author %s has no internal user account', author.display_name)
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
                
                # Get attachments from the message_post
                attachment_ids = kwargs.get('attachment_ids', [])
                
                # Create waha.message (will be sent automatically via _compute_msg_uid)
                try:
                    _logger.info('Creating waha.message for outbound send')
                    
                    # Get phone number from partner
                    waha_partner = self.env['waha.partner'].sudo().search([
                        ('partner_id', '=', partner.id),
                        ('wa_account_id', '=', wa_account.id)
                    ], limit=1)
                    
                    sender_phone = waha_partner.phone_number if waha_partner else partner.mobile or partner.phone
                    if sender_phone:
                        sender_phone = sender_phone.replace('+', '').replace(' ', '').replace('-', '')
                    
                    # Determine content type based on attachments
                    content_type = 'text'
                    if attachment_ids:
                        # Get first attachment to determine type
                        first_attachment = self.env['ir.attachment'].browse(attachment_ids[0][1] if isinstance(attachment_ids[0], tuple) else attachment_ids[0])
                        if first_attachment.exists():
                            if first_attachment.mimetype and first_attachment.mimetype.startswith('image/'):
                                content_type = 'image'
                            elif first_attachment.mimetype and first_attachment.mimetype.startswith('video/'):
                                content_type = 'video'
                            elif first_attachment.mimetype and first_attachment.mimetype.startswith('audio/'):
                                content_type = 'audio'
                            else:
                                content_type = 'document'
                    
                    mail_message = result if getattr(result, '_name', None) == 'mail.message' else self.env['mail.message'].browse(result).exists()

                    # Get reply_to if this is a reply to another message
                    reply_to_msg_uid = None
                    reply_to_message_id = False
                    parent_id = kwargs.get('parent_id')
                    if parent_id:
                        # Find the waha.message linked to this mail.message
                        parent_waha_message = self.env['waha.message'].sudo().search([
                            ('mail_message_id', '=', parent_id)
                        ], limit=1)
                        
                        if parent_waha_message and parent_waha_message.msg_uid:
                            reply_to_msg_uid = parent_waha_message.msg_uid
                            reply_to_message_id = parent_waha_message.id
                            _logger.info('Reply to message detected: parent_id=%s, msg_uid=%s', parent_id, reply_to_msg_uid)
                    
                    # Create waha.message with mail_message_id to prevent duplication
                    # Auto-send will happen via _compute_msg_uid
                    waha_message_vals = {
                        'wa_account_id': wa_account.id,
                        'discuss_channel_id': self.id,
                        'message_type': 'outbound',
                        'content_type': content_type,
                        'state': 'outgoing',
                        'body': message_body,
                        'raw_chat_id': self.wa_chat_id,
                        'raw_sender_phone': sender_phone,
                        'mail_message_id': mail_message.id if mail_message else False,
                        'reply_to_message_id': reply_to_message_id,
                        'reply_to_msg_uid': reply_to_msg_uid,
                    }
                    
                    waha_message = self.env['waha.message'].sudo().create(waha_message_vals)
                    
                    # Link attachments to waha.message
                    if attachment_ids:
                        _logger.info('Processing %d attachments for waha.message %s', len(attachment_ids), waha_message.id)
                        
                        # Handle different formats of attachment_ids
                        # Can be: [(6, 0, [1,2,3])], [(4, 1), (4, 2)], or [1, 2, 3]
                        attachment_records = self.env['ir.attachment']
                        
                        for att_cmd in attachment_ids:
                            if isinstance(att_cmd, (list, tuple)):
                                if att_cmd[0] == 6:  # (6, 0, [ids])
                                    attachment_records |= self.env['ir.attachment'].browse(att_cmd[2])
                                elif att_cmd[0] == 4:  # (4, id)
                                    attachment_records |= self.env['ir.attachment'].browse(att_cmd[1])
                            else:  # Direct ID
                                attachment_records |= self.env['ir.attachment'].browse(att_cmd)
                        
                        # Copy attachments to waha.message
                        for attachment in attachment_records:
                            if attachment.exists():
                                # Create a copy for waha.message
                                attachment.sudo().copy({
                                    'res_model': 'waha.message',
                                    'res_id': waha_message.id,
                                })
                                _logger.info('Copied attachment %s to waha.message %s', attachment.name, waha_message.id)

                    _logger.info('mail_message_id: %s', isinstance(result, int) and result or (result.id if result else 'None'))
                    
                    _logger.info('Created waha.message %s (type=%s, auto-send via compute, mail_msg: %s)', 
                                waha_message.id, content_type, waha_message.mail_message_id.id if waha_message.mail_message_id else None)
                except Exception as e:
                    _logger.warning('Error sending message: %s', str(e))
                    # Don't fail the post, just warn
                
                _logger.info('=== WhatsApp message_post() COMPLETED ===')
                    
            except Exception as e:
                _logger.exception('Error in WhatsApp message_post: %s', str(e))
        
        return result

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
