# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import secrets
import string
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.addons.waha.tools.waha_api import WahaApi
from odoo.addons.waha.tools.waha_exception import WahaError

_logger = logging.getLogger(__name__)


class WahaAccount(models.Model):
    _name = 'waha.account'
    _inherit = ['mail.thread']
    _description = 'WAHA WhatsApp Account'

    name = fields.Char(string="Name", tracking=True, required=True)
    active = fields.Boolean(default=True, tracking=True)

    # WAHA Configuration (replaces WhatsApp Business API credentials)
    waha_url = fields.Char(
        string="WAHA Server URL",
        required=True,
        default='http://localhost:3000',
        tracking=True,
        help='Base URL of your WAHA server (e.g., http://localhost:3000)'
    )
    session_name = fields.Char(
        string="Session Name",
        required=True,
        default='default',
        tracking=True,
        help='Session name in WAHA (must be unique)'
    )
    api_key = fields.Char(
        string="API Key",
        groups='waha.group_waha_admin',
        help='API Key for WAHA authentication (if configured)'
    )

    # Account Information
    phone_uid = fields.Char(
        string="Phone Number ID",
        readonly=True,
        copy=False,
        help='Phone number ID from WAHA'
    )
    account_uid = fields.Char(
        string="Account UID",
        compute='_compute_account_uid',
        store=True,
        help='Unique account identifier'
    )

    # Webhook Configuration
    webhook_verify_token = fields.Char(
        string="Webhook Verify Token",
        compute='_compute_verify_token',
        groups='waha.group_waha_admin',
        store=True,
        help='Token to verify webhook requests'
    )
    callback_url = fields.Char(
        string="Callback URL",
        compute='_compute_callback_url',
        readonly=True,
        copy=False
    )

    # QR Code for Connection
    qr_code = fields.Binary(
        string="QR Code",
        attachment=False,
        help='QR code to scan with WhatsApp'
    )
    qr_code_expiry = fields.Datetime(
        string="QR Code Expiry",
        help='QR code expiration time'
    )

    # Connection Status
    status = fields.Selection([
        ('disconnected', 'Disconnected'),
        ('connecting', 'Connecting'),
        ('connected', 'Connected'),
        ('error', 'Error')
    ], default='disconnected', readonly=True, tracking=True, string="Status")

    # Configuration
    allowed_company_ids = fields.Many2many(
        comodel_name='res.company',
        string="Allowed Companies",
        default=lambda self: self.env.company
    )
    notify_user_ids = fields.Many2many(
        comodel_name='res.users',
        default=lambda self: self.env.user,
        domain=[('share', '=', False)],
        required=True,
        tracking=True,
        help="Users to notify when a message is received"
    )

    # Statistics
    templates_count = fields.Integer(
        string="Templates Count",
        compute='_compute_templates_count'
    )

    _sql_constraints = [
        ('phone_uid_unique', 'unique(phone_uid)',
         "The same phone number ID already exists"),
        ('session_name_unique', 'unique(session_name)',
         "Session name must be unique")
    ]

    @api.depends('session_name')
    def _compute_account_uid(self):
        """Generate account UID based on session name"""
        for account in self:
            if account.session_name:
                account.account_uid = f"waha_{account.session_name}"
            else:
                account.account_uid = False

    @api.depends('session_name')
    def _compute_verify_token(self):
        """Generate webhook verification token"""
        for rec in self:
            if rec.id and not rec.webhook_verify_token:
                rec.webhook_verify_token = ''.join(
                    secrets.choice(string.ascii_letters + string.digits)
                    for _ in range(16)
                )

    def _compute_callback_url(self):
        """Calculate webhook callback URL"""
        for account in self:
            account.callback_url = self.get_base_url() + '/waha/webhook'

    def _compute_templates_count(self):
        """Count associated templates"""
        for account in self:
            account.templates_count = self.env['waha.template'].search_count([
                ('wa_account_id', '=', account.id)
            ])

    @api.constrains('notify_user_ids')
    def _check_notify_user_ids(self):
        """Validate that at least one user is set for notifications"""
        for account in self:
            if len(account.notify_user_ids) < 1:
                raise ValidationError(_("At least one user to notify is required"))

    def action_view_templates(self):
        """View templates for this account"""
        self.ensure_one()
        return {
            'name': _('Templates'),
            'type': 'ir.actions.act_window',
            'res_model': 'waha.template',
            'view_mode': 'list,form',
            'domain': [('wa_account_id', '=', self.id)],
            'context': {'default_wa_account_id': self.id}
        }

    # ============================================================
    # CONNECTION AND SESSION MANAGEMENT
    # ============================================================

    def action_connect(self):
        """Start WAHA session connection"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            result = api.start_session()
            self.write({'status': 'connecting'})
            self.message_post(body=_('Session connection initiated'))
            return self.action_get_qr()
        except WahaError as err:
            self.write({'status': 'error'})
            error_message = str(err)
            if "Cannot connect to WAHA server" in error_message:
                raise UserError(_(
                    "Cannot connect to WAHA server at %s\n\n"
                    "Please verify:\n"
                    "• WAHA server is running\n"
                    "• The URL is correct\n"
                    "• No firewall is blocking the connection\n\n"
                    "Original error: %s"
                ) % (self.waha_url, error_message)) from err
            elif "timeout" in error_message.lower():
                raise UserError(_(
                    "WAHA server timeout at %s\n\n"
                    "The server is not responding. Please check if WAHA is running properly.\n\n"
                    "Original error: %s"
                ) % (self.waha_url, error_message)) from err
            else:
                raise UserError(_("WAHA Error: %s") % error_message) from err

    def action_get_qr(self):
        """Get QR code for scanning"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            qr_data = api.get_qr_code()

            if qr_data.get('qr'):
                # Store QR code as base64
                import base64
                qr_base64 = qr_data['qr']
                if ',' in qr_base64:
                    qr_base64 = qr_base64.split(',')[1]
                self.qr_code = qr_base64
                self.qr_code_expiry = fields.Datetime.now() + timedelta(minutes=2)

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'waha.account',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'current',
            }
        except WahaError as err:
            error_message = str(err)
            if "Cannot connect to WAHA server" in error_message:
                raise UserError(_(
                    "Cannot connect to WAHA server at %s\n\n"
                    "Please check if WAHA is running and accessible."
                ) % self.waha_url) from err
            else:
                raise UserError(_("Failed to get QR code: %s") % error_message) from err

    def action_refresh_status(self):
        """Refresh connection status from WAHA"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            status_data = api.get_session_status()

            # Map WAHA status to model status
            waha_status = status_data.get('status', 'DISCONNECTED')
            if waha_status in ['WORKING', 'CONNECTED']:
                self.status = 'connected'
                self.qr_code = False  # Clear QR when connected
                # Try to get phone number
                if 'me' in status_data:
                    self.phone_uid = status_data['me'].get('id', '')
            elif waha_status in ['STARTING', 'SCAN_QR_CODE']:
                self.status = 'connecting'
            else:
                self.status = 'disconnected'

            self.message_post(body=_('Status updated: %s', self.status))
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Status Updated'),
                    'message': _('Current status: %s', self.status),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except WahaError as err:
            self.status = 'error'
            error_message = str(err)
            if "Cannot connect to WAHA server" in error_message:
                raise UserError(_(
                    "Cannot connect to WAHA server at %s\n\n"
                    "Failed to refresh status. Please verify WAHA is running."
                ) % self.waha_url) from err
            else:
                raise UserError(_("Failed to refresh status: %s") % error_message) from err

    def action_disconnect(self):
        """Disconnect WAHA session"""
        self.ensure_one()
        try:
            api = WahaApi(self)
            api.stop_session()
            self.write({
                'status': 'disconnected',
                'qr_code': False,
            })
            self.message_post(body=_('Session disconnected'))
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Disconnected'),
                    'message': _('WhatsApp session has been disconnected'),
                    'type': 'warning',
                }
            }
        except WahaError as err:
            error_message = str(err)
            if "Cannot connect to WAHA server" in error_message:
                raise UserError(_(
                    "Cannot disconnect - WAHA server at %s is not responding\n\n"
                    "The session may already be disconnected or WAHA is not running."
                ) % self.waha_url) from err
            else:
                raise UserError(_("Failed to disconnect: %s") % error_message) from err

    def button_sync_waha_templates(self):
        """
        Sync templates from WAHA
        Note: WAHA doesn't have template approval system like WhatsApp Business API
        Templates are created locally in Odoo
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Information"),
                'message': _("WAHA does not require template synchronization. "
                           "Create templates directly in Odoo."),
                'type': 'info',
                'sticky': False,
            }
        }

    # ============================================================
    # MESSAGE SENDING
    # ============================================================

    def _send_waha_message(self, number, message_type='text', **kwargs):
        """
        Send message through WAHA API
        
        Args:
            number: Phone number in E164 format
            message_type: 'text', 'image', 'document', 'video', 'audio'
            **kwargs: body, media_data, caption, filename, mimetype, etc.
        
        Returns:
            dict: Response from WAHA API with message ID
        """
        self.ensure_one()

        if self.status != 'connected':
            raise UserError(_('WhatsApp account is not connected. Please connect first.'))

        try:
            api = WahaApi(self)

            # Format number to WhatsApp chat ID
            chat_id = f"{number.replace('+', '')}@c.us"

            # Send based on type
            if message_type == 'text':
                result = api.send_text(chat_id, kwargs.get('body', ''))
            elif message_type == 'image':
                result = api.send_image(
                    chat_id,
                    kwargs.get('media_data'),
                    kwargs.get('caption')
                )
            elif message_type == 'document':
                result = api.send_file(
                    chat_id,
                    kwargs.get('media_data'),
                    kwargs.get('filename'),
                    kwargs.get('mimetype')
                )
            elif message_type == 'video':
                result = api.send_video(
                    chat_id,
                    kwargs.get('media_data'),
                    kwargs.get('caption')
                )
            elif message_type == 'audio':
                result = api.send_audio(
                    chat_id,
                    kwargs.get('media_data')
                )
            else:
                raise UserError(_('Unsupported message type: %s', message_type))

            return result

        except WahaError as err:
            _logger.error('Error sending WAHA message: %s', str(err))
            error_message = str(err)
            if "Cannot connect to WAHA server" in error_message:
                raise UserError(_(
                    "Cannot send message - WAHA server at %s is not responding\n\n"
                    "Please verify WAHA is running before sending messages."
                ) % self.waha_url) from err
            else:
                raise UserError(_("Failed to send WhatsApp message: %s") % error_message) from err

    # ============================================================
    # CRON AND MAINTENANCE
    # ============================================================

    @api.model
    def _cron_check_connection_status(self):
        """Cron job to check connection status of all accounts"""
        accounts = self.search([('status', 'in', ['connected', 'connecting'])])
        for account in accounts:
            try:
                account.action_refresh_status()
            except Exception as e:
                _logger.error(
                    'Error checking WAHA account %s status: %s',
                    account.name, str(e)
                )
