# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class WahaChat(models.Model):
    """
    WAHA Chat - Manages WhatsApp conversations and Discuss channels
    
    Responsibilities:
    - Create and update discuss.channel records
    - Manage channel members (add/remove participants)
    - Sync group information from WAHA (name, avatar, participants)
    - Handle both 1-1 chats and group chats
    - Maintain bidirectional linking between WAHA chat_id and discuss.channel
    """
    _name = 'waha.chat'
    _description = 'WhatsApp Chat/Conversation'
    _order = 'last_message_time desc, id desc'

    # ============================================================
    # FIELDS
    # ============================================================
    
    name = fields.Char(
        string="Chat Name",
        required=True,
        help="Display name of the chat (contact name or group name)"
    )
    
    wa_chat_id = fields.Char(
        string="WhatsApp Chat ID",
        required=True,
        index=True,
        help="WAHA chat identifier (e.g., 123456@c.us for 1-1, 123456@g.us for groups)"
    )
    
    chat_type = fields.Selection([
        ('individual', 'Individual Chat'),
        ('group', 'Group Chat'),
    ], string="Chat Type", required=True, compute='_compute_chat_type', store=True)
    
    wa_account_id = fields.Many2one(
        'waha.account',
        string="WhatsApp Account",
        required=True,
        ondelete='cascade',
        index=True
    )
    
    discuss_channel_id = fields.Many2one(
        'discuss.channel',
        string="Discuss Channel",
        compute='_compute_discuss_channel_id',
        store=True,
        readonly=False,
        ondelete='set null',
        help="Linked Discuss channel for this conversation"
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string="Contact",
        compute='_compute_partner_id',
        store=True,
        readonly=False,
        help="Contact for 1-1 chats (null for groups)"
    )
    
    # Group-specific fields
    group_participants = fields.Many2many(
        'res.partner',
        'waha_chat_participant_rel',
        'chat_id',
        'partner_id',
        string="Group Participants",
        help="Members of the group chat"
    )
    
    group_description = fields.Text(string="Group Description")
    group_avatar_url = fields.Char(string="Group Avatar URL")
    
    # Metadata
    last_message_time = fields.Datetime(string="Last Message Time")
    message_count = fields.Integer(string="Message Count", default=0)
    unread_count = fields.Integer(string="Unread Messages", default=0)
    
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('unique_chat_per_account', 
         'unique(wa_chat_id, wa_account_id)',
         "Each chat ID must be unique per WhatsApp account.")
    ]

    # ============================================================
    # COMPUTED FIELDS
    # ============================================================
    
    @api.depends('wa_chat_id')
    def _compute_chat_type(self):
        """Determine if chat is individual or group based on chat_id"""
        for chat in self:
            if chat.wa_chat_id:
                chat.chat_type = 'group' if '@g.us' in chat.wa_chat_id else 'individual'
            else:
                chat.chat_type = 'individual'
    
    @api.depends('wa_chat_id', 'wa_account_id', 'name', 'partner_id')
    def _compute_discuss_channel_id(self):
        """
        Auto-compute discuss channel relationship
        
        Searches for existing channel or creates one if missing
        """
        for chat in self:
            if not chat.wa_chat_id or not chat.wa_account_id:
                chat.discuss_channel_id = False
                continue
            
            # Search for existing channel
            channel = self.env['discuss.channel'].sudo().search([
                ('wa_chat_id', '=', chat.wa_chat_id),
                ('is_whatsapp', '=', True),
                ('whatsapp_account_id', '=', chat.wa_account_id.id),
            ], limit=1)
            
            if channel:
                chat.discuss_channel_id = channel
            else:
                # Auto-create channel if missing
                _logger.info('Auto-creating discuss.channel for chat: %s', chat.wa_chat_id)
                
                # Use partner name for individual chats, chat name for groups
                if chat.chat_type == 'individual' and chat.partner_id:
                    channel_name = chat.partner_id.name
                else:
                    channel_name = chat.name or chat.wa_chat_id
                
                channel_vals = {
                    'name': channel_name,
                    'channel_type': 'whatsapp',
                    'description': chat.wa_chat_id,
                    'is_whatsapp': True,
                    'whatsapp_account_id': chat.wa_account_id.id,
                    'wa_chat_id': chat.wa_chat_id,
                }
                
                channel = self.env['discuss.channel'].sudo().create(channel_vals)
                chat.discuss_channel_id = channel
                
                # Add initial members
                chat._sync_channel_members()
    
    @api.depends('wa_chat_id', 'chat_type')
    def _compute_partner_id(self):
        """
        Auto-compute partner for 1-1 chats
        
        For individual chats, tries to find partner from wa_chat_id
        For groups, partner is always False
        """
        for chat in self:
            if chat.chat_type == 'group':
                chat.partner_id = False
                continue
            
            if not chat.wa_chat_id:
                chat.partner_id = False
                continue
            
            # Extract phone from chat_id
            phone = chat.wa_chat_id.split('@')[0]
            
            # Search for partner
            partner = self.env['res.partner'].sudo().search([
                '|',
                ('mobile', 'ilike', phone),
                ('phone', 'ilike', phone)
            ], limit=1)
            
            chat.partner_id = partner if partner else False

    # ============================================================
    # CRUD & LIFECYCLE
    # ============================================================
    
    @api.model
    def find_or_create(self, wa_account, chat_id, partner=None):
        """
        Find existing chat or create new one
        
        Args:
            wa_account: waha.account record
            chat_id: WhatsApp chat ID (e.g., "123456@c.us")
            partner: res.partner record (optional, for 1-1 chats)
            
        Returns:
            waha.chat record
        """
        # Search for existing chat
        chat = self.search([
            ('wa_chat_id', '=', chat_id),
            ('wa_account_id', '=', wa_account.id),
        ], limit=1)
        
        if chat:
            _logger.info('Found existing waha.chat %s for chat_id %s', chat.id, chat_id)
            return chat
        
        # Create new chat
        is_group = '@g.us' in chat_id
        
        if is_group:
            # For groups, get info from WAHA
            chat_name = self._get_group_name_from_waha(wa_account, chat_id)
        else:
            # For 1-1 chats, use partner name
            chat_name = partner.name if partner else chat_id
        
        vals = {
            'name': chat_name,
            'wa_chat_id': chat_id,
            'wa_account_id': wa_account.id,
            'chat_type': 'group' if is_group else 'individual',
        }
        
        # Note: partner_id and discuss_channel_id will be computed automatically
        
        chat = self.create(vals)
        _logger.info('Created new waha.chat %s for chat_id %s (type=%s, channel auto-created)', 
                     chat.id, chat_id, vals['chat_type'])
        
        return chat
    
    def _get_group_name_from_waha(self, wa_account, chat_id):
        """Get group name from WAHA API"""
        try:
            from odoo.addons.waha.tools.waha_api import WahaApi
            api = WahaApi(wa_account)
            group_info = api.get_group_info(chat_id)
            
            if group_info:
                return group_info.get('name', chat_id)
        except Exception as e:
            _logger.warning('Could not get group name from WAHA: %s', str(e))
        
        return chat_id

    # ============================================================
    # DISCUSS CHANNEL MANAGEMENT
    # ============================================================
    
    def get_or_create_discuss_channel(self):
        """
        Get existing discuss channel (auto-created by computed field)
        
        The discuss_channel_id is now auto-computed, so this method
        just ensures it exists and returns it.
        """
        self.ensure_one()
        
        # Trigger recompute if needed
        if not self.discuss_channel_id:
            self._compute_discuss_channel_id()
        
        return self.discuss_channel_id
    
    def _sync_channel_members(self):
        """Sync channel members with discuss.channel"""
        self.ensure_one()
        
        if not self.discuss_channel_id:
            _logger.warning('No discuss channel to sync members for chat %s', self.id)
            return
        
        channel = self.discuss_channel_id
        admin = self.env.ref('base.user_admin').sudo()
        
        if self.chat_type == 'individual':
            # For 1-1 chats: add partner + admin
            if self.partner_id:
                members_to_add = [self.partner_id.id, admin.partner_id.id]
            else:
                members_to_add = [admin.partner_id.id]
        else:
            # For groups: add all participants + admin
            members_to_add = [admin.partner_id.id] + self.group_participants.ids
        
        # Get current members
        current_members = channel.channel_partner_ids.ids
        
        # Add missing members
        new_members = [m for m in members_to_add if m not in current_members]
        if new_members:
            channel.write({
                'channel_partner_ids': [(4, mid) for mid in new_members]
            })
            _logger.info('Added %d members to channel %s', len(new_members), channel.id)
    
    def add_participant(self, partner):
        """Add participant to group chat"""
        self.ensure_one()
        
        if self.chat_type != 'group':
            raise UserError(_('Can only add participants to group chats'))
        
        if partner not in self.group_participants:
            self.write({
                'group_participants': [(4, partner.id)]
            })
            _logger.info('Added partner %s to group chat %s', partner.id, self.id)
            
            # Sync to discuss channel
            if self.discuss_channel_id:
                self.discuss_channel_id.write({
                    'channel_partner_ids': [(4, partner.id)]
                })
    
    def remove_participant(self, partner):
        """Remove participant from group chat"""
        self.ensure_one()
        
        if self.chat_type != 'group':
            raise UserError(_('Can only remove participants from group chats'))
        
        if partner in self.group_participants:
            self.write({
                'group_participants': [(3, partner.id)]
            })
            _logger.info('Removed partner %s from group chat %s', partner.id, self.id)
            
            # Sync to discuss channel
            if self.discuss_channel_id:
                self.discuss_channel_id.write({
                    'channel_partner_ids': [(3, partner.id)]
                })

    # ============================================================
    # GROUP SYNC FROM WAHA
    # ============================================================
    
    def sync_group_info_from_waha(self):
        """Sync group information from WAHA (name, description, avatar, participants)"""
        self.ensure_one()
        
        if self.chat_type != 'group':
            _logger.warning('Cannot sync group info for non-group chat %s', self.id)
            return
        
        try:
            from odoo.addons.waha.tools.waha_api import WahaApi
            api = WahaApi(self.wa_account_id)
            
            # Get group info
            group_info = api.get_group_info(self.wa_chat_id)
            
            if not group_info:
                _logger.warning('No group info returned from WAHA for %s', self.wa_chat_id)
                return
            
            # Update basic info
            vals = {}
            
            if group_info.get('name'):
                vals['name'] = group_info['name']
            
            if group_info.get('description'):
                vals['group_description'] = group_info['description']
            
            # Update participants
            participants_data = group_info.get('participants', [])
            if participants_data:
                self._sync_group_participants(participants_data)
            
            if vals:
                self.write(vals)
                _logger.info('Synced group info for chat %s', self.id)
            
            # Update discuss channel name if changed
            if self.discuss_channel_id and vals.get('name'):
                self.discuss_channel_id.write({'name': vals['name']})
        
        except Exception as e:
            _logger.error('Failed to sync group info for chat %s: %s', self.id, str(e))
    
    def _sync_group_participants(self, participants_data):
        """
        Sync group participants from WAHA data
        
        Args:
            participants_data: List of participant dicts from WAHA
        """
        WahaPartner = self.env['waha.partner']
        
        participant_partners = []
        
        for participant in participants_data:
            # Extract phone number from participant ID
            participant_id = participant.get('id', {})
            if isinstance(participant_id, dict):
                phone = participant_id.get('user', '').split('@')[0]
            else:
                phone = str(participant_id).split('@')[0]
            
            if not phone:
                continue
            
            # Find or create partner
            partner = WahaPartner.find_or_create_by_phone(
                phone=phone,
                wa_account=self.wa_account_id
            )
            
            if partner:
                participant_partners.append(partner.id)
        
        # Update group participants
        if participant_partners:
            self.write({
                'group_participants': [(6, 0, participant_partners)]
            })
            _logger.info('Updated %d participants for group %s', 
                        len(participant_partners), self.id)
            
            # Sync to discuss channel
            self._sync_channel_members()

    # ============================================================
    # MESSAGE TRACKING
    # ============================================================
    
    def update_last_message(self, message_time=None):
        """Update last message timestamp and increment counter"""
        self.ensure_one()
        
        vals = {
            'message_count': self.message_count + 1,
        }
        
        if message_time:
            vals['last_message_time'] = message_time
        else:
            vals['last_message_time'] = fields.Datetime.now()
        
        self.write(vals)
    
    def increment_unread(self):
        """Increment unread message counter"""
        self.ensure_one()
        self.write({'unread_count': self.unread_count + 1})
    
    def mark_as_read(self):
        """Reset unread counter"""
        self.ensure_one()
        self.write({'unread_count': 0})
    
    def action_update_channel_name(self):
        """Update discuss channel name and type based on chat type and partner"""
        self.ensure_one()
        
        if not self.discuss_channel_id:
            raise UserError(_('No Discuss channel linked to this chat'))
        
        # Use partner name for individual chats, chat name for groups
        if self.chat_type == 'individual' and self.partner_id:
            new_name = self.partner_id.name
        else:
            new_name = self.name or self.wa_chat_id
        
        # Update both name and channel_type to ensure it's in WhatsApp section
        self.discuss_channel_id.write({
            'name': new_name,
            'channel_type': 'whatsapp',
        })
        _logger.info('Updated channel name to: %s and type to: whatsapp', new_name)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Channel Updated'),
                'message': _('Channel moved to WhatsApp section with name: %s') % new_name,
                'type': 'success',
                'sticky': False,
            }
        }
