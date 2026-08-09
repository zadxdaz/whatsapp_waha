# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import html
import logging
import re
from datetime import datetime
from html.parser import HTMLParser

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.addons.waha.tools.waha_api import WahaApi

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML → WhatsApp markdown converter
# ---------------------------------------------------------------------------
# Odoo Discuss stores rich text as HTML.  WhatsApp uses its own lightweight
# markdown (*bold*, _italic_, ~strike~, `code`, bullet lists, newlines).
# Simply stripping tags loses all formatting; this converter preserves it.

class _WaHtmlParser(HTMLParser):
    """SAX-style parser that converts Odoo HTML to WhatsApp markdown."""

    # Inline tags whose open/close both wrap the content with a marker.
    _INLINE = {
        'strong': '*', 'b': '*',
        'em': '_', 'i': '_',
        'del': '~', 's': '~', 'strike': '~',
        'code': '`',
    }

    def __init__(self):
        # convert_charrefs=True decodes &amp; &nbsp; etc. automatically
        super().__init__(convert_charrefs=True)
        self._parts = []
        self._in_pre = False
        self._in_blockquote = False

    # -- tag handlers --------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == 'br':
            self._parts.append('\n')
        elif t in ('p', 'div', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            # Inside a blockquote the '> ' marker already started the line;
            # suppress the leading newline so we don't get "> \ntext".
            if not self._in_blockquote and self._parts and not self._parts[-1].endswith('\n'):
                self._parts.append('\n')
        elif t == 'li':
            self._parts.append('• ')
        elif t == 'pre':
            self._in_pre = True
            self._parts.append('```\n')
        elif t == 'blockquote':
            self._in_blockquote = True
            if self._parts and not self._parts[-1].endswith('\n'):
                self._parts.append('\n')
            self._parts.append('> ')
        elif t in self._INLINE:
            self._parts.append(self._INLINE[t])
        # <a>, <ul>, <ol>, <span>, <table>, <td>, etc. → just render content

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == 'blockquote':
            self._in_blockquote = False
            if self._parts and not self._parts[-1].endswith('\n'):
                self._parts.append('\n')
        elif t in ('p', 'div', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'):
            if not self._in_blockquote:
                self._parts.append('\n')
        elif t == 'pre':
            self._in_pre = False
            self._parts.append('\n```')
        elif t in self._INLINE:
            self._parts.append(self._INLINE[t])

    def handle_data(self, data):
        # &nbsp; becomes \xa0 after convert_charrefs — normalise to regular space
        self._parts.append(data.replace('\xa0', ' '))

    # -- result --------------------------------------------------------------

    def get_text(self):
        text = ''.join(self._parts)
        # Collapse 3+ consecutive newlines → 2 (single blank line max)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def _html_to_whatsapp(html_body):
    """Convert Odoo HTML rich text to WhatsApp markdown plain text.

    Mapping:
        <strong>/<b>        → *bold*
        <em>/<i>            → _italic_
        <del>/<s>/<strike>  → ~strikethrough~
        <code>              → `code`
        <pre>               → ```block```
        <br>, </p>, </div>  → newline
        <li>                → bullet (•)
        <blockquote>        → > prefix
        everything else     → text content only (tags stripped)
    """
    if not html_body:
        return ''
    parser = _WaHtmlParser()
    parser.feed(html_body)
    return parser.get_text()
# ---------------------------------------------------------------------------


class WahaMessage(models.Model):
    """
    WAHA Message - Manages WhatsApp messages
    
    Responsibilities:
    - Store message content and metadata
    - Send messages through WAHA API
    - Update message status (sent, delivered, read, failed)
    - Create discuss.message entries in channels
    - Handle message attachments (media)
    - Link to discuss.channel and res.partner
    
    Delegates:
    - Conversation management → discuss.channel (channel_type='waha')
    - Contact management → waha.partner
    """
    _name = 'waha.message'
    _description = 'WhatsApp Message'
    _order = 'wa_timestamp desc, id desc'
    _rec_name = 'msg_uid'

    # ============================================================
    # FIELDS
    # ============================================================
    
    # Core identification
    msg_uid = fields.Char(
        string="WhatsApp Message ID",
        compute='_compute_msg_uid',
        store=True,
        readonly=False,
        index=True,
        help="Unique message identifier from WAHA (auto-sent if missing)"
    )
    
    wa_account_id = fields.Many2one(
        'waha.account',
        string="WhatsApp Account",
        required=True,
        ondelete='cascade',
        index=True
    )
    
    # Message direction and type
    message_type = fields.Selection([
        ('outbound', 'Outbound'),
        ('inbound', 'Inbound')
    ], string="Direction", required=True, default='outbound', index=True)
    
    content_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('sticker', 'Sticker'),
        ('location', 'Location'),
    ], string="Content Type", compute='_compute_content_type', store=True, readonly=False, default='text')
    
    # Message state
    state = fields.Selection([
        ('draft', 'Draft'),
        ('outgoing', 'Sending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('received', 'Received'),
        ('error', 'Failed'),
        ('cancel', 'Cancelled')
    ], string="State", default='draft', required=True, index=True)
    
    failure_type = fields.Selection([
        ('account', 'Account Error'),
        ('phone_invalid', 'Invalid Phone Number'),
        ('contact_not_found', 'Contact Not in WhatsApp'),
        ('network', 'Network Error'),
        ('unknown', 'Unknown Error')
    ], string="Failure Type")
    
    failure_reason = fields.Text(string="Failure Reason")
    
    # Content
    body = fields.Text(string="Message Content", required=True)
    
    # Raw WAHA identifiers (used to compute relationships)
    raw_chat_id = fields.Char(
        string="Raw Chat ID",
        help="Original chat ID from WAHA (e.g., 123456@c.us or 123456@g.us)"
    )
    
    raw_sender_lid = fields.Char(
        string="Raw Sender LID",
        help="Sender's WhatsApp LID (Long ID)"
    )
    
    raw_sender_phone = fields.Char(
        string="Raw Sender Phone",
        help="Sender's phone number (normalized, no symbols)"
    )
    
    # Links to other models (computed automatically)
    discuss_channel_id = fields.Many2one(
        'discuss.channel',
        string="Discuss Channel",
        compute='_compute_discuss_channel_id',
        store=True,
        readonly=False,
        ondelete='set null',
        index=True,
        help="WhatsApp conversation channel (discuss.channel) this message belongs to"
    )
    
    waha_partner_id = fields.Many2one(
        'waha.partner',
        string="WAHA Contact",
        compute='_compute_waha_partner_id',
        store=True,
        readonly=False,
        ondelete='set null',
        index=True,
        help="WAHA partner record who sent/received this message"
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string="Contact",
        related='waha_partner_id.partner_id',
        store=True,
        readonly=True,
        help="Contact who sent/received this message (from WAHA partner)"
    )
    
    mail_message_id = fields.Many2one(
        'mail.message',
        string="Discuss Message",
        compute='_compute_mail_message_id',
        store=True,
        readonly=False,
        ondelete='set null',
        help="Linked message in Discuss channel (auto-created)"
    )
    
    # Reply handling
    reply_to_message_id = fields.Many2one(
        'waha.message',
        string="Reply To",
        ondelete='set null',
        help="Original message this is replying to"
    )
    
    reply_to_msg_uid = fields.Char(
        string="Reply To Message UID",
        help="WAHA message UID to reply to"
    )
    
    # Attachments
    attachment_ids = fields.One2many(
        'ir.attachment',
        'res_id',
        domain=[('res_model', '=', 'waha.message')],
        string="Attachments"
    )
    
    # Timestamps
    wa_timestamp = fields.Datetime(
        string="WhatsApp Timestamp",
        help="Original timestamp from WhatsApp"
    )
    
    sent_date = fields.Datetime(string="Sent Date")
    delivered_date = fields.Datetime(string="Delivered Date")
    read_date = fields.Datetime(string="Read Date")
    
    # Metadata
    participant_id = fields.Char(
        string="Participant ID",
        help="For group messages: WhatsApp ID of the sender"
    )
    
    raw_payload = fields.Json(
        string="Raw WAHA Payload",
        help="Complete JSON payload from WAHA webhook"
    )
    
    sent_from_device = fields.Boolean(
        string="Sent from Device",
        default=False,
        help="True when this outbound message was sent directly from a physical device "
             "(not dispatched by Odoo through the WAHA API). "
             "These messages are stored for visibility only — they must never be re-sent."
    )

    attachment_msg_uids = fields.Json(
        string="Attachment Message UIDs",
        help="List of WAHA message IDs for each individual attachment sent in a "
             "multi-attachment message. Used to deduplicate webhook echoes when a "
             "single Odoo message triggers multiple WAHA sends."
    )

    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('unique_msg_uid',
         'unique(msg_uid, wa_account_id)',
         "Each WhatsApp message ID must be unique per account.")
    ]
    
    @api.constrains('discuss_channel_id', 'mail_message_id')
    def _check_chat_channel_consistency(self):
        """
        Ensure all messages from the same chat are in the same discuss channel
        
        This prevents data inconsistency where messages from one WhatsApp chat
        could end up in different discuss channels.
        """
        for message in self:
            if not message.discuss_channel_id or not message.mail_message_id:
                continue
            
            # Get the channel from mail_message
            message_channel = message.mail_message_id.model == 'discuss.channel' and \
                            self.env['discuss.channel'].browse(message.mail_message_id.res_id)
            
            if not message_channel:
                continue
            
            # Validate they match
            if message_channel.id != message.discuss_channel_id.id:
                raise ValidationError(_(
                    'Message consistency error: Messages from chat "%s" (ID: %s) must all be in the same discuss channel.\n'
                    'Expected channel: "%s" (ID: %s)\n'
                    'Found channel: "%s" (ID: %s)\n\n'
                    'All messages from the same WhatsApp chat must belong to the same discuss channel.'
                ) % (
                    message.discuss_channel_id.name,
                    message.discuss_channel_id.id,
                    message.discuss_channel_id.name,
                    message.discuss_channel_id.id,
                    message_channel.name,
                    message_channel.id
                ))

    # ============================================================
    # COMPUTED FIELDS - AUTO RELATIONSHIPS
    # ============================================================
    
    @api.depends('raw_payload')
    def _compute_content_type(self):
        """
        Auto-detect content type from raw_payload
        
        Uses WAHA payload structure to determine if message contains
        text, image, video, audio, document, sticker, or location.
        """
        for message in self:
            if not message.raw_payload:
                message.content_type = 'text'
                continue
            
            message.content_type = message._detect_content_type(message.raw_payload)
    
    @api.depends('raw_chat_id', 'wa_account_id')
    def _compute_discuss_channel_id(self):
        """
        Auto-compute channel relationship from raw_chat_id (lookup only)
        
        This is intentionally a pure lookup: it NEVER creates a channel.
        Channels are created explicitly by the callers (webhook, composer,
        factories) via discuss.channel.find_or_create_wa().
        """
        for message in self:
            if not message.raw_chat_id or not message.wa_account_id:
                message.discuss_channel_id = False
                continue
            
            # Search for existing channel (no auto-create)
            channel = self.env['discuss.channel'].search([
                ('is_whatsapp', '=', True),
                ('wa_chat_id', '=', message.raw_chat_id),
                ('whatsapp_account_id', '=', message.wa_account_id.id)
            ], limit=1)
            
            message.discuss_channel_id = channel or False
    
    @api.depends('raw_sender_lid', 'raw_sender_phone', 'wa_account_id', 'message_type')
    def _compute_waha_partner_id(self):
        """
        Auto-compute waha.partner relationship from raw_sender_lid or raw_sender_phone
        
        Search priority:
        1. By LID (most reliable)
        2. By phone number
        
        For inbound messages: waha_partner is the sender
        For outbound messages: waha_partner is the recipient
        """
        for message in self:
            _logger.info('Computing waha_partner for message %s: lid=%s, phone=%s, chat=%s', 
                        message.id, message.raw_sender_lid, message.raw_sender_phone, message.raw_chat_id)
            
            # Need at least one identifier
            if not (message.raw_sender_lid or message.raw_sender_phone) or not message.wa_account_id:
                _logger.warning('No identifiers for message %s', message.id)
                message.waha_partner_id = False
                continue
            
            # Skip if invalid phone number (when no LID)
            if not message.raw_sender_lid and message.raw_sender_phone in ['0', '']:
                _logger.warning('Skipping partner creation for invalid identifiers')
                message.waha_partner_id = False
                continue
            
            # Skip if this is a group ID (groups don't have partners)
            if message.raw_sender_phone and '@g.us' in str(message.raw_sender_phone):
                _logger.warning('Skipping partner for group phone: %s', message.raw_sender_phone)
                message.waha_partner_id = False
                continue
            
            if message.raw_chat_id and '@g.us' in str(message.raw_chat_id):
                # This is a group message - partner is the participant who sent it
                _logger.info('Group message detected, searching for participant partner')
            
            # 1. Try to find by LID first (most reliable)
            waha_partner = None
            if message.raw_sender_lid:
                waha_partner = self.env['waha.partner'].search([
                    ('lid', '=', message.raw_sender_lid),
                    ('wa_account_id', '=', message.wa_account_id.id)
                ], limit=1)
                
                if waha_partner:
                    _logger.info('Found waha.partner by LID %s: %s', 
                               message.raw_sender_lid, waha_partner.id)
                    
                    # Update phone if missing and we have it
                    if message.raw_sender_phone and not waha_partner.phone_number:
                        _logger.info('Updating waha.partner %s with phone %s', 
                                   waha_partner.id, message.raw_sender_phone)
                        waha_partner.sudo().write({'phone_number': message.raw_sender_phone})
                    
                    message.waha_partner_id = waha_partner
                    continue
                else:
                    _logger.info('No waha.partner found by LID %s', message.raw_sender_lid)
            
            # 2. Try to find by phone number
            if message.raw_sender_phone:
                waha_partner = self.env['waha.partner'].search([
                    ('phone_number', '=', message.raw_sender_phone),
                    ('wa_account_id', '=', message.wa_account_id.id)
                ], limit=1)
                
                if waha_partner:
                    _logger.info('Found waha.partner by phone %s: %s', 
                               message.raw_sender_phone, waha_partner.id)
                    
                    # Update LID if missing and we have it
                    if message.raw_sender_lid and not waha_partner.lid:
                        _logger.info('Updating waha.partner %s with LID %s', 
                                   waha_partner.id, message.raw_sender_lid)
                        waha_partner.sudo().write({'lid': message.raw_sender_lid})
                    
                    message.waha_partner_id = waha_partner
                    continue
                else:
                    _logger.info('No waha.partner found by phone %s', message.raw_sender_phone)
            
            # 3. Not found - Auto-create waha.partner
            _logger.info('Auto-creating waha.partner (LID=%s, phone=%s)', 
                        message.raw_sender_lid, message.raw_sender_phone)
            
            # For group messages, don't auto-enrich (too slow and can fail)
            auto_enrich = '@g.us' not in str(message.raw_chat_id)
            
            waha_partner = self.env['waha.partner'].find_or_create_by_lid_or_phone(
                lid=message.raw_sender_lid,
                phone=message.raw_sender_phone,
                wa_account=message.wa_account_id,
                auto_enrich=auto_enrich
            )
            
            if waha_partner:
                _logger.info('Created/found waha.partner: %s', waha_partner.id)
                message.waha_partner_id = waha_partner
            else:
                _logger.warning('Failed to create waha.partner for LID=%s, phone=%s', 
                              message.raw_sender_lid, message.raw_sender_phone)
                message.waha_partner_id = False
    
    @api.depends('discuss_channel_id', 'waha_partner_id', 'body', 'wa_timestamp', 'message_type', 'reply_to_message_id')
    def _compute_mail_message_id(self):
        """
        Auto-compute discuss message relationship
        
        Creates mail.message in the discuss channel if:
        - discuss_channel_id exists
        - waha_partner_id exists (message author)
        - No mail_message_id exists yet
        
        All messages from the same chat land in the same channel by design:
        the channel is resolved from the WhatsApp chat id (raw_chat_id), and the
        same channel instance is reused for every message of that chat.
        """
        for message in self:
            # Skip if already has mail_message_id (ORM cache check)
            if message.mail_message_id:
                _logger.debug('Message %s already has mail_message_id: %s', message.id, message.mail_message_id.id)
                continue

            # Guard against multiple compute triggers within the same transaction.
            # discuss_channel_id and waha_partner_id are also computed fields, so Odoo can
            # fire this compute once per dependency that resolves. By the time the
            # second trigger runs, mail_message_id may already be written in DB even
            # though the ORM cache still shows False. Read directly from DB.
            if message.id:
                self.env.cr.execute(
                    'SELECT mail_message_id FROM waha_message WHERE id = %s',
                    (message.id,)
                )
                row = self.env.cr.fetchone()
                if row and row[0]:
                    _logger.debug('Message %s already has mail_message_id in DB: %s — skipping', message.id, row[0])
                    message.mail_message_id = row[0]
                    continue

            # Outbound messages posted from Odoo Discuss must already be linked
            # to the mail.message created by message_post(). If they are not,
            # do not auto-create a new Discuss message: using the recipient as
            # author would make it look like the contact sent our own text back.
            allow_outbound_discuss_sync = self.env.context.get('allow_outbound_discuss_sync')
            if message.message_type == 'outbound' and not allow_outbound_discuss_sync:
                _logger.warning(
                    'Outbound waha.message %s has no linked mail_message_id; '
                    'skipping auto-create to avoid duplicate Discuss messages',
                    message.id,
                )
                message.mail_message_id = False
                continue
            
            _logger.info('Processing message %s for discuss message creation (channel=%s, waha_partner=%s)', 
                        message.id, 
                        message.discuss_channel_id.id if message.discuss_channel_id else None,
                        message.waha_partner_id.id if message.waha_partner_id else None)
            
            # Need channel and waha_partner to create discuss message
            if not message.discuss_channel_id or not message.waha_partner_id:
                _logger.warning('Message %s missing channel or waha_partner: channel=%s, waha_partner=%s', 
                              message.id, 
                              bool(message.discuss_channel_id), 
                              bool(message.waha_partner_id))
                message.mail_message_id = False
                continue
            
            discuss_channel = message.discuss_channel_id
            
            _logger.info('Using chat channel: %s (id=%s, type=%s)', 
                        discuss_channel.name, 
                        discuss_channel.id,
                        discuss_channel.channel_type)
            
            # Auto-create discuss message
            _logger.info(
                'Auto-creating discuss message for waha.message %s in channel %s',
                message.id, discuss_channel.name
            )
            
            try:
                # Clean HTML from body
                body_clean = re.sub(r'<[^>]+>', '', message.body or '').strip()

                # Ensure we have a valid partner for author_id
                if not message.waha_partner_id or not message.waha_partner_id.partner_id:
                    _logger.warning('No waha_partner_id or partner_id for message %s, cannot create discuss message', message.id)
                    message.mail_message_id = False
                    continue

                if message.message_type == 'outbound':
                    author_partner = (
                        message.wa_account_id.account_partner_id
                        or message.wa_account_id.notify_user_ids[:1].partner_id
                        or self.env.user.partner_id
                    )
                else:
                    author_partner = message.waha_partner_id.partner_id

                # Before creating, check if a matching mail.message already exists
                # in the channel (guards against duplicate triggers / resyncs).
                # Skip for phone-sent messages (source='app'/'web'/'mobile') —
                # those are always new messages and should never match old posts.
                waha_webhook_source = self.env.context.get('waha_webhook_source', '')
                is_phone_source = waha_webhook_source and waha_webhook_source != 'api'
                if not is_phone_source:
                    existing_mail = message._find_existing_discuss_mail_message()
                    if existing_mail:
                        _logger.info(
                            'Found existing discuss message %s for waha.message %s — linking instead of creating',
                            existing_mail.id, message.id,
                        )
                        message.mail_message_id = existing_mail
                        continue

                # Prepare post params
                post_params = {
                    'body': body_clean,
                    'message_type': 'comment',
                    'subtype_xmlid': 'mail.mt_comment',
                    'author_id': author_partner.id,
                }
                _logger.info('Author partner for discuss message: %s', post_params['author_id'])

                # Resolve WhatsApp @mentions to Odoo partner IDs so that:
                # - Discuss highlights the mention visually
                # - "Solo menciones" notification preference fires for those users
                mentioned_ids = (message.raw_payload or {}).get('mentionedIds', [])
                if mentioned_ids:
                    mention_partner_ids = message._resolve_wa_mentions_to_partner_ids(mentioned_ids)
                    if mention_partner_ids:
                        post_params['partner_ids'] = mention_partner_ids
                        _logger.info(
                            'Resolved %d WhatsApp mention(s) to partner IDs: %s',
                            len(mention_partner_ids), mention_partner_ids,
                        )

                if message.wa_timestamp:
                    post_params['date'] = message.wa_timestamp

                # Add parent_id if this is a reply.  Do not force-create
                # missing outbound parents: that duplicates Discuss messages.
                if message.reply_to_message_id:
                    _logger.info('Message %s is reply to message %s', message.id, message.reply_to_message_id.id)
                    parent_mail_message = message._resolve_reply_parent_mail_message()
                    if parent_mail_message:
                        post_params['parent_id'] = parent_mail_message.id
                        _logger.info('Setting parent_id=%s for reply in Discuss', post_params['parent_id'])
                    else:
                        _logger.warning('Cannot set parent_id: parent message %s has no resolvable mail_message_id', message.reply_to_message_id.id)

                _logger.info('message_post params: %s', post_params)

                # Create message (with flag to prevent recursion)
                _logger.info('Calling message_post on channel %s (type=%s)', discuss_channel.id, discuss_channel.channel_type)
                discuss_msg = discuss_channel.with_context(
                    skip_whatsapp_send=True
                ).message_post(**post_params)

                _logger.info('message_post returned: %s', discuss_msg.id if discuss_msg else None)

                message.mail_message_id = discuss_msg

                _logger.info(
                    'Created discuss message %s for waha.message %s',
                    discuss_msg.id, message.id,
                )
            except Exception as e:
                _logger.exception(
                    'Failed to auto-create discuss message for waha.message %s: %s',
                    message.id, str(e)
                )
                import traceback
                _logger.error('Full traceback: %s', traceback.format_exc())
                message.mail_message_id = False
    
    def _clean_discuss_body(self, body):
        """Return a plain-text value comparable with mail.message.body."""
        self.ensure_one()
        return html.unescape(re.sub(r'<[^>]+>', '', body or '').strip())

    def _expected_discuss_author_partner(self):
        """Return the partner that should author this message in Discuss."""
        self.ensure_one()
        if self.message_type == 'outbound':
            return (
                self.wa_account_id.account_partner_id
                or self.wa_account_id.notify_user_ids[:1].partner_id
                or self.env.user.partner_id
            )
        return self.waha_partner_id.partner_id if self.waha_partner_id else self.env['res.partner']

    def _find_existing_discuss_mail_message(self):
        """Find a unique existing Discuss mail.message for this WAHA message.

        This is intentionally lookup-only: it never creates a Discuss message.
        Used to:
        - Repair historical outbound records whose mail_message_id was not linked.
        - Handle the API-send race condition where Odoo's transaction commits just
          before the webhook creates a waha.message.

        The search is intentionally strict:
        - Only matches within a 30-second window of the WhatsApp timestamp.
        - Never matches a mail.message already linked to another waha.message.
        """
        self.ensure_one()
        channel = self.discuss_channel_id
        if not channel:
            return self.env['mail.message']

        compare_date = self.wa_timestamp or self.sent_date
        if not compare_date:
            return self.env['mail.message']

        base_domain = [
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', channel.id),
            ('message_type', '=', 'comment'),
        ]
        expected_body = self._clean_discuss_body(self.body)

        def _matching_candidates(domain):
            candidates = self.env['mail.message'].sudo().search(domain, order='date desc, id desc', limit=200)
            if expected_body:
                candidates = candidates.filtered(lambda m: self._clean_discuss_body(m.body) == expected_body)
            # Always apply the time window — without it a single-match result
            # would be returned even if it is hours old (false positive).
            candidates = candidates.filtered(
                lambda m: m.date and abs((m.date - compare_date).total_seconds()) <= 30
            )
            return candidates

        expected_author = self._expected_discuss_author_partner()
        author_domain = list(base_domain)
        if expected_author:
            author_domain.append(('author_id', '=', expected_author.id))
        candidates = _matching_candidates(author_domain)

        # Historical unlinked outbound messages may have been authored by the
        # actual posting user, not the account notification user. If the strict
        # author match finds nothing, fall back to a channel/body match.
        if not candidates:
            candidates = _matching_candidates(base_domain)

        # Exclude candidates already claimed by another waha.message to avoid
        # linking two waha.messages to the same Discuss post.
        if candidates:
            already_linked = self.env['waha.message'].sudo().search([
                ('mail_message_id', 'in', candidates.ids),
                ('id', '!=', self.id),
            ]).mapped('mail_message_id').ids
            candidates = candidates.filtered(lambda m: m.id not in already_linked)

        if len(candidates) == 1:
            _logger.info('Resolved existing Discuss mail.message %s for waha.message %s', candidates.id, self.id)
            return candidates

        if len(candidates) > 1:
            _logger.warning(
                'Ambiguous Discuss mail.message match for waha.message %s in channel %s; leaving unlinked',
                self.id, channel.id,
            )
        return self.env['mail.message']

    def _resolve_reply_parent_mail_message(self):
        """Resolve the mail.message to use as parent_id for this reply."""
        self.ensure_one()
        parent = self.reply_to_message_id
        if not parent:
            return self.env['mail.message']
        if parent.mail_message_id:
            return parent.mail_message_id

        parent_mail_message = parent._find_existing_discuss_mail_message()
        if parent_mail_message:
            parent.sudo().write({'mail_message_id': parent_mail_message.id})
            return parent_mail_message
        return self.env['mail.message']

    def _backfill_missing_mail_message_id(self):
        """Safely link existing Discuss messages to missing WAHA records.

        Only unique matches are linked; ambiguous candidates are logged and left
        untouched to avoid corrupting reply threading.
        """
        repaired = self.env['waha.message']
        for message in self.filtered(lambda m: not m.mail_message_id):
            mail_message = message._find_existing_discuss_mail_message()
            if mail_message:
                message.sudo().write({'mail_message_id': mail_message.id})
                repaired |= message
        return repaired

    @api.depends('discuss_channel_id', 'waha_partner_id', 'state', 'body', 'wa_account_id')
    def _compute_msg_uid(self):
        """
        Auto-compute msg_uid by sending message through WAHA
        
        For outbound messages without msg_uid:
        - Validates required fields
        - Sends message through WAHA API
        - Sets msg_uid from WAHA response
        - Updates state to 'sent'
        
        For inbound messages or messages with msg_uid: keeps existing value
        """
        for message in self:
            # Skip if already has msg_uid or is inbound
            if message.msg_uid or message.message_type == 'inbound':
                continue
            
            # Skip if not outgoing state
            if message.state != 'outgoing':
                continue

            # Never re-send messages that came in from a physical device
            if message.sent_from_device:
                continue
            
            # Need channel and account to send
            if not message.discuss_channel_id or not message.wa_account_id:
                continue
            
            # Check account is connected
            if message.wa_account_id.status != 'connected':
                _logger.warning(
                    'Cannot auto-send message %s: account not connected',
                    message.id
                )
                continue
            
            # Auto-send through WAHA
            _logger.info(
                'Auto-sending message %s through WAHA (compute msg_uid)',
                message.id
            )
            
            try:
                api = WahaApi(message.wa_account_id)

                chat_wa_id = message.discuss_channel_id.wa_chat_id
                body_clean = _html_to_whatsapp(message.body)

                # Sort ascending by id so attachments are sent in the order they
                # were uploaded, not reversed (ir.attachment default is id desc).
                attachments = message.attachment_ids.sorted(key=lambda a: a.id)

                if not attachments and not body_clean:
                    _logger.warning('Message %s has no body or attachments', message.id)
                    continue

                all_uids = []

                if not attachments:
                    # Text-only message
                    _logger.info('Sending text message to %s', chat_wa_id)
                    result = api.send_text(chat_wa_id, body_clean, message.reply_to_msg_uid)
                    if result and result.get('id'):
                        all_uids.append(result['id'])
                else:
                    # Send every attachment; caption and reply_to only on the first.
                    for idx, att in enumerate(attachments):
                        caption = body_clean if idx == 0 else None
                        reply_to = message.reply_to_msg_uid if idx == 0 else None
                        mime = att.mimetype or ''

                        raw = att.datas
                        if isinstance(raw, bytes):
                            raw = raw.decode('utf-8')

                        _logger.info(
                            'Sending attachment %d/%d for message %s: name=%s, mime=%s',
                            idx + 1, len(attachments), message.id, att.name, mime,
                        )

                        if mime.startswith('image/'):
                            result = api.send_image(
                                chat_wa_id, raw,
                                caption=caption, filename=att.name, reply_to=reply_to,
                            )
                        elif mime.startswith('video/'):
                            result = api.send_video(
                                chat_wa_id, raw,
                                caption=caption, reply_to=reply_to,
                            )
                        elif mime.startswith('audio/'):
                            result = api.send_voice(
                                chat_wa_id, raw,
                                convert=True, reply_to=reply_to,
                            )
                        else:
                            result = api.send_file(
                                chat_wa_id, raw, att.name, mime,
                                caption=caption, reply_to=reply_to,
                            )

                        if result and result.get('id'):
                            all_uids.append(result['id'])
                            _logger.info(
                                'Attachment %d/%d sent, uid=%s',
                                idx + 1, len(attachments), result['id'],
                            )
                        else:
                            _logger.warning(
                                'Attachment %d/%d returned no id for message %s',
                                idx + 1, len(attachments), message.id,
                            )

                if all_uids:
                    message.msg_uid = all_uids[0]
                    message.state = 'sent'
                    message.sent_date = fields.Datetime.now()
                    # Store all uids so the webhook dedup can silence the echoes
                    # for attachments 2..N without creating duplicate records.
                    if len(all_uids) > 1:
                        message.attachment_msg_uids = all_uids
                    _logger.info(
                        'Auto-sent message %s: %d uid(s) %s',
                        message.id, len(all_uids), all_uids,
                    )
                    if message.discuss_channel_id:
                        message.discuss_channel_id._touch_wa_activity()

            except Exception as e:
                error_msg = str(e)
                _logger.error('Failed to auto-send message %s: %s', message.id, error_msg)
                
                # Classify error
                if 'No LID for user' in error_msg or 'not found' in error_msg.lower():
                    failure_type = 'contact_not_found'
                elif 'Invalid session' in error_msg or 'not connected' in error_msg.lower():
                    failure_type = 'account'
                else:
                    failure_type = 'unknown'
                
                # Update state to error (but don't set msg_uid)
                message.state = 'error'
                message.failure_type = failure_type
                message.failure_reason = error_msg

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _resolve_wa_mentions_to_partner_ids(self, mentioned_ids):
        """Resolve a list of WhatsApp mention IDs to res.partner IDs.

        Each entry in `mentioned_ids` is a full WAHA id such as
        ``"11932090237110@lid"`` or ``"5491234567890@c.us"``.
        Lookup order mirrors _resolve_mentions() in the webhook controller:
        1. By LID (most reliable)
        2. By phone number

        Returns a plain list of res.partner IDs (no duplicates).
        """
        self.ensure_one()
        WahaPartner = self.env['waha.partner'].sudo()
        partner_ids = []
        seen = set()
        for raw_id in (mentioned_ids or []):
            if not raw_id:
                continue
            parts = raw_id.split('@')
            numeric = parts[0]
            suffix = parts[1] if len(parts) > 1 else ''
            wp = None
            # Try LID lookup for @lid entries AND for bare numeric IDs (no suffix).
            # WAHA sometimes omits the @lid suffix in mentionedIds.
            if suffix in ('lid', ''):
                wp = WahaPartner.search([
                    ('lid', '=', numeric),
                    ('wa_account_id', '=', self.wa_account_id.id),
                ], limit=1)
            if not wp:
                wp = WahaPartner.search([
                    ('phone_number', '=', numeric),
                    ('wa_account_id', '=', self.wa_account_id.id),
                ], limit=1)
            if wp and wp.partner_id and wp.partner_id.id not in seen:
                seen.add(wp.partner_id.id)
                partner_ids.append(wp.partner_id.id)
                _logger.info(
                    'Resolved WA mention %s → partner %s (%s)',
                    raw_id, wp.partner_id.id, wp.partner_id.name,
                )
            else:
                _logger.info('Could not resolve WA mention %s to a known partner', raw_id)
        return partner_ids

    def create_discuss_message(self, discuss_channel=None, author_partner=None):
        """
        Trigger creation of discuss message (now handled by computed field)
        
        This is now mostly a convenience method since mail_message_id
        is computed automatically. Just triggers recomputation.
        
        Args:
            discuss_channel: Optional, ignored. Always uses discuss_channel_id
            author_partner: Optional, for compatibility (not used)
            
        Returns:
            mail.message record (from mail_message_id)
        """
        self.ensure_one()
        
        # Validate channel if provided - must match the message's channel
        if discuss_channel and self.discuss_channel_id:
            if discuss_channel.id != self.discuss_channel_id.id:
                raise ValidationError(_(
                    'Cannot create message in channel "%s" (ID: %s). '
                    'Messages from chat "%s" must be in channel "%s" (ID: %s).'
                ) % (
                    discuss_channel.name,
                    discuss_channel.id,
                    self.discuss_channel_id.wa_chat_id,
                    self.discuss_channel_id.name,
                    self.discuss_channel_id.id
                ))
        
        # Force recomputation of mail_message_id (uses the message's channel)
        self._compute_mail_message_id()
        
        return self.mail_message_id

    # ============================================================
    # MEDIA ATTACHMENTS
    # ============================================================
    
    def process_payload_media(self):
        """
        Public method to process media from raw_payload
        
        Should be called after message creation when raw_payload contains media.
        Automatically detects content type and creates attachments.
        
        Returns:
            list: IDs of created attachments
        """
        self.ensure_one()
        
        if not self.raw_payload:
            _logger.warning('No raw_payload to process media from')
            return []
        
        # Auto-detect content type from payload
        detected_type = self._detect_content_type(self.raw_payload)
        
        # Skip if no media
        if detected_type == 'text':
            return []
        
        # Process media
        attachment_ids = self._process_media_from_payload(self.raw_payload, detected_type)
        
        # Notify the discuss channel about new attachments
        if attachment_ids and self.mail_message_id:
            self._notify_discuss_attachments()
        
        return attachment_ids
    
    def _process_media_from_payload(self, payload, content_type):
        """
        Download and attach media from WAHA payload
        
        Simplified approach: if hasMedia=True, download from URL
        Same procedure for all media types (image, video, audio, document)
        
        Args:
            payload: WAHA payload with media info
            content_type: Type of media (image, video, etc.)
            
        Returns:
            list: IDs of created attachments
        """
        self.ensure_one()
        
        if not self.mail_message_id:
            _logger.warning('No mail_message_id to attach media to (waha.message=%s)', self.id)
            return []
        
        media = payload.get('media', {})
        if not media:
            _logger.warning('No media in payload for %s', content_type)
            return []
        
        # Get media URL
        media_url = media.get('url')
        if not media_url:
            _logger.warning('No media URL in payload for %s', content_type)
            return []
        
        mimetype = media.get('mimetype') or self._get_default_mimetype(content_type)
        filename = media.get('filename') or self._get_default_filename(content_type, mimetype)
        
        # Download media from URL
        try:
            # Fix localhost URLs
            if 'localhost' in media_url or '127.0.0.1' in media_url:
                media_url = media_url.replace(
                    'http://localhost:3000',
                    self.wa_account_id.waha_url.rstrip('/')
                )
            
            # Download with authentication
            headers = {}
            if self.wa_account_id.api_key:
                headers['X-Api-Key'] = self.wa_account_id.api_key
            
            _logger.info('Downloading %s from URL: %s', content_type, media_url)
            timeout = 60 if content_type in ('video', 'document') else 30
            
            import requests
            response = requests.get(media_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            media_binary = response.content
            
            _logger.info('Downloaded %s: %d bytes, mimetype=%s', content_type, len(media_binary), mimetype)
            
        except Exception as e:
            _logger.error('Failed to download %s from URL: %s', content_type, str(e))
            return []
        
        # Create attachments
        if media_binary:
            try:
                import base64
                
                _logger.info('Creating attachment: name=%s, mimetype=%s, size=%d bytes', 
                            filename, mimetype, len(media_binary))
                
                # Create attachment linked to waha.message (for our records)
                attachment_waha = self.env['ir.attachment'].sudo().create({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(media_binary),
                    'mimetype': mimetype,
                    'res_model': 'waha.message',
                    'res_id': self.id,
                })
                
                _logger.info('Attachment created for waha.message: id=%s', attachment_waha.id)
                
                # Create a COPY for mail.message (for Discuss UI)
                if self.mail_message_id:
                    attachment_mail = self.env['ir.attachment'].sudo().create({
                        'name': filename,
                        'type': 'binary',
                        'datas': base64.b64encode(media_binary),
                        'mimetype': mimetype,
                        'res_model': 'mail.message',
                        'res_id': self.mail_message_id.id,
                    })
                    _logger.info('Attachment created for mail.message: id=%s', attachment_mail.id)
                    
                    # Link attachment to mail.message
                    self.mail_message_id.sudo().write({
                        'attachment_ids': [(4, attachment_mail.id)]
                    })
                    _logger.info('Attachment %s linked to mail.message.attachment_ids', attachment_mail.id)
                    
                    return [attachment_waha.id, attachment_mail.id]
                
                return [attachment_waha.id]
                
            except Exception as e:
                _logger.error('Failed to create attachment: %s', str(e), exc_info=True)
                return []
        
        return []
    
    def _get_default_mimetype(self, content_type):
        """Get default mimetype for content type"""
        defaults = {
            'image': 'image/jpeg',
            'video': 'video/mp4',
            'audio': 'audio/ogg',
            'document': 'application/pdf',
            'sticker': 'image/webp',
        }
        return defaults.get(content_type, 'application/octet-stream')
    
    def _detect_content_type(self, payload):
        """Detect content type from WAHA payload"""
        if payload.get('location'):
            return 'location'
        
        if payload.get('hasMedia'):
            # Try to get type from payload.type or _data.type
            msg_type = payload.get('type')
            if not msg_type:
                _data = payload.get('_data', {})
                msg_type = _data.get('type', 'text')
            
            type_mapping = {
                'image': 'image',
                'video': 'video',
                'audio': 'audio',
                'document': 'document',
                'sticker': 'sticker',
                'ptt': 'audio',  # Push-to-talk voice message
            }
            
            return type_mapping.get(msg_type, 'document')
        
        return 'text'
    
    def _get_default_filename(self, content_type, mimetype=None):
        """Get default filename for content type based on mimetype"""
        # Try to infer extension from mimetype
        if mimetype:
            ext_mapping = {
                'image/jpeg': '.jpg',
                'image/jpg': '.jpg',
                'image/png': '.png',
                'image/gif': '.gif',
                'image/webp': '.webp',
                'video/mp4': '.mp4',
                'video/webm': '.webm',
                'audio/ogg': '.ogg',
                'audio/mpeg': '.mp3',
                'audio/mp3': '.mp3',
                'application/pdf': '.pdf',
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
            }
            ext = ext_mapping.get(mimetype)
            if ext:
                return f'{content_type}{ext}'
        
        # Fallback to defaults
        defaults = {
            'image': 'image.jpg',
            'video': 'video.mp4',
            'audio': 'audio.ogg',
            'document': 'document.pdf',
            'sticker': 'sticker.webp',
        }
        return defaults.get(content_type, 'file.bin')
    
    def _notify_discuss_attachments(self):
        """
        Notify Discuss channel about new attachments
        
        This triggers a real-time update in the Odoo Discuss UI
        so users don't need to refresh the page to see new attachments.
        """
        self.ensure_one()
        
        if not self.mail_message_id or not self.discuss_channel_id:
            return
        
        try:
            # Get the discuss channel
            channel = self.discuss_channel_id
            
            # Notify channel members about the message update
            # This will trigger the frontend to refresh the message and show attachments
            channel._notify_thread(self.mail_message_id)
            
            _logger.info('Notified Discuss channel %s about new attachments for message %s', 
                        channel.id, self.mail_message_id.id)
        except Exception as e:
            _logger.warning('Failed to notify Discuss about attachments: %s', str(e))

    # ============================================================
    # SEND MESSAGE (OUTBOUND)
    # ============================================================
    
    @api.model
    def send_message(self, channel, partner, body, reply_to=None, attachments=None, mail_message_id=None):
        """
        Send a new outbound WhatsApp message
        
        Args:
            channel: discuss.channel record (WhatsApp channel)
            partner: res.partner (recipient)
            body: Message text
            reply_to: waha.message to reply to (optional)
            attachments: ir.attachment records (optional)
            mail_message_id: mail.message ID to link (optional, prevents auto-creation)
            
        Returns:
            waha.message record
        """
        # Find phone number from partner
        waha_partner = self.env['waha.partner'].search([
            ('partner_id', '=', partner.id),
            ('wa_account_id', '=', channel.whatsapp_account_id.id)
        ], limit=1)
        
        sender_phone = waha_partner.phone_number if waha_partner else partner.mobile or partner.phone
        if sender_phone:
            sender_phone = sender_phone.replace('+', '').replace(' ', '').replace('-', '')
        
        # Create waha.message record
        vals = {
            'wa_account_id': channel.whatsapp_account_id.id,
            'discuss_channel_id': channel.id,
            'message_type': 'outbound',
            'content_type': 'document' if attachments else 'text',
            'state': 'outgoing',
            'body': body,
            'raw_chat_id': channel.wa_chat_id,
            'raw_sender_phone': sender_phone,
        }
        
        # Link to existing mail.message if provided (prevents auto-creation)
        if mail_message_id:
            vals['mail_message_id'] = mail_message_id
        
        if reply_to:
            vals['reply_to_message_id'] = reply_to.id
            vals['reply_to_msg_uid'] = reply_to.msg_uid
        
        message = self.create(vals)
        _logger.info('Created outbound message: %s', message.id)
        
        # Link attachments
        if attachments:
            attachments.write({
                'res_model': 'waha.message',
                'res_id': message.id,
            })
        
        return message
    
    def _send_through_waha(self):
        """
        Send this message through WAHA API (manual/retry)
        
        Note: This is now mainly for manual retry actions.
        Normal sending happens automatically via _compute_msg_uid.
        
        Returns:
            str: msg_uid from WAHA response
        """
        self.ensure_one()
        
        if self.wa_account_id.status != 'connected':
            raise UserError(_('WhatsApp account is not connected'))
        
        _logger.info('Manually sending message %s through WAHA', self.id)
        
        try:
            api = WahaApi(self.wa_account_id)

            chat_wa_id = self.discuss_channel_id.wa_chat_id if self.discuss_channel_id else False
            if not chat_wa_id:
                _logger.warning('Message %s has no discuss channel', self.id)
                return ''
            body_clean = _html_to_whatsapp(self.body)

            attachments = self.attachment_ids.sorted(key=lambda a: a.id)
            first_uid = None

            if not attachments:
                result = api.send_text(chat_wa_id, body_clean, self.reply_to_msg_uid)
                if result and result.get('id'):
                    first_uid = result['id']
            else:
                for idx, att in enumerate(attachments):
                    caption = body_clean if idx == 0 else None
                    reply_to = self.reply_to_msg_uid if idx == 0 else None
                    mime = att.mimetype or ''
                    raw = att.datas
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8')

                    if mime.startswith('image/'):
                        result = api.send_image(chat_wa_id, raw, caption=caption, filename=att.name, reply_to=reply_to)
                    elif mime.startswith('video/'):
                        result = api.send_video(chat_wa_id, raw, caption=caption, reply_to=reply_to)
                    elif mime.startswith('audio/'):
                        result = api.send_voice(chat_wa_id, raw, convert=True, reply_to=reply_to)
                    else:
                        result = api.send_file(chat_wa_id, raw, att.name, mime, caption=caption, reply_to=reply_to)

                    if result and result.get('id') and first_uid is None:
                        first_uid = result['id']

            msg_uid = first_uid or ''
            self.write({
                'state': 'sent',
                'msg_uid': msg_uid,
                'sent_date': fields.Datetime.now(),
            })
            
            _logger.info('Message sent successfully: %s', msg_uid)
            
            # Update channel activity
            if self.discuss_channel_id:
                self.discuss_channel_id._touch_wa_activity()
            
            return msg_uid
            
        except Exception as e:
            error_msg = str(e)
            _logger.error('Failed to send message: %s', error_msg)
            
            # Classify error
            if 'No LID for user' in error_msg or 'not found' in error_msg.lower():
                failure_type = 'contact_not_found'
            elif 'Invalid session' in error_msg or 'not connected' in error_msg.lower():
                failure_type = 'account'
            else:
                failure_type = 'unknown'
            
            self.write({
                'state': 'error',
                'failure_type': failure_type,
                'failure_reason': error_msg,
            })
            
            raise

    # ============================================================
    # STATUS UPDATES
    # ============================================================
    
    def update_status_from_webhook(self, status_data):
        """
        Update message status from WAHA status webhook
        
        Args:
            status_data: Status webhook payload with 'ack' field
        """
        self.ensure_one()
        
        ack = status_data.get('ack', 0)
        
        # Map WAHA ACK to state
        state_mapping = {
            0: 'error',
            1: 'outgoing',
            2: 'sent',
            3: 'delivered',
            4: 'read',
            5: 'read',
        }
        
        new_state = state_mapping.get(ack, self.state)
        
        if new_state != self.state:
            vals = {'state': new_state}
            
            if new_state == 'sent' and not self.sent_date:
                vals['sent_date'] = fields.Datetime.now()
            elif new_state == 'delivered' and not self.delivered_date:
                vals['delivered_date'] = fields.Datetime.now()
            elif new_state == 'read' and not self.read_date:
                vals['read_date'] = fields.Datetime.now()
            
            self.write(vals)
            _logger.info('Updated message %s status: %s → %s', self.id, self.state, new_state)

    # ============================================================
    # ACTIONS
    # ============================================================
    
    def action_retry_send(self):
        """Retry sending failed messages"""
        for message in self:
            if message.state != 'error' or message.message_type != 'outbound':
                continue
            
            _logger.info('Retrying send for message %s', message.id)
            
            # Clear previous error state (but keep mail_message_id to prevent duplicates)
            message.write({
                'state': 'outgoing',
                'failure_type': False,
                'failure_reason': False,
                'msg_uid': False,  # Clear to allow resend
            })
            
            # Send directly (don't use compute to avoid side effects)
            try:
                message._send_through_waha()
                _logger.info('Message %s resent successfully', message.id)
            except Exception as e:
                _logger.error('Retry failed for message %s: %s', message.id, str(e))
    
    def action_view_discuss_message(self):
        """Open linked discuss message"""
        self.ensure_one()
        
        if not self.mail_message_id:
            raise UserError(_('No linked discuss message'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.message',
            'res_id': self.mail_message_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_chat(self):
        """Open the WhatsApp discuss channel"""
        self.ensure_one()
        
        if not self.discuss_channel_id:
            raise UserError(_('No linked channel'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'discuss.channel',
            'res_id': self.discuss_channel_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
