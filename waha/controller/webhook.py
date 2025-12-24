# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
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
            
            # Verify webhook token
            verify_token = request.httprequest.headers.get('X-Webhook-Token')
            if not self._verify_token(verify_token):
                _logger.warning('Invalid webhook token')
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
    
    def _verify_token(self, token):
        """Verify webhook token matches any account's verify token"""
        if not token:
            return False
        
        account = request.env['waha.account'].sudo().search([
            ('webhook_verify_token', '=', token)
        ], limit=1)
        
        return bool(account)
    
    def _handle_incoming_message(self, data):
        """
        Handle incoming message webhook
        
        Example data:
        {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "true_1234567890@c.us_ABCDEF",
                "timestamp": 1234567890,
                "from": "1234567890@c.us",
                "fromMe": false,
                "body": "Hello!",
                "hasMedia": false,
                "ack": 0
            }
        }
        """
        try:
            session_name = data.get('session')
            payload = data.get('payload', {})
            
            # Find account by session name
            account = request.env['waha.account'].sudo().search([
                ('session_name', '=', session_name)
            ], limit=1)
            
            if not account:
                _logger.warning('No account found for session: %s', session_name)
                return
            
            # Extract message data
            msg_uid = payload.get('id')
            from_number = payload.get('from', '').replace('@c.us', '')
            body = payload.get('body', '')
            has_media = payload.get('hasMedia', False)
            
            # Check if message already exists
            existing = request.env['waha.message'].sudo().search([
                ('msg_uid', '=', msg_uid)
            ], limit=1)
            
            if existing:
                _logger.info('Message already exists: %s', msg_uid)
                return
            
            # Create incoming message
            message_vals = {
                'wa_account_id': account.id,
                'msg_uid': msg_uid,
                'mobile_number': from_number,
                'body': body,
                'message_type': 'inbound',
                'state': 'received',
                'free_text_json': json.dumps(payload),
            }
            
            message = request.env['waha.message'].sudo().create(message_vals)
            
            # Find partner by phone number
            partner = self._find_partner_by_phone(from_number)
            
            # Post to chatter if partner found
            if partner:
                partner.sudo().message_post(
                    body=f'<p><strong>WhatsApp Message:</strong></p>{body}',
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
                message.mail_message_id = partner.message_ids[0].id
            
            _logger.info('Incoming message processed: %s', msg_uid)
            
        except Exception as e:
            _logger.exception('Error handling incoming message: %s', str(e))
    
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
            ack = payload.get('ack', 0)
            
            # Find message
            message = request.env['waha.message'].sudo().search([
                ('msg_uid', '=', msg_uid)
            ], limit=1)
            
            if not message:
                _logger.warning('Message not found for ACK: %s', msg_uid)
                return
            
            # Update state based on ACK
            state_mapping = {
                0: 'error',
                1: 'outgoing',
                2: 'sent',
                3: 'delivered',
                4: 'read',
                5: 'read',
            }
            
            new_state = state_mapping.get(ack, message.state)
            if new_state != message.state:
                message.write({'state': new_state})
                _logger.info('Message %s updated to state: %s', msg_uid, new_state)
            
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
    
    def _find_partner_by_phone(self, phone):
        """Find partner by phone number"""
        try:
            # Try to find by mobile first
            partner = request.env['res.partner'].sudo().search([
                ('mobile', 'ilike', phone)
            ], limit=1)
            
            if not partner:
                # Try by phone
                partner = request.env['res.partner'].sudo().search([
                    ('phone', 'ilike', phone)
                ], limit=1)
            
            return partner
            
        except Exception:
            return None
