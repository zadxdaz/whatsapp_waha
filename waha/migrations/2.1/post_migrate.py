# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migration script for waha module 2.1

    Makes discuss.channel the source of truth for WhatsApp conversations:
    - Migrates existing channels from channel_type='whatsapp' to 'waha'
    - Creates a discuss.channel for every waha.chat that has none
    - Backfills discuss.channel fields (wa_chat_id, account, partner, group)
    - Links every waha_message to its discuss.channel
    - Creates channels for message raw_chat_ids that have no waha.chat
    """
    _logger.info('=== WAHA Migration 2.1 START ===')

    # Guard: only run if the new column was created by the ORM
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name='waha_message' AND column_name='discuss_channel_id'
    """)
    if not cr.fetchone():
        _logger.info('waha_message.discuss_channel_id missing — skipping 2.1 migration')
        return

    # 1. Migrate existing channels (channel_type whatsapp -> waha) and backfill fields
    cr.execute("""
        UPDATE discuss_channel dc
        SET channel_type = 'waha',
            is_whatsapp = TRUE,
            wa_chat_id = wc.wa_chat_id,
            whatsapp_account_id = wc.wa_account_id,
            whatsapp_partner_id = wc.whatsapp_partner_id,
            whatsapp_group_id = wc.whatsapp_group_id
        FROM waha_chat wc
        WHERE dc.id = wc.discuss_channel_id
          AND dc.id IS NOT NULL
    """)
    _logger.info('Migrated %d existing channels to waha type', cr.rowcount)

    # 2. Create a discuss.channel for every waha.chat without one
    cr.execute("""
        INSERT INTO discuss_channel
            (name, channel_type, is_whatsapp, wa_chat_id, whatsapp_account_id,
             whatsapp_partner_id, whatsapp_group_id, create_uid, create_date,
             write_uid, write_date)
        SELECT wc.name, 'waha', TRUE, wc.wa_chat_id, wc.wa_account_id,
               wc.whatsapp_partner_id, wc.whatsapp_group_id, 1, now(), 1, now()
        FROM waha_chat wc
        WHERE wc.discuss_channel_id IS NULL
    """)
    channels_created = cr.rowcount
    _logger.info('Created %d new discuss channels', channels_created)

    # Link waha.chat to the freshly created channels
    cr.execute("""
        UPDATE waha_chat wc
        SET discuss_channel_id = dc.id
        FROM discuss_channel dc
        WHERE wc.discuss_channel_id IS NULL
          AND dc.wa_chat_id = wc.wa_chat_id
          AND dc.whatsapp_account_id = wc.wa_account_id
    """)

    # 3. Link messages to channels (via waha.chat FK, then via raw_chat_id)
    cr.execute("""
        UPDATE waha_message wm
        SET discuss_channel_id = wc.discuss_channel_id
        FROM waha_chat wc
        WHERE wm.waha_chat_id = wc.id
          AND wm.discuss_channel_id IS NULL
          AND wc.discuss_channel_id IS NOT NULL
    """)
    _logger.info('Linked %d messages via waha.chat', cr.rowcount)

    cr.execute("""
        UPDATE waha_message wm
        SET discuss_channel_id = dc.id
        FROM discuss_channel dc
        WHERE wm.discuss_channel_id IS NULL
          AND dc.wa_chat_id = wm.raw_chat_id
          AND dc.whatsapp_account_id = wm.wa_account_id
    """)
    _logger.info('Linked %d messages via raw_chat_id', cr.rowcount)

    # 4. Create channels for raw_chat_ids that have no channel at all
    cr.execute("""
        INSERT INTO discuss_channel
            (name, channel_type, is_whatsapp, wa_chat_id, whatsapp_account_id,
             create_uid, create_date, write_uid, write_date)
        SELECT wm.raw_chat_id, 'waha', TRUE, wm.raw_chat_id, wm.wa_account_id,
               1, now(), 1, now()
        FROM (SELECT DISTINCT raw_chat_id, wa_account_id FROM waha_message
              WHERE raw_chat_id IS NOT NULL AND raw_chat_id != ''
              AND discuss_channel_id IS NULL) wm
        LEFT JOIN discuss_channel dc
          ON dc.wa_chat_id = wm.raw_chat_id
         AND dc.whatsapp_account_id = wm.wa_account_id
        WHERE dc.id IS NULL
    """)
    _logger.info('Created %d channels for orphan raw_chat_ids', cr.rowcount)

    cr.execute("""
        UPDATE waha_message wm
        SET discuss_channel_id = dc.id
        FROM discuss_channel dc
        WHERE wm.discuss_channel_id IS NULL
          AND dc.wa_chat_id = wm.raw_chat_id
          AND dc.whatsapp_account_id = wm.wa_account_id
    """)
    _logger.info('Linked %d orphan messages', cr.rowcount)

    _logger.info('=== WAHA Migration 2.1 COMPLETE ===')
