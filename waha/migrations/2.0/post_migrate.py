# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migration script for waha module 2.0
    
    Changes:
    - Migrates waha_chat_id from Char to Many2one
    - Populates new raw_chat_id field from old waha_chat_id_old
    - Removes obsolete fields
    """
    _logger.info('=== WAHA Migration 2.0 START ===')
    
    # Check if old column exists
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='waha_message' 
        AND column_name='waha_chat_id_old'
    """)
    
    if cr.fetchone():
        _logger.info('Found waha_chat_id_old column, migrating data...')
        
        # Populate raw_chat_id from waha_chat_id_old
        cr.execute("""
            UPDATE waha_message 
            SET raw_chat_id = waha_chat_id_old 
            WHERE waha_chat_id_old IS NOT NULL 
            AND raw_chat_id IS NULL
        """)
        
        rows_updated = cr.rowcount
        _logger.info('Migrated %d rows: waha_chat_id_old -> raw_chat_id', rows_updated)
        
        # Drop old column
        cr.execute("ALTER TABLE waha_message DROP COLUMN IF EXISTS waha_chat_id_old CASCADE")
        _logger.info('Dropped waha_chat_id_old column')
    else:
        _logger.info('No waha_chat_id_old column found, skipping migration')
    
    # Clean up other obsolete columns if they still exist
    obsolete_columns = [
        'mobile_number',
        'mobile_number_formatted',
        'free_text_json',
        'parent_id',
        'wa_template_id'
    ]
    
    for col in obsolete_columns:
        cr.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='waha_message' 
            AND column_name='{col}'
        """)
        
        if cr.fetchone():
            cr.execute(f"ALTER TABLE waha_message DROP COLUMN IF EXISTS {col} CASCADE")
            _logger.info('Dropped obsolete column: %s', col)
    
    _logger.info('=== WAHA Migration 2.0 COMPLETE ===')
