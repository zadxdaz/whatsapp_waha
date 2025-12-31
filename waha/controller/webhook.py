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
        Handle incoming message webhook - delegates to waha.message.process_inbound_webhook
        """
        try:
            session_name = data.get('session')
            
            # Find account
            account = request.env['waha.account'].sudo().search([
                ('session_name', '=', session_name)
            ], limit=1)
            
            if not account:
                _logger.warning('No account found for session: %s', session_name)
                return
            
            # Delegate to waha.message.process_inbound_webhook
            message = request.env['waha.message'].sudo().process_inbound_webhook(data, account)
            
            _logger.info('Incoming message processed: %s', message.id)
            
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
