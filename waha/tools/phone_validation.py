# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""
Phone validation utilities for WAHA
Based on whatsapp/tools/phone_validation.py
"""

import logging
import phonenumbers

from odoo.addons.phone_validation.tools import phone_validation

_logger = logging.getLogger(__name__)


def wa_phone_format(country, number, force_format='E164', raise_exception=True):
    """
    Format phone number for WhatsApp
    
    Args:
        country: res.country record or country code
        number: Phone number to format
        force_format: Format to use ('E164', 'INTERNATIONAL', 'WHATSAPP')
        raise_exception: Whether to raise exception on error
        
    Returns:
        str: Formatted phone number or False
    """
    try:
        # Get country code
        if hasattr(country, 'code'):
            country_code = country.code
        elif hasattr(country, 'phone_code'):
            country_code = None
            region = None
        else:
            country_code = country if isinstance(country, str) else None

        # Format number
        formatted = phone_validation.phone_format(
            number,
            country_code,
            country.phone_code if hasattr(country, 'phone_code') else None,
            force_format=force_format,
            raise_exception=raise_exception
        )
        
        # For WhatsApp format, add @c.us suffix
        if force_format == 'WHATSAPP' and formatted:
            # Remove + from E164 format
            clean_number = formatted.replace('+', '')
            return f"{clean_number}@c.us"
        
        return formatted
        
    except Exception as e:
        if raise_exception:
            raise
        _logger.warning('Error formatting phone number %s: %s', number, str(e))
        return False


def wa_sanitize_number(number):
    """
    Sanitize phone number for WhatsApp
    Removes all non-digit characters except +
    
    Args:
        number: Phone number to sanitize
        
    Returns:
        str: Sanitized number
    """
    if not number:
        return ''
    
    # Keep only digits and +
    import re
    sanitized = re.sub(r'[^\d+]', '', str(number))
    
    return sanitized
