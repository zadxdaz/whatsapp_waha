# -*- coding: utf-8 -*-
from odoo import fields, models


class ResUsersSettings(models.Model):
    _inherit = 'res.users.settings'

    is_discuss_sidebar_category_whatsapp_open = fields.Boolean(
        string='WhatsApp Category Open',
        default=True,
        help="If checked, the WhatsApp category is open in the discuss sidebar"
    )
