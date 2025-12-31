# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID
import logging
import json

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Post-migration script for v1.2
    1. Extract waha_chat_id from free_text_json for all messages
    2. Extract and store wa_chat_id in partners from their received messages
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    _logger.info('Starting migration 1.2: Extract waha_chat_id and populate wa_chat_id')
    
    # First, extract waha_chat_id from free_text_json for messages
    messages = env['waha.message'].search([('message_type', '=', 'inbound')])
    
    message_updated_count = 0
    for message in messages:
        try:
            if message.free_text_json:
                payload = message.free_text_json if isinstance(message.free_text_json, dict) else json.loads(message.free_text_json)
                
                # Extract chat_id from the payload
                chat_id = payload.get('chatId', '') or payload.get('from', '')
                
                if chat_id and not message.waha_chat_id:
                    message.write({'waha_chat_id': chat_id})
                    _logger.info('Updated message %s with waha_chat_id: %s', message.id, chat_id)
                    message_updated_count += 1
        except Exception as e:
            _logger.warning('Could not extract waha_chat_id from message %s: %s', message.id, str(e))
    
    _logger.info('Updated %d message records with waha_chat_id', message_updated_count)
    
    # Second, extract wa_chat_id from messages and store in partners
    partners = env['res.partner'].search([])
    
    partner_updated_count = 0
    for partner in partners:
        try:
            # Find the first received message for this partner
            msg = env['waha.message'].search([
                ('mobile_number', 'ilike', partner.mobile if partner.mobile else ''),
                ('message_type', '=', 'inbound'),
                ('waha_chat_id', '!=', False),
            ], order='id asc', limit=1)
            
            if msg and msg.waha_chat_id and not partner.wa_chat_id:
                partner.write({'wa_chat_id': msg.waha_chat_id})
                _logger.info('Updated partner %s with wa_chat_id: %s', partner.id, msg.waha_chat_id)
                partner_updated_count += 1
        except Exception as e:
            _logger.warning('Could not extract wa_chat_id for partner %s: %s', partner.id, str(e))
    
    _logger.info('Migration 1.2 complete: Updated %d partners with wa_chat_id', partner_updated_count)
