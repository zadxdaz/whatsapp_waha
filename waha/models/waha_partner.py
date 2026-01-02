# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from odoo.addons.phone_validation.tools import phone_validation

_logger = logging.getLogger(__name__)


class WahaPartner(models.Model):
    """
    WAHA Partner - Manages WhatsApp contact information
    
    Responsibilities:
    - Find or create res.partner records for WhatsApp contacts
    - Enrich partner data from WAHA (name, avatar, status, business info)
    - Validate and normalize phone numbers
    - Track WhatsApp-specific contact metadata
    - Maintain bidirectional linking between phone numbers and partners
    """
    _name = 'waha.partner'
    _description = 'WhatsApp Contact Information'
    _rec_name = 'display_name'

    # ============================================================
    # FIELDS
    # ============================================================
    
    partner_id = fields.Many2one(
        'res.partner',
        string="Contact",
        required=True,
        ondelete='cascade',
        index=True
    )
    
    display_name = fields.Char(related='partner_id.name', string="Name", readonly=True)
    
    wa_account_id = fields.Many2one(
        'waha.account',
        string="WhatsApp Account",
        required=True,
        ondelete='cascade',
        index=True
    )
    
    phone_number = fields.Char(
        string="Phone Number",
        required=True,
        index=True,
        help="Normalized phone number (E.164 format)"
    )
    
    wa_contact_id = fields.Char(
        string="WhatsApp Contact ID",
        help="WAHA contact identifier (e.g., 123456@c.us or 123456@lid)"
    )
    
    # WhatsApp-specific fields
    wa_name = fields.Char(
        string="WhatsApp Name",
        help="Name as it appears in WhatsApp"
    )
    
    wa_pushname = fields.Char(
        string="Push Name",
        help="Name set by the user in their WhatsApp profile"
    )
    
    wa_status = fields.Text(
        string="WhatsApp Status",
        help="Contact's WhatsApp status message"
    )
    
    is_business = fields.Boolean(
        string="Is Business Account",
        default=False
    )
    
    business_description = fields.Text(string="Business Description")
    business_category = fields.Char(string="Business Category")
    business_website = fields.Char(string="Business Website")
    
    # Metadata
    last_seen = fields.Datetime(string="Last Seen")
    is_blocked = fields.Boolean(string="Is Blocked", default=False)
    is_contact_synced = fields.Boolean(
        string="Contact Synced from WhatsApp",
        default=False,
        help="Indicates if contact info has been retrieved from WAHA"
    )
    last_sync_date = fields.Datetime(string="Last Sync Date")
    
    active = fields.Boolean(default=True)
    
    _sql_constraints = [
        ('unique_partner_per_account',
         'unique(partner_id, wa_account_id)',
         "Each partner can only have one WhatsApp contact per account.")
    ]

    # ============================================================
    # CRUD & LIFECYCLE
    # ============================================================
    
    @api.model
    def find_or_create_by_phone(self, phone, wa_account, auto_enrich=True):
        """
        Find existing partner or create new one from phone number
        
        Args:
            phone: Phone number (any format)
            wa_account: waha.account record
            auto_enrich: Whether to automatically enrich from WAHA
            
        Returns:
            res.partner record
        """
        # Normalize phone number
        normalized_phone = self._normalize_phone(phone, wa_account)
        
        if not normalized_phone:
            _logger.warning('Could not normalize phone: %s', phone)
            return self.env['res.partner']
        
        # Search for existing waha.partner
        waha_partner = self.search([
            ('phone_number', '=', normalized_phone),
            ('wa_account_id', '=', wa_account.id),
        ], limit=1)
        
        if waha_partner:
            _logger.info('Found existing waha.partner %s for phone %s', 
                        waha_partner.id, normalized_phone)
            return waha_partner.partner_id
        
        # Search for existing res.partner by phone
        partner = self.env['res.partner'].sudo().search([
            '|',
            ('mobile', 'ilike', normalized_phone),
            ('phone', 'ilike', normalized_phone),
        ], limit=1)
        
        if not partner:
            # Create new partner
            contact_name = normalized_phone  # Default name
            contact_image = None
            
            # Try to get contact info from WAHA before creating
            if auto_enrich:
                try:
                    from odoo.addons.waha.tools.waha_api import WahaApi
                    api = WahaApi(wa_account)
                    contact_info = api.get_contact(normalized_phone)
                    
                    if contact_info:
                        contact_name = self._extract_contact_name(contact_info)
                        contact_image = self._download_contact_avatar(
                            wa_account, contact_info
                        )
                except Exception as e:
                    _logger.warning('Could not enrich contact from WAHA: %s', str(e))
            
            # Create partner
            partner_vals = {
                'name': contact_name,
                'mobile': f"+{normalized_phone}",
                'phone': f"+{normalized_phone}",
            }
            
            if contact_image:
                partner_vals['image_1920'] = contact_image
            
            partner = self.env['res.partner'].sudo().create(partner_vals)
            _logger.info('Created new partner %s for phone %s', partner.id, normalized_phone)
        
        # Create waha.partner link
        wa_contact_id = f"{normalized_phone}@c.us"
        
        waha_partner_vals = {
            'partner_id': partner.id,
            'wa_account_id': wa_account.id,
            'phone_number': normalized_phone,
            'wa_contact_id': wa_contact_id,
        }
        
        waha_partner = self.create(waha_partner_vals)
        _logger.info('Created waha.partner link %s', waha_partner.id)
        
        # Enrich if requested
        if auto_enrich:
            waha_partner.enrich_from_waha()
        
        return partner
    
    def _normalize_phone(self, phone, wa_account):
        """
        Normalize phone number to E.164 format (without +)
        
        Args:
            phone: Phone number in any format
            wa_account: waha.account record (for country context)
            
        Returns:
            Normalized phone number string or False
        """
        if not phone:
            return False
        
        # Remove common prefixes/suffixes from WhatsApp IDs
        phone = str(phone).replace('@c.us', '').replace('@lid', '').replace('@g.us', '')
        phone = phone.replace('+', '').replace(' ', '').replace('-', '')
        
        # If already normalized (digits only), return as-is
        if phone.isdigit():
            return phone
        
        # Try phone validation
        try:
            country = wa_account.company_id.country_id if wa_account.company_id else False
            
            result = phone_validation.phone_format(
                phone,
                country.code if country else None,
                country.phone_code if country else None,
                force_format='E164',
                raise_exception=False
            )
            
            if result:
                return result.replace('+', '')
        except Exception as e:
            _logger.debug('Phone validation failed for %s: %s', phone, str(e))
        
        return phone if phone.isdigit() else False

    # ============================================================
    # ENRICHMENT FROM WAHA
    # ============================================================
    
    def enrich_from_waha(self):
        """
        Enrich partner data from WAHA API
        
        Gets: name, avatar, status, business info
        """
        self.ensure_one()
        
        try:
            from odoo.addons.waha.tools.waha_api import WahaApi
            api = WahaApi(self.wa_account_id)
            
            # Get contact info
            contact_info = api.get_contact(self.phone_number)
            
            if not contact_info:
                _logger.warning('No contact info returned from WAHA for %s', 
                              self.phone_number)
                return
            
            # Update waha.partner fields
            vals = {}
            
            # Extract names
            wa_name = self._extract_contact_name(contact_info)
            pushname = contact_info.get('pushname') or contact_info.get('pushName')
            
            if wa_name:
                vals['wa_name'] = wa_name
            
            if pushname:
                vals['wa_pushname'] = pushname
            
            # Extract business info
            if contact_info.get('isBusiness'):
                vals['is_business'] = True
                
                business_profile = contact_info.get('businessProfile', {})
                if business_profile:
                    if business_profile.get('description'):
                        vals['business_description'] = business_profile['description']
                    if business_profile.get('category'):
                        vals['business_category'] = business_profile['category']
                    if business_profile.get('website'):
                        vals['business_website'] = business_profile['website']
            
            # Update contact ID if available
            contact_id = contact_info.get('id')
            if contact_id:
                if isinstance(contact_id, dict):
                    vals['wa_contact_id'] = contact_id.get('_serialized', 
                                                           contact_id.get('user', ''))
                else:
                    vals['wa_contact_id'] = str(contact_id)
            
            vals['is_contact_synced'] = True
            vals['last_sync_date'] = fields.Datetime.now()
            
            self.write(vals)
            _logger.info('Enriched waha.partner %s from WAHA', self.id)
            
            # Update res.partner if we have better name
            if wa_name and self.partner_id.name == self.phone_number:
                self.partner_id.write({'name': wa_name})
                _logger.info('Updated partner name to: %s', wa_name)
            
            # Download and update avatar
            avatar = self._download_contact_avatar(self.wa_account_id, contact_info)
            if avatar:
                self.partner_id.write({'image_1920': avatar})
                _logger.info('Updated partner avatar for %s', self.partner_id.name)
        
        except Exception as e:
            _logger.error('Failed to enrich contact from WAHA: %s', str(e))
    
    def _extract_contact_name(self, contact_info):
        """
        Extract best available name from WAHA contact info
        
        Priority: name > pushname > verifiedName > phone
        """
        return (
            contact_info.get('name') or
            contact_info.get('pushname') or
            contact_info.get('pushName') or
            contact_info.get('verifiedName') or
            None
        )
    
    def _download_contact_avatar(self, wa_account, contact_info):
        """
        Download contact profile picture from WAHA
        
        Returns:
            base64 encoded image or False
        """
        try:
            from odoo.addons.waha.tools.waha_api import WahaApi
            import requests
            import base64
            
            api = WahaApi(wa_account)
            
            # Get contact ID
            contact_id = contact_info.get('id')
            if isinstance(contact_id, dict):
                contact_id = contact_id.get('_serialized', contact_id.get('user'))
            
            if not contact_id:
                # Build from phone number
                phone = contact_info.get('number', self.phone_number)
                contact_id = f"{phone}@c.us"
            
            # Get profile picture URL
            profile_pic_url = api.get_contact_profile_picture(contact_id)
            
            if not profile_pic_url:
                return False
            
            # Fix localhost URLs
            if 'localhost' in profile_pic_url or '127.0.0.1' in profile_pic_url:
                profile_pic_url = profile_pic_url.replace(
                    'http://localhost:3000',
                    wa_account.waha_url.rstrip('/')
                )
                profile_pic_url = profile_pic_url.replace(
                    'http://127.0.0.1:3000',
                    wa_account.waha_url.rstrip('/')
                )
            
            # Download image
            headers = {}
            if wa_account.api_key:
                headers['X-Api-Key'] = wa_account.api_key
            
            response = requests.get(profile_pic_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            return base64.b64encode(response.content)
        
        except Exception as e:
            _logger.warning('Failed to download avatar: %s', str(e))
            return False

    # ============================================================
    # PHONE VALIDATION & UTILITIES
    # ============================================================
    
    @api.model
    def validate_phone_for_whatsapp(self, phone, wa_account):
        """
        Validate if phone number exists in WhatsApp
        
        Args:
            phone: Phone number to validate
            wa_account: waha.account record
            
        Returns:
            dict with 'exists', 'wa_id', 'name' keys
        """
        normalized_phone = self._normalize_phone(phone, wa_account)
        
        if not normalized_phone:
            return {'exists': False, 'error': 'Invalid phone number'}
        
        try:
            from odoo.addons.waha.tools.waha_api import WahaApi
            api = WahaApi(wa_account)
            
            # Check if number exists in WhatsApp
            result = api.check_number_exists(normalized_phone)
            
            return {
                'exists': result.get('exists', False),
                'wa_id': result.get('numberExists', ''),
                'name': result.get('name', ''),
            }
        
        except Exception as e:
            _logger.error('Failed to validate phone: %s', str(e))
            return {'exists': False, 'error': str(e)}
    
    def refresh_contact_info(self):
        """Manually refresh contact information from WAHA"""
        for record in self:
            record.enrich_from_waha()
    
    def action_view_partner(self):
        """Open partner form view"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
