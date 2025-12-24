# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import json


class WahaTemplate(models.Model):
    _name = 'waha.template'
    _description = 'WhatsApp Message Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    name = fields.Char('Template Name', required=True, tracking=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    wa_account_id = fields.Many2one(
        'waha.account', 
        string='WhatsApp Account',
        required=True,
        ondelete='cascade'
    )
    
    # Template Content
    body = fields.Html('Body', required=True, sanitize=False)
    header_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
    ], string='Header Type')
    header_text = fields.Char('Header Text')
    header_attachment_id = fields.Many2one('ir.attachment', string='Header Attachment')
    
    footer_text = fields.Char('Footer Text')
    
    # Variables
    variable_ids = fields.One2many(
        'waha.template.variable',
        'template_id',
        string='Variables'
    )
    
    # Buttons
    button_ids = fields.One2many(
        'waha.template.button',
        'template_id',
        string='Buttons'
    )
    
    # Model Integration
    model = fields.Char('Model')
    model_id = fields.Many2one('ir.model', string='Applies to', 
                               domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model', string='Model Name', 
                             readonly=True, store=True)
    
    # Statistics
    messages_count = fields.Integer('Messages', compute='_compute_messages_count')
    
    # Language
    lang = fields.Selection(
        selection=lambda self: self.env['res.lang'].get_installed(),
        string='Language',
        default=lambda self: self.env.lang
    )
    
    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    active = fields.Boolean(default=True)

    @api.depends('wa_account_id')
    def _compute_messages_count(self):
        """Compute number of messages sent with this template"""
        for template in self:
            template.messages_count = self.env['waha.message'].search_count([
                ('wa_template_id', '=', template.id)
            ])

    @api.model_create_multi
    def create(self, vals_list):
        """Override to extract variables from body"""
        templates = super().create(vals_list)
        for template in templates:
            template._extract_variables_from_body()
        return templates

    def write(self, vals):
        """Override to update variables when body changes"""
        res = super().write(vals)
        if 'body' in vals:
            for template in self:
                template._extract_variables_from_body()
        return res

    def _extract_variables_from_body(self):
        """Extract {{variable}} placeholders from body and create variable records"""
        self.ensure_one()
        import re
        
        # Find all {{variable_name}} patterns
        body_text = self.body or ''
        pattern = r'\{\{(\w+)\}\}'
        variables = re.findall(pattern, body_text)
        
        # Get existing variables
        existing_vars = {var.name: var for var in self.variable_ids}
        
        # Create new variables
        for var_name in set(variables):
            if var_name not in existing_vars:
                self.env['waha.template.variable'].create({
                    'template_id': self.id,
                    'name': var_name,
                    'field_name': var_name.lower(),
                    'demo_value': f'Sample {var_name}',
                })

    def action_approve(self):
        """Approve template"""
        self.write({'status': 'approved'})

    def action_reset_to_draft(self):
        """Reset to draft"""
        self.write({'status': 'draft'})

    def action_view_messages(self):
        """View messages using this template"""
        self.ensure_one()
        return {
            'name': _('Messages'),
            'type': 'ir.actions.act_window',
            'res_model': 'waha.message',
            'view_mode': 'list,form',
            'domain': [('wa_template_id', '=', self.id)],
            'context': {'default_wa_template_id': self.id}
        }

    def _get_formatted_body(self, record=None):
        """
        Format template body replacing variables with actual values
        
        :param record: Record to get values from (res.partner, sale.order, etc)
        :return: Formatted text
        """
        self.ensure_one()
        body = self.body or ''
        
        if not record:
            return body
        
        # Replace variables
        for variable in self.variable_ids:
            placeholder = f'{{{{{variable.name}}}}}'
            value = variable._get_value(record)
            body = body.replace(placeholder, str(value or ''))
        
        return body


class WahaTemplateVariable(models.Model):
    _name = 'waha.template.variable'
    _description = 'WhatsApp Template Variable'
    _order = 'sequence, name'

    template_id = fields.Many2one(
        'waha.template',
        string='Template',
        required=True,
        ondelete='cascade'
    )
    name = fields.Char('Variable Name', required=True)
    sequence = fields.Integer('Sequence', default=10)
    
    # Field mapping
    field_name = fields.Char('Field Name', 
                             help='Technical field name from the model')
    field_type = fields.Selection([
        ('char', 'Text'),
        ('integer', 'Integer'),
        ('float', 'Float'),
        ('date', 'Date'),
        ('datetime', 'Datetime'),
        ('boolean', 'Boolean'),
        ('many2one', 'Many2one'),
    ], string='Field Type', default='char')
    
    demo_value = fields.Char('Demo Value', 
                             help='Value shown in preview')

    _sql_constraints = [
        ('name_template_unique', 'unique(name, template_id)',
         'Variable name must be unique per template!')
    ]

    def _get_value(self, record):
        """
        Get variable value from record
        
        :param record: Record to extract value from
        :return: Formatted value
        """
        self.ensure_one()
        
        if not record or not self.field_name:
            return self.demo_value or ''
        
        try:
            value = record[self.field_name]
            
            # Format based on field type
            if self.field_type == 'date' and value:
                return value.strftime('%d/%m/%Y')
            elif self.field_type == 'datetime' and value:
                return value.strftime('%d/%m/%Y %H:%M')
            elif self.field_type == 'many2one' and value:
                return value.display_name
            elif self.field_type == 'float':
                return f'{value:.2f}'
            
            return str(value) if value else ''
            
        except Exception:
            return self.demo_value or ''


class WahaTemplateButton(models.Model):
    _name = 'waha.template.button'
    _description = 'WhatsApp Template Button'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'waha.template',
        string='Template',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer('Sequence', default=10)
    
    button_type = fields.Selection([
        ('quick_reply', 'Quick Reply'),
        ('url', 'URL'),
        ('phone', 'Phone Number'),
    ], string='Button Type', required=True, default='quick_reply')
    
    name = fields.Char('Button Text', required=True)
    
    # For URL buttons
    url = fields.Char('URL')
    url_type = fields.Selection([
        ('static', 'Static'),
        ('dynamic', 'Dynamic'),
    ], string='URL Type', default='static')
    
    # For Phone buttons
    phone_number = fields.Char('Phone Number')
    
    # For Quick Reply
    payload = fields.Char('Payload')

    @api.constrains('button_type', 'url', 'phone_number')
    def _check_button_data(self):
        """Validate button configuration"""
        for button in self:
            if button.button_type == 'url' and not button.url:
                raise ValidationError(_('URL is required for URL buttons'))
            if button.button_type == 'phone' and not button.phone_number:
                raise ValidationError(_('Phone number is required for phone buttons'))
