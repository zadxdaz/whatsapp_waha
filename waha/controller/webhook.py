# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class WahaWebhookController(http.Controller):
    
    @http.route('/waha/webhook', type='http', auth='public', methods=['POST'], csrf=False)
    def waha_webhook(self, **kwargs):
        """
        Webhook endpoint for WAHA events
        
        WAHA sends webhooks for:
        - message: New incoming message
        - message.ack: Message acknowledgment (sent, delivered, read)
        - session.status: Session status change
        """
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))
            _logger.info('WAHA Webhook received: %s', json.dumps(data, indent=2))
            
            # Verify webhook token (optional - only if configured in account)
            verify_token = request.httprequest.headers.get('X-Webhook-Token')
            session_name = data.get('session')
            
            # Find account by session name
            account = request.env['waha.account'].sudo().search([
                ('session_name', '=', session_name)
            ], limit=1)
            
            if not account:
                _logger.warning('No account found for session: %s', session_name)
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'Session not found'}),
                    headers=[('Content-Type', 'application/json')]
                )
            
            # Only verify token if account has one configured
            if account.webhook_verify_token and verify_token != account.webhook_verify_token:
                _logger.warning('Invalid webhook token for session: %s', session_name)
                return request.make_response(
                    json.dumps({'status': 'error', 'message': 'Invalid token'}),
                    headers=[('Content-Type', 'application/json')]
                )
            
            # Process based on event type
            event = data.get('event')
            
            if event == 'message':
                self._handle_incoming_message(data)
            elif event == 'message.ack':
                self._handle_message_ack(data)
            elif event == 'session.status':
                self._handle_session_status(data)
            else:
                _logger.info('Unhandled event type: %s', event)
            
            return request.make_response(
                json.dumps({'status': 'ok'}),
                headers=[('Content-Type', 'application/json')]
            )
            
        except Exception as e:
            _logger.exception('Error processing WAHA webhook: %s', str(e))
            return request.make_response(
                json.dumps({'status': 'error', 'message': str(e)}),
                headers=[('Content-Type', 'application/json')]
            )
    
    def _handle_incoming_message(self, data):
        """
        Handle incoming message webhook
        
        Creates waha.message from WAHA webhook payload.
        Orchestrates the creation of message, chat, and partner records.
        """
        try:
            payload = data.get('payload', {})
            session_name = data.get('session')
            msg_uid = payload.get('id')
            
            _logger.info('=== Processing incoming message: %s ===', msg_uid)
            
            # Find account
            account = request.env['waha.account'].sudo().search([
                ('session_name', '=', session_name)
            ], limit=1)
            
            if not account:
                _logger.warning('No account found for session: %s', session_name)
                return
            
            # Check if message already exists
            existing = request.env['waha.message'].sudo().search([
                ('msg_uid', '=', msg_uid),
                ('wa_account_id', '=', account.id)
            ], limit=1)
            
            if existing:
                _logger.info('Message already exists: %s', existing.id)
                return
            
            # Extract message context
            context = self._extract_message_context(payload)
            
            # Validate payload for raw_payload
            if not payload or not isinstance(payload, dict):
                _logger.error('Invalid payload for message %s: type=%s, value=%s', 
                            context['msg_uid'], type(payload).__name__, payload)
                valid_payload = {}
            else:
                valid_payload = payload
            
            # Create waha.message with raw fields (relationships auto-computed)
            vals = {
                'msg_uid': context['msg_uid'],
                'wa_account_id': account.id,
                'message_type': 'outbound' if context['from_me'] else 'inbound',
                'state': 'sent' if context['from_me'] else 'received',
                'body': context['body'],
                'raw_chat_id': context['chat_id'],
                'raw_sender_lid': context['sender_lid'],
                'raw_sender_phone': context['sender_phone'],
                'wa_timestamp': context['wa_timestamp'],
                'raw_payload': valid_payload,
            }
            
            if context['participant']:
                vals['participant_id'] = context['participant']
            
            # Handle reply_to from quoted message
            if context.get('reply_to_stanza_id'):
                stanza_id = context['reply_to_stanza_id']
                original_msg = self._find_reply_to_message(
                    request.env,
                    account,
                    context['chat_id'],
                    stanza_id,
                )
                
                if original_msg:
                    vals['reply_to_message_id'] = original_msg.id
                    vals['reply_to_msg_uid'] = original_msg.msg_uid
                    _logger.info('Message is reply to stanzaID %s (found msg: %s)', stanza_id, original_msg.id)
                else:
                    _logger.warning('Reply to message with ID %s not found', stanza_id)
            
            message = request.env['waha.message'].sudo().create(vals)
            _logger.info('Created waha.message: %s (type=%s, relations auto-computed)', 
                        message.id, context['from_me'] and 'outbound' or 'inbound')
            
            # Get auto-computed chat and partner
            chat = message.waha_chat_id
            partner = message.partner_id
            
            _logger.info('Auto-computed relations: chat=%s (channel=%s), partner=%s, mail_message=%s', 
                        chat.id if chat else None,
                        chat.discuss_channel_id.id if (chat and chat.discuss_channel_id) else None,
                        partner.id if partner else None,
                        message.mail_message_id.id if message.mail_message_id else None)
            
            if not chat:
                _logger.error('Failed to auto-compute chat for message %s', message.id)
                return
            
            # Log discuss channel details
            if chat.discuss_channel_id:
                _logger.info('Discuss channel details: id=%s, name=%s, type=%s, members=%s',
                           chat.discuss_channel_id.id,
                           chat.discuss_channel_id.name,
                           chat.discuss_channel_id.channel_type,
                           len(chat.discuss_channel_id.channel_partner_ids))
            else:
                _logger.warning('Chat %s has no discuss_channel_id!', chat.id)
            
            # Only create discuss.message for INBOUND messages
            # Outbound messages already have mail_message_id from _compute_mail_message_id
            if not context['from_me']:
                if not partner:
                    _logger.warning('No partner for inbound message %s', message.id)
                
                # Create discuss.message in channel (auto-computed)
                discuss_channel = chat.discuss_channel_id
                if discuss_channel and message.mail_message_id:
                    _logger.info('Discuss message auto-created: %s', message.mail_message_id.id)
                else:
                    _logger.warning('Failed to auto-create discuss message for %s', message.id)
            else:
                _logger.info('Skipping discuss.message for outbound message (already exists)')
            
            # Process media attachments - now delegated to waha.message
            message.process_payload_media()
            
            # Update chat metadata
            chat.update_last_message(message.wa_timestamp)
            
            _logger.info('Successfully processed incoming message: %s', message.id)
            
        except Exception as e:
            _logger.exception('Error handling incoming message: %s', str(e))
    
    def _extract_message_context(self, payload):
        """
        Extract and normalize message context from WAHA payload
        
        Returns:
            dict with parsed message information
        """
        # Extract basic info
        from_raw = payload.get('from', '')
        from_me = payload.get('fromMe', False)
        participant = payload.get('participant', '')
        
        _logger.info('Extracting context: from=%s, fromMe=%s, participant=%s', from_raw, from_me, participant)
        
        # Determine chat type
        is_group = '@g.us' in from_raw
        chat_id = from_raw
        
        # Extract sender ID (could be LID or phone)
        sender_raw = participant if (is_group and participant) else from_raw
        
        _logger.info('Sender raw: %s (is_group=%s)', sender_raw, is_group)
        
        # Determine if it's a LID or phone number
        sender_lid = None
        sender_phone = None
        
        if '@lid' in sender_raw:
            # It's a LID
            sender_lid = sender_raw.split('@')[0]
            _logger.info('Extracted LID: %s', sender_lid)
        elif '@c.us' in sender_raw:
            # It's a phone number
            sender_phone = sender_raw.split('@')[0]
            _logger.info('Extracted phone: %s', sender_phone)
        else:
            # Fallback - treat as phone
            sender_phone = sender_raw.split('@')[0] if '@' in sender_raw else sender_raw
            _logger.info('Fallback phone: %s', sender_phone)
        
        # Extract content
        body = payload.get('body', '')
        if isinstance(body, dict):
            body = body.get('text', '') or str(body)
        elif not isinstance(body, str):
            body = str(body) if body else ''
        
        # Extract timestamp
        timestamp_value = payload.get('timestamp')
        wa_timestamp = None
        if timestamp_value:
            try:
                wa_timestamp = datetime.fromtimestamp(int(timestamp_value))
            except (ValueError, TypeError):
                wa_timestamp = fields.Datetime.now()
        
        # Extract reply_to (quoted message)
        reply_to_stanza_id = None

        # Modern WAHA payloads expose quoted messages in top-level `replyTo`.
        # Older/engine-specific payloads may only expose `_data.quotedStanzaID`.
        # Prefer the full message id when it is available because it matches
        # our stored msg_uid exactly; fall back to stanza id suffix otherwise.
        reply_to = payload.get('replyTo') or {}
        if isinstance(reply_to, dict):
            reply_to_stanza_id = reply_to.get('id')

        _data = payload.get('_data', {})
        quoted_stanza_id = _data.get('quotedStanzaID')
        
        if not reply_to_stanza_id and quoted_stanza_id:
            reply_to_stanza_id = quoted_stanza_id
        if reply_to_stanza_id:
            _logger.info('Detected reply to message ID: %s', reply_to_stanza_id)
        
        return {
            'msg_uid': payload.get('id'),
            'from_me': from_me,
            'chat_id': chat_id,
            'is_group': is_group,
            'sender_lid': sender_lid,
            'sender_phone': sender_phone,
            'participant': participant,
            'body': body,
            'wa_timestamp': wa_timestamp or fields.Datetime.now(),
            'reply_to_stanza_id': reply_to_stanza_id,
        }

    def _find_reply_to_message(self, env, account, chat_id, reply_to_id):
        """Find the waha.message referenced by a WAHA reply payload."""
        if not reply_to_id:
            return env['waha.message']

        Message = env['waha.message'].sudo()
        base_domain = [
            ('wa_account_id', '=', account.id),
            ('raw_chat_id', '=', chat_id),
        ]

        # First try the exact modern WAHA replyTo.id value.
        message = Message.search(base_domain + [('msg_uid', '=', reply_to_id)], limit=1)
        if message:
            return message

        # Fallback for older `_data.quotedStanzaID`, which is often only the
        # suffix of the serialized WhatsApp message id.
        return Message.search(base_domain + [('msg_uid', 'ilike', reply_to_id)], limit=1)
    
    def _handle_message_ack(self, data):
        """
        Handle message acknowledgment webhook
        
        ACK values:
        - 0: ERROR
        - 1: PENDING
        - 2: SERVER
        - 3: DEVICE
        - 4: READ
        - 5: PLAYED
        """
        try:
            payload = data.get('payload', {})
            msg_uid = payload.get('id')
            
            if not msg_uid:
                _logger.warning('No message ID in ACK webhook')
                return
            
            # Find message by msg_uid
            message = request.env['waha.message'].sudo().search([
                ('msg_uid', '=', msg_uid)
            ], limit=1)
            
            if not message:
                _logger.warning('Message not found for ACK: %s', msg_uid)
                return
            
            # Delegate to waha.message.update_status_from_webhook
            message.update_status_from_webhook(payload)
            
        except Exception as e:
            _logger.exception('Error handling message ACK: %s', str(e))
    
    def _handle_session_status(self, data):
        """
        Handle session status change webhook
        
        Status values:
        - STOPPED
        - STARTING
        - SCAN_QR_CODE
        - WORKING
        - FAILED
        """
        try:
            session_name = data.get('session')
            payload = data.get('payload', {})
            status = payload.get('status')
            
            # Find account
            account = request.env['waha.account'].sudo().search([
                ('session_name', '=', session_name)
            ], limit=1)
            
            if not account:
                _logger.warning('No account found for session: %s', session_name)
                return
            
            # Map WAHA status to account status
            status_mapping = {
                'STOPPED': 'disconnected',
                'STARTING': 'connecting',
                'SCAN_QR_CODE': 'connecting',
                'WORKING': 'connected',
                'FAILED': 'error',
            }
            
            new_status = status_mapping.get(status)
            if new_status and new_status != account.status:
                account.write({'status': new_status})
                _logger.info('Account %s status updated to: %s', account.name, new_status)
            
        except Exception as e:
            _logger.exception('Error handling session status: %s', str(e))
