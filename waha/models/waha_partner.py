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
        related='partner_id.mobile',
        string="Phone Number",
        readonly=True,
        store=True,
        help="Phone number from partner (E.164 format)"
    )
    
    lid = fields.Char(
        string="WhatsApp LID",
        compute='_compute_lid',
        store=True,
        readonly=False,
        index=True,
        help="WhatsApp Long ID (LID) - unique identifier"
    )
    
    wa_contact_id = fields.Char(
        string="WhatsApp Contact ID",
        index=True,
        help="WAHA contact identifier from API (e.g., 123456@c.us or 123456@lid)"
    )
    
    # WhatsApp-specific fields
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
         "Each partner can only have one WhatsApp contact per account."),
    ]

    # ============================================================
    # COMPUTED FIELDS - LID/PHONE RELATIONSHIP
    # ============================================================
    
    @api.depends('partner_id.mobile', 'partner_id.phone', 'wa_account_id')
    def _compute_lid(self):
        """
        Auto-compute LID from phone_number using WAHA API
        
        If we have a phone_number but no LID, automatically fetch
        the LID from WAHA using the API endpoint.
        """
        for partner in self:
            # Skip if already has LID or no phone
            if partner.lid or not partner.phone_number or not partner.wa_account_id:
                continue
            
            try:
                from odoo.addons.waha.tools.waha_api import WahaApi
                api = WahaApi(partner.wa_account_id)
                
                # Normalize phone before API call
                normalized = partner._normalize_phone(partner.phone_number, partner.wa_account_id)
                if not normalized:
                    continue
                
                # Get LID from phone
                result = api.get_lid_by_phone(normalized)
                
                if result and result.get('lid'):
                    lid_value = str(result['lid']).replace('@lid', '').replace('@c.us', '').replace('@g.us', '')
                    _logger.info('Auto-fetched LID for phone %s: %s', normalized, lid_value)
                    partner.lid = lid_value
                else:
                    _logger.debug('No LID found for phone %s', normalized)
                    
            except Exception as e:
                _logger.warning('Failed to fetch LID for phone %s: %s', 
                              partner.phone_number, str(e))
    
    @api.onchange('lid')
    def _onchange_lid_fetch_phone(self):
        """
        When LID is manually set, try to update partner phone
        """
        if self.lid and not self.partner_id.mobile and self.wa_account_id:
            try:
                from odoo.addons.waha.tools.waha_api import WahaApi
                api = WahaApi(self.wa_account_id)
                
                # Get phone from LID
                result = api.get_phone_by_lid(self.lid)
                
                if result and result.get('pn'):
                    phone = result['pn']
                    _logger.info('Auto-fetched phone for LID %s: %s', self.lid, phone)
                    self.partner_id.mobile = f"+{phone}"
                    
            except Exception as e:
                _logger.warning('Failed to fetch phone for LID %s: %s', 
                              self.lid, str(e))

    # ============================================================
    # CRUD & LIFECYCLE
    # ============================================================
    
    @api.model
    def find_or_create_by_lid_or_phone(self, lid=None, phone=None, wa_account=None, auto_enrich=True):
        """
        Find or create waha.partner by LID or phone (trying LID first)
        
        Args:
            lid: WhatsApp LID
            phone: Phone number
            wa_account: waha.account record
            auto_enrich: Whether to auto-enrich from WAHA
        
        Returns:
            waha.partner record (or empty recordset if invalid)
        """
        if not wa_account:
            _logger.error('wa_account is required')
            return self.env['waha.partner']
        
        # Don't create partners for group IDs
        if phone and '@g.us' in str(phone):
            _logger.warning('Attempted to create partner for group ID: %s', phone)
            return self.env['waha.partner']
        
        waha_partner = None
        
        # Normalize LID (remove @lid suffix)
        if lid:
            lid = str(lid).replace('@lid', '').replace('@c.us', '').replace('@g.us', '')
        
        # Normalize phone
        normalized_phone = None
        if phone:
            normalized_phone = self._normalize_phone(phone, wa_account)
        
        # BEFORE searching, try to enrich to get the missing identifier
        # This prevents creating duplicates when we only have one identifier
        if auto_enrich and wa_account.status == 'connected':
            # If we only have LID, try to get phone
            if lid and not normalized_phone:
                try:
                    from odoo.addons.waha.tools.waha_api import WahaApi
                    api = WahaApi(wa_account)
                    result = api.get_phone_by_lid(lid)
                    if result and result.get('pn'):
                        normalized_phone = result['pn']
                        _logger.info('Enriched: got phone %s from LID %s', normalized_phone, lid)
                except Exception as e:
                    _logger.debug('Could not fetch phone from LID %s: %s', lid, str(e))
            
            # If we only have phone, try to get LID
            elif normalized_phone and not lid:
                try:
                    from odoo.addons.waha.tools.waha_api import WahaApi
                    api = WahaApi(wa_account)
                    result = api.get_lid_by_phone(normalized_phone)
                    if result and result.get('lid'):
                        lid = str(result['lid']).replace('@lid', '').replace('@c.us', '').replace('@g.us', '')
                        _logger.info('Enriched: got LID %s from phone %s', lid, normalized_phone)
                except Exception as e:
                    _logger.debug('Could not fetch LID from phone %s: %s', normalized_phone, str(e))
        
        # 1. Try to find by LID first (more reliable)
        if lid:
            waha_partner = self.search([
                ('lid', '=', lid),
                ('wa_account_id', '=', wa_account.id),
            ], limit=1)
            
            if waha_partner:
                _logger.info('Found waha.partner by LID %s: %s', lid, waha_partner.id)
                # Update partner phone if we have it and it's missing
                if normalized_phone and not waha_partner.partner_id.mobile:
                    _logger.info('Updating partner %s with phone %s', waha_partner.partner_id.id, normalized_phone)
                    waha_partner.partner_id.sudo().write({'mobile': f"+{normalized_phone}"})
                return waha_partner
        
        # 2. Try to find by phone number
        if normalized_phone:
            waha_partner = self.search([
                ('phone_number', '=', normalized_phone),
                ('wa_account_id', '=', wa_account.id),
            ], limit=1)
            
            if waha_partner:
                _logger.info('Found waha.partner by phone %s: %s', 
                           normalized_phone, waha_partner.id)
                # Update LID if we have it and it's missing
                if lid and not waha_partner.lid:
                    _logger.info('Updating waha.partner %s with LID %s', waha_partner.id, lid)
                    waha_partner.sudo().write({'lid': lid})
                return waha_partner
        
        # 3. Not found - create new partner
        res_partner, _ = self._create_partner_with_lid_or_phone(
            lid=lid, 
            phone=normalized_phone,  # Use normalized phone
            wa_account=wa_account, 
            auto_enrich=True  # Let it enrich with contact_info
        )
        
        # Return the waha.partner linked to the res.partner
        if res_partner:
            return self.search([
                ('partner_id', '=', res_partner.id),
                ('wa_account_id', '=', wa_account.id)
            ], limit=1)
        
        return self.env['waha.partner']
    
    def _create_partner_with_lid_or_phone(self, lid=None, phone=None, wa_account=None, auto_enrich=True):
        """
        Create new partner with LID and/or phone
        
        Args:
            lid: WhatsApp LID
            phone: Phone number (already normalized)
            wa_account: waha.account record
            auto_enrich: Whether to auto-enrich from WAHA
            
        Returns:
            tuple: (res.partner record, contact_info dict or None)
        """
        normalized_phone = phone  # Already normalized by caller
        
        # Determine display name
        contact_name = None
        contact_image = None
        contact_info = None
        
        # Try to enrich from WAHA before creating
        if auto_enrich and (normalized_phone or lid):
            try:
                from odoo.addons.waha.tools.waha_api import WahaApi
                api = WahaApi(wa_account)
                
                # Get contact info by phone or LID
                if normalized_phone:
                    contact_info = api.get_contact(normalized_phone)
                elif lid:
                    contact_info = api.get_contact(lid)
                
                if contact_info:
                    extracted_name = self._extract_contact_name(contact_info)
                    if extracted_name:
                        contact_name = extracted_name
                    contact_image = self._download_contact_avatar(wa_account, contact_info)
            except Exception as e:
                _logger.warning('Could not enrich contact from WAHA: %s', str(e))
        
        # Fallback name
        if not contact_name:
            if normalized_phone:
                contact_name = f"WhatsApp +{normalized_phone}"
            elif lid:
                contact_name = f"WhatsApp {lid[:10]}..."
            else:
                contact_name = "WhatsApp Contact"
        
        # Search for existing res.partner by phone number before creating
        partner = None
        if normalized_phone:
            partner = self.env['res.partner'].sudo().search([
                '|',
                ('mobile', 'ilike', normalized_phone),
                ('phone', 'ilike', normalized_phone),
            ], limit=1)
            
            if partner:
                _logger.info('Found existing partner %s with phone %s', partner.id, normalized_phone)
        
        # Create res.partner only if not found
        if not partner:
            partner_vals = {'name': contact_name}
            
            if normalized_phone:
                partner_vals['mobile'] = f"+{normalized_phone}"
                partner_vals['phone'] = f"+{normalized_phone}"
            
            if contact_image:
                partner_vals['image_1920'] = contact_image
            
            partner = self.env['res.partner'].sudo().create(partner_vals)
            _logger.info('Created new partner %s (LID=%s, phone=%s)', 
                        partner.id, lid, normalized_phone)
        else:
            # Update existing partner with enriched data if available
            update_vals = {}
            if contact_image and not partner.image_1920:
                update_vals['image_1920'] = contact_image
                _logger.info('Updated partner %s with avatar', partner.id)
            
            # Update name if current name is generic and we have better one
            if contact_name and contact_name != f"WhatsApp +{normalized_phone}":
                if not partner.name or 'WhatsApp' in partner.name or partner.name == normalized_phone:
                    update_vals['name'] = contact_name
                    _logger.info('Updated partner %s name to: %s', partner.id, contact_name)
            
            if update_vals:
                partner.sudo().write(update_vals)
        
        # Check if waha.partner already exists before creating
        existing_waha_partner = self.search([
            ('partner_id', '=', partner.id),
            ('wa_account_id', '=', wa_account.id),
        ], limit=1)
        
        if existing_waha_partner:
            _logger.info('Found existing waha.partner %s for partner %s, updating it', 
                        existing_waha_partner.id, partner.id)
            
            # Update with new data if available
            update_vals = {}
            if lid and not existing_waha_partner.lid:
                update_vals['lid'] = lid
            
            if update_vals:
                existing_waha_partner.sudo().write(update_vals)
                _logger.info('Updated waha.partner %s with new data', existing_waha_partner.id)
            
            return partner, contact_info
        
        # Create waha.partner link
        waha_partner_vals = {
            'partner_id': partner.id,
            'wa_account_id': wa_account.id,
        }
        
        if lid:
            waha_partner_vals['lid'] = lid
        
        waha_partner = self.create(waha_partner_vals)
        _logger.info('Created waha.partner link %s', waha_partner.id)
        
        # Enrich if requested (reuse contact_info to avoid duplicate API call)
        if auto_enrich:
            waha_partner.enrich_from_waha(contact_info=contact_info)
        
        return partner, contact_info
    
    @api.model
    def find_or_create_by_phone(self, phone, wa_account, auto_enrich=True):
        """
        Find existing partner or create new one from phone number
        (Backward compatibility wrapper)
        
        Args:
            phone: Phone number (any format)
            wa_account: waha.account record
            auto_enrich: Whether to automatically enrich from WAHA
            
        Returns:
            waha.partner record
        """
        return self.find_or_create_by_lid_or_phone(
            lid=None,
            phone=phone,
            wa_account=wa_account,
            auto_enrich=auto_enrich
        )
    
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
            # Use default company for country context
            country = self.env.company.country_id if self.env.company else False
            
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
    
    def enrich_from_waha(self, contact_info=None):
        """
        Enrich partner data from WAHA API
        
        Args:
            contact_info: Optional dict with contact data from WAHA API.
                         If not provided, will fetch from API.
        
        Gets: name, avatar, status, business info
        """
        self.ensure_one()
        
        try:
            # Use provided contact_info or fetch from API
            if not contact_info:
                from odoo.addons.waha.tools.waha_api import WahaApi
                api = WahaApi(self.wa_account_id)
                
                identifier = self.wa_contact_id if self.wa_contact_id else (
                    self.lid if self.lid else self._normalize_phone(self.phone_number, self.wa_account_id)
                )
                contact_info = api.get_contact(identifier)
            
            if not contact_info:
                _logger.warning('No contact info available for enrichment')
                return
            # Update waha.partner fields
            vals = {}
            
            # Extract contact ID from API response
            contact_id = contact_info.get('id')
            if contact_id:
                if isinstance(contact_id, dict):
                    wa_contact_id = contact_id.get('_serialized', contact_id.get('user', ''))
                else:
                    wa_contact_id = str(contact_id)
                
                if wa_contact_id:
                    vals['wa_contact_id'] = wa_contact_id
                    _logger.info('Got wa_contact_id from WAHA: %s', wa_contact_id)
            
            # Extract and update partner name
            wa_name = self._extract_contact_name(contact_info)
            _logger.info('Extracted name from WAHA: %s', wa_name)
            if wa_name:
                self.partner_id.sudo().write({'name': wa_name})
                _logger.info('Updated partner name to: %s', wa_name)
            
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
            
            vals['is_contact_synced'] = True
            vals['last_sync_date'] = fields.Datetime.now()
            
            self.write(vals)
            _logger.info('Enriched waha.partner %s from WAHA', self.id)
            
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
    
    def get_or_fetch_wa_contact_id(self):
        """
        Get wa_contact_id, fetching from WAHA if not available
        
        Returns:
            str: WhatsApp contact ID or False
        """
        self.ensure_one()
        
        if self.wa_contact_id:
            return self.wa_contact_id
        
        # Try to get from WAHA
        try:
            from odoo.addons.waha.tools.waha_api import WahaApi
            api = WahaApi(self.wa_account_id)
            
            identifier = self.lid if self.lid else self._normalize_phone(self.phone_number, self.wa_account_id)
            if not identifier:
                return False
            
            contact_info = api.get_contact(identifier)
            if contact_info:
                contact_id = contact_info.get('id')
                if contact_id:
                    if isinstance(contact_id, dict):
                        wa_contact_id = contact_id.get('_serialized', contact_id.get('user', ''))
                    else:
                        wa_contact_id = str(contact_id)
                    
                    if wa_contact_id:
                        self.sudo().write({'wa_contact_id': wa_contact_id})
                        return wa_contact_id
        except Exception as e:
            _logger.warning('Failed to fetch wa_contact_id: %s', str(e))
        
        return False
    
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
                # Build from phone number or LID
                if self.lid:
                    contact_id = f"{self.lid}@lid"
                elif self.phone_number:
                    phone = self._normalize_phone(self.phone_number, wa_account)
                    contact_id = f"{phone}@c.us" if phone else None
                
                if not contact_id:
                    return False
            
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
        """Manually refresh contact information from WAHA (bulk action)"""
        success_count = 0
        error_count = 0
        
        for record in self:
            try:
                record.enrich_from_waha()
                success_count += 1
                _logger.info('Successfully refreshed contact %s', record.display_name)
            except Exception as e:
                error_count += 1
                _logger.error('Failed to refresh contact %s: %s', record.display_name, str(e))
        
        # Show notification if called from UI (multiple records)
        if len(self) > 1 or self.env.context.get('show_notification'):
            if success_count > 0:
                message = f'Refreshed {success_count} contact(s)'
                if error_count > 0:
                    message += f' ({error_count} failed)'
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Contacts Updated',
                        'message': message,
                        'type': 'success' if error_count == 0 else 'warning',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': f'Failed to refresh contacts ({error_count} errors)',
                        'type': 'danger',
                        'sticky': False,
                    }
                }
    
    def action_fetch_wa_contact_id(self):
        """
        Fetch and update wa_contact_id from WAHA API
        Can be executed on multiple records
        """
        success_count = 0
        error_count = 0
        
        for record in self:
            try:
                from odoo.addons.waha.tools.waha_api import WahaApi
                api = WahaApi(record.wa_account_id)
                
                # Use LID if available, otherwise phone
                identifier = record.lid if record.lid else False # We require LID or phone to fetch contact ID
                
                if not identifier:
                    _logger.warning('No identifier (LID/phone) for waha.partner %s', record.id)
                    error_count += 1
                    continue
                
                # Get contact info from WAHA
                contact_info = api.get_contact_id_by_lid(identifier)
                
                if not contact_info:
                    _logger.warning('No contact info from WAHA for %s', identifier)
                    error_count += 1
                    continue
                
                # Extract contact ID
                contact_id = contact_info.get('id') or contact_info.get('pn')
                if contact_id:
                    if isinstance(contact_id, dict):
                        wa_contact_id = contact_id.get('_serialized', contact_id.get('user', ''))
                    else:
                        wa_contact_id = str(contact_id)
                    
                    if wa_contact_id:
                        record.sudo().write({'wa_contact_id': wa_contact_id})
                        _logger.info('Updated wa_contact_id for %s: %s', record.display_name, wa_contact_id)
                        success_count += 1
                    else:
                        _logger.warning('Empty wa_contact_id for %s', identifier)
                        error_count += 1
                else:
                    _logger.warning('No contact ID in response for %s', identifier)
                    error_count += 1
                    
            except Exception as e:
                _logger.error('Failed to fetch wa_contact_id for %s: %s', record.display_name, str(e))
                error_count += 1
        
        # Show notification
        if success_count > 0:
            message = f'Updated {success_count} contact(s)'
            if error_count > 0:
                message += f' ({error_count} failed)'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'WhatsApp Contact ID Updated',
                    'message': message,
                    'type': 'success' if error_count == 0 else 'warning',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Failed to update contact IDs ({error_count} errors)',
                    'type': 'danger',
                    'sticky': False,
                }
            }
    
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
