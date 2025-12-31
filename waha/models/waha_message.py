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
        index=True,
        ondelete="set null"
    )
    
    reply_to_msg_uid = fields.Char(
        string="Reply To Message UID",
        help="WhatsApp message UID to reply to (used for linking responses to original messages)"
    )
    
    waha_chat_id = fields.Char(
        string="WAHA Chat ID",
        help="Chat ID in WAHA format (e.g., 11932090237110@lid or 123456@c.us). Used for sending messages."
    )
    
    mail_message_id = fields.Many2one('mail.message', string="Mail Message", index=True)
    body = fields.Html(string="Message Body")
    body_html = fields.Html(related='mail_message_id.body', string="Mail Body", related_sudo=False)
    
    participant_id = fields.Char(
        string="Participant ID",
        help="WhatsApp participant ID (for group messages, the person who sent it). Format: e.g., 69814777340003@lid"
    )
    
    wa_timestamp = fields.Datetime(
        string="WhatsApp Timestamp",
        help="Original timestamp from WhatsApp message (when the message was sent/received in WhatsApp)"
    )

    _sql_constraints = [
        ('unique_msg_uid', 'unique(msg_uid)',
         "Each WhatsApp message should correspond to a single message UUID.")
    ]

    def has_discuss_message(self):
        """Check if this waha.message has an associated discuss message"""
        self.ensure_one()
        return bool(self.mail_message_id and self.mail_message_id.exists())
    
    def get_or_create_discuss_message(self):
        """
        Get existing discuss message or create one if missing
        
        This is useful for fixing data inconsistencies or importing
        historical messages that weren't properly linked.
        
        Returns:
            mail.message record
        """
        self.ensure_one()
        
        if self.has_discuss_message():
            return self.mail_message_id
        
        _logger.info('Creating missing discuss message for waha.message %s', self.id)
        
        # Find partner and channel
        partner = self.env['res.partner'].sudo().search([
            ('mobile', 'ilike', self.mobile_number)
        ], limit=1)
        
        if not partner:
            _logger.warning('Cannot create discuss message: partner not found for %s', self.mobile_number)
            return self.env['mail.message']
        
        # Find channel
        channel = self.env['discuss.channel'].sudo().search([
            ('wa_chat_id', '=', self.waha_chat_id),
            ('is_whatsapp', '=', True),
        ], limit=1)
        
        if not channel:
            _logger.warning('Cannot create discuss message: channel not found for %s', self.waha_chat_id)
            return self.env['mail.message']
        
        # Determine author
        if self.message_type == 'outbound':
            author = self.env.user.partner_id
        else:
            author = partner
        
        # Create discuss message
        discuss_msg = self.find_or_create_discuss_message(
            waha_msg=self,
            channel=channel,
            partner=author
        )
        
        # Add partner to channel if not already a member (useful for groups)
        if partner not in channel.channel_partner_ids:
            channel.write({
                'channel_partner_ids': [(4, partner.id)]
            })
            _logger.info('Added partner %s to channel %s', partner.id, channel.id)
        
        self.write({'mail_message_id': discuss_msg.id})
        return discuss_msg

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
        
        _logger.info('=== waha.message._send() STARTED ===')
        _logger.info('Message ID: %s', self.id)
        _logger.info('Current State: %s', self.state)
        _logger.info('Phone Number: %s', self.mobile_number)
        _logger.info('Account: %s (ID: %s)', self.wa_account_id.name, self.wa_account_id.id)
        
        if self.state != 'outgoing':
            _logger.warning('Message %s is not in outgoing state: %s', self.id, self.state)
            return False
        
        if not self.wa_account_id:
            _logger.error('Message %s has no WhatsApp account configured', self.id)
            self.write({
                'state': 'error',
                'failure_type': 'account',
                'failure_reason': 'No WhatsApp account configured'
            })
            return False
        
        if self.wa_account_id.status != 'connected':
            _logger.error('WhatsApp account %s status is not connected: %s', 
                         self.wa_account_id.name, self.wa_account_id.status)
            self.write({
                'state': 'error',
                'failure_type': 'account',
                'failure_reason': f'WhatsApp account status is {self.wa_account_id.status}, not connected'
            })
            return False
        
        try:
            # Get message content and clean HTML tags
            import re
            raw_body = self.mail_message_id.body if self.mail_message_id else self.body or ''
            body = re.sub(r'<[^>]+>', '', raw_body).strip()
            _logger.info('Message body length: %d chars', len(body))
            
            _logger.info('Preparing to send message %s to %s (account: %s)', 
                        self.id, self.mobile_number, self.wa_account_id.name)
            
            # Prepare message data
            message_data = {
                'body': body,
            }
            
            # Add reply_to if this message is replying to another
            if self.reply_to_msg_uid:
                message_data['reply_to_msg_uid'] = self.reply_to_msg_uid
                _logger.info('Message %s is replying to: %s', self.id, self.reply_to_msg_uid)
            
            # Add attachments if any
            if self.mail_message_id and self.mail_message_id.attachment_ids:
                attachment = self.mail_message_id.attachment_ids[0]
                import base64
                message_data['media_data'] = base64.b64encode(attachment.datas).decode()
                message_data['filename'] = attachment.name
                message_data['mimetype'] = attachment.mimetype
                message_data['caption'] = body
                
                _logger.info('Message %s has attachment: %s (%s)', 
                            self.id, attachment.name, attachment.mimetype)
                
                # Determine message type from mimetype
                for msg_type, mimetypes in self._SUPPORTED_ATTACHMENT_TYPE.items():
                    if attachment.mimetype in mimetypes:
                        message_type = msg_type
                        break
                else:
                    message_type = 'document'
            else:
                message_type = 'text'
            
            _logger.info('Calling WAHA API: type=%s, phone=%s, body_len=%d', 
                        message_type, self.mobile_number, len(body))
            
            # Send through WAHA - pass waha_chat_id if available
            if self.waha_chat_id:
                message_data['waha_chat_id'] = self.waha_chat_id
                _logger.info('Passing waha_chat_id to WAHA API: %s', self.waha_chat_id)
            
            # Send through WAHA
            result = self.wa_account_id._send_waha_message(
                self.mobile_number,
                message_type,
                **message_data
            )
            
            _logger.info('=== WAHA API Response ===')
            _logger.info('Message %s sent successfully', self.id)
            _logger.info('Response message ID: %s', result.get('id', 'N/A'))
            _logger.debug('Full response: %s', result)
            
            # Update message with result
            self.write({
                'state': 'sent',
                'msg_uid': result.get('id', ''),
            })
            
            _logger.info('=== waha.message._send() COMPLETED ===')
            return True
            
        except UserError as err:
            error_msg = str(err)
            _logger.error('UserError sending message %s: %s', self.id, error_msg)
            self.write({
                'state': 'error',
                'failure_type': 'waha_unrecoverable',
                'failure_reason': error_msg
            })
            return False
        except Exception as err:
            error_msg = str(err)
            
            # Detect specific error types
            if 'No LID for user' in error_msg:
                failure_type = 'waha_recoverable'
                failure_reason = f'Contact not found in WhatsApp. Please ensure the contact exists. Error: {error_msg}'
                _logger.warning('Message %s failed - contact not found: %s', self.id, self.mobile_number)
            elif 'Invalid session' in error_msg or 'ENOTCONNECTED' in error_msg:
                failure_type = 'account'
                failure_reason = 'WhatsApp session disconnected'
                _logger.error('Message %s failed - session error: %s', self.id, error_msg)
            else:
                failure_type = 'unknown'
                failure_reason = error_msg
                _logger.error('Unexpected error sending message %s: %s', self.id, error_msg, exc_info=True)
            
            self.write({
                'state': 'error',
                'failure_type': failure_type,
                'failure_reason': failure_reason
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

    # ============================================================
    # MESSAGE CREATION FROM API RESPONSE
    # ============================================================

    @api.model
    def create_from_api_response(self, account, msg_data, chat_id=None):
        """
        Create waha.message from WAHA API response JSON
        
        This method intelligently creates a message record from any WAHA API
        message format (webhook, get_messages, etc.) and automatically:
        - Detects message direction (inbound/outbound)
        - Handles group participant extraction
        - Creates/finds partner and channel
        - Creates discuss message
        - Links everything together
        
        Args:
            account: waha.account record
            msg_data: dict - Message JSON from WAHA API
            chat_id: str - Optional chat_id if not in msg_data
            
        Returns:
            waha.message record (created or existing)
            
        Example msg_data formats:
            {
                "id": "false_5491121928204@c.us_...",
                "from": "5491121928204@c.us",
                "fromMe": false,
                "body": "Hello",
                "timestamp": 1234567890,
                "participant": "5491198765432@c.us"  # Only in groups
            }
        """
        _logger.info('=== create_from_api_response START ===')
        _logger.info('Message ID: %s', msg_data.get('id'))
        
        # Step 1: Check if already exists
        msg_uid = msg_data.get('id', 'unknown')
        existing = self.search([('msg_uid', '=', msg_uid)], limit=1)
        if existing:
            _logger.info('Message already exists: %s', existing.id)
            return existing
        
        # Step 2: Extract basic info
        msg_body = msg_data.get('body', '')
        from_me = msg_data.get('fromMe', False)
        
        # Extract from/chat_id
        from_obj = msg_data.get('from', {})
        if isinstance(from_obj, dict):
            from_id = from_obj.get('_serialized', from_obj.get('user', 'Unknown'))
        else:
            from_id = str(from_obj) if from_obj else 'Unknown'
        
        # Use provided chat_id or from_id
        actual_chat_id = chat_id or from_id
        
        # Detect if group
        is_group = '@g.us' in actual_chat_id
        
        # Get participant for group messages
        participant = msg_data.get('participant', '') if is_group else ''
        
        # Normalize sender number
        sender_number = from_id.replace('@c.us', '').replace('@g.us', '').replace('@lid', '').split('@')[0]
        
        # For groups with participant, use it for participant_id
        if is_group and participant:
            participant_id = participant
        else:
            participant_id = from_id
        
        # Extract timestamp (WAHA uses Unix timestamp in seconds)
        timestamp_value = msg_data.get('timestamp')
        wa_timestamp = None
        if timestamp_value:
            from datetime import datetime
            try:
                # Convert Unix timestamp to datetime
                wa_timestamp = datetime.fromtimestamp(int(timestamp_value))
            except (ValueError, TypeError) as e:
                _logger.warning('Invalid timestamp %s: %s', timestamp_value, str(e))
        
        # Step 3: Create waha.message record
        vals = {
            'wa_account_id': account.id,
            'mobile_number': sender_number,
            'msg_uid': msg_uid,
            'message_type': 'outbound' if from_me else 'inbound',
            'state': 'sent' if from_me else 'received',
            'body': msg_body[:1000] if msg_body else '',
            'waha_chat_id': actual_chat_id,
        }
        
        if not from_me:
            vals['participant_id'] = participant_id
        
        if wa_timestamp:
            vals['wa_timestamp'] = wa_timestamp
        
        waha_msg = self.create(vals)
        _logger.info('Created waha.message: %s', waha_msg.id)
        
        # Step 4: Find/create partner and channel for ALL messages
        if from_me:
            # For outbound messages, recipient is the partner, author is current user
            partner = self.find_or_create_contact(waha_msg=waha_msg)
            author = self.env.user.partner_id
        else:
            # For inbound messages, sender is both partner and author
            author = self.find_or_create_contact(waha_msg=waha_msg)
            partner = author
        
        _logger.info('Partner resolved: %s (ID: %s)', partner.name, partner.id)
        
        # Step 5: Find/create channel
        channel = self.find_or_create_channel(waha_msg=waha_msg, partner=partner)
        _logger.info('Channel resolved: %s (ID: %s)', channel.name, channel.id)
        
        # Step 6: Create discuss message for ALL messages (inbound and outbound)
        # The skip_whatsapp_send flag prevents mail_thread.py from trying to send again
        discuss_msg = self.find_or_create_discuss_message(
            waha_msg=waha_msg,
            channel=channel,
            partner=author
        )
        
        # Step 7: Link messages
        waha_msg.write({'mail_message_id': discuss_msg.id})
        _logger.info('Discuss message created and linked: %s', discuss_msg.id)
        
        # Step 8: Process media attachments (images, stickers, etc.)
        msg_type = waha_msg._detect_message_type(msg_data)
        if msg_type in ('image', 'sticker', 'audio', 'video', 'document'):
            waha_msg.process_media_attachments(msg_data, msg_type)
        
        _logger.info('=== create_from_api_response END ===')
        return waha_msg

    # ============================================================
    # INBOUND FLOW: Webhook → waha.message → discuss.message
    # ============================================================

    @api.model
    def process_inbound_webhook(self, webhook_payload, account):
        """
        ORCHESTRATOR: Process incoming message from WAHA webhook
        
        Responsibilities:
        - Validate payload
        - Deduplicate (avoid double processing)
        - Find/create contact
        - Find/create channel
        - Create waha.message inbound
        - Create discuss.message
        - Enrich contact data from WAHA
        
        Args:
            webhook_payload: Full webhook data from WAHA (contains 'payload' key)
            account: waha.account record
            
        Returns:
            waha.message record (created or existing)
        """
        try:
            payload = webhook_payload.get('payload', {})
            _logger.info('=== INBOUND: process_inbound_webhook START ===')
            _logger.info('Message ID: %s', payload.get('id'))
            _logger.info('From: %s', payload.get('from'))
            
            # Step 1: Deduplicate
            existing = self.deduplicate_inbound(payload.get('id'))
            if existing:
                _logger.info('Message already exists: %s', existing.id)
                return existing
            
            # Step 2: Extract and normalize context
            msg_context = self._extract_inbound_context(payload, account)
            _logger.info('Extracted context - Is group: %s, Sender: %s', 
                        msg_context['is_group'], msg_context['sender_number'])
            
            # Step 3: Create waha.message FIRST (so we have all the info)
            message = self.create_inbound_message(account, None, None, msg_context, payload)
            _logger.info('waha.message created: %s', message.id)
            
            # Step 4: Find or create contact (using waha.message)
            partner = self.find_or_create_contact(waha_msg=message)
            _logger.info('Contact resolved: %s (ID: %s)', partner.name, partner.id)
            
            # Step 5: Find or create channel (using waha.message)
            channel = self.find_or_create_channel(waha_msg=message, partner=partner)
            _logger.info('Channel resolved: %s (ID: %s)', channel.name, channel.id)
            
            # Step 6: Create discuss.message (using waha.message)
            discuss_msg = self.find_or_create_discuss_message(
                message, channel, partner
            )
            message.write({'mail_message_id': discuss_msg.id})
            _logger.info('discuss.message created: %s', discuss_msg.id)
            
            # Step 7: Process media attachments (images, stickers, etc.)
            if msg_context['message_type'] in ('image', 'sticker', 'audio', 'video', 'document'):
                message.process_media_attachments(payload, msg_context['message_type'])
            
            # Step 8: Enrich contact (async/best-effort)
            self.env['res.partner'].sudo().browse(partner.id).enrich_contact_from_waha(account)
            
            _logger.info('=== INBOUND: process_inbound_webhook END ===')
            return message
            
        except Exception as e:
            _logger.exception('Error in process_inbound_webhook: %s', str(e))
            raise

    def _extract_inbound_context(self, payload, account):
        """
        Extract and normalize inbound message context
        
        Returns dict with:
        - msg_uid: External message ID
        - from_number: Sender phone (normalized)
        - sender_number: Actual sender (group member or sender)
        - participant: Raw participant field (for groups)
        - chat_id: WAHA chat ID
        - is_group: Boolean
        - body: Message text
        - timestamp: Message timestamp
        - message_type: 'text' | 'image' | etc
        """
        from_raw = payload.get('from', '')
        participant = payload.get('participant', '')
        chat_id = payload.get('from', '')  # WAHA uses 'from' as chat ID
        
        # Normalize phone numbers
        from_number = from_raw.replace('@c.us', '').replace('@lid', '').replace('@g.us', '')
        
        # Detect group
        is_group = '@g.us' in from_raw
        
        # Extract sender (for group messages)
        if is_group and participant:
            sender_number = participant.split('@')[0]
        else:
            sender_number = from_number
        
        return {
            'msg_uid': payload.get('id'),
            'from_number': from_number,
            'sender_number': sender_number,
            'participant': participant,
            'chat_id': chat_id,
            'is_group': is_group,
            'chat_name': payload.get('chatName', ''),
            'body': payload.get('body', ''),
            'timestamp': payload.get('timestamp'),
            'message_type': self._detect_message_type(payload),
        }

    def deduplicate_inbound(self, external_message_id):
        """
        Check if message already exists in DB
        
        Args:
            external_message_id: WAHA message ID (msg_uid)
            
        Returns:
            waha.message record if exists, False otherwise
        """
        existing = self.search([('msg_uid', '=', external_message_id)], limit=1)
        return existing if existing else False

    def find_or_create_contact(self, waha_msg=None, msg_context=None):
        """
        Find or create res.partner for sender
        
        Args:
            waha_msg: waha.message record (optional, uses msg_context if not provided)
            msg_context: dict from _extract_inbound_context (legacy webhook support)
            
        Returns:
            res.partner record
        """
        # Extract info from waha_msg or msg_context
        if waha_msg:
            account = waha_msg.wa_account_id
            chat_id = waha_msg.waha_chat_id
            is_group = '@g.us' in (chat_id or '')
            
            # For groups, use participant_id; otherwise use mobile_number
            if is_group and waha_msg.participant_id:
                sender_number = waha_msg.participant_id.split('@')[0]
            else:
                sender_number = waha_msg.mobile_number
        elif msg_context:
            # Legacy webhook support
            account = self.env['waha.account']  # Will be passed separately in webhook
            sender_number = msg_context.get('sender_number')
            chat_id = msg_context.get('chat_id')
            is_group = msg_context.get('is_group', False)
            if is_group and msg_context.get('participant'):
                sender_number = msg_context['participant'].split('@')[0]
        else:
            raise ValueError('Either waha_msg or msg_context must be provided')
        
        _logger.info('find_or_create_contact: sender=%s, is_group=%s', sender_number, is_group)
        
        partner = self.env['res.partner'].sudo().search([
            ('mobile', 'ilike', sender_number)
        ], limit=1)
        
        if not partner:
            # Get contact info from WhatsApp before creating partner
            contact_name = sender_number  # Default fallback
            contact_image = None
            
            if waha_msg and account:
                try:
                    from odoo.addons.waha.tools.waha_api import WahaApi
                    api = WahaApi(account)
                
                    # Try to get contact info from WAHA for regular contacts
                    contact_info = api.get_contact(sender_number)
                    if contact_info:
                        # Extract name (try different fields)
                        contact_name = (
                            contact_info.get('name') or 
                            contact_info.get('pushname') or 
                            contact_info.get('pushName') or
                            contact_info.get('verifiedName') or
                            sender_number
                        )
                        _logger.info('Got contact name from WAHA: %s', contact_name)
                        
                        # Get profile picture
                        contact_id = contact_info.get('id')
                        if not contact_id:
                            # Build contact ID
                            contact_id = f"{sender_number}@c.us"
                        
                            profile_pic_url = api.get_contact_profile_picture(contact_id)
                            if profile_pic_url:
                                try:
                                    import requests
                                    import base64
                                    
                                    # Fix URL if it uses localhost (replace with actual WAHA server)
                                    if 'localhost' in profile_pic_url or '127.0.0.1' in profile_pic_url:
                                        profile_pic_url = profile_pic_url.replace('http://localhost:3000', account.waha_url.rstrip('/'))
                                        profile_pic_url = profile_pic_url.replace('http://127.0.0.1:3000', account.waha_url.rstrip('/'))
                                        _logger.info('Fixed profile picture URL: %s', profile_pic_url)
                                    
                                    # Prepare headers with authentication
                                    headers = {}
                                    if account.api_key:
                                        headers['X-Api-Key'] = account.api_key
                                    
                                    response = requests.get(profile_pic_url, headers=headers, timeout=10)
                                    response.raise_for_status()
                                    contact_image = base64.b64encode(response.content)
                                    _logger.info('Downloaded profile picture for %s', contact_name)
                                except Exception as e:
                                    _logger.warning('Failed to download profile picture: %s', str(e))
                
                except Exception as e:
                    _logger.warning('Could not get contact info from WAHA (non-critical): %s', str(e))
            
            # Create new partner
            partner_vals = {
                'name': contact_name,
                'mobile': f"+{sender_number}",
                'phone': f"+{sender_number}",
            }
            if contact_image:
                partner_vals['image_1920'] = contact_image
            if waha_msg:
                partner_vals['wa_account_id'] = account.id
            if chat_id and not is_group:  # Only set wa_chat_id for 1-1 chats
                partner_vals['wa_chat_id'] = chat_id
            
            partner = self.env['res.partner'].sudo().create(partner_vals)
            _logger.info('Created new partner: %s with name: %s', partner.id, contact_name)
        else:
            # Update wa_chat_id if needed (only for 1-1 chats)
            if chat_id and not is_group and (not partner.wa_chat_id or partner.wa_chat_id != chat_id):
                update_vals = {'wa_chat_id': chat_id}
                if waha_msg:
                    update_vals['wa_account_id'] = account.id
                partner.write(update_vals)
                _logger.info('Updated partner wa_chat_id: %s', chat_id)
        
        return partner

    def find_or_create_channel(self, waha_msg, partner, msg_context=None):
        """
        Find or create discuss.channel for this conversation
        
        Args:
            waha_msg: waha.message record (uses its waha_chat_id, wa_account_id)
            partner: res.partner (for channel name)
            msg_context: dict from _extract_inbound_context (legacy webhook support)
            
        Returns:
            discuss.channel record
        """
        api = WahaApi(waha_msg.wa_account_id)
        # Extract info from waha_msg or msg_context
        if waha_msg:
            account = waha_msg.wa_account_id
            chat_id = waha_msg.waha_chat_id
            is_group = '@g.us' in (chat_id or '')
            chat_name = ''  # Could be added to waha.message model if needed
            sender_number = waha_msg.mobile_number
        elif msg_context:
            # Legacy webhook support
            account = None  # Will need to be passed
            chat_id = msg_context.get('chat_id')
            chat_name = msg_context.get('chat_name', '')
            is_group = msg_context.get('is_group', False)
            sender_number = msg_context.get('sender_number')
        else:
            raise ValueError('Either waha_msg or msg_context must be provided')
        
        # Determine channel name and search key
        if is_group:
            channel_name = f"WA Group: {chat_name or chat_id}"
            search_key = chat_id
        else:
            channel_name = f"WA: {partner.name}"
            search_key = chat_id or sender_number
        
        # Search for existing channel by wa_chat_id or description
        if chat_id:
            channel = self.env['discuss.channel'].sudo().search([
                ('wa_chat_id', '=', chat_id),
                ('is_whatsapp', '=', True),
                ('whatsapp_account_id', '=', account.id),
            ], limit=1)
        else:
            channel = self.env['discuss.channel'].sudo().search([
                ('description', '=', search_key),
                ('is_whatsapp', '=', True),
                ('whatsapp_account_id', '=', account.id),
            ], limit=1)
        
        if not channel:
            group_info = api.get_group_info(chat_id) if is_group else None
            if is_group and group_info:
                channel_name = group_info.get('name') or chat_id
            # Create new channel
            channel_vals = {
                'name': channel_name,
                'channel_type': 'channel',  # Always 'channel' for WhatsApp (groups and 1-1)
                'description': search_key,
                'is_whatsapp': True,
                'whatsapp_account_id': account.id,
            }
            if chat_id:
                channel_vals['wa_chat_id'] = chat_id
            
            channel = self.env['discuss.channel'].sudo().create(channel_vals)
            _logger.info('Created new channel: %s', channel.id)
            
            # Add members
            admin = self.env.ref('base.user_admin').sudo()
            channel.write({
                'channel_partner_ids': [(4, partner.id), (4, admin.partner_id.id)]
            })
        
        return channel

    def create_inbound_message(self, account, partner, channel, msg_context, payload):
        """
        Create waha.message inbound record
        
        Args:
            account: waha.account
            partner: res.partner (sender) - OPTIONAL, can be None
            channel: discuss.channel - OPTIONAL, can be None
            msg_context: dict from _extract_inbound_context
            payload: Full WAHA payload
            
        Returns:
            waha.message record
        """
        # Parse content based on message type
        body_text = self.parse_content_from_payload(payload, msg_context)
        
        # Extract timestamp
        timestamp_value = msg_context.get('timestamp')
        wa_timestamp = None
        if timestamp_value:
            from datetime import datetime
            try:
                wa_timestamp = datetime.fromtimestamp(int(timestamp_value))
            except (ValueError, TypeError) as e:
                _logger.warning('Invalid timestamp %s: %s', timestamp_value, str(e))
        
        vals = {
            'wa_account_id': account.id,
            'mobile_number': msg_context['sender_number'],
            'msg_uid': msg_context['msg_uid'],
            'message_type': 'inbound',
            'state': 'received',
            'body': body_text,
            'participant_id': msg_context['participant'],
            'waha_chat_id': msg_context['chat_id'],
            'free_text_json': payload,
        }
        
        if wa_timestamp:
            vals['wa_timestamp'] = wa_timestamp
        
        message = self.create(vals)
        _logger.info('Created waha.message %s', message.id)
        return message

    def find_or_create_discuss_message(self, waha_msg, channel, partner, msg_context=None):
        """
        Create discuss.message (mail.message) in the channel
        
        Args:
            waha_msg: waha.message record (uses its body field)
            channel: discuss.channel
            partner: res.partner (sender/author)
            msg_context: dict from _extract_inbound_context (legacy webhook support)
            
        Returns:
            mail.message record
        """
        import re
        
        # Get body from waha_msg or msg_context
        if msg_context and 'body' in msg_context:
            body_text = msg_context['body']
        else:
            body_text = waha_msg.body or ''
        
        # Handle case where body_text might be a dict or other non-string type
        if isinstance(body_text, dict):
            # Try to extract text from common dict structures
            body_text = body_text.get('text', '') or body_text.get('body', '') or str(body_text)
        elif not isinstance(body_text, str):
            body_text = str(body_text) if body_text else ''
        
        # Clean HTML tags
        body_text = re.sub(r'<[^>]+>', '', body_text).strip()
        
        # Prepare message_post params
        post_params = {
            'body': body_text,
            'message_type': 'comment',
            'subtype_xmlid': 'mail.mt_comment',
            'author_id': partner.id,
        }
        
        # Use WhatsApp timestamp if available
        if waha_msg.wa_timestamp:
            post_params['date'] = waha_msg.wa_timestamp
            _logger.info('Using WhatsApp timestamp: %s', waha_msg.wa_timestamp)
        
        # Use context flag to prevent triggering outbound send in mail_thread.py
        discuss_msg = channel.with_context(skip_whatsapp_send=True).message_post(**post_params)
        
        _logger.info('Created mail.message %s in channel %s', discuss_msg.id, channel.id)
        return discuss_msg

    def parse_content_from_payload(self, payload, msg_context):
        """
        Delegate parsing based on message type
        
        Args:
            payload: WAHA payload
            msg_context: dict from _extract_inbound_context
            
        Returns:
            Formatted content for Discuss
        """
        msg_type = msg_context.get('message_type', 'text')
        
        if msg_type == 'text':
            return self.parse_text_content(payload)
        elif msg_type == 'image':
            return self.parse_image_content(payload)
        elif msg_type == 'sticker':
            return self.parse_sticker_content(payload)
        elif msg_type == 'audio':
            return self.parse_audio_content(payload)
        elif msg_type == 'video':
            return self.parse_video_content(payload)
        elif msg_type == 'document':
            return self.parse_document_content(payload)
        elif msg_type == 'location':
            return self.parse_location_content(payload)
        else:
            # Unknown type - try text
            return self.parse_text_content(payload)

    def parse_text_content(self, payload):
        """Parse text content from payload"""
        body = payload.get('body', '')
        # Clean HTML tags
        import re
        body = re.sub(r'<[^>]+>', '', body).strip()
        return body

    def parse_image_content(self, payload):
        """
        Parse image caption from WhatsApp
        
        Note: Actual image download happens later in process_media_attachments()
        Returns caption text for message body
        """
        caption = payload.get('caption', '')
        return caption if caption else '[📷 Image]'

    def parse_sticker_content(self, payload):
        """
        Parse sticker from WhatsApp
        
        Note: Actual sticker download happens later in process_media_attachments()
        Stickers have no caption, just emoji placeholder
        """
        return '🎨 Sticker'

    def process_media_attachments(self, payload, msg_type):
        """
        Process and download media attachments (images, stickers, etc.)
        
        Must be called AFTER waha.message and mail.message are created.
        Creates ir.attachment and links to mail.message.
        
        Args:
            payload: WAHA payload containing media info
            msg_type: 'image' | 'sticker' | 'audio' | 'video' | 'document'
        """
        if not self.mail_message_id:
            _logger.warning('Cannot process media: waha.message %s has no mail_message_id', self.id)
            return
        
        media = payload.get('media', {})
        if not media:
            _logger.warning('No media found in payload for %s', msg_type)
            return
        
        # WAHA returns media as base64 data or URL
        media_data = media.get('data')  # base64 string
        media_url = media.get('url')    # HTTP URL
        mimetype = media.get('mimetype') or self._get_default_mimetype(msg_type)
        filename = media.get('filename') or self._get_default_filename(msg_type)
        
        # Extract filename from URL if not provided
        if not filename and media_url:
            import os
            filename = os.path.basename(media_url.split('?')[0]) or self._get_default_filename(msg_type)
        
        # Ensure filename is never None
        if not filename:
            filename = self._get_default_filename(msg_type)
        
        _logger.info('process_media_attachments: type=%s, has_data=%s, has_url=%s, filename=%s', 
                    msg_type, bool(media_data), bool(media_url), filename)
        
        # Try to get media binary data
        import base64
        media_binary = None
        
        if media_data:
            # Direct base64 data
            try:
                media_binary = base64.b64decode(media_data)
                _logger.info('Decoded base64 %s: %d bytes', msg_type, len(media_binary))
            except Exception as e:
                _logger.error('Failed to decode base64 %s: %s', msg_type, str(e))
        
        elif media_url:
            # Download from URL
            try:
                import requests
                
                # Get account for URL fixing and authentication
                account = self.wa_account_id
                
                # Fix URL if it uses localhost (replace with actual WAHA server)
                if 'localhost' in media_url or '127.0.0.1' in media_url:
                    media_url = media_url.replace('http://localhost:3000', account.waha_url.rstrip('/'))
                    media_url = media_url.replace('http://127.0.0.1:3000', account.waha_url.rstrip('/'))
                    _logger.info('Fixed media URL: %s', media_url)
                
                # Prepare headers with authentication
                headers = {}
                if account.api_key:
                    headers['X-Api-Key'] = account.api_key
                
                response = requests.get(media_url, headers=headers, timeout=30)
                response.raise_for_status()
                media_binary = response.content
                _logger.info('Downloaded %s from URL: %d bytes', msg_type, len(media_binary))
            except Exception as e:
                _logger.error('Failed to download %s from %s: %s', msg_type, media_url, str(e))
        
        # Create attachment if we have media data
        if media_binary:
            try:
                attachment = self.env['ir.attachment'].sudo().create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(media_binary),
                    'mimetype': mimetype,
                    'res_model': 'mail.message',
                    'res_id': self.mail_message_id.id,
                })
                _logger.info('Created %s attachment: %s (ID: %s)', msg_type, filename, attachment.id)
            except Exception as e:
                _logger.error('Failed to create %s attachment: %s', msg_type, str(e))
    
    def _get_default_mimetype(self, msg_type):
        """Get default mimetype for media type"""
        defaults = {
            'image': 'image/jpeg',
            'sticker': 'image/webp',
            'audio': 'audio/ogg',
            'video': 'video/mp4',
            'document': 'application/pdf',
        }
        return defaults.get(msg_type, 'application/octet-stream')
    
    def _get_default_filename(self, msg_type):
        """Get default filename for media type"""
        defaults = {
            'image': 'image.jpg',
            'sticker': 'sticker.webp',
            'audio': 'audio.ogg',
            'video': 'video.mp4',
            'document': 'document.pdf',
        }
        return defaults.get(msg_type, 'file.bin')

    def parse_audio_content(self, payload):
        """Parse audio content - STUB for now"""
        media = payload.get('media', {})
        url = media.get('url', '')
        return f"[Audio]\nURL: {url}" if url else "[Audio]"

    def parse_video_content(self, payload):
        """Parse video content - STUB for now"""
        media = payload.get('media', {})
        caption = payload.get('caption', '')
        url = media.get('url', '')
        return f"[Video] {caption}\nURL: {url}" if caption or url else "[Video]"

    def parse_document_content(self, payload):
        """Parse document content - STUB for now"""
        media = payload.get('media', {})
        filename = media.get('filename', '')
        url = media.get('url', '')
        return f"[Document] {filename}\nURL: {url}" if filename or url else "[Document]"

    def parse_location_content(self, payload):
        """Parse location content - STUB for now"""
        location = payload.get('location', {})
        latitude = location.get('latitude')
        longitude = location.get('longitude')
        name = location.get('name', '')
        return f"[Location] {name}\nLat: {latitude}, Lon: {longitude}"

    def _detect_message_type(self, payload):
        """
        Detect message type from WAHA payload
        
        Returns: 'text' | 'image' | 'sticker' | 'audio' | 'video' | 'document' | 'location'
        """
        # Check for location first
        if payload.get('location'):
            return 'location'
        
        # Check for media
        if payload.get('hasMedia'):
            msg_type = payload.get('type', 'text')
            
            # WAHA types: text, image, sticker, audio, video, document, ptt, location, vcard, etc
            # Normalize to our supported types
            if msg_type in ('image', 'sticker', 'audio', 'video', 'document'):
                return msg_type
            elif msg_type == 'ptt':  # Push-to-talk voice message
                return 'audio'
            else:
                # Try to detect from URL/filename if type is unclear
                media = payload.get('media', {})
                media_url = media.get('url', '')
                filename = media.get('filename', '')
                
                # Check file extension
                file_to_check = filename or media_url
                if file_to_check:
                    file_lower = file_to_check.lower()
                    if any(ext in file_lower for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                        return 'image'
                    elif any(ext in file_lower for ext in ['.mp4', '.avi', '.mov', '.mkv']):
                        return 'video'
                    elif any(ext in file_lower for ext in ['.mp3', '.ogg', '.oga', '.wav', '.m4a', '.aac']):
                        return 'audio'
                    elif any(ext in file_lower for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
                        return 'document'
                
                # Unknown media type - treat as document
                _logger.warning('Unknown media type: %s (url: %s)', msg_type, media_url)
                return 'document'
        
        # Default to text
        return 'text'

    # ============================================================
    # OUTBOUND FLOW: discuss.message → waha.message → WAHA API
    # ============================================================

    @api.model
    def process_outbound_send(self, channel, partner, text_body, reply_to_msg_uid=None):
        """
        ORCHESTRATOR: Process outbound message send
        
        Responsibilities:
        - Resolve contact/channel
        - Create waha.message outbound
        - Create discuss.message
        - Send to WAHA API
        - On failure: rollback discuss.message + error handling
        
        Args:
            channel: discuss.channel
            partner: res.partner (recipient)
            text_body: Message text to send
            reply_to_msg_uid: Optional message ID to reply to
            
        Returns:
            dict with 'success', 'message_id', 'error' keys
        """
        try:
            _logger.info('=== OUTBOUND: process_outbound_send START ===')
            _logger.info('Channel: %s, Partner: %s', channel.id, partner.id)
            
            # Find account
            account = channel.whatsapp_account_id
            if not account:
                raise UserError(_('Channel is not linked to a WhatsApp account'))
            
            _logger.info('Account: %s', account.name)
            
            # Step 1: Create waha.message outbound
            waha_msg = self.create_outbound_message(
                account, partner, channel, text_body, reply_to_msg_uid
            )
            _logger.info('waha.message created: %s', waha_msg.id)
            
            # Step 2: Create discuss.message
            discuss_msg = self.create_outbound_discuss_message(
                waha_msg, channel, text_body
            )
            waha_msg.write({'mail_message_id': discuss_msg.id})
            _logger.info('discuss.message created: %s', discuss_msg.id)
            
            # Step 3: Send to WAHA
            try:
                result = waha_msg.send_to_waha()
                _logger.info('Message sent to WAHA: %s', result.get('id'))
                _logger.info('=== OUTBOUND: process_outbound_send END (SUCCESS) ===')
                
                return {
                    'success': True,
                    'message_id': waha_msg.id,
                    'waha_id': result.get('id'),
                }
            except Exception as send_err:
                # On send failure: rollback discuss.message
                _logger.error('Send to WAHA failed: %s', str(send_err))
                self.handle_outbound_error(waha_msg, discuss_msg, send_err)
                
                return {
                    'success': False,
                    'message_id': waha_msg.id,
                    'error': str(send_err),
                }
        
        except Exception as e:
            _logger.exception('Error in process_outbound_send: %s', str(e))
            raise

    def create_outbound_message(self, account, partner, channel, text_body, reply_to_msg_uid=None):
        """
        Create waha.message outbound record
        
        Args:
            account: waha.account
            partner: res.partner (recipient)
            channel: discuss.channel
            text_body: Message text
            reply_to_msg_uid: Optional message to reply to
            
        Returns:
            waha.message record
        """
        # Extract phone from partner
        phone = partner.mobile or partner.phone
        phone = phone.replace('+', '').replace(' ', '') if phone else ''
        
        # Get wa_chat_id if available
        wa_chat_id = partner.wa_chat_id or f"{phone}@c.us"
        
        vals = {
            'wa_account_id': account.id,
            'mobile_number': phone,
            'message_type': 'outbound',
            'state': 'outgoing',
            'body': text_body,
            'waha_chat_id': wa_chat_id,
            'reply_to_msg_uid': reply_to_msg_uid,
        }
        
        message = self.create(vals)
        _logger.info('Created outbound waha.message %s', message.id)
        return message

    def create_outbound_discuss_message(self, waha_msg, channel, text_body):
        """
        Create discuss.message (visible to user immediately)
        
        Args:
            waha_msg: waha.message record
            channel: discuss.channel
            text_body: Message text
            
        Returns:
            mail.message record
        """
        import re
        # Clean HTML tags
        body_clean = re.sub(r'<[^>]+>', '', text_body).strip()
        
        admin = self.env.ref('base.user_admin').sudo()
        # Use context flag to prevent recursion in mail_thread.py override
        discuss_msg = channel.with_context(skip_whatsapp_send=True).message_post(
            body=body_clean,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            author_id=admin.partner_id.id,
        )
        
        _logger.info('Created discuss.message %s', discuss_msg.id)
        return discuss_msg

    def send_to_waha(self):
        """
        Send message to WAHA API
        
        Responsibilities:
        - Validate state (outgoing)
        - Prepare WAHA payload
        - Call WAHA endpoint
        - Update waha.message with result
        
        Returns:
            dict with response data
            
        Raises:
            UserError: If validation fails
            Exception: If API call fails
        """
        self.ensure_one()
        _logger.info('=== send_to_waha START ===')
        _logger.info('Message: %s, State: %s', self.id, self.state)
        
        if self.state != 'outgoing':
            raise UserError(
                _('Only messages in "outgoing" state can be sent. Current state: %s') 
                % self.state
            )
        
        if not self.wa_account_id or self.wa_account_id.status != 'connected':
            raise UserError(
                _('WhatsApp account is not connected')
            )
        
        # Prepare message payload
        import re
        raw_body = self.mail_message_id.body if self.mail_message_id else self.body or ''
        body = re.sub(r'<[^>]+>', '', raw_body).strip()
        
        _logger.info('Preparing to send: chat_id=%s, body_len=%d', 
                    self.waha_chat_id, len(body))
        
        try:
            # Call WAHA API via account
            result = self.wa_account_id._send_waha_message_new(
                chat_id=self.waha_chat_id,
                text=body,
                reply_to_msg_uid=self.reply_to_msg_uid,
            )
            
            # Update waha.message with result
            self.write({
                'state': 'sent',
                'msg_uid': result.get('id', ''),
            })
            
            _logger.info('=== send_to_waha END (SUCCESS) ===')
            return result
        
        except Exception as e:
            _logger.exception('WAHA API error: %s', str(e))
            # Don't update state here - let caller handle
            raise

    def handle_outbound_error(self, waha_msg, discuss_msg, error):
        """
        Handle outbound send failure
        
        Responsibilities:
        - Mark waha.message as failed
        - Delete discuss.message (or mark as failed)
        - Log error details
        - Notify user via UserError
        
        Args:
            waha_msg: waha.message record
            discuss_msg: mail.message to revert
            error: Exception object
        """
        error_msg = str(error)
        _logger.error('Handling outbound error: %s', error_msg)
        
        # Determine failure type
        if 'No LID for user' in error_msg:
            failure_type = 'waha_recoverable'
            user_msg = _('Contact not found in WhatsApp. Please verify the phone number.')
        elif 'Invalid session' in error_msg or 'ENOTCONNECTED' in error_msg:
            failure_type = 'account'
            user_msg = _('WhatsApp session disconnected. Please reconnect.')
        else:
            failure_type = 'unknown'
            user_msg = _('Failed to send message: %s') % error_msg
        
        # Update waha.message
        waha_msg.write({
            'state': 'error',
            'failure_type': failure_type,
            'failure_reason': error_msg,
        })
        
        # Revert discuss.message
        if discuss_msg:
            discuss_msg.unlink()
            _logger.info('Deleted discuss.message %s due to send failure', discuss_msg.id)
        
        # Notify user
        raise UserError(user_msg)

    # ============================================================
    # TRANSVERSAL: State management and consistency
    # ============================================================

    def update_status_from_waha(self, status_payload):
        """
        Update message status from WAHA ACK/status webhook
        
        Responsibilities:
        - Map WAHA status to waha.message state
        - Optionally update discuss.message with visual indicator
        
        Args:
            status_payload: dict with 'ack' field from WAHA webhook
                - 0: ERROR
                - 1: PENDING
                - 2: SERVER
                - 3: DEVICE
                - 4: READ
                - 5: PLAYED
        """
        self.ensure_one()
        _logger.info('Updating message %s status from WAHA', self.id)
        
        ack_value = status_payload.get('ack', 0)
        
        # Map ACK to state
        state_mapping = {
            0: 'error',
            1: 'outgoing',
            2: 'sent',
            3: 'delivered',
            4: 'read',
            5: 'read',
        }
        
        new_state = state_mapping.get(ack_value, self.state)
        
        if new_state != self.state:
            self.write({'state': new_state})
            _logger.info('Message %s state updated: %s → %s', self.id, self.state, new_state)
        
        # TODO: Optionally add visual indicator to discuss.message
        # (e.g., reaction emoji, icon in message body, etc.)

    def ensure_links_consistency(self):
        """
        Validate and fix consistency of waha.message links
        
        Responsibilities:
        - Ensure partner_id/contact is valid
        - Ensure channel_id/discuss is valid
        - Ensure mail_message_id exists if needed
        - Rebuild missing links if possible
        
        Returns:
            dict with 'issues_found', 'fixed_count' keys
        """
        self.ensure_one()
        _logger.info('Checking consistency of message %s', self.id)
        
        issues = {
            'issues_found': 0,
            'fixed_count': 0,
        }
        
        # TODO: Implement consistency checks
        # - If partner_id missing but mobile_number exists: search/create partner
        # - If mail_message_id missing: recreate discuss.message
        # - If channel_id missing: find/create channel
        
        return issues
