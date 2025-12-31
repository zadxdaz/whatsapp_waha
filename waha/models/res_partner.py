# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # WhatsApp fields
    wa_account_id = fields.Many2one(
        'waha.account',
        string='WhatsApp Account',
        help='Default WhatsApp account for this contact'
    )
    
    wa_chat_id = fields.Char(
        string='WhatsApp Chat ID',
        help='Chat ID in WAHA format (e.g., 11932090237110@lid, 11932090237110@c.us, 123456@g.us). '
             'Automatically populated from the first received message.'
    )
    
    wa_group_ids = fields.Many2many(
        'waha.group',
        'waha_group_member_rel',
        'partner_id',
        'group_id',
        string='WhatsApp Groups',
        help='WhatsApp groups this partner belongs to'
    )
    
    # Statistics
    waha_message_ids = fields.One2many(
        'waha.message',
        'mobile_number',
        string='WhatsApp Messages',
        compute='_compute_waha_message_ids',
        store=False
    )
    waha_messages_count = fields.Integer(
        'WhatsApp Messages',
        compute='_compute_waha_messages_count'
    )

    def write(self, vals):
        """Override write to update WhatsApp channels when name changes"""
        result = super().write(vals)
        
        # If name changed, update associated channels
        if 'name' in vals:
            self._update_whatsapp_channels()
        
        return result

    @api.depends('mobile', 'phone')
    def _compute_waha_message_ids(self):
        """Compute related WhatsApp messages"""
        for partner in self:
            numbers = []
            if partner.mobile:
                numbers.append(partner.mobile)
            if partner.phone:
                numbers.append(partner.phone)
            
            if numbers:
                messages = self.env['waha.message'].search([
                    ('mobile_number', 'in', numbers)
                ])
                partner.waha_message_ids = messages
            else:
                partner.waha_message_ids = []

    def _update_whatsapp_channels(self):
        """Update discuss.channel names based on partner changes"""
        for partner in self:
            try:
                # Update individual chat channels
                numbers = []
                if partner.mobile:
                    numbers.append(partner.mobile.replace('+', ''))
                if partner.phone:
                    numbers.append(partner.phone.replace('+', ''))
                
                if numbers:
                    # Search channels for individual chats (not part of a group channel)
                    channels = self.env['discuss.channel'].search([
                        ('description', 'in', numbers),
                        ('channel_type', '=', 'channel'),
                        ('name', 'like', 'WhatsApp:'),
                        ('name', 'not like', 'WhatsApp Group:')
                    ])
                    
                    new_name = f'WhatsApp: {partner.name}'
                    for channel in channels:
                        if channel.name != new_name:
                            channel.write({'name': new_name})
            except Exception as e:
                import logging
                _logger = logging.getLogger(__name__)
                _logger.exception('Error updating WhatsApp channels for partner %s: %s', partner.id, str(e))

    @api.depends('waha_message_ids')
    def _compute_waha_messages_count(self):
        """Count WhatsApp messages"""
        for partner in self:
            numbers = []
            if partner.mobile:
                numbers.append(partner.mobile)
            if partner.phone:
                numbers.append(partner.phone)
            
            if numbers:
                partner.waha_messages_count = self.env['waha.message'].search_count([
                    ('mobile_number', 'in', numbers)
                ])
            else:
                partner.waha_messages_count = 0

    def action_send_whatsapp_message(self):
        """Open WhatsApp composer"""
        self.ensure_one()
        
        if not self.mobile and not self.phone:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Phone Number'),
                    'message': _('This contact does not have a phone number.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        return {
            'name': _('Send WhatsApp Message'),
            'type': 'ir.actions.act_window',
            'res_model': 'waha.composer',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': 'res.partner',
                'default_res_id': self.id,
                'default_mobile_number': self.mobile or self.phone,
                'default_wa_account_id': self.wa_account_id.id if self.wa_account_id else False,
            }
        }

    def action_view_whatsapp_messages(self):
        """View WhatsApp messages for this partner"""
        self.ensure_one()
        
        numbers = []
        if self.mobile:
            numbers.append(self.mobile)
        if self.phone:
            numbers.append(self.phone)
        
        return {
            'name': _('WhatsApp Messages'),
            'type': 'ir.actions.act_window',
            'res_model': 'waha.message',
            'view_mode': 'list,form',
            'domain': [('mobile_number', 'in', numbers)],
            'context': {'default_mobile_number': self.mobile or self.phone}
        }

    def action_get_whatsapp_info(self):
        """Get and enrich WhatsApp contact info from WAHA API (for debugging)"""
        self.ensure_one()
        
        import logging
        _logger = logging.getLogger(__name__)
        
        phone = self.mobile or self.phone
        if not phone:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('This contact does not have a phone number.'),
                    'type': 'danger',
                    'sticky': True,
                }
            }
        
        try:
            # Use partner's account or first available
            account = self.wa_account_id
            if not account:
                account = self.env['waha.account'].search([('status', '=', 'connected')], limit=1)
            
            if not account:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('No connected WhatsApp account found.'),
                        'type': 'danger',
                        'sticky': True,
                    }
                }
            
            # Enrich contact from WAHA API (this retrieves and updates the contact)
            self.enrich_contact_from_waha(account)
            
            # Get the updated contact info for display
            from odoo.addons.waha.tools.waha_api import WahaApi
            api = WahaApi(account)
            phone_clean = phone.replace('+', '').replace(' ', '')
            contact_info = api.get_contact(phone_clean)
            
            if not contact_info:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Data'),
                        'message': _('No contact information found in WhatsApp for this number.'),
                        'type': 'warning',
                        'sticky': True,
                    }
                }
            
            # Build readable info string
            info_parts = []
            info_parts.append(f"📱 Phone: {phone}")
            
            if contact_info.get('id'):
                info_parts.append(f"ID: {contact_info.get('id')}")
            
            if contact_info.get('name'):
                info_parts.append(f"Name: {contact_info.get('name')}")
            
            if contact_info.get('pushName'):
                info_parts.append(f"Push Name: {contact_info.get('pushName')}")
            
            if contact_info.get('verifiedLevel'):
                info_parts.append(f"Verified Level: {contact_info.get('verifiedLevel')}")
            
            if contact_info.get('verifiedName'):
                info_parts.append(f"Verified Name: {contact_info.get('verifiedName')}")
            
            if contact_info.get('isBusiness'):
                info_parts.append(f"Is Business: {contact_info.get('isBusiness')}")
            
            if contact_info.get('image'):
                info_parts.append(f"Image: {contact_info.get('image')[:50]}...")
            
            # Format full message
            message = "✅ WhatsApp Contact Information:\n\n"
            message += "\n".join(info_parts)
            message += f"\n\n📥 Contact has been enriched from WhatsApp"
            message += f"\n(From Account: {account.name})"
            
            _logger.info('WhatsApp info retrieved and contact enriched for %s: %s', phone, contact_info)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WhatsApp Contact Info'),
                    'message': message,
                    'type': 'success',
                    'sticky': True,
                }
            }
        
        except Exception as e:
            _logger.exception('Error fetching WhatsApp info for %s: %s', phone, str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error fetching WhatsApp info: %s') % str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def enrich_contact_from_waha(self, account):
        """
        Enrich partner data from WAHA API (best-effort, non-blocking)
        
        Responsibilities:
        - Call WAHA API get_contact endpoint
        - Update partner fields if data available (name, email, etc.)
        - Handle errors gracefully (log but don't fail)
        
        Args:
            account: waha.account record
        """
        self.ensure_one()
        
        import logging
        _logger = logging.getLogger(__name__)
        
        try:
            from odoo.addons.waha.tools.waha_api import WahaApi
            
            # Extract phone number
            phone = self.mobile or self.phone
            if not phone:
                _logger.warning('Partner %s has no phone number for WAHA enrichment', self.id)
                return
            
            phone = phone.replace('+', '').replace(' ', '')
            
            # Call WAHA API
            api = WahaApi(account)
            contact_info = api.get_contact(phone)
            
            if not contact_info:
                _logger.debug('No contact info found from WAHA for %s', phone)
                return
            
            # Extract update fields
            update_vals = {}
            
            # Get contact name (try different fields)
            contact_name = (
                contact_info.get('name') or 
                contact_info.get('pushname') or 
                contact_info.get('pushName') or
                contact_info.get('verifiedName')
            )
            if contact_name and contact_name != self.name:
                update_vals['name'] = contact_name
            
            # Get email if available
            contact_email = contact_info.get('email')
            if contact_email and not self.email:
                update_vals['email'] = contact_email
            
            # Apply updates
            if update_vals:
                self.write(update_vals)
                _logger.info('Enriched partner %s (mobile: %s) with WAHA data: %s', 
                           self.id, self.mobile, update_vals)
            else:
                _logger.debug('No new data to enrich for partner %s (mobile: %s)', 
                            self.id, self.mobile)
            
        except Exception as e:
            # Log but don't fail - enrichment is best-effort
            _logger.warning('Could not enrich partner %s from WAHA: %s', self.id, str(e))
