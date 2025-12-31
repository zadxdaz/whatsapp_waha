# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID
import re
import logging

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Post-migration script to clean up data
    1. Clean up discuss.channel records with invalid whatsapp fields
    2. Normalize mobile_number in waha.message records (remove @lid, @c.us, @g.us suffixes)
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Clean up any discuss.channel records with invalid whatsapp_group_id
    # This shouldn't happen but protect against it
    channels = env['discuss.channel'].search([])
    
    for channel in channels:
        # If channel is not whatsapp but has whatsapp fields set, clear them
        if not channel.is_whatsapp:
            if channel.whatsapp_group_id or channel.whatsapp_account_id:
                channel.write({
                    'whatsapp_group_id': False,
                    'whatsapp_account_id': False,
                })
                _logger.info('Cleaned up non-WhatsApp channel %s', channel.id)
    
    # Normalize mobile_number in waha.message records
    # Remove @lid, @c.us, @g.us suffixes that may have been incorrectly stored
    messages = env['waha.message'].search([])
    
    for message in messages:
        if message.mobile_number:
            original = message.mobile_number
            # Remove WhatsApp format suffixes
            normalized = original.replace('@c.us', '').replace('@lid', '').replace('@g.us', '')
            # Remove non-digit characters except +
            normalized = re.sub(r'[^\d+]', '', normalized)
            # Remove leading + if present
            normalized = normalized.lstrip('+')
            
            # Only update if it changed
            if normalized != original:
                # Validate it's still a reasonable phone number
                digits_only = ''.join(filter(str.isdigit, normalized))
                if 10 <= len(digits_only) <= 15:
                    message.write({'mobile_number': digits_only})
                    _logger.info('Normalized mobile_number: %s -> %s', original, digits_only)
                else:
                    _logger.warning('Could not normalize mobile_number: %s (digits: %s)', original, digits_only)
