# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class WahaMessage(models.Model):
    """
    WAHA Message - Manages WhatsApp messages
    
    Responsibilities:
    - Store message content and metadata
    - Send messages through WAHA API
    - Update message status (sent, delivered, read, failed)
    - Create discuss.message entries in channels
    - Handle message attachments (media)
    - Link to waha.chat and res.partner
    
    Delegates:
    - Channel management → waha.chat
    - Contact management → waha.partner
    """
    _name = 'waha.message'
    _description = 'WhatsApp Message'
    _order = 'wa_timestamp desc, id desc'
    _rec_name = 'msg_uid'

    # ============================================================
    # FIELDS
    # ============================================================
    
    # Core identification
    msg_uid = fields.Char(
        string="WhatsApp Message ID",
        index=True,
        help="Unique message identifier from WAHA"
    )
    
    wa_account_id = fields.Many2one(
        'waha.account',
        string="WhatsApp Account",
        required=True,
        ondelete='cascade',
        index=True
    )
    
    # Message direction and type
    message_type = fields.Selection([
        ('outbound', 'Outbound'),
        ('inbound', 'Inbound')
    ], string="Direction", required=True, default='outbound', index=True)
    
    content_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('sticker', 'Sticker'),
        ('location', 'Location'),
    ], string="Content Type", default='text', required=True)
    
    # Message state
    state = fields.Selection([
        ('draft', 'Draft'),
        ('outgoing', 'Sending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('received', 'Received'),
        ('error', 'Failed'),
        ('cancel', 'Cancelled')
    ], string="State", default='draft', required=True, index=True)
    
    failure_type = fields.Selection([
        ('account', 'Account Error'),
        ('phone_invalid', 'Invalid Phone Number'),
        ('contact_not_found', 'Contact Not in WhatsApp'),
        ('network', 'Network Error'),
        ('unknown', 'Unknown Error')
    ], string="Failure Type")
    
    failure_reason = fields.Text(string="Failure Reason")
    
    # Content
    body = fields.Text(string="Message Content", required=True)
    
    # Raw WAHA identifiers (used to compute relationships)
    raw_chat_id = fields.Char(
        string="Raw Chat ID",
        help="Original chat ID from WAHA (e.g., 123456@c.us or 123456@g.us)"
    )
    
    raw_sender_phone = fields.Char(
        string="Raw Sender Phone",
        help="Sender's phone number (normalized, no symbols)"
    )
    
    # Links to other models (computed automatically)
    waha_chat_id = fields.Many2one(
        'waha.chat',
        string="Chat",
        compute='_compute_waha_chat_id',
        store=True,
        readonly=False,
        ondelete='set null',
        index=True,
        help="WhatsApp chat/conversation this message belongs to"
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string="Contact",
        compute='_compute_partner_id',
        store=True,
        readonly=False,
        ondelete='set null',
        index=True,
        help="Contact who sent/received this message"
    )
    
    mail_message_id = fields.Many2one(
        'mail.message',
        string="Discuss Message",
        ondelete='set null',
        help="Linked message in Discuss channel"
    )
    
    # Reply handling
    reply_to_message_id = fields.Many2one(
        'waha.message',
        string="Reply To",
        ondelete='set null',
        help="Original message this is replying to"
    )
    
    reply_to_msg_uid = fields.Char(
        string="Reply To Message UID",
        help="WAHA message UID to reply to"
    )
    
    # Attachments
    attachment_ids = fields.One2many(
        'ir.attachment',
        'res_id',
        domain=[('res_model', '=', 'waha.message')],
        string="Attachments"
    )
    
    # Timestamps
    wa_timestamp = fields.Datetime(
        string="WhatsApp Timestamp",
        help="Original timestamp from WhatsApp"
    )
    
    sent_date = fields.Datetime(string="Sent Date")
    delivered_date = fields.Datetime(string="Delivered Date")
    read_date = fields.Datetime(string="Read Date")
    
    # Metadata
    participant_id = fields.Char(
        string="Participant ID",
        help="For group messages: WhatsApp ID of the sender"
    )
    
    raw_payload = fields.Json(
        string="Raw WAHA Payload",
        help="Complete JSON payload from WAHA webhook"
    )
    
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('unique_msg_uid',
         'unique(msg_uid, wa_account_id)',
         "Each WhatsApp message ID must be unique per account.")
    ]

    # ============================================================
    # COMPUTED FIELDS - AUTO RELATIONSHIPS
    # ============================================================
    
    @api.depends('raw_chat_id', 'wa_account_id')
    def _compute_waha_chat_id(self):
        """
        Auto-compute chat relationship from raw_chat_id
        
        This ensures that waha_chat_id is always correctly set,
        regardless of how the message was created.
        """
        for message in self:
            if not message.raw_chat_id or not message.wa_account_id:
                message.waha_chat_id = False
                continue
            
            # Search for existing chat
            chat = self.env['waha.chat'].search([
                ('wa_chat_id', '=', message.raw_chat_id),
                ('wa_account_id', '=', message.wa_account_id.id)
            ], limit=1)
            
            if chat:
                message.waha_chat_id = chat
            else:
                # Auto-create chat if missing
                _logger.info('Auto-creating chat for raw_chat_id: %s', message.raw_chat_id)
                
                # Determine partner for 1-1 chats
                partner = None
                if message.partner_id:
                    partner = message.partner_id
                elif message.raw_sender_phone and '@g.us' not in message.raw_chat_id:
                    # Try to find partner for 1-1 chat
                    partner = self.env['waha.partner'].find_or_create_by_phone(
                        phone=message.raw_sender_phone,
                        wa_account=message.wa_account_id,
                        auto_enrich=False
                    )
                
                chat = self.env['waha.chat'].find_or_create(
                    wa_account=message.wa_account_id,
                    chat_id=message.raw_chat_id,
                    partner=partner
                )
                message.waha_chat_id = chat
    
    @api.depends('raw_sender_phone', 'wa_account_id', 'message_type')
    def _compute_partner_id(self):
        """
        Auto-compute partner relationship from raw_sender_phone
        
        For inbound messages: partner is the sender
        For outbound messages: partner is the recipient
        """
        for message in self:
            if not message.raw_sender_phone or not message.wa_account_id:
                message.partner_id = False
                continue
            
            # Search for existing waha.partner
            waha_partner = self.env['waha.partner'].search([
                ('phone_number', '=', message.raw_sender_phone),
                ('wa_account_id', '=', message.wa_account_id.id)
            ], limit=1)
            
            if waha_partner:
                message.partner_id = waha_partner.partner_id
            else:
                # Auto-create partner if missing
                _logger.info('Auto-creating partner for phone: %s', message.raw_sender_phone)
                
                partner = self.env['waha.partner'].find_or_create_by_phone(
                    phone=message.raw_sender_phone,
                    wa_account=message.wa_account_id,
                    auto_enrich=True
                )
                message.partner_id = partner

    # ============================================================
    # CREATE FROM WEBHOOK
    # ============================================================
    
    @api.model
    def create_from_webhook(self, webhook_payload, wa_account):
        """
        Create waha.message from WAHA webhook payload
        
        This is the main entry point for incoming messages.
        Orchestrates the creation of message, chat, and partner records.
        
        Args:
            webhook_payload: Complete webhook JSON from WAHA
            wa_account: waha.account record
            
        Returns:
            waha.message record
        """
        try:
            payload = webhook_payload.get('payload', {})
            msg_uid = payload.get('id')
            
            _logger.info('=== create_from_webhook: %s ===', msg_uid)
            
            # Check if already exists
            existing = self.search([
                ('msg_uid', '=', msg_uid),
                ('wa_account_id', '=', wa_account.id)
            ], limit=1)
            
            if existing:
                _logger.info('Message already exists: %s', existing.id)
                return existing
            
            # Extract message context
            context = self._extract_message_context(payload, wa_account)
            
            # Find or create partner
            WahaPartner = self.env['waha.partner']
            partner = WahaPartner.find_or_create_by_phone(
                phone=context['sender_phone'],
                wa_account=wa_account,
                auto_enrich=True
            )
            
            # Find or create chat
            WahaChat = self.env['waha.chat']
            chat = WahaChat.find_or_create(
                wa_account=wa_account,
                chat_id=context['chat_id'],
                partner=partner if not context['is_group'] else None
            )
            
            # Create waha.message
            message = self._create_message_record(context, wa_account, chat, partner)
            
            # Create discuss.message in channel
            discuss_channel = chat.get_or_create_discuss_channel()
            message._create_discuss_message(discuss_channel, partner, context)
            
            # Process media attachments
            if context['content_type'] != 'text':
                message._process_media_from_payload(payload, context['content_type'])
            
            # Update chat metadata
            chat.update_last_message(message.wa_timestamp)
            
            _logger.info('Successfully created message: %s', message.id)
            return message
            
        except Exception as e:
            _logger.exception('Error creating message from webhook: %s', str(e))
            raise
    
    def _extract_message_context(self, payload, wa_account):
        """
        Extract and normalize message context from WAHA payload
        
        Returns:
            dict with parsed message information
        """
        # Extract basic info
        from_raw = payload.get('from', '')
        from_me = payload.get('fromMe', False)
        participant = payload.get('participant', '')
        
        # Determine chat type
        is_group = '@g.us' in from_raw
        chat_id = from_raw
        
        # Extract sender phone
        if is_group and participant:
            sender_phone = participant.split('@')[0]
        else:
            sender_phone = from_raw.split('@')[0]
        
        # Extract content
        body = payload.get('body', '')
        if isinstance(body, dict):
            body = body.get('text', '') or str(body)
        elif not isinstance(body, str):
            body = str(body) if body else ''
        
        # Detect content type
        content_type = self._detect_content_type(payload)
        
        # Extract timestamp
        timestamp_value = payload.get('timestamp')
        wa_timestamp = None
        if timestamp_value:
            try:
                wa_timestamp = datetime.fromtimestamp(int(timestamp_value))
            except (ValueError, TypeError):
                wa_timestamp = fields.Datetime.now()
        
        return {
            'msg_uid': payload.get('id'),
            'from_me': from_me,
            'chat_id': chat_id,
            'is_group': is_group,
            'sender_phone': sender_phone,
            'participant': participant,
            'body': body,
            'content_type': content_type,
            'wa_timestamp': wa_timestamp or fields.Datetime.now(),
            'raw_payload': payload,
        }
    
    def _detect_content_type(self, payload):
        """Detect content type from WAHA payload"""
        if payload.get('location'):
            return 'location'
        
        if payload.get('hasMedia'):
            msg_type = payload.get('type', 'text')
            
            type_mapping = {
                'image': 'image',
                'video': 'video',
                'audio': 'audio',
                'document': 'document',
                'sticker': 'sticker',
                'ptt': 'audio',  # Push-to-talk voice message
            }
            
            return type_mapping.get(msg_type, 'document')
        
        return 'text'
    
    def _create_message_record(self, context, wa_account, chat, partner):
        """Create waha.message record from context"""
        vals = {
            'msg_uid': context['msg_uid'],
            'wa_account_id': wa_account.id,
            'message_type': 'outbound' if context['from_me'] else 'inbound',
            'content_type': context['content_type'],
            'state': 'sent' if context['from_me'] else 'received',
            'body': context['body'],
            'raw_chat_id': context['chat_id'],
            'raw_sender_phone': context['sender_phone'],
            'wa_timestamp': context['wa_timestamp'],
            'raw_payload': context['raw_payload'],
        }
        
        if context['participant']:
            vals['participant_id'] = context['participant']
        
        # Note: waha_chat_id and partner_id will be computed automatically
        # from raw_chat_id and raw_sender_phone
        message = self.create(vals)
        _logger.info('Created waha.message: %s (chat and partner auto-linked)', message.id)
        return message

    # ============================================================
    # DISCUSS MESSAGE CREATION
    # ============================================================
    
    def _create_discuss_message(self, discuss_channel, author_partner, context):
        """
        Create mail.message in the discuss channel
        
        Args:
            discuss_channel: discuss.channel record
            author_partner: res.partner (message author)
            context: Message context dict
        """
        self.ensure_one()
        
        # Clean HTML from body
        body_clean = re.sub(r'<[^>]+>', '', self.body).strip()
        
        # Create message in channel
        post_params = {
            'body': body_clean,
            'message_type': 'comment',
            'subtype_xmlid': 'mail.mt_comment',
            'author_id': author_partner.id,
        }
        
        if self.wa_timestamp:
            post_params['date'] = self.wa_timestamp
        
        # Use context flag to prevent recursion in mail_thread override
        discuss_msg = discuss_channel.with_context(
            skip_whatsapp_send=True
        ).message_post(**post_params)
        
        self.write({'mail_message_id': discuss_msg.id})
        _logger.info('Created discuss message: %s', discuss_msg.id)
        
        return discuss_msg

    # ============================================================
    # MEDIA ATTACHMENTS
    # ============================================================
    
    def _process_media_from_payload(self, payload, content_type):
        """
        Download and attach media from WAHA payload
        
        Args:
            payload: WAHA payload with media info
            content_type: Type of media (image, video, etc.)
        """
        self.ensure_one()
        
        media = payload.get('media', {})
        if not media:
            _logger.warning('No media in payload for %s', content_type)
            return
        
        # Get media data
        media_data = media.get('data')  # base64
        media_url = media.get('url')    # HTTP URL
        mimetype = media.get('mimetype') or self._get_default_mimetype(content_type)
        filename = media.get('filename') or self._get_default_filename(content_type)
        
        # Get binary data
        import base64
        import requests
        
        media_binary = None
        
        if media_data:
            try:
                media_binary = base64.b64decode(media_data)
            except Exception as e:
                _logger.error('Failed to decode base64 media: %s', str(e))
        
        elif media_url:
            try:
                # Fix localhost URLs
                if 'localhost' in media_url or '127.0.0.1' in media_url:
                    media_url = media_url.replace(
                        'http://localhost:3000',
                        self.wa_account_id.waha_url.rstrip('/')
                    )
                
                # Download with authentication
                headers = {}
                if self.wa_account_id.api_key:
                    headers['X-Api-Key'] = self.wa_account_id.api_key
                
                response = requests.get(media_url, headers=headers, timeout=30)
                response.raise_for_status()
                media_binary = response.content
            except Exception as e:
                _logger.error('Failed to download media from URL: %s', str(e))
        
        # Create attachment
        if media_binary:
            try:
                attachment = self.env['ir.attachment'].sudo().create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(media_binary),
                    'mimetype': mimetype,
                    'res_model': 'waha.message',
                    'res_id': self.id,
                })
                
                # Also link to mail.message if available
                if self.mail_message_id:
                    attachment.write({
                        'res_model': 'mail.message',
                        'res_id': self.mail_message_id.id,
                    })
                
                _logger.info('Created attachment: %s (%s)', filename, content_type)
            except Exception as e:
                _logger.error('Failed to create attachment: %s', str(e))
    
    def _get_default_mimetype(self, content_type):
        """Get default mimetype for content type"""
        defaults = {
            'image': 'image/jpeg',
            'video': 'video/mp4',
            'audio': 'audio/ogg',
            'document': 'application/pdf',
            'sticker': 'image/webp',
        }
        return defaults.get(content_type, 'application/octet-stream')
    
    def _get_default_filename(self, content_type):
        """Get default filename for content type"""
        defaults = {
            'image': 'image.jpg',
            'video': 'video.mp4',
            'audio': 'audio.ogg',
            'document': 'document.pdf',
            'sticker': 'sticker.webp',
        }
        return defaults.get(content_type, 'file.bin')

    # ============================================================
    # SEND MESSAGE (OUTBOUND)
    # ============================================================
    
    @api.model
    def send_message(self, chat, partner, body, reply_to=None, attachments=None):
        """
        Send a new outbound WhatsApp message
        
        Args:
            chat: waha.chat record
            partner: res.partner (recipient)
            body: Message text
            reply_to: waha.message to reply to (optional)
            attachments: ir.attachment records (optional)
            
        Returns:
            waha.message record
        """
        # Find phone number from partner
        waha_partner = self.env['waha.partner'].search([
            ('partner_id', '=', partner.id),
            ('wa_account_id', '=', chat.wa_account_id.id)
        ], limit=1)
        
        sender_phone = waha_partner.phone_number if waha_partner else partner.mobile or partner.phone
        if sender_phone:
            sender_phone = sender_phone.replace('+', '').replace(' ', '').replace('-', '')
        
        # Create waha.message record
        vals = {
            'wa_account_id': chat.wa_account_id.id,
            'message_type': 'outbound',
            'content_type': 'document' if attachments else 'text',
            'state': 'outgoing',
            'body': body,
            'raw_chat_id': chat.wa_chat_id,
            'raw_sender_phone': sender_phone,
        }
        
        # Note: waha_chat_id and partner_id will be computed automatically
        
        if reply_to:
            vals['reply_to_message_id'] = reply_to.id
            vals['reply_to_msg_uid'] = reply_to.msg_uid
        
        message = self.create(vals)
        _logger.info('Created outbound message: %s', message.id)
        
        # Link attachments
        if attachments:
            attachments.write({
                'res_model': 'waha.message',
                'res_id': message.id,
            })
        
        # Create discuss.message
        discuss_channel = chat.get_or_create_discuss_channel()
        admin_partner = self.env.ref('base.user_admin').sudo().partner_id
        
        message._create_discuss_message(
            discuss_channel,
            admin_partner,
            {'wa_timestamp': fields.Datetime.now()}
        )
        
        # Send through WAHA
        try:
            message._send_through_waha()
            chat.update_last_message()
            return message
        except Exception as e:
            # On failure: mark as error and delete discuss message
            message.write({
                'state': 'error',
                'failure_type': 'unknown',
                'failure_reason': str(e),
            })
            
            if message.mail_message_id:
                message.mail_message_id.unlink()
            
            raise
    
    def _send_through_waha(self):
        """Send this message through WAHA API"""
        self.ensure_one()
        
        if self.state != 'outgoing':
            raise UserError(_('Only outgoing messages can be sent'))
        
        if self.wa_account_id.status != 'connected':
            raise UserError(_('WhatsApp account is not connected'))
        
        _logger.info('Sending message %s through WAHA', self.id)
        
        try:
            from odoo.addons.waha.tools.waha_api import WahaApi
            api = WahaApi(self.wa_account_id)
            
            # Prepare message data
            chat_wa_id = self.waha_chat_id.wa_chat_id
            body_clean = re.sub(r'<[^>]+>', '', self.body).strip()
            
            message_data = {
                'chatId': chat_wa_id,
                'text': body_clean,
            }
            
            # Add reply_to if present
            if self.reply_to_msg_uid:
                message_data['reply_to'] = self.reply_to_msg_uid
            
            # Send based on content type
            if self.content_type == 'text':
                result = api.send_text(chat_wa_id, body_clean, self.reply_to_msg_uid)
            else:
                # Handle media sending
                if self.attachment_ids:
                    attachment = self.attachment_ids[0]
                    result = api.send_file(
                        chat_wa_id,
                        attachment.datas,
                        attachment.name,
                        attachment.mimetype,
                        body_clean
                    )
                else:
                    # Fallback to text
                    result = api.send_text(chat_wa_id, body_clean, self.reply_to_msg_uid)
            
            # Update message with result
            self.write({
                'state': 'sent',
                'msg_uid': result.get('id', ''),
                'sent_date': fields.Datetime.now(),
            })
            
            _logger.info('Message sent successfully: %s', result.get('id'))
            return result
            
        except Exception as e:
            error_msg = str(e)
            _logger.error('Failed to send message: %s', error_msg)
            
            # Classify error
            if 'No LID for user' in error_msg or 'not found' in error_msg.lower():
                failure_type = 'contact_not_found'
            elif 'Invalid session' in error_msg or 'not connected' in error_msg.lower():
                failure_type = 'account'
            else:
                failure_type = 'unknown'
            
            self.write({
                'state': 'error',
                'failure_type': failure_type,
                'failure_reason': error_msg,
            })
            
            raise

    # ============================================================
    # STATUS UPDATES
    # ============================================================
    
    def update_status_from_webhook(self, status_data):
        """
        Update message status from WAHA status webhook
        
        Args:
            status_data: Status webhook payload with 'ack' field
        """
        self.ensure_one()
        
        ack = status_data.get('ack', 0)
        
        # Map WAHA ACK to state
        state_mapping = {
            0: 'error',
            1: 'outgoing',
            2: 'sent',
            3: 'delivered',
            4: 'read',
            5: 'read',
        }
        
        new_state = state_mapping.get(ack, self.state)
        
        if new_state != self.state:
            vals = {'state': new_state}
            
            if new_state == 'sent' and not self.sent_date:
                vals['sent_date'] = fields.Datetime.now()
            elif new_state == 'delivered' and not self.delivered_date:
                vals['delivered_date'] = fields.Datetime.now()
            elif new_state == 'read' and not self.read_date:
                vals['read_date'] = fields.Datetime.now()
            
            self.write(vals)
            _logger.info('Updated message %s status: %s → %s', self.id, self.state, new_state)

    # ============================================================
    # ACTIONS
    # ============================================================
    
    def action_retry_send(self):
        """Retry sending failed messages"""
        for message in self:
            if message.state == 'error' and message.message_type == 'outbound':
                message.write({'state': 'outgoing'})
                try:
                    message._send_through_waha()
                except Exception as e:
                    _logger.error('Retry failed for message %s: %s', message.id, str(e))
    
    def action_view_discuss_message(self):
        """Open linked discuss message"""
        self.ensure_one()
        
        if not self.mail_message_id:
            raise UserError(_('No linked discuss message'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.message',
            'res_id': self.mail_message_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_chat(self):
        """Open chat form"""
        self.ensure_one()
        
        if not self.waha_chat_id:
            raise UserError(_('No linked chat'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'waha.chat',
            'res_id': self.waha_chat_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
