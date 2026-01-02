/** @odoo-module **/

import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";

patch(Thread.prototype, {
    get channelTypeLabel() {
        if (this.channel_type === "whatsapp") {
            return "WhatsApp";
        }
        return super.channelTypeLabel;
    },
});
