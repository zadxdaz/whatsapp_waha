# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID
import re
import logging

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    """
    Post-migration script for v1.1
    Normalize mobile_number in waha.message records 
    - Remove @lid, @c.us, @g.us suffixes that may have been incorrectly stored
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    _logger.info('Starting migration 1.1: Normalize mobile_number fields')
    
    # Normalize mobile_number in waha.message records
    messages = env['waha.message'].search([])
    
    normalized_count = 0
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
                    normalized_count += 1
                else:
                    _logger.warning('Could not normalize mobile_number: %s (digits: %s)', original, digits_only)
    
    _logger.info('Migration 1.1 complete: Normalized %d message records', normalized_count)
