# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import secrets
import string
import requests
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.waha.tools.waha_api import WahaApi

_logger = logging.getLogger(__name__)


class WahaAccount(models.Model):
    _name = 'waha.account'
    _inherit = ['mail.thread']
    _description = 'WAHA WhatsApp Account'

    name = fields.Char(string="Name", tracking=True, required=True)
    active = fields.Boolean(default=True, tracking=True)

    # WAHA Configuration (replaces WhatsApp Business API credentials)
    waha_url = fields.Char(
        string="WAHA Server URL",
        required=True,
        default='http://localhost:3000',
        tracking=True,
        help='Base URL of your WAHA server (e.g., http://localhost:3000)'
    )
    session_name = fields.Char(
        string="Session Name",
        required=True,
        default='default',
        tracking=True,
        help='Session name in WAHA (must be unique)'
    )
    api_key = fields.Char(
        string="API Key",
        groups='waha.group_waha_admin',
        help='API Key for WAHA authentication (if configured)'
    )

    # Account Information
    phone_uid = fields.Char(
        string="Phone Number ID",
        readonly=True,
        copy=False,
        help='Phone number ID from WAHA'
    )
    account_uid = fields.Char(
        string="Account UID",
        compute='_compute_account_uid',
        store=True,
        help='Unique account identifier'
    )

    # Webhook Configuration
    webhook_verify_token = fields.Char(
        string="Webhook Verify Token",
        compute='_compute_verify_token',
        groups='waha.group_waha_admin',
        store=True,
        help='Token to verify webhook requests'
    )
    callback_url = fields.Char(
        string="Callback URL",
        compute='_compute_callback_url',
        readonly=True,
        copy=False
    )

    # QR Code for Connection
    qr_code = fields.Binary(
        string="QR Code",
        attachment=False,
        help='QR code to scan with WhatsApp'
    )
    qr_code_expiry = fields.Datetime(
        string="QR Code Expiry",
        help='QR code expiration time'
    )

    # Connection Status
    status = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], default='disconnected', readonly=True, tracking=True, string="Status")

    # Configuration
    notify_user_ids = fields.Many2many(
        comodel_name='res.users',
        default=lambda self: self.env.user,
        domain=[('share', '=', False)],
        required=True,
        tracking=True,
        help="Users to notify when a message is received"
    )

    sync_chat_limit = fields.Integer(
        string="Chats to Sync",
        default=10,
        required=True,
        help="Maximum number of recent WAHA chats to import from this account."
    )
    sync_message_limit = fields.Integer(
        string="Messages per Chat",
        default=100,
        required=True,
        help="Maximum number of recent WAHA messages to import for each chat."
    )

    # Statistics
    templates_count = fields.Integer(
        string="Templates Count",
        compute='_compute_templates_count'
    )

    _sql_constraints = [
        ('phone_uid_unique', 'unique(phone_uid)',
         "The same phone number ID already exists"),
        ('session_name_unique', 'unique(session_name)',
         "Session name must be unique")
    ]

    @api.depends('session_name')
    def _compute_account_uid(self):
        """Generate account UID based on session name"""
        for account in self:
            if account.session_name:
                account.account_uid = f"waha_{account.session_name}"
            else:
                account.account_uid = False

    @api.depends('session_name')
    def _compute_verify_token(self):
        """Generate webhook verification token"""
        for rec in self:
            if rec.id and not rec.webhook_verify_token:
                rec.webhook_verify_token = ''.join(
                    secrets.choice(string.ascii_letters + string.digits)
                    for _ in range(16)
                )

    def _compute_callback_url(self):
        """Calculate webhook callback URL"""
        for account in self:
            account.callback_url = self.get_base_url() + '/waha/webhook'

    def _compute_templates_count(self):
        """Count associated templates"""
        for account in self:
            account.templates_count = self.env['waha.template'].search_count([
                ('wa_account_id', '=', account.id)
            ])

    @api.constrains('notify_user_ids')
    def _check_notify_user_ids(self):
        """Validate that at least one user is set for notifications"""
        for account in self:
            if len(account.notify_user_ids) < 1:
                raise ValidationError(_("At least one user to notify is required"))

    @api.constrains('sync_chat_limit', 'sync_message_limit')
    def _check_sync_limits(self):
        for account in self:
            if account.sync_chat_limit < 1:
                raise ValidationError(_("Chats to Sync must be greater than zero"))
            if account.sync_message_limit < 1:
                raise ValidationError(_("Messages per Chat must be greater than zero"))

    def action_view_templates(self):
        """View templates for this account"""
        self.ensure_one()
        return {
            'name': _('Templates'),
            'type': 'ir.actions.act_window',
            'res_model': 'waha.template',
            'view_mode': 'list,form',
            'domain': [('wa_account_id', '=', self.id)],
            'context': {'default_wa_account_id': self.id}
        }

    # ============================================================
    # CONNECTION AND SESSION MANAGEMENT
    # ============================================================

    def action_connect(self):
        """Start WAHA session connection"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            result = api.start_session()
            self.write({'status': 'connecting'})
            self.message_post(body=_('Session connection initiated'))
            return self.action_get_qr()
        except requests.exceptions.ConnectionError:
            self.write({'status': 'error'})
            raise UserError(_(
                "Cannot connect to WAHA server at %s\n\n"
                "Please verify:\n"
                "• WAHA server is running\n"
                "• The URL is correct\n"
                "• No firewall is blocking the connection"
            ) % self.waha_url)
        except requests.exceptions.Timeout:
            self.write({'status': 'error'})
            raise UserError(_(
                "WAHA server timeout at %s\n\n"
                "The server is not responding. Please check if WAHA is running properly."
            ) % self.waha_url)
        except Exception as e:
            self.write({'status': 'error'})
            raise UserError(_("Error connecting to WAHA: %s") % str(e))

    def action_get_qr(self):
        """Get QR code for scanning"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            
            # First check session status
            status_data = api.get_session_status()
            session_status = status_data.get('status', '')
            
            _logger.info('Fetching QR for %s - Current WAHA status: %s', self.session_name, session_status)
            
            # Only try to get QR if session is in SCAN_QR_CODE state
            if session_status == 'SCAN_QR_CODE':
                qr_data = api.get_qr_code()
                
                _logger.info('QR Response for %s: %s', self.session_name, bool(qr_data.get('qr')))

                if qr_data.get('qr'):
                    # Store QR code as base64
                    import base64
                    qr_base64 = qr_data['qr']
                    if ',' in qr_base64:
                        qr_base64 = qr_base64.split(',')[1]
                    self.qr_code = qr_base64
                    self.qr_code_expiry = fields.Datetime.now() + timedelta(minutes=2)
                    
                    _logger.info('QR code saved for %s', self.session_name)
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('QR Code Ready'),
                            'message': _('QR code has been loaded. Scan it with WhatsApp to connect.\n\n'
                                       'Go to: WhatsApp > Settings > Linked Devices > Link a Device'),
                            'type': 'success',
                            'sticky': True,
                        }
                    }
                else:
                    raise UserError(_("Failed to get QR code from WAHA server"))
                    
            elif session_status in ['WORKING', 'CONNECTED']:
                # Already connected
                self.status = 'connected'
                self.qr_code = False
                if 'me' in status_data:
                    self.phone_uid = status_data['me'].get('id', '')
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Already Connected'),
                        'message': _('Session is already connected!\n\nPhone: %s') % self.phone_uid,
                        'type': 'warning',
                        'sticky': True,
                    }
                }
            else:
                # Session is starting, ask user to wait
                _logger.info('Session %s is in state %s, waiting to reach SCAN_QR_CODE', self.session_name, session_status)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Session Initializing'),
                        'message': _('Session is starting (status: %s)\n\n'
                                   'Please wait a moment and click "Get QR Code" again.') % session_status,
                        'type': 'info',
                        'sticky': True,
                    }
                }
        except requests.exceptions.ConnectionError:
            _logger.exception('Cannot connect to WAHA server at %s', self.waha_url)
            raise UserError(_("Cannot connect to WAHA server at %s") % self.waha_url)
        except UserError:
            raise
        except Exception as e:
            _logger.exception('Error getting QR code: %s', str(e))
            raise UserError(_("Error getting QR code: %s") % str(e))
            raise UserError(_("Error getting QR code: %s") % str(e))

    def action_refresh_status(self):
        """Refresh connection status from WAHA"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            status_data = api.get_session_status()

            # Log full response for debugging
            _logger.info('WAHA Status Response for %s: %s', self.session_name, status_data)

            # Map WAHA status to model status
            waha_status = status_data.get('status', 'DISCONNECTED')
            statuses = status_data.get('statuses', [])
            
            if waha_status in ['WORKING', 'CONNECTED']:
                self.status = 'connected'
                self.qr_code = False  # Clear QR when connected
                # Try to get phone number
                if 'me' in status_data:
                    self.phone_uid = status_data['me'].get('id', '')
                msg = f"✅ Connected - Phone: {self.phone_uid}"
            elif waha_status in ['STARTING', 'SCAN_QR_CODE']:
                self.status = 'connecting'
                msg = f"⏳ Connecting... WAHA Status: {waha_status}"
                if statuses:
                    msg += f"\n\nStatus History:"
                    for s in statuses[-3:]:  # Last 3 statuses
                        msg += f"\n  • {s.get('status')} - {s.get('timestamp')}"
            else:
                self.status = 'disconnected'
                msg = f"❌ Disconnected - WAHA Status: {waha_status}"

            self.message_post(body=_('Status updated: %s (WAHA: %s)', self.status, waha_status))
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Status Updated'),
                    'message': msg,
                    'type': 'success' if self.status == 'connected' else 'info',
                    'sticky': True,
                }
            }
        except requests.exceptions.ConnectionError:
            self.status = 'error'
            raise UserError(_("Cannot connect to WAHA server at %s") % self.waha_url)
        except Exception as e:
            self.status = 'error'
            _logger.exception('Error refreshing status: %s', str(e))
            raise UserError(_("Error refreshing status: %s") % str(e))

    def action_disconnect(self):
        """Disconnect WAHA session"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            api.stop_session()
            self.write({
                'status': 'disconnected',
                'qr_code': False,
            })
            self.message_post(body=_('Session disconnected'))
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Disconnected'),
                    'message': _('WhatsApp session has been disconnected'),
                    'type': 'warning',
                }
            }
        except requests.exceptions.ConnectionError:
            raise UserError(_("Cannot connect to WAHA server at %s") % self.waha_url)
        except Exception as e:
            raise UserError(_("Error disconnecting: %s") % str(e))

    def action_repair_discuss_channels(self):
        """Create missing discuss.channel for every waha.chat that doesn't have one.
        Also migrates existing channels from channel_type='whatsapp' to 'waha'."""
        self.ensure_one()

        # Migrate old channel_type='whatsapp' channels created by this module
        old_channels = self.env['discuss.channel'].sudo().search([
            ('whatsapp_account_id', '=', self.id),
            ('channel_type', '=', 'whatsapp'),
        ])
        if old_channels:
            old_channels.sudo().write({'channel_type': 'waha'})
            _logger.info('Migrated %d channels from whatsapp to waha type', len(old_channels))

        # Create channels for chats that don't have one yet
        chats_without_channel = self.env['waha.chat'].search([
            ('wa_account_id', '=', self.id),
            ('discuss_channel_id', '=', False),
        ])
        repaired = 0
        for chat in chats_without_channel:
            try:
                chat._ensure_discuss_channel()
                repaired += 1
            except Exception as e:
                _logger.warning('Could not repair channel for chat %s: %s', chat.id, e)

        _logger.info('Repaired %d discuss channels for account %s', repaired, self.name)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Channels Repaired'),
                'message': _('Migrated old channels. Created %d new Discuss channels.') % repaired,
                'type': 'success',
            },
        }

    def action_resync_messages(self):
        """Re-trigger mail_message_id compute for waha.messages that have a channel but no discuss message."""
        self.ensure_one()
        messages_to_sync = self.env['waha.message'].sudo().search([
            ('wa_account_id', '=', self.id),
            ('mail_message_id', '=', False),
            ('message_type', '=', 'inbound'),
            ('waha_chat_id.discuss_channel_id', '!=', False),
        ])
        _logger.info('Re-syncing %d messages for account %s', len(messages_to_sync), self.name)
        messages_to_sync.with_context(allow_outbound_discuss_sync=False)._compute_mail_message_id()
        synced = messages_to_sync.filtered(lambda m: m.mail_message_id)
        _logger.info('Successfully synced %d/%d messages', len(synced), len(messages_to_sync))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Messages Synced'),
                'message': _('%d of %d messages loaded into conversations.') % (len(synced), len(messages_to_sync)),
                'type': 'success',
            },
        }

    def action_fetch_chats_and_messages(self):
        """
        Fetch recent chats and recent messages from each chat, persist to DB
        
        Compatible with refactored architecture:
        - Uses waha.chat.find_or_create() for chats
        - Creates messages with raw_chat_id and raw_sender_phone
        - Auto-compute handles all relationships automatically
        """
        self.ensure_one()
        
        try:
            api = WahaApi(self)
            
            # Get all chats from WAHA
            chats_response = api.get_chats()
            
            _logger.info('Chats response type: %s', type(chats_response))
            
            # Parse chats from response
            if isinstance(chats_response, dict):
                chats = chats_response.get('chats', []) or chats_response.get('data', []) or chats_response.get('result', [])
            elif isinstance(chats_response, list):
                chats = chats_response
            else:
                chats = []
            
            _logger.info('Parsed %d chats from WAHA', len(chats))
            
            if not chats:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Chats'),
                        'message': _('No chats found in WhatsApp'),
                        'type': 'warning',
                        'sticky': True,
                    }
                }
            
            chat_limit = self.sync_chat_limit or 10
            message_limit = self.sync_message_limit or 100

            # Sort by timestamp and take the configured number of recent chats
            chats = sorted(chats, key=lambda x: x.get('timestamp', 0), reverse=True)[:chat_limit]
            
            # Counters
            chats_created = 0
            messages_created = 0
            
            # Process each chat
            for idx, chat in enumerate(chats, 1):
                try:
                    # Extract chat_id
                    chat_id = self._extract_waha_message_id(chat.get('id'))
                    if not chat_id:
                        _logger.warning('Skipping chat without id: %s', chat)
                        continue
                    
                    chat_name = chat.get('name', chat_id)
                    is_group = '@g.us' in chat_id
                    
                    _logger.info('Processing chat %d/%d: %s (group=%s)', idx, len(chats), chat_name, is_group)
                    
                    # Use waha.chat.find_or_create (handles groups, channels, partners)
                    waha_chat = self.env['waha.chat'].find_or_create(
                        wa_account=self,
                        chat_id=chat_id,
                        partner=None  # Will auto-create if needed
                    )
                    
                    if waha_chat:
                        chats_created += 1
                    
                    # Get messages for this chat
                    messages_response = api.get_messages(chat_id, limit=message_limit)
                    
                    # Parse messages
                    if isinstance(messages_response, dict):
                        messages = messages_response.get('messages', []) or messages_response.get('data', []) or messages_response.get('result', [])
                    elif isinstance(messages_response, list):
                        messages = messages_response
                    else:
                        messages = []
                    
                    _logger.info('Got %d messages for chat %s', len(messages), chat_id)
                    
                    # Sort messages by timestamp (oldest first) to maintain chronological order
                    messages = sorted(messages, key=lambda x: x.get('timestamp', 0))
                    
                    # Process each message
                    for msg in messages:
                        try:
                            context = self._extract_synced_message_context(msg, chat_id)
                            msg_uid = context['msg_uid']
                            if not msg_uid:
                                _logger.warning('Skipping message without id: %s', msg)
                                continue
                            
                            # Skip if message already exists
                            existing = self.env['waha.message'].search([
                                ('msg_uid', '=', msg_uid),
                                ('wa_account_id', '=', self.id)
                            ], limit=1)
                            
                            if existing:
                                continue
                            
                            # Detect content type
                            content_type = 'text'
                            if msg.get('type'):
                                msg_type = msg.get('type', '').lower()
                                if msg_type in ['image', 'video', 'audio', 'document', 'sticker']:
                                    content_type = msg_type
                            
                            # Validate msg for raw_payload
                            if not msg or not isinstance(msg, dict):
                                _logger.error('Invalid msg payload for message %s: type=%s, value=%s',
                                            msg_uid, type(msg).__name__, msg)
                                valid_msg = {}
                            else:
                                valid_msg = msg
                            
                            # Create message with raw fields (auto-compute handles rest)
                            vals = {
                                'wa_account_id': self.id,
                                'msg_uid': msg_uid,
                                'message_type': 'outbound' if context['from_me'] else 'inbound',
                                'content_type': content_type,
                                'state': 'sent' if context['from_me'] else 'received',
                                'body': context['body'] or '(no content)',
                                'raw_chat_id': chat_id,
                                'raw_sender_lid': context['sender_lid'],
                                'raw_sender_phone': context['sender_phone'],
                                'wa_timestamp': context['wa_timestamp'],
                                'raw_payload': valid_msg,
                            }

                            if context.get('participant'):
                                vals['participant_id'] = context['participant']

                            if context.get('reply_to_msg_uid'):
                                original_msg = self._find_synced_reply_to_message(
                                    chat_id,
                                    context['reply_to_msg_uid'],
                                )
                                if original_msg:
                                    vals['reply_to_message_id'] = original_msg.id
                                    vals['reply_to_msg_uid'] = original_msg.msg_uid
                            
                            # Create message - auto-compute will handle:
                            # 1. waha_chat_id
                            # 2. partner_id
                            # 3. mail_message_id (Discuss message)
                            waha_msg = self.env['waha.message'].with_context(
                                allow_outbound_discuss_sync=True
                            ).create(vals)
                            
                            if waha_msg:
                                messages_created += 1
                                
                                # Process media if present
                                if content_type != 'text' and msg:
                                    try:
                                        waha_msg._process_media_from_payload(msg, content_type)
                                    except Exception as e:
                                        _logger.warning('Failed to process media for %s: %s', msg_uid, str(e))
                            
                        except Exception as e:
                            _logger.warning('Failed to create message %s: %s', msg.get('id'), str(e))
                            continue
                    
                    # Update chat metadata
                    if waha_chat:
                        waha_chat.update_last_message()
                    
                except Exception as e:
                    _logger.exception('Error processing chat %s: %s', chat_id, str(e))
                    continue
            
            # Build summary message
            summary = []
            summary.append(f"✅ Sync Complete\n")
            summary.append(f"📊 Processed {len(chats)} chats (limit: {chat_limit})")
            summary.append(f"🧾 Read up to {message_limit} messages per chat")
            summary.append(f"💬 Chats created/updated: {chats_created}")
            summary.append(f"📨 Messages created: {messages_created}")
            summary.append(f"\nNote: Partners, channels, and discuss messages created automatically via auto-compute")
            
            message = "\n".join(summary)
            
            _logger.info('Sync complete: %d chats, %d messages created', chats_created, messages_created)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Chats & Messages Synced'),
                    'message': message,
                    'type': 'success',
                    'sticky': True,
                }
            }
            
        except requests.exceptions.ConnectionError:
            raise UserError(_("Cannot connect to WAHA server at %s") % self.waha_url)
        except Exception as e:
            _logger.exception('Error fetching chats and messages: %s', str(e))
            raise UserError(_("Error fetching chats and messages: %s") % str(e)) 

    def _extract_waha_message_id(self, value):
        """Return WAHA serialized id from either string or id dict."""
        if isinstance(value, dict):
            return value.get('_serialized') or value.get('id') or value.get('user') or ''
        return str(value) if value else ''

    def _extract_synced_message_context(self, msg, chat_id):
        """Normalize a message returned by WAHA chat history endpoints."""
        msg_uid = self._extract_waha_message_id(msg.get('id'))
        from_me = bool(msg.get('fromMe'))
        participant = self._extract_waha_message_id(msg.get('participant') or msg.get('author'))
        from_raw = self._extract_waha_message_id(msg.get('from')) or chat_id
        is_group = '@g.us' in chat_id or '@g.us' in from_raw

        sender_raw = participant if (is_group and participant) else from_raw
        if from_me and not is_group:
            # For outbound 1-1 history, keep the recipient as waha_partner so it
            # matches messages created from Odoo Discuss.
            sender_raw = chat_id

        sender_lid = None
        sender_phone = None
        if '@lid' in sender_raw:
            sender_lid = sender_raw.split('@')[0]
        elif '@c.us' in sender_raw:
            sender_phone = sender_raw.split('@')[0]
        elif sender_raw and '@g.us' not in sender_raw:
            sender_phone = sender_raw.split('@')[0] if '@' in sender_raw else sender_raw

        body = msg.get('body', '')
        if isinstance(body, dict):
            body = body.get('text') or body.get('body') or str(body)
        elif not body and isinstance(msg.get('text'), dict):
            body = msg['text'].get('body') or msg['text'].get('text') or ''
        elif not isinstance(body, str):
            body = str(body) if body else ''

        timestamp_value = msg.get('timestamp')
        wa_timestamp = None
        if timestamp_value is not None:
            try:
                from datetime import datetime
                wa_timestamp = datetime.fromtimestamp(int(timestamp_value))
            except (ValueError, TypeError):
                wa_timestamp = fields.Datetime.now()

        reply_to = msg.get('replyTo') or {}
        reply_to_msg_uid = None
        if isinstance(reply_to, dict):
            reply_to_msg_uid = self._extract_waha_message_id(reply_to.get('id'))
        if not reply_to_msg_uid:
            quoted_stanza_id = (msg.get('_data') or {}).get('quotedStanzaID')
            reply_to_msg_uid = quoted_stanza_id or None

        return {
            'msg_uid': msg_uid,
            'from_me': from_me,
            'sender_lid': sender_lid,
            'sender_phone': sender_phone,
            'participant': participant,
            'body': body,
            'wa_timestamp': wa_timestamp or fields.Datetime.now(),
            'reply_to_msg_uid': reply_to_msg_uid,
        }

    def _find_synced_reply_to_message(self, chat_id, reply_to_id):
        if not reply_to_id:
            return self.env['waha.message']
        base_domain = [
            ('wa_account_id', '=', self.id),
            ('raw_chat_id', '=', chat_id),
        ]
        message = self.env['waha.message'].search(
            base_domain + [('msg_uid', '=', reply_to_id)],
            limit=1,
        )
        if message:
            return message
        return self.env['waha.message'].search(
            base_domain + [('msg_uid', 'ilike', reply_to_id)],
            limit=1,
        )

    def button_sync_waha_templates(self):
        """
        Sync templates from WAHA
        Note: WAHA doesn't have template approval system like WhatsApp Business API
        Templates are created locally in Odoo
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Information"),
                'message': _("WAHA does not require template synchronization. "
                           "Create templates directly in Odoo."),
                'type': 'info',
                'sticky': False,
            }
        }

    # ============================================================
    # MESSAGE SENDING
    # ============================================================

    def _send_waha_message(self, number, message_type='text', **kwargs):
        """
        Send message through WAHA API
        
        Args:
            number: Phone number (can be with or without +)
            message_type: 'text', 'image', 'document', 'video', 'audio'
            **kwargs: body, media_data, caption, filename, mimetype, waha_chat_id, etc.
        
        Returns:
            dict: Response from WAHA API with message ID
        """
        self.ensure_one()
        
        _logger.info('=== WAHA Message Send Request Started ===')
        _logger.info('Account: %s (ID: %s)', self.name, self.id)
        _logger.info('Message Type: %s', message_type)
        _logger.info('Original Phone Number: %s', number)

        if self.status != 'connected':
            _logger.error('Account status is not connected: %s', self.status)
            raise UserError(_('WhatsApp account is not connected. Please connect first.'))

        try:
            # Check if we have a pre-built chat_id from a received message
            waha_chat_id = kwargs.pop('waha_chat_id', None)
            
            if waha_chat_id:
                chat_id = waha_chat_id
                _logger.info('Using provided waha_chat_id: %s', chat_id)
            else:
                # Normalize phone number
                phone_clean = self._normalize_phone_number(number)
                _logger.info('Normalized Phone Number: %s -> %s', number, phone_clean)
                
                if not phone_clean:
                    _logger.error('Phone number normalization failed for: %s', number)
                    raise UserError(_('Invalid phone number format: %s') % number)
                
                # Format number to WhatsApp chat ID - try @c.us first
                chat_id = f"{phone_clean}@c.us"
                _logger.info('Constructed chat_id: %s', chat_id)
            
            # Validate message data
            if message_type == 'text':
                body = kwargs.get('body', '').strip()
                if not body:
                    raise UserError(_('Message body cannot be empty'))
                _logger.info('Preparing to send text message to %s via WAHA account %s', 
                            chat_id, self.name)
            
            api = WahaApi(self)

            # Try to validate that the chat exists before sending
            # This helps avoid "No LID for user" errors
            try:
                chats = api.get_chats()
                chat_exists = False
                if chats and 'data' in chats:
                    for chat in chats.get('data', []):
                        if chat.get('id') == chat_id:
                            chat_exists = True
                            break
                
                if not chat_exists:
                    _logger.warning(
                        'Chat %s not found in WhatsApp. The contact may not exist or conversation has not been initiated. '
                        'Attempting to send anyway, but this may fail with "No LID for user" error.',
                        chat_id
                    )
            except Exception as e:
                # If we can't validate chats, log warning but proceed
                _logger.warning('Could not validate chat existence: %s', str(e))

            # Send based on type
            if message_type == 'text':
                reply_to = kwargs.get('reply_to_msg_uid')
                result = api.send_text(chat_id, body, reply_to=reply_to)
            elif message_type == 'image':
                result = api.send_image(
                    chat_id,
                    kwargs.get('media_data'),
                    kwargs.get('caption')
                )
            elif message_type == 'document':
                result = api.send_file(
                    chat_id,
                    kwargs.get('media_data'),
                    kwargs.get('filename'),
                    kwargs.get('mimetype')
                )
            elif message_type == 'video':
                result = api.send_video(
                    chat_id,
                    kwargs.get('media_data'),
                    kwargs.get('caption')
                )
            elif message_type == 'audio':
                result = api.send_audio(
                    chat_id,
                    kwargs.get('media_data')
                )
            else:
                raise UserError(_('Unsupported message type: %s') % message_type)

            _logger.info('WAHA message sent successfully to %s. Response: %s', chat_id, result)
            return result

        except UserError:
            # Re-raise UserError as-is
            raise
        except Exception as err:
            error_msg = str(err)
            
            # Handle specific WAHA errors
            if 'No LID for user' in error_msg:
                raise UserError(
                    _('WhatsApp contact not found or conversation not initiated.\n\n'
                      'Possible solutions:\n'
                      '1. Open a chat with this contact in WhatsApp Web first\n'
                      '2. Make sure the phone number format is correct\n'
                      '3. Ensure the contact exists in your WhatsApp account\n\n'
                      'Phone: %s\n'
                      'Error: %s') % (number, error_msg)
                )
            elif 'Invalid session' in error_msg or 'ENOTCONNECTED' in error_msg:
                raise UserError(_('WhatsApp session disconnected. Please reconnect the account.'))
            else:
                _logger.error('Error sending WAHA message to %s: %s', number, error_msg)
                raise UserError(_('Failed to send WhatsApp message: %s') % error_msg)

    def _normalize_phone_number(self, number):
        """
        Normalize phone number to just digits
        
        Args:
            number: Phone number with any formatting (may include @c.us, @lid, @g.us)
        
        Returns:
            str: Cleaned phone number (digits only), or None if invalid
        """
        if not number:
            return None
        
        _logger.info('Normalizing phone: %s', number)
        
        # Remove WhatsApp format suffixes (@c.us, @lid, @g.us, etc)
        clean = number.replace('@c.us', '').replace('@lid', '').replace('@g.us', '')
        
        # Remove common formatting characters
        clean = clean.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        
        # Keep only digits
        clean = ''.join(filter(str.isdigit, clean))
        
        _logger.info('After removing non-digits: %s', clean)
        
        # Validate minimum length (international format usually 10-15 digits)
        if len(clean) < 10 or len(clean) > 15:
            _logger.warning('Phone number has invalid length: %s (cleaned: %s)', number, clean)
            return None
        
        _logger.info('Final normalized phone: %s', clean)
        return clean

    # ============================================================
    # CRON AND MAINTENANCE
    # ============================================================

    @api.model
    def _cron_check_connection_status(self):
        """Cron job to check connection status of all accounts"""
        accounts = self.search([('status', 'in', ['connected', 'connecting'])])
        for account in accounts:
            try:
                account.action_refresh_status()
            except Exception as e:
                _logger.error(
                    'Error checking WAHA account %s status: %s',
                    account.name, str(e)
                )

    # ============================================================
    # NEW REFACTORED SEND METHOD (for waha_message.send_to_waha)
    # ============================================================

    def _send_waha_message_new(self, chat_id, text, reply_to_msg_uid=None):
        """
        Simplified message send for refactored waha_message flow
        
        Args:
            chat_id: WAHA chat ID (e.g., "11932090237110@c.us")
            text: Message text
            reply_to_msg_uid: Optional message UID to reply to
            
        Returns:
            dict: API response with 'id' key
            
        Raises:
            UserError: On validation or API errors
        """
        self.ensure_one()
        
        _logger.info('=== _send_waha_message_new START ===')
        _logger.info('Account: %s, Chat ID: %s', self.name, chat_id)
        
        if self.status != 'connected':
            raise UserError(_('WhatsApp account is not connected'))
        
        if not text or not text.strip():
            raise UserError(_('Message text cannot be empty'))
        
        if not chat_id:
            raise UserError(_('Chat ID is required'))
        
        try:
            api = WahaApi(self)
            
            # Log chat validation attempt
            try:
                chats = api.get_chats()
                if chats and 'data' in chats:
                    chat_exists = any(chat.get('id') == chat_id for chat in chats.get('data', []))
                    if not chat_exists:
                        _logger.warning('Chat %s not found in WhatsApp', chat_id)
            except Exception as e:
                _logger.warning('Could not validate chat: %s', str(e))
            
            # Send message
            result = api.send_text(chat_id, text, reply_to=reply_to_msg_uid)
            
            _logger.info('Message sent successfully. ID: %s', result.get('id'))
            return result
            
        except Exception as e:
            error_msg = str(e)
            _logger.error('Send error: %s', error_msg)
            
            # Specific error handling
            if 'No LID for user' in error_msg:
                raise UserError(
                    _('Contact not found in WhatsApp.\n'
                      'Solutions:\n'
                      '1. Open chat in WhatsApp first\n'
                      '2. Verify phone number format\n'
                      '3. Ensure contact exists')
                )
            elif 'Invalid session' in error_msg:
                raise UserError(_('WhatsApp session disconnected. Please reconnect.'))
            else:
                raise UserError(_('Failed to send message: %s') % error_msg)
