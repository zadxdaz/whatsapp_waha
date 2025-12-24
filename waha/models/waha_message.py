# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.addons.phone_validation.tools import phone_validation
from odoo.addons.waha.tools import phone_validation as wa_phone_validation
from odoo.addons.waha.tools.waha_api import WahaApi
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class WahaMessage(models.Model):
    _name = 'waha.message'
    _description = 'WhatsApp Messages'
    _order = 'id desc'
    _rec_name = 'mobile_number'

    # Supported attachment types
    _SUPPORTED_ATTACHMENT_TYPE = {
        'audio': ('audio/aac', 'audio/mp4', 'audio/mpeg', 'audio/amr', 'audio/ogg'),
        'document': (
            'text/plain', 'application/pdf', 'application/vnd.ms-powerpoint',
            'application/msword', 'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ),
        'image': ('image/jpeg', 'image/png'),
        'video': ('video/mp4',),
    }
    _ACTIVE_THRESHOLD_DAYS = 15

    mobile_number = fields.Char(string="Sent To", required=True)
    mobile_number_formatted = fields.Char(
        string="Mobile Number Formatted",
        compute="_compute_mobile_number_formatted",
        readonly=False,
        store=True
    )
    
    message_type = fields.Selection([
        ('outbound', 'Outbound'),
        ('inbound', 'Inbound')
    ], string="Message Type", default='outbound', required=True)
    
    state = fields.Selection([
        ('outgoing', 'In Queue'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('replied', 'Replied'),
        ('received', 'Received'),
        ('error', 'Failed'),
        ('bounced', 'Bounced'),
        ('cancel', 'Cancelled')
    ], string="State", default='outgoing', required=True)
    
    failure_type = fields.Selection([
        ('account', 'Account Error'),
        ('blacklisted', 'Blacklisted Phone Number'),
        ('network', 'Network Error'),
        ('outdated_channel', 'The channel is no longer active'),
        ('phone_invalid', 'Wrong Number Format'),
        ('unknown', 'Unknown Error'),
        ('waha_recoverable', 'Identified Error'),
        ('waha_unrecoverable', 'Other Technical Error')
    ], string="Failure Type")
    
    failure_reason = fields.Char(string="Failure Reason")
    
    free_text_json = fields.Json(string="Free Text Template Parameters")
    wa_template_id = fields.Many2one('waha.template', string="Template")
    msg_uid = fields.Char(string="WhatsApp Message ID", index=True)
    wa_account_id = fields.Many2one(
        'waha.account',
        string="WhatsApp Business Account",
        required=True
    )
    parent_id = fields.Many2one(
        'waha.message',
        string="Response To",
        index='btree_not_null',
        ondelete="set null"
    )
    
    mail_message_id = fields.Many2one('mail.message', string="Mail Message", index=True)
    body = fields.Html(string="Message Body")
    body_html = fields.Html(related='mail_message_id.body', string="Mail Body", related_sudo=False)

    _sql_constraints = [
        ('unique_msg_uid', 'unique(msg_uid)',
         "Each WhatsApp message should correspond to a single message UUID.")
    ]

    @api.depends('mobile_number')
    def _compute_mobile_number_formatted(self):
        """Format mobile number for display"""
        for message in self:
            recipient_partner = (
                message.mail_message_id.partner_ids[0]
                if message.mail_message_id.partner_ids
                else self.env['res.partner']
            )
            country = (
                recipient_partner.country_id
                if recipient_partner.country_id
                else self.env.company.country_id
            )
            formatted = wa_phone_validation.wa_phone_format(
                country,
                number=message.mobile_number,
                force_format="E164",
                raise_exception=False,
            )
            message.mobile_number_formatted = formatted or message.mobile_number

    def _send(self):
        """Send the WhatsApp message through WAHA"""
        self.ensure_one()
        
        if self.state != 'outgoing':
            _logger.warning('Message %s is not in outgoing state', self.id)
            return False
        
        if not self.wa_account_id:
            self.write({
                'state': 'error',
                'failure_type': 'account',
                'failure_reason': 'No WhatsApp account configured'
            })
            return False
        
        if self.wa_account_id.status != 'connected':
            self.write({
                'state': 'error',
                'failure_type': 'account',
                'failure_reason': 'WhatsApp account is not connected'
            })
            return False
        
        try:
            # Get message content
            body = self.mail_message_id.body if self.mail_message_id else ''
            
            # Prepare message data
            message_data = {
                'body': body,
            }
            
            # Add attachments if any
            if self.mail_message_id and self.mail_message_id.attachment_ids:
                attachment = self.mail_message_id.attachment_ids[0]
                import base64
                message_data['media_data'] = base64.b64encode(attachment.datas).decode()
                message_data['filename'] = attachment.name
                message_data['mimetype'] = attachment.mimetype
                message_data['caption'] = body
                
                # Determine message type from mimetype
                for msg_type, mimetypes in self._SUPPORTED_ATTACHMENT_TYPE.items():
                    if attachment.mimetype in mimetypes:
                        message_type = msg_type
                        break
                else:
                    message_type = 'document'
            else:
                message_type = 'text'
            
            # Send through WAHA
            result = self.wa_account_id._send_waha_message(
                self.mobile_number,
                message_type,
                **message_data
            )
            
            # Update message with result
            self.write({
                'state': 'sent',
                'msg_uid': result.get('id', ''),
            })
            
            return True
            
        except UserError as err:
            _logger.error('Error sending WAHA message %s: %s', self.id, str(err))
            self.write({
                'state': 'error',
                'failure_type': 'waha_unrecoverable',
                'failure_reason': str(err)
            })
            return False
        except Exception as err:
            _logger.error('Unexpected error sending message %s: %s', self.id, str(err))
            self.write({
                'state': 'error',
                'failure_type': 'unknown',
                'failure_reason': str(err)
            })
            return False

    def action_send(self):
        """Action to send message"""
        return self._send()

    def action_retry(self):
        """Retry sending failed messages"""
        for message in self:
            if message.state in ('error', 'bounced'):
                message.write({'state': 'outgoing'})
                message._send()

    @api.model
    def _process_incoming_webhook(self, webhook_data, account):
        """
        Process incoming message from webhook
        
        Args:
            webhook_data: Webhook payload from WAHA
            account: waha.account record
        """
        payload = webhook_data.get('payload', {})
        
        # Extract message data
        msg_uid = payload.get('id')
        from_number = payload.get('from', '').split('@')[0]
        body = payload.get('body', '')
        timestamp = payload.get('timestamp')
        
        # Check if message already exists
        existing = self.search([('msg_uid', '=', msg_uid)], limit=1)
        if existing:
            return existing
        
        # Find or create partner
        partner = self.env['res.partner']._find_or_create_from_number(
            from_number,
            payload.get('notifyName')
        )
        
        # Create message record
        message = self.create({
            'wa_account_id': account.id,
            'mobile_number': from_number,
            'msg_uid': msg_uid,
            'message_type': 'inbound',
            'state': 'received',
            'free_text_json': payload,
        })
        
        # Post to chatter if partner found
        if partner and hasattr(partner, 'message_post'):
            mail_message = partner.message_post(
                body=body,
                message_type='whatsapp',
                subtype_xmlid='mail.mt_comment',
            )
            message.mail_message_id = mail_message.id
        
        # Notify users
        if account.notify_user_ids:
            account.notify_user_ids._notify_incoming_whatsapp(message)
        
        return message
