# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'WAHA Messaging',
    'category': 'Marketing/WhatsApp',
    'summary': 'WhatsApp Integration using WAHA (WhatsApp HTTP API)',
    'version': '1.0',
    'description': """
        This module integrates Odoo with WAHA (WhatsApp HTTP API) to use WhatsApp messaging service.
        WAHA is a self-hosted WhatsApp HTTP API that you can run on your own server.
        
        Features:
        - Send and receive WhatsApp messages
        - Message templates with variables
        - Integration with discuss channels
        - Webhook support for incoming messages
        - QR code authentication
        - Multi-session support
    """,
    'depends': ['mail', 'phone_validation'],
    'data': [
        # Security
        'security/ir_module_category_data.xml',
        'security/res_groups.xml',
        'security/ir_rules.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/ir_actions_server_data.xml',
        'data/ir_cron_data.xml',
        
        # Wizard
        'wizard/waha_composer_views.xml',
        
        # Views
        'views/waha_account_views.xml',
        'views/waha_message_views.xml',
        'views/waha_template_views.xml',
        'views/res_partner_views.xml',
        'views/waha_menus.xml',
    ],
    'demo': [
        'data/waha_demo.xml',
    ],
    'external_dependencies': {
        'python': ['phonenumbers', 'requests'],
    },
    'assets': {
        'web.assets_backend': [
            'waha/static/src/scss/*.scss',
            'waha/static/src/core/common/**/*',
            'waha/static/src/core/web/**/*',
            'waha/static/src/components/**/*',
            'waha/static/src/views/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
