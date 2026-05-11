# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import models
from odoo.addons.mail.tools.discuss import Store

_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = 'mail.message'

    def _to_store(self, store: Store, /, *, fields=None, format_reply=True, msg_vals=None,
                  for_current_user=False, add_followers=False, followers=None):
        super()._to_store(
            store, fields=fields, format_reply=format_reply, msg_vals=msg_vals,
            for_current_user=for_current_user, add_followers=add_followers, followers=followers
        )
        if not self:
            return

        waha_msgs = self.env['waha.message'].sudo().search([
            ('mail_message_id', 'in', self.ids),
            ('message_type', '=', 'outbound'),
        ])
        if not waha_msgs:
            return

        state_by_mail_id = {w.mail_message_id.id: w.state for w in waha_msgs}

        for message in self:
            waha_state = state_by_mail_id.get(message.id)
            if waha_state:
                store.add(message, {'waha_delivery_state': waha_state})
